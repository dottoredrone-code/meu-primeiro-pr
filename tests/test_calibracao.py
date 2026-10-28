import json
import tempfile
import unittest
from pathlib import Path

from torralles_studio.calibracao import calibrar, carregar_ancoras, registrar_notas
from torralles_studio.referencias import _prompt, arquivo_da_analise, identificar


def _analise(i, juiz, suas, provedor="gemini_video"):
    return {"id": f"v{i}", "categoria": "A", "provedor": provedor,
            "potencial": {c: {"nota": n, "evidencia": "ok"} for c, n in juiz.items()}, "notas_diego": suas}


class TestCalibrar(unittest.TestCase):
    def test_juiz_generoso_rigido_e_alinhado(self):
        generoso = [_analise(i, {"gancho": 90, "fluxo": 80}, {"gancho": 7, "fluxo": 6.5}) for i in range(3)]
        r = calibrar(generoso)
        self.assertEqual(r["videos"], 3)
        self.assertEqual(r["por_juiz"]["gemini_video"]["veredito"], "mais generoso")
        self.assertAlmostEqual(r["geral"]["media_diferenca"], 1.75)
        self.assertIn("suba a nota mínima em 18 pontos", r["recomendacoes"][0])  # escala 0–100 do config
        self.assertIn("70 → 88", r["recomendacoes"][0])

        rigido = [_analise(i, {"valor": 50}, {"valor": 7}) for i in range(3)]
        self.assertEqual(calibrar(rigido)["geral"]["veredito"], "mais rígido")

        alinhado = [_analise(i, {"gancho": 80}, {"gancho": 8.5}) for i in range(3)]
        r = calibrar(alinhado)
        self.assertEqual(r["geral"]["veredito"], "alinhado")
        self.assertEqual(r["recomendacoes"], ["juiz alinhado com você: nada a ajustar"])

    def test_discorda_muito_pede_ancora(self):
        notas = [(90, 4), (30, 8), (85, 3)]  # média perto de zero, mas discorda em cada vídeo
        r = calibrar([_analise(i, {"tendencia": j}, {"tendencia": s}) for i, (j, s) in enumerate(notas)])
        self.assertEqual(r["por_juiz"]["gemini_video"]["veredito"], "discorda muito")
        self.assertTrue(any("tendencia" in x and "âncora" in x for x in r["recomendacoes"]))

    def test_diferenca_constante_e_vies_nao_discordancia(self):  # verificador: +2,5 sempre = generoso
        r = calibrar([_analise(i, {"gancho": 85, "fluxo": 75}, {"gancho": 6, "fluxo": 5}) for i in range(3)])
        self.assertEqual(r["por_juiz"]["gemini_video"]["veredito"], "mais generoso")
        self.assertIn("25 pontos", r["recomendacoes"][0])
        self.assertFalse(any("âncora" in x for x in r["recomendacoes"]))

    def test_arquivo_estragado_nao_derruba(self):
        dados = [_analise(i, {"gancho": 80}, {"gancho": 8}) for i in range(3)]
        dados += ["lixo", {"potencial": {"gancho": 5}, "notas_diego": {"gancho": 5}}, {"notas_diego": "x"}]
        self.assertEqual(calibrar(dados)["videos"], 3)

    def test_por_juiz_e_minimo_de_videos(self):
        dados = [_analise(0, {"gancho": 90}, {"gancho": 6}, "a"), _analise(1, {"gancho": 60}, {"gancho": 6}, "b"),
                 _analise(2, {"gancho": 60}, {"gancho": 6}, "b"), _analise(3, {"gancho": 70}, {})]
        r = calibrar(dados)
        self.assertEqual(set(r["por_juiz"]), {"a", "b"})
        self.assertEqual(r["videos"], 3)  # o vídeo sem a sua nota não conta
        with self.assertRaises(ValueError):
            calibrar(dados[:2])
        with self.assertRaises(ValueError):  # nota estragada não conta
            calibrar([_analise(i, {"gancho": float("nan")}, {"gancho": 5}) for i in range(3)])


class TestNotasEAncoras(unittest.TestCase):
    def test_registrar_notas_na_analise_existente(self):
        link = "https://www.youtube.com/shorts/abc123?si=x"
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):  # ainda não analisado
                registrar_notas(d, link, "A", {"gancho": 8})
            _, ident, _ = identificar(link)
            arq = arquivo_da_analise(d, "A", ident)
            arq.parent.mkdir(parents=True)
            arq.write_text(json.dumps({"id": ident, "categoria": "A"}), encoding="utf-8")
            registrar_notas(d, "https://youtu.be/abc123", "A", {"gancho": 8})  # outro link do mesmo vídeo
            registrar_notas(d, link, "A", {"fluxo": 6})
            self.assertEqual(json.loads(arq.read_text(encoding="utf-8"))["notas_diego"], {"gancho": 8.0, "fluxo": 6.0})
            for ruim in ({}, {"gancho": 11}, {"gancho": True}, {"inventado": 5}, {"valor": float("nan")}):
                with self.assertRaises(ValueError):
                    registrar_notas(d, link, "A", ruim)

    def test_ancoras_aprovadas_entram_no_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "ancoras.toml"
            arq.write_text('[A]\ngancho = "nota 90: número no 1º segundo"\nfluxo = ""\nlixo = "x"\n', encoding="utf-8")
            ancoras = carregar_ancoras(arq, "A")
            self.assertEqual(ancoras, {"gancho": "nota 90: número no 1º segundo"})
            self.assertEqual(carregar_ancoras(arq, "B"), {})
            self.assertEqual(carregar_ancoras(Path(d) / "nada.toml", "A"), {})
        self.assertIn("número no 1º segundo", _prompt("A", None, ancoras))
        self.assertNotIn("Âncoras aprovadas", _prompt("A"))

    def test_config_de_ancoras_do_repositorio_e_valido(self):
        raiz = Path(__file__).resolve().parent.parent
        self.assertIsInstance(carregar_ancoras(raiz / "config" / "ancoras.toml", "A"), dict)


if __name__ == "__main__":
    unittest.main()

import json
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from torralles_studio.provedores.base import Provedor
from torralles_studio.referencias import LIMITE_TRECHO, _duracao_maxima, analisar_referencia, validar_analise
from torralles_studio.roteador import Roteador

ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "referencias.toml"


class TestCanais(unittest.TestCase):  # K11
    def setUp(self):
        self.dados = tomllib.loads(ARQUIVO.read_text(encoding="utf-8"))["categorias"]

    def test_seis_categorias_da_spec_09(self):
        self.assertEqual(sorted(self.dados), ["A", "B", "C", "D", "E", "F"])

    def test_categoria_a_completa(self):
        canais = self.dados["A"]["canais"]
        self.assertEqual(len([c for c in canais if c["status"] != "pendente"]), 5)
        self.assertEqual(self.dados["A"]["negativos"], 2)

    def test_campos_validos(self):
        for cat, d in self.dados.items():
            for c in d["canais"]:
                self.assertIn(c["status"], ("aprovado", "sugestao", "pendente"), (cat, c))
                self.assertIn(c["idioma"], ("en", "pt-BR"), (cat, c))
                if "url" in c:
                    self.assertTrue(c["url"].startswith("https://www.youtube.com/"), (cat, c))

BOA = {
    "duracao_s": 42, "cortes_por_minuto": 18, "duracao_media_plano_s": 3.3, "palavras_por_segundo": 2.8,
    "musica": {"tem": True, "abaixo_da_voz": True},
    "estrutura": [{"parte": "gancho", "inicio_s": 0, "fim_s": 3, "resumo": "pergunta sobre o céu"},
                  {"parte": "desenvolvimento", "inicio_s": 3, "fim_s": 38, "resumo": "explica a luz"},
                  {"parte": "cta", "inicio_s": 38, "fim_s": 42, "resumo": "pede para seguir"},
                  {"parte": "inventada", "inicio_s": 1, "fim_s": 2}],
    "gancho": {"tipo": "pergunta_concreta", "momento_s": 0, "trecho": "Por que o céu é azul? " * 20},
    "potencial": {c: {"nota": n, "evidencia": "ok"} for c, n in
                  (("gancho", 90), ("fluxo", 80), ("valor", 70), ("tendencia", 60))},
    "ancoras_sugeridas": {"gancho": "nota 90: pergunta concreta no 1º segundo; nota 40: frase genérica"},
}


class Juiz(Provedor):
    tipo = "juiz_video"

    def __init__(self, respostas):
        super().__init__("gemini_video", {"familia": "google", "custo_usd": 0.03})
        self.respostas, self.pedidos = list(respostas), []

    def configurado(self):
        return None

    def executar(self, video, prompt, sistema=None, duracao=None):
        self.pedidos.append({"video": video, "prompt": prompt, "sistema": sistema, "duracao": duracao})
        return self.respostas.pop(0)


class TestValidacao(unittest.TestCase):
    def test_normaliza_e_corta_trechos(self):
        a = validar_analise(json.dumps(BOA))
        self.assertEqual([e["parte"] for e in a["estrutura"]], ["gancho", "desenvolvimento", "cta"])
        self.assertLessEqual(len(a["gancho"]["trecho"]), 150)  # só trecho curto (ética, spec 09)
        self.assertEqual(a["nota_potencial"], 75.0)
        self.assertEqual(a["ancoras_sugeridas"]["fluxo"], "")

    def test_recusa_sem_evidencia_ou_numero_absurdo(self):
        nan = {c: {"nota": float("nan"), "evidencia": "x"} for c in BOA["potencial"]}
        for mexer in ({"palavras_por_segundo": 50}, {"potencial": {"gancho": {"nota": 90}}}, {"estrutura": []},
                      {"duracao_s": "longo"}, {"duracao_s": float("nan")}, {"potencial": nan},
                      {"cortes_por_minuto": float("inf")}):
            with self.assertRaises(ValueError):
                validar_analise(json.dumps({**BOA, **mexer}))  # json.dumps escreve NaN/Infinity, como um modelo faria

    def test_tempos_dentro_do_video_e_textos_curtos(self):
        estrutura = [{"parte": "gancho", "inicio_s": 0, "fim_s": 9999, "resumo": "a\nb"},
                     {"parte": "cta", "inicio_s": float("nan"), "fim_s": 3}]
        longo = {c: {"nota": 50, "evidencia": "x" * 400} for c in BOA["potencial"]}
        a = validar_analise(json.dumps({**BOA, "estrutura": estrutura, "potencial": longo,
                                        "gancho": {"tipo": "promessa", "momento_s": -4, "trecho": "oi"},
                                        "ancoras_sugeridas": {"gancho": "y" * 400}}))
        self.assertEqual(a["estrutura"], [{"parte": "gancho", "inicio_s": 0.0, "fim_s": 42.0, "resumo": "a b"}])
        self.assertEqual(a["gancho"]["momento_s"], 0.0)
        self.assertTrue(all(len(v["evidencia"]) <= LIMITE_TRECHO for v in a["potencial"].values()))
        self.assertLessEqual(len(a["ancoras_sugeridas"]["gancho"]), LIMITE_TRECHO)

    def test_duracao_maxima_do_formato(self):
        self.assertEqual([_duracao_maxima(f) for f in ("15–60 s, vertical", "5–20 min", "curto ou longo", None)],
                         [60, 1200, 1200, None])


class TestAnalisar(unittest.TestCase):
    def test_link_do_youtube_e_analisado_sem_baixar_e_salvo(self):
        juiz = Juiz(["não é json", json.dumps(BOA)])
        rt = Roteador({"gemini_video": juiz, "outro": Juiz([json.dumps(BOA)])},
                      {"juiz_video": ["gemini_video", "outro"]}, dormir=lambda s: None)
        with tempfile.TemporaryDirectory() as d:
            r = analisar_referencia(rt, " https://www.youtube.com/shorts/abc123?si=XYZ ", "A", nome_categoria="Curto",
                                    formato="5–20 min", pasta=d)
            r2 = analisar_referencia(rt, "https://youtu.be/abc123", "A", pasta=d)
            self.assertEqual(r["id"], r2["id"])  # mesmo vídeo por outro link: mesmo arquivo, sem duplicata
            self.assertEqual(r["medido_por"], "gemini (estimado pelo link)")
            self.assertEqual(r["provedor"], "outro")  # o 1º respondeu JSON inválido: vai ao próximo
            salvo = json.loads(Path(r["arquivo"]).read_text(encoding="utf-8"))
            self.assertEqual(salvo["origem"], "https://www.youtube.com/watch?v=abc123")  # sem o token si=
            self.assertNotIn("transcricao", salvo)
        self.assertEqual(juiz.pedidos[0]["video"], "https://www.youtube.com/shorts/abc123?si=XYZ")
        self.assertEqual(juiz.pedidos[0]["duracao"], 1200)  # custo estimado pela maior duração da categoria
        self.assertIn("Curto", juiz.pedidos[0]["prompt"])

    def test_entrada_que_nao_e_video(self):
        rt = Roteador({"gemini_video": Juiz([])}, {"juiz_video": ["gemini_video"]})
        with self.assertRaises(ValueError):
            analisar_referencia(rt, "https://www.youtube.com/@canal", "A")

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
    def test_arquivo_local_usa_as_medicoes_reais(self):
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "ref.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:d=4",
                            "-f", "lavfi", "-i", "sine=f=300:d=4", "-shortest", "-pix_fmt", "yuv420p", str(video)],
                           check=True)
            rt = Roteador({"gemini_video": Juiz([json.dumps(BOA)])}, {"juiz_video": ["gemini_video"]})
            r = analisar_referencia(rt, video, "A")
            self.assertAlmostEqual(r["duracao_s"], 4, delta=0.2)  # medido pelo FFmpeg, não os 42 s estimados
            self.assertEqual(r["origem"], "ref.mp4")  # sem o caminho do PC
            self.assertEqual(r["medido_por"], "ffmpeg+gemini")
            self.assertEqual(r["resolucao"], "320x240")
            self.assertIsNotNone(r["lufs"])
            self.assertEqual(r["cortes_por_minuto"], 0)  # um plano só: o 0 medido vale, não os 18 estimados


class TestCusto(unittest.TestCase):
    def test_juiz_de_video_cobra_pela_duracao(self):
        from torralles_studio.config import carregar_config
        from torralles_studio.seguranca import Orcamento

        cfg = carregar_config()["provedores"]["gemini_video"]
        p = Juiz([])
        p.cfg = cfg
        self.assertAlmostEqual(Orcamento.estimar(p, {"duracao": 30}), 0.03, places=3)
        self.assertGreater(Orcamento.estimar(p, {"duracao": 1200}), 1.0)
        self.assertAlmostEqual(Orcamento.estimar(p, {}), Orcamento.estimar(p, {"duracao": 60}))


if __name__ == "__main__":
    unittest.main()

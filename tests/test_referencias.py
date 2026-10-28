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

    def test_tempos_conferidos_pela_duracao_medida(self):
        estrutura = [{"parte": "gancho", "inicio_s": 0, "fim_s": 50}, {"parte": "cta", "inicio_s": 50, "fim_s": 70}]
        a = validar_analise(json.dumps({**BOA, "duracao_s": 30, "estrutura": estrutura}), duracao_medida=60)
        self.assertEqual([(e["inicio_s"], e["fim_s"]) for e in a["estrutura"]], [(0, 50), (50, 60)])
        b = validar_analise(json.dumps({**BOA, "duracao_s": 30, "estrutura": estrutura}))
        self.assertEqual([e["parte"] for e in b["estrutura"]], ["gancho"])  # cta começa depois do fim: sai

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

    def test_reanalise_mantem_as_suas_notas(self):  # K14: ajustar âncora e reanalisar não apaga a calibração
        rt = Roteador({"gemini_video": Juiz([json.dumps(BOA)] * 2)}, {"juiz_video": ["gemini_video"]})
        with tempfile.TemporaryDirectory() as d:
            r = analisar_referencia(rt, "https://youtu.be/abc123", "A", pasta=d)
            dados = json.loads(Path(r["arquivo"]).read_text(encoding="utf-8"))
            Path(r["arquivo"]).write_text(json.dumps({**dados, "notas_diego": {"gancho": 7.0}}), encoding="utf-8")
            r2 = analisar_referencia(rt, "https://youtu.be/abc123", "A", pasta=d, negativo=True,
                                     ancoras={"gancho": "nota 90: x"})
            self.assertEqual(r2["notas_diego"], {"gancho": 7.0})
            self.assertTrue(r2["negativo"])

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



def _analise(i, **mexer):
    a = {"id": f"v{i}", "categoria": "A", "negativo": False, "duracao_s": 20 + i * 10, "cortes_por_minuto": 10 + i,
         "duracao_media_plano_s": 3.0, "palavras_por_segundo": 2.0 + i / 10, "musica": {"tem": True, "abaixo_da_voz": True},
         "gancho": {"tipo": "pergunta_concreta" if i % 2 else "fato_surpreendente"}, "nota_potencial": 60 + i * 5}
    a.update(mexer)
    return a


class TestPerfilCategoria(unittest.TestCase):  # K13
    def test_percentil_como_numpy(self):
        from torralles_studio.referencias import percentil

        self.assertEqual(percentil([1, 2, 3, 4], 25), 1.75)
        self.assertEqual(percentil([1, 2, 3, 4], 75), 3.25)
        self.assertEqual(percentil([5], 25), 5)

    def test_faixas_so_das_positivas(self):
        from torralles_studio.referencias import perfil_da_categoria

        analises = [_analise(i) for i in range(1, 6)] + [_analise(9, negativo=True, duracao_s=500)]
        p = perfil_da_categoria(analises)
        self.assertEqual(p["n"], 5)
        self.assertEqual(p["faixas"]["duracao_s"], [40.0, 60.0])  # 30,40,50,60,70: o negativo (500) não entra
        self.assertEqual(p["gancho_tipos_aceitos"], ["pergunta_concreta", "fato_surpreendente"])
        self.assertEqual(p["nota_potencial_minima"], 70.0)
        self.assertEqual(p["musica_sob_voz"], 1.0)

    def test_poucas_referencias_ou_valor_estragado(self):
        from torralles_studio.referencias import perfil_da_categoria

        with self.assertRaises(ValueError):
            perfil_da_categoria([_analise(1), _analise(2), _analise(3, negativo=True)])
        p = perfil_da_categoria([_analise(1), _analise(2), _analise(3, palavras_por_segundo=None)])
        self.assertNotIn("palavras_por_segundo", p["faixas"])  # só 2 valores válidos: sem faixa

    def test_salvar_carregar_e_manter_outras_categorias(self):
        from torralles_studio.referencias import carregar_analises, carregar_perfil, perfil_da_categoria, salvar_perfil

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "A").mkdir()
            for i in range(1, 4):
                (Path(d) / "A" / f"v{i}.json").write_text(json.dumps(_analise(i)), encoding="utf-8")
            (Path(d) / "A" / "ruim.json").write_text("{", encoding="utf-8")
            analises = carregar_analises(d, "A")
            self.assertEqual(len(analises), 3)
            arq = Path(d) / "perfis.toml"
            salvar_perfil(arq, "B", perfil_da_categoria([_analise(i) for i in range(1, 4)]), data="2026-10-28")
            salvar_perfil(arq, "A", perfil_da_categoria(analises), data="2026-10-28")
            a, b = carregar_perfil(arq, "A"), carregar_perfil(arq, "B")
            self.assertEqual(a["duracao_s"], [35.0, 45.0])
            self.assertEqual(a["n_referencias"], 3)
            self.assertIsNotNone(b)
            self.assertIsNone(carregar_perfil(arq, "C"))
            self.assertIsNone(carregar_perfil(Path(d) / "nao-existe.toml", "A"))

    def test_alertas_do_video_fora_da_faixa(self):
        from torralles_studio.referencias import alertas_referencia, medidas_do_video

        roteiro = {"cenas": [{"narracao": "um dois três quatro cinco"}, {"narracao": "seis sete oito nove dez"}]}
        m = medidas_do_video({"duracao_s": 10, "tempos": [{}, {}]}, roteiro)
        self.assertEqual(m, {"duracao_s": 10.0, "cortes_por_minuto": 6.0, "duracao_media_plano_s": 5.0,
                             "palavras_por_segundo": 1.0})
        alertas = alertas_referencia(m, {"duracao_s": [20, 45], "palavras_por_segundo": [0.5, 2.0],
                                         "cortes_por_minuto": "lixo"}, "A")
        self.assertEqual(len(alertas), 1)
        self.assertIn("abaixo da faixa", alertas[0])
        self.assertIn("categoria A", alertas[0])
        self.assertEqual(medidas_do_video({"duracao_s": 0}, roteiro), {})


if __name__ == "__main__":
    unittest.main()

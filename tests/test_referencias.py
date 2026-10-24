import json
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from torralles_studio.provedores.base import Provedor
from torralles_studio.referencias import analisar_referencia, validar_analise
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

    def executar(self, video, prompt, sistema=None):
        self.pedidos.append({"video": video, "prompt": prompt, "sistema": sistema})
        return self.respostas.pop(0)


class TestValidacao(unittest.TestCase):
    def test_normaliza_e_corta_trechos(self):
        a = validar_analise(json.dumps(BOA))
        self.assertEqual([e["parte"] for e in a["estrutura"]], ["gancho", "desenvolvimento", "cta"])
        self.assertLessEqual(len(a["gancho"]["trecho"]), 150)  # só trecho curto (ética, spec 09)
        self.assertEqual(a["nota_potencial"], 75.0)
        self.assertEqual(a["ancoras_sugeridas"]["fluxo"], "")

    def test_recusa_sem_evidencia_ou_numero_absurdo(self):
        for mexer in ({"palavras_por_segundo": 50}, {"potencial": {"gancho": {"nota": 90}}}, {"estrutura": []},
                      {"duracao_s": "longo"}):
            with self.assertRaises(ValueError):
                validar_analise(json.dumps({**BOA, **mexer}))


class TestAnalisar(unittest.TestCase):
    def test_link_do_youtube_e_analisado_sem_baixar_e_salvo(self):
        juiz = Juiz(["não é json", json.dumps(BOA)])
        rt = Roteador({"gemini_video": juiz, "outro": Juiz([json.dumps(BOA)])},
                      {"juiz_video": ["gemini_video", "outro"]}, dormir=lambda s: None)
        with tempfile.TemporaryDirectory() as d:
            r = analisar_referencia(rt, "https://www.youtube.com/shorts/abc123", "A", nome_categoria="Curto", pasta=d)
            self.assertEqual(r["medido_por"], "gemini (estimado pelo link)")
            self.assertEqual(r["provedor"], "outro")  # o 1º respondeu JSON inválido: vai ao próximo
            salvo = json.loads(Path(r["arquivo"]).read_text(encoding="utf-8"))
            self.assertEqual(salvo["origem"], "https://www.youtube.com/shorts/abc123")
            self.assertNotIn("transcricao", salvo)
        self.assertEqual(juiz.pedidos[0]["video"], "https://www.youtube.com/shorts/abc123")
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


if __name__ == "__main__":
    unittest.main()

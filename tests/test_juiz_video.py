import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio.provedores import CLASSES
from torralles_studio.provedores.base import Provedor
from torralles_studio.provedores.juiz_video import GeminiVideoJuiz, eh_youtube
from torralles_studio.qualidade import Avaliador
from torralles_studio.rede import ErroProvedor
from torralles_studio.roteador import Roteador

DEMO = Path(__file__).resolve().parent.parent / "exemplos" / "demo_torralles_studio_v2.mp4"
CRITERIOS = ["gancho", "fluidez", "coesao", "audio", "sincronia"]


def resposta_gemini(texto):
    return {"candidates": [{"content": {"parts": [{"text": texto}]}}]}


def veredito(n=80, problemas=()):
    return json.dumps({"criterios": {c: {"evidencia": "aos 0.5s abre com pergunta", "nota": n} for c in CRITERIOS},
                       "problemas": list(problemas), "correcao_sugerida": "encurtar a cena 2"})


class TestProvedorGeminiVideo(unittest.TestCase):
    def setUp(self):
        self.juiz = GeminiVideoJuiz("gemini_video", {"modelo": "gemini-x", "chave_env": "GEMINI_API_KEY"})

    def test_video_local_vai_inline_com_som_e_temperatura_baixa(self):
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "v.mp4"
            video.write_bytes(b"mp4 bytes")
            with mock.patch("torralles_studio.provedores.juiz_video.post_json",
                            return_value=resposta_gemini('{"ok": 1}')) as post:
                self.assertEqual(self.juiz.executar(video, "avalie", sistema="regras"), '{"ok": 1}')
        url, corpo = post.call_args[0][:2]
        self.assertIn("models/gemini-x:generateContent", url)
        parte = corpo["contents"][0]["parts"][0]["inline_data"]
        self.assertEqual((parte["mime_type"], base64.b64decode(parte["data"])), ("video/mp4", b"mp4 bytes"))
        self.assertEqual(corpo["generationConfig"]["temperature"], 0.2)
        self.assertEqual(corpo["systemInstruction"]["parts"][0]["text"], "regras")

    def test_link_do_youtube_vai_sem_baixar(self):
        url = "https://www.youtube.com/watch?v=abc123"
        self.assertTrue(eh_youtube(url))
        with mock.patch("torralles_studio.provedores.juiz_video.post_json", return_value=resposta_gemini("{}")) as post:
            self.juiz.executar(url, "avalie")
        self.assertEqual(post.call_args[0][1]["contents"][0]["parts"][0], {"file_data": {"file_uri": url, "mime_type": "video/*"}})

    def test_outros_links_e_arquivo_inexistente_sao_recusados(self):
        for video in ("https://site.exemplo.com/v.mp4", "/nao/existe.mp4"):
            with self.subTest(video=video), self.assertRaises(ErroProvedor):
                self.juiz.executar(video, "avalie")

    def test_video_grande_e_reduzido_antes_de_enviar(self):
        self.juiz.cfg["limite_inline_mb"] = 0.00001
        with tempfile.TemporaryDirectory() as d:
            grande = Path(d) / "grande.mp4"
            grande.write_bytes(b"x" * 100)
            leve = Path(d) / "leve.mp4"
            leve.write_bytes(b"y")
            with mock.patch("torralles_studio.provedores.juiz_video.versao_leve", return_value=leve) as reduzir, \
                 mock.patch("torralles_studio.provedores.juiz_video.post_json", return_value=resposta_gemini("{}")) as post:
                self.juiz.executar(grande, "avalie")
        reduzir.assert_called_once()
        self.assertEqual(base64.b64decode(post.call_args[0][1]["contents"][0]["parts"][0]["inline_data"]["data"]), b"y")

    def test_resposta_bloqueada_vira_erro_claro(self):
        with tempfile.TemporaryDirectory() as d:
            video = Path(d) / "v.mp4"
            video.write_bytes(b"x")
            with mock.patch("torralles_studio.provedores.juiz_video.post_json",
                            return_value={"promptFeedback": {"blockReason": "SAFETY"}}):
                with self.assertRaisesRegex(ErroProvedor, "SAFETY"):
                    self.juiz.executar(video, "avalie")

    def test_classe_registrada(self):
        self.assertIs(CLASSES["gemini_video"], GeminiVideoJuiz)


class JuizVideoFalso(Provedor):
    tipo = "juiz_video"

    def __init__(self, nome, familia, respostas):
        super().__init__(nome, {"familia": familia})
        self.respostas = list(respostas)
        self.pedidos = []

    def configurado(self):
        return None

    def executar(self, video, prompt, sistema=None):
        self.pedidos.append({"video": video, "prompt": prompt, "sistema": sistema})
        return self.respostas.pop(0)


def avaliador_com(*juizes):
    from torralles_studio.config import carregar_config

    rt = Roteador({j.nome: j for j in juizes}, {"juiz_video": [j.nome for j in juizes], "juiz": []})
    return Avaliador(rt, carregar_config()["avaliacao"])


class TestAvaliarVideo(unittest.TestCase):
    def test_nota_na_regua_com_problemas_marcados_no_tempo(self):
        from torralles_studio.percepcao import avaliar_video

        juiz = JuizVideoFalso("gemini_video", "google", [veredito(
            80, [{"momento": "3.3s", "descricao": "música cobre a voz", "gravidade": "alta"}])])
        av = avaliar_video(avaliador_com(juiz), "https://youtu.be/abc", contexto="vídeo sobre chá",
                           percepcao={"duracao": 30, "cortes": [1.0, 5.2], "quadros": ["muito", "grande"]})
        self.assertTrue(av.aprovado)
        self.assertEqual(av.nota, 80.0)
        self.assertEqual(av.juizes, ["gemini_video"])
        self.assertIn("aos 3.3s: música cobre a voz (gravidade alta)", av.problemas)
        pedido = juiz.pedidos[0]
        self.assertEqual(pedido["video"], "https://youtu.be/abc")
        self.assertIn("assista inteiro, com som", pedido["sistema"])
        self.assertIn('"duracao": 30', pedido["prompt"])
        self.assertNotIn("muito", pedido["prompt"])  # quadros ficam de fora
        self.assertIn("aos 3.3s", av.feedback(nota_minima=70))

    def test_juiz_de_video_da_mesma_familia_do_gerador_e_pulado(self):
        from torralles_studio.percepcao import avaliar_video

        mesmo = JuizVideoFalso("gemini_video", "google", [veredito(100)])
        outro = JuizVideoFalso("outro_video", "openai", [veredito(70)])
        av = avaliar_video(avaliador_com(mesmo, outro), "https://youtu.be/abc", gerador="gemini_video")
        self.assertEqual(av.juizes, ["outro_video"])
        self.assertEqual(mesmo.pedidos, [])

    def test_regua_do_video_final_soma_100(self):
        from torralles_studio.config import carregar_avaliador

        rub = carregar_avaliador().rubricas["video_final"]
        self.assertEqual(sum(c["peso"] for c in rub.criterios.values()), 100)


@unittest.skipUnless(os.environ.get("GEMINI_API_KEY") and DEMO.exists(),
                     "teste real: precisa de GEMINI_API_KEY (roda no PC com a chave)")
class TestRealDemo(unittest.TestCase):
    def test_demo_devolve_json_na_regua(self):
        from torralles_studio.config import carregar_avaliador
        from torralles_studio.percepcao import avaliar_video

        av = avaliar_video(carregar_avaliador(), DEMO, contexto="vídeo demonstrativo do Torralles Studio")
        self.assertFalse(av.sem_juiz, av.problemas)
        self.assertIsNotNone(av.nota)
        self.assertEqual(set(av.criterios), set(CRITERIOS))
        print("\nNota real do demo:", json.dumps(av.como_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    unittest.main()

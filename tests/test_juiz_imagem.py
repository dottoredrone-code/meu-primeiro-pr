"""K38 (spec 03 §3.3, spec 14 §F.2): juiz de visão nas imagens das cenas."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from torralles_studio.provedores.base import Provedor
from torralles_studio.provedores.texto import AnthropicTexto, GeminiTexto, OpenAICompatTexto
from torralles_studio.qualidade import Avaliador
from torralles_studio.rede import ErroProvedor
from torralles_studio.roteador import Roteador

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
RUBRICA = {"imagem": {"nota_minima": 70, "num_juizes": 1, "criterios": {
    "aderencia": {"peso": 60, "descricao": "mostra o pedido"},
    "artefatos": {"peso": 40, "piso": 60, "descricao": "sem defeitos"}}}}


def resposta(aderencia=80, artefatos=80):
    return json.dumps({"criterios": {"aderencia": {"evidencia": "xícara visível", "nota": aderencia},
                                     "artefatos": {"evidencia": "sem defeitos", "nota": artefatos}},
                       "problemas": [], "correcao_sugerida": "mostrar o vapor"})


class TestProvedoresComVisao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.img = Path(self.tmp.name) / "a.png"
        self.img.write_bytes(PNG)

    def tearDown(self):
        self.tmp.cleanup()

    def _enviar(self, classe, cfg, retorno):
        enviado = {}

        def falso(url, corpo, cab, timeout):
            enviado.update(corpo=corpo)
            return retorno

        with mock.patch("torralles_studio.provedores.texto.post_json", falso), \
                mock.patch.dict(os.environ, {"CHAVE_TESTE": "x"}):
            classe("p", {"chave_env": "CHAVE_TESTE", "modelo": "m", "base_url": "https://x", **cfg}).executar(
                "avalie", imagens=[self.img])
        return enviado["corpo"]

    def test_cada_api_recebe_a_imagem_no_formato_dela(self):
        c = self._enviar(AnthropicTexto, {"visao": True}, {"content": [{"type": "text", "text": "ok"}]})
        self.assertEqual(c["messages"][0]["content"][0]["source"]["media_type"], "image/png")
        c = self._enviar(OpenAICompatTexto, {"visao": True}, {"choices": [{"message": {"content": "ok"}}]})
        self.assertTrue(c["messages"][-1]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,"))
        c = self._enviar(GeminiTexto, {"visao": True}, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
        self.assertEqual(c["contents"][0]["parts"][0]["inline_data"]["mime_type"], "image/png")

    def test_modelo_sem_visao_recusa(self):
        with self.assertRaises(ErroProvedor):
            self._enviar(OpenAICompatTexto, {}, {"choices": [{"message": {"content": "ok"}}]})


class JuizFalso(Provedor):
    tipo = "texto"

    def __init__(self, nome, familia, respostas):
        super().__init__(nome, {"familia": familia, "visao": True})
        self.respostas, self.recebidos = list(respostas), []

    def configurado(self):
        return None

    def executar(self, prompt, sistema=None, imagens=None):
        self.recebidos.append({"imagens": imagens, "sistema": sistema})
        return self.respostas.pop(0)


class TestAvaliador(unittest.TestCase):
    def test_imagem_vai_para_a_cadeia_de_visao_e_exclui_a_familia_de_quem_gerou(self):
        google = JuizFalso("gemini", "google", [resposta()])
        anthropic = JuizFalso("claude", "anthropic", [resposta(90, 85)])
        gerador = Provedor("nano", {"familia": "google"})
        rt = Roteador({"gemini": google, "claude": anthropic, "nano": gerador},
                      {"juiz": ["gemini"], "juiz_imagem": ["gemini", "claude"]}, dormir=lambda s: None)
        av = Avaliador(rt, RUBRICA).avaliar("imagem", "pedido", gerador="nano", imagens=["x.png"])
        self.assertEqual(av.juizes, ["claude"])
        self.assertEqual(google.recebidos, [])
        self.assertEqual(anthropic.recebidos[0]["imagens"], [Path("x.png")])
        self.assertIn("IMAGENS anexadas", anthropic.recebidos[0]["sistema"])
        self.assertTrue(av.aprovado)

    def test_sem_cadeia_de_visao_fica_para_revisar(self):
        rt = Roteador({"j": JuizFalso("j", "x", [])}, {"juiz": ["j"]}, dormir=lambda s: None)
        av = Avaliador(rt, RUBRICA).avaliar("imagem", "pedido", imagens=["x.png"])
        self.assertTrue(av.sem_juiz and av.revisar_manual)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestNaProducao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        self.img = self.pasta / "cena_01.png"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1",
                        str(self.img)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _avaliador(self, *notas):
        juiz = JuizFalso("claude", "anthropic", [resposta(n, 80) for n in notas])
        rt = Roteador({"claude": juiz}, {"juiz_imagem": ["claude"]}, dormir=lambda s: None)
        return Avaliador(rt, RUBRICA), juiz

    def test_julgar_manda_jpeg_pequeno(self):
        from torralles_studio.producao import julgar_imagem

        avaliador, juiz = self._avaliador(90)
        av = julgar_imagem(avaliador, {"prompt_imagem": "red square"}, self.img)
        self.assertEqual(av.nota, 86.0)
        self.assertEqual(juiz.recebidos[0]["imagens"][0].suffix, ".jpg")

    def test_reprovada_refaz_uma_vez_e_fica_a_melhor(self):
        from torralles_studio import producao

        avaliador, _ = self._avaliador(20, 90)
        loop = SimpleNamespace(avaliador=avaliador)
        original = self.img.read_bytes()
        refeita = {}

        def gerar(roteador, prompt, saida, perfil=None, proporcao=None, cena=None):
            refeita["prompt"] = cena.get("correcao", "")
            Path(saida).write_bytes(original)  # a primeira foi movida para a reserva
            return SimpleNamespace(provedor="cloudflare_flux")

        with mock.patch.object(producao.funcoes, "gerar_imagem", gerar):
            campos = producao._imagem_com_juiz(None, loop, {"prompt_imagem": "red square"}, self.img, 1, self.pasta,
                                               None, "9:16", "pollinations", lambda t: None)
        self.assertIn("provedor_refeito", campos, campos)
        self.assertIn("mostrar o vapor", refeita["prompt"])
        self.assertEqual(campos["provedor_refeito"], "cloudflare_flux")
        self.assertEqual(campos["nota_imagem"], 86.0)
        self.assertFalse((self.pasta / "cena_01_antes.png").exists())

    def test_refeita_pior_volta_a_primeira(self):
        from torralles_studio import producao

        avaliador, _ = self._avaliador(50, 10)
        original = self.img.read_bytes()

        def gerar(roteador, prompt, saida, perfil=None, proporcao=None, cena=None):
            Path(saida).write_bytes(original[:-1] + b"\x00")
            return SimpleNamespace(provedor="outro")

        with mock.patch.object(producao.funcoes, "gerar_imagem", gerar), \
                mock.patch.object(producao, "julgar_imagem", side_effect=[
                    avaliador.avaliar("imagem", "p", imagens=[self.img]),
                    avaliador.avaliar("imagem", "p", imagens=[self.img])]):
            campos = producao._imagem_com_juiz(None, SimpleNamespace(avaliador=avaliador), {"prompt_imagem": "x"},
                                               self.img, 1, self.pasta, None, "9:16", "g", lambda t: None)
        self.assertTrue(campos["revisar"])
        self.assertEqual(self.img.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

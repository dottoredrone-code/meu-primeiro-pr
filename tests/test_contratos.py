import re
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio.config import CONFIG_PADRAO, montar_provedores

# Modelos (ou famílias) já desligados/aposentados pelos fornecedores (ver docs/sdd/00-descoberta.md).
APOSENTADOS = [
    r"^deepseek-chat$", r"^deepseek-reasoner$", r"^gemini-2\.5-", r"^gpt-image-1$",
    r"kling-video/v[12](\.\d)?/", r"^fal-ai/wan-i2v$",
]


class TestContratos(unittest.TestCase):
    def setUp(self):
        self.dados = tomllib.loads(Path(CONFIG_PADRAO).read_text())

    def test_config_sem_modelos_aposentados(self):
        from torralles_studio import percepcao

        usados = {cfg.get("modelo") for cfg in self.dados["provedores"].values() if cfg.get("modelo")}
        padrao_percepcao = re.search(r'GEMINI_MODELO_PERCEPCAO", "([^"]+)"', Path(percepcao.__file__).read_text())
        usados.add(padrao_percepcao.group(1))
        ruins = {m for m in usados for padrao in APOSENTADOS if re.search(padrao, m)}
        self.assertFalse(ruins, f"modelos aposentados: {ruins}")

    def test_familia_do_juiz_bate_com_o_modelo(self):
        # Juiz nunca é da família de quem gerou (D15): a família precisa ser a do MODELO, não a do serviço.
        prefixos = {"deepseek": "deepseek", "gemini": "google", "gpt": "openai", "claude": "anthropic"}
        for nome, cfg in self.dados["provedores"].items():
            if "familia" not in cfg or not cfg.get("modelo"):
                continue
            modelo = cfg["modelo"].split("/")[-1].lower()
            for prefixo, familia in prefixos.items():
                if modelo.startswith(prefixo):
                    self.assertEqual(cfg["familia"], familia, f"{nome} roda {cfg['modelo']}")

    def test_kling_v3_recebe_start_image_url(self):
        provedores = montar_provedores(self.dados)
        kling = provedores["fal_kling"]
        enviado = {}

        def falso_post(url, corpo, cab, timeout):
            enviado.update(url=url, corpo=corpo)
            return {"video": {"url": "https://v3.fal.media/x.mp4"}}

        img = Path(__file__).with_name("_img_teste.png")
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        try:
            with mock.patch("torralles_studio.provedores.video.post_json", falso_post), \
                 mock.patch("torralles_studio.provedores.video.baixar", return_value=b"mp4"), \
                 mock.patch("torralles_studio.provedores.video.salvar", side_effect=lambda s, d: s):
                kling.executar(img, "câmera avança", Path("/tmp/x.mp4"), duracao=5)
        finally:
            img.unlink()
        self.assertIn("/v3/", enviado["url"])
        self.assertIn("start_image_url", enviado["corpo"])
        self.assertNotIn("image_url", enviado["corpo"])

    def test_wan_continua_com_image_url(self):
        wan = montar_provedores(self.dados)["fal_wan"]
        corpo = {}
        with mock.patch("torralles_studio.provedores.video.post_json",
                        lambda u, c, h, t: corpo.update(c) or {"video": {"url": "u"}}), \
             mock.patch("torralles_studio.provedores.video.baixar", return_value=b""), \
             mock.patch("torralles_studio.provedores.video.salvar", side_effect=lambda s, d: s), \
             mock.patch("torralles_studio.provedores.video.data_uri", return_value="data:"):
            wan.executar("img.png", "p", Path("/tmp/y.mp4"))
        self.assertIn("image_url", corpo)
        self.assertNotIn("duration", corpo)


if __name__ == "__main__":
    unittest.main()


class TestClaudeAtual(unittest.TestCase):
    """KR1 24/10/2026: modelos atuais pensam antes de responder; cortar ou recusar vira falha (vai para o próximo)."""

    def chamar(self, resposta):
        from unittest import mock

        from torralles_studio.provedores import texto

        enviados = []

        def falso(url, corpo, cab, timeout):
            enviados.append(corpo)
            return resposta

        prov = texto.AnthropicTexto("claude", {"modelo": "claude-sonnet-5-5"})
        with mock.patch.object(texto, "post_json", falso):
            return prov.executar("oi"), enviados

    def test_texto_ignora_bloco_de_raciocinio_e_nao_manda_temperature(self):
        r, enviados = self.chamar({"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": ""},
                                                                           {"type": "text", "text": "olá"}]})
        self.assertEqual(r, "olá")
        self.assertNotIn("temperature", enviados[0])
        self.assertGreaterEqual(enviados[0]["max_tokens"], 16000)

    def test_cortada_ou_recusada_e_erro(self):
        from torralles_studio.rede import ErroProvedor

        for motivo in ("max_tokens", "refusal"):
            with self.assertRaises(ErroProvedor):
                self.chamar({"stop_reason": motivo, "content": [{"type": "text", "text": "{\"a\": "}]})

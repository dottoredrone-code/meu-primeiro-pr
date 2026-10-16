import tomllib
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio.config import CONFIG_PADRAO, montar_provedores
from torralles_studio.provedores.video import FalVideo

# Modelos já desligados ou aposentados pelos fornecedores (ver docs/sdd/00-descoberta.md).
APOSENTADOS = {
    "deepseek-chat", "deepseek-reasoner", "gemini-2.5-flash", "gemini-2.5-flash-image",
    "gpt-image-1", "fal-ai/kling-video/v2.1/standard/image-to-video", "fal-ai/wan-i2v",
}


class TestContratos(unittest.TestCase):
    def setUp(self):
        self.dados = tomllib.loads(Path(CONFIG_PADRAO).read_text())

    def test_config_sem_modelos_aposentados(self):
        usados = {cfg.get("modelo") for cfg in self.dados["provedores"].values()}
        self.assertFalse(usados & APOSENTADOS, f"modelos aposentados no config: {usados & APOSENTADOS}")

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
                 mock.patch("torralles_studio.provedores.video.requisitar", return_value=b"mp4"), \
                 mock.patch("torralles_studio.provedores.video.salvar", side_effect=lambda s, d: s):
                kling.executar(img, "câmera avança", Path("/tmp/x.mp4"), duracao=5)
        finally:
            img.unlink()
        self.assertIn("/v3/", enviado["url"])
        self.assertIn("start_image_url", enviado["corpo"])
        self.assertNotIn("image_url", enviado["corpo"])

    def test_wan_continua_com_image_url(self):
        wan = FalVideo("wan", {"modelo": "fal-ai/wan-25-preview/image-to-video", "enviar_duracao": False})
        corpo = {}
        with mock.patch("torralles_studio.provedores.video.post_json",
                        lambda u, c, h, t: corpo.update(c) or {"video": {"url": "u"}}), \
             mock.patch("torralles_studio.provedores.video.requisitar", return_value=b""), \
             mock.patch("torralles_studio.provedores.video.salvar", side_effect=lambda s, d: s), \
             mock.patch("torralles_studio.provedores.video.data_uri", return_value="data:"):
            wan.executar("img.png", "p", Path("/tmp/y.mp4"))
        self.assertIn("image_url", corpo)
        self.assertNotIn("duration", corpo)


if __name__ == "__main__":
    unittest.main()

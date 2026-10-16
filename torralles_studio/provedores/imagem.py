import base64
import urllib.parse

from ..rede import ErroProvedor, post_json, requisitar
from .base import Provedor, salvar


class GeminiImagem(Provedor):
    """Nano Banana: modelo de imagem do Gemini."""

    tipo = "imagem"

    def executar(self, prompt, saida):
        r = post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent",
            {"contents": [{"parts": [{"text": prompt}]}]},
            {"x-goog-api-key": self.chave},
            self.timeout,
        )
        for parte in r["candidates"][0]["content"]["parts"]:
            if "inlineData" in parte:
                return salvar(saida, base64.b64decode(parte["inlineData"]["data"]))
        raise ErroProvedor("o modelo não devolveu imagem")


class OpenAIImagem(Provedor):
    tipo = "imagem"

    def executar(self, prompt, saida):
        r = post_json(
            "https://api.openai.com/v1/images/generations",
            {"model": self.modelo, "prompt": prompt, "size": self.cfg.get("tamanho", "1536x1024")},
            {"Authorization": f"Bearer {self.chave}"},
            self.timeout,
        )
        return salvar(saida, base64.b64decode(r["data"][0]["b64_json"]))


class FalImagem(Provedor):
    """Modelos de imagem hospedados no fal.ai (FLUX etc.)."""

    tipo = "imagem"

    def executar(self, prompt, saida):
        r = post_json(
            f"https://fal.run/{self.modelo}",
            {"prompt": prompt, "image_size": self.cfg.get("tamanho", "landscape_16_9")},
            {"Authorization": f"Key {self.chave}"},
            self.timeout,
        )
        return salvar(saida, requisitar(r["images"][0]["url"], timeout=self.timeout))


class PollinationsImagem(Provedor):
    """Gerador gratuito e sem chave; bom como último recurso."""

    tipo = "imagem"

    def executar(self, prompt, saida):
        q = urllib.parse.urlencode(
            {"width": self.cfg.get("largura", 1280), "height": self.cfg.get("altura", 720), "nologo": "true"}
        )
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?{q}"
        return salvar(saida, requisitar(url, timeout=self.timeout))

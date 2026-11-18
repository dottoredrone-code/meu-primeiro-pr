import base64
import os
import urllib.parse

from ..rede import ErroProvedor, baixar, post_json
from .base import Provedor, salvar


class GeminiImagem(Provedor):
    """Nano Banana: modelo de imagem do Gemini."""

    tipo = "imagem"

    def executar(self, prompt, saida, proporcao=None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent"
        corpo = {"contents": [{"parts": [{"text": prompt}]}]}
        if proporcao:
            corpo["generationConfig"] = {"imageConfig": {"aspectRatio": proporcao}}
        try:
            r = post_json(url, corpo, {"x-goog-api-key": self.chave}, self.timeout)
        except ErroProvedor as e:
            if not proporcao or e.status != 400:
                raise
            corpo.pop("generationConfig")  # modelo sem opção de proporção: a montagem recorta depois
            r = post_json(url, corpo, {"x-goog-api-key": self.chave}, self.timeout)
        for parte in r["candidates"][0]["content"]["parts"]:
            if "inlineData" in parte:
                return salvar(saida, base64.b64decode(parte["inlineData"]["data"]))
        raise ErroProvedor("o modelo não devolveu imagem")


class OpenAIImagem(Provedor):
    tipo = "imagem"

    def executar(self, prompt, saida, proporcao=None):
        r = post_json(
            "https://api.openai.com/v1/images/generations",
            {"model": self.modelo, "prompt": prompt,
             "size": {"9:16": "1024x1536", "4:5": "1024x1536", "1:1": "1024x1024"}.get(proporcao)
             or self.cfg.get("tamanho", "1536x1024")},
            {"Authorization": f"Bearer {self.chave}"},
            self.timeout,
        )
        return salvar(saida, base64.b64decode(r["data"][0]["b64_json"]))


class FalImagem(Provedor):
    """Modelos de imagem hospedados no fal.ai (FLUX etc.)."""

    tipo = "imagem"

    def executar(self, prompt, saida, proporcao=None):
        tamanho = {"9:16": "portrait_16_9", "4:5": "portrait_4_3", "1:1": "square_hd", "16:9": "landscape_16_9"}
        r = post_json(
            f"https://fal.run/{self.modelo}",
            {"prompt": prompt, "image_size": tamanho.get(proporcao) or self.cfg.get("tamanho", "landscape_16_9")},
            {"Authorization": f"Key {self.chave}"},
            self.timeout,
        )
        return salvar(saida, baixar(r["images"][0]["url"], timeout=self.timeout))


class CloudflareImagem(Provedor):
    """Workers AI da Cloudflare (FLUX.1 schnell): cota grátis diária de neurons, uso comercial (K36).

    Precisa de duas variáveis no .env: a conta (conta_env) e o token (chave_env). A resposta traz a imagem em
    base64 no próprio JSON, então não há download de outro domínio.
    """

    tipo = "imagem"

    def configurado(self):
        motivo = super().configurado()
        conta = self.cfg.get("conta_env")
        if not motivo and conta and not os.environ.get(conta):
            motivo = f"falta {conta}"
        return motivo

    def executar(self, prompt, saida, proporcao=None):
        conta = os.environ.get(self.cfg.get("conta_env", ""), "")
        url = f"https://api.cloudflare.com/client/v4/accounts/{urllib.parse.quote(conta)}/ai/run/{self.modelo}"
        r = post_json(url, {"prompt": prompt[:2048], "steps": int(self.cfg.get("passos", 4))},
                      {"Authorization": f"Bearer {self.chave}"}, self.timeout)
        imagem = (r.get("result") or {}).get("image") if isinstance(r, dict) else None
        if not imagem:
            erros = "; ".join(str(e.get("message", e)) for e in (r.get("errors") or [])) if isinstance(r, dict) else ""
            raise ErroProvedor(f"Cloudflare não devolveu imagem{': ' + erros if erros else ''}")
        try:
            dados = base64.b64decode(imagem, validate=True)
        except (ValueError, TypeError):
            raise ErroProvedor("Cloudflare devolveu uma imagem em base64 inválido") from None
        return salvar(saida, dados)


class PollinationsImagem(Provedor):
    """Gerador gratuito e sem chave; bom como último recurso."""

    tipo = "imagem"

    def executar(self, prompt, saida, proporcao=None):
        from .video import TAMANHOS

        largura, altura = TAMANHOS.get(proporcao) or (self.cfg.get("largura", 1280), self.cfg.get("altura", 720))
        q = urllib.parse.urlencode({"width": largura, "height": altura, "nologo": "true"})
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?{q}"
        return salvar(saida, baixar(url, timeout=self.timeout))

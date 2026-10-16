import os

from ..rede import ErroProvedor, post_json
from .base import Provedor


def _exigir_texto(texto):
    if not texto or not texto.strip():
        raise ErroProvedor("resposta vazia")
    return texto


class OpenAICompatTexto(Provedor):
    """APIs no formato da OpenAI: DeepSeek, OpenAI, OpenRouter, Ollama..."""

    tipo = "texto"

    @property
    def base_url(self):
        env = self.cfg.get("base_url_env")
        return ((os.environ.get(env) if env else None) or self.cfg["base_url"]).rstrip("/")

    def configurado(self):
        env = self.cfg.get("base_url_env")
        if env and not os.environ.get(env):
            return f"falta {env}"
        return super().configurado()

    def executar(self, prompt, sistema=None):
        mensagens = [{"role": "system", "content": sistema}] if sistema else []
        mensagens.append({"role": "user", "content": prompt})
        cab = {"Authorization": f"Bearer {self.chave}"} if self.chave else {}
        r = post_json(
            f"{self.base_url}/chat/completions",
            {"model": self.modelo, "messages": mensagens},
            cab,
            self.timeout,
        )
        return _exigir_texto(r["choices"][0]["message"]["content"])


class AnthropicTexto(Provedor):
    tipo = "texto"

    def executar(self, prompt, sistema=None):
        corpo = {
            "model": self.modelo,
            "max_tokens": self.cfg.get("max_tokens", 4096),
            "messages": [{"role": "user", "content": prompt}],
        }
        if sistema:
            corpo["system"] = sistema
        r = post_json(
            "https://api.anthropic.com/v1/messages",
            corpo,
            {"x-api-key": self.chave, "anthropic-version": "2023-06-01"},
            self.timeout,
        )
        return _exigir_texto("".join(b["text"] for b in r["content"] if b["type"] == "text"))


class GeminiTexto(Provedor):
    tipo = "texto"

    def executar(self, prompt, sistema=None):
        corpo = {"contents": [{"parts": [{"text": prompt}]}]}
        if sistema:
            corpo["systemInstruction"] = {"parts": [{"text": sistema}]}
        r = post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent",
            corpo,
            {"x-goog-api-key": self.chave},
            self.timeout,
        )
        partes = r["candidates"][0]["content"]["parts"]
        return _exigir_texto("".join(p.get("text", "") for p in partes))

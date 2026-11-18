import os

from ..rede import ErroProvedor, post_json
from .base import Provedor, data_uri


def _sem_visao(provedor, imagens):
    if imagens and not provedor.cfg.get("visao"):
        raise ErroProvedor("este modelo não está marcado com visao = true no config")


def _base64(caminho):
    uri = data_uri(caminho)
    mime, dados = uri[5:].split(";base64,", 1)
    return mime, dados


def _temperatura(cfg):
    """Campo opcional `temperatura` do provedor (ex.: juízes com 0.2); None = padrão da API."""
    t = cfg.get("temperatura")
    if t is None:
        return None
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 <= t <= 2:
        raise ErroProvedor(f"temperatura inválida no config: {t!r} (use um número de 0 a 2)")
    return t


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

    def executar(self, prompt, sistema=None, imagens=None):
        _sem_visao(self, imagens)
        mensagens = [{"role": "system", "content": sistema}] if sistema else []
        if imagens:
            conteudo = [{"type": "image_url", "image_url": {"url": data_uri(i)}} for i in imagens]
            mensagens.append({"role": "user", "content": [*conteudo, {"type": "text", "text": prompt}]})
        else:
            mensagens.append({"role": "user", "content": prompt})
        cab = {"Authorization": f"Bearer {self.chave}"} if self.chave else {}
        corpo = {"model": self.modelo, "messages": mensagens}
        if (temp := _temperatura(self.cfg)) is not None:
            corpo["temperature"] = temp
        r = post_json(
            f"{self.base_url}/chat/completions",
            corpo,
            cab,
            self.timeout,
        )
        return _exigir_texto(r["choices"][0]["message"]["content"])


class AnthropicTexto(Provedor):
    tipo = "texto"

    def executar(self, prompt, sistema=None, imagens=None):
        _sem_visao(self, imagens)
        conteudo = prompt
        if imagens:
            blocos = []
            for i in imagens:
                mime, dados = _base64(i)
                blocos.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": dados}})
            conteudo = [*blocos, {"type": "text", "text": prompt}]
        # Modelos atuais pensam antes de responder e o raciocínio conta no max_tokens: folga para não cortar o JSON.
        corpo = {
            "model": self.modelo,
            "max_tokens": self.cfg.get("max_tokens", 16000),
            "messages": [{"role": "user", "content": conteudo}],
        }
        if sistema:
            corpo["system"] = sistema
        if (temp := _temperatura(self.cfg)) is not None:  # a API da Anthropic aceita de 0 a 1
            corpo["temperature"] = min(temp, 1)
        if self.cfg.get("esforco"):  # low | medium | high (opcional; menos esforço = mais barato e rápido)
            corpo["output_config"] = {"effort": self.cfg["esforco"]}
        r = post_json(
            "https://api.anthropic.com/v1/messages",
            corpo,
            {"x-api-key": self.chave, "anthropic-version": "2023-06-01"},
            self.timeout,
        )
        motivo = r.get("stop_reason")
        if motivo == "max_tokens":
            raise ErroProvedor("resposta cortada no limite de tokens (aumente max_tokens no config)")
        if motivo == "refusal":
            raise ErroProvedor("o modelo recusou o pedido")
        return _exigir_texto("".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text"))


class GeminiTexto(Provedor):
    tipo = "texto"

    def executar(self, prompt, sistema=None, imagens=None):
        _sem_visao(self, imagens)
        partes = []
        for i in imagens or []:
            mime, dados = _base64(i)
            partes.append({"inline_data": {"mime_type": mime, "data": dados}})
        corpo = {"contents": [{"parts": [*partes, {"text": prompt}]}]}
        if sistema:
            corpo["systemInstruction"] = {"parts": [{"text": sistema}]}
        if (temp := _temperatura(self.cfg)) is not None:
            corpo["generationConfig"] = {"temperature": temp}
        r = post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent",
            corpo,
            {"x-goog-api-key": self.chave},
            self.timeout,
        )
        partes = r["candidates"][0]["content"]["parts"]
        return _exigir_texto("".join(p.get("text", "") for p in partes))

import base64
import mimetypes
import os
from pathlib import Path


class Provedor:
    """Base de todos os provedores.

    Cada subclasse define `tipo` (texto, busca, imagem, voz ou video) e
    implementa `executar` com a assinatura combinada para aquele tipo:

      texto:  executar(prompt, sistema=None) -> str
      busca:  executar(consulta, max_resultados=5) -> list[dict]
      imagem: executar(prompt, saida) -> Path
      voz:    executar(texto, saida) -> Path
      video:  executar(imagem, prompt, saida, duracao=5) -> Path
    """

    tipo = ""

    def __init__(self, nome, cfg):
        self.nome = nome
        self.cfg = cfg
        self.timeout = cfg.get("timeout", 120)

    @property
    def chave(self):
        env = self.cfg.get("chave_env")
        return os.environ.get(env, "") if env else ""

    @property
    def modelo(self):
        env = self.cfg.get("modelo_env")
        return (os.environ.get(env) if env else None) or self.cfg.get("modelo", "")

    def configurado(self):
        """Retorna None se o provedor pode ser usado, senão o motivo."""
        for campo in ("chave_env", "modelo_env"):
            env = self.cfg.get(campo)
            if env and not os.environ.get(env):
                return f"falta {env}"
        return None

    def executar(self, **kwargs):
        raise NotImplementedError


def salvar(saida, dados):
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_bytes(dados)
    return saida


def data_uri(caminho):
    caminho = Path(caminho)
    mime = mimetypes.guess_type(caminho.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(caminho.read_bytes()).decode()}"

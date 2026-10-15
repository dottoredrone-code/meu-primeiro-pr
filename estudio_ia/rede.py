"""Chamadas HTTP usando só a biblioteca padrão, com erros padronizados."""

import json
import socket
import urllib.error
import urllib.request

# Códigos que indicam problema passageiro: vale tentar de novo.
STATUS_TEMPORARIOS = {408, 409, 425, 429, 500, 502, 503, 504, 529}


class ErroProvedor(Exception):
    """Falha ao chamar um provedor.

    status: código HTTP (None para falhas de rede).
    temporario: True quando repetir a chamada pode resolver.
    """

    def __init__(self, mensagem, status=None, temporario=False):
        super().__init__(mensagem)
        self.status = status
        self.temporario = temporario


def requisitar(url, *, metodo="GET", corpo=None, cabecalhos=None, timeout=120):
    cab = {"User-Agent": "estudio-ia/0.1", **(cabecalhos or {})}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode()
        cab.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=dados, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detalhe = e.read()[:300].decode(errors="replace")
        raise ErroProvedor(
            f"HTTP {e.code}: {detalhe}",
            status=e.code,
            temporario=e.code in STATUS_TEMPORARIOS,
        ) from e
    except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
        raise ErroProvedor(f"falha de rede: {e}", temporario=True) from e


def post_json(url, corpo, cabecalhos=None, timeout=120):
    return json.loads(requisitar(url, metodo="POST", corpo=corpo, cabecalhos=cabecalhos, timeout=timeout))


def get_json(url, cabecalhos=None, timeout=120):
    return json.loads(requisitar(url, cabecalhos=cabecalhos, timeout=timeout))

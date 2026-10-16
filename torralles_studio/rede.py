"""Chamadas HTTP usando só a biblioteca padrão, com erros padronizados."""

import json
import socket
import urllib.error
import urllib.parse
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


# Downloads de arquivos devolvidos pelos provedores: só destes domínios (D8).
# Ajustável em [seguranca] no config/fallbacks.toml.
DOMINIOS_DOWNLOAD = ["fal.media", "storage.googleapis.com", "image.pollinations.ai"]
TAMANHO_MAXIMO_DOWNLOAD = 300 * 1024 * 1024


def configurar_downloads(dominios=None, tamanho_maximo_mb=None):
    global DOMINIOS_DOWNLOAD, TAMANHO_MAXIMO_DOWNLOAD
    if dominios is not None:
        DOMINIOS_DOWNLOAD = [d.lower() for d in dominios]
    if tamanho_maximo_mb is not None:
        TAMANHO_MAXIMO_DOWNLOAD = int(tamanho_maximo_mb * 1024 * 1024)


def dominio_permitido(url, permitidos=None):
    partes = urllib.parse.urlparse(url)
    host = (partes.hostname or "").lower()
    if partes.scheme != "https" or not host:
        return False
    return any(host == d or host.endswith("." + d) for d in (permitidos or DOMINIOS_DOWNLOAD))


def baixar(url, *, timeout=120, permitidos=None, tamanho_maximo=None):
    """Baixa um arquivo só de domínio permitido, por HTTPS e até um tamanho máximo."""
    limite = tamanho_maximo or TAMANHO_MAXIMO_DOWNLOAD
    if not dominio_permitido(url, permitidos):
        raise ErroProvedor(f"download recusado: domínio não permitido ({urllib.parse.urlparse(url).hostname})")
    req = urllib.request.Request(url, headers={"User-Agent": "torralles-studio/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if not dominio_permitido(resp.geturl(), permitidos):  # redirecionou para fora da lista
                raise ErroProvedor("download recusado: redirecionado para domínio não permitido")
            declarado = resp.headers.get("Content-Length")
            if declarado and int(declarado) > limite:
                raise ErroProvedor(f"download recusado: arquivo maior que {limite} bytes")
            dados = resp.read(limite + 1)
    except urllib.error.HTTPError as e:
        raise ErroProvedor(f"HTTP {e.code} no download", status=e.code, temporario=e.code in STATUS_TEMPORARIOS) from e
    except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
        raise ErroProvedor(f"falha de rede no download: {e}", temporario=True) from e
    if len(dados) > limite:
        raise ErroProvedor(f"download recusado: arquivo maior que {limite} bytes")
    return dados


def requisitar(url, *, metodo="GET", corpo=None, cabecalhos=None, timeout=120):
    cab = {"User-Agent": "torralles-studio/0.1", **(cabecalhos or {})}
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

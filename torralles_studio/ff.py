"""Chamadas ao FFmpeg e ao ffprobe com prazo e texto em UTF-8.

- Prazo sempre: FFmpeg travado vira ErroProvedor em vez de prender a produção.
- Saída lida como UTF-8 (com troca de bytes inválidos): no Windows o padrão é cp1252, e caminho com acento
  no log do FFmpeg quebrava a leitura.
"""

import subprocess

from .rede import ErroProvedor

PRAZO_S = 900      # nenhuma etapa leva tanto: passou disso, o FFmpeg travou
PRAZO_SONDA_S = 60  # ffprobe só lê o cabeçalho


def _tempo(prazo):
    return f"{prazo // 60:.0f} min" if prazo >= 120 else f"{prazo:.0f} s"


def rodar(args, *, prazo=PRAZO_S, cwd=None, binario=False):
    """Roda o programa (args[0]) e devolve o CompletedProcess, sem olhar o código de saída.

    binario=True devolve stdout em bytes (áudio cru); senão, texto UTF-8.
    """
    args = [str(a) for a in args]
    texto = {} if binario else {"text": True, "encoding": "utf-8", "errors": "replace"}
    try:
        return subprocess.run(args, capture_output=True, stdin=subprocess.DEVNULL, cwd=cwd, timeout=prazo, **texto)
    except subprocess.TimeoutExpired:
        raise ErroProvedor(f"{args[0]} travou (mais de {_tempo(prazo)}) e foi interrompido") from None
    except FileNotFoundError:
        raise ErroProvedor(f"{args[0]} não instalado") from None


def ffmpeg(args, *, prazo=PRAZO_S, cwd=None, falha="ffmpeg falhou", limite=400):
    """Roda o FFmpeg (sobrescreve a saída, sem ler o teclado) e devolve o log (stderr).

    Código de saída diferente de 0 vira ErroProvedor com `falha` e o fim do log.
    """
    proc = rodar(["ffmpeg", "-y", "-hide_banner", "-nostdin", *args], prazo=prazo, cwd=cwd)
    if proc.returncode != 0:
        raise ErroProvedor(f"{falha}: {(proc.stderr or '').strip()[-limite:]}")
    return proc.stderr or ""


def ffprobe(args, *, prazo=PRAZO_SONDA_S):
    """stdout do ffprobe (vazio se falhar: quem chama decide o que fazer)."""
    proc = rodar(["ffprobe", "-v", "error", *args], prazo=prazo)
    return proc.stdout or ""

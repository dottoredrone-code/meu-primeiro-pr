import shutil
import subprocess
import unicodedata
from pathlib import Path

from ..rede import ErroProvedor, baixar, post_json
from .base import Provedor, data_uri, salvar


# Tamanho final por proporção (spec 03 §3.6: 1080×1920 ou 1920×1080; 1:1 e 4:5 para feed).
TAMANHOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def tamanho_do_formato(proporcao):
    """(largura, altura) da proporção; erro claro se a proporção não for conhecida."""
    try:
        return TAMANHOS[str(proporcao).strip()]
    except KeyError:
        raise ValueError(f"proporção desconhecida: {proporcao!r} (use {', '.join(TAMANHOS)})") from None


class FalVideo(Provedor):
    """Imagem → vídeo com modelos do fal.ai (Kling, Wan...)."""

    tipo = "video"

    def executar(self, imagem, prompt, saida, duracao=5, proporcao=None):
        # A proporção vem da imagem de entrada (gerada já no formato do perfil). Cada modelo nomeia o campo da imagem de um jeito (Kling v3: start_image_url; Wan: image_url).
        corpo = {"prompt": prompt, self.cfg.get("campo_imagem", "image_url"): data_uri(imagem)}
        if self.cfg.get("enviar_duracao", True):
            corpo["duration"] = str(duracao)
        r = post_json(f"https://fal.run/{self.modelo}", corpo, {"Authorization": f"Key {self.chave}"}, self.timeout)
        return salvar(saida, baixar(r["video"]["url"], timeout=self.timeout))


class KenBurnsVideo(Provedor):
    """Zoom lento sobre a imagem, feito localmente com FFmpeg.

    Não é IA, mas é gratuito e sempre funciona: garante que o vídeo
    sai mesmo quando todos os geradores pagos falham.
    """

    tipo = "video"

    def configurado(self):
        return None if shutil.which("ffmpeg") else "FFmpeg não instalado"

    def executar(self, imagem, prompt, saida, duracao=5, proporcao=None):
        """proporcao ("9:16", "16:9"…) define o tamanho do quadro; sem ela, usa largura/altura do config."""
        if proporcao:
            largura, altura = tamanho_do_formato(proporcao)
        else:
            largura, altura = self.cfg.get("largura", 1280), self.cfg.get("altura", 720)
        fps = self.cfg.get("fps", 25)
        quadros = max(2, round(float(duracao) * fps))
        z, x, y = movimento(prompt, quadros - 1)
        # Amplia e recorta para cobrir o quadro antes do zoom (evita tremido e distorção).
        filtro = (
            f"scale={largura * 2}:{altura * 2}:force_original_aspect_ratio=increase,"
            f"crop={largura * 2}:{altura * 2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={quadros}:s={largura}x{altura}:fps={fps},setsar=1"
        )
        saida = Path(saida)
        saida.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(imagem), "-vf", filtro,
               "-frames:v", str(quadros), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(saida)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ErroProvedor(f"ffmpeg falhou: {proc.stderr.strip()[:300]}")
        return saida


# Movimento lido do prompt_movimento do roteiro (pt-BR ou inglês). Padrão: aproximar devagar.
_MOVIMENTOS = [
    ("afastar", ("zoom out", "afast", "recu", "abrir")),
    ("direita", ("pan right", "direita")),
    ("esquerda", ("pan left", "esquerda")),
    ("subir", ("tilt up", "para cima", "sobe", "subi")),
    ("descer", ("tilt down", "para baixo", "desce", "desc")),
]


def movimento(prompt, ultimo):
    """Expressões (z, x, y) do zoompan para o movimento pedido; `on` vai de 0 a `ultimo`."""
    t = "".join(c for c in unicodedata.normalize("NFD", str(prompt or "").lower()) if unicodedata.category(c) != "Mn")
    tipo = next((nome for nome, chaves in _MOVIMENTOS if any(k in t for k in chaves)), "aproximar")
    p = f"(on/{max(1, ultimo)})"  # progresso 0 → 1
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return {
        "aproximar": (f"1+0.2*{p}", cx, cy),
        "afastar": (f"1.2-0.2*{p}", cx, cy),
        "direita": ("1.15", f"(iw-iw/zoom)*{p}", cy),
        "esquerda": ("1.15", f"(iw-iw/zoom)*(1-{p})", cy),
        "subir": ("1.15", cx, f"(ih-ih/zoom)*(1-{p})"),
        "descer": ("1.15", cx, f"(ih-ih/zoom)*{p}"),
    }[tipo]

import re
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

    def executar(self, imagem, prompt, saida, duracao=5, proporcao=None, clima=None):
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

    def executar(self, imagem, prompt, saida, duracao=5, proporcao=None, clima=None):
        """proporcao ("9:16", "16:9"…) define o tamanho do quadro; sem ela, usa largura/altura do config.
        clima (do roteiro): efeitos leves por clima (efeitos_do_clima); sem clima, só o movimento."""
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
        if clima and self.cfg.get("efeitos", True):
            filtro += "," + ",".join(efeitos_do_clima(clima, largura, altura))
        saida = Path(saida)
        saida.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(imagem), "-vf", filtro,
               "-frames:v", str(quadros), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(saida)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ErroProvedor(f"ffmpeg falhou: {proc.stderr.strip()[:300]}")
        return saida


# Movimento lido do prompt_movimento do roteiro (pt-BR ou inglês). Padrão: aproximar devagar.
# Palavras inteiras; em "da direita para a esquerda" vale o destino.
_MOVIMENTOS = [
    ("afastar", r"\bzoom out\b|\bafast\w*|\brecu(ar|a|ando)\b"),
    ("direita", r"\b(pan|move|moves) right\b|\bdireita\b"),
    ("esquerda", r"\b(pan|move|moves) left\b|\besquerda\b"),
    ("subir", r"\btilt up\b|\bs[uo]b(ir|indo|e)\b|\bpara cima\b"),
    ("descer", r"\btilt down\b|\bdesc(er|endo|e)\b|\bpara baixo\b"),
]
_DESTINO = {"direita": "direita", "esquerda": "esquerda", "cima": "subir", "baixo": "descer",
            "right": "direita", "left": "esquerda"}


def movimento(prompt, ultimo):
    """Expressões (z, x, y) do zoompan para o movimento pedido; `on` vai de 0 a `ultimo`."""
    t = "".join(c for c in unicodedata.normalize("NFD", str(prompt or "").lower()) if unicodedata.category(c) != "Mn")
    destino = re.search(r"\b(?:para|pra|to)(?: a| o| the)? (direita|esquerda|cima|baixo|right|left)\b", t)
    if destino:
        tipo = _DESTINO[destino.group(1)]
    else:
        tipo = next((nome for nome, padrao in _MOVIMENTOS if re.search(padrao, t)), "aproximar")
    q = f"(on/{max(1, ultimo)})"  # progresso 0 → 1
    p = f"({q}*{q}*(3-2*{q}))"  # com aceleração suave: começa e termina devagar (como câmera de verdade)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    deriva = f"1.12+0.06*{p}"  # nos pans, um leve zoom junto dá sensação de profundidade
    return {
        "aproximar": (f"1+0.22*{p}", cx, cy),
        "afastar": (f"1.22-0.22*{p}", cx, cy),
        "direita": (deriva, f"(iw-iw/zoom)*{p}", cy),
        "esquerda": (deriva, f"(iw-iw/zoom)*(1-{p})", cy),
        "subir": (deriva, cx, f"(ih-ih/zoom)*(1-{p})"),
        "descer": (deriva, cx, f"(ih-ih/zoom)*{p}"),
    }[tipo]


def efeitos_do_clima(clima, largura, altura):
    """Filtros leves do FFmpeg por clima da cena (vinheta, brilho que pulsa, granulado, tremor, cor)."""
    clima = str(clima or "").strip().lower()
    filtros = ["vignette=PI/5"]  # bordas um pouco mais escuras: o olhar vai para o centro
    if clima in ("alegre", "inspirador"):
        filtros.append("eq=brightness='0.035*sin(2*PI*t/2.5)':saturation=1.08:eval=frame")
    elif clima == "epico":
        filtros = ["vignette=PI/4", "eq=contrast=1.08:saturation=1.12"]
    elif clima == "reflexivo":
        filtros.append("noise=alls=6:allf=t")  # granulado de filme
    elif clima == "tenso":
        m = max(8, largura // 90)  # tremor discreto: recorta uma janela que oscila e volta ao tamanho
        filtros = ["vignette=PI/4", f"crop={largura - 2 * m}:{altura - 2 * m}:'{m}+{m * 0.6:.1f}*sin(t*17)':"
                   f"'{m}+{m * 0.6:.1f}*cos(t*13)'", f"scale={largura}:{altura}"]
    return filtros

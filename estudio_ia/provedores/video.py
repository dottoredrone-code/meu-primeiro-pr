import shutil
import subprocess
from pathlib import Path

from ..rede import ErroProvedor, post_json, requisitar
from .base import Provedor, data_uri, salvar


class FalVideo(Provedor):
    """Imagem → vídeo com modelos do fal.ai (Kling, Wan...)."""

    tipo = "video"

    def executar(self, imagem, prompt, saida, duracao=5):
        corpo = {"prompt": prompt, "image_url": data_uri(imagem)}
        if self.cfg.get("enviar_duracao", True):
            corpo["duration"] = str(duracao)
        r = post_json(f"https://fal.run/{self.modelo}", corpo, {"Authorization": f"Key {self.chave}"}, self.timeout)
        return salvar(saida, requisitar(r["video"]["url"], timeout=self.timeout))


class KenBurnsVideo(Provedor):
    """Zoom lento sobre a imagem, feito localmente com FFmpeg.

    Não é IA, mas é gratuito e sempre funciona: garante que o vídeo
    sai mesmo quando todos os geradores pagos falham.
    """

    tipo = "video"

    def configurado(self):
        return None if shutil.which("ffmpeg") else "FFmpeg não instalado"

    def executar(self, imagem, prompt, saida, duracao=5):
        largura, altura = self.cfg.get("largura", 1280), self.cfg.get("altura", 720)
        fps = self.cfg.get("fps", 25)
        quadros = int(duracao * fps)
        # Amplia e recorta para cobrir o quadro antes do zoom (evita tremido e distorção).
        filtro = (
            f"scale={largura * 2}:{altura * 2}:force_original_aspect_ratio=increase,"
            f"crop={largura * 2}:{altura * 2},"
            f"zoompan=z='min(zoom+0.0012,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={quadros}:s={largura}x{altura}:fps={fps}"
        )
        saida = Path(saida)
        saida.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(imagem), "-vf", filtro,
               "-frames:v", str(quadros), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(saida)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ErroProvedor(f"ffmpeg falhou: {proc.stderr.strip()[:300]}")
        return saida

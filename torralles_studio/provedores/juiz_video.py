"""Juiz que assiste o vídeo inteiro, com som (K06, spec 10 nível 4).

Recebe um arquivo de vídeo local ou um link do YouTube (para analisar referências sem baixar) e devolve
o texto da resposta do modelo (JSON na régua, validado pelo Avaliador).
"""

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..rede import ErroProvedor, post_json
from .base import Provedor

# A API aceita ~20 MB por pedido; em base64 o arquivo cresce 4/3, então o limite do arquivo bruto é ~14 MB.
LIMITE_INLINE_MB = 14
_HOSTS_YOUTUBE = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
# Tipos aceitos pela API (lista de vídeo do Gemini); outros formatos são convertidos para mp4 antes.
_MIME = {".mp4": "video/mp4", ".mov": "video/mov", ".webm": "video/webm", ".mpeg": "video/mpeg",
         ".mpg": "video/mpg", ".avi": "video/avi", ".wmv": "video/wmv", ".flv": "video/x-flv", ".3gp": "video/3gpp"}


def eh_youtube(video):
    """Link de UM vídeo do YouTube (watch?v=, shorts/, live/ ou youtu.be/<id>); canal e playlist não servem."""
    u = urlparse(str(video).strip())
    host = (u.hostname or "").lower()
    if u.scheme.lower() not in ("http", "https") or host not in _HOSTS_YOUTUBE:
        return False
    if host == "youtu.be":
        return len(u.path.strip("/")) > 0
    if u.path.rstrip("/") == "/watch":
        return bool((parse_qs(u.query).get("v") or [""])[0].strip())
    partes = u.path.strip("/").split("/")
    return len(partes) >= 2 and partes[0] in ("shorts", "live") and bool(partes[1])


def versao_leve(video, pasta, altura=720):
    """Cópia menor para caber no pedido (720p, CRF 32, áudio 64 kbps). Exige FFmpeg."""
    if not shutil.which("ffmpeg"):
        raise ErroProvedor("vídeo grande demais para enviar e FFmpeg não está instalado para reduzir")
    saida = Path(pasta) / "leve.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"scale=-2:'min({altura},trunc(ih/2)*2)'",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "64k", str(saida)]
    r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise ErroProvedor(f"não consegui reduzir o vídeo: {r.stderr[-300:]}")
    return saida


class GeminiVideoJuiz(Provedor):
    tipo = "juiz_video"

    def _parte_video(self, video, pasta):
        if eh_youtube(video):
            return {"file_data": {"file_uri": str(video).strip()}}
        if urlparse(str(video)).scheme in ("http", "https"):
            raise ErroProvedor("só links do YouTube podem ser assistidos direto; baixe o vídeo para avaliar")
        caminho = Path(video)
        if not caminho.is_file():
            raise ErroProvedor(f"vídeo não encontrado: {caminho}")
        limite = self.cfg.get("limite_inline_mb", LIMITE_INLINE_MB) * 1024 * 1024
        if caminho.stat().st_size > limite or caminho.suffix.lower() not in _MIME:
            caminho = versao_leve(caminho, pasta)  # grande demais ou formato que a API não aceita (.mkv…)
            if caminho.stat().st_size > limite:
                raise ErroProvedor("vídeo grande demais mesmo reduzido: envie um trecho ou um link do YouTube")
        mime = _MIME[caminho.suffix.lower()]
        return {"inline_data": {"mime_type": mime, "data": base64.b64encode(caminho.read_bytes()).decode()}}

    def executar(self, video, prompt, sistema=None):
        with tempfile.TemporaryDirectory() as pasta:
            corpo = {
                "contents": [{"parts": [self._parte_video(video, pasta), {"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            }
            if self.cfg.get("temperatura") is not None:
                corpo["generationConfig"]["temperature"] = self.cfg["temperatura"]
        if sistema:
            corpo["systemInstruction"] = {"parts": [{"text": sistema}]}
        r = post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent",
            corpo, {"x-goog-api-key": self.chave}, self.timeout,
        )
        try:
            partes = r["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            motivo = (r.get("promptFeedback") or {}).get("blockReason") if isinstance(r, dict) else None
            raise ErroProvedor(f"resposta sem conteúdo do juiz de vídeo{f' (bloqueio: {motivo})' if motivo else ''}")
        texto = "".join(p.get("text", "") for p in partes).strip()
        if not texto:
            raise ErroProvedor("o juiz de vídeo respondeu vazio")
        return texto

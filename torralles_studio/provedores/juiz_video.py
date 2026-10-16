"""Juiz que assiste o vídeo inteiro, com som (K06, spec 10 nível 4).

Recebe um arquivo de vídeo local ou um link do YouTube (para analisar referências sem baixar) e devolve
o texto da resposta do modelo (JSON na régua, validado pelo Avaliador).
"""

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from ..rede import ErroProvedor, post_json
from .base import Provedor

LIMITE_INLINE_MB = 18  # a API aceita até ~20 MB por pedido; acima disso, uma cópia leve é enviada
_HOSTS_YOUTUBE = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_MIME = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".mkv": "video/x-matroska"}


def eh_youtube(video):
    texto = str(video)
    return urlparse(texto).scheme in ("http", "https") and (urlparse(texto).hostname or "").lower() in _HOSTS_YOUTUBE


def versao_leve(video, pasta, altura=720):
    """Cópia menor para caber no pedido (720p, CRF 32, áudio 64 kbps). Exige FFmpeg."""
    if not shutil.which("ffmpeg"):
        raise ErroProvedor("vídeo grande demais para enviar e FFmpeg não está instalado para reduzir")
    saida = Path(pasta) / "leve.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"scale=-2:'min({altura},ih)'",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-c:a", "aac", "-b:a", "64k", str(saida)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ErroProvedor(f"não consegui reduzir o vídeo: {r.stderr[-300:]}")
    return saida


class GeminiVideoJuiz(Provedor):
    tipo = "juiz_video"

    def _parte_video(self, video, pasta):
        if eh_youtube(video):
            return {"file_data": {"file_uri": str(video), "mime_type": "video/*"}}
        if urlparse(str(video)).scheme in ("http", "https"):
            raise ErroProvedor("só links do YouTube podem ser assistidos direto; baixe o vídeo para avaliar")
        caminho = Path(video)
        if not caminho.is_file():
            raise ErroProvedor(f"vídeo não encontrado: {caminho}")
        limite = self.cfg.get("limite_inline_mb", LIMITE_INLINE_MB) * 1024 * 1024
        if caminho.stat().st_size > limite:
            caminho = versao_leve(caminho, pasta)
            if caminho.stat().st_size > limite:
                raise ErroProvedor("vídeo grande demais mesmo reduzido: envie um trecho ou um link do YouTube")
        mime = _MIME.get(caminho.suffix.lower(), "video/mp4")
        return {"inline_data": {"mime_type": mime, "data": base64.b64encode(caminho.read_bytes()).decode()}}

    def executar(self, video, prompt, sistema=None):
        with tempfile.TemporaryDirectory() as pasta:
            corpo = {
                "contents": [{"parts": [self._parte_video(video, pasta), {"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            }
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

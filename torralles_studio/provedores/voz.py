import asyncio
import base64
import importlib.util
from pathlib import Path

from ..rede import ErroProvedor, post_json, requisitar
from .base import Provedor, salvar


class ElevenLabsVoz(Provedor):
    tipo = "voz"

    def executar(self, texto, saida):
        voz = self.cfg.get("voz_id", "21m00Tcm4TlvDq8ikWAM")
        dados = requisitar(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voz}?output_format=mp3_44100_128",
            metodo="POST",
            corpo={"text": texto, "model_id": self.modelo},
            cabecalhos={"xi-api-key": self.chave},
            timeout=self.timeout,
        )
        return salvar(saida, dados)


class OpenAIVoz(Provedor):
    tipo = "voz"

    def executar(self, texto, saida):
        dados = requisitar(
            "https://api.openai.com/v1/audio/speech",
            metodo="POST",
            corpo={
                "model": self.modelo,
                "voice": self.cfg.get("voz", "alloy"),
                "input": texto,
                "response_format": "mp3",
            },
            cabecalhos={"Authorization": f"Bearer {self.chave}"},
            timeout=self.timeout,
        )
        return salvar(saida, dados)


class EdgeVoz(Provedor):
    """Vozes neurais do Microsoft Edge via pacote `edge-tts` (gratuito, não oficial)."""

    tipo = "voz"

    def configurado(self):
        if importlib.util.find_spec("edge_tts") is None:
            return "instale com: pip install edge-tts"
        return None

    def executar(self, texto, saida):
        import edge_tts

        saida = Path(saida)
        saida.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(edge_tts.Communicate(texto, self.cfg.get("voz", "pt-BR-FranciscaNeural")).save(str(saida)))
        return saida


class GeminiVoz(Provedor):
    """Voz do Gemini (TTS) com a mesma chave do texto e do juiz. Fala pt-BR natural e aceita instrução de tom.

    A resposta traz o áudio em base64; o formato vem no próprio mimeType (PCM cru "audio/L16;…rate=24000" vira WAV
    com o módulo wave; outro formato é gravado como veio). Saída com outra extensão (.mp3) é convertida pelo FFmpeg.
    """

    tipo = "voz"

    def executar(self, texto, saida):
        tom = self.cfg.get("tom", "Fale em português do Brasil, com naturalidade, ritmo de vídeo curto e "
                                   "pronúncia clara (lh, nh, r e rr bem marcados)")
        corpo = {
            "contents": [{"parts": [{"text": f"{tom}: {texto}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {
                                     "voiceName": self.cfg.get("voz", "Kore")}}}},
        }
        r = post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent",
                      corpo, {"x-goog-api-key": self.chave}, self.timeout)
        try:
            parte = next(p["inlineData"] for p in r["candidates"][0]["content"]["parts"] if "inlineData" in p)
        except (KeyError, IndexError, StopIteration, TypeError):
            raise ErroProvedor("o Gemini não devolveu áudio") from None
        dados, mime = base64.b64decode(parte["data"]), str(parte.get("mimeType", "")).lower()
        if not dados:
            raise ErroProvedor("o Gemini devolveu áudio vazio")
        return _gravar_audio(dados, mime, Path(saida))


def _gravar_audio(dados, mime, saida):
    import re
    import shutil
    import subprocess
    import tempfile
    import wave

    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as pasta:
        tipo = mime.split(";")[0].strip()
        if tipo in ("audio/l16", "audio/pcm"):  # PCM cru: 16 bits, little-endian, mono; taxa no mimeType
            achada = re.search(r"rate=(\d+)", mime)
            taxa = int(achada.group(1)) if achada else 24000  # padrão do Gemini TTS quando o mime não diz
            bruto = Path(pasta) / "voz.wav"
            with wave.open(str(bruto), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(taxa)
                w.writeframes(dados)
        else:
            extensao = {"audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
                        "audio/ogg": ".ogg"}.get(mime.split(";")[0], ".bin")
            bruto = Path(pasta) / f"voz{extensao}"
            bruto.write_bytes(dados)
        if bruto.suffix == saida.suffix.lower():
            shutil.copyfile(bruto, saida)
            return saida
        proc = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(bruto), str(saida)], capture_output=True,
                              stdin=subprocess.DEVNULL, text=True)
        if proc.returncode != 0:
            raise ErroProvedor(f"ffmpeg falhou ao converter a voz: {proc.stderr.strip()[-200:]}")
        return saida

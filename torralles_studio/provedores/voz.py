import asyncio
import base64
import importlib.util
from pathlib import Path

from ..rede import ErroProvedor, post_json, requisitar
from .base import Provedor, salvar

PRAZO_CONVERTER_S = 120  # converter uma fala curta leva segundos: passou disso, o FFmpeg travou


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


RAIZ = Path(__file__).resolve().parents[2]
FERRAMENTA_KOKORO = RAIZ / "ferramentas" / "kokoro_tts.py"


_KOKORO_ISOLADO = {}


def _kokoro_no_isolado():
    """O processo separado (python -I, sem o site-packages do usuário) acha o kokoro-onnx? Confere uma vez."""
    if "ok" not in _KOKORO_ISOLADO:
        import subprocess
        import sys

        try:
            proc = subprocess.run([sys.executable, "-I", "-c",
                                   "import importlib.util as u, sys; sys.exit(u.find_spec('kokoro_onnx') is None)"],
                                  capture_output=True, stdin=subprocess.DEVNULL, timeout=30)
            _KOKORO_ISOLADO["ok"] = proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            _KOKORO_ISOLADO["ok"] = False
    return _KOKORO_ISOLADO["ok"]


class KokoroVoz(Provedor):
    """Kokoro-82M em português, no próprio PC e grátis (K42). Roda em processo separado (ferramentas/kokoro_tts.py):
    o Studio não importa o Kokoro nem o fonemizador, que é GPL-3 (D26)."""

    tipo = "voz"

    def _arquivo(self, campo, padrao):
        caminho = Path(self.cfg.get(campo, padrao))
        return caminho if caminho.is_absolute() else RAIZ / caminho

    def configurado(self):
        if importlib.util.find_spec("kokoro_onnx") is None or not _kokoro_no_isolado():
            return "opcional: pip install kokoro-onnx, sem --user (fonemizador GPL-3, veja D26)"
        for campo, padrao in (("modelo_arquivo", "dados/modelos/kokoro/kokoro-v1.0.int8.onnx"),
                              ("vozes_arquivo", "dados/modelos/kokoro/voices-v1.0.bin")):
            if not self._arquivo(campo, padrao).is_file():
                return f"falta o arquivo do modelo {self._arquivo(campo, padrao).name} (docs/teste-real.md)"
        return None

    def executar(self, texto, saida):
        import sys
        import tempfile

        from .. import ff

        saida = Path(saida)
        modelo = self._arquivo("modelo_arquivo", "dados/modelos/kokoro/kokoro-v1.0.int8.onnx")
        vozes = self._arquivo("vozes_arquivo", "dados/modelos/kokoro/voices-v1.0.bin")
        with tempfile.TemporaryDirectory() as pasta:
            entrada, wav = Path(pasta) / "fala.txt", Path(pasta) / "fala.wav"
            entrada.write_text(str(texto), encoding="utf-8")
            proc = ff.rodar([sys.executable, "-I", str(FERRAMENTA_KOKORO), "--texto-arquivo", str(entrada),
                             "--saida", str(wav), "--voz", str(self.cfg.get("voz", "pf_dora")),
                             "--velocidade", str(float(self.cfg.get("velocidade", 1.0))),
                             "--modelo", str(modelo), "--vozes", str(vozes)], prazo=self.timeout, cwd=RAIZ)
            if proc.returncode != 0 or not wav.is_file():
                raise ErroProvedor(f"o Kokoro falhou: {(proc.stderr or '').strip()[-300:] or 'sem detalhe'}")
            return _gravar_audio(wav.read_bytes(), "audio/wav", saida)


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
    import tempfile
    import wave

    from .. import ff

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
        ff.ffmpeg(["-v", "error", "-i", str(bruto), str(saida)], prazo=PRAZO_CONVERTER_S,
                  falha="ffmpeg falhou ao converter a voz", limite=200)
        return saida

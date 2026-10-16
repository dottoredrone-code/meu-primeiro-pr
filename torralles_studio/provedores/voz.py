import asyncio
import importlib.util
from pathlib import Path

from ..rede import requisitar
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

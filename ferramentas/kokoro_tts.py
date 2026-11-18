"""Ferramenta externa e opcional: fala em português com o Kokoro-82M (K42, D26).

Roda em processo separado, chamada pelo provedor `kokoro` do Studio (como o FFmpeg): o Studio não importa o
Kokoro nem o fonemizador. Motivo: o `kokoro-onnx` (MIT) e os pesos do Kokoro (Apache-2.0) usam o `phonemizer`
e o `espeak-ng`, que são GPL-3. Esta ferramenta não vai junto com o Studio; quem quiser instala:

    pip install kokoro-onnx
    (modelo em dados/modelos/kokoro/, veja docs/teste-real.md)

Uso: python ferramentas/kokoro_tts.py --texto-arquivo fala.txt --saida fala.wav [--voz pf_dora] [--velocidade 1.0]
     [--modelo ...onnx] [--vozes ...bin]
"""

import argparse
import sys
import wave
from pathlib import Path


def main(argv=None):
    p = argparse.ArgumentParser(description="Kokoro em português (pt-br) → WAV mono 16 bits")
    p.add_argument("--texto-arquivo", required=True, help="arquivo UTF-8 com o texto da fala")
    p.add_argument("--saida", required=True, help="arquivo .wav de saída")
    p.add_argument("--voz", default="pf_dora", help="pf_dora, pm_alex ou pm_santa")
    p.add_argument("--velocidade", type=float, default=1.0)
    p.add_argument("--modelo", default="dados/modelos/kokoro/kokoro-v1.0.int8.onnx")
    p.add_argument("--vozes", default="dados/modelos/kokoro/voices-v1.0.bin")
    a = p.parse_args(argv)

    import numpy as np
    from kokoro_onnx import Kokoro

    texto = Path(a.texto_arquivo).read_text(encoding="utf-8").strip()
    if not texto:
        print("texto vazio", file=sys.stderr)
        return 2
    amostras, taxa = Kokoro(a.modelo, a.vozes).create(texto, voice=a.voz, speed=a.velocidade, lang="pt-br")
    if amostras is None or len(amostras) == 0:
        print("o Kokoro não gerou áudio", file=sys.stderr)
        return 3
    saida = Path(a.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(saida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(taxa))
        w.writeframes((np.clip(amostras, -1, 1) * 32767).astype("<i2").tobytes())
    return 0


if __name__ == "__main__":
    sys.exit(main())

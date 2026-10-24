import base64
import math
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio.pronuncia import conferir_voz, limpar_transcricao, taxa_erro
from torralles_studio.provedores import voz as voz_mod
from torralles_studio.rede import ErroProvedor


class TestTaxaDeErro(unittest.TestCase):
    def test_wer(self):
        self.assertEqual(taxa_erro("Olha que vermelho!", "olha que vermelho"), 0.0)
        self.assertEqual(taxa_erro("olha que vermelho bonito", "ola que vermelo bonito"), 0.5)  # lh virou l
        self.assertEqual(taxa_erro("um dois", "um dois três"), 0.5)
        self.assertEqual(taxa_erro("", ""), 0.0)

    def test_limpa_marcas_da_transcricao(self):
        texto = "[00:01] Olha que vermelho.\n[00:03.5] O filho chegou.\nSONS: música suave aos 00:02"
        self.assertEqual(" ".join(limpar_transcricao(texto).split()), "Olha que vermelho. O filho chegou.")

    def test_conferir_voz(self):
        ok = conferir_voz("x.mp3", "olha o filho", transcrever=lambda a, p: {"texto": "[00:00] Olha o filho", "motor": "t"})
        self.assertEqual((ok["wer"], ok["ok"]), (0.0, True))
        ruim = conferir_voz("x.mp3", "olha o filho", transcrever=lambda a, p: {"texto": "ola o filo", "motor": "t"})
        self.assertFalse(ruim["ok"])
        self.assertIsNone(conferir_voz("x.mp3", "olha", transcrever=lambda a, p: {"texto": None, "motivo": "sem chave"}))


def _pcm(segundos=0.5, taxa=24000):
    return b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / taxa)))
                    for i in range(int(segundos * taxa)))


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestGeminiVoz(unittest.TestCase):
    def resposta(self, dados, mime):
        return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime,
                                                                      "data": base64.b64encode(dados).decode()}}]}}]}

    def test_pcm_vira_mp3_com_a_duracao_certa(self):
        pedidos = []

        def falso(url, corpo, cab, timeout):
            pedidos.append((url, corpo))
            return self.resposta(_pcm(0.5), "audio/L16;codec=pcm;rate=24000")

        prov = voz_mod.GeminiVoz("gemini_voz", {"modelo": "m-tts", "voz": "Kore", "chave_env": "CHAVE_X"})
        with tempfile.TemporaryDirectory() as d, mock.patch.object(voz_mod, "post_json", falso):
            saida = prov.executar("Olha que vermelho", Path(d) / "voz.mp3")
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(saida)], capture_output=True, text=True)
            self.assertAlmostEqual(float(r.stdout), 0.5, delta=0.1)
        url, corpo = pedidos[0]
        self.assertIn("m-tts:generateContent", url)
        self.assertEqual(corpo["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(corpo["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"],
                         "Kore")
        self.assertIn("Olha que vermelho", corpo["contents"][0]["parts"][0]["text"])

    def test_sem_audio_e_erro(self):
        prov = voz_mod.GeminiVoz("gemini_voz", {"modelo": "m"})
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(voz_mod, "post_json", lambda *a: {"candidates": [{"content": {"parts": [{"text": "x"}]}}]}):
            with self.assertRaises(ErroProvedor):
                prov.executar("oi", Path(d) / "v.mp3")


if __name__ == "__main__":
    unittest.main()

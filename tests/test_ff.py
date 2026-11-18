import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio import ff
from torralles_studio.rede import ErroProvedor


class TestRodar(unittest.TestCase):
    def test_travado_vira_erro_de_provedor(self):
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 5)):
            with self.assertRaises(ErroProvedor) as ctx:
                ff.ffmpeg(["-i", "x.wav", "y.wav"], prazo=5)
        self.assertIn("travou", str(ctx.exception))

    def test_sem_programa_vira_erro_de_provedor(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(ErroProvedor) as ctx:
                ff.ffprobe(["x.mp4"])
        self.assertIn("não instalado", str(ctx.exception))

    def test_sempre_com_prazo_e_utf8(self):
        feito = subprocess.CompletedProcess([], 0, "", "log")
        with mock.patch("subprocess.run", return_value=feito) as run:
            ff.ffmpeg(["-i", "x.wav", "y.wav"])
            ff.ffprobe(["x.mp4"])
        for chamada in run.call_args_list:
            self.assertEqual(chamada.kwargs["encoding"], "utf-8")
            self.assertEqual(chamada.kwargs["errors"], "replace")
            self.assertGreater(chamada.kwargs["timeout"], 0)
            self.assertIs(chamada.kwargs["stdin"], subprocess.DEVNULL)
        with mock.patch("subprocess.run", return_value=feito) as run:
            ff.rodar(["ffmpeg"], binario=True, prazo=7)
        self.assertNotIn("encoding", run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs["timeout"], 7)

    def test_falha_traz_o_fim_do_log(self):
        with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "x" * 50 + "erro")):
            with self.assertRaises(ErroProvedor) as ctx:
                ff.ffmpeg(["-i", "a"], falha="ffmpeg falhou no teste", limite=10)
        self.assertEqual(str(ctx.exception), "ffmpeg falhou no teste: xxxxxxerro")


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestCaminhoComAcento(unittest.TestCase):
    def test_mede_arquivo_em_pasta_com_acento(self):  # no Windows o padrão cp1252 quebrava o log do FFmpeg
        from torralles_studio.montagem import duracao, medir_volume, trecho_falado

        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d) / "canção ação ç ã é"
            pasta.mkdir()
            voz = pasta / "narração—teste.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1",
                            "-af", "adelay=300,apad=pad_dur=0.3", str(voz)], check=True)
            self.assertAlmostEqual(duracao(voz), 1.6, delta=0.05)
            self.assertIsNotNone(medir_volume(voz)["lufs"])
            ini, fim, _ = trecho_falado(voz)
            self.assertAlmostEqual(ini, 0.3, delta=0.05)
            with self.assertRaises(ErroProvedor) as ctx:  # o erro também sai legível (sem UnicodeDecodeError)
                ff.ffmpeg(["-i", str(pasta / "não_existe.wav"), "-f", "null", "-"])
            self.assertIn("ffmpeg falhou", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

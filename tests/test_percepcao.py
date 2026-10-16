import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from estudio_ia.percepcao import analisar_video


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestPercepcao(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.video = self.dir / "teste.mp4"
        # 2 s vermelho + 2 s azul (um corte), com 1,5 s de tom e depois silêncio.
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=red:s=320x240:d=2:r=25",
             "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2:r=25",
             "-f", "lavfi", "-i", "sine=f=440:d=1.5",
             "-filter_complex", "[0][1]concat=n=2:v=1:a=0[v];[2]apad=whole_dur=4[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             str(self.video)],
            check=True,
        )

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_relatorio_tem_olhos_e_ouvidos(self):
        rel = analisar_video(self.video, self.dir / "saida", transcrever_audio=False)
        self.assertAlmostEqual(rel["duracao_s"], 4.0, delta=0.2)
        self.assertEqual((rel["largura"], rel["altura"]), (320, 240))
        self.assertTrue(any(1.8 <= c <= 2.2 for c in rel["cortes_s"]), rel["cortes_s"])
        self.assertTrue(rel["som"]["silencios_s"], "deveria detectar o silêncio depois do tom")
        self.assertIsNotNone(rel["som"]["lufs_integrado"])
        self.assertTrue(Path(rel["folha_contato"]).exists())
        self.assertTrue(all(Path(q).exists() for q in rel["quadros"]))
        self.assertTrue((self.dir / "saida" / "percepcao.json").exists())
        json.loads((self.dir / "saida" / "percepcao.json").read_text())

    def test_sem_motor_de_transcricao_explica_o_motivo(self):
        rel = analisar_video(self.video, self.dir / "saida")
        transcricao = rel["transcricao"]
        if transcricao["texto"] is None:
            self.assertIn("motivo", transcricao)


if __name__ == "__main__":
    unittest.main()

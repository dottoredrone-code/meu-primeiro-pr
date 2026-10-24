import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from torralles_studio.exportar import ErroExportacao, exportar_capcut
from torralles_studio.montagem import duracao, montar


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestExportarCapCut(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)

    def tearDown(self):
        self._d.cleanup()

    def montagem(self, trilha=False):
        cenas = []
        for i in (1, 2):
            _ff("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:d=3", "-pix_fmt", "yuv420p", str(self.d / f"c{i}.mp4"))
            _ff("-f", "lavfi", "-i", "sine=f=300:d=1.4", "-af", "adelay=200,apad=pad_dur=0.3", str(self.d / f"v{i}.wav"))
            cenas.append({"video": self.d / f"c{i}.mp4", "voz": self.d / f"v{i}.wav", "narracao": f"Cena número {i}."})
        musica = None
        if trilha:
            musica = self.d / "m.wav"
            _ff("-f", "lavfi", "-i", "sine=f=110:d=3", str(musica))
        return montar(cenas, self.d / "final.mp4", tamanho=(180, 320), trilha=musica, cfg={"preset": "ultrafast"},
                      pasta_trabalho=self.d / "trabalho")

    def test_pasta_pronta_para_o_capcut(self):
        r = self.montagem(trilha=True)
        destino = exportar_capcut(r, self.d / "capcut", creditos="Créditos:\n- Música por Bia", titulo="Chá verde")
        cenas = sorted((destino / "01_clipes").glob("*.mp4"))
        self.assertEqual([c.name for c in cenas], ["cena_01.mp4", "cena_02.mp4"])
        for c, tp in zip(cenas, r["tempos"]):  # cada clipe com a duração exata da cena (sem a sobra da transição)
            self.assertAlmostEqual(duracao(c), tp["duracao"], delta=0.08)
        self.assertAlmostEqual(sum(duracao(c) for c in cenas), r["duracao_s"], delta=0.15)
        for arq in ("02_audio/narracao.wav", "02_audio/trilha.wav", "03_legendas/legendas.srt", "video_final.mp4"):
            self.assertTrue((destino / arq).is_file(), arq)
        leia = (destino / "LEIA-ME.txt").read_text(encoding="utf-8")
        self.assertIn("Importar legendas", leia)
        self.assertIn("Música por Bia", leia)
        linha = json.loads((destino / "linha_do_tempo.json").read_text(encoding="utf-8"))
        self.assertEqual(len(linha["cenas"]), 2)

    def test_sem_trilha_e_refazer_limpa_a_pasta(self):
        r = self.montagem()
        destino = self.d / "capcut"
        destino.mkdir()
        (destino / "velho.txt").write_text("x")
        exportar_capcut(r, destino)
        self.assertFalse((destino / "velho.txt").exists())
        self.assertFalse((destino / "02_audio" / "trilha.wav").exists())
        self.assertNotIn("trilha.wav", (destino / "LEIA-ME.txt").read_text(encoding="utf-8"))

    def test_trilha_de_montagem_antiga_nao_e_exportada(self):  # verificador K23: crédito (D18)
        com = self.montagem(trilha=True)
        self.assertTrue(com["trilha"])
        sem = self.montagem(trilha=False)  # mesma pasta de trabalho, agora sem trilha
        self.assertFalse((self.d / "trabalho" / "trilha.wav").exists())
        destino = exportar_capcut(sem, self.d / "capcut")
        self.assertFalse((destino / "02_audio" / "trilha.wav").exists())

    def test_clipes_somam_a_linha_do_tempo_em_quadros(self):  # verificador K23: cortes não atrasam
        r = self.montagem()
        destino = exportar_capcut(r, self.d / "capcut")
        quadros = 0
        for c in sorted((destino / "01_clipes").glob("*.mp4")):
            saida = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                    "stream=nb_read_frames", "-of", "csv=p=0", str(c)], capture_output=True, text=True)
            quadros += int(saida.stdout.strip())
        self.assertEqual(quadros, round(r["duracao_s"] * r["fps"]))

    def test_pasta_movida_exporta_pelo_comando(self):
        import io
        import json as js
        from contextlib import redirect_stdout

        from torralles_studio.__main__ import main

        r = self.montagem()
        video = self.d / "video"
        video.mkdir()
        (video / "montagem.json").write_text(js.dumps(r))
        (self.d / "trabalho").rename(video / "montagem")  # como se a pasta tivesse sido movida
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["exportar-capcut", str(video)]), 0)
        self.assertTrue((video / "capcut" / "02_audio" / "narracao.wav").is_file())

    def test_sem_arquivos_de_trabalho_explica(self):
        with self.assertRaises(ErroExportacao):
            exportar_capcut({"pasta_trabalho": str(self.d / "nada"), "tempos": [{"inicio": 0, "duracao": 2}]},
                            self.d / "capcut")


if __name__ == "__main__":
    unittest.main()

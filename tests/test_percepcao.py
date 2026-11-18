import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from torralles_studio.percepcao import analisar_video


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
        from unittest import mock

        from torralles_studio import percepcao

        # sem motor nenhum (o teste não baixa o modelo do Whisper nem chama o Gemini)
        with mock.patch.object(percepcao, "whisper_disponivel", return_value=False), \
                mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            rel = analisar_video(self.video, self.dir / "saida")
        transcricao = rel["transcricao"]
        if transcricao["texto"] is None:
            self.assertIn("motivo", transcricao)


if __name__ == "__main__":
    unittest.main()


class TestFonteDaFolha(unittest.TestCase):
    def test_caminho_do_windows_escapado_para_o_ffmpeg(self):  # achado no teste do PC (Windows)
        from unittest import mock

        from torralles_studio import percepcao

        with mock.patch.object(percepcao, "_FONTES", ["C:\\Windows\\Fonts\\arial.ttf"]), \
                mock.patch.object(percepcao.Path, "is_file", return_value=True):
            self.assertEqual(percepcao._fonte(), "C\\:/Windows/Fonts/arial.ttf")
        with mock.patch.object(percepcao, "_FONTES", []):
            self.assertIsNone(percepcao._fonte())  # sem fonte: folha sai sem o tempo escrito


class TestSondar(unittest.TestCase):  # item 3 e 13
    def rodar(self, saida, codigo=0, erro=""):
        from unittest import mock

        from torralles_studio import percepcao

        proc = subprocess.CompletedProcess([], codigo, stdout=json.dumps(saida) if saida is not None else "",
                                           stderr=erro)
        with mock.patch.object(percepcao.ff, "rodar", return_value=proc):
            return percepcao._sondar("x.mp4")

    def test_fps_zero_sobre_zero_nao_quebra(self):
        info = self.rodar({"format": {"duration": "3.0"},
                           "streams": [{"codec_type": "video", "width": 10, "height": 20, "r_frame_rate": "0/0"}]})
        self.assertEqual((info["largura"], info["fps"]), (10, None))

    def test_capa_do_audio_nao_conta_como_video(self):
        info = self.rodar({"format": {"duration": "3.0"}, "streams": [
            {"codec_type": "audio"},
            {"codec_type": "video", "width": 500, "height": 500, "r_frame_rate": "90000/1",
             "disposition": {"attached_pic": 1}}]})
        self.assertTrue(info["tem_audio"])
        self.assertNotIn("largura", info)

    def test_erro_do_ffprobe_vira_erro_provedor(self):
        from torralles_studio.rede import ErroProvedor

        with self.assertRaises(ErroProvedor) as ctx:
            self.rodar(None, codigo=1, erro="x.mp4: Invalid data found when processing input")
        self.assertIn("Invalid data", str(ctx.exception))
        with self.assertRaises(ErroProvedor):
            self.rodar({"format": {}, "streams": []})  # sem duração

    def test_fps_fracionario(self):
        from torralles_studio.percepcao import _fps

        self.assertEqual((_fps("30000/1001"), _fps("25/1"), _fps(""), _fps("x/y")), (29.97, 25.0, None, None))

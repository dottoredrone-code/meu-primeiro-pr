"""K40: clipes de banco grátis (Pexels/Pixabay) nas cenas, no lugar da imagem parada."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from torralles_studio import producao
from torralles_studio.midia import SemMidia
from torralles_studio.provedores.base import Provedor
from torralles_studio.roteador import Roteador

TEM_FFMPEG = shutil.which("ffmpeg") is not None
CENA = {"prompt_imagem": "A cup of green tea on a wooden table, steam rising", "narracao": "Chá verde."}


def _sondar(arquivo):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height:format=duration",
                        "-of", "default=nw=1", str(arquivo)], capture_output=True, text=True, check=True)
    return dict(l.split("=") for l in r.stdout.split())


class Midia(Provedor):
    tipo = "midia"

    def __init__(self, nome, motivo=None):
        super().__init__(nome, {})
        self.motivo = motivo

    def configurado(self):
        return self.motivo


class TestBancoPronto(unittest.TestCase):
    def test_so_com_chave_de_algum_banco_de_video(self):
        sem = Roteador({"pexels": Midia("pexels", "falta PEXELS_API_KEY")}, {"midia_video": ["pexels"]})
        com = Roteador({"pexels": Midia("pexels", "falta"), "pixabay": Midia("pixabay")},
                       {"midia_video": ["pexels", "pixabay"]})
        self.assertFalse(producao.banco_de_video_pronto(sem))
        self.assertTrue(producao.banco_de_video_pronto(com))
        self.assertFalse(producao.banco_de_video_pronto(Roteador({}, {})))


@unittest.skipUnless(TEM_FFMPEG, "FFmpeg não instalado")
class TestClipeDeBanco(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        self.clipe = self.pasta / "banco.mp4"  # clipe horizontal curto (2 s), como os de banco
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:d=2",
                        "-pix_fmt", "yuv420p", str(self.clipe)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cena_no_formato_vertical_e_na_duracao_da_fala_mesmo_com_clipe_curto(self):
        saida = producao._cena_de_banco(self.clipe, self.pasta / "cena.mp4", 4.5, "9:16")
        info = _sondar(saida)
        self.assertEqual((info["width"], info["height"]), ("1080", "1920"))
        self.assertAlmostEqual(float(info["duration"]), 4.5, delta=0.15)

    def test_acha_clipe_que_combina_e_tira_o_quadro_da_cena(self):
        biblioteca = SimpleNamespace(caminho=lambda ativo: self.clipe)
        ativo = {"hash": "h", "caminho": "video/h.mp4", "licenca": "pexels", "fonte": "Pexels", "autor": "A",
                 "titulo": "green tea cup"}
        consultas = []

        def buscar(roteador, bib, consulta, tipo, **kw):
            consultas.append((consulta, tipo, kw["minimo_relevancia"]))
            return ativo

        img = self.pasta / "cena_01.png"
        with mock.patch("torralles_studio.midia.buscar_midia", buscar):
            r = producao._video_de_banco(None, biblioteca, CENA, img, "9:16", None, lambda t: None)
        self.assertEqual(r["licenca"], "pexels")
        self.assertIs(r["video_banco"], True)  # guarda o ativo, não o caminho do PC
        self.assertEqual(consultas[0][1:], ("video", 1))  # nunca aceita clipe fora do tema
        self.assertTrue(img.is_file())

    def test_nada_combina_segue_para_a_imagem(self):
        def buscar(*a, **kw):
            raise SemMidia("nada")

        with mock.patch("torralles_studio.midia.buscar_midia", buscar):
            self.assertIsNone(producao._video_de_banco(None, None, CENA, self.pasta / "x.png", "9:16", None,
                                                       lambda t: None))


class TestRetomadaEPexels(unittest.TestCase):
    def test_clipe_e_achado_pela_biblioteca_e_sumido_vira_none(self):
        with tempfile.TemporaryDirectory() as pasta:
            clipe = Path(pasta) / "video" / "h.mp4"
            clipe.parent.mkdir()
            clipe.write_bytes(b"x")
            bib = SimpleNamespace(caminho=lambda ativo: Path(pasta) / ativo["caminho"])
            foto = {"caminho": "video/h.mp4", "video_banco": True}
            self.assertEqual(producao._clipe_guardado(foto, bib), clipe)
            clipe.unlink()
            self.assertIsNone(producao._clipe_guardado(foto, bib))
            self.assertIsNone(producao._clipe_guardado({"licenca": "pexels"}, bib))  # foto comum

    def test_titulo_do_video_do_pexels_vem_do_link(self):
        from torralles_studio.midia import relevancia
        from torralles_studio.provedores.midia import _titulo_do_link

        titulo = _titulo_do_link("https://www.pexels.com/video/woman-drinking-green-tea-8765432/")
        self.assertEqual(titulo, "woman drinking green tea")
        self.assertGreaterEqual(relevancia({"titulo": titulo, "tags": []}, "green tea cup"), 1)
        self.assertIsNone(_titulo_do_link(None))


if __name__ == "__main__":
    unittest.main()

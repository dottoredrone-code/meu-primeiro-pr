import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from torralles_studio.banco import Banco
from torralles_studio.biblioteca import Biblioteca
from torralles_studio.provedores.base import Provedor
from torralles_studio.roteador import Roteador
from torralles_studio.trilha import SemTrilha, clima_dominante, escolher_trilha, medir_ritmo, pontuar, tem_voz


def _musica(arquivo, bpm, segundos=20):
    p = 60 / bpm
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"aevalsrc='0.6*sin(2*PI*110*t)*exp(-12*mod(t,{p}))+0.05*sin(2*PI*330*t)':s=22050:d={segundos}",
                    "-c:a", "libmp3lame", str(arquivo)], check=True)
    return Path(arquivo)


class TestRegras(unittest.TestCase):
    def test_clima_dominante(self):
        self.assertEqual(clima_dominante({"cenas": [{"clima": "alegre"}, {"clima": "calmo"}, {"clima": "alegre"}]}),
                         "alegre")
        self.assertEqual(clima_dominante({"cenas": []}), "inspirador")

    def test_voz_e_eliminatoria(self):
        self.assertTrue(tem_voz({"titulo": "Summer Song (feat. Ana)"}))
        self.assertTrue(tem_voz({"titulo": "Calm", "tags": ["vocals", "pop"]}))
        self.assertFalse(tem_voz({"titulo": "Calm piano", "tags": ["instrumental", "no vocals"]}))
        self.assertFalse(tem_voz({"titulo": "Morning ambient loop"}))
        nota, detalhe = pontuar({"titulo": "Happy song with lyrics"}, {"energia": 0.7, "bpm": 120, "duracao_s": 60},
                                "alegre", 30)
        self.assertEqual((nota, detalhe), (0, {"eliminatorio": "parece ter voz"}))

    def test_energia_e_ritmo_do_clima_pesam(self):
        cand = {"titulo": "happy upbeat instrumental", "duracao": 60}
        certa, _ = pontuar(cand, {"energia": 0.7, "bpm": 120, "duracao_s": 60}, "alegre", 30)
        errada, _ = pontuar(cand, {"energia": 0.1, "bpm": 65, "duracao_s": 60}, "alegre", 30)
        self.assertGreater(certa, errada)
        self.assertLessEqual(certa, 100)


class Midia(Provedor):
    tipo = "midia"

    def __init__(self, candidatos):
        super().__init__("openverse_midia", {"cache": False})
        self.candidatos, self.pedidos = candidatos, []

    def configurado(self):
        return None

    def executar(self, consulta, tipo="audio", max_resultados=5, proporcao=None, categoria=None):
        self.pedidos.append({"consulta": consulta, "categoria": categoria})
        return self.candidatos


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestComFFmpeg(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)

    def tearDown(self):
        self._d.cleanup()

    def test_mede_o_ritmo(self):
        for bpm in (80, 120):
            m = medir_ritmo(_musica(self.d / f"m{bpm}.mp3", bpm))
            self.assertAlmostEqual(m["bpm"], bpm, delta=2)
            self.assertTrue(0 <= m["energia"] <= 1)

    def test_escolhe_instrumental_guarda_com_credito_e_depois_usa_o_acervo(self):
        arquivos = {"https://x.storage.jamendo.com/a": _musica(self.d / "a.mp3", 120),
                    "https://x.storage.jamendo.com/b": _musica(self.d / "b.mp3", 70)}
        candidatos = [
            {"url": "https://x.storage.jamendo.com/v", "licenca": "cc-by", "autor": "Cantor", "titulo": "Sunny song",
             "tags": ["vocals"], "fonte": "Openverse (jamendo)"},
            {"url": "https://x.storage.jamendo.com/b", "licenca": "cc-by", "autor": "Bia", "titulo": "Slow piano",
             "tags": ["instrumental"], "fonte": "Openverse (jamendo)", "duracao": 60},
            {"url": "https://x.storage.jamendo.com/a", "licenca": "cc-by", "autor": "Ana",
             "titulo": "Happy upbeat instrumental", "tags": ["instrumental"], "fonte": "Openverse (jamendo)",
             "duracao": 60},
        ]
        midia = Midia(candidatos)
        rt = Roteador({"openverse_midia": midia}, {"midia_trilha": ["openverse_midia"]}, dormir=lambda s: None)
        roteiro = {"cenas": [{"clima": "alegre"}, {"clima": "alegre"}, {"clima": "calmo"}]}
        with Banco(self.d / "b.db") as banco:
            bib = Biblioteca(self.d / "bib", banco)
            t = escolher_trilha(rt, bib, roteiro, 30, baixar_arquivo=lambda url: arquivos[url].read_bytes())
            self.assertEqual(t["clima"], "alegre")
            self.assertEqual(t["ativo"]["autor"], "Ana")  # energia e ritmo de alegre; a com voz nem foi baixada
            self.assertAlmostEqual(t["bpm"], 120, delta=2)
            self.assertEqual(midia.pedidos[0]["categoria"], "music")
            self.assertIn("Ana", bib.creditos([t["ativo"]]))
            t2 = escolher_trilha(rt, bib, roteiro, 30, baixar_arquivo=lambda url: self.fail("não deveria baixar"))
            self.assertEqual(t2["detalhe"], {"camada": "acervo"})
            self.assertEqual(len(midia.pedidos), 1)

    def test_so_musica_com_voz_nao_serve(self):
        midia = Midia([{"url": "https://x.storage.jamendo.com/v", "licenca": "cc-by", "autor": "C",
                        "titulo": "Love song", "fonte": "Openverse"}])
        rt = Roteador({"openverse_midia": midia}, {"midia_trilha": ["openverse_midia"]}, dormir=lambda s: None)
        with Banco(self.d / "b.db") as banco, self.assertRaises(SemTrilha):
            escolher_trilha(rt, Biblioteca(self.d / "bib", banco), {"cenas": [{"clima": "calmo"}]}, 30,
                            baixar_arquivo=lambda url: b"")


if __name__ == "__main__":
    unittest.main()

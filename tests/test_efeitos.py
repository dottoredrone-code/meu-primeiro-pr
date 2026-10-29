import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from torralles_studio.banco import Banco
from torralles_studio.biblioteca import Biblioteca
from torralles_studio.efeitos import escolher_efeitos, etiquetas_do_nome, importar_pasta


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _som(pasta, nome, dur=0.5, freq=900):
    arq = Path(pasta) / nome
    _ff("-f", "lavfi", "-i", f"sine=f={freq}:d={dur}", "-ar", "44100", str(arq))
    return arq


class TestNomes(unittest.TestCase):
    def test_etiquetas_pelo_nome(self):
        self.assertEqual(etiquetas_do_nome("whoosh-short.mp3"),
                         ["efeito", "som-whoosh-short", "whoosh-short", "whoosh", "short"])
        self.assertEqual(etiquetas_do_nome("Impact Bass 1.wav"),
                         ["efeito", "som-impact-bass-1", "impact-bass-1", "impact", "bass"])


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestAcervo(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)
        self.banco = Banco(self.d / "b.db").__enter__()
        self.bib = Biblioteca(self.d / "bib", self.banco)
        self.sons = self.d / "sons"
        self.sons.mkdir()

    def tearDown(self):
        self.banco.__exit__(None, None, None)
        self._d.cleanup()

    def test_importa_com_licenca_e_ignora_o_que_nao_e_audio(self):
        _som(self.sons, "whoosh.mp3")
        _som(self.sons, "pop.mp3", 0.3)
        (self.sons / "CREDITS.md").write_text("créditos", encoding="utf-8")
        importados, problemas = importar_pasta(self.bib, self.sons, "Pixabay Content License", "Pixabay",
                                               link="https://pixabay.com/service/license-summary/")
        self.assertEqual((len(importados), problemas), (2, []))
        self.assertEqual({a["licenca"] for a in importados}, {"pixabay"})
        de_novo, _ = importar_pasta(self.bib, self.sons, "pixabay", "Pixabay")
        self.assertTrue(all(a["duplicado"] for a in de_novo))  # sem duplicatas

    def test_licenca_nao_comercial_nao_entra(self):  # D2
        _som(self.sons, "whoosh.mp3")
        importados, problemas = importar_pasta(self.bib, self.sons, "CC BY-NC 4.0", "Freesound")
        self.assertEqual(importados, [])
        self.assertIn("não permite uso comercial", problemas[0])

    def test_escolhe_pelo_nome_exato_e_pelo_clima(self):
        for nome, dur in [("whoosh.mp3", 0.5), ("whoosh-short.mp3", 0.4), ("whoosh-cinematic.mp3", 4.0),
                          ("pop.mp3", 0.3)]:
            _som(self.sons, nome, dur)
        importar_pasta(self.bib, self.sons, "pixabay", "Pixabay")
        from torralles_studio.montagem import duracao

        e = escolher_efeitos(self.bib, ["curioso", "alegre", "tenso", "tenso", "epico"], duracao_de=duracao)
        self.assertIsNone(e[0])  # não há corte antes da 1ª cena
        self.assertEqual(e[1]["nome"], "pop")
        self.assertEqual(e[2]["nome"], "whoosh")  # "tenso" sem impacto no acervo: cai no padrão
        self.assertEqual(e[3]["nome"], "whoosh-short")  # alterna para não repetir o mesmo som
        self.assertEqual(e[4]["nome"], "whoosh")  # o cinematic (4 s) é longo demais para um corte
        self.assertTrue(Path(e[1]["arquivo"]).name.endswith(".mp3"))
        self.assertEqual(e[1]["ativo"]["titulo"], "pop")

    def test_mesmo_arquivo_com_dois_nomes_e_achado_pelos_dois(self):  # verificador: Pixabay repete o whoosh
        som = _som(self.sons, "whoosh-short.mp3", 0.4)
        shutil.copyfile(som, self.sons / "whoosh.mp3")
        importar_pasta(self.bib, self.sons, "pixabay", "Pixabay")
        e = escolher_efeitos(self.bib, [None, None, None])
        self.assertEqual([x["nome"] for x in e[1:]], ["whoosh", "whoosh-short"])

    def test_acervo_vazio_nao_escolhe_nada(self):
        self.assertEqual(escolher_efeitos(self.bib, ["alegre", "tenso"]), [None, None])


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestMontagemComEfeitos(unittest.TestCase):
    def test_efeito_no_corte_15_lu_abaixo_da_voz(self):
        from torralles_studio.montagem import ErroMontagem, montar, verificar_montagem

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            clipe = d / "a.mp4"
            _ff("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:d=3", "-pix_fmt", "yuv420p", str(clipe))
            voz = d / "v.wav"
            _ff("-f", "lavfi", "-i", "sine=f=300:d=1.6", "-af", "adelay=300,apad=pad_dur=0.4,volume=-8dB",
                "-ar", "48000", str(voz))
            alto = _som(d, "whoosh.mp3", 0.5, 2000)  # som bem alto: a montagem precisa abaixar
            cenas = [{"video": clipe, "voz": voz, "narracao": "Primeira cena curta."},
                     {"video": clipe, "voz": voz, "narracao": "Segunda cena curta.", "efeito": alto}]
            r = montar(cenas, d / "final.mp4", proporcao="9:16", cfg={"preset": "ultrafast"},
                       pasta_trabalho=d / "trabalho")
            self.assertEqual(r["efeitos"]["quantidade"], 1)
            self.assertTrue(14 <= r["efeitos"]["voz_menos_efeitos_lu"] <= 16.5, r["efeitos"])
            v = verificar_montagem(r)
            self.assertEqual(v["problemas"], [])
            self.assertGreaterEqual(v["medidas"]["voz_menos_efeitos_lu"], 14)
            alto_demais = verificar_montagem(dict(r, efeitos=dict(r["efeitos"], voz_menos_efeitos_lu=8.0)))
            self.assertIn("efeitos sonoros só 8.0 LU abaixo da voz (mín. 14)", alto_demais["problemas"])
            # sem efeito, a montagem seguinte na mesma pasta não reaproveita o som antigo
            r2 = montar([dict(c, efeito=None) for c in cenas], d / "final2.mp4", proporcao="9:16",
                        cfg={"preset": "ultrafast"}, pasta_trabalho=d / "trabalho")
            self.assertIsNone(r2["efeitos"])
            self.assertFalse((d / "trabalho" / "efeitos.wav").exists())
            with self.assertRaises(ErroMontagem):
                montar([cenas[0], dict(cenas[1], efeito=d / "sumiu.mp3")], d / "x.mp4", cfg={"preset": "ultrafast"})


if __name__ == "__main__":
    unittest.main()

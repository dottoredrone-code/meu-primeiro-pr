"""K41: legenda karaokê no tempo real de cada palavra (Whisper), alinhada ao texto do roteiro."""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio import producao
from torralles_studio.montagem import _karaoke, alinhar_palavras, checar_legendas, gerar_ass, retemporizar_legendas

FALA = [("O", 0.0, 0.26), ("que", 0.26, 0.38), ("uma", 0.38, 0.52), ("xícara", 0.52, 1.0), ("de", 1.0, 1.16),
        ("chá", 1.16, 1.4), ("verde", 1.4, 1.8)]


def ks(texto):
    return [int(x) for x in re.findall(r"\\k(\d+)", texto)]


class TestAlinhamento(unittest.TestCase):
    def test_casa_palavras_mesmo_com_pontuacao_e_acento(self):
        tempos = alinhar_palavras("O que uma xícara de chá verde?", FALA)
        self.assertEqual(tempos[3], (0.52, 1.0))
        self.assertEqual(tempos[-1], (1.4, 1.8))

    def test_palavra_falada_diferente_ganha_tempo_entre_as_vizinhas(self):
        fala = [("Bebi", 0.0, 0.3), ("trinta", 0.3, 0.8), ("xícaras", 0.8, 1.4), ("hoje", 1.4, 1.8)]
        tempos = alinhar_palavras("Bebi 30 xícaras hoje", fala)
        self.assertEqual(tempos[0], (0.0, 0.3))
        a, b = tempos[1]  # "30" não casa com "trinta": fica entre "Bebi" e "xícaras"
        self.assertAlmostEqual(a, 0.3)
        self.assertAlmostEqual(b, 0.8)
        self.assertEqual(tempos[2], (0.8, 1.4))

    def test_fala_que_nao_bate_volta_para_a_estimativa(self):
        self.assertIsNone(alinhar_palavras("Texto totalmente diferente aqui", FALA))
        self.assertIsNone(alinhar_palavras("O que", []))


class TestKaraoke(unittest.TestCase):
    def test_cada_palavra_acende_quando_e_dita(self):
        tempos = [(10.0 + a, 10.0 + b) for _, a, b in FALA[:3]]
        texto = _karaoke(["O que uma"], 2.0, tempos, inicio=10.0)
        self.assertEqual(ks(texto), [26, 12, 14])  # 0,26 s; 0,12 s; até o fim de "uma"

    def test_atraso_no_comeco_vira_silaba_vazia(self):
        tempos = [(10.5, 10.8), (10.8, 11.0)]
        texto = _karaoke(["O que"], 2.0, tempos, inicio=10.0)
        self.assertTrue(texto.startswith("{\\k50}"))
        self.assertEqual(ks(texto), [50, 30, 20])

    def test_sem_tempos_ou_contagem_errada_usa_a_estimativa(self):
        estimado = _karaoke(["O que uma"], 2.0)
        self.assertEqual(_karaoke(["O que uma"], 2.0, [(0, 1)], 0.0), estimado)
        self.assertEqual(sum(ks(estimado)), 170)  # 85% do bloco

    def test_gerar_ass_usa_os_tempos_de_cada_legenda(self):
        legendas = [(10.0, 12.0, ["O que uma"]), (12.0, 13.0, ["xícara"])]
        tempos = [[(10.0, 10.26), (10.26, 10.38), (10.38, 10.52)], None]
        ass = gerar_ass(legendas, [], 1080, 1920, "9:16", karaoke=True, tempos_palavras=tempos)
        linhas = [l for l in ass.splitlines() if l.startswith("Dialogue: 0")]
        self.assertEqual(ks(linhas[0]), [26, 12, 14])
        self.assertEqual(ks(linhas[1]), [85])  # a 2ª ficou na estimativa


class TestPalavrasDaVoz(unittest.TestCase):
    def test_transcreve_uma_vez_e_guarda_ao_lado_da_voz(self):
        with tempfile.TemporaryDirectory() as pasta:
            voz = Path(pasta) / "voz_01.mp3"
            voz.write_bytes(b"x")
            chamadas = []

            def whisper(arquivo, palavras=False):
                chamadas.append(palavras)
                return [{"inicio": 0, "fim": 1, "texto": "O que", "palavras": [("O", 0.0, 0.2), ("que", 0.2, 0.4)]}]

            with mock.patch("torralles_studio.percepcao.whisper_disponivel", return_value=True), \
                    mock.patch("torralles_studio.percepcao.transcrever_whisper", whisper):
                primeira = producao.palavras_da_voz(voz)
                segunda = producao.palavras_da_voz(voz)  # retomada: vem do arquivo
            self.assertEqual(primeira, [("O", 0.0, 0.2), ("que", 0.2, 0.4)])
            self.assertEqual(segunda, primeira)
            self.assertEqual(chamadas, [True])
            self.assertTrue(json.loads((Path(pasta) / "voz_01.palavras.json").read_text(encoding="utf-8")))

    def test_sem_whisper_fica_a_estimativa(self):
        with tempfile.TemporaryDirectory() as pasta, \
                mock.patch("torralles_studio.percepcao.whisper_disponivel", return_value=False):
            voz = Path(pasta) / "voz_01.mp3"
            voz.write_bytes(b"x")
            self.assertIsNone(producao.palavras_da_voz(voz))


class TestBlocosNoTempoReal(unittest.TestCase):
    def test_bloco_comeca_na_primeira_palavra_e_continua_legivel(self):
        blocos = [(10.0, 11.5, ["O que uma xícara"]), (11.5, 13.0, ["de chá verde"])]
        tempos = [[(10.3, 10.5), (10.5, 10.6), (10.6, 10.8), (10.8, 11.3)], [(11.8, 12.0), (12.0, 12.3), (12.3, 12.7)]]
        novos = retemporizar_legendas(blocos, tempos, fim_cena=14.0)
        self.assertEqual(novos[0][0], 10.3)
        self.assertEqual(novos[1][0], 11.8)
        self.assertLessEqual(novos[0][1], novos[1][0])  # nunca invade o seguinte
        self.assertEqual(checar_legendas(novos), [])

    def test_bloco_sem_tempo_fica_como_estava(self):
        blocos = [(10.0, 11.5, ["texto"])]
        self.assertEqual(retemporizar_legendas(blocos, [None]), [(10.0, 11.5, ["texto"])])


class TestCacheDasPalavras(unittest.TestCase):
    def _rodar(self, pasta, conteudo, voz_mais_nova=False):
        import os
        import time

        voz = Path(pasta) / "voz_01.mp3"
        voz.write_bytes(b"x")
        guardado = Path(pasta) / "voz_01.palavras.json"
        guardado.write_text(conteudo, encoding="utf-8")
        if voz_mais_nova:
            agora = time.time()
            os.utime(guardado, (agora - 60, agora - 60))
        chamadas = []

        def whisper(arquivo, palavras=False):
            chamadas.append(1)
            return [{"inicio": 0, "fim": 1, "texto": "oi", "palavras": [("oi", 0.0, 0.3)]}]

        with mock.patch("torralles_studio.percepcao.whisper_disponivel", return_value=True),                 mock.patch("torralles_studio.percepcao.transcrever_whisper", whisper):
            return producao.palavras_da_voz(voz), chamadas

    def test_voz_refeita_transcreve_de_novo(self):
        with tempfile.TemporaryDirectory() as pasta:
            palavras, chamadas = self._rodar(pasta, '[["velha", 0, 1]]', voz_mais_nova=True)
            self.assertEqual((palavras, len(chamadas)), ([("oi", 0.0, 0.3)], 1))

    def test_arquivo_estragado_e_ignorado(self):
        with tempfile.TemporaryDirectory() as pasta:
            palavras, chamadas = self._rodar(pasta, '[["so dois campos", 1]]')
            self.assertEqual((palavras, len(chamadas)), ([("oi", 0.0, 0.3)], 1))


@unittest.skipUnless(__import__("shutil").which("ffmpeg"), "FFmpeg não instalado")
class TestMontagemComPalavras(unittest.TestCase):
    def test_montar_usa_o_tempo_real_na_legenda(self):
        import subprocess

        from torralles_studio.montagem import montar

        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            img, voz = pasta / "c.png", pasta / "v.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=270x480", "-frames:v", "1",
                            str(img)], check=True)
            # 0,5 s de silêncio + 2 s de "fala" (tom) + 0,5 s de silêncio
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
                            "-af", "adelay=500,apad=pad_dur=0.5", str(voz)], check=True)
            palavras = [["Chá", 0.5, 0.9], ["verde", 0.9, 1.4], ["faz", 1.4, 1.8], ["bem.", 1.8, 2.4]]
            r = montar([{"video": str(img), "voz": str(voz), "narracao": "Chá verde faz bem.", "palavras": palavras}],
                       pasta / "final.mp4", cfg={"preset": "ultrafast", "fps": 15}, pasta_trabalho=pasta / "m")
            self.assertEqual(r["legendas_tempo_real"], 1)
            ass = (pasta / "m" / "legendas.ass").read_text(encoding="utf-8")
            linha = next(l for l in ass.splitlines() if l.startswith("Dialogue: 0"))
            # bloco começa na 1ª palavra (sem atraso): "Chá", "verde", "faz", "bem." no tempo falado
            self.assertEqual(ks(linha), [40, 50, 40, 60])


if __name__ == "__main__":
    unittest.main()

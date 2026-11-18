"""Capa com título e texto para postar (melhoria tirada dos concorrentes)."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from torralles_studio.publicacao import (_validar_texto, escrever_post, gerar_capa, gerar_texto, hashtag,
                                         texto_por_regra)
from torralles_studio.roteador import Resultado

ROTEIRO = {"titulo": "Chá verde: benefícios com equilíbrio", "cta": "Siga para mais.",
           "cenas": [{"narracao": "O que uma xícara de chá verde faz pelo corpo?"}, {"narracao": "Tem cafeína."}]}


class RoteadorFalso:
    cadeias = {"roteiro": ["x"]}

    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro, self.prompts = resposta, erro, []

    def executar(self, tarefa, prompt, sistema=None, validar=None):
        self.prompts.append(prompt)
        if self.erro:
            raise self.erro
        return Resultado(validar(self.resposta), "falso")


class TestTexto(unittest.TestCase):
    def test_hashtag_sem_acento_e_curta_fora(self):
        self.assertEqual(hashtag("Equilíbrio"), "#equilibrio")
        self.assertIsNone(hashtag("de"))

    def test_regra_sem_ia(self):
        dados = texto_por_regra(ROTEIRO, "chá verde")
        self.assertEqual(dados["titulo"], ROTEIRO["titulo"])
        self.assertIn("Siga para mais.", dados["descricao"])
        self.assertIn("#verde", dados["hashtags"])
        self.assertEqual(dados["origem"], "regra")

    def test_ia_valida_e_limita(self):
        resposta = json.dumps({"titulo": "T" * 200, "descricao": "D", "hashtags": ["#Chá Verde", "fyp", "a"]})
        rt = RoteadorFalso(resposta)
        dados = gerar_texto(rt, ROTEIRO, "chá verde", creditos="Foto: Fulano (CC BY)")
        self.assertEqual(len(dados["titulo"]), 70)
        self.assertEqual(dados["hashtags"], ["#chaverde"])  # genéricas (#fyp) saem
        self.assertEqual(dados["creditos"], "Foto: Fulano (CC BY)")
        self.assertIn("xícara de chá verde", rt.prompts[0])  # só fatos da narração

    def test_ia_fora_cai_na_regra(self):
        dados = gerar_texto(RoteadorFalso(erro=RuntimeError("todas falharam")), ROTEIRO, "chá verde")
        self.assertEqual(dados["origem"], "regra")

    def test_resposta_sem_titulo_recusada(self):
        with self.assertRaises(ValueError):
            _validar_texto('{"descricao": "x"}')

    def test_post_txt_pronto_para_colar(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = escrever_post({**texto_por_regra(ROTEIRO, "chá verde"), "creditos": "Música: X (CC BY)"}, pasta)
            texto = destino.read_text(encoding="utf-8")
            self.assertTrue(texto.startswith("Chá verde"))
            self.assertIn("Créditos:\nMúsica: X (CC BY)", texto)
            self.assertTrue((Path(pasta) / "post.json").is_file())


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestCapa(unittest.TestCase):
    def test_capa_no_tamanho_do_formato_com_acento_no_caminho(self):
        with tempfile.TemporaryDirectory() as raiz:
            pasta = Path(raiz) / "Área de Trabalho"
            pasta.mkdir()
            imagem = pasta / "cena.png"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=640x480", "-frames:v", "1",
                            str(imagem)], check=True)
            capa = gerar_capa(imagem, "Chá verde: {benefícios} \\ equilíbrio", pasta / "capa.jpg",
                              largura=540, altura=960)
            sonda = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                                    str(capa)], capture_output=True, text=True, check=True)
            self.assertEqual(sonda.stdout.strip(), "540,960")
            self.assertFalse((pasta / "capa.ass").exists())


if __name__ == "__main__":
    unittest.main()

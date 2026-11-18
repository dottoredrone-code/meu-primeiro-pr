"""K37 (spec 14 §E): pedidos para sites no navegador e importação segura."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio.banco import Banco
from torralles_studio.biblioteca import Biblioteca
from torralles_studio.navegador import ErroNavegador, Navegador, _Site, fila_de_sites, tipo_pelos_bytes

TEM_FFMPEG = shutil.which("ffmpeg") is not None
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

SITES = {
    "site_ok": _Site("site_ok", {"modalidades": ["imagem", "animar"], "licenca": "comercial", "molde": "flux",
                                 "endereco": "https://exemplo.test", "nome": "Site OK",
                                 "cota": {"limite": 10, "renova": "00:00 UTC"}}),
    "site_nc": _Site("site_nc", {"modalidades": ["imagem"], "licenca": "nao_comercial"}),
    "site_marca": _Site("site_marca", {"modalidades": ["imagem"], "licenca": "comercial", "marca_dagua": True}),
    "site_novo": _Site("site_novo", {"modalidades": ["imagem"], "licenca": "a_conferir"}),
}
CENA = {"indice": 1, "prompt_imagem": "A cup of green tea on a wooden table", "clima": "calmo",
        "prompt_movimento": "slow zoom in"}


class TestFila(unittest.TestCase):
    def test_so_entra_site_com_licenca_conferida_comercial_e_sem_marca(self):
        fila = dict(fila_de_sites(SITES, "imagem"))
        self.assertIsNone(fila["site_ok"])
        for fora in ("site_nc", "site_marca", "site_novo"):
            self.assertIsNotNone(fila[fora], fora)
        fila = dict(fila_de_sites(SITES, "imagem", comercial=False, regras={"imagem": "como_freesound"}))
        self.assertIsNone(fila["site_nc"])
        self.assertIsNotNone(fila["site_novo"])

    def test_tipo_pelos_bytes(self):
        self.assertEqual(tipo_pelos_bytes(PNG[:16]), "imagem")
        self.assertEqual(tipo_pelos_bytes(b"\x00\x00\x00\x18ftypmp42"), "video")
        self.assertIsNone(tipo_pelos_bytes(b"MZ\x90\x00 executavel"))


class TestPedidosEImportacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.raiz = Path(self.tmp.name)
        self.tema = self.raiz / "saidas" / "cha"
        self.banco = Banco(self.raiz / "t.db")
        self.nav = Navegador(self.banco, SITES, tamanho_maximo_mb=1)

    def tearDown(self):
        self.banco.fechar()
        self.tmp.cleanup()

    def test_cria_pedido_com_prompt_por_site_e_refazer_leva_correcao(self):
        dados = self.nav.criar_pedidos(self.tema, [CENA], "imagem")
        pedido = dados["pedidos"][0]
        self.assertEqual(pedido["id"], "c01-imagem")
        self.assertEqual(list(pedido["prompts"]), ["site_ok"])
        self.assertTrue((self.tema / "navegador" / "pedidos.json").is_file())
        self.nav.marcar(self.tema, "c01-imagem", "refazer")
        dados = self.nav.criar_pedidos(self.tema, [CENA], "imagem", feedback={1: "show the steam clearly"})
        self.assertIn("show the steam clearly", dados["pedidos"][0]["prompts"]["site_ok"]["prompt"])
        self.assertEqual(self.nav.pedido("c01-imagem", self.tema)["tentativas"], 2)

    def test_correcao_do_juiz_nao_reprova_o_prompt(self):
        self.nav.criar_pedidos(self.tema, [CENA], "imagem")
        self.nav.marcar(self.tema, "c01-imagem", "refazer")
        dados = self.nav.criar_pedidos(self.tema, [CENA], "imagem", feedback={1: "remove the caption text"})
        self.assertIn("remove the caption text", dados["pedidos"][0]["prompts"]["site_ok"]["prompt"])

    def test_rodar_de_novo_nao_reabre_importado_e_nao_mistura_temas(self):
        self.nav.criar_pedidos(self.tema, [CENA], "imagem")
        self.nav.marcar(self.tema, "c01-imagem", "importado")
        dados = self.nav.criar_pedidos(self.tema, [CENA], "imagem")
        self.assertEqual(dados["pedidos"][0]["estado"], "importado")
        self.assertEqual(self.nav.pedido("c01-imagem", self.tema)["estado"], "importado")
        outro = self.raiz / "saidas" / "outro"
        self.nav.criar_pedidos(outro, [CENA], "imagem")
        self.assertEqual(self.nav.pedido("c01-imagem", outro)["tentativas"], 1)

    def test_estado_sobrevive_entre_execucoes(self):
        self.nav.criar_pedidos(self.tema, [CENA], "imagem")
        self.banco.fechar()
        self.banco = Banco(self.raiz / "t.db")
        self.assertEqual(Navegador(self.banco, SITES).pedido("c01-imagem", self.tema)["estado"], "pendente")

    def test_recusa_tipo_falso_grande_demais_sem_pedido_e_atalho(self):
        self.nav.criar_pedidos(self.tema, [CENA], "imagem")
        pasta = self.tema / "navegador"
        (pasta / "c01-imagem.png").write_bytes(b"MZ isto e um executavel")
        (pasta / "c99-imagem.png").write_bytes(PNG)
        (pasta / "c01-imagem.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024))
        importados, problemas = self.nav.importar(self.tema)
        self.assertEqual(importados, [])
        texto = "\n".join(problemas)
        self.assertIn("não é a imagem", texto)
        self.assertIn("nenhum pedido", texto)
        self.assertIn("tamanho fora do limite", texto)
        fora = self.raiz / "fora.png"
        fora.write_bytes(PNG)
        try:
            os.symlink(fora, pasta / "c01-imagem.webp")
        except (OSError, NotImplementedError):
            return  # Windows sem permissão de atalho: o caso não existe aqui
        _, problemas = self.nav.importar(self.tema)
        self.assertTrue(any("atalho" in p for p in problemas))

    def test_site_fora_do_pedido_recusado(self):
        self.nav.criar_pedidos(self.tema, [CENA], "imagem")
        (self.tema / "navegador" / "c01-imagem.png").write_bytes(PNG)
        with mock.patch("torralles_studio.navegador._sondar", return_value={"width": 8, "height": 8}):
            _, problemas = self.nav.importar(self.tema, site="site_nc")
        self.assertIn("não foi feito para", problemas[0])

    @unittest.skipUnless(TEM_FFMPEG, "FFmpeg não instalado")
    def test_importa_imagem_real_com_licenca_do_config(self):
        self.nav.criar_pedidos(self.tema, [CENA], "imagem")
        destino = self.tema / "navegador" / "c01-imagem.png"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=64x64", "-frames:v", "1",
                        str(destino)], check=True)
        bib = Biblioteca(self.raiz / "bib", self.banco)
        importados, problemas = self.nav.importar(self.tema, bib)
        self.assertEqual(problemas, [])
        self.assertEqual(importados[0]["site"], "site_ok")
        ativo = bib.obter(importados[0]["ativo"])
        self.assertEqual(ativo["licenca"], "gerado_ia")
        self.assertEqual(ativo["fonte"], "Site OK")
        pedido = self.nav.pedido("c01-imagem", self.tema)
        self.assertEqual((pedido["estado"], pedido["licenca"]), ("importado", "comercial"))
        self.assertTrue(pedido["prompt"])
        _, problemas = self.nav.importar(self.tema)  # de novo: já importado
        self.assertTrue(any("importado" in p for p in problemas))

    def test_pedido_de_video_nao_aceita_imagem(self):
        self.nav.criar_pedidos(self.tema, [CENA], "animar")
        (self.tema / "navegador" / "c01-animar.png").write_bytes(PNG)
        _, problemas = self.nav.importar(self.tema)
        self.assertIn("é de video", problemas[0])

    def test_modalidade_invalida(self):
        with self.assertRaises(ErroNavegador):
            self.nav.criar_pedidos(self.tema, [CENA], "musica")


if __name__ == "__main__":
    unittest.main()

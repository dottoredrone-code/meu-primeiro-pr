"""K36: Cloudflare Workers AI (FLUX schnell grátis) e regras de licença que o perfil não pode afrouxar."""

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio.config import CONFIG_PADRAO, carregar_roteador
from torralles_studio.perfis import ErroPerfil, _validar
from torralles_studio.provedores.imagem import CloudflareImagem
from torralles_studio.rede import ErroProvedor

CFG = {"classe": "cloudflare_imagem", "modelo": "@cf/black-forest-labs/flux-1-schnell",
       "chave_env": "CF_TESTE_TOKEN", "conta_env": "CF_TESTE_CONTA", "passos": 4}


class TestCloudflare(unittest.TestCase):
    def test_pede_conta_e_token(self):
        with mock.patch.dict(os.environ, {"CF_TESTE_TOKEN": "x"}, clear=False):
            os.environ.pop("CF_TESTE_CONTA", None)
            self.assertEqual(CloudflareImagem("cf", CFG).configurado(), "falta CF_TESTE_CONTA")

    def test_grava_a_imagem_do_base64_sem_download(self):
        enviado = {}

        def falso_post(url, corpo, cab, timeout):
            enviado.update(url=url, corpo=corpo, cab=cab)
            return {"success": True, "result": {"image": base64.b64encode(b"\xff\xd8\xffJPEG").decode()}}

        with tempfile.TemporaryDirectory() as pasta, \
                mock.patch.dict(os.environ, {"CF_TESTE_TOKEN": "tok", "CF_TESTE_CONTA": "conta1"}), \
                mock.patch("torralles_studio.provedores.imagem.post_json", falso_post):
            saida = CloudflareImagem("cf", CFG).executar("a cup of tea", Path(pasta) / "a.jpg")
            self.assertEqual(saida.read_bytes(), b"\xff\xd8\xffJPEG")
        self.assertIn("/accounts/conta1/ai/run/@cf/black-forest-labs/flux-1-schnell", enviado["url"])
        self.assertEqual(enviado["corpo"], {"prompt": "a cup of tea", "steps": 4})
        self.assertEqual(enviado["cab"]["Authorization"], "Bearer tok")

    def test_sem_imagem_vira_erro_do_provedor(self):
        with tempfile.TemporaryDirectory() as pasta, \
                mock.patch.dict(os.environ, {"CF_TESTE_TOKEN": "t", "CF_TESTE_CONTA": "c"}), \
                mock.patch("torralles_studio.provedores.imagem.post_json",
                           return_value={"success": False, "errors": [{"message": "daily free allocation exceeded"}]}):
            with self.assertRaises(ErroProvedor) as erro:
                CloudflareImagem("cf", CFG).executar("x", Path(pasta) / "a.jpg")
        self.assertIn("daily free allocation", str(erro.exception))

    def test_config_padrao_tem_cloudflare_comercial_com_cota_e_sites_validos(self):
        rt = carregar_roteador(CONFIG_PADRAO)
        self.assertIn("cloudflare_flux", rt.cadeias["imagem"])
        cf = rt.provedores["cloudflare_flux"].cfg
        self.assertEqual((cf["licenca"], cf["cota"]["renova"]), ("comercial", "00:00 UTC"))


class TestPerfilNaoAfrouxaLicenca(unittest.TestCase):
    def test_perfil_nao_muda_licenca_nem_cota(self):
        with tempfile.TemporaryDirectory() as pasta:
            for campo, valor in (("somente_nao_comercial", False), ("licenca", "comercial"), ("marca_dagua", False),
                                 ("cota", {"limite": 999})):
                dados = {"id": "canal", "nome": "C", "provedores": {"freesound_midia": {campo: valor}}}
                with self.assertRaises(ErroPerfil, msg=campo):
                    _validar(dados, Path(pasta) / "canal.toml", Path(pasta), None)


if __name__ == "__main__":
    unittest.main()

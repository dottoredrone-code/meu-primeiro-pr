import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio.banco import Banco
from torralles_studio.biblioteca import Biblioteca
from torralles_studio.midia import SemMidia, buscar_midia, candidatos_aceitos, etiquetas_da_consulta
from torralles_studio.provedores.base import Provedor
from torralles_studio.provedores.midia import FreesoundMidia, OpenverseMidia, PexelsMidia, PixabayMidia
from torralles_studio.rede import ErroProvedor, dominio_permitido
from torralles_studio.roteador import Roteador


def candidato(licenca, url="https://images.pexels.com/a.jpg", autor="Ana", **extra):
    return {"url": url, "licenca": licenca, "autor": autor, "link": "https://www.pexels.com/foto/1",
            "titulo": "xícara de chá", "fonte": "Teste", "tipo": "imagem", "tags": ["cha"], **extra}


class FonteFalsa(Provedor):
    tipo = "midia"

    def __init__(self, nome, respostas):
        super().__init__(nome, {})
        self.respostas = list(respostas)
        self.pedidos = []

    def configurado(self):
        return None

    def executar(self, consulta, tipo="imagem", max_resultados=5, proporcao=None):
        self.pedidos.append((consulta, tipo, proporcao))
        return self.respostas.pop(0)


class TestFiltroDeLicenca(unittest.TestCase):
    def test_bloqueadas_e_incompletas_sao_descartadas(self):
        lista = [candidato("CC BY-NC 4.0"), candidato("http://creativecommons.org/licenses/by-nd/4.0/"),
                 candidato("cc-by", autor=""), candidato("pexels", url="http://images.pexels.com/x.jpg"),
                 candidato("desconhecida"), candidato("Creative Commons 0"),
                 candidato("https://creativecommons.org/licenses/by/4.0/")]
        aceitos = candidatos_aceitos(lista)
        self.assertEqual([c["licenca"] for c in aceitos], ["cc0", "cc-by"])

    def test_etiquetas_da_consulta(self):
        self.assertEqual(etiquetas_da_consulta("Xícara de chá na mesa"), ["xicara", "cha", "mesa"])


class TestBuscarMidia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.banco = Banco(Path(self.tmp.name) / "t.db")
        self.bib = Biblioteca(Path(self.tmp.name) / "bib", self.banco)

    def tearDown(self):
        self.banco.fechar()
        self.tmp.cleanup()

    def roteador(self, *fontes, tipo="imagem"):
        return Roteador({f.nome: f for f in fontes}, {f"midia_{tipo}": [f.nome for f in fontes]})

    def test_baixa_guarda_com_licenca_e_gera_creditos(self):
        fonte = FonteFalsa("openverse_midia", [[candidato("cc-by-nc"), candidato("cc-by", autor="Bia")]])
        ativo = buscar_midia(self.roteador(fonte), self.bib, "xícara de chá", proporcao="9:16",
                             baixar_arquivo=lambda url: b"jpeg bytes")
        self.assertEqual((ativo["camada"], ativo["licenca"], ativo["autor"]), ("api", "cc-by", "Bia"))
        self.assertIn("xicara", ativo["tags"])
        self.assertEqual(self.bib.caminho(ativo).read_bytes(), b"jpeg bytes")
        self.assertIn("por Bia", self.bib.creditos([ativo]))
        self.assertEqual(fonte.pedidos[0], ("xícara de chá", "imagem", "9:16"))

    def test_acervo_local_vem_antes_e_nao_chama_api(self):
        arq = Path(self.tmp.name) / "local.jpg"
        arq.write_bytes(b"local")
        self.bib.adicionar(arq, "cc0", "acervo", tags=["xicara", "cha"])
        fonte = FonteFalsa("pexels_midia", [])
        ativo = buscar_midia(self.roteador(fonte), self.bib, "xícara de chá", baixar_arquivo=None)
        self.assertEqual(ativo["camada"], "acervo")
        self.assertEqual(fonte.pedidos, [])

    def test_fonte_so_com_licenca_bloqueada_passa_para_a_proxima(self):
        a = FonteFalsa("pexels_midia", [[candidato("uso pessoal")]])
        b = FonteFalsa("pixabay_midia", [[candidato("pixabay")]])
        ativo = buscar_midia(self.roteador(a, b), self.bib, "chá", baixar_arquivo=lambda url: b"x")
        self.assertEqual((ativo["licenca"], ativo["provedor"]), ("pixabay", "pixabay_midia"))

    def test_nada_aceito_lanca_sem_midia(self):
        fonte = FonteFalsa("pexels_midia", [[candidato("cc-by-nc-sa")]])
        with self.assertRaisesRegex(SemMidia, "licença aceita"):
            buscar_midia(self.roteador(fonte), self.bib, "chá", baixar_arquivo=lambda url: b"x")
        self.assertEqual(self.bib.buscar(["cha"]), [])

    def test_download_recusado_tenta_o_proximo_candidato(self):
        fonte = FonteFalsa("openverse_midia", [[candidato("cc0", url="https://site-qualquer.exemplo/a.jpg"),
                                                 candidato("cc0", url="https://upload.wikimedia.org/b.jpg")]])

        def baixar(url):
            if "site-qualquer" in url:
                raise ErroProvedor("download recusado: domínio não permitido")
            return b"ok"

        ativo = buscar_midia(self.roteador(fonte), self.bib, "chá", baixar_arquivo=baixar)
        self.assertEqual(self.bib.caminho(ativo).read_bytes(), b"ok")

    def test_link_invalido_da_fonte_pula_o_candidato(self):
        fonte = FonteFalsa("openverse_midia", [[candidato("cc0", link="javascript:x"), candidato("cc0", url="https://images.pexels.com/2.jpg")]])
        conteudos = iter([b"um", b"dois"])
        ativo = buscar_midia(self.roteador(fonte), self.bib, "chá", baixar_arquivo=lambda url: next(conteudos))
        self.assertEqual(self.bib.caminho(ativo).read_bytes(), b"dois")

    # Regressões da verificação independente (K20)
    def test_download_falhou_em_tudo_tenta_a_proxima_fonte(self):
        a = FonteFalsa("pixabay_midia", [[candidato("pixabay", url="https://pixabay.com/get/vencido.jpg")]])
        b = FonteFalsa("openverse_midia", [[candidato("cc0", url="https://upload.wikimedia.org/ok.jpg")]])

        def baixar(url):
            if "vencido" in url:
                raise ErroProvedor("HTTP 403 no download")
            return b"imagem"

        ativo = buscar_midia(self.roteador(a, b), self.bib, "chá", baixar_arquivo=baixar)
        self.assertEqual((ativo["provedor"], len(b.pedidos)), ("openverse_midia", 1))

    def test_pagina_html_e_extensao_estranha(self):
        fonte = FonteFalsa("openverse_midia", [[candidato("cc0", url="https://upload.wikimedia.org/a.jpg"),
                                                 candidato("cc0", url="https://upload.wikimedia.org/logo.svg"),
                                                 candidato("cc0", url="https://upload.wikimedia.org/c.jpg"),
                                                 candidato("cc0", url="https://upload.wikimedia.org/d")]])
        respostas = iter([b"\xef\xbb\xbf<html>erro</html>", b"<svg xmlns='x'/>", b"bytes da imagem"])
        baixados = []

        def baixar(url):
            baixados.append(url)
            return next(respostas)

        ativo = buscar_midia(self.roteador(fonte), self.bib, "chá", baixar_arquivo=baixar)
        self.assertEqual((ativo["tipo"], Path(ativo["caminho"]).suffix), ("imagem", ".jpg"))
        self.assertNotIn("https://upload.wikimedia.org/logo.svg", baixados)  # .svg nem é baixado
        self.assertEqual(self.bib.caminho(ativo).read_bytes(), b"bytes da imagem")  # SVG disfarçado também é recusado

    def test_fonte_so_nao_comercial_fica_fora_de_projeto_comercial(self):
        livre = FonteFalsa("freesound_midia", [[candidato("cc0", url="https://cdn.freesound.org/a.mp3")]] * 2)
        livre.cfg["somente_nao_comercial"] = True
        outra = FonteFalsa("openverse_midia", [[candidato("cc0", url="https://upload.wikimedia.org/b.mp3")]])
        rt = Roteador({"freesound_midia": livre, "openverse_midia": outra}, {"midia_audio": ["freesound_midia", "openverse_midia"]})
        a = buscar_midia(rt, self.bib, "passos", "audio", baixar_arquivo=lambda url: url.encode())
        self.assertEqual((a["provedor"], livre.pedidos), ("openverse_midia", []))  # padrão: comercial
        b = buscar_midia(rt, self.bib, "chuva", "audio", comercial=False, baixar_arquivo=lambda url: b"som")
        self.assertEqual(b["provedor"], "freesound_midia")

    def test_dominios_das_fontes_estao_liberados(self):
        from torralles_studio.config import carregar_config

        lista = carregar_config()["seguranca"]["dominios_download"]
        for url in ("https://images.pexels.com/p.jpg", "https://videos.pexels.com/v.mp4", "https://cdn.pixabay.com/x.jpg",
                    "https://cdn.freesound.org/previews/1.mp3"):
            self.assertTrue(dominio_permitido(url, lista), url)


class TestProvedores(unittest.TestCase):
    def chamar(self, provedor, resposta, **kw):
        with mock.patch("torralles_studio.provedores.midia.get_json", return_value=resposta) as get:
            return provedor.executar("chá", **kw), get.call_args[0][0]

    def test_pexels_imagem_e_video(self):
        p = PexelsMidia("pexels_midia", {"chave_env": "PEXELS_API_KEY"})
        r, url = self.chamar(p, {"photos": [{"src": {"large2x": "https://images.pexels.com/1.jpg"}, "photographer": "Ana",
                                             "url": "https://www.pexels.com/p/1", "width": 1, "height": 2}]},
                             proporcao="9:16")
        self.assertEqual((r[0]["licenca"], r[0]["autor"]), ("pexels", "Ana"))
        self.assertIn("orientation=portrait", url)
        r, _ = self.chamar(p, {"videos": [{"video_files": [{"link": "https://videos.pexels.com/a.mp4", "height": 720, "width": 405},
                                                           {"link": "https://videos.pexels.com/b.mp4", "height": 1920, "width": 1080}],
                                           "user": {"name": "Bia"}, "duration": 8}]}, tipo="video", proporcao="9:16")
        self.assertEqual(r[0]["url"], "https://videos.pexels.com/b.mp4")

    def test_pixabay_openverse_freesound(self):
        r, _ = self.chamar(PixabayMidia("p", {}), {"hits": [{"largeImageURL": "https://cdn.pixabay.com/1.jpg", "user": "u",
                                                             "pageURL": "https://pixabay.com/p", "tags": "chá, xícara"}]})
        self.assertEqual((r[0]["licenca"], r[0]["tags"]), ("pixabay", ["chá", "xícara"]))
        r, url = self.chamar(OpenverseMidia("o", {}), {"results": [
            {"url": "https://upload.wikimedia.org/a.jpg", "license": "by-sa", "creator": "c"},
            {"url": "https://upload.wikimedia.org/b.jpg", "license": "pdm", "creator": "d"}]})
        self.assertEqual([c["licenca"] for c in r], ["cc-by-sa", "cc0"])
        r, _ = self.chamar(OpenverseMidia("o", {}), {"results": [{"url": "https://upload.wikimedia.org/c.jpg", "license": None}]})
        self.assertIsNone(r[0]["licenca"])
        self.assertEqual(candidatos_aceitos(r), [])  # sem licença clara: bloqueado, nunca CC0
        self.assertIn("license_type=commercial%2Cmodification", url)
        r, _ = self.chamar(FreesoundMidia("f", {}), {"results": [
            {"name": "passos", "username": "u", "license": "http://creativecommons.org/publicdomain/zero/1.0/",
             "previews": {"preview-hq-mp3": "https://cdn.freesound.org/previews/1.mp3"}, "url": "https://freesound.org/s/1"},
            {"name": "sem prévia", "license": "x", "previews": {}}]}, tipo="audio")
        self.assertEqual(len(r), 1)
        self.assertEqual(candidatos_aceitos(r)[0]["licenca"], "cc0")

    def test_pixabay_video_sem_large_usa_medium(self):
        r, _ = self.chamar(PixabayMidia("p", {}), {"hits": [{"user": "u", "pageURL": "https://pixabay.com/v", "tags": "",
                                                             "videos": {"large": {"url": "", "size": 0},
                                                                        "medium": {"url": "https://cdn.pixabay.com/m.mp4", "width": 1920}}}]},
                           tipo="video")
        self.assertEqual(r[0]["url"], "https://cdn.pixabay.com/m.mp4")

    def test_pexels_ignora_hls_e_freesound_usa_cabecalho(self):
        p = PexelsMidia("p", {})
        r, _ = self.chamar(p, {"videos": [{"video_files": [{"link": "https://player.vimeo.com/x.m3u8", "file_type": "video/hls", "width": None},
                                                           {"link": "https://videos.pexels.com/a.mp4", "file_type": "video/mp4", "width": 1080, "height": 1920}],
                                           "user": {"name": "u"}}]}, tipo="video")
        self.assertEqual(r[0]["url"], "https://videos.pexels.com/a.mp4")
        f = FreesoundMidia("f", {"chave_env": "FREESOUND_API_KEY"})
        with mock.patch("torralles_studio.provedores.midia.get_json", return_value={"results": [
                {"previews": {"preview-hq-mp3": "https://cdn.freesound.org/1.mp3"}, "license": "x"}]}) as get, \
             mock.patch.dict("os.environ", {"FREESOUND_API_KEY": "segredo123456"}):
            f.executar("chá", tipo="audio")
        self.assertNotIn("segredo", get.call_args[0][0])
        self.assertEqual(get.call_args[0][1], {"Authorization": "Token segredo123456"})

    def test_texto_misto_de_licenca_nao_usa_o_link(self):
        from torralles_studio.biblioteca import normalizar_licenca
        self.assertEqual(normalizar_licenca("CC BY-NC see creativecommons.org/licenses/by/4.0/")[:8], "cc-by-nc")

    def test_tipo_nao_suportado_e_sem_resultados(self):
        with self.assertRaises(ErroProvedor):
            PexelsMidia("p", {}).executar("chá", tipo="audio")
        with self.assertRaisesRegex(ErroProvedor, "sem resultados"):
            self.chamar(PixabayMidia("p", {}), {"hits": []})


if __name__ == "__main__":
    unittest.main()

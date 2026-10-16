import io
import unittest
from unittest import mock

from torralles_studio import rede
from torralles_studio.rede import ErroProvedor, baixar, dominio_permitido


class RespostaFalsa(io.BytesIO):
    def __init__(self, dados, url, tamanho=None):
        super().__init__(dados)
        self._url = url
        self.headers = {"Content-Length": str(tamanho)} if tamanho is not None else {}

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestDownloads(unittest.TestCase):
    def test_dominios(self):
        self.assertTrue(dominio_permitido("https://v3.fal.media/files/a.mp4"))
        self.assertTrue(dominio_permitido("https://fal.media/a.png"))
        self.assertFalse(dominio_permitido("http://v3.fal.media/a.mp4"), "só HTTPS")
        self.assertFalse(dominio_permitido("https://fal.media.ataque.com/a.mp4"), "sufixo enganoso")
        self.assertFalse(dominio_permitido("https://evilfal.media/a.mp4"), "sem ponto antes do domínio")
        self.assertFalse(dominio_permitido("https://exemplo.com/a.mp4"))

    def test_recusa_dominio_fora_da_lista_sem_abrir_conexao(self):
        with mock.patch("urllib.request.urlopen") as abrir:
            with self.assertRaises(ErroProvedor):
                baixar("https://exemplo.com/a.mp4")
            abrir.assert_not_called()

    def test_recusa_redirecionamento_para_fora(self):
        resp = RespostaFalsa(b"x", "https://exemplo.com/outro.mp4")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            with self.assertRaises(ErroProvedor):
                baixar("https://v3.fal.media/a.mp4")

    def test_recusa_arquivo_grande_declarado_e_real(self):
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b"x", "https://fal.media/a", tamanho=10**9)):
            with self.assertRaises(ErroProvedor):
                baixar("https://fal.media/a")
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b"x" * 101, "https://fal.media/a")):
            with self.assertRaises(ErroProvedor):
                baixar("https://fal.media/a", tamanho_maximo=100)

    def test_baixa_dentro_das_regras(self):
        with mock.patch("urllib.request.urlopen", return_value=RespostaFalsa(b"ok", "https://v3.fal.media/a", tamanho=2)):
            self.assertEqual(baixar("https://v3.fal.media/a"), b"ok")

    def test_lista_configuravel(self):
        original = list(rede.DOMINIOS_DOWNLOAD)
        try:
            rede.configurar_downloads(["images.pexels.com"])
            self.assertTrue(dominio_permitido("https://images.pexels.com/x.jpg"))
            self.assertFalse(dominio_permitido("https://fal.media/x.jpg"))
        finally:
            rede.configurar_downloads(original)


if __name__ == "__main__":
    unittest.main()

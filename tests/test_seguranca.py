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


class TestMascarar(unittest.TestCase):
    def test_esconde_valor_de_variavel_de_chave(self):
        from torralles_studio.seguranca import mascarar

        with mock.patch.dict("os.environ", {"FAL_KEY": "abcd1234segredo9876"}):
            texto = mascarar("erro com chave abcd1234segredo9876 no corpo")
        self.assertNotIn("abcd1234segredo9876", texto)
        self.assertIn("abc…9876", texto)

    def test_esconde_formatos_conhecidos(self):
        from torralles_studio.seguranca import mascarar

        texto = mascarar("Authorization: Bearer abcdefghijklmnop1234 e sk-proj_ABCDEFGHIJKLMNOPQRST e AIzaSyA1234567890abcdefghij")
        for segredo in ("abcdefghijklmnop1234", "sk-proj_ABCDEFGHIJKLMNOPQRST", "AIzaSyA1234567890abcdefghij"):
            self.assertNotIn(segredo, texto)

    def test_erro_de_provedor_ja_sai_mascarado(self):
        with mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-segredo-muito-longo-123456"}):
            erro = ErroProvedor("HTTP 401: chave sk-segredo-muito-longo-123456 inválida")
        self.assertNotIn("sk-segredo-muito-longo-123456", str(erro))


class TestOrcamento(unittest.TestCase):
    def _roteador(self, teto, *provedores):
        from torralles_studio.roteador import Roteador
        from torralles_studio.seguranca import Orcamento

        return Roteador({p.nome: p for p in provedores}, {"video": [p.nome for p in provedores]},
                        dormir=lambda s: None, orcamento=Orcamento(teto))

    def _provedor(self, nome, cfg, resposta="ok", erro=None):
        from torralles_studio.provedores.base import Provedor

        class P(Provedor):
            tipo = "video"
            chamadas = 0

            def executar(self, **kw):
                P.chamadas += 1
                if erro:
                    raise erro
                return resposta

        return P(nome, cfg)

    def test_pula_pago_que_nao_cabe_e_usa_gratis(self):
        kling = self._provedor("kling", {"custo_usd_por_segundo": 0.1}, "kling")
        zoom = self._provedor("zoom", {}, "zoom")
        rt = self._roteador(0.30, kling, zoom)
        r = rt.executar("video", duracao=5)  # 0,50 > 0,30
        self.assertEqual(r.provedor, "zoom")
        self.assertIn("teto de custo", r.tentativas[0].detalhe)
        self.assertEqual(rt.orcamento.gasto_usd, 0)

    def test_registra_gasto_e_para_quando_acaba(self):
        from torralles_studio.roteador import TodosFalharam

        img = self._provedor("img", {"custo_usd": 0.6})
        rt = self._roteador(1.0, img)
        rt.executar("video")
        self.assertAlmostEqual(rt.orcamento.gasto_usd, 0.6)
        with self.assertRaises(TodosFalharam) as ctx:
            rt.executar("video")
        self.assertIn("teto de custo", str(ctx.exception))

    def test_repeticao_tambem_conta_no_gasto(self):
        erro = ErroProvedor("503", status=503, temporario=True)
        img = self._provedor("img", {"custo_usd": 0.4}, erro=erro)
        rt = self._roteador(1.0, img)
        from torralles_studio.roteador import TodosFalharam

        with self.assertRaises(TodosFalharam):
            rt.executar("video")
        self.assertAlmostEqual(rt.orcamento.gasto_usd, 0.8)  # tentativa + 1 repetição

    def test_config_padrao_tem_teto_de_1_50(self):
        from torralles_studio.config import carregar_roteador

        self.assertEqual(carregar_roteador().orcamento.teto_usd, 1.50)

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from torralles_studio.banco import Banco
from torralles_studio.cerebro import coletar, exportar, resumo_markdown, sugestoes
from torralles_studio.loop import ResultadoLoop, TentativaPeca
from torralles_studio.qualidade import Avaliacao


def tentativa(n, provedor, aprovado, nota, problemas=(), custo=0.01, eliminatorios=()):
    av = Avaliacao("roteiro", aprovado=aprovado, nota=nota, problemas=list(problemas),
                   eliminatorios=list(eliminatorios))
    return TentativaPeca(n, provedor, f"v{n}", av, custo, {provedor: custo})


def registrar(banco, projeto, chave, tentativas, aprovado):
    melhor = tentativas[-1]
    resultado = ResultadoLoop(melhor.valor, melhor.provedor, melhor.avaliacao, aprovado, not aprovado,
                              "aprovado" if aprovado else "limite de tentativas", tentativas)
    banco.registrar_peca(projeto, "roteiro", chave, resultado)


class TestCerebro(unittest.TestCase):
    def setUp(self):
        self.banco = Banco()
        self.pid = self.banco.criar_projeto("vídeo 1", perfil="canal-a")
        for i in range(3):
            registrar(self.banco, self.pid, f"r{i}", [
                tentativa(1, "deepseek_chat", False, 55, ["Gancho fraco na cena 1"], eliminatorios=["duração total 41 s fora"]),
                tentativa(2, "claude", True, 85),
            ], True)
        outro = self.banco.criar_projeto("post 1", perfil="loja-b")
        registrar(self.banco, outro, "x", [tentativa(1, "claude", True, 90)], True)

    def test_numeros_de_producao(self):
        d = coletar(self.banco)
        self.assertEqual((d["pecas"], d["tentativas"], d["pecas_aprovadas"]), (4, 7, 4))
        self.assertEqual(d["etapas"]["roteiro"]["aprovadas"], 4)
        self.assertAlmostEqual(d["custo_total_usd"], 0.07)
        ds = {p["provedor"]: p for p in d["provedores"]}
        self.assertEqual((ds["deepseek_chat"]["taxa_reprovacao"], ds["claude"]["taxa_reprovacao"]), (1.0, 0.0))

    def test_problemas_parecidos_sao_agrupados(self):
        d = coletar(self.banco)
        problemas = {p["problema"]: p["vezes"] for p in d["problemas_recorrentes"]}
        self.assertEqual(problemas["gancho fraco na cena #"], 3)
        self.assertEqual(problemas["duração total # s fora"], 3)

    def test_sugestoes_positivas_com_numeros(self):
        texto = " ".join(sugestoes(coletar(self.banco)))
        self.assertIn("Prefira **claude** em roteiro: aprovou 4 de 4", texto)
        self.assertIn("Coloque **deepseek_chat** mais para o fim da cadeia de roteiro: reprovou 100% de 3", texto)
        self.assertIn("previna este problema que se repetiu 3 vezes", texto)

    def test_filtro_por_perfil_nao_mistura(self):
        d = coletar(self.banco, perfil="loja-b")
        self.assertEqual((d["pecas"], d["tentativas"]), (1, 1))
        self.assertIn("perfil loja-b", resumo_markdown(d, "2026-10-16"))

    def test_sem_dados_poucos_dados_e_nenhum_aprovado(self):
        vazio = Banco()
        self.assertIn("Sem produção registrada", resumo_markdown(coletar(vazio)))
        pid = vazio.criar_projeto("x")
        registrar(vazio, pid, "a", [tentativa(1, "gemini_flash", False, 40)], False)
        self.assertIn("ainda há poucos dados", resumo_markdown(coletar(vazio)))
        for i in range(3):
            registrar(vazio, pid, f"b{i}", [tentativa(1, "gemini_flash", False, 40)], False)
        self.assertIn("nenhum provedor aprovou em 4 tentativas", resumo_markdown(coletar(vazio)))

    def test_chaves_nunca_aparecem(self):
        pid = self.banco.criar_projeto("y")
        registrar(self.banco, pid, "k", [tentativa(1, "a", False, 10, ["erro com sk-abcdefghijklmnop0123"]),
                                         tentativa(2, "a", False, 10, ["erro com sk-abcdefghijklmnop0123"])], False)
        self.assertNotIn("sk-abcdefghijklmnop0123", resumo_markdown(coletar(self.banco)))

    def test_exportar_nao_sobrescreve_e_comando(self):
        with tempfile.TemporaryDirectory() as d:
            a = exportar(self.banco, d, data="2026-10-16")
            b = exportar(self.banco, d, data="2026-10-16")
            self.assertEqual((a.name, b.name), ("cerebro_2026-10-16.md", "cerebro_2026-10-16_2.md"))
            self.assertTrue(a.read_text(encoding="utf-8").startswith("## Torralles Studio — aprendizados (2026-10-16)"))

            from torralles_studio.__main__ import main
            from torralles_studio.config import CONFIG_PADRAO
            texto = Path(CONFIG_PADRAO).read_text(encoding="utf-8").replace(
                'caminho = "dados/torralles.db"', f'caminho = "{Path(d).as_posix()}/t.db"')
            cfg = Path(d) / "c.toml"
            cfg.write_text(texto, encoding="utf-8")
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--config", str(cfg), "cerebro", "-o", str(Path(d) / "c")]), 0)
            self.assertIn("Sem produção registrada", saida.getvalue())


if __name__ == "__main__":
    unittest.main()

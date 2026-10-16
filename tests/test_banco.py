import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio import banco as banco_mod
from torralles_studio.banco import Banco, chave_cache
from torralles_studio.loop import LoopCorrecao
from torralles_studio.provedores.base import Provedor
from torralles_studio.qualidade import Avaliador
from torralles_studio.rede import ErroProvedor
from torralles_studio.roteador import Roteador
from torralles_studio.seguranca import Orcamento

CRITERIOS = {"gancho": {"peso": 50, "descricao": "gancho"}, "clareza": {"peso": 50, "descricao": "clareza"}}
CONFIG = {"roteiro": {"nota_minima": 70, "criterios": CRITERIOS}}


def nota(n):
    return json.dumps({"criterios": {"gancho": {"evidencia": "x", "nota": n},
                                     "clareza": {"evidencia": "x", "nota": n}}, "problemas": []})


class Texto(Provedor):
    """Gerador falso: responde com o prompt (ou erro, se o prompt tiver 'QUEBRA')."""
    tipo = "texto"

    def __init__(self, nome, familia=None, custo=0.1, modelo="m1"):
        super().__init__(nome, {"familia": familia or nome, "custo_usd": custo, "modelo": modelo})
        self.chamadas = []

    def configurado(self):
        return None

    def executar(self, prompt, sistema=None):
        self.chamadas.append(prompt)
        if "QUEBRA" in prompt:
            raise ErroProvedor("serviço fora do ar", status=500)
        return f"resultado de: {prompt}"


class JuizFixo(Texto):
    def __init__(self, n=90):
        super().__init__("juiz", custo=0.01)
        self.n = n

    def executar(self, prompt, sistema=None):
        self.chamadas.append(prompt)
        return nota(self.n)


class Arquivo(Provedor):
    tipo = "imagem"

    def __init__(self):
        super().__init__("img", {"custo_usd": 0.05, "modelo": "img-1"})
        self.chamadas = 0

    def configurado(self):
        return None

    def executar(self, prompt, saida):
        self.chamadas += 1
        Path(saida).parent.mkdir(parents=True, exist_ok=True)
        Path(saida).write_bytes(f"png:{prompt}".encode())
        return Path(saida)


def montar(banco=None, gen=None, juiz=None, cache=False):
    gen, juiz = gen or Texto("gen"), juiz or JuizFixo()
    rt = Roteador({"gen": gen, "juiz": juiz}, {"roteiro": ["gen"], "juiz": ["juiz"]},
                  dormir=lambda s: None, repeticoes=0, orcamento=Orcamento(), cache=banco if cache else None)
    return LoopCorrecao(rt, Avaliador(rt, CONFIG)), gen, juiz


class TestEsquema(unittest.TestCase):
    def test_migracoes_aplicadas_e_reabrir_preserva_dados(self):
        with tempfile.TemporaryDirectory() as d:
            db = Banco(Path(d) / "t.db")
            self.assertEqual(db.versao, len(banco_mod.MIGRACOES))
            pid = db.criar_projeto("Vídeo de teste", {"tema": "café"})
            db.fechar()
            db = Banco(Path(d) / "t.db")
            self.assertEqual(db.projeto(pid)["briefing"], {"tema": "café"})
            db.fechar()

    def test_migracao_nova_e_aplicada_em_banco_existente(self):
        with tempfile.TemporaryDirectory() as d:
            Banco(Path(d) / "t.db").fechar()
            nova = banco_mod.MIGRACOES + [["ALTER TABLE projetos ADD COLUMN idioma TEXT DEFAULT 'a;b'"]]
            with mock.patch.object(banco_mod, "MIGRACOES", nova):
                db = Banco(Path(d) / "t.db")
                self.assertEqual(db.versao, len(nova))
                pid = db.criar_projeto("x")
                self.assertEqual(db.projeto(pid)["idioma"], "a;b")  # ";" dentro de texto não quebra
                db.fechar()

    def test_migracao_com_erro_nao_fica_pela_metade(self):
        quebrada = banco_mod.MIGRACOES + [["CREATE TABLE t1 (a)", "CREATE TABLE projetos (b)"]]
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(banco_mod, "MIGRACOES", quebrada):
                with self.assertRaises(Exception):
                    Banco(Path(d) / "t.db")
            db = Banco(Path(d) / "t.db")
            self.assertEqual(db.versao, len(banco_mod.MIGRACOES))
            tabelas = {r[0] for r in db.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("t1", tabelas)
            db.fechar()

    def test_banco_mais_novo_que_o_programa_avisa(self):
        with tempfile.TemporaryDirectory() as d:
            db = Banco(Path(d) / "t.db")
            db.con.execute("PRAGMA user_version = 99")
            db.fechar()
            with self.assertRaisesRegex(RuntimeError, "mais nova que este programa"):
                Banco(Path(d) / "t.db")

    def test_cenas_salvas_e_substituidas(self):
        db = Banco()
        pid = db.criar_projeto("x")
        db.salvar_cenas(pid, [{"narracao": "a", "duracao": 5, "clima": "calmo"}, {"narracao": "b", "duracao": 4}])
        db.salvar_cenas(pid, [{"narracao": "a2", "duracao": 6}])
        cenas = db.cenas(pid)
        self.assertEqual(len(cenas), 1)
        self.assertEqual((cenas[0]["narracao"], cenas[0]["duracao"]), ("a2", 6))


class TestRetomada(unittest.TestCase):
    def test_retomar_sem_pagar_de_novo(self):
        db = Banco()
        pid = db.criar_projeto("Vídeo com 3 cenas")
        loop, gen, _ = montar(db)

        def rodar(prompts):
            pecas = []
            for i, p in enumerate(prompts, 1):
                peca, _ = db.produzir(pid, "roteiro", f"cena{i}",
                                      lambda refazer, p=p: loop.executar("roteiro", "roteiro", lambda fb, p=p: {"prompt": p},
                                                                         refazer=refazer))
                pecas.append(peca)
            return pecas

        primeira = rodar(["cena 1", "cena 2", "cena 3 QUEBRA"])
        self.assertEqual([p["status"] for p in primeira], ["aprovado", "aprovado", "falhou"])
        custo_antes = db.custo_projeto(pid)["total"]
        chamadas_antes = len(gen.chamadas)

        segunda = rodar(["cena 1", "cena 2", "cena 3"])  # o serviço voltou
        self.assertEqual([p["status"] for p in segunda], ["aprovado"] * 3)
        self.assertEqual(gen.chamadas[chamadas_antes:], ["cena 3"])  # só a cena que faltava
        self.assertAlmostEqual(db.custo_projeto(pid)["total"] - custo_antes, 0.11)  # 0,10 geração + 0,01 juiz

    def test_peca_em_revisao_nao_e_refeita_a_nao_ser_que_peca(self):
        db = Banco()
        pid = db.criar_projeto("x")
        loop, gen, _ = montar(db, juiz=JuizFixo(40))
        fazer = lambda refazer: loop.executar("roteiro", "roteiro", lambda fb: {"prompt": "p"}, refazer=refazer)
        peca, reaproveitada = db.produzir(pid, "roteiro", "r", fazer)
        self.assertEqual((peca["status"], peca["revisar_manual"], reaproveitada), ("revisar", True, False))
        n = len(gen.chamadas)
        _, reaproveitada = db.produzir(pid, "roteiro", "r", fazer)
        self.assertTrue(reaproveitada)
        self.assertEqual(len(gen.chamadas), n)
        db.produzir(pid, "roteiro", "r", fazer, aceitar_revisar=False)
        self.assertGreater(len(gen.chamadas), n)
        # 2 + 2 (um gerador só: sai da peça após 2 reprovações), numeradas em sequência
        self.assertEqual([t["numero"] for t in db.tentativas(pid, chave="r")], [1, 2, 3, 4])

    def test_erro_na_avaliacao_guarda_o_custo_pago(self):
        db = Banco()
        pid = db.criar_projeto("x")
        loop, _, _ = montar(db)

        def checar(valor):
            raise RuntimeError("checagem quebrou")

        peca, _ = db.produzir(pid, "roteiro", "r", lambda refazer: loop.executar(
            "roteiro", "roteiro", lambda fb: {"prompt": "p"}, checar=checar))
        self.assertEqual(peca["status"], "revisar")
        self.assertEqual(db.custo_projeto(pid)["total"], 0.1)
        t = db.tentativas(pid)[0]
        self.assertEqual(t["modelo"], "m1")
        self.assertIn("checagem quebrou", t["erro"])

    def test_cada_tentativa_grava_seu_arquivo_e_a_escolhida_vai_para_a_saida(self):
        with tempfile.TemporaryDirectory() as d:
            img = Arquivo()
            juiz = JuizFixo()
            notas = iter([60, 65, 50, 40, 40, 40])
            juiz.executar = lambda prompt, sistema=None: nota(next(notas))
            rt = Roteador({"img": img, "juiz": juiz}, {"imagem": ["img"], "juiz": ["juiz"]}, orcamento=Orcamento())
            cfg = {"imagem": {"nota_minima": 70, "criterios": CRITERIOS}}
            loop = LoopCorrecao(rt, Avaliador(rt, cfg), tentativas_por_provedor=5, tentativas_totais=3)
            saida = Path(d) / "cena1.png"
            r = loop.executar("imagem", "imagem", lambda fb: {"prompt": "tentativa " + ("2" if fb else "1"),
                                                               "saida": saida})
            self.assertEqual(r.valor, saida)
            self.assertEqual(r.nota, 65.0)
            self.assertEqual(saida.read_bytes(), r.tentativas[1].valor.read_bytes())
            self.assertEqual(len({t.valor for t in r.tentativas}), 3)
            # refazer não sobrescreve os arquivos das tentativas anteriores
            r2 = loop.executar("imagem", "imagem", lambda fb: {"prompt": "nova", "saida": saida}, refazer=True)
            self.assertFalse({t.valor for t in r2.tentativas} & {t.valor for t in r.tentativas})

    def test_arquivo_apagado_obriga_a_refazer(self):
        with tempfile.TemporaryDirectory() as d:
            db = Banco(Path(d) / "t.db")
            pid = db.criar_projeto("x")
            arq = Path(d) / "cena1.png"
            arq.write_bytes(b"png")
            from torralles_studio.loop import ResultadoLoop
            db.registrar_peca(pid, "imagem", "cena1", ResultadoLoop(arq, "img", None, True, False, "aprovado"))
            self.assertEqual(db.peca_pronta(pid, "imagem", "cena1")["valor"], arq)
            arq.unlink()
            self.assertIsNone(db.peca_pronta(pid, "imagem", "cena1"))
            db.fechar()

    def test_custo_por_etapa_provedor_e_mes(self):
        db = Banco()
        pid = db.criar_projeto("x")
        loop, _, _ = montar(db)
        db.produzir(pid, "roteiro", "r", lambda refazer: loop.executar("roteiro", "roteiro", lambda fb: {"prompt": "p"}))
        custo = db.custo_projeto(pid)
        self.assertEqual(custo, {"total": 0.11, "por_etapa": {"roteiro": 0.11},
                                 "por_provedor": {"gen": 0.1, "juiz": 0.01}})
        from datetime import datetime, timezone
        self.assertEqual(db.custo_mes(datetime.now(timezone.utc).strftime("%Y-%m")), 0.11)
        self.assertEqual(db.projeto(pid)["custo_total_usd"], 0.11)


class TestCache(unittest.TestCase):
    def test_mesmo_pedido_nao_e_pago_duas_vezes(self):
        db = Banco()
        gen = Texto("gen")
        rt = Roteador({"gen": gen}, {"t": ["gen"]}, orcamento=Orcamento(), cache=db)
        r1 = rt.executar("t", prompt="ideias sobre café")
        r2 = rt.executar("t", prompt="ideias sobre café")
        self.assertEqual(r1.valor, r2.valor)
        self.assertEqual(len(gen.chamadas), 1)
        self.assertEqual(r2.tentativas[-1].status, "cache")
        self.assertAlmostEqual(rt.orcamento.gasto_usd, 0.1)
        rt.executar("t", prompt="ideias sobre chá")
        self.assertEqual(len(gen.chamadas), 2)

    def test_chave_muda_com_modelo_e_ignora_saida(self):
        a = chave_cache("gen", "m1", {"prompt": "x", "saida": "/tmp/a.png"})
        self.assertEqual(a, chave_cache("gen", "m1", {"prompt": "x", "saida": "/tmp/b.png"}))
        self.assertNotEqual(a, chave_cache("gen", "m2", {"prompt": "x"}))
        self.assertNotEqual(a, chave_cache("outro", "m1", {"prompt": "x"}))

    def test_arquivo_de_entrada_vale_pelo_conteudo(self):
        with tempfile.TemporaryDirectory() as d:
            a, b, c = Path(d) / "a.png", Path(d) / "b.png", Path(d) / "c.png"
            a.write_bytes(b"1"), b.write_bytes(b"1"), c.write_bytes(b"2")
            ka, kb, kc = (chave_cache("v", "m", {"imagem": p, "prompt": "zoom"}) for p in (a, b, c))
            self.assertEqual(ka, kb)
            self.assertNotEqual(ka, kc)

    def test_arquivo_vem_do_cache_mesmo_se_o_original_sumir(self):
        with tempfile.TemporaryDirectory() as d:
            db = Banco(Path(d) / "dados" / "t.db")
            img = Arquivo()
            rt = Roteador({"img": img}, {"imagem": ["img"]}, orcamento=Orcamento(), cache=db)
            r1 = rt.executar("imagem", prompt="pôr do sol", saida=Path(d) / "v1" / "cena1.png")
            r1.valor.unlink()
            r2 = rt.executar("imagem", prompt="pôr do sol", saida=Path(d) / "v2" / "cena1.png")
            self.assertEqual(img.chamadas, 1)
            self.assertEqual(r2.valor, Path(d) / "v2" / "cena1.png")
            self.assertEqual(r2.valor.read_bytes(), "png:pôr do sol".encode())
            db.fechar()

    def test_resultado_guardado_que_nao_valida_mais_chama_o_provedor(self):
        db = Banco()
        gen = Texto("gen")
        rt = Roteador({"gen": gen}, {"t": ["gen"]}, orcamento=Orcamento(), cache=db)
        rt.executar("t", prompt="p")

        def exigir_json(t):
            raise ValueError("não é JSON")

        with self.assertRaises(Exception):
            rt.executar("t", prompt="p", validar=exigir_json)
        self.assertEqual(len(gen.chamadas), 2)

    # Regressões da verificação independente (K24)
    def test_refazer_peca_rejeitada_nao_devolve_o_mesmo_resultado_do_cache(self):
        db = Banco()
        pid = db.criar_projeto("x")
        loop, gen, _ = montar(db, juiz=JuizFixo(40), cache=True)
        fazer = lambda refazer: loop.executar("roteiro", "roteiro", lambda fb: {"prompt": "p"}, refazer=refazer)
        db.produzir(pid, "roteiro", "r", fazer)
        n = len(gen.chamadas)
        db.produzir(pid, "roteiro", "r", fazer, aceitar_revisar=False)
        self.assertGreater(len(gen.chamadas), n)
        self.assertEqual(gen.chamadas[n], "p")  # o mesmo pedido foi ao gerador, não ao cache

    def test_mudar_config_do_provedor_muda_a_chave(self):
        db = Banco()
        gen = Texto("gen")
        rt = Roteador({"gen": gen}, {"t": ["gen"]}, orcamento=Orcamento(), cache=db)
        rt.executar("t", prompt="p")
        gen.cfg["voz"] = "outra"
        r = rt.executar("t", prompt="p")
        self.assertEqual(len(gen.chamadas), 2)
        self.assertEqual(r.tentativas[-1].status, "ok")
        gen.cfg["timeout"] = 999  # não muda o resultado: continua no cache
        self.assertEqual(rt.executar("t", prompt="p").tentativas[-1].status, "cache")

    def test_cache_de_qualquer_provedor_da_cadeia_vale_antes_de_pagar(self):
        db = Banco()
        a, b = Texto("a"), Texto("b")
        rt = Roteador({"a": a, "b": b}, {"t": ["a", "b"]}, orcamento=Orcamento(), cache=db, repeticoes=0)
        a.configurado = lambda: "fora do ar"  # a indisponível: b gera e guarda
        rt.executar("t", prompt="p")
        a.configurado = lambda: None  # a voltou
        r = rt.executar("t", prompt="p")
        self.assertEqual((r.provedor, r.tentativas[-1].status, len(a.chamadas)), ("b", "cache", 0))

    def test_saida_igual_ao_arquivo_do_cache(self):
        with tempfile.TemporaryDirectory() as d:
            db = Banco(Path(d) / "t.db")
            img = Arquivo()
            rt = Roteador({"img": img}, {"imagem": ["img"]}, orcamento=Orcamento(), cache=db)
            rt.executar("imagem", prompt="x", saida=Path(d) / "a.png")
            guardado = next((Path(d) / "cache").iterdir())
            r = rt.executar("imagem", prompt="x", saida=guardado)
            self.assertEqual((img.chamadas, r.tentativas[-1].status), (1, "cache"))
            db.fechar()

    def test_provedor_pode_desligar_o_cache(self):
        db = Banco()
        gen = Texto("gen")
        gen.cfg["cache"] = False
        rt = Roteador({"gen": gen}, {"t": ["gen"]}, orcamento=Orcamento(), cache=db)
        rt.executar("t", prompt="p")
        rt.executar("t", prompt="p")
        self.assertEqual(len(gen.chamadas), 2)

    def test_cache_com_defeito_nao_derruba_a_geracao(self):
        class Quebrado:
            def cache_buscar(self, *a):
                raise RuntimeError("disco cheio")

            def cache_guardar(self, *a):
                raise RuntimeError("disco cheio")

        gen = Texto("gen")
        rt = Roteador({"gen": gen}, {"t": ["gen"]}, orcamento=Orcamento(), cache=Quebrado())
        self.assertEqual(rt.executar("t", prompt="p").valor, "resultado de: p")


class TestConfigDoBanco(unittest.TestCase):
    def test_carregar_banco_usa_caminho_do_config(self):
        from torralles_studio.config import CONFIG_PADRAO, carregar_banco

        with tempfile.TemporaryDirectory() as d:
            destino = Path(d) / "sub" / "x.db"
            texto = Path(CONFIG_PADRAO).read_text(encoding="utf-8").replace(
                'caminho = "dados/torralles.db"', f'caminho = "{destino.as_posix()}"')
            cfg = Path(d) / "c.toml"
            cfg.write_text(texto, encoding="utf-8")
            db = carregar_banco(cfg)
            self.assertTrue(destino.exists())
            db.fechar()


if __name__ == "__main__":
    unittest.main()

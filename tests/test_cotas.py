"""K34 (spec 14 §B e §C): cotas que duram entre execuções e licença por modalidade (D24)."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from torralles_studio.banco import Banco
from torralles_studio.config import CONFIG_PADRAO, carregar_roteador, validar_cotas_e_licencas
from torralles_studio.cotas import (Cotas, bloqueio_de_licenca, cota_esgotada, licenca_do_provedor,
                                    proxima_renovacao, validar_renova)
from torralles_studio.perfis import ErroPerfil, Perfil, _validar
from torralles_studio.provedores.base import Provedor
from torralles_studio.rede import ErroProvedor, _retry_after
from torralles_studio.roteador import Roteador, TodosFalharam

UTC = timezone.utc


class Falso(Provedor):
    def __init__(self, nome, respostas=(), cfg=None, tipo="imagem"):
        super().__init__(nome, cfg or {})
        self.tipo = tipo
        self.respostas = list(respostas)
        self.chamadas = 0

    def configurado(self):
        return None

    def executar(self, **kwargs):
        self.chamadas += 1
        r = self.respostas.pop(0) if self.respostas else "ok"
        if isinstance(r, Exception):
            raise r
        return r


class Parede:
    def __init__(self, quando):
        self.agora = quando

    def __call__(self):
        return self.agora


def roteador(banco, relogio, *provedores, tarefa="imagem"):
    return Roteador({p.nome: p for p in provedores}, {tarefa: [p.nome for p in provedores]},
                    dormir=lambda s: None, repeticoes=0, cotas=Cotas(banco, relogio))


class TestRenovacao(unittest.TestCase):
    def test_horario_fixo_utc(self):
        inicio = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
        self.assertEqual(proxima_renovacao("00:00 UTC", inicio), datetime(2026, 11, 18, 0, 0, tzinfo=UTC))
        self.assertEqual(proxima_renovacao("12:30 UTC", inicio), datetime(2026, 11, 17, 12, 30, tzinfo=UTC))

    def test_24h_corridas_e_mensal(self):
        inicio = datetime(2026, 12, 20, 10, 0, tzinfo=UTC)
        self.assertEqual(proxima_renovacao("24h corridas", inicio), inicio + timedelta(hours=24))
        self.assertEqual(proxima_renovacao("mensal:1", inicio), datetime(2027, 1, 1, tzinfo=UTC))
        self.assertEqual(proxima_renovacao("mensal:25", inicio), datetime(2026, 12, 25, tzinfo=UTC))

    def test_formato_invalido(self):
        for errado in ("todo dia", "25:00 UTC", "mensal:31", 3):
            self.assertIsNotNone(validar_renova(errado), errado)
        self.assertIsNone(validar_renova(None))


class TestCotaQueDura(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.caminho = Path(self.pasta.name) / "t.db"
        self.relogio = Parede(datetime(2026, 11, 17, 10, 0, tzinfo=UTC))
        self.cfg = {"cota": {"limite": 2, "renova": "00:00 UTC", "padroes": ["daily quota"]}}

    def tearDown(self):
        self.pasta.cleanup()

    def test_limite_do_config_pula_ate_renovar_mesmo_em_nova_execucao(self):
        with Banco(self.caminho) as banco:
            a, b = Falso("a", cfg=self.cfg), Falso("b")
            rt = roteador(banco, self.relogio, a, b)
            self.assertEqual(rt.executar("imagem", usar_cache=False).provedor, "a")
            self.assertEqual(rt.executar("imagem", usar_cache=False).provedor, "a")
            self.assertEqual(rt.executar("imagem", usar_cache=False).provedor, "b")
            self.assertEqual(a.chamadas, 2)
        with Banco(self.caminho) as banco:  # nova execução: o banco lembra
            a, b = Falso("a", cfg=self.cfg), Falso("b")
            r = roteador(banco, self.relogio, a, b).executar("imagem", usar_cache=False)
            self.assertEqual((r.provedor, a.chamadas), ("b", 0))
            self.assertIn("cota acabou", r.tentativas[0].detalhe)
            self.assertIn("17/11 às 21:00", r.tentativas[0].detalhe)  # 00:00 UTC de 18/11 = 21:00 de 17/11 em Brasília
            self.relogio.agora = datetime(2026, 11, 18, 0, 1, tzinfo=UTC)  # virou o dia
            self.assertEqual(roteador(banco, self.relogio, a, b).executar("imagem", usar_cache=False).provedor, "a")

    def test_mensagem_de_cota_esgota_e_rate_limit_so_descansa(self):
        with Banco(self.caminho) as banco:
            a = Falso("a", [ErroProvedor("HTTP 429: daily quota exceeded", status=429)], cfg=self.cfg)
            rt = roteador(banco, self.relogio, a, Falso("b"))
            rt.executar("imagem", usar_cache=False)
            self.assertIsNotNone(Cotas(banco, self.relogio).estado("a")["esgotado_ate"])

            c = Falso("c", [ErroProvedor("HTTP 429: rate limit, try again", status=429)], cfg=self.cfg)
            rt = roteador(banco, self.relogio, c, Falso("d"))
            rt.executar("imagem", usar_cache=False)
            self.assertIsNone(Cotas(banco, self.relogio).estado("c")["esgotado_ate"])
            self.assertIn("descanso", rt._em_descanso("c"))  # descanso curto de sempre

    def test_retry_after_longo_esgota_mesmo_sem_padrao(self):
        erro = ErroProvedor("HTTP 429", status=429, retry_after=7200)
        self.assertTrue(cota_esgotada(erro, {}))
        self.assertFalse(cota_esgotada(ErroProvedor("HTTP 429", status=429, retry_after=30), {}))
        self.assertFalse(cota_esgotada(ErroProvedor("rate limit reached", status=429), {"padroes": ["quota"]}))

    def test_cada_chamada_gasta_inclusive_repeticao_e_cache_nao_gasta(self):
        with Banco(self.caminho) as banco:
            cfg = {"cota": {"limite": 10, "renova": "24h corridas", "creditos": {"animar": 4}}}
            a = Falso("a", [ErroProvedor("503", status=503, temporario=True), "x"], cfg=cfg, tipo="video")
            rt = Roteador({"a": a}, {"animar": ["a"]}, dormir=lambda s: None, repeticoes=1,
                          cotas=Cotas(banco, self.relogio), cache=banco)
            rt.executar("animar", prompt="p")
            self.assertEqual(Cotas(banco, self.relogio).estado("a")["usado"], 8)  # 2 chamadas × 4 créditos
            rt.executar("animar", prompt="p")  # mesmo pedido: vem do cache
            self.assertEqual(a.chamadas, 2)
            self.assertEqual(Cotas(banco, self.relogio).estado("a")["usado"], 8)

    def test_conta_compartilhada_soma_entre_provedores(self):
        with Banco(self.caminho) as banco:
            cfg = {"cota": {"conta": "conta-x", "limite": 1, "renova": "24h corridas"}}
            a, b, c = Falso("a", cfg=cfg), Falso("b", cfg=cfg), Falso("c")
            r = roteador(banco, self.relogio, a, b, c)
            r.executar("imagem", usar_cache=False)
            self.assertEqual(r.executar("imagem", usar_cache=False).provedor, "c")

    def test_sem_banco_funciona_como_antes(self):
        a = Falso("a", [ErroProvedor("daily quota", status=429), "x"], cfg=self.cfg)
        rt = Roteador({"a": a, "b": Falso("b")}, {"imagem": ["a", "b"]}, dormir=lambda s: None, repeticoes=0)
        self.assertEqual(rt.executar("imagem").provedor, "b")
        self.assertEqual(rt.executar("imagem", usar_cache=False).provedor, "b")  # não bate de novo nesta execução

    def test_retry_after_do_cabecalho(self):
        self.assertEqual(_retry_after({"Retry-After": "120"}), 120)
        self.assertIsNone(_retry_after({}))
        self.assertIsNone(_retry_after({"Retry-After": "amanhã"}))


class TestLicenca(unittest.TestCase):
    def test_compatibilidade_com_somente_nao_comercial_e_padrao_comercial(self):
        self.assertEqual(licenca_do_provedor(Falso("f", cfg={"somente_nao_comercial": True})), "nao_comercial")
        self.assertEqual(licenca_do_provedor(Falso("k")), "comercial")

    def test_regras_por_modalidade(self):
        nc = Falso("nc", cfg={"licenca": "nao_comercial"})
        self.assertIsNotNone(bloqueio_de_licenca(nc, "imagem", comercial=False))  # regra padrão: comercial
        self.assertIsNone(bloqueio_de_licenca(nc, "imagem", comercial=False, regras={"imagem": "como_freesound"}))
        self.assertIsNotNone(bloqueio_de_licenca(nc, "imagem", comercial=True, regras={"imagem": "como_freesound"}))
        self.assertIsNotNone(bloqueio_de_licenca(Falso("m", cfg={"marca_dagua": True}), "animar"))
        self.assertIsNone(bloqueio_de_licenca(nc, "midia_audio"))  # buscas de mídia seguem a regra do midia.py

    def test_a_conferir_nunca_entra(self):
        prov = Falso("x", cfg={"licenca": "a_conferir"})
        for tarefa in ("imagem", "texto", "midia_imagem"):
            self.assertIn("a conferir", bloqueio_de_licenca(prov, tarefa, comercial=False,
                                                            regras={"imagem": "como_freesound"}))

    def test_roteador_pula_nao_comercial_em_perfil_comercial(self):
        nc, ok = Falso("nc", cfg={"licenca": "nao_comercial"}), Falso("ok")
        rt = Roteador({"nc": nc, "ok": ok}, {"imagem": ["nc", "ok"]}, dormir=lambda s: None)
        rt.licenca_por_modalidade = {"imagem": "como_freesound"}
        self.assertEqual(rt.executar("imagem").provedor, "ok")
        self.assertEqual(nc.chamadas, 0)
        rt.comercial = False
        self.assertEqual(rt.executar("imagem", usar_cache=False).provedor, "nc")

    def test_perfil_valida_e_passa_a_regra_ao_roteador(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "canal.toml"
            dados = {"id": "canal", "nome": "Canal", "comercial": False, "licenca_por_modalidade": {"animar": "como_freesound"}}
            perfil = _validar(dados, arquivo, Path(pasta), None)
            base = Roteador({"a": Falso("a")}, {"imagem": ["a"]})
            rt = perfil.roteador(base)
            self.assertEqual((rt.comercial, rt.licenca_por_modalidade), (False, {"animar": "como_freesound"}))
            for errado in ({"animar": "livre"}, {"musica": "comercial"}):
                with self.assertRaises(ErroPerfil):
                    _validar({"id": "canal", "nome": "Canal", "licenca_por_modalidade": errado}, arquivo, Path(pasta), None)

    def test_config_recusa_licenca_e_cota_erradas(self):
        for cfg in ({"licenca": "livre"}, {"cota": {"renova": "sempre"}}, {"cota": {"limite": 0, "renova": "24h corridas"}},
                    {"cota": 5}, {"cota": {"limite": 3}}):
            with self.assertRaises(ValueError):
                validar_cotas_e_licencas({"x": Falso("x", cfg=cfg)})


class TestApelidoETarefaAnimar(unittest.TestCase):
    def test_config_padrao_tem_animar_e_video_vira_apelido(self):
        rt = carregar_roteador(CONFIG_PADRAO)
        self.assertIn("animar", rt.cadeias)
        self.assertNotIn("video", rt.cadeias)
        self.assertEqual(rt.tipo_da_tarefa("video"), rt.tipo_da_tarefa("animar"))

    def test_config_antigo_com_video_aceita_animar(self):
        rt = Roteador({"a": Falso("a", tipo="video")}, {"video": ["a"]}, dormir=lambda s: None)
        self.assertEqual(rt.executar("animar").provedor, "a")

    def test_apelido_video_vale_para_licenca_e_creditos(self):
        from torralles_studio.cotas import creditos_de

        marca = Falso("m", cfg={"marca_dagua": True, "cota": {"creditos": {"animar": 7}}})
        self.assertIsNotNone(bloqueio_de_licenca(marca, "video"))
        self.assertEqual(creditos_de(marca, "video"), 7)
        with tempfile.TemporaryDirectory() as pasta:
            perfil = _validar({"id": "canal", "nome": "C", "licenca_por_modalidade": {"video": "como_freesound"}},
                              Path(pasta) / "canal.toml", Path(pasta), None)
            self.assertEqual(perfil.licenca_por_modalidade, {"animar": "como_freesound"})

    def test_gasto_atomico_entre_duas_conexoes(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "t.db"
            relogio = Parede(datetime(2026, 11, 17, 10, 0, tzinfo=UTC))
            cota = {"renova": "24h corridas"}
            with Banco(caminho) as b1, Banco(caminho) as b2:
                for _ in range(5):
                    Cotas(b1, relogio).gastar("x", cota)
                    Cotas(b2, relogio).gastar("x", cota)
                self.assertEqual(Cotas(b1, relogio).estado("x")["usado"], 10)


class TestComandoCotas(unittest.TestCase):
    def test_esgotar_listar_e_liberar(self):
        from torralles_studio.__main__ import main

        with tempfile.TemporaryDirectory() as pasta:
            config = Path(pasta) / "c.toml"
            texto = CONFIG_PADRAO.read_text(encoding="utf-8").replace(
                'caminho = "dados/torralles.db"', f'caminho = "{(Path(pasta) / "t.db").as_posix()}"')
            texto += '\n[provedores.pollinations.cota]\nlimite = 50\nrenova = "00:00 UTC"\n'
            config.write_text(texto, encoding="utf-8")
            saida = io.StringIO()
            with redirect_stdout(saida):
                self.assertEqual(main(["--config", str(config), "cotas", "--esgotar", "pollinations"]), 0)
                self.assertEqual(main(["--config", str(config), "cotas"]), 0)
                self.assertEqual(main(["--config", str(config), "cotas", "--liberar", "pollinations"]), 0)
            texto = saida.getvalue()
            self.assertIn("esgotado", texto)
            self.assertIn("0 de 50 créditos", texto)
            self.assertIn("liberada", texto)
            self.assertEqual(main(["--config", str(config), "cotas", "--esgotar", "nao-existe"]), 1)


if __name__ == "__main__":
    unittest.main()

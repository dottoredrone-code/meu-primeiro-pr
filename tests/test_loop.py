import json
import unittest

from torralles_studio.loop import LoopCorrecao
from torralles_studio.provedores.base import Provedor
from torralles_studio.qualidade import Avaliador
from torralles_studio.relatorio import RelatorioQualidade
from torralles_studio.roteador import Roteador
from torralles_studio.seguranca import Orcamento

CRITERIOS = {"gancho": {"peso": 50, "piso": 60, "descricao": "gancho"},
             "clareza": {"peso": 50, "descricao": "clareza"}}
CONFIG = {"roteiro": {"nota_minima": 70, "num_juizes": 1, "divergencia_maxima": 20, "criterios": CRITERIOS}}


def nota(gancho, clareza):
    return json.dumps({"criterios": {"gancho": {"evidencia": "abre com fato", "nota": gancho},
                                     "clareza": {"evidencia": "frases curtas", "nota": clareza}},
                       "problemas": [f"gancho {gancho}"], "correcao_sugerida": "abra com uma pergunta"})


class Falso(Provedor):
    tipo = "texto"

    def __init__(self, nome, respostas, familia=None, custo=0.0):
        super().__init__(nome, {"familia": familia or nome, "custo_usd": custo})
        self.respostas = list(respostas)
        self.prompts = []

    def configurado(self):
        return None

    def executar(self, prompt, sistema=None):
        self.prompts.append(prompt)
        return self.respostas.pop(0)


def montar(geradores, juizes, teto=None, **limites):
    provs = {p.nome: p for p in geradores + juizes}
    cadeias = {"roteiro": [g.nome for g in geradores], "juiz": [j.nome for j in juizes]}
    rt = Roteador(provs, cadeias, dormir=lambda s: None, orcamento=Orcamento(teto))
    return LoopCorrecao(rt, Avaliador(rt, CONFIG), **limites)


def prompt(feedback):
    return {"prompt": "Escreva o roteiro." + (f"\n\n{feedback}" if feedback else "")}


class TestLoopCorrecao(unittest.TestCase):
    def test_aprova_na_segunda_com_feedback_no_prompt(self):
        gen = Falso("gen", ["v1", "v2"])
        loop = montar([gen], [Falso("juiz", [nota(40, 90), nota(85, 80)])])
        r = loop.executar("roteiro", "roteiro", prompt)
        self.assertTrue(r.aprovado)
        self.assertEqual((r.valor, r.motivo, len(r.tentativas)), ("v2", "aprovado", 2))
        self.assertNotIn("reprovada", gen.prompts[0])
        self.assertIn("A tentativa anterior foi reprovada (nota 65 / mínimo 70)", gen.prompts[1])
        self.assertIn("[gancho 40, abaixo do piso]", gen.prompts[1])
        self.assertIn("Mantenha o que estava bom: clareza (90)", gen.prompts[1])

    def test_para_no_limite_e_devolve_a_melhor_para_revisao(self):
        gen = Falso("gen", ["v1", "v2", "v3"])
        juiz = Falso("juiz", [nota(50, 50), nota(65, 70), nota(55, 60)])
        r = montar([gen], [juiz], tentativas_por_provedor=5, tentativas_totais=3).executar("roteiro", "roteiro", prompt)
        self.assertFalse(r.aprovado)
        self.assertTrue(r.revisar_manual)
        self.assertEqual((r.valor, r.nota, r.motivo), ("v2", 67.5, "limite de tentativas"))
        self.assertEqual(len(r.tentativas), 3)

    def test_provedor_que_reprova_demais_passa_ao_proximo(self):
        a, b = Falso("a", ["a1", "a2", "a3"]), Falso("b", ["b1"])
        juiz = Falso("juiz", [nota(40, 40), nota(40, 40), nota(90, 90)])
        r = montar([a, b], [juiz], tentativas_por_provedor=2).executar("roteiro", "roteiro", prompt)
        self.assertTrue(r.aprovado)
        self.assertEqual([t.provedor for t in r.tentativas], ["a", "a", "b"])
        self.assertIn("reprovada", b.prompts[0])  # o próximo provedor recebe o feedback

    def test_eliminatorio_nao_chama_juiz_e_perde_para_tentativa_sem_eliminatorio(self):
        gen = Falso("gen", ["R$ 22 a 28", "ok", "R$ 99"])
        juiz = Falso("juiz", [nota(50, 50)])

        def checar(valor):
            return ["preço inventado"] if "R$" in valor else []

        r = montar([gen], [juiz], tentativas_por_provedor=5, tentativas_totais=3).executar(
            "roteiro", "roteiro", prompt, checar=checar)
        self.assertEqual(len(juiz.prompts), 1)  # só a tentativa sem eliminatório foi ao juiz
        self.assertIn("[eliminatório] preço inventado", gen.prompts[1])
        self.assertEqual(r.valor, "ok")
        self.assertTrue(r.revisar_manual)

    def test_teto_de_custo_encerra_o_loop(self):
        gen = Falso("gen", ["v1", "v2", "v3"], custo=0.5)
        r = montar([gen], [Falso("juiz", [nota(40, 40)] * 3)], teto=1.0, tentativas_por_provedor=5).executar(
            "roteiro", "roteiro", prompt)
        self.assertEqual((r.motivo, len(r.tentativas)), ("teto de custo", 2))
        self.assertEqual([t.custo_usd for t in r.tentativas], [0.5, 0.5])
        self.assertTrue(r.revisar_manual)

    def test_sem_provedor_devolve_vazio_para_revisao(self):
        r = montar([], [Falso("juiz", [])]).executar("roteiro", "roteiro", prompt)
        self.assertEqual((r.valor, r.aprovado, r.revisar_manual, r.motivo), (None, False, True, "nenhum provedor disponível"))

    def test_sem_juiz_aceita_mas_marca_revisao(self):
        r = montar([Falso("gen", ["v1"])], []).executar("roteiro", "roteiro", prompt)
        self.assertTrue(r.aprovado)
        self.assertTrue(r.revisar_manual)
        self.assertTrue(r.avaliacao.sem_juiz)

    def test_cada_tentativa_vai_para_o_relatorio(self):
        loop = montar([Falso("gen", ["v1", "v2"])], [Falso("juiz", [nota(40, 40), nota(90, 90)])])
        loop.relatorio = RelatorioQualidade("demo")
        loop.executar("roteiro", "roteiro", prompt, peca="roteiro_principal")
        resumo = loop.relatorio.resumo()
        self.assertEqual((resumo["pecas"], resumo["tentativas"], resumo["aprovadas"]), (1, 2, 1))

    def test_juiz_nunca_e_da_familia_do_gerador_dentro_do_loop(self):
        gen = Falso("deepseek_chat", ["v1"], familia="deepseek")
        mesmo = Falso("openrouter_gratis", [nota(100, 100)], familia="deepseek")
        outro = Falso("claude", [nota(80, 80)], familia="anthropic")
        r = montar([gen], [mesmo, outro]).executar("roteiro", "roteiro", prompt)
        self.assertEqual(r.avaliacao.juizes, ["claude"])
        self.assertEqual(mesmo.prompts, [])

    def test_limites_invalidos(self):
        with self.assertRaises(ValueError):
            montar([], [], tentativas_totais=0)

    def test_config_padrao(self):
        from torralles_studio.config import carregar_loop

        loop = carregar_loop()
        self.assertEqual((loop.tentativas_por_provedor, loop.tentativas_totais), (2, 4))
        self.assertIs(loop.avaliador.roteador, loop.roteador)


if __name__ == "__main__":
    unittest.main()

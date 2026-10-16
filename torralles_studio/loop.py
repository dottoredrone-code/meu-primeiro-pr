"""Loop de correção (K09, spec 01): refaz só a peça reprovada, com feedback, até aprovar ou bater um limite.

Cada tentativa: gerar → checagem automática (eliminatórios) → juiz de outra família → aprovado? fim.
Se reprovar, o feedback (o que corrigir e o que manter) entra no prompt da próxima tentativa.
Um provedor que reprova `tentativas_por_provedor` vezes sai da cadeia nesta peça (passa ao próximo).
Ao estourar tentativas, provedores ou teto de custo, devolve a **melhor tentativa** com `revisar_manual`.
"""

import json
from dataclasses import dataclass, field

from .roteador import TodosFalharam


@dataclass
class TentativaPeca:
    numero: int
    provedor: str
    valor: object
    avaliacao: object
    custo_usd: float = 0.0


@dataclass
class ResultadoLoop:
    valor: object
    provedor: str | None
    avaliacao: object
    aprovado: bool
    revisar_manual: bool
    motivo: str
    tentativas: list = field(default_factory=list)

    @property
    def nota(self):
        return getattr(self.avaliacao, "nota", None)


def _como_texto(valor):
    if isinstance(valor, str):
        return valor
    try:
        return json.dumps(valor, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(valor)


def _chave_melhor(t):
    """Melhor tentativa: sem eliminatório > maior nota > menos critérios abaixo do piso > mais recente."""
    av = t.avaliacao
    return (not av.eliminatorios, av.nota if av.nota is not None else -1, -len(av.abaixo_do_piso), t.numero)


class LoopCorrecao:
    def __init__(self, roteador, avaliador, tentativas_por_provedor=2, tentativas_totais=4, relatorio=None):
        if tentativas_totais < 1 or tentativas_por_provedor < 1:
            raise ValueError("os limites do loop precisam ser de pelo menos 1 tentativa")
        self.roteador = roteador
        self.avaliador = avaliador
        self.tentativas_por_provedor = tentativas_por_provedor
        self.tentativas_totais = tentativas_totais
        self.relatorio = relatorio

    @classmethod
    def do_config(cls, roteador, avaliador, cfg, relatorio=None):
        return cls(roteador, avaliador,
                   tentativas_por_provedor=int(cfg.get("tentativas_por_provedor", 2)),
                   tentativas_totais=int(cfg.get("tentativas_totais", 4)),
                   relatorio=relatorio)

    def _gasto(self):
        orc = getattr(self.roteador, "orcamento", None)
        return orc.gasto_usd if orc is not None else 0.0

    def _sem_orcamento(self):
        orc = getattr(self.roteador, "orcamento", None)
        return orc is not None and orc.teto_usd is not None and orc.gasto_usd >= orc.teto_usd - 1e-9

    def executar(self, etapa, tarefa, montar_kwargs, *, checar=None, contexto=None, validar=None,
                 peca=None, excluir=()):
        """Produz uma peça com controle de qualidade.

        montar_kwargs(feedback) -> kwargs para o provedor (ex.: {"prompt": ...}); feedback é None na 1ª tentativa.
        checar(valor) -> lista de problemas eliminatórios (checagens automáticas e fatos travados).
        """
        peca = peca or etapa
        rubrica = self.avaliador.rubricas[etapa]
        tentativas, reprovacoes, excluidos = [], {}, set(excluir)
        feedback, motivo = None, "limite de tentativas"

        while len(tentativas) < self.tentativas_totais:
            if tentativas and self._sem_orcamento():
                motivo = "teto de custo"
                break
            gasto_antes = self._gasto()
            try:
                r = self.roteador.executar(tarefa, validar=validar, excluir=excluidos, **montar_kwargs(feedback))
            except TodosFalharam:
                motivo = "nenhum provedor disponível"
                break
            eliminatorios = list(checar(r.valor)) if checar else []
            av = self.avaliador.avaliar(etapa, _como_texto(r.valor), contexto=contexto, gerador=r.provedor,
                                        eliminatorios=eliminatorios)
            t = TentativaPeca(len(tentativas) + 1, r.provedor, r.valor, av, round(self._gasto() - gasto_antes, 6))
            tentativas.append(t)
            if self.relatorio is not None:
                self.relatorio.registrar(etapa, peca, t.numero, t.provedor, av, t.custo_usd)
            if av.aprovado:
                return ResultadoLoop(r.valor, r.provedor, av, True, av.revisar_manual, "aprovado", tentativas)
            reprovacoes[r.provedor] = reprovacoes.get(r.provedor, 0) + 1
            if reprovacoes[r.provedor] >= self.tentativas_por_provedor:
                excluidos.add(r.provedor)
            feedback = av.feedback(rubrica)

        if not tentativas:
            return ResultadoLoop(None, None, None, False, True, motivo, tentativas)
        melhor = max(tentativas, key=_chave_melhor)
        return ResultadoLoop(melhor.valor, melhor.provedor, melhor.avaliacao, False, True, motivo, tentativas)

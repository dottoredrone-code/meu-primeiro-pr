"""Relatório de qualidade e custo por peça (K10, spec 01 "Registro")."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RelatorioQualidade:
    projeto: str
    entradas: list = field(default_factory=list)

    def registrar(self, etapa, peca, tentativa, provedor, avaliacao=None, custo_usd=0.0, arquivo=None):
        self.entradas.append({
            "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "etapa": etapa,
            "peca": peca,
            "tentativa": tentativa,
            "provedor": provedor,
            "arquivo": str(arquivo) if arquivo else None,
            "custo_usd": round(float(custo_usd or 0), 4),
            "avaliacao": avaliacao.como_dict() if hasattr(avaliacao, "como_dict") else avaliacao,
        })

    def registrar_final(self, etapa, peca, resultado):
        """Decisão do loop de correção para a peça: tentativa escolhida, aprovado, revisar_manual e motivo."""
        escolhida = next((t.numero for t in resultado.tentativas if t.valor is resultado.valor
                          and t.avaliacao is resultado.avaliacao), None)
        av = resultado.avaliacao
        self.entradas.append({
            "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "etapa": etapa,
            "peca": peca,
            "final": True,
            "tentativa_escolhida": escolhida,
            "provedor": resultado.provedor,
            "aprovado": resultado.aprovado,
            "revisar_manual": resultado.revisar_manual,
            "motivo": resultado.motivo,
            "custo_usd": 0.0,
            "avaliacao": av.como_dict() if hasattr(av, "como_dict") else av,
        })

    def resumo(self, orcamento=None):
        finais = {}
        for e in self.entradas:  # vale a decisão final do loop; sem ela, a última tentativa da peça
            chave = (e["etapa"], e["peca"])
            if e.get("final") or not finais.get(chave, {}).get("final"):
                finais[chave] = e
        tentativas = [e for e in self.entradas if not e.get("final")]

        def campo(e, nome):
            return e[nome] if nome in e else (e["avaliacao"] or {}).get(nome)

        avaliadas = [e for e in finais.values() if e["avaliacao"] or e.get("final")]
        notas = [e["avaliacao"]["nota"] for e in avaliadas if e["avaliacao"] and e["avaliacao"].get("nota") is not None]
        custo = orcamento.gasto_usd if orcamento is not None else sum(e["custo_usd"] for e in tentativas)
        return {
            "projeto": self.projeto,
            "pecas": len(finais),
            "tentativas": len(tentativas),
            "aprovadas": sum(1 for e in avaliadas if campo(e, "aprovado")),
            "reprovadas": sum(1 for e in avaliadas if not campo(e, "aprovado")),
            "revisar_manual": sum(1 for e in avaliadas if campo(e, "revisar_manual")),
            "nota_media": round(sum(notas) / len(notas), 1) if notas else None,
            "custo_total_usd": round(custo, 4),
            "teto_usd": getattr(orcamento, "teto_usd", None),
        }

    def salvar(self, caminho, orcamento=None):
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = {"resumo": self.resumo(orcamento), "entradas": self.entradas}
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return caminho

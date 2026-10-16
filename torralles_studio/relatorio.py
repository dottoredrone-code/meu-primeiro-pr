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

    def resumo(self, orcamento=None):
        finais = {}
        for e in self.entradas:  # a última tentativa de cada peça é a que vale
            finais[(e["etapa"], e["peca"])] = e
        avaliacoes = [e["avaliacao"] for e in finais.values() if e["avaliacao"]]
        notas = [a["nota"] for a in avaliacoes if a.get("nota") is not None]
        custo = orcamento.gasto_usd if orcamento is not None else sum(e["custo_usd"] for e in self.entradas)
        return {
            "projeto": self.projeto,
            "pecas": len(finais),
            "tentativas": len(self.entradas),
            "aprovadas": sum(1 for a in avaliacoes if a.get("aprovado")),
            "reprovadas": sum(1 for a in avaliacoes if not a.get("aprovado")),
            "revisar_manual": sum(1 for a in avaliacoes if a.get("revisar_manual")),
            "nota_media": round(sum(notas) / len(notas), 1) if notas else None,
            "custo_total_usd": round(custo, 4),
            "teto_usd": getattr(orcamento, "teto_usd", None),
        }

    def salvar(self, caminho, orcamento=None):
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = {"resumo": self.resumo(orcamento), "entradas": self.entradas}
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2))
        return caminho

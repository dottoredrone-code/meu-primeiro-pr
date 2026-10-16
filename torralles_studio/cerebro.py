"""Aprendizados do Studio para o Cérebro Centralizado (K27, D16, spec 07).

O Studio guarda os dados operacionais (banco local) e exporta um **resumo em Markdown** pronto para colar no
`CEREBRO_MESTRE.md`. O resumo segue o padrão do Cérebro: instruções positivas ("prefira X", "faça Y") e
números que sustentam cada uma. Nada de chaves (tudo passa por `mascarar`) e nada de conteúdo gerado inteiro.
"""

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .seguranca import mascarar

MIN_TENTATIVAS = 3          # abaixo disso, poucos dados para recomendar algo sobre um provedor
TAXA_ALTA_REPROVACAO = 0.5  # provedor que reprova mais que isso numa etapa vira sugestão de reordenar


def _normalizar_problema(texto):
    """Agrupa problemas parecidos: tira números, tempos e trechos entre aspas."""
    t = mascarar(str(texto)).lower()
    t = re.sub(r"aos [\d.,]+s:\s*", "", t)
    t = re.sub(r"['\"“”].*?['\"“”]", "…", t)
    t = re.sub(r"\d+([.,]\d+)?", "#", t)
    return re.sub(r"\s+", " ", t).strip()[:140]


def coletar(banco, desde=None, perfil=None):
    """Números de produção a partir do banco: por etapa, por provedor e problemas recorrentes."""
    sql = ("SELECT t.etapa, t.provedor, t.status, t.custo_usd, t.custos_json, t.criado_em, "
           "a.nota_final, a.problemas_json, a.eliminatorios_json, p.status AS status_peca, p.id AS peca_id "
           "FROM tentativas t JOIN pecas p ON p.id = t.peca_id JOIN projetos pr ON pr.id = p.projeto_id "
           "LEFT JOIN avaliacoes a ON a.tentativa_id = t.id WHERE 1 = 1")
    args = []
    if desde:
        sql, args = sql + " AND t.criado_em >= ?", args + [str(desde)]
    if perfil:
        sql, args = sql + " AND pr.perfil = ?", args + [perfil]
    linhas = [dict(l) for l in banco.con.execute(sql, args)]

    etapas, provedores, problemas, pecas = {}, {}, Counter(), {}
    custo_total = 0.0
    for l in linhas:
        custo_total += l["custo_usd"] or 0
        e = etapas.setdefault(l["etapa"], {"tentativas": 0, "aprovadas": 0, "custo_usd": 0.0, "notas": []})
        e["tentativas"] += 1
        e["aprovadas"] += l["status"] == "aprovado"
        e["custo_usd"] += l["custo_usd"] or 0
        if l["nota_final"] is not None:
            e["notas"].append(l["nota_final"])
        chave = (l["etapa"], l["provedor"] or "?")
        p = provedores.setdefault(chave, {"tentativas": 0, "aprovadas": 0, "notas": []})
        p["tentativas"] += 1
        p["aprovadas"] += l["status"] == "aprovado"
        if l["nota_final"] is not None:
            p["notas"].append(l["nota_final"])
        for campo in ("problemas_json", "eliminatorios_json"):
            for item in json.loads(l[campo] or "[]"):
                if str(item).startswith("nenhum juiz disponível"):
                    continue
                problemas[(l["etapa"], _normalizar_problema(item))] += 1
        pecas[l["peca_id"]] = l["status_peca"]

    media = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    return {
        "periodo_desde": desde,
        "perfil": perfil,
        "tentativas": len(linhas),
        "pecas": len(pecas),
        "pecas_aprovadas": sum(1 for s in pecas.values() if s == "aprovado"),
        "pecas_revisar": sum(1 for s in pecas.values() if s == "revisar"),
        "custo_total_usd": round(custo_total, 4),
        "etapas": {k: {**v, "custo_usd": round(v["custo_usd"], 4), "nota_media": media(v.pop("notas"))}
                   for k, v in sorted(etapas.items())},
        "provedores": [{"etapa": et, "provedor": pr, "tentativas": v["tentativas"], "aprovadas": v["aprovadas"],
                        "taxa_reprovacao": round(1 - v["aprovadas"] / v["tentativas"], 2),
                        "nota_media": media(v["notas"])}
                       for (et, pr), v in sorted(provedores.items())],
        "problemas_recorrentes": [{"etapa": et, "problema": pb, "vezes": n}
                                  for (et, pb), n in problemas.most_common(10) if n >= 2],
    }


def sugestoes(dados):
    """Instruções positivas para o Cérebro, sempre com o número que as sustenta."""
    itens = []
    por_etapa = {}
    for p in dados["provedores"]:
        if p["tentativas"] >= MIN_TENTATIVAS:
            por_etapa.setdefault(p["etapa"], []).append(p)
    for etapa, lista in sorted(por_etapa.items()):
        melhor = max(lista, key=lambda p: (1 - p["taxa_reprovacao"], p["nota_media"] or 0))
        if not any(p["aprovadas"] for p in lista):
            total = sum(p["tentativas"] for p in lista)
            itens.append(f"Revise o prompt e a régua de {etapa}: nenhum provedor aprovou em {total} tentativas.")
            continue
        if melhor["aprovadas"]:
            itens.append(f"Prefira **{melhor['provedor']}** em {etapa}: aprovou {melhor['aprovadas']} de "
                         f"{melhor['tentativas']} tentativas" + (f" (nota média {melhor['nota_media']})."
                                                                 if melhor["nota_media"] is not None else "."))
        for p in lista:
            if p is not melhor and p["taxa_reprovacao"] > TAXA_ALTA_REPROVACAO:
                itens.append(f"Coloque **{p['provedor']}** mais para o fim da cadeia de {etapa}: reprovou "
                             f"{round(p['taxa_reprovacao'] * 100)}% de {p['tentativas']} tentativas.")
    for pb in dados["problemas_recorrentes"][:5]:
        itens.append(f"No prompt de {pb['etapa']}, previna este problema que se repetiu {pb['vezes']} vezes: "
                     f"\"{pb['problema']}\".")
    return itens


def resumo_markdown(dados, data=None):
    """Seção pronta para colar no CEREBRO_MESTRE.md."""
    data = data or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    titulo = f"## Torralles Studio — aprendizados ({data})"
    if dados.get("perfil"):
        titulo += f" · perfil {dados['perfil']}"
    linhas = [titulo, ""]
    if not dados["tentativas"]:
        return "\n".join(linhas + ["Sem produção registrada no período: nada a aprender ainda.", ""])
    periodo = f" desde {dados['periodo_desde']}" if dados.get("periodo_desde") else ""
    linhas += [
        f"**Produção{periodo}:** {dados['pecas']} peças ({dados['pecas_aprovadas']} aprovadas, "
        f"{dados['pecas_revisar']} para revisão), {dados['tentativas']} tentativas, "
        f"US$ {dados['custo_total_usd']:.2f} no total.", "",
        "| Etapa | Tentativas | Aprovadas | Nota média | Custo (US$) |", "|---|---|---|---|---|",
    ]
    for etapa, e in dados["etapas"].items():
        nota = "-" if e["nota_media"] is None else e["nota_media"]
        linhas.append(f"| {etapa} | {e['tentativas']} | {e['aprovadas']} | {nota} | {e['custo_usd']:.3f} |")
    itens = sugestoes(dados)
    linhas += ["", "**Faça assim nas próximas produções:**"]
    linhas += [f"- {i}" for i in itens] or ["- Continue coletando: ainda há poucos dados para recomendar mudanças."]
    linhas.append("")
    return mascarar("\n".join(linhas))


def exportar(banco, pasta, desde=None, perfil=None, data=None):
    """Grava o resumo em <pasta>/cerebro_<data>[_perfil].md (sem sobrescrever) e devolve o caminho."""
    data = data or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    texto = resumo_markdown(coletar(banco, desde, perfil), data)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    base = f"cerebro_{data}" + (f"_{perfil}" if perfil else "")
    destino, n = pasta / f"{base}.md", 2
    while destino.exists():
        destino, n = pasta / f"{base}_{n}.md", n + 1
    destino.write_text(texto, encoding="utf-8")
    return destino

"""Teste prático do benchmark (K31, spec 04): os mesmos 3 briefings, a mesma régua para todas as ferramentas.

Pasta (padrão dados/benchmark/, fora do Git):
    <briefing>/<ferramenta>.mp4    o vídeo de cada ferramenta (CapCut, InVideo… você gera e salva aqui)
    <briefing>/<ferramenta>.json   dados anotados à mão (comando `benchmark dados`) ou pelo Studio
O Studio faz os vídeos dele com `benchmark produzir` (cada briefing com o próprio teto de US$ 1,50).
`benchmark avaliar` passa todos pela mesma régua: checagens automáticas (FFmpeg) e o mesmo juiz que assiste com
som, sem excluir a família de quem gerou (a régua é igual para todos). Resultado em resultados.json e
relatorio.md; com --doc, também em docs/sdd/04b-benchmark-pratico.md.
"""

import json
import math
import re
import shutil
from datetime import date
from pathlib import Path

BRIEFINGS = {
    "A": {"tema": "história do café no Brasil", "tipo": "informativo", "testa": "pesquisa e precisão"},
    "B": {"tema": "como funciona a fotossíntese", "tipo": "explicativo", "testa": "clareza e fidelidade"},
    "C": {"tema": "amanhecer numa fazenda de café", "tipo": "visual/emocional", "testa": "imagem e vídeo"},
}
DURACAO_S = 30
PROPORCAO = "9:16"
ESTUDIO = "torralles-studio"
EXTENSOES = (".mp4", ".mov", ".webm", ".mkv")
# dados anotados: nome → (descrição, mínimo, máximo)
CAMPOS_MANUAIS = {
    "tempo_min": ("tempo até o vídeo pronto (minutos)", 0, 24 * 60),
    "custo_usd": ("custo real em US$ (0 no plano grátis)", 0, 10_000),
    "creditos": ("créditos gastos", 0, 1_000_000),
    "intervencoes": ("intervenções manuais", 0, 1000),
    "tentativas": ("tentativas até um resultado aceitável", 0, 1000),
    "nota_diego": ("sua nota geral (0 a 10)", 0, 10),
    "voz_ptbr": ("qualidade da voz em pt-BR (0 a 10)", 0, 10),
    "legenda_ptbr": ("qualidade da legenda em pt-BR (0 a 10)", 0, 10),
}


def nome_ferramenta(nome):
    """Nome seguro para arquivo: minúsculas, números e hífen ("Google Flow" → "google-flow")."""
    import unicodedata

    t = "".join(c for c in unicodedata.normalize("NFD", str(nome).lower()) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    if not t:
        raise ValueError(f"nome de ferramenta inválido: {nome!r}")
    return t[:40]


def briefing_valido(b):
    b = str(b).upper()
    if b not in BRIEFINGS:
        raise ValueError(f"briefing {b!r} não existe (use {', '.join(BRIEFINGS)})")
    return b


def _ler_json(arq):
    try:
        dados = json.loads(Path(arq).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar_json(arq, dados):
    arq = Path(arq)
    arq.parent.mkdir(parents=True, exist_ok=True)
    parte = arq.with_name(arq.name + ".parte")
    parte.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    parte.replace(arq)


def _finito(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def registrar_dados(pasta, briefing, ferramenta, valores, observacoes=None):
    """Anota (ou completa) os dados à mão de uma ferramenta num briefing; devolve o arquivo."""
    briefing, ferramenta = briefing_valido(briefing), nome_ferramenta(ferramenta)
    novos = {}
    for campo, valor in valores.items():
        if valor is None:
            continue
        if campo not in CAMPOS_MANUAIS:
            raise ValueError(f"campo desconhecido: {campo}")
        _, minimo, maximo = CAMPOS_MANUAIS[campo]
        if not _finito(valor) or not minimo <= valor <= maximo:
            raise ValueError(f"{CAMPOS_MANUAIS[campo][0]}: precisa ser um número de {minimo:g} a {maximo:g}")
        novos[campo] = float(valor)
    if observacoes:
        novos["observacoes"] = " ".join(str(observacoes).split())[:500]
    if not novos:
        raise ValueError("nada para anotar: use --tempo-min, --custo, --intervencoes, --tentativas, --nota…")
    arq = Path(pasta) / briefing / f"{ferramenta}.json"
    _gravar_json(arq, {**_ler_json(arq), **novos})
    return arq


def registrar_estudio(pasta, briefing, relatorio):
    """Copia o vídeo do Studio para a pasta do benchmark e anota tempo, custo e tentativas (sem intervenção)."""
    briefing = briefing_valido(briefing)
    destino = Path(pasta) / briefing / f"{ESTUDIO}.mp4"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(relatorio["video"], destino)
    tentativas = 1 + sum(max(0, int(e.get("tentativas", 1)) - 1) for e in relatorio.get("etapas", [])
                         if isinstance(e, dict) and _finito(e.get("tentativas")))
    _gravar_json(destino.with_suffix(".json"), {
        **_ler_json(destino.with_suffix(".json")),
        "tempo_min": round(float(relatorio.get("tempo_s") or 0) / 60, 1),
        "custo_usd": float(relatorio.get("custo_usd") or 0), "intervencoes": 0.0, "tentativas": float(tentativas),
        "aprovado_pelo_studio": bool(relatorio.get("aprovado")),
    })
    return destino


def listar_videos(pasta):
    """[(briefing, ferramenta, vídeo)] em ordem; um vídeo por ferramenta (a 1ª extensão encontrada)."""
    saida = []
    for b in BRIEFINGS:
        vistos = set()
        for video in sorted((Path(pasta) / b).glob("*")):
            if video.suffix.lower() not in EXTENSOES or not video.is_file():
                continue
            try:
                f = nome_ferramenta(video.stem)
            except ValueError:
                continue
            if f not in vistos:
                vistos.add(f)
                saida.append((b, f, video))
    return saida


def checar_video(video, duracao_alvo=DURACAO_S):
    """Checagens automáticas da spec 03 que valem para qualquer vídeo (FFmpeg, grátis)."""
    import tempfile

    from .percepcao import analisar_video

    with tempfile.TemporaryDirectory() as tmp:
        rel = analisar_video(video, tmp, transcrever_audio=False)
    largura, altura, dur = rel.get("largura"), rel.get("altura"), rel.get("duracao_s") or 0
    som = rel.get("som") if isinstance(rel.get("som"), dict) else {}
    medidas = {"duracao_s": round(dur, 1), "resolucao": f"{largura}x{altura}" if largura and altura else None,
               "cortes_por_minuto": rel.get("cortes_por_minuto"), "lufs": som.get("lufs_integrado")}
    problemas = []
    if largura and altura and abs(largura / altura - 9 / 16) > 0.02:
        problemas.append(f"proporção {largura}x{altura} (pedido 9:16)")
    if largura and altura and min(largura, altura) < 1080:
        problemas.append(f"resolução {largura}x{altura} abaixo de 1080 no lado menor")
    if dur and abs(dur - duracao_alvo) > duracao_alvo * 0.2:
        problemas.append(f"duração {dur:.0f} s (pedido ~{duracao_alvo} s)")
    lufs = som.get("lufs_integrado")
    if not som or lufs is None:
        problemas.append("sem áudio medível")
    elif abs(lufs + 14) > 2:
        problemas.append(f"volume {lufs:.1f} LUFS (redes: −14)")
    return {"medidas": medidas, "problemas": problemas, "percepcao": rel}


def _contexto(briefing):
    b = BRIEFINGS[briefing]
    return (f"Briefing pedido a todas as ferramentas: vídeo {b['tipo']} sobre \"{b['tema']}\", vertical 9:16, "
            f"cerca de {DURACAO_S} s, narração e legenda em português do Brasil. Avalie quanto o vídeo cumpre esse "
            "briefing. A mesma régua vale para todas as ferramentas; ignore marcas d'água e logotipos.")


def avaliar_benchmark(pasta, novo_avaliador, *, aviso=None, checar=checar_video, avaliar=None):
    """Avalia todos os vídeos da pasta; salva e devolve a lista de resultados.

    novo_avaliador(): um Avaliador por briefing (cada um com o próprio teto de custo).
    """
    if avaliar is None:
        from .percepcao import avaliar_video as avaliar
    avisar = aviso or (lambda t: None)
    resultados, avaliador, atual = [], None, None
    for briefing, ferramenta, video in listar_videos(pasta):
        if briefing != atual:
            avaliador, atual = novo_avaliador(), briefing
        avisar(f"== {briefing} · {ferramenta}")
        item = {"briefing": briefing, "ferramenta": ferramenta, "video": video.name,
                # dados anotados pelo nome normalizado ("CapCut.mov" → capcut.json), como o `benchmark dados` grava
                "manual": _ler_json(video.with_name(f"{ferramenta}.json")) or _ler_json(video.with_suffix(".json"))}
        try:
            chk = checar(video)
            item.update(medidas=chk["medidas"], problemas=chk["problemas"])
            percepcao = chk.get("percepcao")
        except Exception as e:  # vídeo corrompido não derruba o benchmark inteiro
            from .seguranca import mascarar

            item.update(medidas={}, problemas=[f"não deu para medir: {mascarar(str(e))[:200]}"])
            percepcao = None
        try:
            av = avaliar(avaliador, str(video), contexto=_contexto(briefing), percepcao=percepcao)
            item.update(nota_juiz=av.nota, aprovado_juiz=av.aprovado, sem_juiz=av.sem_juiz, juizes=av.juizes,
                        criterios=av.criterios, problemas_juiz=av.problemas[:5])
        except Exception as e:
            from .seguranca import mascarar

            item.update(nota_juiz=None, sem_juiz=True, problemas_juiz=[mascarar(str(e))[:200]])
        resultados.append(item)
    if resultados:
        _gravar_json(Path(pasta) / "resultados.json",
                     {"avaliado_em": date.today().isoformat(), "resultados": resultados})
    return resultados


def _media(valores):
    v = [x for x in valores if _finito(x)]
    return round(sum(v) / len(v), 1) if v else None


def _fmt(v, sufixo=""):
    return "—" if v is None else f"{v:g}{sufixo}"


def ranking(resultados):
    """Médias por ferramenta, da maior nota do juiz para a menor (sem nota vai para o fim)."""
    por = {}
    for r in resultados:
        por.setdefault(r["ferramenta"], []).append(r)
    linhas = []
    for f, itens in por.items():
        man = [i.get("manual") or {} for i in itens]
        linhas.append({
            "ferramenta": f, "videos": len(itens), "nota_juiz": _media(i.get("nota_juiz") for i in itens),
            "nota_diego": _media(m.get("nota_diego") for m in man),
            "custo_usd": round(sum(m["custo_usd"] for m in man if _finito(m.get("custo_usd"))), 3)
            if any(_finito(m.get("custo_usd")) for m in man) else None,
            "tempo_min": _media(m.get("tempo_min") for m in man),
            "intervencoes": _media(m.get("intervencoes") for m in man),
            "tentativas": _media(m.get("tentativas") for m in man),
            "voz_ptbr": _media(m.get("voz_ptbr") for m in man), "legenda_ptbr": _media(m.get("legenda_ptbr") for m in man),
            "problemas": sum(len(i.get("problemas") or []) for i in itens),
        })
    return sorted(linhas, key=lambda x: (x["nota_juiz"] is None, -(x["nota_juiz"] or 0), x["ferramenta"]))


def relatorio_markdown(resultados):
    hoje = date.today().strftime("%d/%m/%Y")
    linhas = [f"# 04b — Benchmark prático ({hoje})", "",
              "> Gerado por `python -m torralles_studio benchmark avaliar` (K31, protocolo da "
              "[spec 04](04-benchmark.md)). Mesma régua para todos: checagens automáticas (FFmpeg) e o mesmo juiz "
              "que assiste com som. Dados de tempo, custo, intervenções e notas pessoais são anotados à mão.", ""]
    if not resultados:
        return "\n".join(linhas + ["Nenhum vídeo encontrado na pasta do benchmark.", ""])
    linhas += ["## Resultado geral", "",
               "| Ferramenta | Vídeos | Nota do juiz (0–100) | Sua nota (0–10) | Custo total (US$) | Tempo médio (min) "
               "| Intervenções | Tentativas | Voz pt-BR | Legenda pt-BR | Problemas automáticos |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in ranking(resultados):
        linhas.append(f"| {r['ferramenta']} | {r['videos']} | {_fmt(r['nota_juiz'])} | {_fmt(r['nota_diego'])} | "
                      f"{_fmt(r['custo_usd'])} | {_fmt(r['tempo_min'])} | {_fmt(r['intervencoes'])} | "
                      f"{_fmt(r['tentativas'])} | {_fmt(r['voz_ptbr'])} | {_fmt(r['legenda_ptbr'])} | {r['problemas']} |")
    for b, info in BRIEFINGS.items():
        itens = [r for r in resultados if r["briefing"] == b]
        if not itens:
            continue
        linhas += ["", f"## Briefing {b}: {info['tema']} ({info['tipo']}; testa {info['testa']})", "",
                   "| Ferramenta | Nota do juiz | Duração | Resolução | Volume (LUFS) | Problemas |", "|---|---|---|---|---|---|"]
        for r in sorted(itens, key=lambda x: (x.get("nota_juiz") is None, -(x.get("nota_juiz") or 0))):
            m = r.get("medidas") or {}
            probs = "; ".join((r.get("problemas") or []) + (["sem juiz: " + "; ".join(r.get("problemas_juiz") or [])]
                                                            if r.get("sem_juiz") else [])) or "—"
            linhas.append(f"| {r['ferramenta']} | {_fmt(r.get('nota_juiz'))} | {_fmt(m.get('duracao_s'), ' s')} | "
                          f"{m.get('resolucao') or '—'} | {_fmt(m.get('lufs'))} | {probs.replace('|', '/')} |")
            obs = (r.get("manual") or {}).get("observacoes")
            if obs:
                linhas.append(f"|  | _{str(obs).replace('|', '/')}_ | | | | |")
    linhas += ["", "## Como ler", "",
               "- Nota do juiz: régua da spec 03 (0–100), a mesma para todos. Sem nota = nenhum juiz conseguiu "
               "assistir (falta chave, bloqueio).",
               "- Sua nota e as de voz/legenda vêm do `benchmark dados`; são também uma rodada de calibração do juiz.",
               "- Problemas automáticos: proporção, resolução, duração (±20% de 30 s) e volume (−14 LUFS ±2).", ""]
    return "\n".join(linhas)

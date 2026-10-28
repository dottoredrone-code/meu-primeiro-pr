"""Teste prático do benchmark (K31, spec 04): os mesmos 3 briefings, a mesma régua para todas as ferramentas.

Pasta (padrão dados/benchmark/, fora do Git):
    <briefing>/<ferramenta>.mp4    o vídeo de cada ferramenta (CapCut, InVideo… você gera e salva aqui)
    <briefing>/<ferramenta>.json   dados anotados à mão (comando `benchmark dados`) ou pelo Studio
O Studio faz os vídeos dele com `benchmark produzir` (cada execução com o próprio teto de US$ 1,50; custo, tempo
e tentativas se somam entre execuções, e cada retomada conta como intervenção).
`benchmark avaliar` passa todos pela mesma régua: as checagens do vídeo final da spec 03 §3.6 (FFmpeg) e o mesmo
juiz que assiste com som. Exceção consciente à D15: o juiz NÃO exclui a família de quem gerou (só o Gemini assiste
vídeo, e a régua tem de ser igual para todos); suas notas servem de conferência desse possível viés.
Resultado em resultados.json e relatorio.md; com --doc, também em docs/sdd/04b-benchmark-pratico.md.
"""

import json
import math
import re
import shutil
import subprocess
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
TETO_USD = 1.50
EXTENSOES = (".mp4", ".mov", ".webm", ".mkv")
# dados anotados: nome → (descrição, mínimo, máximo, inteiro?)
CAMPOS_MANUAIS = {
    "tempo_min": ("tempo até o vídeo pronto (minutos)", 0, 24 * 60, False),
    "custo_usd": ("custo real em US$ (0 no plano grátis)", 0, 10_000, False),
    "creditos": ("créditos gastos", 0, 1_000_000, False),
    "intervencoes": ("intervenções manuais", 0, 1000, True),
    "tentativas": ("tentativas até um resultado aceitável", 0, 1000, True),
    "nota_diego": ("sua nota geral (0 a 10)", 0, 10, False),
    "voz_ptbr": ("qualidade da voz em pt-BR (0 a 10)", 0, 10, False),
    "legenda_ptbr": ("qualidade da legenda em pt-BR (0 a 10)", 0, 10, False),
}
# régua do vídeo final (spec 03 §3.6, a mesma de montagem.verificar_montagem)
TOLERANCIA_DURACAO = 0.10
LUFS_ALVO, TOLERANCIA_LUFS = -14.0, 1.0
PICO_MAXIMO_DB = -1.0
RESOLUCAO = (1080, 1920)


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
    """Anota (ou completa) os dados à mão de uma ferramenta num briefing; devolve o arquivo.

    O que você anota aqui nunca é trocado pelo `benchmark produzir` (fica em "anotado_a_mao").
    """
    briefing, ferramenta = briefing_valido(briefing), nome_ferramenta(ferramenta)
    novos = {}
    for campo, valor in valores.items():
        if valor is None:
            continue
        if campo not in CAMPOS_MANUAIS:
            raise ValueError(f"campo desconhecido: {campo}")
        descricao, minimo, maximo, inteiro = CAMPOS_MANUAIS[campo]
        if not _finito(valor) or not minimo <= valor <= maximo or (inteiro and valor != int(valor)):
            tipo = "um número inteiro" if inteiro else "um número"
            raise ValueError(f"{descricao}: precisa ser {tipo} de {minimo:g} a {maximo:g}")
        novos[campo] = float(valor)
    if observacoes:
        novos["observacoes"] = " ".join(str(observacoes).split())[:500]
    if not novos:
        raise ValueError("nada para anotar: use --tempo-min, --custo, --intervencoes, --tentativas, --nota…")
    arq = Path(pasta) / briefing / f"{ferramenta}.json"
    atual = _ler_json(arq)
    marcados = sorted(set(atual.get("anotado_a_mao") or []) | {c for c in novos if c in CAMPOS_MANUAIS})
    _gravar_json(arq, {**atual, **novos, "anotado_a_mao": marcados})
    return arq


def registrar_execucao(pasta, briefing, *, custo_usd, tempo_s, tentativas=0, relatorio=None):
    """Soma uma execução do Studio (concluída ou não) aos números dele no briefing.

    Custo, tempo e tentativas se acumulam: retomar depois de uma parada não zera o que já foi gasto. Cada execução
    depois da primeira conta como intervenção (alguém teve de rodar de novo). Campos que você anotou à mão
    (`benchmark dados`) não são trocados. relatorio: o do produzir, quando o vídeo ficou pronto (copia o vídeo).
    """
    briefing = briefing_valido(briefing)
    destino = Path(pasta) / briefing / f"{ESTUDIO}.mp4"
    arq = destino.with_suffix(".json")
    atual = _ler_json(arq)
    manual = set(atual.get("anotado_a_mao") or [])
    execucoes = int(atual.get("execucoes") or 0) + 1
    novo = dict(atual, execucoes=execucoes)
    soma = {"custo_usd": round(float(atual.get("custo_usd_total", 0)) + float(custo_usd or 0), 4),
            "tempo_min": round(float(atual.get("tempo_min_total", 0)) + float(tempo_s or 0) / 60, 1),
            "tentativas": float(int(atual.get("tentativas_total", 0)) + max(0, int(tentativas)))}
    if relatorio is not None and not soma["tentativas"]:
        # o roteiro saiu numa execução que parou depois: usa as tentativas guardadas no roteiro.json (mín. 1)
        guardadas = [int(e["tentativas"]) for e in relatorio.get("etapas", [])
                     if isinstance(e, dict) and e.get("etapa") == "roteiro" and _finito(e.get("tentativas"))]
        soma["tentativas"] = float(max(guardadas + [1]))
    novo.update(custo_usd_total=soma["custo_usd"], tempo_min_total=soma["tempo_min"],
                tentativas_total=int(soma["tentativas"]))
    for campo, valor in (*soma.items(), ("intervencoes", float(execucoes - 1))):
        if campo not in manual:
            novo[campo] = valor
    novo["acima_do_teto"] = soma["custo_usd"] > TETO_USD + 1e-9
    if relatorio is not None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(relatorio["video"], destino)
        novo["aprovado_pelo_studio"] = bool(relatorio.get("aprovado"))
    _gravar_json(arq, novo)
    return destino


def tentativas_do_relatorio(relatorio):
    """Tentativas feitas nesta execução (as reaproveitadas não contam de novo)."""
    total = 0
    for e in relatorio.get("etapas", []):
        if isinstance(e, dict) and not e.get("reaproveitado") and _finito(e.get("tentativas")):
            total += max(0, int(e["tentativas"]))
    return total


def listar_videos(pasta, aviso=None):
    """[(briefing, ferramenta, vídeo)] em ordem; um vídeo por ferramenta (avisa se houver dois com o mesmo nome)."""
    avisar = aviso or (lambda t: None)
    saida = []
    for b in BRIEFINGS:
        escolhidos = {}
        for video in sorted((Path(pasta) / b).glob("*"), key=lambda p: (p.name.lower(), p.name)):
            if video.name.startswith(".") or video.suffix.lower() not in EXTENSOES or not video.is_file():
                continue  # arquivos ocultos (._capcut.mp4 do macOS) não são vídeos
            try:
                f = nome_ferramenta(video.stem)
            except ValueError:
                continue
            if f in escolhidos:
                avisar(f"  ⚠ {b}: {video.name} ignorado (já existe {escolhidos[f].name} para '{f}')")
                continue
            escolhidos[f] = video
            saida.append((b, f, video))
    return saida


def _sondar(video):
    """Fluxos do arquivo (codecs, tamanho já girado pela rotação do celular)."""
    proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_type,codec_name,pix_fmt,width,height:stream_tags=rotate:"
                           "stream_side_data=rotation", "-of", "json", str(video)],
                          capture_output=True, stdin=subprocess.DEVNULL, text=True)
    if proc.returncode != 0:
        raise ValueError("o arquivo não abre como vídeo (corrompido ou formato desconhecido)")
    fluxos = json.loads(proc.stdout or "{}").get("streams", [])
    v = next((s for s in fluxos if s.get("codec_type") == "video"), None)
    a = next((s for s in fluxos if s.get("codec_type") == "audio"), None)
    info = {"video": v is not None, "audio": a is not None, "codec_audio": (a or {}).get("codec_name")}
    if v:
        rot = 0
        for lado in v.get("side_data_list") or []:
            if _finito(lado.get("rotation")):
                rot = int(lado["rotation"])
        try:
            rot = rot or int((v.get("tags") or {}).get("rotate", 0))
        except ValueError:
            pass
        largura, altura = v.get("width"), v.get("height")
        if abs(rot) % 180 == 90:  # vídeo de celular gravado "deitado" com marca de rotação
            largura, altura = altura, largura
        info.update(largura=largura, altura=altura, codec_video=v.get("codec_name"), pix_fmt=v.get("pix_fmt"))
    return info


def checar_video(video, duracao_alvo=DURACAO_S):
    """Checagens automáticas do vídeo final (spec 03 §3.6), iguais para qualquer ferramenta (FFmpeg, grátis)."""
    import tempfile

    from .percepcao import analisar_video

    info = _sondar(video)
    problemas = []
    if not info["video"]:
        return {"medidas": {}, "problemas": ["o arquivo não tem imagem (só áudio)"], "percepcao": None}
    with tempfile.TemporaryDirectory() as tmp:
        rel = analisar_video(video, tmp, transcrever_audio=False)
    largura, altura, dur = info.get("largura"), info.get("altura"), rel.get("duracao_s") or 0
    som = rel.get("som") if isinstance(rel.get("som"), dict) else {}
    lufs, pico = som.get("lufs_integrado"), som.get("pico_dbfs")
    medidas = {"duracao_s": round(dur, 1), "resolucao": f"{largura}x{altura}" if largura and altura else None,
               "cortes_por_minuto": rel.get("cortes_por_minuto"), "lufs": lufs, "pico_db": pico}
    if (largura, altura) != RESOLUCAO:
        problemas.append(f"resolução {largura}x{altura} (pedido {RESOLUCAO[0]}x{RESOLUCAO[1]}, 9:16)")
    if dur and abs(dur - duracao_alvo) > duracao_alvo * TOLERANCIA_DURACAO:
        problemas.append(f"duração {dur:.0f} s (pedido {duracao_alvo} s ±10%)")
    if not info["audio"] or lufs is None:
        problemas.append("sem áudio medível")
    else:
        if abs(lufs - LUFS_ALVO) > TOLERANCIA_LUFS:
            problemas.append(f"volume {lufs:.1f} LUFS (redes: −14 ±1)")
        if pico is not None and pico > PICO_MAXIMO_DB:
            problemas.append(f"pico {pico:.1f} dB (máx. −1)")
    formato = [(info.get("codec_video"), "h264"), (info.get("pix_fmt"), "yuv420p")]
    if info.get("codec_audio"):  # sem áudio já é outro problema: não conta duas vezes
        formato.append((info["codec_audio"], "aac"))
    if any(atual != certo for atual, certo in formato):
        problemas.append(f"formato {'/'.join(str(a) for a, _ in formato)} (redes aceitam melhor "
                         f"{'/'.join(c for _, c in formato)})")
    pretas = sum(f - i for i, f in rel.get("telas_pretas_s") or [] if _finito(i) and _finito(f))
    congelado = sum(f - i for i, f in rel.get("congelamentos_s") or [] if _finito(i) and _finito(f))
    if pretas > 0.5:
        problemas.append(f"tela preta por {pretas:.1f} s")
    if congelado > 2:
        problemas.append(f"imagem congelada por {congelado:.1f} s")
    rel = {**rel, "arquivo": Path(video).name}  # o juiz não precisa do caminho do PC
    return {"medidas": medidas, "problemas": problemas, "percepcao": rel}


def _contexto(briefing):
    b = BRIEFINGS[briefing]
    return (f"Briefing pedido a todas as ferramentas: vídeo {b['tipo']} sobre \"{b['tema']}\", vertical 9:16, "
            f"cerca de {DURACAO_S} s, narração e legenda em português do Brasil. Avalie quanto o vídeo cumpre esse "
            "briefing. A mesma régua vale para todas as ferramentas; ignore marcas d'água e logotipos.")


def _sem_caminho(texto, video):
    """Erro mascarado e sem o caminho do PC (o relatório vai para a 04b, que é commitada)."""
    from .seguranca import mascarar

    t = mascarar(str(texto))
    for parte in (str(Path(video).resolve()), str(video), str(Path(video).parent)):
        t = t.replace(parte, Path(video).name)
    return " ".join(t.split())[:200]


def avaliar_benchmark(pasta, novo_avaliador, *, aviso=None, checar=checar_video, avaliar=None, refazer=False):
    """Avalia todos os vídeos da pasta; salva e devolve a lista de resultados.

    novo_avaliador(): um Avaliador por briefing (cada um com o próprio teto de custo).
    Vídeo já julgado e não mudou (mesmo hash): reaproveita a nota (não paga de novo); refazer=True julga de novo.
    """
    from .banco import _hash_arquivo

    if avaliar is None:
        from .percepcao import avaliar_video as avaliar
    avisar = aviso or (lambda t: None)
    anteriores = {}
    if not refazer:
        for r in _ler_json(Path(pasta) / "resultados.json").get("resultados") or []:
            if isinstance(r, dict) and r.get("hash") and _finito(r.get("nota_juiz")):
                anteriores[(r.get("briefing"), r.get("ferramenta"), r["hash"])] = r
    resultados, avaliador, atual = [], None, None
    for briefing, ferramenta, video in listar_videos(pasta, aviso=avisar):
        avisar(f"== {briefing} · {ferramenta}")
        hash_video = _hash_arquivo(video)
        manual = _ler_json(video.with_name(f"{ferramenta}.json")) or _ler_json(video.with_suffix(".json"))
        guardado = anteriores.get((briefing, ferramenta, hash_video))
        if guardado:  # mesma nota de antes; os dados anotados podem ter mudado
            resultados.append({**guardado, "video": video.name, "manual": manual})
            avisar("  (já julgado: nota reaproveitada)")
            continue
        if briefing != atual:
            avaliador, atual = novo_avaliador(), briefing
        item = {"briefing": briefing, "ferramenta": ferramenta, "video": video.name, "hash": hash_video,
                # dados anotados pelo nome normalizado ("CapCut.mov" → capcut.json), como o `benchmark dados` grava
                "manual": manual}
        try:
            chk = checar(video)
            item.update(medidas=chk["medidas"], problemas=chk["problemas"])
            percepcao = chk.get("percepcao")
        except Exception as e:  # vídeo corrompido não derruba o benchmark inteiro
            item.update(medidas={}, problemas=[f"não deu para medir: {_sem_caminho(e, video)}"])
            percepcao = None
        try:
            av = avaliar(avaliador, str(video), contexto=_contexto(briefing), percepcao=percepcao)
            item.update(nota_juiz=av.nota, aprovado_juiz=av.aprovado, sem_juiz=av.sem_juiz, juizes=av.juizes,
                        criterios=av.criterios, problemas_juiz=[_sem_caminho(p, video) for p in av.problemas[:5]])
        except Exception as e:
            item.update(nota_juiz=None, sem_juiz=True, problemas_juiz=[_sem_caminho(e, video)])
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


def _celula(texto):
    """Texto seguro numa célula de tabela Markdown: uma linha só, sem barra vertical."""
    return " ".join(str(texto).split()).replace("|", "/") or "—"


def ranking(resultados):
    """Médias por ferramenta, da maior nota do juiz para a menor (sem nota vai para o fim)."""
    por = {}
    for r in resultados:
        por.setdefault(r["ferramenta"], []).append(r)
    linhas = []
    for f, itens in por.items():
        man = [i.get("manual") or {} for i in itens]
        custos = [m["custo_usd"] for m in man if _finito(m.get("custo_usd"))]
        linhas.append({
            "ferramenta": f, "videos": len(itens), "briefings": "".join(sorted({i["briefing"] for i in itens})),
            "com_nota": sum(1 for i in itens if _finito(i.get("nota_juiz"))),
            "nota_juiz": _media(i.get("nota_juiz") for i in itens),
            "nota_diego": _media(m.get("nota_diego") for m in man),
            "custo_usd": round(sum(custos), 3) if custos else None,
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
              "[spec 04](04-benchmark.md)). Mesma régua para todos: checagens do vídeo final da spec 03 §3.6 "
              "(FFmpeg) e o mesmo juiz que assiste com som. Dados de tempo, custo, intervenções e notas pessoais "
              "são anotados à mão.", ""]
    if not resultados:
        return "\n".join(linhas + ["Nenhum vídeo encontrado na pasta do benchmark.", ""])
    linhas += ["## Resultado geral", "",
               "| Ferramenta | Briefings | Nota do juiz (0–100) | Sua nota (0–10) | Custo total (US$) | Tempo médio (min) "
               "| Intervenções | Tentativas | Voz pt-BR | Legenda pt-BR | Problemas automáticos |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in ranking(resultados):
        nota = _fmt(r["nota_juiz"]) + (f" ({r['com_nota']} de {r['videos']})" if r["com_nota"] < r["videos"] else "")
        linhas.append(f"| {_celula(r['ferramenta'])} | {r['briefings']} | {nota} | {_fmt(r['nota_diego'])} | "
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
                                                            if r.get("sem_juiz") else []))
            linhas.append(f"| {_celula(r['ferramenta'])} | {_fmt(r.get('nota_juiz'))} | {_fmt(m.get('duracao_s'), ' s')} | "
                          f"{m.get('resolucao') or '—'} | {_fmt(m.get('lufs'))} | {_celula(probs)} |")
            man = r.get("manual") or {}
            if man.get("observacoes"):
                linhas.append(f"|  | _{_celula(man['observacoes'])}_ | | | | |")
            if man.get("acima_do_teto"):
                linhas.append(f"|  | custo somado acima do teto de US$ {TETO_USD:.2f} | | | | |")
    linhas += ["", "## Como ler", "",
               "- Nota do juiz: régua da spec 03 (0–100), a mesma para todos; a média é só dos vídeos com nota "
               "(\"(2 de 3)\" = um ficou sem juiz). Compare de preferência ferramentas com os 3 briefings.",
               "- Sem nota = nenhum juiz conseguiu assistir: falta chave, bloqueio ou o teto de custo do briefing "
               "(o motivo está na tabela do briefing).",
               "- Exceção à regra do juiz de outra família (D15): só o Gemini assiste vídeo e a régua tem de ser igual "
               "para todos, então ferramentas do Google (e o Studio, se usou Gemini) são julgadas pela própria "
               "família. Suas notas são a conferência desse possível viés.",
               "- Sua nota e as de voz/legenda vêm do `benchmark dados`; são também uma rodada de calibração do juiz.",
               "- Studio: custo, tempo e tentativas somam todas as execuções; cada retomada conta como intervenção.",
               "- Problemas automáticos (spec 03 §3.6): resolução 1080x1920, duração 30 s ±10%, volume −14 LUFS ±1, "
               "pico ≤ −1 dB, formato h264/aac/yuv420p, telas pretas e imagem congelada.", ""]
    return "\n".join(linhas)

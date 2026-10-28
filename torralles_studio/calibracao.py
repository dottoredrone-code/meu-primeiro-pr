"""Calibração dos juízes (K14, spec 03 §7 e spec 09): suas notas × notas do juiz nas mesmas referências.

Você dá nota de 0 a 10 aos 4 critérios de potencial (gancho, fluxo, valor, tendência) de vídeos já analisados com
`analisar-referencia`. O juiz deu nota de 0 a 100; aqui ela vira 0 a 10 para comparar.
- juiz **mais generoso** que você (média ≥ +1) → subir a nota mínima;
- juiz **mais rígido** (média ≤ −1) → descer a nota mínima ou ajustar os pesos;
- juiz que **discorda muito** (a diferença varia mais de 2 pontos em torno da média: ora dá mais, ora menos) →
  ajustar as âncoras ou trocar o juiz. Diferença constante não é discordância: é viés, e se corrige na nota mínima.
A recomendação de nota mínima sai na escala do config (0–100: 1 ponto de 0–10 = 10 pontos).
O juiz calibrado aqui é o que analisa as referências (cadeia `juiz_video`). Os juízes que aprovam as peças em
produção são de outra família (D15): use o resultado como indicação para eles, não como regra automática.
As âncoras aprovadas ficam em `config/ancoras.toml` e entram no prompt da análise; reanalise e calibre de novo.
"""

import json
import math
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from .referencias import CRITERIOS, arquivo_da_analise, identificar

DIVERGENCIA_MAXIMA = 2.0  # spec 03: mesma tolerância entre juízes
VIES = 1.0
MINIMO_NOTAS = 3


def registrar_notas(pasta, video, categoria, notas):
    """Guarda suas notas (0–10 por critério) na análise do vídeo; devolve o caminho do arquivo."""
    if not notas:
        raise ValueError("dê nota a pelo menos um critério (--gancho, --fluxo, --valor, --tendencia)")
    for c, n in notas.items():
        if c not in CRITERIOS:
            raise ValueError(f"critério desconhecido: {c}")
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not 0 <= n <= 10:
            raise ValueError(f"nota de {c} precisa ser de 0 a 10")
    _, ident, _ = identificar(video)
    arq = arquivo_da_analise(pasta, categoria, ident)
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = None
    if not isinstance(dados, dict):
        raise ValueError(f"esse vídeo ainda não foi analisado na categoria {categoria}: rode analisar-referencia "
                         "primeiro") from None
    anteriores = dados.get("notas_diego") if isinstance(dados.get("notas_diego"), dict) else {}
    dados["notas_diego"] = {**anteriores, **{c: float(n) for c, n in notas.items()}}
    dados["notas_diego_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return arq


def _pares(analises):
    """(provedor, critério, nota do juiz 0–10, sua nota 0–10) de cada critério com as duas notas."""
    for a in analises:
        if not isinstance(a, dict):
            continue
        suas = a.get("notas_diego") if isinstance(a.get("notas_diego"), dict) else {}
        potencial = a.get("potencial") if isinstance(a.get("potencial"), dict) else {}
        for c in CRITERIOS:
            item = potencial.get(c) if isinstance(potencial.get(c), dict) else {}
            juiz, sua = item.get("nota"), suas.get(c)
            if all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in (juiz, sua)):
                yield a.get("provedor") or "?", c, juiz / 10, float(sua)


def _resumo(diferencas):
    media = sum(diferencas) / len(diferencas)
    return {"n": len(diferencas), "media_diferenca": round(media, 2),
            "media_absoluta": round(sum(abs(d) for d in diferencas) / len(diferencas), 2),
            "dispersao": round(sum(abs(d - media) for d in diferencas) / len(diferencas), 2),
            "maior": round(max(diferencas, key=abs), 2)}


def _pontos_0_100(diferenca):
    """Diferença em 0–10 → pontos da nota mínima do config (0–100), arredondando 0,5 para cima."""
    return int(math.floor(abs(diferenca) * 10 + 0.5))


def _veredito(r):
    if r["dispersao"] > DIVERGENCIA_MAXIMA:
        return "discorda muito"
    if r["media_diferenca"] >= VIES:
        return "mais generoso"
    if r["media_diferenca"] <= -VIES:
        return "mais rígido"
    return "alinhado"


def calibrar(analises, minimo=MINIMO_NOTAS):
    """Compara as notas; ValueError se houver menos de `minimo` vídeos com as duas notas."""
    pares = list(_pares(analises))
    videos = {a.get("id") for a in analises if any(True for _ in _pares([a]))}
    if len(videos) < minimo:
        raise ValueError(f"precisa de pelo menos {minimo} vídeos com a sua nota (tem {len(videos)}); "
                         "use nota-referencia")
    geral = _resumo([j - s for _, _, j, s in pares])
    por_criterio = {c: _resumo(d) for c in CRITERIOS if (d := [j - s for _, k, j, s in pares if k == c])}
    por_juiz = {}
    for p in sorted({p for p, *_ in pares}):
        r = _resumo([j - s for q, _, j, s in pares if q == p])
        por_juiz[p] = {**r, "veredito": _veredito(r)}
    recomendacoes = []
    for p, r in por_juiz.items():
        v = r["veredito"]
        if v == "mais generoso":
            recomendacoes.append(f"{p} dá em média {r['media_diferenca']:+.1f} ponto(s) a mais que você (0–10): suba a "
                                 f"nota mínima em {_pontos_0_100(r['media_diferenca'])} pontos na escala do config "
                                 f"(ex.: 70 → {70 + _pontos_0_100(r['media_diferenca'])})")
        elif v == "mais rígido":
            recomendacoes.append(f"{p} dá em média {abs(r['media_diferenca']):.1f} ponto(s) a menos que você (0–10): "
                                 f"desça a nota mínima em {_pontos_0_100(r['media_diferenca'])} pontos na escala do "
                                 f"config (ex.: 70 → {70 - _pontos_0_100(r['media_diferenca'])}) ou ajuste os pesos")
        elif v == "discorda muito":
            recomendacoes.append(f"{p} discorda de você de forma irregular (ora mais, ora menos; variação "
                                 f"{r['dispersao']:.1f}): ajuste as âncoras ou tire esse juiz da cadeia")
    for c, r in por_criterio.items():
        if r["dispersao"] > DIVERGENCIA_MAXIMA:
            recomendacoes.append(f"critério {c}: notas irregulares (variação {r['dispersao']:.1f}); reescreva a "
                                 "âncora dele em config/ancoras.toml e reanalise")
    return {"videos": len(videos), "geral": {**geral, "veredito": _veredito(geral)}, "por_criterio": por_criterio,
            "por_juiz": por_juiz, "recomendacoes": recomendacoes or ["juiz alinhado com você: nada a ajustar"]}


def carregar_ancoras(caminho, categoria):
    """Âncoras aprovadas da categoria ({critério: texto}); vazio se não houver arquivo ou seção."""
    try:
        dados = tomllib.loads(Path(caminho).read_text(encoding="utf-8")).get(str(categoria), {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    if not isinstance(dados, dict):
        return {}
    return {c: " ".join(str(dados[c]).split())[:400] for c in CRITERIOS if str(dados.get(c, "")).strip()}

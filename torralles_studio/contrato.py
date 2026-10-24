"""Contrato Torralles Ops → Studio (K28, spec 08, D13/D14): pedido e resultado em JSON.

validar_pedido() confere o pedido e devolve (pedido_normalizado, problemas). O mesmo contrato serve para o
HTTP local, para o MCP (Hermes) e para outros sistemas: o Studio não depende do Ops.
"""

import re

VERSAO = "1.0"
CAMPOS_BRIEFING = ("tipo_peca", "conceito_visual", "paleta_cores", "formato_dimensoes", "texto_overlay",
                   "ferramenta_sugerida")
ENTREGAVEIS = ("imagem", "carrossel", "video_curto", "story")
SUPORTADOS = ("imagem", "video_curto", "story")  # carrossel vem depois (várias imagens coerentes, K17)
MODOS = ("economico", "misto", "premium")
STATUS = ("na_fila", "produzindo", "avaliando", "aguardando_aprovacao", "concluido", "falhou", "cancelado")
TETO_USD = 1.50  # D20: nunca acima do teto do Studio
_PLACEHOLDER = re.compile(r"^\s*(\.\.\.|…|-|tbd|todo|a definir|<[^>]*>|lorem ipsum.*)\s*$", re.I)


def entregavel_do_tipo(tipo_peca):
    """Deriva o entregável do tipo de peça do Ops ("post estático" → imagem, "reels" → vídeo curto…)."""
    t = str(tipo_peca or "").lower()
    if any(p in t for p in ("story", "stories")):
        return "story"
    if any(p in t for p in ("reels", "reel", "vídeo", "video", "shorts", "tiktok")):
        return "video_curto"
    if "carrossel" in t or "carousel" in t:
        return "carrossel"
    return "imagem"


def proporcao_do_formato(formato, entregavel):
    """'1080x1920' → '9:16'; '1:1' → '1:1'; sem formato claro, o padrão do entregável."""
    texto = str(formato or "").lower().replace(" ", "")
    m = re.search(r"(\d{3,4})[x×:](\d{3,4})", texto) or re.search(r"(\d{1,2}):(\d{1,2})", texto)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        r = w / h if h else 0
        for nome, alvo in (("9:16", 9 / 16), ("4:5", 4 / 5), ("1:1", 1.0), ("16:9", 16 / 9)):
            if abs(r - alvo) < 0.04:
                return nome
        return None
    return "9:16" if entregavel in ("video_curto", "story") else "1:1"


def _texto(valor):
    return isinstance(valor, str) and valor.strip() and not _PLACEHOLDER.match(valor)


def validar_pedido(dados):
    """(pedido normalizado, problemas). Problema = pedido recusado; a mensagem diz o campo e o porquê."""
    problemas = []
    if not isinstance(dados, dict):
        return None, ["o pedido precisa ser um objeto JSON"]
    versao = str(dados.get("versao_contrato") or VERSAO)
    if versao.split(".")[0] != VERSAO.split(".")[0]:
        problemas.append(f"versao_contrato {versao!r} não suportada (use {VERSAO})")
    briefing = dados.get("briefing")
    if not isinstance(briefing, dict):
        return None, problemas + ["falta o objeto 'briefing'"]
    for campo in CAMPOS_BRIEFING:
        if not _texto(briefing.get(campo)):
            problemas.append(f"briefing.{campo} vazio ou provisório")
    entregaveis = dados.get("entregaveis") or [entregavel_do_tipo(briefing.get("tipo_peca"))]
    if not isinstance(entregaveis, list) or not entregaveis:
        problemas.append("entregaveis precisa ser uma lista")
        entregaveis = []
    for e in entregaveis:
        if e not in ENTREGAVEIS:
            problemas.append(f"entregável desconhecido: {e!r} (use {', '.join(ENTREGAVEIS)})")
        elif e not in SUPORTADOS:
            problemas.append(f"entregável {e!r} ainda não é produzido pelo Studio (hoje: {', '.join(SUPORTADOS)})")
    principal = entregaveis[0] if entregaveis else "imagem"
    proporcao = proporcao_do_formato(briefing.get("formato_dimensoes"), principal)
    if proporcao is None:
        problemas.append(f"briefing.formato_dimensoes {briefing.get('formato_dimensoes')!r} não é 9:16, 4:5, 1:1 "
                         "nem 16:9")
    fatos = dados.get("fatos_travados") or {}
    if not isinstance(fatos, dict) or not all(isinstance(v, (str, int, float)) for v in fatos.values()):
        problemas.append("fatos_travados precisa ser um objeto com textos ou números")
        fatos = {}
    orcamento = dados.get("orcamento") or {}
    modo = orcamento.get("modo", "economico")
    if modo not in MODOS:
        problemas.append(f"orcamento.modo {modo!r} inválido (use {', '.join(MODOS)})")
    try:
        teto = min(float(orcamento.get("custo_maximo_usd", TETO_USD)), TETO_USD)
        if teto <= 0:
            raise ValueError
    except (TypeError, ValueError):
        problemas.append("orcamento.custo_maximo_usd precisa ser um número maior que zero")
        teto = TETO_USD
    contexto = dados.get("contexto_campanha") if isinstance(dados.get("contexto_campanha"), dict) else {}
    origem = dados.get("origem") if isinstance(dados.get("origem"), dict) else {}
    perfil = dados.get("perfil")
    if perfil is not None and not (isinstance(perfil, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", perfil)):
        problemas.append("perfil precisa ser o id de um perfil do Studio (letras minúsculas, números e hífen)")
    if problemas:
        return None, problemas
    return {
        "versao_contrato": VERSAO, "origem": origem, "perfil": perfil,
        "briefing": {c: str(briefing[c]).strip() for c in CAMPOS_BRIEFING},
        "contexto_campanha": {k: str(v) for k, v in contexto.items() if isinstance(v, (str, int, float))},
        "fatos_travados": {k: str(v) for k, v in fatos.items()},
        "entregaveis": entregaveis, "entregavel": principal, "proporcao": proporcao,
        "orcamento": {"custo_maximo_usd": round(teto, 2), "modo": modo},
        "duracao_s": int(dados.get("duracao_s") or (15 if principal == "story" else 30)),
        "aprovacao_humana": bool(dados.get("aprovacao_humana", True)),
    }, []


def tema_do_pedido(pedido):
    """Texto-base para o roteiro/imagem a partir do briefing e da campanha (sem inventar nada)."""
    b, c = pedido["briefing"], pedido["contexto_campanha"]
    partes = [b["conceito_visual"]]
    if c.get("objetivo"):
        partes.append(f"Objetivo: {c['objetivo']}")
    if c.get("publico_alvo"):
        partes.append(f"Público: {c['publico_alvo']}")
    if c.get("copy_principal"):
        partes.append(f"Mensagem: {c['copy_principal']}")
    if c.get("cta"):
        partes.append(f"Chamada final: {c['cta']}")
    partes.append(f"Texto obrigatório na tela: {b['texto_overlay']}")
    partes.append(f"Paleta: {b['paleta_cores']}")
    return ". ".join(partes)


def estimativa_custo(pedido):
    """Estimativa simples (US$) para a resposta imediata; o teto real é o do orçamento."""
    base = {"imagem": 0.08, "story": 0.45, "video_curto": 0.6}.get(pedido["entregavel"], 0.3)
    return round(min(base, pedido["orcamento"]["custo_maximo_usd"]), 2)

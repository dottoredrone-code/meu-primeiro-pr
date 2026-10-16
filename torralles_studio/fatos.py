"""Fatos travados (D15): preço, links, percentuais e nomes do briefing não podem ser alterados nem inventados.

Todo texto gerado (roteiro, legenda, texto sobre a imagem) passa por checar_fatos(). Qualquer preço, link
ou percentual que não esteja nos fatos do briefing reprova a peça (eliminatório).
"""

import re
import unicodedata

# Ordem importa: milhar com ponto (1.249,00) → decimal com vírgula (49,90) → decimal com ponto/inteiro (24.49, 22).
_PRECO = re.compile(r"(R\$|US\$|\$|€)\s*(\d+(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}|\d+(?:\.\d{1,2})?)", re.I)
_FAIXA_PRECO = re.compile(r"(R\$|US\$|\$|€)\s*\d+(?:[.,]\d{1,2})?\s*(?:a|-|até|ou)\s*\d+", re.I)
_LINK = re.compile(r"(?:https?://|www\.)[^\s)\]]+|(?<![\w.])(?:[a-z0-9-]+\.)+(?:la|ly|com|com\.br|net|br|io|me)/[^\s)\]]*", re.I)
_PERCENTUAL = re.compile(r"\d+(?:[.,]\d+)?\s?%")


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def _valor_preco(moeda, numero):
    """Normaliza 'R$ 1.234,56' / '$24.49' para (moeda, centavos)."""
    moeda = moeda.upper().replace("US$", "$")
    n = numero.replace(" ", "")
    if "," in n:                       # padrão brasileiro: 1.234,56
        n = n.replace(".", "").replace(",", ".")
    elif n.count(".") >= 1 and all(len(g) == 3 for g in n.split(".")[1:]):
        n = n.replace(".", "")         # 1.234 / 1.234.567 (milhar sem centavos)
    return moeda, round(float(n) * 100)


def _precos(texto):
    return {_valor_preco(m, n) for m, n in _PRECO.findall(texto)}


def _links(texto):
    return {l.rstrip(".,;!?").lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
            for l in _LINK.findall(texto)}


def _percentuais(texto):
    return {p.replace(" ", "").replace(",", ".") for p in _PERCENTUAL.findall(texto)}


def checar_fatos(texto, fatos):
    """Devolve a lista de problemas (vazia = ok).

    fatos: dict do briefing, ex. {"preco": "R$ 49,90", "link": "loja.com/x", "nome_produto": "...",
           "desconto": "20%", "obrigatorios": ["nome_produto"]}
    """
    if not texto or not fatos:
        return []
    problemas = []
    valores = [str(v) for k, v in fatos.items() if k != "obrigatorios" and v]
    referencia = " ".join(valores)

    if _FAIXA_PRECO.search(texto):
        problemas.append("faixa de preço inventada (o preço do briefing é fixo)")
    precos_ok = _precos(referencia)
    for preco in sorted(_precos(texto) - precos_ok):
        problemas.append(f"preço não autorizado no texto: {preco[0]} {preco[1] / 100:.2f}")

    links_ok = _links(referencia)
    for link in sorted(_links(texto) - links_ok):
        problemas.append(f"link não autorizado no texto: {link}")

    perc_ok = _percentuais(referencia)
    for perc in sorted(_percentuais(texto) - perc_ok):
        problemas.append(f"percentual não autorizado no texto: {perc}")

    texto_norm = _sem_acento(texto)
    for chave in fatos.get("obrigatorios", []):
        valor = fatos.get(chave)
        if valor and _sem_acento(str(valor)) not in texto_norm:
            problemas.append(f"fato obrigatório ausente ou alterado: {chave} = {valor!r}")
    return problemas

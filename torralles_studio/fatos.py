"""Fatos travados (D15): preço, links, percentuais e nomes do briefing não podem ser alterados nem inventados.

Todo texto gerado (roteiro, legenda, texto sobre a imagem) passa por checar_fatos(). Qualquer preço, link
ou percentual que não esteja nos fatos do briefing reprova a peça (eliminatório).
"""

import re
import unicodedata

# Número de preço. Ordem importa: milhar com ponto (1.249,00) → decimal com vírgula (49,90) → ponto/inteiro.
_NUM = r"(\d+(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}|\d+(?:\.\d{1,2})?)"
_MOEDA_ANTES = r"(R\$|US\$|\$|€|BRL|USD|EUR)"
_MOEDA_DEPOIS = r"(reais|real|d[oó]lares|d[oó]lar|euros?)"
_PRECO = re.compile(rf"{_MOEDA_ANTES}\s*{_NUM}(?!\d)|(?<![\w.,]){_NUM}\s*{_MOEDA_DEPOIS}\b", re.I)
# Faixa: "R$ 22 a 28", "R$ 22–R$ 28". Só conta quando o 2º valor também tem moeda ou fecha a frase
# ("até 31/10", "a 50 metros", "até 100 unidades" não são faixa). O 2º valor ainda precisa ser maior.
_FAIXA_PRECO = re.compile(
    rf"{_MOEDA_ANTES}\s*{_NUM}\s*(?:a|-|–|até)\s*"
    rf"(?:{_MOEDA_ANTES}\s*{_NUM}|{_NUM}(?=\s*(?:$|[.,;:!?)]|reais\b|e\b|ou\b)))",
    re.I,
)
_LINK = re.compile(
    r"\b[a-z][a-z0-9+.-]*://[^\s)\]]+"                                       # qualquer esquema
    r"|\bwww\.[^\s)\]]+"
    r"|(?<![\w.@,-])[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*\.([a-z]{2,})(?![\w-])(/[^\s)\]]*)?",  # domínio
    re.I,
)
# Domínio sem caminho só conta com terminação comum ("Sr.Silva", "foto.jpg", "Node.js" não são links).
_TLD_COMUNS = {"com", "br", "net", "org", "io", "me", "ly", "la", "co", "app", "shop", "store", "site",
               "online", "xyz", "info", "biz", "tv", "ai", "link", "page", "pt", "us", "gl", "gg", "dev"}
# Com caminho, qualquer terminação conta, menos extensões de arquivo e linguagem.
_EXTENSOES = {"js", "ts", "py", "jpg", "jpeg", "png", "gif", "webp", "pdf", "mp4", "mp3", "wav", "txt",
              "doc", "docx", "csv", "json", "html", "css", "zip"}
_NAO_SAO_LINKS = {"asp.net"}
_PERCENTUAL = re.compile(r"(\d+(?:[.,]\d+)?)\s?%")
_CAMPOS_PRECO = ("preco", "preço", "valor", "preco_promocional")
_MOEDAS = {"R$": "R$", "BRL": "R$", "REAIS": "R$", "REAL": "R$", "US$": "$", "$": "$", "USD": "$",
           "DOLAR": "$", "DOLARES": "$", "€": "€", "EUR": "€", "EURO": "€", "EUROS": "€"}


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def _centavos(numero):
    n = numero.replace(" ", "")
    if "," in n:                       # padrão brasileiro: 1.234,56
        n = n.replace(".", "").replace(",", ".")
    elif n.count(".") >= 1 and all(len(g) == 3 for g in n.split(".")[1:]):
        n = n.replace(".", "")         # 1.234 / 1.234.567 (milhar sem centavos)
    return round(float(n) * 100)


def _valor_preco(moeda, numero):
    """Normaliza 'R$ 1.234,56' / '$24.49' / '39,90 reais' para (moeda, centavos)."""
    return _MOEDAS.get(_sem_acento(moeda).upper(), moeda.upper()), _centavos(numero)


def _precos(texto):
    achados = set()
    for m1, n1, n2, m2 in _PRECO.findall(texto):
        achados.add(_valor_preco(m1, n1) if m1 else _valor_preco(m2, n2))
    return achados


def _precos_dos_fatos(fatos, referencia):
    """Preços autorizados. Preço do briefing sem moeda ("49,90" ou 49.9) vale como R$."""
    precos = _precos(referencia)
    for chave in _CAMPOS_PRECO:
        valor = fatos.get(chave)
        if valor is None or valor == "" or isinstance(valor, bool):
            continue
        if isinstance(valor, (int, float)):
            precos.add(("R$", round(valor * 100)))
        elif not _precos(str(valor)) and re.fullmatch(_NUM, str(valor).strip()):
            precos.add(("R$", _centavos(str(valor).strip())))
    return precos


def _normalizar_link(link):
    link = link.rstrip(".,;:!?").lower()
    link = re.sub(r"^[a-z][a-z0-9+.-]*://", "", link)
    return link.removeprefix("www.").rstrip("/")


def _links(texto):
    links = set()
    for m in _LINK.finditer(texto):
        tld, caminho = (m.group(1) or "").lower(), m.group(2)
        if tld and (tld in _EXTENSOES or (not caminho and tld not in _TLD_COMUNS)):
            continue
        link = _normalizar_link(m.group(0))
        if link not in _NAO_SAO_LINKS:
            links.add(link)
    return links


def _link_autorizado(link, permitidos):
    """Mesmo link, ou só o domínio de um link autorizado (citar "loja.com" quando o fato é "loja.com/p/1")."""
    if link in permitidos:
        return True
    return "/" not in link and any(p.split("/", 1)[0] == link for p in permitidos)


def _percentuais(texto):
    return {float(p.replace(",", ".")) for p in _PERCENTUAL.findall(texto)}


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

    for m in _FAIXA_PRECO.finditer(texto):
        if _centavos(m.group(4) or m.group(5)) > _centavos(m.group(2)):
            problemas.append("faixa de preço inventada (o preço do briefing é fixo)")
            break
    precos_ok = _precos_dos_fatos(fatos, referencia)
    for preco in sorted(_precos(texto) - precos_ok):
        problemas.append(f"preço não autorizado no texto: {preco[0]} {preco[1] / 100:.2f}")

    links_ok = _links(referencia)
    for link in sorted(_links(texto)):
        if not _link_autorizado(link, links_ok):
            problemas.append(f"link não autorizado no texto: {link}")

    perc_ok = _percentuais(referencia)
    for perc in sorted(_percentuais(texto) - perc_ok):
        problemas.append(f"percentual não autorizado no texto: {perc:g}%")

    texto_norm = _sem_acento(texto)
    for chave in fatos.get("obrigatorios", []):
        valor = fatos.get(chave)
        if valor and _sem_acento(str(valor)) not in texto_norm:
            problemas.append(f"fato obrigatório ausente ou alterado: {chave} = {valor!r}")
    return problemas

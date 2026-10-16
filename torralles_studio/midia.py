"""Mídia em 3 camadas (K20, D18, spec 11): acervo local → APIs gratuitas → (geração por IA, outros cartões).

buscar_midia() devolve um ativo da biblioteca (com licença conferida e créditos):
1. Procura na biblioteca (acervo local) por etiquetas — grátis e offline.
2. Se não houver, busca nas APIs gratuitas pela cadeia `midia_<tipo>` (Pexels, Pixabay, Openverse, Freesound),
   descarta licenças bloqueadas, baixa só de domínios permitidos (rede.baixar) e guarda na biblioteca.
"""

import re
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from .biblioteca import TIPOS, ErroLicenca, conferir_licenca
from .rede import ErroProvedor, baixar
from .roteador import TodosFalharam

_PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "e", "em", "com", "para", "um", "uma", "o", "a", "os", "as",
                    "no", "na", "nos", "nas", "por", "pelo", "pela", "pelos", "pelas", "ao", "aos", "ou",
                    "the", "of", "and", "in", "on", "with"}
_EXTENSAO = {"imagem": ".jpg", "video": ".mp4", "audio": ".mp3"}


class SemMidia(Exception):
    """Nenhuma mídia com licença aceita foi encontrada (nem no acervo, nem nas APIs)."""


def etiquetas_da_consulta(consulta):
    t = "".join(c for c in unicodedata.normalize("NFD", consulta.lower()) if unicodedata.category(c) != "Mn")
    return [p for p in re.findall(r"[a-z0-9]+", t) if p not in _PALAVRAS_VAZIAS and len(p) > 1]


def candidatos_aceitos(candidatos):
    """Só candidatos com licença aceita (spec 11), link https e, se exigir crédito, autor."""
    aceitos = []
    for c in candidatos or []:
        try:
            codigo, regras = conferir_licenca(c.get("licenca"))
        except ErroLicenca:
            continue
        if regras["credito"] and not str(c.get("autor") or "").strip():
            continue
        if urlparse(str(c.get("url", ""))).scheme != "https":
            continue
        aceitos.append({**c, "licenca": codigo})
    return aceitos


def _validar_candidatos(candidatos):
    aceitos = candidatos_aceitos(candidatos)
    if not aceitos:
        raise ValueError("nenhum resultado com licença aceita")  # o roteador passa ao próximo provedor
    return aceitos


def _extensao(url, tipo):
    """Extensão só se combinar com o tipo pedido (.svg, .php… viram a padrão do tipo)."""
    ext = Path(urlparse(url).path).suffix.lower()
    return ext if ext in TIPOS[tipo] else _EXTENSAO[tipo]


def _parece_pagina(dados):
    """Página de erro (HTML) salva como mídia não entra na biblioteca."""
    inicio = dados[:64].lstrip().lower()
    return inicio.startswith((b"<!doctype", b"<html", b"<?xml", b"{"))


def buscar_midia(roteador, biblioteca, consulta, tipo="imagem", *, perfil=None, proporcao=None, max_resultados=5,
                 usar_acervo=True, baixar_arquivo=baixar):
    """Devolve um ativo (dict da biblioteca) com `camada` = "acervo" ou "api". Lança SemMidia se não achar."""
    etiquetas = etiquetas_da_consulta(consulta)
    if usar_acervo and etiquetas:
        achados = biblioteca.buscar(etiquetas, tipo=tipo, perfil=perfil, limite=1)
        if achados:
            return {**achados[0], "camada": "acervo"}

    falhas, tentados = [], set()
    with tempfile.TemporaryDirectory() as pasta:
        while True:  # se nenhum arquivo de uma fonte baixar, tenta a próxima fonte da cadeia
            try:
                r = roteador.executar(f"midia_{tipo}", consulta=consulta, tipo=tipo, max_resultados=max_resultados,
                                      proporcao=proporcao, validar=_validar_candidatos, excluir=tentados,
                                      usar_cache=False)
            except (TodosFalharam, KeyError) as e:
                if not falhas:
                    raise SemMidia(f"nenhuma {tipo} com licença aceita para {consulta!r}: {e}") from None
                break
            tentados.add(r.provedor)
            for i, c in enumerate(r.valor):
                try:
                    dados = baixar_arquivo(c["url"])
                except ErroProvedor as e:  # domínio fora da lista, grande demais, link vencido…
                    falhas.append(f"{c.get('fonte')}: {e}")
                    continue
                if _parece_pagina(dados):
                    falhas.append(f"{c.get('fonte')}: o link devolveu uma página, não um arquivo")
                    continue
                arquivo = Path(pasta) / f"midia_{len(falhas)}_{i}{_extensao(c['url'], tipo)}"
                arquivo.write_bytes(dados)
                try:
                    ativo = biblioteca.adicionar(
                        arquivo, c["licenca"], c.get("fonte") or r.provedor, autor=c.get("autor"),
                        link=c.get("link"), titulo=c.get("titulo") or consulta,
                        tags=etiquetas + list(c.get("tags") or [])[:10], perfil=perfil, provedor=r.provedor,
                        parametros={"consulta": consulta, "proporcao": proporcao, "largura": c.get("largura"),
                                    "altura": c.get("altura"), "duracao": c.get("duracao")})
                except ErroLicenca as e:  # dado incompleto da fonte (ex.: link inválido): tenta o próximo
                    falhas.append(f"{c.get('fonte')}: {e}")
                    continue
                return {**ativo, "camada": "api"}
    raise SemMidia(f"nenhum arquivo pôde ser baixado para {consulta!r}: " + "; ".join(falhas[:3]))

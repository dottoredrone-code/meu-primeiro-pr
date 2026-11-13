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


def _raiz(palavra):
    return palavra[:-1] if len(palavra) > 3 and palavra.endswith("s") else palavra  # "cups" ~ "cup"


def relevancia(candidato, consulta):
    """Quantas palavras da consulta aparecem no título, na descrição ou nas etiquetas do candidato.

    Os bancos devolvem foto de evento policial para "green tea moderation": 0 = não combina com a cena."""
    pedidas = {_raiz(p) for p in etiquetas_da_consulta(consulta)}
    texto = " ".join([str(candidato.get("titulo") or ""), *map(str, candidato.get("tags") or [])])
    return len(pedidas & {_raiz(p) for p in etiquetas_da_consulta(texto)})


def _relevancia_no_acervo(ativo, consulta):
    """Relevância de um ativo guardado. Etiquetas postas à mão no acervo valem; as de uma busca automática
    (parametros com "consulta") herdaram palavras da busca e não contam: vale o título e a medida ao baixar.
    Do acervo só volta o que combina (o último recurso, foto fora do tema, vem sempre da API)."""
    parametros = ativo.get("parametros") or {}
    if "consulta" not in parametros:
        return relevancia({"titulo": ativo.get("titulo"), "tags": ativo.get("tags")}, consulta)
    # palavras que a própria fonte deu (título e etiquetas originais), medidas contra a busca ATUAL. Fonte sem
    # título (Pixabay, vídeo do Pexels) é guardada com a busca como título: esse título não conta.
    if "titulo_fonte" in parametros:
        titulo = parametros["titulo_fonte"]
    else:
        titulo = None if ativo.get("titulo") == parametros.get("consulta") else ativo.get("titulo")
    return relevancia({"titulo": titulo, "tags": parametros.get("palavras_fonte") or []}, consulta)


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
    """Extensão do link se combinar com o tipo; sem extensão, a padrão; extensão de outro tipo (.svg) → None."""
    ext = Path(urlparse(url).path).suffix.lower()
    if not ext:
        return _EXTENSAO[tipo]
    return ext if ext in TIPOS[tipo] else None


def _parece_pagina(dados):
    """Página de erro (HTML) salva como mídia não entra na biblioteca."""
    inicio = dados[:64].removeprefix(b"\xef\xbb\xbf").lstrip().lower()
    return inicio.startswith((b"<!doctype", b"<html", b"<?xml", b"<svg", b"{"))


def buscar_midia(roteador, biblioteca, consulta, tipo="imagem", *, perfil=None, proporcao=None, max_resultados=5,
                 usar_acervo=True, baixar_arquivo=baixar, comercial=True, minimo_relevancia=0):
    """Devolve um ativo (dict da biblioteca) com `camada` = "acervo" ou "api". Lança SemMidia se não achar.

    Os candidatos que mais combinam com a consulta (título e etiquetas) vêm primeiro; com minimo_relevancia,
    os que combinam menos que isso nem são baixados.

    comercial: projeto monetizado (padrão, o mais seguro). Fontes com `somente_nao_comercial` no config
    (API do Freesound, D22) só entram quando comercial=False (perfil com `comercial = false`).
    """
    etiquetas = etiquetas_da_consulta(consulta)
    if usar_acervo and etiquetas:
        achados = biblioteca.buscar(etiquetas, tipo=tipo, perfil=perfil, limite=10)
        # As etiquetas guardadas incluem palavras de buscas antigas: o que vale é o título e a relevância medida
        # ao baixar (foto fora do tema aceita como último recurso não volta por aqui).
        achados = [a for a in achados if _relevancia_no_acervo(a, consulta) >= max(1, minimo_relevancia)]
        if achados:
            return {**achados[0], "camada": "acervo"}

    falhas, tentados = [], set()
    bloqueados = {n for n, p in roteador.provedores.items() if comercial and p.cfg.get("somente_nao_comercial")}
    with tempfile.TemporaryDirectory() as pasta:
        while True:  # se nenhum arquivo de uma fonte baixar, tenta a próxima fonte da cadeia
            try:
                r = roteador.executar(f"midia_{tipo}", consulta=consulta, tipo=tipo, max_resultados=max_resultados,
                                      proporcao=proporcao, validar=_validar_candidatos, excluir=tentados | bloqueados,
                                      usar_cache=False)
            except (TodosFalharam, KeyError) as e:
                if not falhas:
                    raise SemMidia(f"nenhuma {tipo} com licença aceita para {consulta!r}: {e}") from None
                break
            tentados.add(r.provedor)
            tentados.update(t.provedor for t in r.tentativas if t.status == "falhou")  # não chama de novo
            candidatos = sorted(r.valor, key=lambda c: -relevancia(c, consulta))  # estável: empate mantém a ordem
            fora = [c for c in candidatos if relevancia(c, consulta) < minimo_relevancia]
            if fora:
                falhas.append(f"{len(fora)} resultado(s) de {r.provedor} não combinam com {consulta!r}")
            for i, c in enumerate(c for c in candidatos if relevancia(c, consulta) >= minimo_relevancia):
                extensao = _extensao(c["url"], tipo)
                if extensao is None:
                    falhas.append(f"{c.get('fonte')}: formato que não é {tipo} ({Path(urlparse(c['url']).path).suffix})")
                    continue
                try:
                    dados = baixar_arquivo(c["url"])
                except (ErroProvedor, ValueError) as e:  # domínio fora da lista, link vencido ou malformado…
                    falhas.append(f"{c.get('fonte')}: {e}")
                    continue
                if _parece_pagina(dados):
                    falhas.append(f"{c.get('fonte')}: o link devolveu uma página, não um arquivo")
                    continue
                arquivo = Path(pasta) / f"midia_{len(falhas)}_{i}{extensao}"
                arquivo.write_bytes(dados)
                try:
                    ativo = biblioteca.adicionar(
                        arquivo, c["licenca"], c.get("fonte") or r.provedor, autor=c.get("autor"),
                        link=c.get("link"), titulo=c.get("titulo") or consulta,
                        # foto que não combina com a busca não ganha as palavras dela (não volta pelo acervo)
                        tags=(etiquetas if relevancia(c, consulta) else []) + list(c.get("tags") or [])[:10],
                        perfil=perfil, provedor=r.provedor,
                        parametros={"consulta": consulta, "proporcao": proporcao, "largura": c.get("largura"),
                                    "altura": c.get("altura"), "duracao": c.get("duracao"),
                                    "relevancia": relevancia(c, consulta),
                                    "palavras_fonte": [str(t) for t in (c.get("tags") or [])][:10],
                                    "titulo_fonte": c.get("titulo")})
                except ErroLicenca as e:  # dado incompleto da fonte (ex.: link inválido): tenta o próximo
                    falhas.append(f"{c.get('fonte')}: {e}")
                    continue
                return {**ativo, "camada": "api"}
    raise SemMidia(f"nenhum arquivo serviu para {consulta!r}: " + "; ".join(falhas[:3]))

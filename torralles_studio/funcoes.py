"""Funções do app, cada uma usando a cadeia de fallback da sua tarefa."""

import json
import re
from pathlib import Path

from .roteador import Resultado, TodosFalharam

SISTEMA_ROTEIRO = (
    "Você é roteirista de vídeos curtos para redes sociais. Responda APENAS com JSON válido, sem texto extra, "
    'no formato: {"titulo": str, "cenas": [{"narracao": str, "prompt_imagem": str, '
    '"prompt_movimento": str, "duracao": int}]}. '
    "Narração em português do Brasil; prompts de imagem e movimento em inglês, bem descritivos."
)


def extrair_json(texto):
    """Lê JSON mesmo quando o modelo o envolve em ```json ... ``` ou texto extra."""
    bloco = re.search(r"```(?:json)?\s*(.*?)```", texto, re.S)
    if bloco:
        texto = bloco.group(1)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim == -1:
        raise ValueError("resposta sem JSON")
    try:
        return json.loads(texto[inicio : fim + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e}") from e


def validar_roteiro(texto):
    roteiro = extrair_json(texto)
    cenas = roteiro.get("cenas")
    if not isinstance(cenas, list) or not cenas:
        raise ValueError("roteiro sem cenas")
    for cena in cenas:
        if not cena.get("narracao") or not cena.get("prompt_imagem"):
            raise ValueError("cena sem narração ou prompt de imagem")
    return roteiro


def _com_perfil(sistema, perfil, etapa):
    """Acrescenta ao prompt de sistema o contexto do perfil do projeto (K26). Sem perfil, nada muda."""
    return f"{sistema}\n\n{perfil.contexto(etapa)}" if perfil else sistema


def gerar_ideias(roteador, tema, quantidade=10, perfil=None):
    return roteador.executar(
        "ideias",
        prompt=f"Dê {quantidade} ideias criativas de vídeos curtos sobre: {tema}. "
        "Para cada uma: título chamativo e gancho dos 3 primeiros segundos.",
        sistema=_com_perfil("Você é estrategista de conteúdo para redes sociais. Responda em português do Brasil.",
                            perfil, "ideias"),
    )


def gerar_roteiro(roteador, tema, duracao=30, contexto="", perfil=None):
    prompt = f"Crie o roteiro de um vídeo de cerca de {duracao} segundos sobre: {tema}."
    if contexto:
        prompt += f"\n\nUse estas informações de pesquisa:\n{contexto}"
    # Resposta que não for um roteiro válido conta como falha e vai para o próximo modelo.
    validar = validar_roteiro
    if perfil:
        def validar(texto):  # palavra proibida pelo perfil conta como resposta inválida (vai ao próximo modelo)
            roteiro = validar_roteiro(texto)
            problemas = perfil.checar(roteiro)
            if problemas:
                raise ValueError("; ".join(problemas))
            return roteiro
    return roteador.executar("roteiro", prompt=prompt, sistema=_com_perfil(SISTEMA_ROTEIRO, perfil, "roteiro"),
                             validar=validar)


def pesquisar(roteador, tema, max_resultados=5):
    """Busca na web e resume com fontes. Sem busca disponível, responde só com o modelo e avisa."""
    tentativas = []
    try:
        busca = roteador.executar("busca", consulta=tema, max_resultados=max_resultados)
        fontes = busca.valor
        tentativas += busca.tentativas
    except TodosFalharam as e:
        fontes = []
        tentativas += e.tentativas

    if fontes:
        lista = "\n".join(f"[{i}] {f['titulo']} — {f['url']}\n{f['trecho']}" for i, f in enumerate(fontes, 1))
        prompt = (
            f"Tema: {tema}\n\nResultados de busca:\n{lista}\n\n"
            "Escreva um resumo organizado em tópicos, citando as fontes como [1], [2]..."
        )
    else:
        prompt = (
            f"Tema: {tema}\n\nNão há busca na web disponível. Resuma o que você sabe, "
            "deixe claro que pode estar desatualizado e não invente fontes."
        )
    sintese = roteador.executar("pesquisa", prompt=prompt, sistema="Você é pesquisador. Responda em português do Brasil.")
    return Resultado(
        {"resumo": sintese.valor, "fontes": fontes},
        sintese.provedor,
        tentativas + sintese.tentativas,
    )


def gerar_imagem(roteador, prompt, saida, perfil=None):
    if perfil and perfil.visual():
        prompt = f"{prompt}. {perfil.visual()}"
    return roteador.executar("imagem", prompt=prompt, saida=Path(saida))


def gerar_voz(roteador, texto, saida):
    return roteador.executar("voz", texto=texto, saida=Path(saida))


def gerar_video(roteador, imagem, prompt, saida, duracao=5):
    return roteador.executar("video", imagem=Path(imagem), prompt=prompt, saida=Path(saida), duracao=duracao)

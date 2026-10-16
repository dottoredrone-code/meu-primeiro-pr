"""Funções do app, cada uma usando a cadeia de fallback da sua tarefa."""

import json
import re
from pathlib import Path

from .roteador import Resultado, TodosFalharam



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
    """Formato do roteiro com clima e sons por cena (K15, ver roteiro.py)."""
    from .roteiro import validar_roteiro as validar

    return validar(texto)


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
    from .roteiro import SISTEMA_ROTEIRO

    return roteador.executar("roteiro", prompt=prompt, sistema=_com_perfil(SISTEMA_ROTEIRO, perfil, "roteiro"),
                             validar=validar)


def pesquisar(roteador, tema, max_resultados=5):
    """Busca na web e resume com fontes. Sem busca disponível, responde só com o modelo e avisa."""
    tentativas = []
    try:
        from .pesquisa import fontes_validas

        busca = roteador.executar("busca", consulta=tema, max_resultados=max_resultados)
        fontes = fontes_validas(busca.valor)
        tentativas += busca.tentativas
    except TodosFalharam as e:
        fontes = []
        tentativas += e.tentativas

    if fontes:
        from .pesquisa import SISTEMA_PESQUISA, montar_prompt

        sintese = roteador.executar("pesquisa", prompt=montar_prompt(tema, fontes), sistema=SISTEMA_PESQUISA)
        return Resultado({"resumo": sintese.valor, "fontes": fontes}, sintese.provedor,
                         tentativas + sintese.tentativas)
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

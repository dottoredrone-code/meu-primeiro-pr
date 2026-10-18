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
    trecho = texto[inicio : fim + 1]
    try:
        return json.loads(trecho)
    except json.JSONDecodeError as e:
        try:  # modelo citou trecho com aspas duplas dentro de um texto: "diz "isso"" → tenta consertar
            return json.loads(_consertar_aspas(trecho))
        except json.JSONDecodeError:
            raise ValueError(f"JSON inválido: {e}") from e


def _consertar_aspas(t):
    """Escapa aspas duplas soltas dentro de textos do JSON e quebras de linha cruas.

    Uma aspa dentro de um texto só fecha o texto se depois dela vier , : } ] (ou o fim).
    """
    saida, dentro, i = [], False, 0
    while i < len(t):
        c = t[i]
        if dentro:
            if c == "\\":
                saida.append(t[i:i + 2])
                i += 2
                continue
            if c == '"':
                resto = t[i + 1:].lstrip()
                if not resto or resto[0] in ",:}]":
                    dentro = False
                    saida.append(c)
                else:
                    saida.append('\\"')
            elif c == "\n":
                saida.append("\\n")
            else:
                saida.append(c)
        else:
            dentro = c == '"'
            saida.append(c)
        i += 1
    return "".join(saida)


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


def gerar_imagem(roteador, prompt, saida, perfil=None, proporcao=None):
    if perfil and perfil.visual():
        prompt = f"{prompt}. {perfil.visual()}"
    proporcao = proporcao or (perfil.formato.get("proporcao") if perfil else None)
    extra = {"proporcao": proporcao} if proporcao else {}
    return roteador.executar("imagem", prompt=prompt, saida=Path(saida), **extra)


def gerar_voz(roteador, texto, saida):
    return roteador.executar("voz", texto=texto, saida=Path(saida))


def gerar_video(roteador, imagem, prompt, saida, duracao=5, proporcao=None, perfil=None):
    """proporcao explícita vence; sem ela, vale a do perfil (formato.proporcao)."""
    proporcao = proporcao or (perfil.formato.get("proporcao") if perfil else None)
    return roteador.executar("video", imagem=Path(imagem), prompt=prompt, saida=Path(saida), duracao=duracao,
                             proporcao=proporcao)

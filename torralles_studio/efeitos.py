"""Efeitos sonoros curtos nas transições (K21, spec 12 §3, D18, D22).

- `importar_pasta`: põe uma pasta de sons no acervo local (biblioteca), com licença conferida e etiquetas
  pelo nome do arquivo ("whoosh-short.mp3" → efeito, whoosh-short, whoosh, short). Arquivo sem licença aceita
  não entra. Serve, por exemplo, para os sons da Pixabay (uso comercial liberado, sem crédito obrigatório).
- `escolher_efeitos`: um som por transição, pelo clima da cena que entra. Só o acervo local: grátis, offline
  e sem a API do Freesound (D22). Sem som no acervo, o vídeo sai sem efeitos.
A montagem põe cada som 15 LU abaixo da voz, começando um pouco antes do corte.
"""

from pathlib import Path

from .biblioteca import TIPOS, _etiqueta

# Ordem de preferência por clima da cena que entra (nomes de arquivo, sem extensão). Alterna entre os que
# existirem para não repetir o mesmo som em todo corte.
SOM_POR_CLIMA = {
    "tenso": ["impact-bass-1", "whoosh", "glitch-1"],
    "epico": ["impact-bass-2", "whoosh", "impact-bass-1"],
    "alegre": ["pop", "whoosh-short", "sparkle"],
    "inspirador": ["sparkle", "whoosh", "chime"],
    "curioso": ["whoosh-short", "pop", "whoosh"],
    "calmo": ["whoosh-short", "chime"],
    "reflexivo": ["whoosh-short", "chime"],
}
PADRAO = ["whoosh", "whoosh-short"]
DURACAO_MAX_S = 3.0  # som longo (riser de 10 s) não serve para um corte


def etiquetas_do_nome(nome):
    """'whoosh-short' → ['efeito', 'som-whoosh-short', 'whoosh-short', 'whoosh', 'short'].

    'som-<nome>' identifica o nome exato (a etiqueta 'whoosh' também está em 'whoosh-short'); arquivo repetido
    com outro nome ganha as duas etiquetas 'som-…' e é achado pelos dois nomes."""
    inteiro = _etiqueta(Path(nome).stem)
    partes = [p for p in inteiro.split("-") if p and not p.isdigit()]
    return list(dict.fromkeys(["efeito", f"som-{inteiro}", inteiro, *partes]))


def importar_pasta(biblioteca, pasta, licenca, fonte, *, link=None, autor=None, perfil=None):
    """Guarda cada áudio da pasta no acervo. Devolve (importados, problemas)."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise FileNotFoundError(f"pasta não encontrada: {pasta}")
    importados, problemas = [], []
    for arq in sorted(pasta.iterdir()):
        if not arq.is_file() or arq.suffix.lower() not in TIPOS["audio"]:
            continue
        try:
            ativo = biblioteca.adicionar(arq, licenca, fonte, autor=autor, link=link, titulo=arq.stem,
                                         tags=etiquetas_do_nome(arq.name), perfil=perfil, provedor="acervo")
        except (ValueError, OSError) as e:  # licença recusada ou arquivo ilegível: os outros seguem
            problemas.append(f"{arq.name}: {e}")
            continue
        importados.append(ativo)
    return importados, problemas


def escolher_efeitos(biblioteca, climas, *, perfil=None, duracao_de=None):
    """[{"arquivo", "ativo", "nome"} ou None] para cada cena; a 1ª é sempre None (não há corte antes dela).

    duracao_de(caminho) → segundos (opcional): descarta sons longos demais para um corte.
    """
    pid = getattr(perfil, "id", perfil)
    cache, usados, escolhas = {}, {}, [None]

    def achar(nome):
        if nome not in cache:
            achados = biblioteca.buscar(["efeito", f"som-{nome}"], tipo="audio", perfil=pid, limite=1)
            ativo = achados[0] if achados else None
            arq = biblioteca.caminho(ativo) if ativo else None
            if arq is None or not arq.is_file():
                ativo = None
            elif duracao_de is not None:
                try:
                    if duracao_de(arq) > DURACAO_MAX_S:
                        ativo = None
                except Exception:  # duração ilegível: arquivo ruim não entra
                    ativo = None
            cache[nome] = ativo
        return cache[nome]

    for clima in list(climas)[1:]:
        opcoes = [n for n in SOM_POR_CLIMA.get(str(clima or "").strip().lower(), PADRAO) + PADRAO if achar(n)]
        opcoes = list(dict.fromkeys(opcoes))
        if not opcoes:
            escolhas.append(None)
            continue
        nome = min(opcoes, key=lambda n: (usados.get(n, 0), opcoes.index(n)))  # o menos usado, na ordem do clima
        usados[nome] = usados.get(nome, 0) + 1
        ativo = cache[nome]
        escolhas.append({"arquivo": str(biblioteca.caminho(ativo)), "ativo": ativo, "nome": nome})
    return escolhas

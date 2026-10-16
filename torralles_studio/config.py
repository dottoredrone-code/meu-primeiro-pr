import os
import tomllib
from pathlib import Path

from .provedores import CLASSES
from .rede import configurar_downloads
from .roteador import Roteador
from .seguranca import Orcamento

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_PADRAO = RAIZ / "config" / "fallbacks.toml"


def carregar_env(caminho=RAIZ / ".env"):
    """Lê um arquivo .env simples (CHAVE=valor) sem sobrescrever variáveis já definidas."""
    if not caminho.exists():
        return
    for linha in caminho.read_text().splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valor = valor.strip()
        if valor[:1] in ('"', "'"):
            valor = valor[1:].split(valor[0], 1)[0]
        else:
            valor = valor.split("#", 1)[0].strip()  # comentário no fim da linha
        if valor:
            os.environ.setdefault(chave.strip(), valor)


def montar_provedores(dados):
    provedores = {}
    for nome, cfg in dados["provedores"].items():
        classe = CLASSES.get(cfg.get("classe"))
        if classe is None:
            raise ValueError(f"provedor '{nome}': classe desconhecida '{cfg.get('classe')}'")
        provedores[nome] = classe(nome, cfg)
    return provedores


def validar_cadeias(provedores, cadeias):
    for tarefa, cadeia in cadeias.items():
        if not cadeia:
            raise ValueError(f"tarefa '{tarefa}' sem provedores")
        tipos = set()
        for nome in cadeia:
            if nome not in provedores:
                raise ValueError(f"tarefa '{tarefa}': provedor '{nome}' não existe")
            tipos.add(provedores[nome].tipo)
        if len(tipos) > 1:
            raise ValueError(f"tarefa '{tarefa}' mistura tipos de provedor: {sorted(tipos)}")


def carregar_config(caminho=None):
    carregar_env()
    caminho = Path(caminho or os.environ.get("TORRALLES_CONFIG") or os.environ.get("ESTUDIO_CONFIG") or CONFIG_PADRAO)
    return tomllib.loads(caminho.read_text())


def carregar_avaliador(roteador=None, caminho=None):
    from .qualidade import Avaliador

    dados = carregar_config(caminho)
    return Avaliador(roteador or carregar_roteador(caminho), dados.get("avaliacao", {}))


def carregar_loop(roteador=None, caminho=None, relatorio=None):
    """Loop de correção (K09) com roteador e avaliador do mesmo config (mesmo orçamento)."""
    from .loop import LoopCorrecao

    roteador = roteador or carregar_roteador(caminho)
    dados = carregar_config(caminho)
    avaliador = carregar_avaliador(roteador, caminho)
    return LoopCorrecao.do_config(roteador, avaliador, dados.get("avaliacao", {}).get("loop", {}), relatorio)


def carregar_banco(caminho=None):
    """Banco local do config ([banco].caminho, relativo à raiz do repositório)."""
    from .banco import Banco

    destino = Path(carregar_config(caminho).get("banco", {}).get("caminho", "dados/torralles.db"))
    return Banco(destino if destino.is_absolute() else RAIZ / destino)


def carregar_biblioteca(caminho=None, banco=None):
    """Biblioteca de mídia (K25) na pasta do config, registrada no banco local."""
    from .biblioteca import Biblioteca

    destino = Path(carregar_config(caminho).get("biblioteca", {}).get("pasta", "dados/biblioteca"))
    return Biblioteca(destino if destino.is_absolute() else RAIZ / destino, banco or carregar_banco(caminho))


MODELO_PERFIL = RAIZ / "config" / "perfil_modelo.toml"


def pasta_perfis(caminho=None):
    destino = Path(carregar_config(caminho).get("perfis", {}).get("pasta", "dados/perfis"))
    return destino if destino.is_absolute() else RAIZ / destino


def carregar_perfis(caminho=None):
    """Perfis por projeto (K26). Ajustes só podem citar provedores que existem no config."""
    from .perfis import Perfis

    dados = carregar_config(caminho)
    return Perfis(pasta_perfis(caminho), provedores_conhecidos=set(dados["provedores"]),
                  teto_maximo=dados.get("roteador", {}).get("teto_custo_usd"))


def carregar_roteador(caminho=None, banco=None):
    """banco: opcional (carregar_banco()); com ele, resultados repetidos vêm do cache sem custo."""
    dados = carregar_config(caminho)
    provedores = montar_provedores(dados)
    cadeias = {tarefa: t["cadeia"] for tarefa, t in dados["tarefas"].items()}
    validar_cadeias(provedores, cadeias)
    seguranca = dados.get("seguranca", {})
    configurar_downloads(seguranca.get("dominios_download"), seguranca.get("tamanho_maximo_download_mb"))
    opcoes = dados.get("roteador", {})
    return Roteador(
        provedores,
        cadeias,
        repeticoes=opcoes.get("repeticoes", 1),
        espera_base=opcoes.get("espera_base", 1.0),
        orcamento=Orcamento(opcoes.get("teto_custo_usd")),
        cache=banco,
    )

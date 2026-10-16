"""Perfis por projeto (K26, D11, D13): estilo, público, formato, voz e kit visual de cada projeto/canal.

Cada perfil é um arquivo `<id>.toml` na pasta de perfis (padrão `dados/perfis/`, fora do Git: são dados
seus, não do produto — D9). Modelo em `config/perfil_modelo.toml`.

Os perfis **não se misturam**:
- o contexto do prompt sai só dos campos do próprio perfil;
- os arquivos do kit visual ficam na pasta do próprio perfil (`<pasta>/<id>/`);
- os ajustes de provedor (ex.: voz) valem num roteador próprio do perfil, sem mexer no original;
- a memória fica separada por perfil no banco (Banco.lembrar / Banco.memorias).
"""

import copy
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .roteador import Roteador
from .seguranca import Orcamento

ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
CATEGORIAS = {"A", "B", "C", "D", "E", "F"}  # spec 09
PROPORCOES = {"9:16", "16:9", "1:1", "4:5"}


class ErroPerfil(ValueError):
    pass


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn").lower()


@dataclass
class Perfil:
    id: str
    nome: str
    pasta: Path                      # pasta própria do perfil (kit visual, imagens de referência)
    categoria: str | None = None     # A–F (spec 09): régua de referência do perfil
    hermes_perfil: str | None = None  # nome do perfil equivalente no Hermes (D13)
    idioma: str = "pt-BR"
    estilo: dict = field(default_factory=dict)       # tom, publico, cta_padrao, palavras_evitar, instrucoes
    formato: dict = field(default_factory=dict)      # proporcao, duracao_s, resolucao
    kit_visual: dict = field(default_factory=dict)   # paleta, fontes, estilo_imagem, logo, referencias
    provedores: dict = field(default_factory=dict)   # ajustes de config por provedor (ex.: voz)
    teto_custo_usd: float | None = None

    # -- prompt ---------------------------------------------------------------
    def contexto(self, etapa=None):
        """Bloco de contexto para o prompt de sistema (roteiro, ideias, imagem). Só dados deste perfil."""
        e, f = self.estilo, self.formato
        linhas = [f"Projeto: {self.nome}. Idioma: {self.idioma}."]
        if e.get("publico"):
            linhas.append(f"Público: {e['publico']}.")
        if e.get("tom"):
            linhas.append(f"Tom: {e['tom']}.")
        if f.get("proporcao") or f.get("duracao_s"):
            partes = [f"proporção {f['proporcao']}" if f.get("proporcao") else "",
                      f"cerca de {f['duracao_s']} s" if f.get("duracao_s") else ""]
            linhas.append("Formato: " + ", ".join(p for p in partes if p) + ".")
        if e.get("cta_padrao"):
            linhas.append(f"Chamada para ação padrão: {e['cta_padrao']}.")
        if e.get("palavras_evitar"):
            linhas.append("Nunca use: " + ", ".join(e["palavras_evitar"]) + ".")
        if etapa == "imagem" and self.visual():
            linhas.append(self.visual())
        if e.get("instrucoes"):
            linhas.append(str(e["instrucoes"]))
        return "\n".join(linhas)

    def visual(self):
        """Estilo visual do kit para o prompt de imagem ("" se o perfil não define)."""
        k = self.kit_visual
        partes = [k.get("estilo_imagem", ""), "paleta " + ", ".join(k["paleta"]) if k.get("paleta") else ""]
        partes = [p for p in partes if p]
        return ("Visual: " + "; ".join(partes) + ".") if partes else ""

    def checar_texto(self, texto):
        """Eliminatório do perfil: palavras proibidas no texto gerado."""
        alvo = _sem_acento(texto)
        return [f"palavra proibida pelo perfil {self.id}: {p!r}"
                for p in self.estilo.get("palavras_evitar", [])
                if re.search(rf"(?<!\w){re.escape(_sem_acento(p))}(?!\w)", alvo)]

    # -- arquivos do kit ------------------------------------------------------
    def arquivo(self, relativo):
        """Caminho de um arquivo do kit, que precisa estar dentro da pasta do perfil."""
        caminho = (self.pasta / relativo).resolve()
        if not caminho.is_relative_to(self.pasta.resolve()):
            raise ErroPerfil(f"o perfil {self.id} só pode usar arquivos da própria pasta: {relativo}")
        return caminho

    def referencias(self):
        return [self.arquivo(r) for r in self.kit_visual.get("referencias", [])]

    # -- roteador do perfil -----------------------------------------------------
    def roteador(self, base):
        """Cópia do roteador com os ajustes de provedor deste perfil (o original não muda).

        O orçamento é próprio do perfil quando ele define teto; o cache é compartilhado, mas a chave do
        cache inclui o config do provedor, então ajustes diferentes (ex.: voz) nunca se misturam.
        """
        provedores = {}
        for nome, prov in base.provedores.items():
            ajustes = self.provedores.get(nome)
            if ajustes:
                prov = copy.copy(prov)
                prov.cfg = {**prov.cfg, **ajustes}
            provedores[nome] = prov
        orcamento = Orcamento(self.teto_custo_usd) if self.teto_custo_usd is not None else base.orcamento
        novo = Roteador(provedores, base.cadeias, repeticoes=base.repeticoes, espera_base=base.espera_base,
                        dormir=base._dormir, relogio=base._relogio, orcamento=orcamento, cache=base.cache)
        novo._descanso_ate = base._descanso_ate  # descanso de provedor (429/401) vale para todos
        return novo


def _validar(dados, arquivo, pasta_raiz, provedores_conhecidos):
    pid = dados.get("id")
    if not pid or not ID_VALIDO.match(str(pid)):
        raise ErroPerfil(f"{arquivo.name}: 'id' inválido (use letras minúsculas, números, '-' ou '_')")
    if arquivo.stem != pid:
        raise ErroPerfil(f"{arquivo.name}: o nome do arquivo precisa ser igual ao id ({pid}.toml)")
    if not str(dados.get("nome", "")).strip():
        raise ErroPerfil(f"perfil {pid}: falta 'nome'")
    cat = dados.get("categoria")
    if cat is not None and cat not in CATEGORIAS:
        raise ErroPerfil(f"perfil {pid}: categoria {cat!r} não existe (use A–F, spec 09)")
    prop = dados.get("formato", {}).get("proporcao")
    if prop is not None and prop not in PROPORCOES:
        raise ErroPerfil(f"perfil {pid}: proporção {prop!r} inválida (use {', '.join(sorted(PROPORCOES))})")
    teto = dados.get("teto_custo_usd")
    if teto is not None and (isinstance(teto, bool) or not isinstance(teto, (int, float)) or teto < 0):
        raise ErroPerfil(f"perfil {pid}: teto_custo_usd inválido")
    for nome, ajustes in dados.get("provedores", {}).items():
        if provedores_conhecidos is not None and nome not in provedores_conhecidos:
            raise ErroPerfil(f"perfil {pid}: provedor desconhecido {nome!r}")
        proibidos = {k for k in ajustes if k.endswith("_env") or k in ("classe", "base_url", "familia")}
        if proibidos:
            raise ErroPerfil(f"perfil {pid}: o perfil não pode mudar {', '.join(sorted(proibidos))} do provedor {nome}")
    perfil = Perfil(
        id=pid, nome=str(dados["nome"]).strip(), pasta=pasta_raiz / pid, categoria=cat,
        hermes_perfil=dados.get("hermes_perfil"), idioma=dados.get("idioma", "pt-BR"),
        estilo=dict(dados.get("estilo", {})), formato=dict(dados.get("formato", {})),
        kit_visual=dict(dados.get("kit_visual", {})), provedores=dict(dados.get("provedores", {})),
        teto_custo_usd=teto,
    )
    for chave in ("logo",):
        if perfil.kit_visual.get(chave):
            perfil.arquivo(perfil.kit_visual[chave])
    perfil.referencias()  # valida que ficam na pasta do perfil
    return perfil


class Perfis:
    """Conjunto de perfis carregados de uma pasta. Arquivos que começam com '_' são ignorados."""

    def __init__(self, pasta, provedores_conhecidos=None):
        self.pasta = Path(pasta)
        self.itens = {}
        self._por_hermes = {}
        if not self.pasta.is_dir():
            return
        for arquivo in sorted(self.pasta.glob("*.toml")):
            if arquivo.name.startswith("_"):
                continue
            try:
                dados = tomllib.loads(arquivo.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as e:
                raise ErroPerfil(f"{arquivo.name}: TOML inválido ({e})") from None
            perfil = _validar(dados, arquivo, self.pasta, provedores_conhecidos)
            if perfil.hermes_perfil:
                if perfil.hermes_perfil in self._por_hermes:
                    raise ErroPerfil(f"o perfil do Hermes {perfil.hermes_perfil!r} está ligado a dois perfis: "
                                     f"{self._por_hermes[perfil.hermes_perfil]} e {perfil.id}")
                self._por_hermes[perfil.hermes_perfil] = perfil.id
            self.itens[perfil.id] = perfil

    def __contains__(self, pid):
        return pid in self.itens

    def __iter__(self):
        return iter(self.itens.values())

    def obter(self, pid):
        """Perfil pelo id do Studio ou pelo nome do perfil no Hermes (campo 'perfil' do contrato, spec 08)."""
        if pid in self.itens:
            return self.itens[pid]
        if pid in self._por_hermes:
            return self.itens[self._por_hermes[pid]]
        disponiveis = ", ".join(sorted(self.itens)) or "nenhum (crie com: python -m torralles_studio perfil-novo)"
        raise ErroPerfil(f"perfil {pid!r} não encontrado. Disponíveis: {disponiveis}")


def criar_perfil(pasta, pid, nome, modelo):
    """Cria <pasta>/<pid>.toml a partir do modelo, com id e nome preenchidos. Não sobrescreve."""
    if not ID_VALIDO.match(pid):
        raise ErroPerfil(f"id inválido: {pid!r} (use letras minúsculas, números, '-' ou '_')")
    pasta = Path(pasta)
    destino = pasta / f"{pid}.toml"
    if destino.exists():
        raise ErroPerfil(f"o perfil {pid} já existe: {destino}")
    texto = Path(modelo).read_text(encoding="utf-8")
    nome_limpo = nome.replace('"', "").replace("\\", "")
    texto, n_id = re.subn(r'(?m)^id = "[^"]*"', lambda m: f'id = "{pid}"', texto, count=1)
    texto, n_nome = re.subn(r'(?m)^nome = "[^"]*"', lambda m: f'nome = "{nome_limpo}"', texto, count=1)
    if not (n_id and n_nome):
        raise ErroPerfil(f"o modelo {modelo} precisa ter as linhas 'id = \"...\"' e 'nome = \"...\"'")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / pid).mkdir(exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return destino

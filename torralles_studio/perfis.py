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
import json
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
# O perfil ajusta estilo do provedor (voz, tamanho…), nunca o que é regra do produto:
# chaves e endereços (segurança), modelo e custo (teto D20 e modelos como dados, KR1), família (juízes).
CAMPOS_PROIBIDOS = {"classe", "base_url", "familia", "modelo", "custo_usd", "custo_usd_por_segundo", "timeout",
                    "cache"}


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

    def checar(self, valor):
        """Eliminatório para o loop de correção (`checar=perfil.checar`): aceita texto ou roteiro (dict)."""
        if isinstance(valor, dict):
            partes = [str(valor.get("titulo", ""))]
            partes += [str(c.get("narracao", "")) for c in valor.get("cenas", []) if isinstance(c, dict)]
            valor = "\n".join(partes)
        return self.checar_texto(str(valor))

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
        if self.teto_custo_usd is not None:
            teto_global = base.orcamento.teto_usd
            teto = self.teto_custo_usd if teto_global is None else min(self.teto_custo_usd, teto_global)
            orcamento = Orcamento(teto)  # o perfil pode ser mais econômico, nunca passar do teto do config
        else:
            orcamento = base.orcamento
        novo = Roteador(provedores, base.cadeias, repeticoes=base.repeticoes, espera_base=base.espera_base,
                        dormir=base._dormir, relogio=base._relogio, orcamento=orcamento, cache=base.cache)
        novo._descanso_ate = base._descanso_ate  # descanso de provedor (429/401) vale para todos
        return novo


def _texto(valor, campo, pid):
    if valor is not None and not isinstance(valor, str):
        raise ErroPerfil(f"perfil {pid}: '{campo}' precisa ser texto")
    return valor or None


def _lista_de_textos(valor, campo, pid):
    if valor is None:
        return []
    if not isinstance(valor, list) or not all(isinstance(v, str) and v.strip() for v in valor):
        raise ErroPerfil(f"perfil {pid}: '{campo}' precisa ser uma lista de textos, ex.: [\"a\", \"b\"]")
    return valor


def _tabela(valor, campo, pid):
    if valor is None:
        return {}
    if not isinstance(valor, dict):
        raise ErroPerfil(f"perfil {pid}: '[{campo}]' precisa ser uma tabela")
    return valor


def _validar(dados, arquivo, pasta_raiz, provedores_conhecidos, teto_maximo=None):
    pid = dados.get("id")
    if not pid or not ID_VALIDO.match(str(pid)):
        raise ErroPerfil(f"{arquivo.name}: 'id' inválido (use letras minúsculas, números, '-' ou '_')")
    if arquivo.stem != pid:
        raise ErroPerfil(f"{arquivo.name}: o nome do arquivo precisa ser igual ao id ({pid}.toml)")
    if not str(dados.get("nome", "")).strip():
        raise ErroPerfil(f"perfil {pid}: falta 'nome'")
    cat = _texto(dados.get("categoria"), "categoria", pid)
    if cat is not None and cat not in CATEGORIAS:
        raise ErroPerfil(f"perfil {pid}: categoria {cat!r} não existe (use A–F, spec 09)")
    formato = dict(_tabela(dados.get("formato"), "formato", pid))
    prop = _texto(formato.get("proporcao"), "formato.proporcao", pid)
    if prop is not None and prop not in PROPORCOES:
        raise ErroPerfil(f"perfil {pid}: proporção {prop!r} inválida (use {', '.join(sorted(PROPORCOES))})")
    teto = dados.get("teto_custo_usd")
    if teto is not None and (isinstance(teto, bool) or not isinstance(teto, (int, float)) or teto < 0):
        raise ErroPerfil(f"perfil {pid}: teto_custo_usd inválido")
    if teto is not None and teto_maximo is not None and teto > teto_maximo:
        raise ErroPerfil(f"perfil {pid}: teto_custo_usd {teto} passa do teto do config (US$ {teto_maximo:.2f}, D20)")
    provedores = _tabela(dados.get("provedores"), "provedores", pid)
    for nome, ajustes in provedores.items():
        if provedores_conhecidos is not None and nome not in provedores_conhecidos:
            raise ErroPerfil(f"perfil {pid}: provedor desconhecido {nome!r}")
        _tabela(ajustes, f"provedores.{nome}", pid)
        proibidos = {k for k in ajustes if k.endswith("_env") or k in CAMPOS_PROIBIDOS}
        if proibidos:
            raise ErroPerfil(f"perfil {pid}: o perfil não pode mudar {', '.join(sorted(proibidos))} do provedor {nome}")
    estilo = dict(_tabela(dados.get("estilo"), "estilo", pid))
    estilo["palavras_evitar"] = _lista_de_textos(estilo.get("palavras_evitar"), "estilo.palavras_evitar", pid)
    kit = dict(_tabela(dados.get("kit_visual"), "kit_visual", pid))
    kit["logo"] = _texto(kit.get("logo"), "kit_visual.logo", pid)
    for campo in ("paleta", "fontes", "referencias"):
        kit[campo] = _lista_de_textos(kit.get(campo), f"kit_visual.{campo}", pid)
    perfil = Perfil(
        id=pid, nome=str(dados["nome"]).strip(), pasta=pasta_raiz / pid, categoria=cat,
        hermes_perfil=_texto(dados.get("hermes_perfil"), "hermes_perfil", pid),
        idioma=_texto(dados.get("idioma"), "idioma", pid) or "pt-BR",
        estilo=estilo, formato=formato,
        kit_visual=kit, provedores=dict(provedores), teto_custo_usd=teto,
    )
    for chave in ("logo",):
        if perfil.kit_visual.get(chave):
            perfil.arquivo(perfil.kit_visual[chave])
    perfil.referencias()  # valida que ficam na pasta do perfil
    return perfil


class Perfis:
    """Conjunto de perfis carregados de uma pasta. Arquivos que começam com '_' são ignorados.

    Um perfil com defeito não derruba os outros: fica de fora e o motivo vai para `erros`.
    """

    def __init__(self, pasta, provedores_conhecidos=None, teto_maximo=None):
        self.pasta = Path(pasta)
        self.itens = {}
        self.erros = {}  # id (nome do arquivo) -> motivo
        self._por_hermes = {}
        if not self.pasta.is_dir():
            return
        candidatos = []
        for arquivo in sorted(self.pasta.glob("*.toml")):
            if arquivo.name.startswith("_"):
                continue
            try:
                try:
                    dados = tomllib.loads(arquivo.read_text(encoding="utf-8"))
                except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
                    raise ErroPerfil(f"{arquivo.name}: TOML inválido ({e})") from None
                candidatos.append(_validar(dados, arquivo, self.pasta, provedores_conhecidos, teto_maximo))
            except ErroPerfil as e:
                self.erros[arquivo.stem] = str(e)
            except (TypeError, AttributeError, ValueError) as e:  # rede de segurança: tipo inesperado no arquivo
                self.erros[arquivo.stem] = f"{arquivo.name}: campo com tipo inválido ({type(e).__name__}: {e})"
        ids = {p.id for p in candidatos}
        for perfil in candidatos:
            h = perfil.hermes_perfil
            if h and (h in self._por_hermes or (h in ids and h != perfil.id)):
                outro = self._por_hermes.get(h, h)
                self.erros[perfil.id] = (f"o perfil do Hermes {h!r} já aponta para o perfil {outro}; "
                                         f"o perfil {perfil.id} ficou de fora")
                continue
            if h:
                self._por_hermes[h] = perfil.id
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
        if pid in self.erros:
            raise ErroPerfil(f"o perfil {pid!r} tem um problema: {self.erros[pid]}")
        disponiveis = ", ".join(sorted(self.itens)) or "nenhum (crie com: python -m torralles_studio perfil-novo)"
        raise ErroPerfil(f"perfil {pid!r} não encontrado. Disponíveis: {disponiveis}")


def criar_perfil(pasta, pid, nome, modelo):
    """Cria <pasta>/<pid>.toml a partir do modelo, com id e nome preenchidos. Não sobrescreve."""
    if not ID_VALIDO.match(pid):
        raise ErroPerfil(f"id inválido: {pid!r} (use letras minúsculas, números, '-' ou '_')")
    nome = str(nome).strip()
    if not nome or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in nome):
        raise ErroPerfil("o nome do perfil não pode ser vazio nem ter quebra de linha ou caractere inválido")
    pasta = Path(pasta)
    destino = pasta / f"{pid}.toml"
    if destino.exists():
        raise ErroPerfil(f"o perfil {pid} já existe: {destino}")
    texto = Path(modelo).read_text(encoding="utf-8")
    texto, n_id = re.subn(r'(?m)^id = "[^"]*"', lambda m: f'id = "{pid}"', texto, count=1)
    # json.dumps gera uma string TOML básica válida (aspas e barras escapadas)
    texto, n_nome = re.subn(r'(?m)^nome = "[^"]*"', lambda m: f"nome = {json.dumps(nome, ensure_ascii=False)}",
                            texto, count=1)
    if not (n_id and n_nome):
        raise ErroPerfil(f"o modelo {modelo} precisa ter as linhas 'id = \"...\"' e 'nome = \"...\"'")
    try:
        _validar(tomllib.loads(texto), destino, pasta, None)
    except (tomllib.TOMLDecodeError, ErroPerfil) as e:
        raise ErroPerfil(f"o perfil gerado ficou inválido: {e}") from None
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / pid).mkdir(exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return destino

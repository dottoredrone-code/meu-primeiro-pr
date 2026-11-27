"""Prompts por serviço de imagem e vídeo, com checagem antes de gastar cota (K35, spec 14 §A e §F.1).

Fluxo: cena do roteiro → prompt neutro (campos) → molde do serviço (config/prompts_midia.toml) → prompt pronto.
A checagem por regra roda antes de qualquer chamada: prompt reprovado nunca chega ao serviço.

No roteador: quando a chamada leva `neutro=...`, cada provedor recebe o prompt escrito no molde dele
(ver Roteador._preparar_prompt); sem `neutro`, nada muda.
"""

import re
import tomllib
import unicodedata
from functools import lru_cache
from pathlib import Path

from .provedores.video import tipo_de_movimento

ARQUIVO_PADRAO = Path(__file__).resolve().parent.parent / "config" / "prompts_midia.toml"
CAMPOS = ("descricao", "acao", "instrucao", "estilo", "luz", "camera", "proporcao")
OBRIGATORIOS = {
    "imagem": ("descricao",),
    "editar_imagem": ("instrucao",),
    "animar": ("camera",),
    "video_texto": ("descricao", "camera"),
    "editar_video": ("instrucao",),
}


class PromptReprovado(ValueError):
    """Prompt que não passa na checagem por regra (não deve chegar ao serviço)."""


@lru_cache(maxsize=8)
def _ler(caminho):
    return tomllib.loads(Path(caminho).read_text(encoding="utf-8"))


def carregar_moldes(caminho=None):
    return _ler(str(caminho or ARQUIVO_PADRAO))


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", str(texto).lower()) if unicodedata.category(c) != "Mn")


def _limpo(texto):
    return " ".join(str(texto or "").split()).strip(" .,;")


def neutro_da_cena(cena, modalidade="imagem", *, perfil=None, proporcao=None, instrucao=None, cfg=None):
    """Prompt neutro (dict de campos) de uma cena do roteiro (ou de uma ideia solta: {"prompt_imagem": ...})."""
    cfg = cfg or carregar_moldes()
    kit = getattr(perfil, "kit_visual", None) or {}
    proporcao = proporcao or ((getattr(perfil, "formato", None) or {}).get("proporcao"))
    movimento = _limpo(cena.get("prompt_movimento"))
    estilo = [kit.get("estilo_imagem") or ""]
    if kit.get("paleta"):
        estilo.append("color palette " + ", ".join(kit["paleta"]))
    neutro = {
        "modalidade": modalidade,
        "descricao": _limpo(cena.get("prompt_imagem")),
        # movimento curto ("slow pan right") já vira a frase de câmera; o longo descreve ação da cena e fica
        "acao": movimento if modalidade in ("animar", "video_texto") and len(movimento.split()) > 6 else "",
        "instrucao": _limpo(instrucao or cena.get("instrucao")),
        "estilo": _limpo("; ".join(e for e in estilo if e)),
        "luz": cfg.get("luz", {}).get(str(cena.get("clima") or "").strip().lower(), ""),
        "camera": "",
        "proporcao": cfg.get("proporcao", {}).get(proporcao or "", ""),
        "evitar": list(dict.fromkeys([*cfg.get("geral", {}).get("evitar_padrao", []),
                                      *(kit.get("evitar") or [])])),
        "texto_na_imagem": bool(cena.get("texto_na_imagem")),
        "correcao": _limpo(cena.get("correcao")),  # feedback do juiz: entra junto da descrição, sem ser checado
        # entram na chave do cache: mudar um molde ou os nomes a evitar do perfil pede resultado novo
        "versao_moldes": _versao(cfg),
        "nomes_evitar": list(kit.get("evitar_nomes") or []),
        "movimento": movimento,
    }
    if modalidade in ("animar", "video_texto"):
        neutro["camera"] = cfg.get("camera", {}).get(tipo_de_movimento(movimento), "")
    return neutro


def _versao(cfg):
    import hashlib
    import json

    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:12]


def molde_do_servico(servico, modalidade, cfg=None):
    cfg = cfg or carregar_moldes()
    moldes = cfg.get("moldes", {})
    nome = (servico if servico in moldes else None) or cfg.get("servicos", {}).get(servico)         or cfg.get("modalidades", {}).get(modalidade) or "padrao"
    return nome, moldes.get(nome) or moldes.get("padrao") or {"forma": "frase", "limite": 900, "ordem": list(CAMPOS)}


def _etiquetas(texto):
    partes = re.split(r"[.;]\s*|,\s*|\s+-\s+", texto)
    return [p.strip() for p in partes if p.strip()]


def _juntar(campos, forma):
    if forma == "etiquetas":
        return ", ".join(e for c in campos for e in _etiquetas(c))
    frase = ". ".join(c[0].upper() + c[1:] for c in campos if c)
    return frase + ("." if frase else "")


def montar(neutro, molde):
    """{"prompt", "negativo", "cortados"}: escreve o neutro no molde; tira campos do fim até caber no limite."""
    forma = molde.get("forma", "frase")
    limite = int(molde.get("limite", 900))
    ordem = [c for c in molde.get("ordem", CAMPOS) if neutro.get(c)]
    negativo_modo = molde.get("negativo", "nenhum")
    evitar = ", ".join(neutro.get("evitar") or [])
    if neutro.get("texto_na_imagem"):  # cena que pede texto: não manda evitar letras
        evitar = ", ".join(e for e in neutro.get("evitar") or [] if e not in ("text", "letters"))
    sufixo = f". Avoid: {evitar}." if negativo_modo == "embutido" and evitar else ""
    cortados = []
    if neutro.get("correcao") and ordem:  # a correção do juiz vem logo depois do primeiro campo e nunca sai
        neutro = {**neutro, ordem[0]: f"{neutro[ordem[0]]}. Fix: {neutro['correcao']}"}
    while True:
        prompt = _juntar([neutro[c] for c in ordem], forma)
        if sufixo:
            prompt = prompt.rstrip(".") + sufixo
        if len(prompt) <= limite or len(ordem) <= 1:
            break
        cortados.append(ordem.pop())
    if len(prompt) > limite and sufixo:  # ainda não coube: sai o "evitar" antes de cortar a descrição
        sufixo, cortados = "", cortados + ["evitar"]
        prompt = _juntar([neutro[c] for c in ordem], forma)
    if len(prompt) > limite:  # só o campo principal e ainda grande: corta na última palavra inteira
        prompt = prompt[:limite].rsplit(" ", 1)[0].rstrip(" ,.;") + "."
        cortados.append("final da descrição")
    return {"prompt": prompt, "negativo": evitar if negativo_modo == "separado" and evitar else None,
            "cortados": cortados}


def checar(neutro, montado, molde, *, perfil=None, cfg=None):
    """Lista de problemas (vazia = aprovado). Só regras grátis; o juiz opcional vem depois (spec 14 §F.1)."""
    cfg = cfg or carregar_moldes()
    problemas = []
    modalidade = neutro.get("modalidade", "imagem")
    for campo in OBRIGATORIOS.get(modalidade, ("descricao",)):
        if not neutro.get(campo):
            problemas.append(f"falta '{campo}' para {modalidade}")
    if len(montado["prompt"]) > int(molde.get("limite", 900)):
        problemas.append(f"passa do limite de {molde.get('limite')} caracteres")
    texto = _sem_acento(" ".join(str(neutro.get(c) or "") for c in ("descricao", "acao", "instrucao")))
    if not neutro.get("texto_na_imagem"):
        pedidos = [p for p in cfg.get("geral", {}).get("pedidos_de_texto", []) if re.search(rf"\b{re.escape(p)}\b", texto)]
        if pedidos:
            problemas.append(f"pede texto escrito na imagem ({', '.join(pedidos)}); legendas e títulos entram na montagem")
    kit = getattr(perfil, "kit_visual", None) or {}
    estilo = getattr(perfil, "estilo", None) or {}
    proibidos = [*(kit.get("evitar_nomes") or []), *(estilo.get("palavras_evitar") or [])]
    achados = [n for n in proibidos if n and re.search(rf"\b{re.escape(_sem_acento(n))}\b", texto)]
    if achados:
        problemas.append(f"usa nomes que o perfil manda evitar: {', '.join(achados)}")
    movimento = neutro.get("acao") or neutro.get("movimento")
    if modalidade == "animar" and movimento:
        pedido = tipo_de_movimento(movimento)
        camera = cfg.get("camera", {}).get(pedido)
        if camera and camera.lower() not in montado["prompt"].lower():
            problemas.append(f"o movimento da cena ({pedido}) não está no prompt")
    return problemas


def preparar(servico, neutro, *, perfil=None, cfg=None):
    """Prompt do serviço já conferido. Lança PromptReprovado com os problemas."""
    cfg = cfg or carregar_moldes()
    nome, molde = molde_do_servico(servico, neutro.get("modalidade", "imagem"), cfg)
    montado = montar(neutro, molde)
    problemas = checar(neutro, montado, molde, perfil=perfil, cfg=cfg)
    if problemas:
        raise PromptReprovado("prompt reprovado na checagem: " + "; ".join(problemas))
    return {**montado, "molde": nome}

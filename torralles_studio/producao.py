"""Vídeo completo a partir de um tema (K32): pesquisa → roteiro → imagem, voz e cena por cena → montagem.

Cada etapa usa o que já existe (loop com juiz, roteador com fallback e teto de custo, montagem com régua).
Os arquivos ficam na pasta do vídeo; rodar de novo reaproveita o que já foi feito (não paga duas vezes)
e continua de onde parou se algo falhou no meio.
"""

import json
import re
import time
import unicodedata
from pathlib import Path

from . import funcoes
from .montagem import PADROES, montar, trecho_falado, verificar_montagem
from .roteador import TodosFalharam


class ErroProducao(Exception):
    """Uma etapa não pôde ser feita por nenhum provedor (a mensagem diz qual e por quê)."""


def pasta_do_tema(tema, base="saidas"):
    t = "".join(c for c in unicodedata.normalize("NFD", tema.lower()) if unicodedata.category(c) != "Mn")
    return Path(base) / (re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:50] or "video")


def _pronto(arquivo):
    return Path(arquivo).is_file() and Path(arquivo).stat().st_size > 0


def _ler_json(arquivo):
    try:
        return json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def prompt_da_imagem(cena, proporcao):
    formato = {"9:16": "vertical 9:16", "16:9": "horizontal 16:9", "1:1": "quadrada 1:1", "4:5": "vertical 4:5"}
    return (f"{cena['prompt_imagem']}. Composição {formato.get(proporcao, proporcao)}, assunto principal no centro, "
            "sem nenhum texto, letra ou logotipo na imagem.")


def produzir_video(roteador, loop, tema, pasta, *, duracao=30, perfil=None, pesquisar=False, trilha=None, bpm=None,
                   cfg_montagem=None, aviso=None):
    """Produz o vídeo e devolve o relatório (também salvo em pasta/relatorio.json)."""
    avisar = aviso or (lambda texto: None)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    proporcao = (perfil.formato.get("proporcao") if perfil else None) or "9:16"
    gasto_inicial, inicio = roteador.orcamento.gasto_usd, time.monotonic()
    etapas = []

    def etapa(nome, provedor=None, reaproveitado=False, **extra):
        etapas.append({"etapa": nome, "provedor": provedor, "reaproveitado": reaproveitado, **extra})

    # 1. Pesquisa (opcional): fontes reais para o roteiro não inventar
    resumo = None
    if pesquisar:
        guardada = _ler_json(pasta / "pesquisa.json")
        if guardada and guardada.get("resumo"):
            resumo = guardada["resumo"]
            etapa("pesquisa", reaproveitado=True)
        else:
            from .pesquisa import produzir_pesquisa

            avisar("== pesquisa")
            r = produzir_pesquisa(loop, tema)
            if r.valor:
                resumo = r.valor.get("resumo")
                (pasta / "pesquisa.json").write_text(json.dumps(r.valor, ensure_ascii=False, indent=2), encoding="utf-8")
            etapa("pesquisa", r.provedor, nota=r.nota, aprovado=r.aprovado)

    # 2. Roteiro com juiz e loop de correção
    roteiro = _ler_json(pasta / "roteiro.json")
    if roteiro and roteiro.get("cenas"):
        etapa("roteiro", reaproveitado=True)
    else:
        from .roteiro import produzir_roteiro

        avisar("== roteiro")
        r = produzir_roteiro(loop, tema, duracao, pesquisa=resumo, perfil=perfil)
        if not r.valor or not r.valor.get("cenas"):
            raise ErroProducao(f"não saiu roteiro: {r.motivo}")
        roteiro = r.valor
        (pasta / "roteiro.json").write_text(json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8")
        etapa("roteiro", r.provedor, nota=r.nota, aprovado=r.aprovado,
              problemas=list(getattr(r.avaliacao, "problemas", None) or [])[:5])

    # 3. Cada cena: imagem → voz → cena animada com a duração da fala
    cenas = []
    folga = PADROES["folga_inicio_s"] + PADROES["folga_fim_s"] + PADROES["transicao_s"] + 0.3
    for i, cena in enumerate(roteiro["cenas"], 1):
        img, voz, video = pasta / f"cena_{i:02d}.png", pasta / f"voz_{i:02d}.mp3", pasta / f"cena_{i:02d}.mp4"
        try:
            if _pronto(img):
                etapa(f"cena {i}: imagem", reaproveitado=True)
            else:
                avisar(f"== cena {i}/{len(roteiro['cenas'])}: imagem")
                r = funcoes.gerar_imagem(roteador, prompt_da_imagem(cena, proporcao), img, perfil=perfil,
                                         proporcao=proporcao)
                etapa(f"cena {i}: imagem", r.provedor)
            if _pronto(voz):
                etapa(f"cena {i}: voz", reaproveitado=True)
            else:
                avisar(f"== cena {i}: narração")
                r = funcoes.gerar_voz(roteador, cena["narracao"], voz)
                etapa(f"cena {i}: voz", r.provedor)
            ini, fim, _ = trecho_falado(voz)
            if _pronto(video):
                etapa(f"cena {i}: vídeo", reaproveitado=True)
            else:
                avisar(f"== cena {i}: movimento")
                ultima = i == len(roteiro["cenas"])  # a última pode segurar até 1,5 s a mais na montagem
                dur = round((fim - ini) + folga + (1.5 if ultima else 0), 2)
                r = funcoes.gerar_video(roteador, img, cena.get("prompt_movimento", ""), video, duracao=dur,
                                        proporcao=proporcao)
                etapa(f"cena {i}: vídeo", r.provedor)
        except TodosFalharam as e:
            raise ErroProducao(f"cena {i}: {e}") from None
        cenas.append({"video": str(video), "voz": str(voz), "narracao": cena["narracao"],
                      "texto_tela": cena.get("texto_tela"), "duracao": cena.get("duracao")})

    # 4. Montagem final + régua da spec 03 §3.6
    avisar("== montagem final")
    final = pasta / "video_final.mp4"
    resultado = montar(cenas, final, proporcao=proporcao, trilha=trilha, bpm=bpm, cfg=cfg_montagem,
                       pasta_trabalho=pasta / "montagem", duracao_alvo=duracao)
    conferencia = verificar_montagem(resultado, duracao_pedida=duracao)
    relatorio = {
        "tema": tema, "video": str(final), "proporcao": proporcao, "duracao_s": resultado["duracao_s"],
        "aprovado": conferencia["aprovado"], "problemas": conferencia["problemas"],
        "medidas": conferencia["medidas"], "custo_usd": round(roteador.orcamento.gasto_usd - gasto_inicial, 4),
        "tempo_s": round(time.monotonic() - inicio), "etapas": etapas,
        "titulo": roteiro.get("titulo"), "cta": roteiro.get("cta"),
    }
    (pasta / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return relatorio

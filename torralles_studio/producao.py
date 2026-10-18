"""Vídeo completo a partir de um tema (K32): pesquisa → roteiro → imagem, voz e cena por cena → montagem.

Cada etapa usa o que já existe (loop com juiz, roteador com fallback e teto de custo, montagem com régua).
Os arquivos ficam na pasta do vídeo; rodar de novo reaproveita o que já foi feito (não paga duas vezes)
e continua de onde parou se algo falhou no meio. Cada arquivo é gravado com nome provisório e só ganha o
nome final quando fica completo, então uma interrupção nunca deixa arquivo pela metade para ser reaproveitado.
"""

import json
import os
import re
import shutil
import time
import unicodedata
from pathlib import Path

from . import funcoes
from .montagem import PADROES, ErroMontagem, duracao as duracao_midia, montar, trecho_falado, verificar_montagem
from .roteador import TodosFalharam

_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_ASSINATURAS = (b"\x89PNG", b"\xff\xd8\xff", b"RIFF", b"GIF8")  # PNG, JPEG, WebP, GIF


class ErroProducao(Exception):
    """Uma etapa não pôde ser feita (a mensagem diz qual e por quê)."""


def pasta_do_tema(tema, base="saidas"):
    t = "".join(c for c in unicodedata.normalize("NFD", tema.lower()) if unicodedata.category(c) != "Mn")
    nome = re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:50].strip("-") or "video"
    return Path(base) / (f"video-{nome}" if nome in _RESERVADOS else nome)  # "con", "nul"… são proibidos no Windows


def _pronto(arquivo):
    """Arquivo completo e legível: imagem com assinatura conhecida; áudio e vídeo com duração."""
    arquivo = Path(arquivo)
    if not arquivo.is_file() or arquivo.stat().st_size == 0:
        return False
    if arquivo.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        with arquivo.open("rb") as f:
            return f.read(4).startswith(_ASSINATURAS)
    try:
        return duracao_midia(arquivo) > 0
    except ErroMontagem:
        return False


def _gerar(destino, fazer):
    """Gera em `nome.parte.ext` e só renomeia para o nome final se ficar completo."""
    destino = Path(destino)
    parte = destino.with_name(f"{destino.stem}.parte{destino.suffix}")
    parte.unlink(missing_ok=True)
    try:
        r = fazer(parte)
        if not _pronto(parte):
            raise ErroProducao(f"{destino.name}: o provedor {getattr(r, 'provedor', '?')} devolveu um arquivo "
                               "vazio ou ilegível")
        os.replace(parte, destino)
        return r
    finally:
        parte.unlink(missing_ok=True)


def _ler_json(arquivo):
    try:
        return json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _roteiro_guardado(pasta, tema, duracao, proporcao):
    """Roteiro salvo, só se for do mesmo tema, duração e formato e tiver o esquema certo."""
    from .roteiro import validar_esquema

    dados = _ler_json(pasta / "roteiro.json")
    if not isinstance(dados, dict) or not isinstance(dados.get("roteiro"), dict):
        return None
    if (dados.get("tema"), dados.get("duracao"), dados.get("proporcao")) != (tema, duracao, proporcao):
        return None
    if validar_esquema(dados["roteiro"]):
        return None
    return dados


def prompt_da_imagem(cena, proporcao):
    formato = {"9:16": "vertical 9:16", "16:9": "horizontal 16:9", "1:1": "quadrada 1:1", "4:5": "vertical 4:5"}
    return (f"{cena['prompt_imagem']}. Composição {formato.get(proporcao, proporcao)}, assunto principal no centro, "
            "sem nenhum texto, letra ou logotipo na imagem.")


def produzir_video(roteador, loop, tema, pasta, *, duracao=30, perfil=None, pesquisar=False, trilha=None, bpm=None,
                   cfg_montagem=None, aviso=None, refazer_roteiro=False):
    """Produz o vídeo e devolve o relatório (também salvo em pasta/relatorio.json)."""
    for programa in ("ffmpeg", "ffprobe"):
        if not shutil.which(programa):
            raise ErroProducao(f"{programa} não encontrado: instale o FFmpeg (ele traz o ffprobe) e abra um "
                               "terminal novo")
    avisar = aviso or (lambda texto: None)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    proporcao = (perfil.formato.get("proporcao") if perfil else None) or "9:16"
    c = {**PADROES, **(cfg_montagem or {})}
    gasto_inicial, inicio = roteador.orcamento.gasto_usd, time.monotonic()
    etapas = []

    def etapa(nome, provedor=None, reaproveitado=False, **extra):
        etapas.append({"etapa": nome, "provedor": provedor, "reaproveitado": reaproveitado, **extra})

    guardado = None if refazer_roteiro else _roteiro_guardado(pasta, tema, duracao, proporcao)

    # 1. Pesquisa (opcional, só se o roteiro ainda vai ser feito): fontes reais para o roteiro não inventar
    resumo = None
    if pesquisar and guardado is None:
        salva = _ler_json(pasta / "pesquisa.json")
        if isinstance(salva, dict) and salva.get("tema") == tema and salva.get("resumo"):
            resumo = salva["resumo"]
            etapa("pesquisa", reaproveitado=True)
        else:
            from .pesquisa import produzir_pesquisa

            avisar("== pesquisa")
            r = produzir_pesquisa(loop, tema)
            if r.valor and r.valor.get("resumo"):
                resumo = r.valor["resumo"]
                (pasta / "pesquisa.json").write_text(json.dumps({"tema": tema, **r.valor}, ensure_ascii=False,
                                                                indent=2), encoding="utf-8")
            etapa("pesquisa", r.provedor, nota=r.nota, aprovado=r.aprovado)

    # 2. Roteiro com juiz e loop de correção
    if guardado:
        roteiro = guardado["roteiro"]
        etapa("roteiro", reaproveitado=True, aprovado=guardado.get("aprovado"))
        if not guardado.get("aprovado"):
            avisar("⚠ usando o roteiro já feito, que não foi aprovado pelo juiz (para refazer: --refazer-roteiro)")
    else:
        from .roteiro import produzir_roteiro

        avisar("== roteiro")
        r = produzir_roteiro(loop, tema, duracao, pesquisa=resumo, perfil=perfil)
        if not r.valor or not r.valor.get("cenas"):
            raise ErroProducao(f"não saiu roteiro: {r.motivo}")
        roteiro = r.valor
        (pasta / "roteiro.json").write_text(json.dumps(
            {"tema": tema, "duracao": duracao, "proporcao": proporcao, "aprovado": r.aprovado, "nota": r.nota,
             "roteiro": roteiro}, ensure_ascii=False, indent=2), encoding="utf-8")
        etapa("roteiro", r.provedor, nota=r.nota, aprovado=r.aprovado,
              problemas=list(getattr(r.avaliacao, "problemas", None) or [])[:5])
        for nome in [p.name for p in pasta.glob("cena_*")] + [p.name for p in pasta.glob("voz_*")]:
            (pasta / nome).unlink(missing_ok=True)  # roteiro novo: mídia das cenas antigas não serve mais

    # 3. Cada cena: imagem → voz → cena animada com a duração da fala
    cenas, total = [], len(roteiro["cenas"])
    folga = c["folga_inicio_s"] + c["folga_fim_s"] + c["transicao_s"] + 0.5  # + pausa extra que a montagem dá
    for i, cena in enumerate(roteiro["cenas"], 1):
        img, voz, video = pasta / f"cena_{i:02d}.png", pasta / f"voz_{i:02d}.mp3", pasta / f"cena_{i:02d}.mp4"
        try:
            if _pronto(img):
                etapa(f"cena {i}: imagem", reaproveitado=True)
            else:
                avisar(f"== cena {i}/{total}: imagem")
                r = _gerar(img, lambda saida: funcoes.gerar_imagem(
                    roteador, prompt_da_imagem(cena, proporcao), saida, perfil=perfil, proporcao=proporcao))
                etapa(f"cena {i}: imagem", r.provedor)
            if _pronto(voz):
                etapa(f"cena {i}: voz", reaproveitado=True)
            else:
                avisar(f"== cena {i}/{total}: narração")
                r = _gerar(voz, lambda saida: funcoes.gerar_voz(roteador, cena["narracao"], saida))
                etapa(f"cena {i}: voz", r.provedor)
            ini, fim, _ = trecho_falado(voz)
            if _pronto(video):
                etapa(f"cena {i}: vídeo", reaproveitado=True)
            else:
                avisar(f"== cena {i}/{total}: movimento")
                dur = round((fim - ini) + folga + (1.5 if i == total else 0), 2)  # a última segura mais no fim
                r = _gerar(video, lambda saida: funcoes.gerar_video(
                    roteador, img, cena.get("prompt_movimento", ""), saida, duracao=dur, proporcao=proporcao))
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

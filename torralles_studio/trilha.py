"""Trilha sonora pelo clima do roteiro (K21, spec 12 §3, D19).

1. Clima dominante do roteiro → busca de músicas instrumentais com licença comercial
   (acervo local primeiro; depois Openverse: Jamendo, Freesound, Wikimedia — sem chave).
2. Cada candidata baixada é medida com FFmpeg (sem dependências novas): ritmo (BPM, por autocorrelação
   da energia), energia média e duração.
3. Pontuação 0–100 da spec 12: clima 35 · curva de energia 25 · sem vocal 20 · duração 10 · licença 10.
   Letra cantada é eliminatória (aqui: título/etiquetas que indicam voz — o juiz que ouve vem depois).
A escolhida entra na biblioteca (licença e crédito guardados) e vai para a montagem com o BPM medido.
"""

import array
import math
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from .biblioteca import ErroLicenca
from .midia import _extensao, _parece_pagina, candidatos_aceitos
from .rede import ErroProvedor, baixar
from .roteador import TodosFalharam

CONSULTA_POR_CLIMA = {
    "calmo": "calm ambient", "curioso": "playful curious", "inspirador": "inspiring uplifting",
    "epico": "epic cinematic", "alegre": "happy upbeat", "reflexivo": "reflective piano",
    "tenso": "suspense tension",
}
# Energia esperada por clima (0 = suave, 1 = intensa) e faixa de BPM que costuma combinar.
ENERGIA_POR_CLIMA = {"calmo": 0.2, "reflexivo": 0.25, "curioso": 0.5, "inspirador": 0.6, "alegre": 0.7,
                     "tenso": 0.7, "epico": 0.85}
BPM_POR_CLIMA = {"calmo": (60, 95), "reflexivo": (60, 95), "curioso": (90, 125), "inspirador": (85, 130),
                 "alegre": (100, 140), "tenso": (90, 150), "epico": (80, 140)}
_VOZ = {"vocal", "vocals", "vocalist", "vox", "voice", "voices", "singing", "singer", "sung", "song", "lyrics",
        "lyric", "rap", "acapella", "cappella", "choir", "chorus", "chant", "feat", "ft", "karaoke", "spoken",
        "speech", "narration", "podcast", "voz", "cancao", "canção", "letra", "cantada", "cantor", "cantora"}
_INSTRUMENTAL = {"instrumental", "background", "ambient", "soundtrack", "score", "loop", "beat", "piano"}


class SemTrilha(Exception):
    """Nenhuma trilha com licença aceita e sem voz foi encontrada."""


def clima_dominante(roteiro):
    climas = [str(c.get("clima") or "").lower() for c in (roteiro or {}).get("cenas", [])]
    climas = [c for c in climas if c in CONSULTA_POR_CLIMA]
    return Counter(climas).most_common(1)[0][0] if climas else "inspirador"


def _palavras(candidato):
    texto = " ".join([str(candidato.get("titulo") or "")] + [str(t) for t in candidato.get("tags") or []])
    return set("".join(ch if ch.isalnum() else " " for ch in texto.lower()).split())


def tem_voz(candidato):
    """Indício de voz cantada ou falada pelo título/etiquetas (eliminatório da spec 12).

    "no vocals", "without voice" e "instrumental" contam como sem voz.
    """
    texto = " ".join([str(candidato.get("titulo") or "")] + [str(t) for t in candidato.get("tags") or []]).lower()
    for neg in ("no vocals", "no vocal", "without vocals", "without voice", "no voice", "non vocal", "non-vocal",
                "sem voz", "sem vocal"):
        texto = texto.replace(neg, " ")
    p = set("".join(ch if ch.isalnum() else " " for ch in texto).split())
    return bool(p & _VOZ)


def medir_ritmo(arquivo, segundos=60):
    """{"bpm", "energia" (0–1), "duracao_s"} medidos com FFmpeg + autocorrelação simples da energia."""
    proc = subprocess.run(["ffmpeg", "-v", "error", "-t", str(segundos), "-i", str(arquivo), "-ac", "1",
                           "-ar", "4000", "-f", "s16le", "-"], capture_output=True, stdin=subprocess.DEVNULL)
    if proc.returncode != 0 or not proc.stdout:
        raise ErroProvedor("não consegui ler o áudio da trilha")
    amostras = array.array("h")
    amostras.frombytes(proc.stdout[: len(proc.stdout) // 2 * 2])
    passo = 40  # 10 ms por janela
    energia = [math.sqrt(sum(x * x for x in amostras[i:i + passo]) / passo) / 32768
               for i in range(0, len(amostras) - passo, passo)]
    if len(energia) < 300 or max(energia) <= 0:
        raise ErroProvedor("trilha curta ou em silêncio")
    rms = math.sqrt(sum(e * e for e in energia) / len(energia))
    db = 20 * math.log10(max(rms, 1e-9))
    if db < -50:  # quase silêncio: a montagem recusaria depois
        raise ErroProvedor(f"trilha quase em silêncio ({db:.0f} dB)")
    surtos = [max(0.0, energia[i] - energia[i - 1]) for i in range(1, len(energia))]  # ataques das notas
    media = sum(surtos) / len(surtos)
    pulsacao = media / (sum(energia) / len(energia))  # quanto a energia "bate"; pad contínuo fica perto de 0
    surtos = [s - media for s in surtos]
    base = sum(x * x for x in surtos) or 1e-12  # autocorrelação no atraso 0
    corrs = {lag: sum(surtos[i] * surtos[i - lag] for i in range(lag, len(surtos))) for lag in range(32, 102)}
    melhor_lag = max(range(33, 101), key=lambda lag: corrs[lag])  # 60 a 180 BPM (janelas de 10 ms)
    bpm = None
    if pulsacao >= 0.03 and corrs[melhor_lag] / base >= 0.2:  # batida clara e regular; sem pulso → sem BPM
        a, b, c = corrs[melhor_lag - 1], corrs[melhor_lag], corrs[melhor_lag + 1]
        ajuste = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) else 0.0  # pico entre dois atrasos
        bpm = round(6000 / (melhor_lag + max(-0.5, min(0.5, ajuste))), 1)
    return {"bpm": bpm,
            "energia": round(min(1.0, max(0.0, (db + 40) / 32)), 2),  # −40 dB → 0 · −8 dB → 1
            "duracao_s": round(_duracao_total(arquivo, len(amostras) / 4000), 1)}


def _duracao_total(arquivo, padrao):
    from .montagem import ErroMontagem, duracao

    try:
        return duracao(arquivo)  # a medição lê só 60 s; a duração real vem do ffprobe
    except ErroMontagem:
        return padrao


def pontuar(candidato, medidas, clima, duracao_video):
    """Nota 0–100 da spec 12 (clima 35, energia 25, sem vocal 20, duração 10, licença 10) e o detalhe."""
    if tem_voz(candidato):
        return 0, {"eliminatorio": "parece ter voz"}
    p = _palavras(candidato)
    alvo = set(CONSULTA_POR_CLIMA[clima].split())
    clima_pts = 15 + 20 * min(1.0, len(p & alvo) / max(1, len(alvo)))  # veio da busca do clima: base 15
    energia_pts = 25 * (1 - min(1.0, abs(medidas["energia"] - ENERGIA_POR_CLIMA[clima]) / 0.6))
    lo, hi = BPM_POR_CLIMA[clima]
    if medidas.get("bpm") and not lo <= medidas["bpm"] <= hi:
        energia_pts *= 0.7
    vocal_pts = 20 if p & _INSTRUMENTAL else 14  # sem indício de voz; "instrumental" confirma
    dur = candidato.get("duracao") or medidas["duracao_s"]
    duracao_pts = 10 if dur >= duracao_video else 6  # curta repete (a montagem faz o loop)
    nota = round(clima_pts + energia_pts + vocal_pts + duracao_pts + 10)
    return nota, {"clima": round(clima_pts), "energia": round(energia_pts), "sem_vocal": vocal_pts,
                  "duracao": duracao_pts, "licenca": 10}


def escolher_trilha(roteador, biblioteca, roteiro, duracao_video, *, perfil=None, baixar_arquivo=baixar,
                    max_candidatas=3, aviso=None):
    """Devolve {"arquivo", "bpm", "clima", "nota", "ativo", "detalhe"}. Lança SemTrilha se não achar."""
    avisar = aviso or (lambda texto: None)
    clima = clima_dominante(roteiro)
    pid = getattr(perfil, "id", None)
    guardadas = biblioteca.buscar(["trilha", clima], tipo="audio", perfil=pid, limite=1)
    if guardadas:  # acervo local: grátis, offline e já conferida (se o arquivo sumiu ou estragou, busca outra)
        ativo = guardadas[0]
        arq = biblioteca.caminho(ativo)
        try:
            medidas = medir_ritmo(arq) if arq.is_file() else None
        except ErroProvedor:
            medidas = None
        if medidas:
            return {"arquivo": str(arq), "bpm": medidas.get("bpm"), "clima": clima, "nota": None, "ativo": ativo,
                    "detalhe": {"camada": "acervo"}}
        avisar("  … trilha do acervo indisponível: buscando outra")

    # O Openverse exige todas as palavras: "playful curious instrumental" volta vazio. Tenta com menos.
    palavras = CONSULTA_POR_CLIMA[clima].split()
    consultas = list(dict.fromkeys([" ".join(palavras + ["instrumental"]), " ".join(palavras), palavras[0]]))
    candidatos, motivo = [], None
    for consulta in consultas:
        avisar(f"  … trilha: buscando música '{consulta}' (clima {clima})")
        try:
            r = roteador.executar("midia_trilha", consulta=consulta, tipo="audio", max_resultados=12,
                                  categoria="music", usar_cache=False)
        except KeyError as e:
            raise SemTrilha(f"busca de trilha falhou: {e}") from None
        except TodosFalharam as e:
            if not all("sem resultados" in str(t.detalhe) for t in e.tentativas):
                # rede, servidor fora do ar ou provedor em descanso: outra consulta só faria esperar de novo
                raise SemTrilha(f"busca de trilha falhou: {e}") from None
            motivo = f"nenhuma música encontrada (tentei {', '.join(repr(c) for c in consultas)})"
            continue
        candidatos = [c for c in candidatos_aceitos(r.valor) if not tem_voz(c)]
        if candidatos:
            break
        motivo = "nenhuma música instrumental com licença comercial"
    if not candidatos:
        raise SemTrilha(motivo)
    candidatos.sort(key=lambda c: (bool(_palavras(c) & _INSTRUMENTAL), (c.get("duracao") or 0) >= duracao_video),
                    reverse=True)
    melhores, motivos = [], []
    with tempfile.TemporaryDirectory() as pasta:
        for i, c in enumerate(candidatos[:max_candidatas]):
            try:
                dados = baixar_arquivo(c["url"])
            except (ErroProvedor, ValueError) as e:
                motivos.append(f"{c.get('titulo')}: {e}")
                continue
            if _parece_pagina(dados):
                motivos.append(f"{c.get('titulo')}: o link devolveu uma página")
                continue
            extensao = _extensao(c["url"], "audio")
            if extensao is None:
                motivos.append(f"{c.get('titulo')}: formato que não é áudio")
                continue
            arq = Path(pasta) / f"trilha_{i}{extensao}"
            arq.write_bytes(dados)
            try:
                medidas = medir_ritmo(arq)
            except ErroProvedor as e:
                motivos.append(f"{c.get('titulo')}: {e}")
                continue
            nota, detalhe = pontuar(c, medidas, clima, duracao_video)
            melhores.append((nota, i, c, medidas, detalhe, arq))
        if not melhores:
            raise SemTrilha("nenhuma trilha pôde ser baixada: " + "; ".join(motivos[:3]))
        nota, _, c, medidas, detalhe, arq = max(melhores, key=lambda m: (m[0], -m[1]))
        try:
            ativo = biblioteca.adicionar(arq, c["licenca"], c.get("fonte") or r.provedor, autor=c.get("autor"),
                                         link=c.get("link"), titulo=c.get("titulo") or consulta,
                                         tags=["trilha", clima] + list(c.get("tags") or [])[:8], perfil=pid,
                                         provedor=r.provedor, parametros={"consulta": consulta, **medidas})
        except ErroLicenca as e:
            raise SemTrilha(f"licença da trilha recusada: {e}") from None
    return {"arquivo": str(biblioteca.caminho(ativo)), "bpm": medidas.get("bpm"), "clima": clima, "nota": nota,
            "ativo": ativo, "detalhe": {**detalhe, **medidas}}

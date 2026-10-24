"""Conferência da narração por transcrição (K18, spec 11): erro de palavras ≤ 10%.

A voz gerada é transcrita (Gemini; Whisper local se instalado) e comparada com o texto do roteiro pela taxa de
erro de palavras (WER). Acima do limite, a produção refaz a fala com o próximo provedor de voz.
Limite honesto: a transcrição às vezes "corrige" uma pronúncia ruim pelo contexto ("ola" → "olha"); por isso o
comando `testar-voz` também grava os áudios para ouvir.
"""

import re
import tempfile
import unicodedata
from pathlib import Path

LIMITE_WER = 0.10
FRASE_TESTE = ("Olha que vermelho bonito: o filho do vizinho trouxe um ninho, e o carro ficou na garagem. "
               "Trabalho, palha e milho; banho, sonho e carinho; rato, honra e terra.")


def palavras(texto):
    """Palavras normalizadas (minúsculas, sem acento e sem pontuação) para comparar fala e texto."""
    t = "".join(c for c in unicodedata.normalize("NFD", str(texto or "").lower()) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", t)


def taxa_erro(referencia, hipotese):
    """WER: (trocas + faltas + sobras) / palavras do texto, pela distância de edição entre as listas."""
    ref, hip = palavras(referencia), palavras(hipotese)
    if not ref:
        return 0.0 if not hip else 1.0
    anterior = list(range(len(hip) + 1))
    for i, r in enumerate(ref, 1):
        atual = [i] + [0] * len(hip)
        for j, h in enumerate(hip, 1):
            atual[j] = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (r != h))
        anterior = atual
    return round(anterior[-1] / len(ref), 3)


def limpar_transcricao(texto):
    """Tira marcas de tempo [mm:ss] e a linha 'SONS:' que a transcrição da percepção acrescenta."""
    texto = re.split(r"(?im)^\s*\**\s*sons\s*:", str(texto or ""))[0]
    return re.sub(r"\[\d{1,2}:\d{2}(?:\.\d+)?\]", " ", texto)


def conferir_voz(arquivo, texto, transcrever=None):
    """{"wer", "transcricao", "motor", "ok"} ou None se não houver como transcrever (sem chave nem Whisper)."""
    if transcrever is None:
        from .percepcao import transcrever
    with tempfile.TemporaryDirectory() as pasta:
        t = transcrever(Path(arquivo), Path(pasta))
    if not t or not t.get("texto"):
        return None
    falado = limpar_transcricao(t["texto"])
    wer = taxa_erro(texto, falado)
    return {"wer": wer, "transcricao": " ".join(falado.split())[:500], "motor": t.get("motor"), "ok": wer <= LIMITE_WER}

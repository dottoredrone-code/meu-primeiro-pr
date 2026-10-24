"""Conferência da narração por transcrição (K18, spec 11): erro de palavras ≤ 10%.

A voz gerada é transcrita (Gemini, com pedido de "só o texto falado"; Whisper local se instalado) e comparada com o
texto do roteiro pela taxa de erro de palavras (WER). Números são comparados por extenso nos dois lados
("30" = "trinta", "70%" = "setenta por cento", "R$ 1.500" = "mil e quinhentos reais").
Só refaz a fala quando há erro de verdade: WER acima de 10% **e** pelo menos 2 palavras erradas
(uma palavra trocada numa cena curta não paga outra voz).
Limite honesto: a transcrição às vezes "corrige" uma pronúncia ruim pelo contexto ("ola" → "olha"); por isso o
comando `testar-voz` também grava os áudios para ouvir.
"""

import base64
import os
import re
import tempfile
import unicodedata
from pathlib import Path

LIMITE_WER = 0.10
MINIMO_ERROS = 2
FRASE_TESTE = ("Olha que vermelho bonito: o filho do vizinho trouxe um ninho, e o carro ficou na garagem. "
               "Trabalho, palha e milho; banho, sonho e carinho; rato, honra e terra.")
PROMPT_TRANSCRICAO = ("Transcreva exatamente o que é falado neste áudio, em português do Brasil. Responda só com o "
                      "texto falado: sem marcas de tempo, sem rótulos de quem fala, sem descrever sons ou música.")

_UNIDADES = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze",
             "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
_DEZENAS = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CENTENAS = ["", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos",
             "oitocentos", "novecentos"]


def por_extenso(n):
    """Número inteiro (0 a 999.999.999) por extenso em pt-BR: 1500 → "mil e quinhentos"."""
    if n < 20:
        return _UNIDADES[n]
    if n < 100:
        d, u = divmod(n, 10)
        return _DEZENAS[d] + (f" e {_UNIDADES[u]}" if u else "")
    if n < 1000:
        if n == 100:
            return "cem"
        c, resto = divmod(n, 100)
        return _CENTENAS[c] + (f" e {por_extenso(resto)}" if resto else "")
    for valor, singular, plural in ((10**6, "um milhão", "milhões"), (1000, "mil", "mil")):
        if n >= valor:
            alto, resto = divmod(n, valor)
            prefixo = singular if alto == 1 else f"{por_extenso(alto)} {plural}"
            if not resto:
                return prefixo
            liga = " e " if resto < 100 or resto % 100 == 0 else " "
            return prefixo + liga + por_extenso(resto)
    return str(n)


def _numeros_por_extenso(texto):
    t = re.sub(r"R\$\s*([\d.]+),(\d{2})\b", r"\1 reais e \2 centavos", texto)  # como se fala um preço
    t = re.sub(r"R\$\s*([\d.]+)", r"\1 reais", t)
    t = re.sub(r"US\$\s*([\d.]+)[,.](\d{2})\b", r"\1 dólares e \2 centavos", t)
    t = re.sub(r"US\$\s*([\d.]+)", r"\1 dólares", t)
    t = re.sub(r"(\d)\s*h\b", r"\1 horas", t)
    t = re.sub(r"(\d)\s*%", r"\1 por cento", t)
    t = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", t)  # 1.500 → 1500

    def troca(m):
        inteiro, _, frac = m.group(0).partition(",")
        texto_num = por_extenso(int(inteiro)) if len(inteiro) <= 9 else inteiro
        return texto_num + (f" vírgula {por_extenso(int(frac))}" if frac and len(frac) <= 3 else "")
    return re.sub(r"\d+(?:,\d+)?", troca, t)


def palavras(texto):
    """Palavras normalizadas (números por extenso, minúsculas, sem acento e sem pontuação)."""
    t = _numeros_por_extenso(str(texto or ""))
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z]+", t)


def _distancia(ref, hip):
    anterior = list(range(len(hip) + 1))
    for i, r in enumerate(ref, 1):
        atual = [i] + [0] * len(hip)
        for j, h in enumerate(hip, 1):
            atual[j] = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (r != h))
        anterior = atual
    return anterior[-1]


def taxa_erro(referencia, hipotese):
    """WER: (trocas + faltas + sobras) / palavras do texto, pela distância de edição entre as listas."""
    ref, hip = palavras(referencia), palavras(hipotese)
    if not ref:
        return 0.0 if not hip else 1.0
    return round(_distancia(ref, hip) / len(ref), 3)


def limpar_transcricao(texto, cortar_sons=True):
    """Tira marcas de tempo, rótulos de quem fala e (na transcrição da percepção) a lista de sons."""
    t = str(texto or "")
    if cortar_sons:
        t = re.split(r"(?im)(?:^|(?<=[.!?])\s+)\s*\**\s*sons?(?:\s+percebidos)?\s*\**\s*:", t)[0]
    t = re.sub(r"[\[(]\s*\d{1,2}(?::\d{2}){1,2}(?:\.\d+)?(?:\s*[-–]\s*\d{1,2}(?::\d{2}){1,2}(?:\.\d+)?)?\s*[\])]",
               " ", t)
    t = re.sub(r"(?im)^\s*(?:transcri[cç][aã]o|narrador|locutor|falante\s*\d*|voz)\s*:\s*", "", t)
    return t


def transcrever_fala(arquivo):
    """{"texto", "motor"}: Gemini com pedido de só o texto falado; senão a transcrição da percepção (Whisper)."""
    if os.environ.get("GEMINI_API_KEY"):
        try:
            from .rede import post_json

            modelo = os.environ.get("GEMINI_MODELO_PERCEPCAO", "gemini-3.6-flash")
            with tempfile.TemporaryDirectory() as pasta:
                import subprocess

                audio = Path(pasta) / "fala.mp3"
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(arquivo), "-vn", "-ac", "1", "-ar", "16000",
                                "-b:a", "48k", str(audio)], check=True, capture_output=True, stdin=subprocess.DEVNULL)
                dados = base64.b64encode(audio.read_bytes()).decode()
            r = post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                          {"contents": [{"parts": [{"inline_data": {"mime_type": "audio/mp3", "data": dados}},
                                                   {"text": PROMPT_TRANSCRICAO}]}],
                           "generationConfig": {"temperature": 0}},
                          {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, 120)
            texto = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
            return {"texto": texto, "motor": f"gemini:fala:{modelo}"}
        except Exception:  # cai para a transcrição da percepção
            pass
    from .percepcao import transcrever

    with tempfile.TemporaryDirectory() as pasta:
        return transcrever(Path(arquivo), Path(pasta))


def conferir_voz(arquivo, texto, transcrever=None):
    """{"wer", "erros", "transcricao", "motor", "ok"} ou None se não houver como transcrever (sem chave nem Whisper)."""
    t = (transcrever or (lambda a, p: transcrever_fala(a)))(Path(arquivo), None)
    if not t or not t.get("texto"):
        return None
    # a transcrição própria já vem sem sons; cortar "Sons:" só na da percepção (a narração pode ter essa palavra)
    falado = limpar_transcricao(t["texto"], cortar_sons=not str(t.get("motor", "")).startswith("gemini:fala"))
    ref, hip = palavras(texto), palavras(falado)
    if not hip:  # nada sobrou para comparar: não conta como erro (não paga outra voz)
        return None
    erros = _distancia(ref, hip)
    wer = round(erros / len(ref), 3) if ref else (0.0 if not hip else 1.0)
    return {"wer": wer, "erros": erros, "transcricao": " ".join(falado.split())[:500], "motor": t.get("motor"),
            "ok": wer <= LIMITE_WER or erros < MINIMO_ERROS}

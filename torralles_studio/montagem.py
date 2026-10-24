"""Montagem final (K22, spec 03 §3.6, spec 12 §3): cenas + narração + legendas + trilha → vídeo pronto.

Etapas:
1. Tempo de cada cena = duração da fala + folgas (sem silêncios longos entre cenas); com o BPM da trilha,
   os cortes caem na batida mais próxima sem cortar a fala.
2. Clipes no tamanho do formato (cobre e recorta) e transições suaves (xfade).
3. Legendas da narração: até 2 linhas, poucas letras por linha, tempo ancorado nas pausas reais da voz,
   na área segura (9:16: fora dos 20% de baixo e dos 10% de cima). texto_tela vai no alto.
4. Trilha opcional: nível medido e ajustado para ficar ≥ 10 LU abaixo da voz (alvo 12) e abaixando
   sozinha quando a voz entra (sidechain).
5. Volume final −14 LUFS e pico ≤ −1 dBTP (loudnorm em duas passadas).
6. verificar_montagem() mede o arquivo pronto (ffprobe + ebur128 + pausas da voz) e lista os eliminatórios.

Usa só FFmpeg. A pasta de trabalho guarda clipes, áudios e legendas (.ass e .srt) para a exportação (K23).
"""

import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .provedores.video import tamanho_do_formato
from .rede import ErroProvedor

PADROES = {
    "fps": 30,
    "transicao": "auto",          # "auto" escolhe pelo clima da cena; ou um tipo fixo do xfade ("fade"…)
    "karaoke": True,              # legenda acende palavra por palavra no ritmo da fala
    "transicao_s": 0.4,
    "folga_inicio_s": 0.2,        # respiro antes da fala de cada cena
    "folga_fim_s": 0.35,          # respiro depois da fala
    "pausa_extra_max_s": 0.3,     # quanto a cena pode crescer até a duração do roteiro
    "cena_min_s": 1.5,
    "max_ajuste_batida_s": 0.35,  # quanto um corte pode andar para cair na batida
    "lufs": -14.0,
    "pico_dbtp": -1.5,            # alvo com margem; o eliminatório é −1
    "trilha_lu_abaixo": 12.0,     # alvo voz − trilha
    "trilha_lu_minimo": 10.0,     # eliminatório
    "fonte": "Arial",             # o FFmpeg troca por uma parecida se não houver
    "crf": 20,
    "preset": "medium",
}
LIMITES_LEGENDA = {"chars_linha": 42, "linhas": 2, "cps": 17.0, "min_s": 1.0}
CHARS_LINHA = {"9:16": 28, "4:5": 32, "1:1": 32, "16:9": 42}  # menos que 42 no vertical para caber com letra grande
AREA_SEGURA = {"9:16": (0.10, 0.20)}  # (cima, baixo) ocupados pela interface das redes; demais formatos: 5%
_IMAGENS = {".png", ".jpg", ".jpeg", ".webp"}
TOLERANCIA_SINCRONIA_S = 0.3
VOZ_LUFS = -18.0  # nível comum das falas antes da mistura (o volume final vem depois)


class ErroMontagem(Exception):
    """Entrada inválida para a montagem (ex.: cena sem vídeo, arquivo que não existe)."""


# ---------------------------------------------------------------- FFmpeg

def _ff(args, cwd=None):
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-nostdin", *args], capture_output=True, stdin=subprocess.DEVNULL, text=True, cwd=cwd)
    if proc.returncode != 0:
        raise ErroProvedor(f"ffmpeg falhou: {proc.stderr.strip()[-400:]}")
    return proc.stderr


def duracao(arquivo):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arquivo)],
                       capture_output=True, stdin=subprocess.DEVNULL, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise ErroMontagem(f"não consegui ler a duração de {Path(arquivo).name}") from None


def medir_volume(arquivo):
    """{"lufs", "pico_dbtp"} pelo ebur128 (pico verdadeiro). None quando não há som medível."""
    log = _ff(["-i", str(arquivo), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    resumo = log[log.rfind("Summary:"):]
    lufs = re.search(r"I:\s*(-?[\d.]+|-inf) LUFS", resumo)
    pico = re.search(r"Peak:\s*(-?[\d.]+|-inf) dBFS", resumo)

    def num(m):
        return float(m.group(1)) if m and m.group(1) != "-inf" and float(m.group(1)) > -70 else None
    return {"lufs": num(lufs), "pico_dbtp": num(pico)}


def pausas(arquivo, ruido_db=-35, minimo_s=0.15):
    """Trechos de silêncio [(início, fim)] de um áudio (silencedetect)."""
    log = _ff(["-i", str(arquivo), "-vn", "-af", f"silencedetect=noise={ruido_db}dB:d={minimo_s}", "-f", "null", "-"])
    inicios = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", log)]
    fins = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", log)]
    if len(fins) < len(inicios):  # silêncio até o fim do arquivo
        fins.append(duracao(arquivo))
    return [(max(0.0, a), b) for a, b in zip(inicios, fins)]


def limiar_silencio(arquivo):
    """Limiar de silêncio relativo ao pico (voz baixa não vira "sem fala"): −35 dB ou 25 dB abaixo do pico."""
    log = _ff(["-i", str(arquivo), "-vn", "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", log)
    return max(-60.0, min(-35.0, float(m.group(1)) - 25)) if m else -35.0  # abaixo de −60 dB é silêncio


def trecho_falado(arquivo):
    """(início, fim, pausas internas) da fala dentro do arquivo de voz."""
    total = duracao(arquivo)
    silencios = pausas(arquivo, limiar_silencio(arquivo))
    ini, fim, internas = 0.0, total, []
    for a, b in silencios:
        if a <= 0.05:
            ini = b
        elif b >= total - 0.05:
            fim = a
        else:
            internas.append((a, b))
    if fim <= ini:  # arquivo todo em silêncio
        return 0.0, 0.0, []
    return ini, fim, internas


# ---------------------------------------------------------------- tempos

def planejar_tempos(falas, duracoes_roteiro=None, cfg=None):
    """Lista de cenas com "inicio", "duracao", "fala_em" (relativo à cena) e "fala_s".

    falas: duração útil da fala de cada cena (0 ou None = cena sem narração).
    Com fala, a cena dura fala + folgas, crescendo no máximo `pausa_extra_max_s` até a duração do roteiro.
    """
    c = {**PADROES, **(cfg or {})}
    duracoes_roteiro = list(duracoes_roteiro or [None] * len(falas))
    tempos, inicio = [], 0.0
    for fala, roteiro in zip(falas, duracoes_roteiro):
        fala = float(fala or 0)
        if fala > 0:
            dur = c["folga_inicio_s"] + fala + c["folga_fim_s"]
            if roteiro:
                dur = max(dur, min(float(roteiro), dur + c["pausa_extra_max_s"]))
            em = c["folga_inicio_s"]
        else:
            dur, em = float(roteiro or c["cena_min_s"]), 0.0
        dur = round(max(dur, c["cena_min_s"]), 3)
        tempos.append({"inicio": round(inicio, 3), "duracao": dur, "fala_em": em, "fala_s": fala})
        inicio += dur
    return tempos


def alinhar_ao_tempo(tempos, bpm, primeira_batida_s=0.0, cfg=None):
    """Move cada corte para a batida mais próxima (até `max_ajuste_batida_s`), sem cortar a fala da cena.

    Devolve uma nova lista; quantos cortes caíram na batida fica em cada cena como "na_batida".
    """
    c = {**PADROES, **(cfg or {})}
    if not bpm or bpm <= 0:
        return [dict(t) for t in tempos]
    periodo = 60.0 / float(bpm)
    novos, inicio = [], 0.0
    for i, t in enumerate(tempos):
        t = {**t, "inicio": round(inicio, 3)}
        fim = inicio + t["duracao"]
        if i < len(tempos) - 1:
            menor_fim = inicio + max(c["cena_min_s"], t["fala_em"] + t["fala_s"] + 0.1)
            k = round((fim - primeira_batida_s) / periodo)
            opcoes = sorted((primeira_batida_s + j * periodo for j in (k - 1, k, k + 1)), key=lambda b: abs(b - fim))
            for batida in opcoes:
                if abs(batida - fim) <= c["max_ajuste_batida_s"] + 1e-9 and batida >= menor_fim - 1e-9:
                    fim = batida
                    t["na_batida"] = True
                    break
        t["duracao"] = round(fim - inicio, 3)
        novos.append(t)
        inicio = fim
    return novos


# ---------------------------------------------------------------- legendas

def _linhas(texto, max_chars, por_frase=True):
    linhas, atual = [], ""
    for p in str(texto or "").split():
        if atual and len(atual) + 1 + len(p) > max_chars:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
        if por_frase and len(atual) >= 12 and atual.endswith((".", "!", "?")):  # frase terminada fecha a linha
            linhas.append(atual)                                                # (frase curta segue junto)
            atual = ""
    if atual:
        linhas.append(atual)
    return linhas


def quebrar_texto(texto, max_chars):
    """Blocos de até 2 linhas com até max_chars cada (quebra por palavra; frase nova começa bloco novo)."""
    linhas = _linhas(texto, max_chars)
    blocos, i = [], 0
    while i < len(linhas):
        # Linha que termina frase fecha o bloco sozinha (a próxima frase começa em bloco novo).
        if i + 1 < len(linhas) and not linhas[i].endswith((".", "!", "?")):
            blocos.append([linhas[i], linhas[i + 1]])
            i += 2
        else:
            blocos.append([linhas[i]])
            i += 1
    # Bloco de uma palavra solta ("hábitos.") puxa a última linha do bloco anterior para ficar junto.
    for k in range(1, len(blocos)):
        if len(blocos[k]) == 1 and len(blocos[k][0]) < 12 and len(blocos[k - 1]) == 2 \
                and not blocos[k - 1][1].endswith((".", "!", "?")):
            blocos[k] = [blocos[k - 1].pop(), blocos[k][0]]
    return blocos


def distribuir_legendas(texto, inicio_fala, fim_fala, pausas_internas=(), max_chars=42, fim_cena=None):
    """[(inicio, fim, [linhas])] no tempo da fala.

    O corte entre blocos vai para uma pausa real perto da estimativa: o bloco seguinte entra quando a fala
    volta e o anterior sai até 0,4 s depois que ela para. Cada bloco fica na tela pelo menos 1 s e o
    bastante para ≤ 17 caracteres/s, sem invadir o bloco seguinte nem passar do fim da cena.
    """
    blocos = quebrar_texto(texto, max_chars)
    if not blocos or fim_fala <= inicio_fala:
        return []
    lim = LIMITES_LEGENDA
    pesos = [sum(len(l) for l in b) for b in blocos]
    total, dur = sum(pesos), fim_fala - inicio_fala
    inis, fins, acumulado = [inicio_fala], [], 0
    for p in pesos[:-1]:
        acumulado += p
        estimado = inicio_fala + dur * acumulado / total
        perto = [(a, b) for a, b in pausas_internas
                 if max(a - estimado, estimado - b, 0) <= 0.6 and b - 0.1 > inis[-1] + 0.3]
        if perto:
            a, b = min(perto, key=lambda x: max(x[0] - estimado, estimado - x[1], 0))
            entra = max(a, b - 0.1)
            fins.append(min(a + 0.4, entra))  # nunca depois que o seguinte entra (pausa curta)
            inis.append(entra)
        else:
            estimado = max(estimado, inis[-1] + 0.3)  # nunca antes do bloco anterior (fala rápida demais)
            fins.append(estimado)
            inis.append(estimado)
    teto = fim_fala + 0.8 if fim_cena is None else max(fim_fala, fim_cena)
    fins.append(min(fim_fala + 0.4, teto))
    # Bloco que ficaria menos de 1 s na tela junta com o vizinho, se os dois couberem em 2 linhas.
    i = 0
    while len(blocos) > 1 and i < len(blocos):
        if fins[i] - inis[i] >= lim["min_s"]:
            i += 1
            continue
        j = i if i + 1 < len(blocos) else i - 1  # junta j com j+1
        juntas = _linhas(" ".join(blocos[j] + blocos[j + 1]), max_chars, por_frase=False)
        if len(juntas) > lim["linhas"]:
            i += 1
            continue
        blocos[j:j + 2] = [juntas]
        del fins[j], inis[j + 1]
        i = max(0, j - 1)
    # Tempo mínimo de leitura: estica o fim até o próximo bloco (ou o fim da cena, no máx. 0,8 s após a fala).
    for i, b in enumerate(blocos):
        precisa = max(lim["min_s"], sum(len(l) for l in b) / lim["cps"])
        limite = inis[i + 1] if i + 1 < len(blocos) else min(teto, fim_fala + 0.8)
        if fins[i] - inis[i] < precisa:
            fins[i] = max(fins[i], min(inis[i] + precisa, limite))
    return [(round(inis[i], 3), round(fins[i], 3), b) for i, b in enumerate(blocos)]


def checar_legendas(legendas, max_chars=LIMITES_LEGENDA["chars_linha"]):
    """Eliminatórios de legibilidade (spec 03 §3.6). Lista vazia = ok."""
    lim, problemas = LIMITES_LEGENDA, []
    for n, (ini, fim, linhas) in enumerate(legendas, 1):
        dur = fim - ini
        if len(linhas) > lim["linhas"]:
            problemas.append(f"legenda {n} com {len(linhas)} linhas (máx. {lim['linhas']})")
        for linha in linhas:
            if len(linha) > min(max_chars, lim["chars_linha"]):
                problemas.append(f"legenda {n} com linha de {len(linha)} caracteres (máx. {min(max_chars, 42)})")
        if dur < lim["min_s"] - 1e-6:
            problemas.append(f"legenda {n} fica só {dur:.2f} s na tela (mín. {lim['min_s']:.0f} s)")
        cps = sum(len(l) for l in linhas) / dur if dur > 0 else float("inf")
        if cps > lim["cps"] + 1e-6:
            problemas.append(f"legenda {n} pede {cps:.1f} caracteres/s (máx. {lim['cps']:.0f})")
        if n > 1 and ini < legendas[n - 2][1] - 1e-6:
            problemas.append(f"legenda {n} começa antes da anterior acabar")
    return problemas


def linhas_tela(texto, proporcao):
    """texto_tela quebrado para a letra maior do alto da tela (pode passar de 2 linhas: a conferência acusa)."""
    return _linhas(texto, int(CHARS_LINHA.get(proporcao, 42) / 1.15), por_frase=False)


def estilo_legenda(largura, altura, proporcao):
    """Tamanho da letra e margens (px) que mantêm as legendas na área segura."""
    max_chars = CHARS_LINHA.get(proporcao, 42)
    cima, baixo = AREA_SEGURA.get(proporcao, (0.05, 0.05))
    tamanho = round(min(0.9 * largura / (max_chars * 0.55), altura * 0.05))
    return {"max_chars": max_chars, "tamanho": tamanho, "tamanho_tela": round(tamanho * 1.15),
            "margem_baixo": math.ceil(altura * (baixo + 0.02)), "margem_cima": math.ceil(altura * (cima + 0.02)),
            "area_segura": (cima, baixo)}


def _tempo_ass(s):
    cs = round(s * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _texto_ass(t):
    return str(t).replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


# Transição de entrada de cada cena pelo clima do roteiro (só tipos do xfade do FFmpeg 5+).
TRANSICAO_POR_CLIMA = {"curioso": "slideleft", "inspirador": "smoothup", "calmo": "fade", "reflexivo": "dissolve",
                       "alegre": "circleopen", "epico": "zoomin", "tenso": "wipeleft"}


def transicao_da_cena(clima, padrao="fade"):
    return TRANSICAO_POR_CLIMA.get(str(clima or "").strip().lower(), padrao)


def _karaoke(linhas, duracao):
    """Texto ASS com cada palavra acendendo no seu tempo (\\k em centésimos, proporcional ao tamanho)."""
    falado = max(duracao * 0.85, 0.1)  # o fim do bloco é só leitura: as palavras acendem antes
    palavras = [w for linha in linhas for w in linha.split()]
    total = sum(len(w) + 1 for w in palavras) or 1
    partes, acumulado, feito = [], 0.0, 0
    for n, linha in enumerate(linhas):
        trechos = []
        for w in linha.split():
            acumulado += (len(w) + 1) / total * falado
            cs = max(1, round(acumulado * 100) - feito)
            feito += cs
            trechos.append(f"{{\\k{cs}}}{_texto_ass(w)}")
        partes.append(" ".join(trechos))
    return "\\N".join(partes)


def gerar_ass(legendas, textos_tela, largura, altura, proporcao, fonte="Arial", karaoke=False):
    """karaoke: a palavra fica amarela quando é falada; sem ele, a legenda inteira aparece branca."""
    e = estilo_legenda(largura, altura, proporcao)
    primaria = "&H0000E5FF" if karaoke else "&H00FFFFFF"  # depois de falada (amarelo) / antes (branco)
    cab = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {largura}\nPlayResY: {altura}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        f"Style: Legenda,{fonte},{e['tamanho']},{primaria},&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(2, e['tamanho'] // 14)},0,2,{round(largura * 0.05)},{round(largura * 0.05)},{e['margem_baixo']},1\n"
        f"Style: Tela,{fonte},{e['tamanho_tela']},&H0000E5FF,&H0000E5FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(2, e['tamanho_tela'] // 14)},0,8,{round(largura * 0.05)},{round(largura * 0.05)},{e['margem_cima']},1\n"
        "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    quebra = "\\N"  # quebra de linha do ASS
    entrada = "{\\fad(120,80)}"  # legenda surge e some suave
    pulo = "{\\fad(200,150)\\fscx80\\fscy80\\t(0,250,\\fscx100\\fscy100)}"  # título cresce ao entrar
    eventos = [f"Dialogue: 0,{_tempo_ass(a)},{_tempo_ass(b)},Legenda,,0,0,0,,{entrada}"
               + (_karaoke(linhas, b - a) if karaoke else quebra.join(map(_texto_ass, linhas)))
               for a, b, linhas in legendas]
    eventos += [f"Dialogue: 1,{_tempo_ass(a)},{_tempo_ass(b)},Tela,,0,0,0,,{pulo}{quebra.join(map(_texto_ass, linhas))}"
                for a, b, linhas in textos_tela]
    return cab + "\n".join(eventos) + "\n"


def gerar_srt(legendas):
    def t(s):
        ms = round(s * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{n}\n{t(a)} --> {t(b)}\n" + "\n".join(linhas) + "\n" for n, (a, b, linhas) in enumerate(legendas, 1))


# ---------------------------------------------------------------- montagem

def _validar_cenas(cenas):
    if not cenas:
        raise ErroMontagem("nenhuma cena para montar")
    for i, c in enumerate(cenas, 1):
        if not c.get("video") or not Path(c["video"]).is_file():
            raise ErroMontagem(f"cena {i}: arquivo de vídeo ou imagem não encontrado")
        if c.get("voz") and not Path(c["voz"]).is_file():
            raise ErroMontagem(f"cena {i}: arquivo de voz não encontrado")


def _clipe(origem, destino, comprimento, largura, altura, c):
    """Clipe no tamanho e duração exatos. Clipe curto: desacelera até 1,5× e, se faltar, segura o último quadro."""
    origem = Path(origem)
    base = f"scale={largura}:{altura}:force_original_aspect_ratio=increase,crop={largura}:{altura},setsar=1"
    if origem.suffix.lower() in _IMAGENS:
        entrada, congelado = ["-loop", "1", "-framerate", str(c["fps"]), "-t", f"{comprimento:.3f}", "-i", str(origem)], 0.0
        filtro = f"{base},fps={c['fps']}"
    else:
        dur = duracao(origem)
        fator = min(comprimento / dur, 1.5) if 0 < dur < comprimento else 1.0
        congelado = max(0.0, comprimento - dur * fator)
        entrada = ["-i", str(origem)]
        filtro = (f"setpts={fator:.4f}*(PTS-STARTPTS),{base},fps={c['fps']},"
                  f"tpad=stop_mode=clone:stop_duration={comprimento:.3f},trim=duration={comprimento:.3f}")
    _ff([*entrada, "-an", "-vf", filtro, "-frames:v", str(round(comprimento * c["fps"])), "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(destino)])
    return round(congelado, 2)


def _loudnorm(origem, destino, c):
    alvo = f"I={c['lufs']}:TP={c['pico_dbtp']}:LRA=11"
    log = _ff(["-i", str(origem), "-af", f"loudnorm={alvo}:print_format=json", "-f", "null", "-"])
    m = json.loads(log[log.rfind("{"):log.rfind("}") + 1])
    medido = (f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
              f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    _ff(["-i", str(origem), "-af", f"loudnorm={alvo}:{medido},aresample=48000", "-c:a", "pcm_f32le", str(destino)])
    # O loudnorm mede diferente do ebur128 em áudio com muitas pausas: corrige o resto se o pico permitir.
    v = medir_volume(destino)
    if v["lufs"] is not None and abs(v["lufs"] - c["lufs"]) > 0.3:
        ganho = c["lufs"] - v["lufs"]
        if v["pico_dbtp"] is None or v["pico_dbtp"] + ganho <= c["pico_dbtp"]:
            ajustado = destino.with_name(destino.stem + "_ajuste.wav")
            _ff(["-i", str(destino), "-af", f"volume={ganho:.2f}dB", "-c:a", "pcm_f32le", str(ajustado)])
            ajustado.replace(destino)


def montar(cenas, saida, *, proporcao="9:16", trilha=None, bpm=None, primeira_batida_s=0.0, cfg=None,
           pasta_trabalho=None, tamanho=None, duracao_alvo=None):
    """Monta o vídeo final. Devolve um dict com tempos, legendas, medidas da trilha e caminhos de trabalho.

    cenas: [{"video": arquivo (vídeo ou imagem), "voz": arquivo ou None, "narracao": texto da legenda,
             "texto_tela": texto curto no alto (opcional), "duracao": segundos do roteiro (opcional)}]
    trilha: arquivo de música (opcional; repete se for curta). bpm: batidas por minuto da trilha (opcional).
    tamanho: (largura, altura) para forçar outro tamanho (testes); o padrão vem da proporção.
    duracao_alvo: duração pedida; se a fala ficar curta, a última cena segura até 1,5 s a mais e as outras
                  ganham até 0,3 s de respiro cada (nunca silêncio longo).
    """
    if not shutil.which("ffmpeg"):
        raise ErroProvedor("FFmpeg não instalado")
    _validar_cenas(cenas)
    if trilha and not Path(trilha).is_file():
        raise ErroMontagem("arquivo da trilha não encontrado")
    c = {**PADROES, **(cfg or {})}
    largura, altura = tamanho or tamanho_do_formato(proporcao)
    saida = Path(saida).resolve()
    saida.parent.mkdir(parents=True, exist_ok=True)
    temporaria = None
    if pasta_trabalho is None:
        temporaria = tempfile.TemporaryDirectory()
        pasta = Path(temporaria.name)
    else:
        pasta = Path(pasta_trabalho).resolve()
        pasta.mkdir(parents=True, exist_ok=True)
    try:
        return _montar(cenas, saida, pasta, proporcao, largura, altura, trilha, bpm, primeira_batida_s, c,
                       duracao_alvo)
    finally:
        if temporaria:
            temporaria.cleanup()


def completar_duracao(tempos, duracao_alvo, extra_final_s=1.5, extra_cena_s=0.3):
    """Estica as cenas quando a soma fica abaixo de 90% da duração pedida (primeiro a última, depois as outras)."""
    tempos = [dict(t) for t in tempos]
    total = sum(t["duracao"] for t in tempos)
    falta = (duracao_alvo or 0) - total
    if not duracao_alvo or total >= 0.9 * duracao_alvo or falta <= 0:
        return tempos
    tempos[-1]["duracao"] = round(tempos[-1]["duracao"] + min(falta, extra_final_s), 3)
    falta -= min(falta, extra_final_s)
    if falta > 0 and len(tempos) > 1:
        cada = min(extra_cena_s, falta / (len(tempos) - 1))
        for t in tempos[:-1]:
            t["duracao"] = round(t["duracao"] + cada, 3)
    inicio = 0.0
    for t in tempos:
        t["inicio"] = round(inicio, 3)
        inicio += t["duracao"]
    return tempos


def _montar(cenas, saida, pasta, proporcao, largura, altura, trilha, bpm, primeira_batida_s, c, duracao_alvo):
    # 1. Fala útil de cada cena e tempos
    falas = []
    for i, cena in enumerate(cenas, 1):
        fala = trecho_falado(cena["voz"]) if cena.get("voz") else None
        if fala and fala[1] <= fala[0]:
            if cena.get("narracao"):
                raise ErroMontagem(f"cena {i}: não encontrei fala no arquivo de voz (está mudo?)")
            fala = None
        falas.append(fala)
    tempos = planejar_tempos([(f[1] - f[0]) if f else 0 for f in falas], [cena.get("duracao") for cena in cenas], c)
    tempos = alinhar_ao_tempo(completar_duracao(tempos, duracao_alvo), bpm, primeira_batida_s, c)
    total = round(tempos[-1]["inicio"] + tempos[-1]["duracao"], 3)
    t = c["transicao_s"] if len(cenas) > 1 else 0.0

    # 2. Clipes no tamanho e duração certos (cada um, menos o último, cobre também a transição)
    clipes, congelados = [], []
    for i, (cena, tp) in enumerate(zip(cenas, tempos)):
        destino = pasta / f"clipe_{i + 1:02d}.mp4"
        comprimento = tp["duracao"] + (t if i < len(cenas) - 1 else 0.0)
        congelados.append(_clipe(cena["video"], destino, comprimento, largura, altura, c))
        clipes.append(destino)

    # 3. Legendas e textos na tela
    estilo = estilo_legenda(largura, altura, proporcao)
    legendas, textos_tela = [], []
    for cena, tp, fala in zip(cenas, tempos, falas):
        fim_cena = tp["inicio"] + tp["duracao"]
        if fala and cena.get("narracao"):
            deslocamento = tp["inicio"] + tp["fala_em"] - fala[0]  # posição do arquivo de voz na linha do tempo
            legendas += distribuir_legendas(
                cena["narracao"], fala[0] + deslocamento, fala[1] + deslocamento,
                [(a + deslocamento, b + deslocamento) for a, b in fala[2]], estilo["max_chars"], fim_cena)
        if cena.get("texto_tela"):
            textos_tela.append((tp["inicio"] + 0.1, fim_cena, linhas_tela(cena["texto_tela"], proporcao)))
    (pasta / "legendas.ass").write_text(gerar_ass(legendas, textos_tela, largura, altura, proporcao, c["fonte"],
                                                  karaoke=bool(c.get("karaoke"))),
                                        encoding="utf-8")
    (pasta / "legendas.srt").write_text(gerar_srt(legendas), encoding="utf-8")

    # 4. Voz: cada fala na sua posição
    voz = pasta / "voz.wav"
    entradas, filtros, rotulos = [], [], []
    for i, (cena, tp, fala) in enumerate(zip(cenas, tempos, falas)):
        if not fala:
            continue
        atraso = round((tp["inicio"] + tp["fala_em"]) * 1000)
        n = len(entradas) // 4
        entradas += ["-ss", f"{fala[0]:.3f}", "-i", str(cena["voz"])]  # pula o silêncio do começo da voz
        # Iguala o nível das falas (provedores de voz diferentes saem com volumes diferentes).
        nivel = medir_volume(cena["voz"])["lufs"]
        ganho = 0.0 if nivel is None else max(-20.0, min(30.0, VOZ_LUFS - nivel))
        filtros.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={ganho:.2f}dB,"
                       f"adelay={atraso}:all=1[v{n}]")
        rotulos.append(f"[v{n}]")
    if rotulos:
        filtros.append(f"{''.join(rotulos)}amix=inputs={len(rotulos)}:normalize=0:duration=longest,"
                       f"apad,atrim=0:{total}[voz]")
    else:
        entradas, filtros = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"], [f"[0:a]atrim=0:{total}[voz]"]
    _ff([*entradas, "-filter_complex", ";".join(filtros), "-map", "[voz]", "-c:a", "pcm_f32le", str(voz)])
    medida_voz = medir_volume(voz) if rotulos else {"lufs": None, "pico_dbtp": None}

    # 5. Trilha abaixo da voz e abaixando quando ela entra
    info_trilha, mistura = None, voz
    for velho in ("trilha_bruta.wav", "trilha.wav", "mistura.wav"):  # de uma montagem anterior na mesma pasta
        (pasta / velho).unlink(missing_ok=True)
    if trilha:
        bruta = pasta / "trilha_bruta.wav"
        _ff(["-stream_loop", "-1", "-t", f"{total}", "-i", str(trilha), "-vn", "-af",
             "aformat=sample_rates=48000:channel_layouts=stereo", "-c:a", "pcm_f32le", str(bruta)])
        nivel = medir_volume(bruta)["lufs"]
        if nivel is None:
            raise ErroMontagem("a trilha está em silêncio")
        referencia = medida_voz["lufs"] if medida_voz["lufs"] is not None else c["lufs"] + c["trilha_lu_abaixo"]
        ganho = referencia - c["trilha_lu_abaixo"] - nivel
        final_trilha = pasta / "trilha.wav"
        for volta in range(3):  # o abaixamento muda o nível: mede e corrige até ficar perto do alvo
            saida_fade = max(0.0, total - 1.5)
            _ff(["-i", str(bruta), "-i", str(voz), "-filter_complex",
                 f"[0:a]volume={ganho:.2f}dB[m];[m][1:a]sidechaincompress=threshold=0.02:ratio=6:attack=15:"
                 f"release=350,afade=t=in:d=0.5,afade=t=out:st={saida_fade:.3f}:d=1.5[t]",
                 "-map", "[t]", "-c:a", "pcm_f32le", str(final_trilha)])
            medida = medir_volume(final_trilha)["lufs"]
            diferenca = None if medida is None or medida_voz["lufs"] is None else medida_voz["lufs"] - medida
            if diferenca is None or c["trilha_lu_minimo"] <= diferenca <= c["trilha_lu_abaixo"] + 1.5 or volta == 2:
                break
            ganho += diferenca - c["trilha_lu_abaixo"]
        info_trilha = {"arquivo": str(trilha), "ganho_db": round(ganho, 2), "lufs": medida,
                       "voz_menos_trilha_lu": None if diferenca is None else round(diferenca, 1), "bpm": bpm}
        mistura = pasta / "mistura.wav"
        _ff(["-i", str(voz), "-i", str(final_trilha), "-filter_complex",
             "[0:a][1:a]amix=inputs=2:normalize=0:duration=first[a]", "-map", "[a]", "-c:a", "pcm_f32le",
             str(mistura)])

    # 6. Volume final
    audio = pasta / "audio_final.wav"
    if medida_voz["lufs"] is None and not trilha:
        shutil.copyfile(mistura, audio)  # vídeo sem som algum: nada a normalizar
    else:
        _loudnorm(mistura, audio, c)

    # 7. Imagem + transições + legendas + áudio
    entradas = []
    for clipe in clipes:
        entradas += ["-i", clipe.name]
    entradas += ["-i", audio.name]
    if len(clipes) == 1:
        cadeia, ultimo = "", "[0:v]"
    else:
        partes, ultimo = [], "[0:v]"
        for k in range(1, len(clipes)):
            tipo = transicao_da_cena(cenas[k].get("clima")) if c["transicao"] == "auto" else c["transicao"]
            partes.append(f"{ultimo}[{k}:v]xfade=transition={tipo}:duration={t}:"
                          f"offset={tempos[k]['inicio']:.3f}[x{k}]")
            ultimo = f"[x{k}]"
        cadeia = ";".join(partes) + ";"
    filtro = f"{cadeia}{ultimo}ass=legendas.ass,format=yuv420p[v]"
    _ff([*entradas, "-filter_complex", filtro, "-map", "[v]", "-map", f"{len(clipes)}:a", "-t", f"{total}",
         "-c:v", "libx264", "-preset", c["preset"], "-crf", str(c["crf"]), "-r", str(c["fps"]),
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(saida)], cwd=pasta)

    return {
        "arquivo": str(saida), "proporcao": proporcao, "largura": largura, "altura": altura,
        "duracao_s": total, "tempos": tempos, "congelado_s": congelados,
        "cortes_na_batida": sum(1 for tp in tempos if tp.get("na_batida")),
        "legendas": [{"inicio": a, "fim": b, "linhas": linhas} for a, b, linhas in legendas],
        "textos_tela": [{"inicio": a, "fim": b, "linhas": linhas} for a, b, linhas in textos_tela],
        "estilo_legenda": estilo, "voz": medida_voz, "trilha": info_trilha,
        "sincronia": dict(zip(("desvios", "problemas"), sincronia(legendas, voz))) if legendas else None,
        "pasta_trabalho": str(pasta), "fps": c["fps"],
    }


# ---------------------------------------------------------------- verificação (eliminatórios da spec 03 §3.6)

def _sondar(arquivo):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name,pix_fmt,width,height", "-of", "json", str(arquivo)],
                       capture_output=True, stdin=subprocess.DEVNULL, text=True)
    try:
        return json.loads(r.stdout).get("streams", [])
    except json.JSONDecodeError:
        return []


def verificar_montagem(resultado, duracao_pedida=None, voz=None):
    """Mede o arquivo pronto e devolve {"aprovado", "problemas", "medidas"}.

    voz: arquivo só com a narração (padrão: voz.wav da pasta de trabalho, se ainda existir) — usado para
    conferir a sincronia: cada legenda começa até 0,3 s de uma entrada real de fala e nenhuma fica na tela
    durante um silêncio longo.
    """
    arquivo = Path(resultado["arquivo"])
    problemas, medidas = [], {}
    fluxos = _sondar(arquivo)
    video = next((f for f in fluxos if f.get("codec_type") == "video"), None)
    audio = next((f for f in fluxos if f.get("codec_type") == "audio"), None)
    if not video or not audio:
        problemas.append("o arquivo precisa ter vídeo e áudio")
    else:
        if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac" or video.get("pix_fmt") != "yuv420p":
            problemas.append(f"formato {video.get('codec_name')}/{audio.get('codec_name')}/{video.get('pix_fmt')} "
                             "(precisa h264/aac/yuv420p)")
        medidas["resolucao"] = f"{video.get('width')}x{video.get('height')}"
        if (video.get("width"), video.get("height")) not in {(1080, 1920), (1920, 1080), (1080, 1080), (1080, 1350)}:
            problemas.append(f"resolução {medidas['resolucao']} (precisa 1080×1920 ou 1920×1080)")
    dur = duracao(arquivo)
    medidas["duracao_s"] = round(dur, 2)
    if duracao_pedida and abs(dur - duracao_pedida) > 0.1 * duracao_pedida:
        problemas.append(f"duração {dur:.1f} s fora de ±10% do pedido ({duracao_pedida} s)")
    if audio:
        vol = medir_volume(arquivo)
        medidas.update(lufs=vol["lufs"], pico_dbtp=vol["pico_dbtp"])
        if vol["lufs"] is None or abs(vol["lufs"] - PADROES["lufs"]) > 1.0:
            problemas.append(f"volume {vol['lufs']} LUFS (precisa −14 ±1)")
        if vol["pico_dbtp"] is not None and vol["pico_dbtp"] > -1.0:
            problemas.append(f"pico {vol['pico_dbtp']} dBTP (máx. −1)")

    legendas = [(l["inicio"], l["fim"], l["linhas"]) for l in resultado.get("legendas", [])]
    estilo = resultado.get("estilo_legenda") or {}
    problemas += checar_legendas(legendas, estilo.get("max_chars", 42))
    if estilo and resultado.get("altura"):
        h = resultado["altura"]
        cima, baixo = estilo["area_segura"]
        base = h - estilo["margem_baixo"]  # linha de baixo da legenda
        topo = base - 2 * estilo["tamanho"] * 1.25
        medidas["legenda_px"] = [round(topo), base]
        if base > h * (1 - baixo) or topo < h * cima or estilo["margem_cima"] < h * cima:
            problemas.append("legenda fora da área segura")

    trilha = resultado.get("trilha")
    if trilha:
        dif = trilha.get("voz_menos_trilha_lu")
        medidas["voz_menos_trilha_lu"] = dif
        if dif is not None and dif < PADROES["trilha_lu_minimo"]:
            problemas.append(f"trilha só {dif} LU abaixo da voz (mín. 10)")

    for n, t in enumerate(resultado.get("textos_tela", []), 1):
        if len(t["linhas"]) > LIMITES_LEGENDA["linhas"]:
            problemas.append(f"texto na tela {n} com {len(t['linhas'])} linhas (máx. 2): encurte")

    voz = Path(voz) if voz else Path(resultado.get("pasta_trabalho", "")) / "voz.wav"
    if legendas:
        if voz.is_file():  # mede de novo (as legendas podem ter mudado depois da montagem)
            desvios, problemas_sinc = sincronia(legendas, voz)
        elif resultado.get("sincronia"):
            desvios, problemas_sinc = resultado["sincronia"]["desvios"], resultado["sincronia"]["problemas"]
        else:
            desvios, problemas_sinc = [], ["sincronia das legendas não medida (falta a faixa de voz)"]
        medidas["sincronia_max_s"] = round(max(desvios), 2) if desvios else None
        problemas += problemas_sinc
    return {"aprovado": not problemas, "problemas": problemas, "medidas": medidas}


def sincronia(legendas, voz, tolerancia=TOLERANCIA_SINCRONIA_S):
    """(desvios, problemas): cada legenda começa perto de fala real e não aparece durante silêncio longo."""
    total = duracao(voz)
    silencios = pausas(voz, limiar_silencio(voz), minimo_s=0.15)
    # Entradas de fala = fins de silêncio (e o começo do arquivo, se já começa falando).
    entradas = [b for a, b in silencios if b < total - 0.05]
    if not silencios or silencios[0][0] > 0.05:
        entradas.insert(0, 0.0)
    desvios, problemas = [], []
    for n, (ini, fim, _) in enumerate(legendas, 1):
        falando = not any(a - 1e-3 <= ini <= b - 1e-3 for a, b in silencios)
        desvio = 0.0 if falando else min((abs(e - ini) for e in entradas), default=float("inf"))
        desvios.append(desvio)
        if desvio > tolerancia:
            problemas.append(f"legenda {n} começa {desvio:.2f} s longe da fala (máx. {tolerancia} s)")
        # Legenda pode ficar um pouco após a fala (leitura); mais de 1 s num silêncio longo é erro.
        longos = [(a, b) for a, b in silencios if b - a >= 1.0 and min(fim, b) - max(ini, a) > 1.0]
        if longos:
            problemas.append(f"legenda {n} fica na tela durante silêncio de {longos[0][1] - longos[0][0]:.1f} s")
    return desvios, problemas

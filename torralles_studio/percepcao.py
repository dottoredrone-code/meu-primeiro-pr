"""Percepção: faz a IA "assistir" e "ouvir" um vídeo.

Junta, num relatório, o que um avaliador precisa:
- olhos: quadros com marcação de tempo (incluindo os de cada corte) e uma folha de contato;
- ouvidos técnicos: volume (LUFS), pico, silêncios, telas pretas e congelamentos;
- transcrição: Gemini (com GEMINI_API_KEY) ou Whisper local (faster-whisper), o que estiver disponível.
"""

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .rede import ErroProvedor, post_json


def _ff(*args, capturar_stderr=False):
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ErroProvedor(f"ffmpeg falhou: {proc.stderr.strip()[-300:]}")
    return proc.stderr if capturar_stderr else proc.stdout


def _sondar(video):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(video)],
        capture_output=True, text=True, check=True,
    )
    dados = json.loads(proc.stdout)
    info = {"duracao_s": round(float(dados["format"]["duration"]), 2), "tem_audio": False}
    for s in dados.get("streams", []):
        if s["codec_type"] == "video":
            num, den = s["r_frame_rate"].split("/")
            info.update(largura=s["width"], altura=s["height"], fps=round(int(num) / int(den), 2))
        elif s["codec_type"] == "audio":
            info["tem_audio"] = True
    return info


def _cortes(video, limiar_seco=10, limiar_suave=5, amostras_por_s=2, juntar_s=1.0):
    """Cortes secos (quadro a quadro) e transições suaves (fade, slide: comparando quadros espaçados)."""
    tempos = []
    for filtro in (f"scdet=threshold={limiar_seco}", f"fps={amostras_por_s},scdet=threshold={limiar_suave}"):
        log = _ff("-i", str(video), "-vf", filtro, "-an", "-f", "null", "-", capturar_stderr=True)
        tempos += [float(t) for t in re.findall(r"lavfi\.scd\.time:\s*([\d.]+)", log)]
    cortes = []
    for t in sorted(tempos):
        if not cortes or t - cortes[-1] > juntar_s:
            cortes.append(round(t, 2))
    return cortes


def _intervalos(log, inicio, fim):
    comecos = [float(x) for x in re.findall(rf"{inicio}:\s*([\d.]+)", log)]
    finais = [float(x) for x in re.findall(rf"{fim}:\s*([\d.]+)", log)]
    return [[round(a, 2), round(b, 2)] for a, b in zip(comecos, finais)]


def _som(video):
    log = _ff("-i", str(video), "-af", "silencedetect=noise=-40dB:d=0.7,ebur128=peak=true", "-vn", "-f", "null", "-",
              capturar_stderr=True)
    resumo = log[log.rfind("Summary:"):] if "Summary:" in log else log
    lufs = re.search(r"I:\s*(-?[\d.]+) LUFS", resumo)
    pico = re.search(r"Peak:\s*(-?[\d.]+|-inf) dBFS", resumo)
    return {
        "lufs_integrado": float(lufs.group(1)) if lufs else None,
        "pico_dbfs": float(pico.group(1)) if pico and pico.group(1) != "-inf" else None,
        "silencios_s": _intervalos(log, "silence_start", "silence_end"),
    }


def _imagem(video):
    log = _ff("-i", str(video), "-vf", "blackdetect=d=0.2:pix_th=0.1,freezedetect=n=0.003:d=1", "-an", "-f", "null", "-",
              capturar_stderr=True)
    return {
        "telas_pretas_s": _intervalos(log, "black_start", "black_end"),
        "congelamentos_s": _intervalos(log, r"lavfi\.freezedetect\.freeze_start", r"lavfi\.freezedetect\.freeze_end"),
    }


def _quadros(video, pasta, tempos):
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for t in tempos:
        arq = pasta / f"quadro_{t:07.2f}s.jpg"
        _ff("-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(arq))
        arquivos.append(str(arq))
    return arquivos


def _folha_contato(video, saida, duracao, colunas=6):
    passo = max(duracao / (colunas * 2), 0.5)
    fonte = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    texto = f"drawtext=fontfile={fonte}:text='%{{pts\\:hms}}':x=10:y=10:fontsize=36:fontcolor=white:box=1:boxcolor=black@0.6"
    _ff("-y", "-loglevel", "error", "-i", str(video), "-vf",
        f"fps=1/{passo:.3f},scale=360:-2,{texto},tile={colunas}x2:padding=6:color=white", "-frames:v", "1", str(saida))
    return str(saida)


def transcrever(video, pasta):
    """Tenta Gemini e depois Whisper local. Devolve {"texto", "motor"} ou {"texto": None, "motivo"}."""
    motivos = []
    if os.environ.get("GEMINI_API_KEY"):
        try:
            return _transcrever_gemini(video, pasta)
        except Exception as e:  # cai para o próximo motor
            motivos.append(f"gemini: {e}")
    else:
        motivos.append("gemini: falta GEMINI_API_KEY")
    try:
        from faster_whisper import WhisperModel  # noqa: F401

        return _transcrever_whisper(video)
    except ImportError:
        motivos.append("whisper: instale faster-whisper")
    except Exception as e:
        motivos.append(f"whisper: {e}")
    return {"texto": None, "motivo": "; ".join(motivos)}


def _transcrever_gemini(video, pasta):
    audio = pasta / "audio.mp3"
    _ff("-y", "-loglevel", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(audio))
    modelo = os.environ.get("GEMINI_MODELO_PERCEPCAO", "gemini-3.6-flash")
    r = post_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
        {"contents": [{"parts": [
            {"inline_data": {"mime_type": "audio/mp3", "data": base64.b64encode(audio.read_bytes()).decode()}},
            {"text": "Transcreva fielmente o áudio em português do Brasil, com marcação [mm:ss] no início de cada frase. "
                     "Depois, numa linha 'SONS:', liste músicas, efeitos e ruídos percebidos com o momento."},
        ]}]},
        {"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        300,
    )
    texto = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
    return {"texto": texto, "motor": f"gemini:{modelo}"}


def _transcrever_whisper(video):
    from faster_whisper import WhisperModel

    modelo = WhisperModel(os.environ.get("WHISPER_MODELO", "small"), compute_type="int8")
    segmentos, _ = modelo.transcribe(str(video), language="pt")
    linhas = [f"[{int(s.start // 60):02d}:{s.start % 60:04.1f}] {s.text.strip()}" for s in segmentos]
    return {"texto": "\n".join(linhas), "motor": "faster-whisper"}


def analisar_video(video, pasta_saida, transcrever_audio=True):
    """Gera o relatório de percepção de um vídeo e salva em pasta_saida/percepcao.json."""
    if not shutil.which("ffmpeg"):
        raise ErroProvedor("FFmpeg não instalado")
    video, pasta = Path(video), Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)

    info = _sondar(video)
    cortes = _cortes(video)
    dur = info["duracao_s"]
    marcas = sorted({0.3, round(dur / 2, 2), round(max(dur - 0.5, 0), 2), *[min(c + 0.3, dur - 0.1) for c in cortes]})
    relatorio = {
        "arquivo": str(video),
        **info,
        "cortes_s": cortes,
        "cortes_por_minuto": round(len(cortes) / dur * 60, 1) if dur else 0,
        **_imagem(video),
        "som": _som(video) if info["tem_audio"] else None,
        "quadros": _quadros(video, pasta / "quadros", marcas),
        "folha_contato": _folha_contato(video, pasta / "folha_contato.jpg", dur),
        "transcricao": transcrever(video, pasta) if transcrever_audio and info["tem_audio"] else None,
    }
    (pasta / "percepcao.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2))
    return relatorio

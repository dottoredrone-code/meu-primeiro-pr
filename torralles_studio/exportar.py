"""Exportação para o CapCut (K23, D5): pasta pronta para arrastar e editar sem retrabalho.

O CapCut não tem formato de projeto público e estável, então a exportação é uma pasta organizada:
- `01_clipes/`: cenas numeradas, já cortadas na duração exata de cada uma (lado a lado = linha do tempo);
- `02_audio/narracao.wav` e `02_audio/trilha.wav`: faixas já alinhadas ao tempo do vídeo (começam em 0 s);
- `03_legendas/legendas.srt`: importável no CapCut (Legendas → Importar legendas);
- `video_final.mp4`: referência do resultado montado pelo Studio;
- `LEIA-ME.txt`: passo a passo, tempos de cada cena e créditos.
"""

import json
import shutil
import subprocess
from pathlib import Path

from .rede import ErroProvedor


class ErroExportacao(Exception):
    """Faltam arquivos da montagem para exportar (a mensagem diz quais)."""


def _tempo(s):
    return f"{int(s // 60):02d}:{s % 60:05.2f}"


def _ganho_final(trabalho):
    """Ganho (dB) que a normalização final deu à mistura, para as faixas soltas soarem como no vídeo pronto."""
    from .montagem import medir_volume

    antes = trabalho / "mistura.wav" if (trabalho / "mistura.wav").is_file() else trabalho / "voz.wav"
    depois = trabalho / "audio_final.wav"
    if not (antes.is_file() and depois.is_file()):
        return 0.0
    a, d = medir_volume(antes)["lufs"], medir_volume(depois)["lufs"]
    return round(d - a, 2) if a is not None and d is not None else 0.0


def _audio(origem, destino, ganho):
    proc = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(origem), "-af", f"volume={ganho}dB,alimiter=limit=0.84:level=disabled",  # pico ≤ −1,5 dB, sem estourar
                           "-c:a", "pcm_s16le", str(destino)], capture_output=True, stdin=subprocess.DEVNULL, text=True)
    if proc.returncode != 0:
        raise ErroProvedor(f"ffmpeg falhou no áudio {Path(destino).name}: {proc.stderr.strip()[-200:]}")


def exportar_capcut(resultado, destino, *, creditos=None, titulo=None, pasta_trabalho=None):
    """Cria a pasta para o CapCut a partir do resultado de `montagem.montar` (com pasta de trabalho).

    pasta_trabalho: onde estão os arquivos da montagem, se a pasta do vídeo foi movida depois.
    """
    trabalho = Path(pasta_trabalho or resultado.get("pasta_trabalho") or "")
    tempos = resultado.get("tempos") or []
    clipes = [trabalho / f"clipe_{i:02d}.mp4" for i in range(1, len(tempos) + 1)]
    faltando = [c.name for c in clipes if not c.is_file()] + ([] if (trabalho / "voz.wav").is_file() else ["voz.wav"])
    if not tempos or faltando:
        raise ErroExportacao("faltam os arquivos de trabalho da montagem: "
                             + (", ".join(faltando[:5]) or "sem cenas") + ". Rode o produzir de novo "
                             "(ele reaproveita o que já existe e refaz só a montagem).")
    destino = Path(destino)
    if destino.exists():
        shutil.rmtree(destino)
    pastas = {n: destino / n for n in ("01_clipes", "02_audio", "03_legendas")}
    for p in pastas.values():
        p.mkdir(parents=True)

    fps = resultado.get("fps") or 30
    for i, (clipe, tp) in enumerate(zip(clipes, tempos), 1):
        # os clipes da montagem têm a transição a mais no fim; aqui cada um fica com a duração exata da cena,
        # contada em quadros acumulados (arredondar cena a cena faria os cortes atrasarem em vídeos longos)
        quadros = round((tp["inicio"] + tp["duracao"]) * fps) - round(tp["inicio"] * fps)
        proc = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(clipe), "-vf", "tpad=stop_mode=clone:stop=3",
                               "-frames:v", str(max(1, quadros)),  # tpad: se faltar 1 quadro no fim, repete o último
                               "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-an",
                               str(pastas["01_clipes"] / f"cena_{i:02d}.mp4")], capture_output=True, stdin=subprocess.DEVNULL, text=True)
        if proc.returncode != 0:
            raise ErroProvedor(f"ffmpeg falhou ao cortar a cena {i}: {proc.stderr.strip()[-200:]}")
    ganho = _ganho_final(trabalho)  # faixas já no volume do vídeo pronto (−14 LUFS juntas)
    _audio(trabalho / "voz.wav", pastas["02_audio"] / "narracao.wav", ganho)
    # só a trilha DESTA montagem (com crédito no relatório); arquivo de montagem antiga não entra
    tem_trilha = bool(resultado.get("trilha")) and (trabalho / "trilha.wav").is_file()
    if tem_trilha:
        _audio(trabalho / "trilha.wav", pastas["02_audio"] / "trilha.wav", ganho)
    if (trabalho / "legendas.srt").is_file():
        shutil.copyfile(trabalho / "legendas.srt", pastas["03_legendas"] / "legendas.srt")
    if Path(resultado.get("arquivo") or "").is_file():
        shutil.copyfile(resultado["arquivo"], destino / "video_final.mp4")

    linhas = [f"{i:02d}  {_tempo(tp['inicio'])} → {_tempo(tp['inicio'] + tp['duracao'])}  ({tp['duracao']:.2f} s)"
              for i, tp in enumerate(tempos, 1)]
    leia = [
        f"Torralles Studio — exportação para o CapCut{f': {titulo}' if titulo else ''}",
        "",
        "Como montar no CapCut (Windows):",
        f"1. Novo projeto, proporção {resultado.get('proporcao', '9:16')}.",
        "2. Importe a pasta 01_clipes e arraste as cenas para a linha do tempo, em ordem (cena_01, cena_02…),",
        "   uma colada na outra, começando em 0 s.",
        "3. Arraste 02_audio/narracao.wav para uma faixa de áudio começando em 0 s."
        + (" Faça o mesmo com 02_audio/trilha.wav (já está abaixo da voz)." if tem_trilha else ""),
        "   Os volumes já estão como no video_final.mp4: não precisa ajustar.",
        "4. Legendas → Importar legendas → 03_legendas/legendas.srt.",
        "5. Agora é só editar: transições, efeitos, textos. Compare com video_final.mp4 se precisar.",
        "",
        "Tempo de cada cena:",
        *linhas,
        "",
        f"Duração total: {resultado.get('duracao_s', 0):.1f} s",
    ]
    if creditos:
        leia += ["", creditos]
    (destino / "LEIA-ME.txt").write_text("\n".join(leia) + "\n", encoding="utf-8")
    (destino / "linha_do_tempo.json").write_text(json.dumps(
        {"proporcao": resultado.get("proporcao"), "duracao_s": resultado.get("duracao_s"),
         "cenas": [{"arquivo": f"01_clipes/cena_{i:02d}.mp4", **tp} for i, tp in enumerate(tempos, 1)],
         "audio": ["02_audio/narracao.wav"] + (["02_audio/trilha.wav"] if tem_trilha else []),
         "legendas": "03_legendas/legendas.srt"}, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino

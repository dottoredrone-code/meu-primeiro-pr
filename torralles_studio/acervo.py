"""Acervo de mídia para os agentes (K47, spec 16).

- `importar_pasta`: põe uma pasta de trilhas, efeitos, sonoplastias, ambientes, imagens ou vídeos na biblioteca,
  com a licença conferida (regras da biblioteca), **medindo cada arquivo** com o FFmpeg e etiquetando por tipo,
  clima, energia, loop e orientação. As medidas ficam guardadas (`ativos.medidas_json`): ninguém mede de novo.
- `buscar`: acha os melhores itens pelo que o projeto pede (tipo, clima, energia, duração, orientação, palavras).
- Cada importação anota a licença da fonte em `<biblioteca>/licencas/` (D18), com cópia do texto se houver.

Etiquetas (por perfil, como o resto da biblioteca): `tipo-<tipo>`, `clima-<clima>`, `energia-<baixa|media|alta>`,
`loop`, `orientacao-<vertical|horizontal|quadrado>` e as palavras do nome do arquivo e das pastas.
Efeitos ganham também as etiquetas antigas do `importar-sons` (`efeito`, `som-<nome>`), para a montagem achá-los.
Só biblioteca padrão + FFmpeg.
"""

import array
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import ff
from .biblioteca import TIPOS, _etiqueta, _limpo, conferir_licenca
from .efeitos import etiquetas_do_nome
from .rede import ErroProvedor

# tipo do acervo → tipo de arquivo da biblioteca
TIPOS_ACERVO = {"trilha": "audio", "efeito": "audio", "sonoplastia": "audio", "ambiente": "audio",
                "imagem": "imagem", "video": "video"}
CLIMAS = ("calmo", "alegre", "epico", "tenso", "inspirador", "curioso", "reflexivo")  # os mesmos do roteiro
# Palavras de nome de arquivo (pt e en) que sugerem o clima. A primeira que aparecer vale.
_PALAVRAS_CLIMA = {
    "calmo": {"calmo", "calma", "calm", "relax", "relaxing", "chill", "peaceful", "soft", "lofi", "ambient"},
    "alegre": {"alegre", "feliz", "happy", "upbeat", "fun", "cheerful", "joyful", "bright"},
    "epico": {"epico", "epic", "cinematic", "trailer", "heroic", "orchestral"},
    "tenso": {"tenso", "tensao", "tense", "suspense", "dark", "horror", "thriller", "mystery"},
    "inspirador": {"inspirador", "inspiring", "inspirational", "uplifting", "motivational", "hope"},
    "curioso": {"curioso", "curious", "playful", "quirky", "funny"},
    "reflexivo": {"reflexivo", "reflective", "sad", "emotional", "melancholy", "piano", "nostalgic"},
}
NIVEIS_ENERGIA = ("baixa", "media", "alta")
ORIENTACOES = ("vertical", "horizontal", "quadrado")
SEGUNDOS_MEDIDOS = 60   # lê no máximo 1 min do áudio (a duração real vem do ffprobe)
PRAZO_MEDIR_S = 120


class ErroAcervo(ValueError):
    pass


# ------------------------------------------------------------------ medidas

def nivel_energia(energia):
    """0–1 → 'baixa' (< 0,4), 'media' (< 0,7) ou 'alta'."""
    if energia is None:
        return None
    return "baixa" if energia < 0.4 else "media" if energia < 0.7 else "alta"


def orientacao(largura, altura):
    if not largura or not altura:
        return None
    razao = largura / altura
    return "vertical" if razao < 0.9 else "horizontal" if razao > 1.1 else "quadrado"


def _sondar(arquivo):
    from .percepcao import sondar
    return sondar(arquivo, "format=duration:stream=codec_type,width,height:stream_disposition=attached_pic")


def _duracao(dados):
    try:
        return round(float(dados.get("format", {}).get("duration")), 2)
    except (TypeError, ValueError):
        return None


def _energia_audio(arquivo):
    """(energia 0–1, rms por janela de 10 ms) dos primeiros 60 s. Silêncio → ErroProvedor."""
    proc = ff.rodar(["ffmpeg", "-nostdin", "-v", "error", "-t", str(SEGUNDOS_MEDIDOS), "-i", str(arquivo), "-ac", "1",
                     "-ar", "4000", "-f", "s16le", "-"], prazo=PRAZO_MEDIR_S, binario=True)
    if proc.returncode != 0 or not proc.stdout:
        raise ErroProvedor("não consegui ler o áudio")
    amostras = array.array("h")
    amostras.frombytes(proc.stdout[: len(proc.stdout) // 2 * 2])
    passo = 40
    janelas = [math.sqrt(sum(x * x for x in amostras[i:i + passo]) / passo) / 32768
               for i in range(0, len(amostras) - passo + 1, passo)]
    if not janelas or max(janelas) <= 0:
        raise ErroProvedor("áudio em silêncio")
    rms = math.sqrt(sum(e * e for e in janelas) / len(janelas))
    db = 20 * math.log10(max(rms, 1e-9))
    if db < -60:
        raise ErroProvedor(f"áudio quase em silêncio ({db:.0f} dB)")
    return round(min(1.0, max(0.0, (db + 40) / 32)), 2), janelas  # mesma escala da trilha (−40 dB → 0, −8 → 1)


def _parece_loop(janelas, duracao):
    """Fim e começo com o mesmo nível (até 3 dB) e sem silêncio: a emenda não pula. Só para sons de 2 s ou mais
    lidos até o fim (o loop é um indício; o nome com 'loop' também vale)."""
    if not duracao or duracao < 2 or duracao > SEGUNDOS_MEDIDOS or len(janelas) < 60:
        return False
    def db(trecho):
        return 20 * math.log10(max(math.sqrt(sum(e * e for e in trecho) / len(trecho)), 1e-9))
    ini, fim = db(janelas[:30]), db(janelas[-30:])
    return ini > -45 and fim > -45 and abs(ini - fim) <= 3


def medir(arquivo, tipo):
    """Medidas do arquivo para o tipo do acervo. Áudio: duracao_s, energia, bpm (trilha), loop.
    Imagem e vídeo: largura, altura, orientacao (vídeo também duracao_s). Arquivo ilegível → ErroProvedor."""
    base = TIPOS_ACERVO[tipo]
    dados = _sondar(arquivo)
    duracao = _duracao(dados)
    if base == "audio":
        if not any(s.get("codec_type") == "audio" for s in dados.get("streams", [])):
            raise ErroProvedor("o arquivo não tem áudio")
        energia, janelas = _energia_audio(arquivo)
        medidas = {"duracao_s": duracao, "energia": energia, "loop": _parece_loop(janelas, duracao)}
        if tipo == "trilha":
            medidas["bpm"] = _bpm(arquivo, duracao)
        return medidas
    video = next((s for s in dados.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video or not video.get("width") or not video.get("height"):
        raise ErroProvedor("não consegui ler o tamanho da imagem")
    medidas = {"largura": int(video["width"]), "altura": int(video["height"]),
               "orientacao": orientacao(int(video["width"]), int(video["height"]))}
    if base == "video":
        if not duracao:
            raise ErroProvedor("o vídeo não tem duração legível")
        medidas["duracao_s"] = duracao
    return medidas


def _bpm(arquivo, duracao):
    """BPM pela medição da trilha (K21); trilha curta, sem batida clara ou ilegível → None."""
    if not duracao or duracao < 3:
        return None
    from .trilha import medir_ritmo
    try:
        return medir_ritmo(arquivo, SEGUNDOS_MEDIDOS).get("bpm")
    except ErroProvedor:
        return None


# ------------------------------------------------------------------ etiquetas

def _palavras(arquivo, pasta):
    """Palavras do nome do arquivo e das pastas abaixo da pasta importada (sem números soltos)."""
    rel = Path(arquivo).relative_to(pasta)
    partes = [*rel.parent.parts, rel.stem]
    return [p for parte in partes for p in _etiqueta(parte).split("-") if p and not p.isdigit()]


def clima_do_nome(palavras):
    for p in palavras:
        for clima, termos in _PALAVRAS_CLIMA.items():
            if p in termos:
                return clima
    return None


def etiquetas(arquivo, pasta, tipo, medidas, clima=None):
    palavras = _palavras(arquivo, pasta)
    clima = clima or clima_do_nome(palavras)
    tags = [f"tipo-{tipo}"]
    if clima:
        tags.append(f"clima-{clima}")
    if medidas.get("energia") is not None:
        tags.append(f"energia-{nivel_energia(medidas['energia'])}")
    if medidas.get("loop") or "loop" in palavras:
        tags.append("loop")
    if medidas.get("orientacao"):
        tags.append(f"orientacao-{medidas['orientacao']}")
    if tipo == "efeito":  # compatível com o importar-sons e a escolha de efeitos da montagem
        tags += etiquetas_do_nome(Path(arquivo).name)
    if tipo == "trilha":  # compatível com a escolha de trilha do `produzir` (busca "trilha" + clima)
        tags += ["trilha"] + ([clima] if clima else [])
    return list(dict.fromkeys(tags + palavras)), clima


# ------------------------------------------------------------------ licença da fonte

def _conferir_arquivo_licenca(arquivo_licenca):
    origem = Path(arquivo_licenca)
    if not origem.is_file():
        raise FileNotFoundError(f"arquivo de licença não encontrado: {origem}")
    return origem


def anotar_licenca(biblioteca, licenca, fonte, *, link=None, arquivo_licenca=None):
    """Guarda em <biblioteca>/licencas/ a licença da fonte (D18): um resumo e, se houver, cópia do texto."""
    codigo, regras = conferir_licenca(licenca)
    pasta = Path(biblioteca.raiz) / "licencas"
    pasta.mkdir(parents=True, exist_ok=True)
    nome = _etiqueta(fonte) or "fonte"
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    copia = None
    if arquivo_licenca:
        origem = _conferir_arquivo_licenca(arquivo_licenca)
        copia = pasta / f"{nome}-{codigo}{origem.suffix.lower() or '.txt'}"
        if copia.resolve() != origem.resolve():  # já é a cópia guardada: nada a copiar
            shutil.copyfile(origem, copia)
    with open(pasta / f"{nome}.txt", "a", encoding="utf-8") as f:
        f.write(f"{agora} · fonte: {_limpo(fonte)} · licença: {regras['nome']} ({codigo}) · "
                f"uso comercial: {'sim' if regras['comercial'] else 'não'} · crédito: "
                f"{'obrigatório' if regras['credito'] else 'não'}"
                + (f" · link: {_limpo(link)}" if link else "") + (f" · texto: {copia.name}" if copia else "") + "\n")
    return pasta / f"{nome}.txt"


# ------------------------------------------------------------------ importação

def importar_pasta(biblioteca, pasta, tipo, licenca, fonte, *, clima=None, link=None, autor=None, perfil=None,
                   arquivo_licenca=None, medir_arquivo=medir):
    """Guarda cada arquivo do tipo na pasta (e subpastas) no acervo, medido e etiquetado.

    Devolve (importados, problemas). Licença recusada: nada entra (lança ErroLicenca antes de abrir a pasta).
    """
    if tipo not in TIPOS_ACERVO:
        raise ErroAcervo(f"tipo {tipo!r} desconhecido (use: {', '.join(TIPOS_ACERVO)})")
    if clima is not None and clima not in CLIMAS:
        raise ErroAcervo(f"clima {clima!r} desconhecido (use: {', '.join(CLIMAS)})")
    conferir_licenca(licenca)
    if arquivo_licenca:
        _conferir_arquivo_licenca(arquivo_licenca)  # antes de importar: nada entra sem a licença anotada (D18)
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise FileNotFoundError(f"pasta não encontrada: {pasta}")
    extensoes = TIPOS[TIPOS_ACERVO[tipo]]
    arquivos = sorted(a for a in pasta.rglob("*") if a.is_file() and a.suffix.lower() in extensoes
                      and not a.name.endswith(".parcial"))
    importados, problemas = [], []
    for arq in arquivos:
        try:
            medidas = medir_arquivo(arq, tipo)
            tags, clima_arq = etiquetas(arq, pasta, tipo, medidas, clima)
            ativo = biblioteca.adicionar(arq, licenca, fonte, autor=autor, link=link, titulo=arq.stem, tags=tags,
                                         perfil=perfil, provedor="acervo",
                                         parametros={"tipo_acervo": tipo, "clima": clima_arq})
            medidas = {**(ativo.get("medidas") or {}), **medidas}  # mesmo arquivo com outro tipo: soma, não apaga
            biblioteca.gravar_medidas(ativo["hash"], medidas)
        except (ValueError, OSError, ErroProvedor) as e:  # licença, arquivo ilegível ou mudo: os outros seguem
            problemas.append(f"{arq.relative_to(pasta)}: {e}")
            continue
        ativo["medidas"] = medidas
        importados.append(ativo)
    if importados:
        anotar_licenca(biblioteca, licenca, fonte, link=link, arquivo_licenca=arquivo_licenca)
    return importados, problemas


# ------------------------------------------------------------------ busca

def buscar(biblioteca, *, tipo=None, clima=None, energia=None, duracao=None, orientacao=None, palavras=(),
           loop=None, perfil=None, limite=10):
    """Itens do acervo que atendem aos filtros, os melhores primeiro.

    duracao (s): trilha e ambiente preferem as que cobrem o tempo (a montagem faz o loop das curtas); efeito,
    sonoplastia e vídeo preferem a mais próxima. Sem medidas, o item vai para o fim.
    """
    for valor, aceitos, nome in ((tipo, TIPOS_ACERVO, "tipo"), (clima, CLIMAS, "clima"),
                                 (energia, NIVEIS_ENERGIA, "energia"), (orientacao, ORIENTACOES, "orientação")):
        if valor is not None and valor not in aceitos:
            raise ErroAcervo(f"{nome} {valor!r} desconhecido (use: {', '.join(aceitos)})")
    if int(limite) < 1:
        raise ErroAcervo("o limite precisa ser 1 ou mais")
    tags = [f"tipo-{tipo}"] if tipo else []
    if clima:
        tags.append(f"clima-{clima}")
    if energia:
        tags.append(f"energia-{energia}")
    if orientacao:
        tags.append(f"orientacao-{orientacao}")
    if loop:
        tags.append("loop")
    tags += [parte for p in palavras or () for parte in _etiqueta(p).split("-") if parte]
    base = TIPOS_ACERVO.get(tipo) if tipo else None
    achados = [a for a in biblioteca.buscar(tags, tipo=base, perfil=perfil, limite=1000)
               if any(t.startswith("tipo-") for t in a["tags"])]  # só o que entrou pelo acervo
    if loop is False:
        achados = [a for a in achados if "loop" not in a["tags"]]

    def nota(a):
        dur = (a.get("medidas") or {}).get("duracao_s")
        if duracao is None:
            return (0, 0)
        if dur is None:
            return (2, 0)
        if tipo in ("trilha", "ambiente"):
            return (0, dur - duracao) if dur >= duracao else (1, duracao - dur)
        return (0, abs(dur - duracao))
    return sorted(achados, key=nota)[: int(limite)]


def resumo(ativo, tipo=None, clima=None):
    """Dicionário enxuto para agentes (JSON): caminho, tipo, clima, medidas, licença e crédito.

    tipo/clima: os pedidos na busca (o mesmo arquivo pode ter entrado com mais de um tipo ou clima)."""
    tags = ativo.get("tags", [])
    return {
        "hash": ativo["hash"], "titulo": ativo.get("titulo"), "caminho": ativo.get("caminho"),
        "tipo": tipo or next((t[5:] for t in tags if t.startswith("tipo-")), None),
        "clima": clima or next((t[6:] for t in tags if t.startswith("clima-")), None),
        "medidas": ativo.get("medidas") or {}, "licenca": ativo["licenca"], "uso_comercial": ativo["uso_comercial"],
        "fonte": ativo["fonte"], "autor": ativo.get("autor"), "link": ativo.get("link"), "etiquetas": tags,
    }


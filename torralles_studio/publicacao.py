"""Material para postar o vídeo: capa com o título e texto pronto (título, descrição, hashtags, créditos).

Funções que os concorrentes (Opus Clip, Submagic, InVideo) entregam junto com o vídeo. Tudo grátis: a capa sai do
FFmpeg a partir da imagem da 1ª cena; o texto vem da cadeia `texto` (grátis primeiro) com reserva por regra, sem
chave nenhuma. Nada aqui publica: o Diego posta (D19).
"""

import json
import re
import unicodedata
from pathlib import Path

from . import ff

LIMITE_TITULO = 70
LIMITE_DESCRICAO = 600
MAX_HASHTAGS = 6
GENERICAS = {"#fyp", "#foryou", "#foryoupage", "#viral", "#trending", "#explore", "#reels", "#shorts", "#tiktok",
             "#paravoce", "#parati"}  # não falam do assunto: o prompt pede para evitar e a validação tira
_PALAVRAS_VAZIAS = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "um",
                    "uma", "para", "por", "com", "que", "se", "seu", "sua", "como", "mais", "muito", "isso", "esse",
                    "essa", "este", "esta", "ao", "aos", "é", "ou", "the", "of", "and", "to", "in"}


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def hashtag(palavra):
    limpa = re.sub(r"[^0-9A-Za-z]", "", _sem_acento(str(palavra)))
    return f"#{limpa.lower()}" if len(limpa) >= 3 else None


def _ass_texto(texto):
    return str(texto).replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def _quebrar(texto, por_linha=18):
    linhas, atual = [], ""
    for palavra in str(texto).split():
        if atual and len(atual) + 1 + len(palavra) > por_linha:
            linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    if atual:
        linhas.append(atual)
    return "\\N".join(linhas[:4])


def gerar_capa(imagem, titulo, saida, *, largura=1080, altura=1920, fonte="Arial", cor_destaque="&H0000E5FF"):
    """capa.jpg: imagem da cena com o título grande no terço de cima (área segura), contorno forte para ler no
    celular. Usa o filtro `ass` (o mesmo das legendas), que não precisa de arquivo de fonte no Windows."""
    imagem, saida = Path(imagem), Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    tamanho = max(60, int(largura * 0.085))
    margem_v = int(altura * 0.16)
    ass = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {largura}\nPlayResY: {altura}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        f"Style: Capa,{fonte},{tamanho},{cor_destaque},&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(4, tamanho // 12)},3,8,{int(largura * 0.08)},{int(largura * 0.08)},{margem_v},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:05.00,Capa,,0,0,0,,{_quebrar(_ass_texto(titulo).upper())}\n"
    )
    trabalho = saida.parent
    (trabalho / "capa.ass").write_text(ass, encoding="utf-8")
    filtro = (f"scale={largura}:{altura}:force_original_aspect_ratio=increase,crop={largura}:{altura},"
              "eq=brightness=-0.04:contrast=1.08,vignette=PI/4,ass=capa.ass")
    try:
        ff.ffmpeg(["-y", "-i", str(imagem.resolve()), "-vf", filtro, "-frames:v", "1", "-q:v", "2",
                   str(saida.resolve())], cwd=trabalho, falha="não deu para gerar a capa")
    finally:
        (trabalho / "capa.ass").unlink(missing_ok=True)
    return saida


def _hashtags_por_regra(roteiro, tema):
    palavras = re.findall(r"\w+", f"{tema} {roteiro.get('titulo', '')}".lower())
    vistas = []
    for p in palavras:
        if p in _PALAVRAS_VAZIAS or len(p) < 4:
            continue
        tag = hashtag(p)
        if tag and tag not in vistas:
            vistas.append(tag)
    return vistas[:MAX_HASHTAGS]


def texto_por_regra(roteiro, tema, creditos=None):
    """Reserva sem IA: título do roteiro, 1ª fala como descrição, CTA e hashtags do tema."""
    cenas = roteiro.get("cenas") or []
    primeira = (cenas[0].get("narracao") if cenas else "") or ""
    descricao = " ".join(x for x in (primeira, roteiro.get("cta") or "") if x).strip()
    return {"titulo": (roteiro.get("titulo") or tema)[:LIMITE_TITULO],
            "descricao": descricao[:LIMITE_DESCRICAO], "hashtags": _hashtags_por_regra(roteiro, tema),
            "creditos": creditos or "", "origem": "regra"}


def _validar_texto(bruto):
    texto = str(bruto).strip()
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim < inicio:
        raise ValueError("resposta sem JSON")
    dados = json.loads(texto[inicio:fim + 1])
    titulo = str(dados.get("titulo") or "").strip()
    descricao = str(dados.get("descricao") or "").strip()
    if not titulo or not descricao:
        raise ValueError("faltou título ou descrição")
    tags = [t for t in (hashtag(str(h).lstrip("#")) for h in (dados.get("hashtags") or []))
            if t and t not in GENERICAS]
    return {"titulo": titulo[:LIMITE_TITULO], "descricao": descricao[:LIMITE_DESCRICAO],
            "hashtags": list(dict.fromkeys(tags))[:MAX_HASHTAGS]}


def gerar_texto(roteador, roteiro, tema, *, creditos=None, perfil=None):
    """Título, descrição e hashtags em pt-BR. Só usa o que está no roteiro (nada inventado); sem IA, vale a regra."""
    falas = "\n".join(f"- {c.get('narracao', '')}" for c in roteiro.get("cenas") or [])
    evitar = ", ".join((getattr(perfil, "estilo", None) or {}).get("palavras_evitar") or [])
    prompt = (
        f"Tema: {tema}\nTítulo do roteiro: {roteiro.get('titulo', '')}\nCTA: {roteiro.get('cta', '')}\n"
        f"Narração:\n{falas}\n\n"
        "Escreva o texto para postar este vídeo curto (Reels, Shorts, TikTok), em português do Brasil, direto e "
        f"sem exagero. Título com até {LIMITE_TITULO} caracteres que desperte curiosidade; descrição com até "
        f"{LIMITE_DESCRICAO} caracteres que resume o vídeo e termina com o CTA; até {MAX_HASHTAGS} hashtags do "
        "assunto (sem # genéricas como #viral ou #fyp). Use só fatos que estão na narração: nada de números, "
        "promessas ou fontes que não estejam lá."
        + (f" Não use estas palavras: {evitar}." if evitar else "")
        + ' Responda só em JSON: {"titulo": "...", "descricao": "...", "hashtags": ["..."]}'
    )
    try:
        tarefa = next((t for t in ("post", "roteiro") if t in roteador.cadeias), "roteiro")  # "post": grátis primeiro
        r = roteador.executar(tarefa, prompt=prompt,
                              sistema="Você escreve textos de postagem para redes sociais.", validar=_validar_texto)
    except Exception:  # sem IA disponível (ou todas falharam): a regra garante o texto
        return texto_por_regra(roteiro, tema, creditos)
    return {**r.valor, "creditos": creditos or "", "origem": r.provedor}


def escrever_post(dados, pasta):
    """post.json e post.txt (pronto para colar). Devolve o caminho do .txt."""
    pasta = Path(pasta)
    (pasta / "post.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    partes = [dados["titulo"], "", dados["descricao"]]
    if dados.get("hashtags"):
        partes += ["", " ".join(dados["hashtags"])]
    if dados.get("creditos"):
        partes += ["", "Créditos:", dados["creditos"].strip()]
    destino = pasta / "post.txt"
    destino.write_text("\n".join(partes).strip() + "\n", encoding="utf-8")
    return destino

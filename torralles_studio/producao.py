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
from .rede import ErroProvedor
from .roteador import TodosFalharam

_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_ASSINATURAS = (b"\x89PNG", b"\xff\xd8\xff", b"RIFF", b"GIF8")  # PNG, JPEG, WebP, GIF


# Palavras de estilo dos prompts de imagem que atrapalham a busca em bancos de fotos.
_PALAVRAS_DE_ESTILO = {"cinematic", "close", "up", "closeup", "shot", "photo", "photograph", "photography",
                       "realistic", "photorealistic", "lighting", "light", "vertical", "horizontal", "composition",
                       "4k", "8k", "hd", "ultra", "detailed", "high", "quality", "style", "soft", "warm", "bokeh",
                       "background", "view", "angle", "wide", "macro", "image", "scene", "frame", "slow"}


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


def _tem_fala(voz):
    """A narração tem fala de verdade (não é só silêncio)."""
    try:
        ini, fim, _ = trecho_falado(voz)
    except (ErroMontagem, ErroProvedor):
        return False
    return fim > ini


def _mais_novo(a, b):
    """`a` foi gravado depois de `b` (ex.: imagem refeita depois do vídeo da cena)."""
    try:
        return Path(a).stat().st_mtime > Path(b).stat().st_mtime + 1e-3
    except OSError:
        return False


_MIDIA_DA_CENA = re.compile(r"(cena_\d{2}(\.parte)?\.(png|mp4)|voz_\d{2}(\.parte)?\.mp3)")


def _apagar(arquivo):
    try:
        Path(arquivo).unlink(missing_ok=True)
    except OSError:  # no Windows, um ffmpeg interrompido pode ainda segurar o arquivo: fica para a próxima
        pass


def _para_juiz(imagem, pasta):
    """Cópia JPEG de até 1024 px para o juiz (menos tokens, mesmo conteúdo)."""
    from . import ff

    destino = Path(pasta) / f"{Path(imagem).stem}_juiz.jpg"
    ff.ffmpeg(["-i", str(imagem), "-vf", "scale='min(1024,iw)':-2", "-frames:v", "1", "-q:v", "3", str(destino)],
              prazo=120, falha="não deu para preparar a imagem para o juiz")
    return destino


def julgar_imagem(avaliador, cena, img, *, anterior=None, gerador=None):
    """Nota do juiz de visão para a imagem da cena (K38, spec 03 §3.3). None se não há avaliador com a rubrica."""
    if avaliador is None or "imagem" not in getattr(avaliador, "rubricas", {}):
        return None
    import tempfile

    with tempfile.TemporaryDirectory() as pasta:
        imagens = [_para_juiz(img, pasta)]
        if anterior is not None and Path(anterior).is_file():
            imagens.append(_para_juiz(anterior, pasta))
        pedido = f"Pedido da cena (o que a imagem deve mostrar): {cena.get('prompt_imagem', '')}"
        if len(imagens) > 1:
            pedido += "\nA segunda imagem é a da cena anterior: use só para julgar a consistência."
        return avaliador.avaliar("imagem", pedido, gerador=gerador, imagens=imagens)


def _gerar(destino, fazer):
    """Gera em `nome.parte.ext` e só renomeia para o nome final se ficar completo."""
    destino = Path(destino)
    parte = destino.with_name(f"{destino.stem}.parte{destino.suffix}")
    _apagar(parte)
    try:
        r = fazer(parte)
        if not _pronto(parte):
            raise ErroProducao(f"{destino.name}: o provedor {getattr(r, 'provedor', '?')} devolveu um arquivo "
                               "vazio ou ilegível")
        os.replace(parte, destino)
        return r
    finally:
        _apagar(parte)


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


CUSTO_CONFERENCIA_USD = 0.002  # estimativa por transcrição curta (revisar no KR1)


def _conferir(conferir_voz, roteador, arquivo, texto):
    """Confere a fala se houver conferência e o teto comportar a transcrição (que entra no orçamento, D20)."""
    if not conferir_voz or not roteador.orcamento.cabe(CUSTO_CONFERENCIA_USD):
        return None
    roteador.orcamento.registrar("conferencia_voz", CUSTO_CONFERENCIA_USD)
    return conferir_voz(arquivo, texto)


def prompt_da_imagem(cena, proporcao):
    formato = {"9:16": "vertical 9:16", "16:9": "horizontal 16:9", "1:1": "quadrada 1:1", "4:5": "vertical 4:5"}
    correcao = f" Fix: {cena['correcao']}." if cena.get("correcao") else ""
    return (f"{cena['prompt_imagem']}.{correcao} Composição {formato.get(proporcao, proporcao)}, assunto principal no centro, "
            "sem nenhum texto, letra ou logotipo na imagem.")


def _foto_gratuita(roteador, biblioteca, cena, img, proporcao, perfil, avisar):
    """Reserva quando nenhuma IA de imagem funcionar: foto de banco gratuito, com licença conferida (K20, D18)."""
    from .midia import SemMidia, buscar_midia, etiquetas_da_consulta

    palavras = [p for p in etiquetas_da_consulta(cena["prompt_imagem"]) if p not in _PALAVRAS_DE_ESTILO]
    consultas = list(dict.fromkeys(" ".join(palavras[:n]) or cena["prompt_imagem"] for n in (5, 3, 2)))
    # bancos de fotos exigem todas as palavras: tenta com menos se não achar. Foto que não combina com a cena
    # (título e etiquetas sem nenhuma palavra da busca) só é aceita na última tentativa, para o vídeo não parar.
    for k, consulta in enumerate(consultas):
        avisar(f"  … buscando foto gratuita para '{consulta}'")
        try:
            ativo = buscar_midia(roteador, biblioteca, consulta, "imagem", perfil=perfil.id if perfil else None,
                                 proporcao=proporcao, comercial=perfil.comercial if perfil else True,
                                 minimo_relevancia=0 if k == len(consultas) - 1 else 1)
            break
        except SemMidia as e:
            motivo = e
    else:
        raise ErroProducao(f"nem IA de imagem nem foto gratuita: {motivo}") from None
    origem = biblioteca.caminho(ativo)
    _gerar(img, lambda saida: shutil.copyfile(origem, saida))
    return {c: ativo.get(c) for c in ("hash", "caminho", "licenca", "fonte", "autor", "link", "titulo", "camada")}


def _imagem_com_juiz(roteador, loop, cena, img, i, pasta, perfil, proporcao, gerador, avisar):
    """Juiz de visão na imagem da cena; reprovada, refaz uma vez com o feedback no prompt e fica a melhor.

    Devolve os campos para o relatório (nota, juiz, revisar) ou None quando não há juiz configurado.
    """
    avaliador = getattr(loop, "avaliador", None)
    anterior = pasta / f"cena_{i - 1:02d}.png" if i > 1 else None
    try:
        av = julgar_imagem(avaliador, cena, img, anterior=anterior, gerador=gerador)
    except (ErroProvedor, OSError) as e:
        avisar(f"  ⚠ juiz da imagem indisponível ({e})")
        return {"juiz_imagem": "revisar"}
    if av is None:
        return None
    if av.sem_juiz:
        return {"juiz_imagem": "revisar"}
    campos = {"nota_imagem": av.nota, "juiz_imagem": ",".join(av.juizes)}
    if av.aprovado:
        return campos
    avisar(f"  ⚠ imagem da cena {i} reprovada pelo juiz ({av.nota}); refazendo uma vez com a correção")
    feedback = "; ".join((av.correcoes or [])[:2] + (av.problemas or [])[:2])[:300]
    nova = {**cena, "correcao": feedback} if feedback else dict(cena)
    reserva = img.with_name(f"{img.stem}_antes{img.suffix}")
    os.replace(img, reserva)
    try:
        r2 = _gerar(img, lambda saida: funcoes.gerar_imagem(
            roteador, prompt_da_imagem(nova, proporcao), saida, perfil=perfil, proporcao=proporcao, cena=nova))
        av2 = julgar_imagem(avaliador, cena, img, anterior=anterior, gerador=r2.provedor)
    except (TodosFalharam, ErroProducao, ErroProvedor, OSError) as e:
        avisar(f"  ⚠ não deu para refazer ({e}); fica a primeira")
        os.replace(reserva, img)
        return {**campos, "revisar": True}
    if av2 is None or av2.sem_juiz or (av2.nota or 0) < (av.nota or 0):
        os.replace(reserva, img)  # a primeira era melhor (ou não deu para julgar a nova)
        return {**campos, "revisar": True}
    _apagar(reserva)
    return {"nota_imagem": av2.nota, "juiz_imagem": ",".join(av2.juizes), "provedor_refeito": r2.provedor,
            **({} if av2.aprovado else {"revisar": True})}


def produzir_video(roteador, loop, tema, pasta, *, duracao=30, perfil=None, pesquisar=False, trilha=None, bpm=None,
                   cfg_montagem=None, aviso=None, refazer_roteiro=False, biblioteca=None, trilha_auto=True,
                   capcut=False, fatos=None, proporcao=None, conferir_voz=None, perfis_referencia=None,
                   efeitos_auto=True, publicacao=True, juiz_imagem=True):
    """Produz o vídeo e devolve o relatório (também salvo em pasta/relatorio.json).

    perfis_referencia: arquivo das faixas por categoria (K13; padrão config/perfis_referencia.toml). Vídeo fora
    da faixa da categoria do perfil ganha alertas no relatório (não reprova).

    biblioteca: com ela, cena cuja imagem nenhuma IA conseguiu gerar usa uma foto gratuita com licença, e
    (com trilha_auto e sem `trilha`) a música de fundo é escolhida pelo clima do roteiro (K21); com efeitos_auto,
    cada corte ganha um som curto do acervo local, pelo clima da cena que entra.
    """
    for programa in ("ffmpeg", "ffprobe"):
        if not shutil.which(programa):
            raise ErroProducao(f"{programa} não encontrado: instale o FFmpeg (ele traz o ffprobe) e abra um "
                               "terminal novo")
    avisar = aviso or (lambda texto: None)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    proporcao = proporcao or (perfil.formato.get("proporcao") if perfil else None) or "9:16"
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
        etapa("roteiro", reaproveitado=True, aprovado=guardado.get("aprovado"), tentativas=guardado.get("tentativas"))
        if not guardado.get("aprovado"):
            avisar("⚠ usando o roteiro já feito, que não foi aprovado pelo juiz (para refazer: --refazer-roteiro)")
    else:
        from .roteiro import produzir_roteiro

        avisar("== roteiro")
        r = produzir_roteiro(loop, tema, duracao, pesquisa=resumo, perfil=perfil, fatos=fatos or None)
        if not r.valor or not r.valor.get("cenas"):
            raise ErroProducao(f"não saiu roteiro: {r.motivo}")
        roteiro = r.valor
        (pasta / "roteiro.json").write_text(json.dumps(
            {"tema": tema, "duracao": duracao, "proporcao": proporcao, "aprovado": r.aprovado, "nota": r.nota,
             "tentativas": len(r.tentativas or []) or 1, "roteiro": roteiro}, ensure_ascii=False, indent=2), encoding="utf-8")
        etapa("roteiro", r.provedor, nota=r.nota, aprovado=r.aprovado, tentativas=len(r.tentativas or []) or 1,
              problemas=list(getattr(r.avaliacao, "problemas", None) or [])[:5])
        for arq in pasta.iterdir():  # roteiro novo: mídia das cenas antigas não serve mais (só os nomes do Studio)
            if arq.is_file() and _MIDIA_DA_CENA.fullmatch(arq.name):
                _apagar(arq)
        _apagar(pasta / "fotos.json")
        _apagar(pasta / "creditos.txt")
        _apagar(pasta / "trilha.json")  # roteiro novo pode ter outro clima

    # 3. Cada cena: imagem → voz → cena animada com a duração da fala
    cenas, total = [], len(roteiro["cenas"])
    fotos = _ler_json(pasta / "fotos.json") or {}  # cena → foto gratuita usada (fonte, autor, licença)
    so_fotos = False  # depois que a IA de imagem falha numa cena, as próximas vão direto para a foto
    folga = c["folga_inicio_s"] + c["folga_fim_s"] + c["transicao_s"] + 0.5  # + pausa extra que a montagem dá
    for i, cena in enumerate(roteiro["cenas"], 1):
        img, voz, video = pasta / f"cena_{i:02d}.png", pasta / f"voz_{i:02d}.mp3", pasta / f"cena_{i:02d}.mp4"
        try:
            if _pronto(img):
                foto = fotos.get(str(i))
                etapa(f"cena {i}: imagem", f"foto gratuita ({foto['fonte']})" if foto else None, reaproveitado=True,
                      **({"licenca": foto["licenca"]} if foto else {}))
            else:
                avisar(f"== cena {i}/{total}: imagem")
                try:
                    if so_fotos and biblioteca is not None:
                        raise ErroProducao("IA de imagem já falhou nesta rodada")
                    r = _gerar(img, lambda saida: funcoes.gerar_imagem(
                        roteador, prompt_da_imagem(cena, proporcao), saida, perfil=perfil, proporcao=proporcao,
                        cena=cena))
                    fotos.pop(str(i), None)
                    nota = None
                    if juiz_imagem:
                        nota = _imagem_com_juiz(roteador, loop, cena, img, i, pasta, perfil, proporcao, r.provedor,
                                                avisar)
                    etapa(f"cena {i}: imagem", r.provedor, **(nota or {}))
                except (TodosFalharam, ErroProducao):
                    if biblioteca is None:
                        raise
                    so_fotos = True
                    fotos[str(i)] = _foto_gratuita(roteador, biblioteca, cena, img, proporcao, perfil, avisar)
                    etapa(f"cena {i}: imagem", f"foto gratuita ({fotos[str(i)]['fonte']})",
                          licenca=fotos[str(i)]["licenca"])
                (pasta / "fotos.json").write_text(json.dumps(fotos, ensure_ascii=False, indent=2), encoding="utf-8")
            if _pronto(voz) and _tem_fala(voz):
                etapa(f"cena {i}: voz", reaproveitado=True)
            else:
                avisar(f"== cena {i}/{total}: narração")
                r = _gerar(voz, lambda saida: funcoes.gerar_voz(roteador, cena["narracao"], saida))
                conferencia = _conferir(conferir_voz, roteador, voz, cena["narracao"])
                if conferencia and not conferencia["ok"]:  # fala diferente do roteiro: tenta a próxima voz (K18)
                    avisar(f"  ⚠ a narração de {r.provedor} errou {conferencia['erros']} palavra(s) "
                           f"({conferencia['wer']:.0%}); tentando outra voz")
                    outra = voz.with_name(f"{voz.stem}_b{voz.suffix}")
                    try:  # cache liberado: se a outra voz já foi paga antes, vem de graça
                        r2 = _gerar(outra, lambda saida: roteador.executar(
                            "voz", texto=cena["narracao"], saida=Path(saida), excluir={r.provedor}))
                        c2 = _conferir(conferir_voz, roteador, outra, cena["narracao"])
                        if c2 is None or c2["wer"] < conferencia["wer"]:  # fica com a que errou menos
                            os.replace(outra, voz)
                            r, conferencia = r2, c2
                        else:
                            avisar("  ⚠ a outra voz não foi melhor: fica a primeira")
                    except (TodosFalharam, ErroProducao):
                        avisar("  ⚠ nenhuma outra voz disponível: fica a primeira")
                    finally:
                        _apagar(outra)
                etapa(f"cena {i}: voz", r.provedor,
                      **({"erro_palavras": conferencia["wer"]} if conferencia else {}))
            fala = trecho_falado(voz)  # medida uma vez: a montagem reaproveita (não mede a voz de novo)
            ini, fim, _ = fala
            if _pronto(video) and not _mais_novo(img, video) and not _mais_novo(voz, video):
                etapa(f"cena {i}: vídeo", reaproveitado=True)
            else:
                avisar(f"== cena {i}/{total}: movimento")
                dur = round((fim - ini) + folga + (1.5 if i == total else 0), 2)  # a última segura mais no fim
                r = _gerar(video, lambda saida: funcoes.gerar_video(
                    roteador, img, cena.get("prompt_movimento", ""), saida, duracao=dur, proporcao=proporcao,
                    clima=cena.get("clima"), cena=cena))
                etapa(f"cena {i}: vídeo", r.provedor)
        except TodosFalharam as e:
            raise ErroProducao(f"cena {i}: {e}") from None
        cenas.append({"video": str(video), "voz": str(voz), "narracao": cena["narracao"], "fala": fala,
                      "texto_tela": cena.get("texto_tela"), "duracao": cena.get("duracao"), "clima": cena.get("clima")})

    # 4. Trilha pelo clima do roteiro (K21): reaproveita a escolhida antes; sem trilha, o vídeo sai só com voz
    musica = None
    if trilha is None and trilha_auto and biblioteca is not None:
        guardada = _ler_json(pasta / "trilha.json")
        if isinstance(guardada, dict) and guardada.get("tema") == tema and Path(guardada.get("arquivo", "")).is_file():
            musica = guardada
            etapa("trilha", reaproveitado=True, licenca=(guardada.get("ativo") or {}).get("licenca"))
        else:
            from .trilha import SemTrilha, escolher_trilha

            avisar("== trilha")
            try:
                t = escolher_trilha(roteador, biblioteca, roteiro, duracao, perfil=perfil, aviso=avisar)
                ativo = {k: t["ativo"].get(k) for k in ("hash", "caminho", "licenca", "fonte", "autor", "link",
                                                        "titulo")}
                musica = {"tema": tema, "arquivo": t["arquivo"], "bpm": t["bpm"], "clima": t["clima"],
                          "nota": t["nota"], "ativo": ativo}
                (pasta / "trilha.json").write_text(json.dumps(musica, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
                etapa("trilha", ativo.get("fonte"), nota=t["nota"], licenca=ativo.get("licenca"))
            except SemTrilha as e:
                avisar(f"  ⚠ sem trilha: {e} (o vídeo sai só com a narração)")
                etapa("trilha", None, aviso=str(e))
        if musica:
            trilha, bpm = musica["arquivo"], bpm or musica.get("bpm")

    # 4b. Efeitos sonoros nos cortes (K21): só do acervo local (grátis, licença conferida, sem Freesound — D22)
    sons = []
    if efeitos_auto and biblioteca is not None and len(cenas) > 1:
        from .efeitos import escolher_efeitos
        from .montagem import duracao as duracao_audio

        escolhas = escolher_efeitos(biblioteca, [c.get("clima") for c in cenas], perfil=perfil,
                                    duracao_de=duracao_audio)
        for i, (cena, e) in enumerate(zip(cenas, escolhas), 1):
            if e:
                cena["efeito"] = e["arquivo"]
                sons.append({"cena": i, "nome": e["nome"],
                             **{k: e["ativo"].get(k) for k in ("hash", "caminho", "licenca", "fonte", "autor",
                                                               "link", "titulo")}})
        if sons:
            etapa("efeitos", "acervo", quantidade=len(sons))
        else:
            aviso_sons = ("sem efeitos sonoros no acervo; para ter: importar-sons <pasta> --licenca pixabay "
                          "--fonte Pixabay")
            avisar(f"  · {aviso_sons}")
            etapa("efeitos", None, aviso=aviso_sons)

    # 5. Montagem final + régua da spec 03 §3.6
    avisar("== montagem final")
    final = pasta / "video_final.mp4"
    try:
        resultado = montar(cenas, final, proporcao=proporcao, trilha=trilha, bpm=bpm, cfg=cfg_montagem,
                           pasta_trabalho=pasta / "montagem", duracao_alvo=duracao)
    except (ErroMontagem, ErroProvedor) as e:
        if not musica and not sons:
            raise
        avisar(f"  ⚠ a montagem falhou com trilha/efeitos ({e}); tentando só com a narração")
        for cena in cenas:
            cena.pop("efeito", None)
        # Se falhar de novo, o problema não era a trilha nem os efeitos: o erro sobe e a trilha escolhida fica
        resultado = montar(cenas, final, proporcao=proporcao, cfg=cfg_montagem, pasta_trabalho=pasta / "montagem",
                           duracao_alvo=duracao)
        if musica:
            _apagar(pasta / "trilha.json")
            etapas.append({"etapa": "trilha", "provedor": None, "reaproveitado": False, "aviso": str(e)})
        if sons:
            etapas.append({"etapa": "efeitos", "provedor": None, "reaproveitado": False, "aviso": str(e)})
        musica, sons = None, []
    conferencia = verificar_montagem(resultado, duracao_pedida=duracao)
    relatorio = {
        "tema": tema, "video": str(final), "proporcao": proporcao, "duracao_s": resultado["duracao_s"],
        "aprovado": conferencia["aprovado"], "problemas": conferencia["problemas"],
        "medidas": conferencia["medidas"], "custo_usd": round(roteador.orcamento.gasto_usd - gasto_inicial, 4),
        "tempo_s": round(time.monotonic() - inicio), "etapas": etapas,
        "titulo": roteiro.get("titulo"), "cta": roteiro.get("cta"),
        "fotos_gratuitas": {k: v for k, v in fotos.items() if int(k) <= total},
        "trilha": musica,
        "efeitos": sons,  # som de cada corte, com fonte e licença (D18)
    }
    categoria = getattr(perfil, "categoria", None)
    if categoria:
        from .config import RAIZ
        from .referencias import alertas_referencia, carregar_perfil, medidas_do_video

        faixas = carregar_perfil(perfis_referencia or RAIZ / "config" / "perfis_referencia.toml", categoria)
        medidas = medidas_do_video(resultado, roteiro)
        relatorio["referencia"] = {"categoria": categoria, "medidas": medidas, "perfil_medido": bool(faixas),
                                   "alertas": alertas_referencia(medidas, faixas, categoria) if faixas else []}
    terceiros = (list(relatorio["fotos_gratuitas"].values()) + ([musica["ativo"]] if musica else [])
                 + [{k: v for k, v in s.items() if k not in ("cena", "nome")} for s in sons])
    if biblioteca is not None and terceiros:
        creditos = biblioteca.creditos(terceiros)
        relatorio["creditos"] = creditos  # vai na descrição do vídeo (CC-BY exige crédito)
        (pasta / "creditos.txt").write_text(creditos or "Nenhuma mídia exige crédito.\n", encoding="utf-8")
    elif not terceiros:
        _apagar(pasta / "creditos.txt")  # sem mídia de terceiros: crédito antigo não pode ir para a descrição
    if publicacao:  # capa e texto para postar (não bloqueiam: o vídeo já está pronto)
        from .provedores.video import TAMANHOS
        from .publicacao import escrever_post, gerar_capa, gerar_texto

        avisar("== capa e texto para postar")
        largura, altura = TAMANHOS.get(proporcao) or (1080, 1920)
        try:
            relatorio["capa"] = str(gerar_capa(pasta / "cena_01.png", roteiro.get("titulo") or tema,
                                               pasta / "capa.jpg", largura=largura, altura=altura))
        except (ErroProvedor, OSError) as e:
            relatorio["capa_erro"] = str(e)
            avisar(f"  ⚠ não deu para gerar a capa ({e})")
        guardado = _ler_json(pasta / "post.json")
        roteiro_arq = pasta / "roteiro.json"
        if (isinstance(guardado, dict) and guardado.get("titulo") and (pasta / "post.txt").is_file()
                and not _mais_novo(roteiro_arq, pasta / "post.json")):  # roteiro igual: reaproveita sem pagar
            post = {**guardado, "creditos": relatorio.get("creditos") or ""}
        else:
            post = gerar_texto(roteador, roteiro, tema, creditos=relatorio.get("creditos"), perfil=perfil)
        try:
            relatorio["post"] = str(escrever_post(post, pasta))
        except OSError as e:
            relatorio["post_erro"] = str(e)
            avisar(f"  ⚠ não deu para gravar o post.txt ({e})")
        relatorio["custo_usd"] = round(roteador.orcamento.gasto_usd - gasto_inicial, 4)  # inclui o texto do post
    # dados da montagem: permitem exportar para o CapCut depois sem refazer nada
    (pasta / "montagem.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2, default=str),
                                         encoding="utf-8")
    if capcut:
        from .exportar import ErroExportacao, exportar_capcut

        avisar("== exportação para o CapCut")
        try:
            relatorio["capcut"] = str(exportar_capcut(resultado, pasta / "capcut", creditos=relatorio.get("creditos"),
                                                      titulo=roteiro.get("titulo"), roteiro=roteiro))
        except (ErroExportacao, ErroProvedor, OSError) as e:  # o vídeo já está pronto: só avisa
            relatorio["capcut_erro"] = str(e)
            avisar(f"  ⚠ não deu para gerar a pasta do CapCut ({e}). Feche o CapCut se estiver com a pasta aberta "
                   "e rode: exportar-capcut")
    (pasta / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return relatorio

"""Linha de comando: python -m torralles_studio <comando> ..."""

import argparse
import json
import sys

from . import funcoes
from .config import carregar_roteador
from .roteador import TodosFalharam


def mostrar_status(roteador):
    for tarefa, itens in roteador.status().items():
        print(f"\n{tarefa}:")
        for i, (nome, motivo) in enumerate(itens, 1):
            print(f"  {i}. {nome:<20} {'pronto' if motivo is None else motivo}")


def relatar(resultado):
    for t in resultado.tentativas:
        if t.status != "ok":
            print(f"  · {t.provedor}: {t.status} ({t.detalhe})", file=sys.stderr)
    print(f"✓ feito com: {resultado.provedor}", file=sys.stderr)


def comando_perfis(args):
    from .config import MODELO_PERFIL, carregar_perfis, pasta_perfis
    from .perfis import ErroPerfil, criar_perfil

    try:
        if args.comando == "perfil-novo":
            destino = criar_perfil(pasta_perfis(args.config), args.id, args.nome, MODELO_PERFIL)
            print(f"✓ perfil criado: {destino}\n  Edite o arquivo e ponha o kit visual em {destino.with_suffix('')}/")
            return 0
        perfis = list(carregar_perfis(args.config))
    except ErroPerfil as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    for pid, motivo in sorted(carregar_perfis(args.config).erros.items()):
        print(f"⚠ {pid}: {motivo}", file=sys.stderr)
    if not perfis:
        print("Nenhum perfil ainda. Crie com: python -m torralles_studio perfil-novo <id> \"<nome>\"")
    for pf in perfis:
        extra = f" · Hermes: {pf.hermes_perfil}" if pf.hermes_perfil else ""
        print(f"{pf.id:<20} {pf.nome} (categoria {pf.categoria or '-'}){extra}")
    return 0


def comando_cerebro(args):
    from pathlib import Path

    from .banco import Banco
    from .cerebro import exportar, validar_data
    from .config import RAIZ, carregar_config
    from .perfis import ID_VALIDO

    try:  # valida antes de tudo, mesmo sem banco
        validar_data(args.desde)
        if args.perfil is not None and not ID_VALIDO.match(args.perfil):
            raise ValueError(f"perfil inválido {args.perfil!r}: use o id do perfil (veja: perfis)")
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    caminho = Path(carregar_config(args.config).get("banco", {}).get("caminho", "dados/torralles.db"))
    caminho = caminho if caminho.is_absolute() else RAIZ / caminho
    if not caminho.exists():  # não cria banco vazio só para resumir
        print("Sem produção registrada ainda (o banco local não existe): nada para o Cérebro.")
        return 0
    banco = Banco(caminho)
    if args.perfil and not banco.projetos(args.perfil):
        print(f"⚠ o perfil {args.perfil!r} não tem projetos no banco (confira o id com: perfis)", file=sys.stderr)
    try:
        destino = exportar(banco, args.pasta or RAIZ / "dados" / "cerebro", desde=args.desde, perfil=args.perfil)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(destino.read_text(encoding="utf-8"))
    print(f"✓ salvo em {destino} (cole no CEREBRO_MESTRE.md)", file=sys.stderr)
    return 0


def comando_avaliar_video(args):
    from .config import carregar_avaliador, carregar_env
    from .percepcao import analisar_video, avaliar_video

    carregar_env()
    from urllib.parse import urlparse

    percepcao = None
    if args.percepcao and urlparse(str(args.video)).scheme.lower() not in ("http", "https"):
        percepcao = analisar_video(args.video, "saidas/percepcao")
    av = avaliar_video(carregar_avaliador(caminho=args.config), args.video, contexto=args.contexto,
                       percepcao=percepcao)
    print(json.dumps(av.como_dict(), ensure_ascii=False, indent=2))
    if av.sem_juiz:
        motivos = av.problemas[1:] or ["nenhum provedor na cadeia juiz_video"]
        print("⚠ nenhum juiz de vídeo conseguiu avaliar:", file=sys.stderr)
        for m in motivos:
            print(f"  · {m}", file=sys.stderr)
        if any("falta GEMINI_API_KEY" in m for m in motivos):
            print("  Coloque GEMINI_API_KEY no .env (veja docs/configurar-chaves.md).", file=sys.stderr)
        return 1
    return 0


def comando_montar(args):
    import tempfile
    from pathlib import Path

    from .config import carregar_config
    from .montagem import ErroMontagem, montar, verificar_montagem
    from .rede import ErroProvedor

    projeto = Path(args.projeto)
    try:
        dados = json.loads(projeto.read_text(encoding="utf-8-sig"))
        base = projeto.resolve().parent  # caminhos relativos valem a partir do JSON

        def caminho(valor):
            return str(base / valor) if valor else None

        cenas = [{**c, "video": caminho(c.get("video")), "voz": caminho(c.get("voz"))} for c in dados["cenas"]]
        with tempfile.TemporaryDirectory() as temporaria:  # sem --trabalho, a voz fica até conferir a sincronia
            r = montar(cenas, args.saida, proporcao=dados.get("proporcao", "9:16"),
                       trilha=caminho(dados.get("trilha")), bpm=dados.get("bpm"),
                       cfg=carregar_config(args.config).get("montagem"), pasta_trabalho=args.trabalho or temporaria,
                       duracao_alvo=dados.get("duracao"))
            v = verificar_montagem(r, duracao_pedida=dados.get("duracao"))
    except KeyError as e:
        print(f"✗ o projeto não tem o campo {e}", file=sys.stderr)
        return 1
    except (OSError, TypeError, ValueError, ErroMontagem, ErroProvedor) as e:
        print(f"✗ não deu para montar: {e}", file=sys.stderr)
        return 1
    print(json.dumps(v["medidas"], ensure_ascii=False))
    for problema in v["problemas"]:
        print(f"✗ {problema}")
    print(f"{'✓' if v['aprovado'] else '⚠'} {r['arquivo']}")
    return 0 if v["aprovado"] else 2


def comando_com_qualidade(args, roteador, perfil):
    """roteiro/pesquisa pelo loop de correção: mostra resultado, nota, motivo e custo."""
    from .config import carregar_loop

    loop = carregar_loop(roteador, args.config)
    if args.comando == "roteiro":
        from .roteiro import produzir_roteiro

        r = produzir_roteiro(loop, args.tema, args.duracao, perfil=perfil)
        saida = json.dumps(r.valor, ensure_ascii=False, indent=2) if r.valor is not None else ""
    else:
        from .pesquisa import produzir_pesquisa

        r = produzir_pesquisa(loop, args.tema)
        v = r.valor or {}
        fontes = "\n".join(f"[{i}] {f['url']}" for i, f in enumerate(v.get("fontes", []), 1))
        saida = v.get("resumo", "") + (f"\n\nFontes:\n{fontes}" if fontes else "")
    estado = "✓ aprovado" if r.aprovado else "⚠ revisar"
    nota = f", nota {r.nota:.0f}" if r.nota is not None else ""
    custo = sum(t.custo_usd for t in r.tentativas)
    print(f"{estado} ({r.motivo}{nota}, {len(r.tentativas)} tentativa(s), US$ {custo:.3f})", file=sys.stderr)
    av = r.avaliacao
    if av is not None and (getattr(av, "sem_juiz", False) or not r.aprovado):
        for problema in (getattr(av, "problemas", None) or [])[:8]:  # por que não houve juiz ou o que reprovou
            print(f"  · {problema}", file=sys.stderr)
    if saida:
        print(saida)
    return 0 if r.valor is not None else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="torralles_studio", description="Gera conteúdo com fallback entre modelos de IA.")
    p.add_argument("--config", help="caminho de um fallbacks.toml alternativo")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("status", help="mostra as cadeias e quais provedores estão prontos")
    sub.add_parser("perfis", help="lista os perfis de projeto")
    s = sub.add_parser("perfil-novo", help="cria um perfil de projeto a partir do modelo")
    s.add_argument("id")
    s.add_argument("nome")
    s = sub.add_parser("ideias")
    s.add_argument("tema")
    s.add_argument("-n", "--quantidade", type=int, default=10)
    s.add_argument("-p", "--perfil", help="id do perfil do projeto")
    s = sub.add_parser("roteiro")
    s.add_argument("tema")
    s.add_argument("-d", "--duracao", type=int, default=30)
    s.add_argument("-p", "--perfil", help="id do perfil do projeto")
    s.add_argument("-q", "--qualidade", action="store_true", help="avalia com juiz e refaz até aprovar (loop)")
    s = sub.add_parser("pesquisa")
    s.add_argument("tema")
    s.add_argument("-q", "--qualidade", action="store_true", help="checa citações e avalia com juiz (loop)")
    s = sub.add_parser("imagem")
    s.add_argument("prompt")
    s.add_argument("-o", "--saida", default="saidas/imagem.png")
    s.add_argument("-p", "--perfil", help="id do perfil do projeto")
    s = sub.add_parser("voz")
    s.add_argument("texto")
    s.add_argument("-o", "--saida", default="saidas/voz.mp3")
    s.add_argument("-p", "--perfil", help="id do perfil do projeto")
    s = sub.add_parser("video")
    s.add_argument("imagem")
    s.add_argument("prompt")
    s.add_argument("-o", "--saida", default="saidas/video.mp4")
    s.add_argument("-d", "--duracao", type=int, default=5)
    s.add_argument("--proporcao", choices=["9:16", "16:9", "1:1", "4:5"], help="padrão: a do perfil")
    s.add_argument("-p", "--perfil", help="id do perfil do projeto")

    s = sub.add_parser("avaliar-video", help="juiz que assiste o vídeo inteiro com som e dá nota na régua 0–100")
    s.add_argument("video", help="arquivo de vídeo ou link do YouTube")
    s.add_argument("-c", "--contexto", help="o que o vídeo deveria ser (briefing, tema)")
    s.add_argument("--percepcao", action="store_true", help="mede antes (cortes, volume, transcrição) e envia ao juiz")

    s = sub.add_parser("cerebro", help="resumo dos aprendizados de produção para colar no Cérebro")
    s.add_argument("--desde", help="só tentativas a partir desta data (AAAA-MM-DD)")
    s.add_argument("-p", "--perfil", help="só um perfil de projeto")
    s.add_argument("-o", "--pasta", help="pasta onde salvar o resumo (padrão: dados/cerebro na raiz do repositório)")

    s = sub.add_parser("assistir", help="analisa um vídeo (quadros, cortes, som, transcrição) para avaliação")
    s.add_argument("video")
    s.add_argument("-o", "--saida", default="saidas/percepcao")
    s.add_argument("--sem-transcricao", action="store_true")

    s = sub.add_parser("montar", help="monta o vídeo final (cenas, narração, legendas, trilha) e confere a régua")
    s.add_argument("projeto", help="arquivo JSON com as cenas (veja docs/montagem.md)")
    s.add_argument("-o", "--saida", default="saidas/final.mp4")
    s.add_argument("--trabalho", help="pasta para guardar clipes, áudios e legendas (para o CapCut)")

    args = p.parse_args(argv)
    if args.comando == "montar":
        return comando_montar(args)
    if args.comando == "assistir":
        from .config import carregar_env
        from .percepcao import analisar_video

        carregar_env()
        rel = analisar_video(args.video, args.saida, transcrever_audio=not args.sem_transcricao)
        resumo = {k: v for k, v in rel.items() if k not in ("quadros",)}
        print(json.dumps(resumo, ensure_ascii=False, indent=2))
        return 0
    if args.comando in ("perfis", "perfil-novo"):
        return comando_perfis(args)
    if args.comando == "avaliar-video":
        return comando_avaliar_video(args)
    if args.comando == "cerebro":
        return comando_cerebro(args)
    roteador = carregar_roteador(args.config)
    roteador.aviso = lambda texto: print(texto, file=sys.stderr, flush=True)  # mostra quem está trabalhando

    if args.comando == "status":
        mostrar_status(roteador)
        return 0

    perfil = None
    if getattr(args, "perfil", None):
        from .config import carregar_perfis
        from .perfis import ErroPerfil

        try:
            perfil = carregar_perfis(args.config).obter(args.perfil)
        except ErroPerfil as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        roteador = perfil.roteador(roteador)

    if getattr(args, "qualidade", False):
        return comando_com_qualidade(args, roteador, perfil)

    try:
        if args.comando == "ideias":
            r = funcoes.gerar_ideias(roteador, args.tema, args.quantidade, perfil=perfil)
            saida = r.valor
        elif args.comando == "roteiro":
            r = funcoes.gerar_roteiro(roteador, args.tema, args.duracao, perfil=perfil)
            saida = json.dumps(r.valor, ensure_ascii=False, indent=2)
        elif args.comando == "pesquisa":
            r = funcoes.pesquisar(roteador, args.tema)
            fontes = "\n".join(f"[{i}] {f['url']}" for i, f in enumerate(r.valor["fontes"], 1))
            saida = r.valor["resumo"] + (f"\n\nFontes:\n{fontes}" if fontes else "")
        elif args.comando == "imagem":
            r = funcoes.gerar_imagem(roteador, args.prompt, args.saida, perfil=perfil)
            saida = str(r.valor)
        elif args.comando == "voz":
            r = funcoes.gerar_voz(roteador, args.texto, args.saida)
            saida = str(r.valor)
        else:
            r = funcoes.gerar_video(roteador, args.imagem, args.prompt, args.saida, args.duracao,
                                   proporcao=args.proporcao, perfil=perfil)
            saida = str(r.valor)
    except TodosFalharam as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    relatar(r)
    print(saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())

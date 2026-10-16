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

    s = sub.add_parser("avaliar-video", help="juiz que assiste o vídeo inteiro com som e dá nota na régua 0–100")
    s.add_argument("video", help="arquivo de vídeo ou link do YouTube")
    s.add_argument("-c", "--contexto", help="o que o vídeo deveria ser (briefing, tema)")
    s.add_argument("--percepcao", action="store_true", help="mede antes (cortes, volume, transcrição) e envia ao juiz")

    s = sub.add_parser("assistir", help="analisa um vídeo (quadros, cortes, som, transcrição) para avaliação")
    s.add_argument("video")
    s.add_argument("-o", "--saida", default="saidas/percepcao")
    s.add_argument("--sem-transcricao", action="store_true")

    args = p.parse_args(argv)
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
    roteador = carregar_roteador(args.config)

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
            r = funcoes.gerar_video(roteador, args.imagem, args.prompt, args.saida, args.duracao)
            saida = str(r.valor)
    except TodosFalharam as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    relatar(r)
    print(saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Linha de comando: python -m estudio_ia <comando> ..."""

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


def main(argv=None):
    p = argparse.ArgumentParser(prog="estudio_ia", description="Gera conteúdo com fallback entre modelos de IA.")
    p.add_argument("--config", help="caminho de um fallbacks.toml alternativo")
    sub = p.add_subparsers(dest="comando", required=True)

    sub.add_parser("status", help="mostra as cadeias e quais provedores estão prontos")
    s = sub.add_parser("ideias")
    s.add_argument("tema")
    s.add_argument("-n", "--quantidade", type=int, default=10)
    s = sub.add_parser("roteiro")
    s.add_argument("tema")
    s.add_argument("-d", "--duracao", type=int, default=30)
    s = sub.add_parser("pesquisa")
    s.add_argument("tema")
    s = sub.add_parser("imagem")
    s.add_argument("prompt")
    s.add_argument("-o", "--saida", default="saidas/imagem.png")
    s = sub.add_parser("voz")
    s.add_argument("texto")
    s.add_argument("-o", "--saida", default="saidas/voz.mp3")
    s = sub.add_parser("video")
    s.add_argument("imagem")
    s.add_argument("prompt")
    s.add_argument("-o", "--saida", default="saidas/video.mp4")
    s.add_argument("-d", "--duracao", type=int, default=5)

    args = p.parse_args(argv)
    roteador = carregar_roteador(args.config)

    if args.comando == "status":
        mostrar_status(roteador)
        return 0

    try:
        if args.comando == "ideias":
            r = funcoes.gerar_ideias(roteador, args.tema, args.quantidade)
            saida = r.valor
        elif args.comando == "roteiro":
            r = funcoes.gerar_roteiro(roteador, args.tema, args.duracao)
            saida = json.dumps(r.valor, ensure_ascii=False, indent=2)
        elif args.comando == "pesquisa":
            r = funcoes.pesquisar(roteador, args.tema)
            fontes = "\n".join(f"[{i}] {f['url']}" for i, f in enumerate(r.valor["fontes"], 1))
            saida = r.valor["resumo"] + (f"\n\nFontes:\n{fontes}" if fontes else "")
        elif args.comando == "imagem":
            r = funcoes.gerar_imagem(roteador, args.prompt, args.saida)
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

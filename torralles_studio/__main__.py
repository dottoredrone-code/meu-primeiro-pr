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


def comando_produzir(args, roteador, perfil):
    from .config import carregar_biblioteca, carregar_config, carregar_loop
    from .montagem import ErroMontagem
    from .producao import ErroProducao, pasta_do_tema, produzir_video
    from .pronuncia import conferir_voz
    from .rede import ErroProvedor

    pasta = args.pasta or pasta_do_tema(args.tema)
    try:
        rel = produzir_video(roteador, carregar_loop(roteador, args.config), args.tema, pasta, duracao=args.duracao,
                             perfil=perfil, pesquisar=args.pesquisa, trilha=args.trilha, bpm=args.bpm,
                             cfg_montagem=carregar_config(args.config).get("montagem"),
                             aviso=lambda t: print(t, file=sys.stderr, flush=True),
                             refazer_roteiro=args.refazer_roteiro, biblioteca=carregar_biblioteca(args.config),
                             trilha_auto=not args.sem_trilha, capcut=args.capcut,
                             conferir_voz=None if args.sem_conferir_voz else conferir_voz)
    except KeyboardInterrupt:
        print(f"\n✗ interrompido. O que já ficou pronto está em {pasta}; rode de novo para continuar.", file=sys.stderr)
        return 130
    except (ErroProducao, ErroMontagem, ErroProvedor, OSError) as e:
        print(f"✗ parou: {e}\n  O que já ficou pronto está em {pasta}; rode de novo para continuar.", file=sys.stderr)
        return 1
    for e in rel["etapas"]:
        if not e["reaproveitado"] and e["etapa"] in ("pesquisa", "roteiro"):
            nota = f"nota {e['nota']:.0f}" if e.get("nota") is not None else "sem juiz"
            print(f"  {e['etapa']}: {e['provedor']} · {nota}", file=sys.stderr)
    for problema in rel["problemas"]:
        print(f"✗ {problema}")
    for alerta in (rel.get("referencia") or {}).get("alertas", []):
        print(f"⚠ {alerta}")
    print(f"{'✓' if rel['aprovado'] else '⚠'} {rel['video']} · {rel['duracao_s']:.1f} s · US$ {rel['custo_usd']:.3f}"
          f" · {rel['tempo_s']} s")
    if rel.get("capcut"):
        print(f"  CapCut: {rel['capcut']} (veja o LEIA-ME.txt)")
    return 0 if rel["aprovado"] else 2


def comando_servidor(args):
    from .config import RAIZ, caminho_banco
    from .servico import ServicoPecas

    canal = None
    if args.comando == "mcp":
        from .servidor import isolar_stdin

        canal = isolar_stdin()  # antes de qualquer FFmpeg: stdin/stdout são só do JSON-RPC
    servico = ServicoPecas(caminho_banco(args.config), pasta_base=RAIZ / "saidas" / "pedidos", config=args.config)
    servico.iniciar()
    try:
        if args.comando == "mcp":
            from .servidor import saida_utf8, servir_mcp

            servir_mcp(servico, entrada=canal, saida=saida_utf8())
            return 0
        from .servidor import criar_servidor_http

        try:
            http = criar_servidor_http(servico, args.host, args.porta)
        except (ValueError, OSError) as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        print(f"✓ Torralles Studio ouvindo em http://{args.host}:{args.porta}/v1/pecas (Ctrl+C para parar)",
              file=sys.stderr)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            print("\nparando…", file=sys.stderr)
        finally:
            http.server_close()
        return 0
    finally:
        servico.parar(esperar=False)


def comando_analisar_referencia(args, roteador):
    import subprocess
    import tomllib

    from .config import RAIZ
    from .rede import ErroProvedor
    from .calibracao import carregar_ancoras
    from .referencias import analisar_referencia
    from .seguranca import mascarar
    from .roteador import TodosFalharam

    try:
        categorias = tomllib.loads((RAIZ / "config" / "referencias.toml").read_text(encoding="utf-8"))["categorias"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        categorias = {}
    categorias = {k: v for k, v in categorias.items() if isinstance(v, dict)} if isinstance(categorias, dict) else {}
    categoria = args.categoria.upper()
    if categorias and categoria not in categorias:
        print(f"✗ categoria {categoria!r} não existe (use {', '.join(categorias)})", file=sys.stderr)
        return 1
    try:
        cat = categorias.get(categoria) or {}
        r = analisar_referencia(roteador, args.video, categoria, nome_categoria=cat.get("nome"),
                                formato=cat.get("formato"), pasta=RAIZ / "dados" / "referencias",
                                negativo=args.negativo,
                                ancoras=carregar_ancoras(RAIZ / "config" / "ancoras.toml", categoria))
    except (TodosFalharam, ValueError, ErroProvedor, subprocess.CalledProcessError, OSError) as e:
        print(f"✗ não deu para analisar: {mascarar(str(e))}", file=sys.stderr)
        return 1
    p = r["potencial"]
    print(f"✓ {r['origem']} · categoria {categoria} · {r['medido_por']}")
    print(f"  duração {r['duracao_s']:.0f} s · {r['cortes_por_minuto']:.0f} cortes/min · plano médio "
          f"{r['duracao_media_plano_s']:.1f} s · {r['palavras_por_segundo']:.1f} palavras/s")
    print(f"  gancho: {r['gancho']['tipo']} aos {r['gancho']['momento_s']:.0f} s — {r['gancho']['trecho']}")
    print("  estrutura: " + " → ".join(f"{e['parte']} ({e['inicio_s']:.0f}–{e['fim_s']:.0f} s)" for e in r["estrutura"]))
    print(f"  potencial {r['nota_potencial']:.0f}/100: " + ", ".join(f"{c} {v['nota']:.0f}" for c, v in p.items()))
    print(f"  salvo em {r['arquivo']}")
    return 0


def comando_perfil_referencia(args):
    from .config import RAIZ
    from .referencias import NOMES_MEDIDAS, carregar_analises, perfil_da_categoria, salvar_perfil

    categoria = args.categoria.upper()
    analises = carregar_analises(RAIZ / "dados" / "referencias", categoria)
    try:
        perfil = perfil_da_categoria(analises)
    except ValueError as e:
        print(f"✗ categoria {categoria}: {e}. Analise mais vídeos com analisar-referencia.", file=sys.stderr)
        return 1
    negativos = len(analises) - perfil["n"]
    print(f"Categoria {categoria}: {perfil['n']} referências positivas" + (f" ({negativos} negativas fora da conta)"
                                                                          if negativos else ""))
    for m, (baixo, alto) in perfil["faixas"].items():
        print(f"  {NOMES_MEDIDAS[m]}: {baixo:g} a {alto:g}")
    print(f"  ganchos: {', '.join(perfil['gancho_tipos_aceitos']) or '—'}")
    if perfil["medidas_estimadas"]:
        print(f"  {perfil['medidas_estimadas']} de {perfil['n']} com números estimados pelo Gemini (link); "
              "arquivos locais são medidos pelo FFmpeg")
    if perfil["nota_potencial_minima"] is not None:
        print(f"  potencial (25º percentil): {perfil['nota_potencial_minima']:g}/100")
    if args.salvar:
        try:
            destino = salvar_perfil(RAIZ / "config" / "perfis_referencia.toml", categoria, perfil)
        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        print(f"✓ salvo em {destino} (revise e commite)")
    else:
        print("  (use --salvar para gravar em config/perfis_referencia.toml)")
    return 0


def comando_nota_referencia(args):
    from .calibracao import registrar_notas
    from .config import RAIZ

    notas = {c: getattr(args, c) for c in ("gancho", "fluxo", "valor", "tendencia") if getattr(args, c) is not None}
    try:
        arq = registrar_notas(RAIZ / "dados" / "referencias", args.video, args.categoria.upper(), notas)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"✓ notas guardadas em {arq}")
    return 0


def comando_calibrar(args):
    from .calibracao import calibrar
    from .config import RAIZ
    from .referencias import carregar_analises

    pasta = RAIZ / "dados" / "referencias"
    cats = [args.categoria.upper()] if args.categoria else sorted(p.name for p in pasta.glob("*") if p.is_dir())
    analises = [a for c in cats for a in carregar_analises(pasta, c)]
    try:
        r = calibrar(analises)
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    g = r["geral"]
    print(f"Calibração ({', '.join(cats) or '—'}): {r['videos']} vídeos · juiz − você = {g['media_diferenca']:+.1f} "
          f"em média (diferença típica {g['media_absoluta']:.1f}) · {g['veredito']}")
    for c, v in r["por_criterio"].items():
        print(f"  {c}: {v['media_diferenca']:+.1f} (típica {v['media_absoluta']:.1f})")
    for p, v in r["por_juiz"].items():
        print(f"  juiz {p}: {v['media_diferenca']:+.1f} · {v['veredito']}")
    for rec in r["recomendacoes"]:
        print(f"→ {rec}")
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"calibracao_{args.categoria.upper() if args.categoria else 'todas'}.json"
    destino.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  salvo em {destino}")
    return 0


def comando_benchmark(args):
    from pathlib import Path

    from . import benchmark as bm
    from .config import RAIZ

    pasta = Path(args.pasta) if args.pasta else RAIZ / "dados" / "benchmark"
    if args.acao == "briefings":
        for b, info in bm.BRIEFINGS.items():
            print(f"{b}. {info['tema']} ({info['tipo']}; testa {info['testa']}) → {pasta / b}/<ferramenta>.mp4")
        print(f"Todos em pt-BR, {bm.PROPORCAO}, ~{bm.DURACAO_S} s. Depois: benchmark dados <briefing> <ferramenta> …")
        return 0
    if args.acao == "dados":
        valores = {c: getattr(args, c) for c in bm.CAMPOS_MANUAIS}
        try:
            arq = bm.registrar_dados(pasta, args.briefing, args.ferramenta, valores, args.obs)
        except ValueError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        print(f"✓ anotado em {arq}")
        return 0
    if args.acao == "produzir":
        return comando_benchmark_produzir(args, pasta)
    from .config import carregar_avaliador

    resultados = bm.avaliar_benchmark(pasta, lambda: carregar_avaliador(caminho=args.config),
                                      aviso=lambda t: print(t, file=sys.stderr, flush=True), refazer=args.refazer)
    if not resultados:
        print(f"✗ nenhum vídeo em {pasta}/<A|B|C>/ (veja: benchmark briefings)", file=sys.stderr)
        return 1
    texto = bm.relatorio_markdown(resultados)
    (pasta / "relatorio.md").write_text(texto, encoding="utf-8")
    for r in bm.ranking(resultados):
        nota = "sem juiz" if r["nota_juiz"] is None else f"juiz {r['nota_juiz']:g}"
        print(f"  {r['ferramenta']}: {nota} · {r['videos']} vídeo(s) · {r['problemas']} problema(s) automático(s)")
    for r in resultados:
        if r.get("sem_juiz"):
            motivo = next(iter(r.get("problemas_juiz") or []), "motivo desconhecido")
            print(f"  ⚠ {r['briefing']} · {r['ferramenta']} sem juiz: {motivo}")
    print(f"✓ relatório em {pasta / 'relatorio.md'}")
    if args.doc:
        doc = RAIZ / "docs" / "sdd" / "04b-benchmark-pratico.md"
        if doc.is_file() and doc.read_text(encoding="utf-8") != texto:
            print(f"  ⚠ {doc.name} já existia e foi substituído (a versão anterior fica no Git)")
        doc.write_text(texto, encoding="utf-8")
        print(f"✓ também em {doc} (revise e commite)")
    return 0


def comando_benchmark_produzir(args, pasta):
    from . import benchmark as bm
    from .config import carregar_biblioteca, carregar_config, carregar_loop
    from .montagem import ErroMontagem
    from .producao import ErroProducao, produzir_video
    from .pronuncia import conferir_voz
    from .rede import ErroProvedor

    try:
        briefings = [bm.briefing_valido(b) for b in args.briefing]
    except ValueError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    import time

    falhas = 0
    for b in briefings:
        tema = bm.BRIEFINGS[b]["tema"]
        if (pasta / b / f"{bm.ESTUDIO}.mp4").is_file() and not args.refazer:
            print(f"== briefing {b}: já tem vídeo do Studio (use --refazer para rodar de novo)", file=sys.stderr)
            continue
        print(f"== briefing {b}: {tema}", file=sys.stderr)
        inicio = time.monotonic()
        roteador = carregar_roteador(args.config)  # um teto de US$ 1,50 por vídeo, não um para os três
        roteador.aviso = lambda texto: print(texto, file=sys.stderr, flush=True)
        trabalho = pasta / b / "_studio"
        try:
            rel = produzir_video(roteador, carregar_loop(roteador, args.config), tema, trabalho,
                                 duracao=bm.DURACAO_S, proporcao=bm.PROPORCAO, pesquisar=not args.sem_pesquisa,
                                 cfg_montagem=carregar_config(args.config).get("montagem"),
                                 aviso=lambda t: print(t, file=sys.stderr, flush=True),
                                 biblioteca=carregar_biblioteca(args.config), conferir_voz=conferir_voz)
        except KeyboardInterrupt:
            bm.registrar_execucao(pasta, b, custo_usd=roteador.orcamento.gasto_usd, tempo_s=time.monotonic() - inicio)
            print(f"\n✗ interrompido. Rode de novo para continuar (o que ficou pronto está em {trabalho}).",
                  file=sys.stderr)
            return 130
        except (ErroProducao, ErroMontagem, ErroProvedor, OSError) as e:
            # o que já foi gasto conta no custo do Studio, mesmo sem vídeo
            bm.registrar_execucao(pasta, b, custo_usd=roteador.orcamento.gasto_usd, tempo_s=time.monotonic() - inicio)
            print(f"✗ briefing {b} parou: {e}. Rode de novo para continuar.", file=sys.stderr)
            falhas += 1
            continue
        if bm.nada_novo(rel) and (pasta / b / f"{bm.ESTUDIO}.json").is_file():
            destino = pasta / b / f"{bm.ESTUDIO}.mp4"  # só reaproveitou: não soma outra execução
            import shutil

            shutil.copyfile(rel["video"], destino)
        else:
            destino = bm.registrar_execucao(pasta, b, custo_usd=rel["custo_usd"], tempo_s=rel["tempo_s"],
                                            tentativas=bm.tentativas_do_relatorio(rel), relatorio=rel)
        print(f"{'✓' if rel['aprovado'] else '⚠'} {destino} · US$ {rel['custo_usd']:.3f} · {rel['tempo_s']} s")
    return 1 if falhas else 0


def comando_testar_voz(args, roteador):
    from pathlib import Path

    from .pronuncia import FRASE_TESTE, conferir_voz
    from .rede import ErroProvedor

    frase, pasta = args.frase or FRASE_TESTE, Path(args.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    print(f"Frase: {frase}\n")
    algum = False
    for nome in roteador.cadeias.get("voz", []):
        prov = roteador.provedores[nome]
        motivo = prov.configurado()
        if motivo:
            print(f"  {nome:12s} pulado ({motivo})")
            continue
        algum = True
        saida = pasta / f"{nome}.mp3"
        try:
            prov.executar(texto=frase, saida=saida)
        except (ErroProvedor, ValueError, OSError) as e:
            print(f"  {nome:12s} falhou: {e}")
            continue
        c = conferir_voz(saida, frase)
        nota = f"erro de palavras {c['wer']:.0%} ({'ok' if c['ok'] else 'acima de 10%'})" if c else "sem transcrição"
        print(f"  {nome:12s} {saida} · {nota}")
    if algum:
        print("\nOuça os arquivos: a transcrição às vezes corrige pronúncia ruim pelo contexto (ex.: 'ola' → 'olha').")
    return 0 if algum else 1


def comando_exportar_capcut(args):
    from pathlib import Path

    from .exportar import ErroExportacao, exportar_capcut
    from .rede import ErroProvedor

    pasta = Path(args.pasta)
    try:
        resultado = json.loads((pasta / "montagem.json").read_text(encoding="utf-8"))
        rel = json.loads((pasta / "relatorio.json").read_text(encoding="utf-8")) if (pasta / "relatorio.json").is_file() else {}
        guardada = Path(resultado.get("pasta_trabalho") or "")
        trabalho = guardada if guardada.is_dir() else pasta / "montagem"  # a pasta do vídeo pode ter sido movida
        destino = exportar_capcut(resultado, pasta / "capcut", creditos=rel.get("creditos"), titulo=rel.get("titulo"),
                                  pasta_trabalho=trabalho)
    except FileNotFoundError:
        print(f"✗ {pasta} não tem montagem.json: produza o vídeo primeiro (comando produzir)", file=sys.stderr)
        return 1
    except (ErroExportacao, ErroProvedor, OSError, ValueError) as e:
        print(f"✗ não deu para exportar: {e}", file=sys.stderr)
        return 1
    print(f"✓ pasta para o CapCut: {destino} (veja o LEIA-ME.txt)")
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
    # Windows com saída redirecionada usa cp1252: "✓" quebrava o comando. Troca por "?" em vez de cair.
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass  # fluxo trocado (testes, StringIO)
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

    s = sub.add_parser("produzir", help="vídeo completo: roteiro com juiz, imagens, narração, cenas e montagem")
    s.add_argument("tema")
    s.add_argument("-d", "--duracao", type=int, default=30, help="segundos (padrão 30)")
    s.add_argument("-p", "--perfil", help="id do perfil do projeto (formato, estilo, voz)")
    s.add_argument("--pesquisa", action="store_true", help="pesquisa na web antes do roteiro (fontes reais)")
    s.add_argument("--trilha", help="arquivo de música (padrão: escolhida pelo clima do roteiro)")
    s.add_argument("--sem-trilha", action="store_true", help="vídeo só com a narração")
    s.add_argument("--bpm", type=float, help="batidas por minuto da trilha (opcional)")
    s.add_argument("-o", "--pasta", help="pasta do vídeo (padrão: saidas/<tema>)")
    s.add_argument("--refazer-roteiro", action="store_true", help="faz um roteiro novo (e cenas novas) mesmo se já houver")
    s.add_argument("--capcut", action="store_true", help="também gera a pasta para editar no CapCut (<pasta>/capcut)")
    s.add_argument("--sem-conferir-voz", action="store_true",
                   help="não transcreve a narração para conferir a pronúncia (mais rápido, sem custo de transcrição)")

    s = sub.add_parser("analisar-referencia", help="analisa um vídeo de referência (link do YouTube ou arquivo) para a régua")
    s.add_argument("video", help="link de um vídeo do YouTube (sem baixar) ou arquivo local")
    s.add_argument("-c", "--categoria", required=True, help="categoria de referência (A, B, C… de config/referencias.toml)")
    marca = s.add_mutually_exclusive_group()
    marca.add_argument("--negativo", dest="negativo", action="store_const", const=True,
                       help="exemplo do que NÃO fazer (fica fora das faixas do perfil)")
    marca.add_argument("--positivo", dest="negativo", action="store_const", const=False,
                       help="desfaz um --negativo anterior (sem nenhum dos dois, mantém o que estava)")

    s = sub.add_parser("perfil-referencia", help="faixas típicas (25º–75º) de uma categoria a partir das análises")
    s.add_argument("-c", "--categoria", required=True, help="categoria (A–F)")
    s.add_argument("--salvar", action="store_true", help="grava em config/perfis_referencia.toml (revise e commite)")

    s = sub.add_parser("nota-referencia", help="sua nota (0 a 10) para um vídeo de referência já analisado (K14)")
    s.add_argument("video", help="o mesmo link ou arquivo usado no analisar-referencia")
    s.add_argument("-c", "--categoria", required=True, help="categoria (A–F)")
    for c in ("gancho", "fluxo", "valor", "tendencia"):
        s.add_argument(f"--{c}", type=float, help=f"nota de 0 a 10 para {c}")

    s = sub.add_parser("calibrar", help="compara as suas notas com as do juiz nas referências (K14)")
    s.add_argument("-c", "--categoria", help="só uma categoria (padrão: todas)")

    s = sub.add_parser("benchmark", help="teste prático: mesmos 3 briefings e mesma régua para todas as ferramentas (K31)")
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--pasta", help="pasta do benchmark (padrão dados/benchmark)")
    bm = s.add_subparsers(dest="acao", required=True)
    b = bm.add_parser("produzir", parents=[comum], help="faz os vídeos do Studio para os briefings (cada um com o próprio teto)")
    b.add_argument("-b", "--briefing", nargs="+", default=["A", "B", "C"], help="quais briefings (A, B, C)")
    b.add_argument("--sem-pesquisa", action="store_true", help="não pesquisa fontes antes do roteiro")
    b.add_argument("--refazer", action="store_true", help="roda de novo os briefings que já têm vídeo do Studio")
    b = bm.add_parser("dados", parents=[comum], help="anota tempo, custo, intervenções e suas notas de uma ferramenta num briefing")
    b.add_argument("briefing", help="A, B ou C")
    b.add_argument("ferramenta", help="nome da ferramenta, igual ao nome do arquivo do vídeo (ex.: capcut)")
    b.add_argument("--tempo-min", type=float, help="minutos até o vídeo pronto")
    b.add_argument("--custo", type=float, dest="custo_usd", help="custo real em US$ (0 no grátis)")
    b.add_argument("--creditos", type=float, help="créditos gastos")
    b.add_argument("--intervencoes", type=float, help="quantas vezes você precisou mexer à mão")
    b.add_argument("--tentativas", type=float, help="tentativas até um resultado aceitável")
    b.add_argument("--nota", type=float, dest="nota_diego", help="sua nota geral de 0 a 10")
    b.add_argument("--voz", type=float, dest="voz_ptbr", help="voz em pt-BR, de 0 a 10")
    b.add_argument("--legenda", type=float, dest="legenda_ptbr", help="legenda em pt-BR, de 0 a 10")
    b.add_argument("--obs", help="observação curta")
    b = bm.add_parser("avaliar", parents=[comum], help="passa todos os vídeos pela mesma régua e gera o relatório comparativo")
    b.add_argument("--doc", action="store_true", help="grava também docs/sdd/04b-benchmark-pratico.md")
    b.add_argument("--refazer", action="store_true", help="julga de novo vídeos já julgados (paga de novo)")
    bm.add_parser("briefings", parents=[comum], help="mostra os 3 briefings e onde salvar os vídeos")

    s = sub.add_parser("testar-voz", help="grava uma frase difícil (lh, nh, rr) em cada voz pronta e mede o erro")
    s.add_argument("-o", "--pasta", default="saidas/teste-voz")
    s.add_argument("--frase", help="frase de teste (padrão: palavras com lh, nh, r e rr)")

    s = sub.add_parser("servidor", help="servidor HTTP local para o Torralles Ops pedir peças (spec 08)")
    s.add_argument("--porta", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1", help="padrão: só este PC")
    sub.add_parser("mcp", help="servidor MCP por stdio para o Hermes (produzir_peca, consultar_peca)")

    s = sub.add_parser("exportar-capcut", help="pasta para editar no CapCut a partir de um vídeo já produzido")
    s.add_argument("pasta", help="pasta do vídeo (ex.: saidas/beneficios-do-cha-verde)")

    s = sub.add_parser("montar", help="monta o vídeo final (cenas, narração, legendas, trilha) e confere a régua")
    s.add_argument("projeto", help="arquivo JSON com as cenas (veja docs/montagem.md)")
    s.add_argument("-o", "--saida", default="saidas/final.mp4")
    s.add_argument("--trabalho", help="pasta para guardar clipes, áudios e legendas (para o CapCut)")

    args = p.parse_args(argv)
    if args.comando in ("servidor", "mcp"):
        return comando_servidor(args)
    if args.comando == "exportar-capcut":
        return comando_exportar_capcut(args)
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
    if args.comando == "benchmark":
        return comando_benchmark(args)
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

    if args.comando == "produzir":
        return comando_produzir(args, roteador, perfil)
    if args.comando == "analisar-referencia":
        return comando_analisar_referencia(args, roteador)
    if args.comando == "perfil-referencia":
        return comando_perfil_referencia(args)
    if args.comando == "nota-referencia":
        return comando_nota_referencia(args)
    if args.comando == "calibrar":
        return comando_calibrar(args)
    if args.comando == "testar-voz":
        return comando_testar_voz(args, roteador)
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

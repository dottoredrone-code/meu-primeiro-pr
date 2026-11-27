"""Painel do Studio no navegador (K43, spec 15): dados para a página local servida pelo servidor.py.

Nada aqui recebe caminho do navegador: projeto é um id (nome da pasta em `saidas/` ou o job_id do pedido), arquivo
é um nome de uma lista fechada e mídia da biblioteca é um hash. Toda pasta resolvida precisa ficar dentro de
`saidas/` (ou da biblioteca), sem link simbólico.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ID_PROJETO = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
ID_PEDIDO = re.compile(r"^stu_[0-9a-f]{4,32}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
ITEM = re.compile(r"^(video|capa|post|peca|cena_\d{2})$")
ARQUIVO = re.compile(r"^(video_final\.mp4|capa\.jpg|peca\.png|base\.png|cena_\d{2}\.(png|jpg|mp4)|voz_\d{2}\.(mp3|wav))$")
DECISOES = ("aprovado", "alterar")
PASTAS_FORA = {"pedidos", "teste-voz", "percepcao"}  # pastas de saídas/ que não são projetos
TIPOS_ARQUIVO = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".mp3": "audio/mpeg", ".wav": "audio/wav", ".webp": "image/webp", ".gif": "image/gif",
                 ".webm": "video/webm", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
LIMITE_COMENTARIO = 2000
LIMITE_POST = 20_000
FORMATOS = {"9:16": "1080x1920", "4:5": "1080x1350", "1:1": "1080x1080", "16:9": "1920x1080"}
TIPOS_PECA = {"video_curto": "reels", "story": "story", "imagem": "post estático"}


class ErroPainel(Exception):
    """Pedido do painel recusado; a mensagem vai para a tela."""

    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.codigo = codigo


def _ler_json(arquivo):
    try:
        return json.loads(Path(arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _data(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def link_seguro(valor):
    """Só link http(s) vai para a tela: dado de API de terceiros (Openverse, Pexels) nunca vira 'javascript:'."""
    texto = str(valor or "").strip()
    return texto if re.fullmatch(r"https?://[^\s<>\"']+", texto, re.I) else None


def _tem_projeto(pasta):
    return pasta.is_dir() and any((pasta / n).is_file() for n in ("relatorio.json", "roteiro.json", "peca.png"))


def _dentro(filho, pai):
    try:
        Path(filho).resolve().relative_to(Path(pai).resolve())
        return True
    except (OSError, ValueError):
        return False


class Painel:
    def __init__(self, saidas, caminho_banco, *, config=None, servico=None, pasta_biblioteca=None):
        self.saidas = Path(saidas)
        self.pasta_biblioteca = Path(pasta_biblioteca) if pasta_biblioteca else None
        self.caminho_banco = str(caminho_banco)
        self.config = config
        self.servico = servico

    def _banco(self):
        from .banco import Banco

        return Banco(self.caminho_banco)

    def _biblioteca(self, banco):
        if self.pasta_biblioteca is not None:
            from .biblioteca import Biblioteca

            return Biblioteca(self.pasta_biblioteca, banco)
        from .config import carregar_biblioteca

        return carregar_biblioteca(self.config, banco=banco)

    # -- pastas ---------------------------------------------------------------
    def pasta(self, pid):
        """Pasta do projeto `pid` (ou ErroPainel 404). Pedido: saidas/pedidos/<job_id>."""
        pid = str(pid)
        if not ID_PROJETO.fullmatch(pid) or pid in PASTAS_FORA:
            raise ErroPainel("projeto inválido", 404)
        base = self.saidas / "pedidos" if ID_PEDIDO.fullmatch(pid) else self.saidas
        pasta = base / pid
        if pasta.is_symlink() or (pasta.exists() and not _dentro(pasta, self.saidas)):
            raise ErroPainel("projeto inválido", 404)
        return pasta

    def arquivo(self, pid, nome):
        """Caminho de um arquivo do projeto pelo nome (lista fechada) ou ErroPainel 404."""
        if not ARQUIVO.fullmatch(str(nome)):
            raise ErroPainel("arquivo não permitido", 404)
        pasta = self.pasta(pid)
        alvo = pasta / nome
        if alvo.is_symlink() or not alvo.is_file() or not _dentro(alvo, pasta):
            raise ErroPainel("arquivo não encontrado", 404)
        return alvo

    def midia(self, digest):
        """Arquivo da biblioteca pelo hash (só ativos visíveis: licença registrada)."""
        if not HASH.fullmatch(str(digest)):
            raise ErroPainel("mídia inválida", 404)
        with self._banco() as banco:
            bib = self._biblioteca(banco)
            ativo = bib.obter(digest)
            alvo = bib.caminho(ativo) if ativo else None
            raiz = bib.raiz
        if alvo is None or alvo.is_symlink() or not alvo.is_file() or not _dentro(alvo, raiz):
            raise ErroPainel("mídia não encontrada", 404)
        return alvo

    # -- listas ---------------------------------------------------------------
    def _ultimas_decisoes(self, revisoes):
        """item → última decisão (as revisões chegam da mais nova para a mais velha)."""
        ultimas = {}
        for r in revisoes:
            ultimas.setdefault(r["item"], r)
        return ultimas

    def _resumo_pasta(self, pid, pasta, pedido=None, decisoes=None):
        rel = _ler_json(pasta / "relatorio.json") if pasta.is_dir() else None
        rot = _ler_json(pasta / "roteiro.json") if pasta.is_dir() else None
        rel = rel if isinstance(rel, dict) else {}
        rot = rot if isinstance(rot, dict) else {}
        roteiro = rot.get("roteiro") if isinstance(rot.get("roteiro"), dict) else {}
        resultado = (pedido or {}).get("resultado") or {}
        imagem = (pasta / "peca.png").is_file() or (pedido or {}).get("pedido", {}).get("entregavel") == "imagem"
        if pedido:
            status = pedido["status"]
            briefing = pedido["pedido"].get("briefing", {})
            titulo = rel.get("titulo") or roteiro.get("titulo") or briefing.get("conceito_visual", "")[:90]
            atualizado = pedido["atualizado_em"]
            custo = resultado.get("custo_usd", rel.get("custo_usd"))
            perfil = pedido["pedido"].get("perfil")
        else:
            status = ("pronto" if rel.get("aprovado") else "pronto_com_avisos") if rel else "incompleto"
            titulo = rel.get("titulo") or roteiro.get("titulo") or rel.get("tema") or rot.get("tema") or pid
            marcas = [p.stat().st_mtime for p in (pasta / "relatorio.json", pasta / "roteiro.json") if p.is_file()]
            atualizado = _data(max(marcas)) if marcas else None
            custo = rel.get("custo_usd")
            perfil = None
        decisoes = decisoes or {}
        principal = decisoes.get("peca" if imagem else "video")
        pendentes = [i for i, r in decisoes.items() if r["decisao"] == "alterar" and not r["atendida"]]
        return {
            "id": pid, "tipo": "imagem" if imagem else "video", "titulo": titulo, "tema": rel.get("tema") or rot.get("tema"),
            "status": status, "nota": rot.get("nota"), "custo_usd": custo, "duracao_s": rel.get("duracao_s"),
            "proporcao": rel.get("proporcao") or rot.get("proporcao"), "atualizado_em": atualizado, "perfil": perfil,
            "capa": next((n for n in ("capa.jpg", "peca.png", "cena_01.png", "cena_01.jpg")
                          if (pasta / n).is_file() and not (pasta / n).is_symlink()), None),
            "decisao": principal["decisao"] if principal else None, "alteracoes_pendentes": len(pendentes),
        }

    def projetos(self):
        with self._banco() as banco:
            pedidos = banco.listar_pedidos()
            todas = banco.revisoes()
        por_projeto = {}
        for r in todas:
            por_projeto.setdefault(r["projeto"], []).append(r)
        itens = []
        vistos = set()
        for p in pedidos:
            vistos.add(p["id"])
            itens.append(self._resumo_pasta(p["id"], self.saidas / "pedidos" / p["id"], p,
                                            self._ultimas_decisoes(por_projeto.get(p["id"], []))))
        if self.saidas.is_dir():
            for pasta in self.saidas.iterdir():
                pid = pasta.name
                if (pid in vistos or pid in PASTAS_FORA or not ID_PROJETO.fullmatch(pid) or pasta.is_symlink()
                        or not _tem_projeto(pasta) or not _dentro(pasta, self.saidas)):
                    continue  # junção/atalho para fora de saidas/ não aparece
                itens.append(self._resumo_pasta(pid, pasta, None,
                                                self._ultimas_decisoes(por_projeto.get(pid, []))))
        itens.sort(key=lambda x: x["atualizado_em"] or "", reverse=True)
        return itens

    def _pedido(self, pid):
        if not ID_PEDIDO.fullmatch(pid):
            return None
        with self._banco() as banco:
            return banco.pedido(pid)

    def projeto(self, pid):
        pasta = self.pasta(pid)
        pedido = self._pedido(pid)
        if not pedido and not _tem_projeto(pasta):
            raise ErroPainel("projeto não encontrado", 404)
        with self._banco() as banco:
            revisoes = banco.revisoes(pid)
        ultimas = self._ultimas_decisoes(revisoes)
        resumo = self._resumo_pasta(pid, pasta, pedido, ultimas)
        rel = _ler_json(pasta / "relatorio.json") if pasta.is_dir() else None
        rel = rel if isinstance(rel, dict) else {}
        rot = _ler_json(pasta / "roteiro.json") if pasta.is_dir() else None
        rot = rot if isinstance(rot, dict) else {}
        roteiro = rot.get("roteiro") if isinstance(rot.get("roteiro"), dict) else {}
        fotos = _ler_json(pasta / "fotos.json") if pasta.is_dir() else None
        fotos = fotos if isinstance(fotos, dict) else {}
        etapas = rel.get("etapas") if isinstance(rel.get("etapas"), list) else []

        def presente(*nomes):
            for nome in nomes:
                alvo = pasta / nome
                if alvo.is_file() and not alvo.is_symlink():
                    return {"nome": nome, "versao": int(alvo.stat().st_mtime)}
            return None

        cenas = []
        for i, cena in enumerate(roteiro.get("cenas") or [], 1):
            if not isinstance(cena, dict):
                continue
            n = f"{i:02d}"
            foto = fotos.get(str(i)) if isinstance(fotos.get(str(i)), dict) else None
            etapa_img = next((e for e in etapas if isinstance(e, dict) and e.get("etapa") == f"cena {i}: imagem"), {})
            origem = None
            if foto:
                origem = {k: foto.get(k) for k in ("fonte", "autor", "licenca", "titulo")}
                origem["link"] = link_seguro(foto.get("link"))
                origem["video_banco"] = bool(foto.get("video_banco"))
            elif etapa_img.get("provedor"):
                origem = {"fonte": etapa_img.get("provedor"), "licenca": etapa_img.get("licenca")}
            cenas.append({
                "numero": i, "item": f"cena_{n}", "narracao": cena.get("narracao"), "texto_tela": cena.get("texto_tela"),
                "clima": cena.get("clima"), "duracao": cena.get("duracao"), "prompt_imagem": cena.get("prompt_imagem"),
                "imagem": presente(f"cena_{n}.png", f"cena_{n}.jpg"), "video": presente(f"cena_{n}.mp4"),
                "voz": presente(f"voz_{n}.mp3", f"voz_{n}.wav"), "origem": origem,
                "decisao": ultimas.get(f"cena_{n}"),
            })
        post = None
        if (pasta / "post.txt").is_file() and not (pasta / "post.txt").is_symlink():
            try:
                post = (pasta / "post.txt").read_text(encoding="utf-8")[:LIMITE_POST]
            except (OSError, UnicodeDecodeError):
                post = None
        creditos = rel.get("creditos")
        if not creditos and (pasta / "creditos.txt").is_file():
            try:
                creditos = (pasta / "creditos.txt").read_text(encoding="utf-8")[:LIMITE_POST]
            except (OSError, UnicodeDecodeError):
                creditos = None
        detalhe = {
            **resumo,
            "video": presente("video_final.mp4"), "imagem_final": presente("peca.png"),
            "capa_arquivo": presente("capa.jpg"), "post": post, "creditos": creditos,
            "problemas": rel.get("problemas") or [], "medidas": rel.get("medidas") or {},
            "etapas": [{k: e.get(k) for k in ("etapa", "provedor", "reaproveitado", "licenca", "aviso", "aprovado")}
                       for e in etapas if isinstance(e, dict)],
            "trilha": rel.get("trilha"), "efeitos": rel.get("efeitos") or [], "cta": rel.get("cta") or roteiro.get("cta"),
            "referencia": rel.get("referencia"), "capcut": bool(rel.get("capcut")),
            "aprovado_regua": rel.get("aprovado"), "cenas": cenas,
            "decisoes": {k: v for k, v in ultimas.items()}, "historico": revisoes[:100],
            "pedido": None,
        }
        if pedido:
            res = pedido.get("resultado") or {}
            detalhe["pedido"] = {"status": pedido["status"], "erro": pedido.get("erro"),
                                 "briefing": pedido["pedido"].get("briefing"),
                                 "entregavel": pedido["pedido"].get("entregavel"),
                                 "teto_usd": pedido["pedido"].get("orcamento", {}).get("custo_maximo_usd"),
                                 "qualidade": res.get("qualidade"), "revisar_manual": res.get("revisar_manual"),
                                 "criado_em": pedido["criado_em"]}
        return detalhe

    # -- ações ----------------------------------------------------------------
    def revisar(self, pid, dados):
        """Grava a decisão do Diego sobre um item. Aprovar o vídeo (ou a peça) de um pedido aprova o pedido."""
        if not isinstance(dados, dict):
            raise ErroPainel("envie um objeto com item, decisao e comentario")
        item, decisao = str(dados.get("item") or ""), str(dados.get("decisao") or "")
        comentario = dados.get("comentario")
        comentario = comentario.strip() if isinstance(comentario, str) else ""
        if not ITEM.fullmatch(item):
            raise ErroPainel("item inválido (use video, capa, post, peca ou cena_01…)")
        if decisao not in DECISOES:
            raise ErroPainel("decisão inválida (use aprovado ou alterar)")
        if decisao == "alterar" and not comentario:
            raise ErroPainel("diga o que alterar no comentário")
        if len(comentario) > LIMITE_COMENTARIO:
            raise ErroPainel(f"comentário grande demais (até {LIMITE_COMENTARIO} caracteres)")
        pasta = self.pasta(pid)
        pedido = self._pedido(pid)
        if not pedido and not _tem_projeto(pasta):
            raise ErroPainel("projeto não encontrado", 404)
        aviso = None
        if (pedido and decisao == "aprovado" and item in ("video", "peca")
                and pedido["status"] == "aguardando_aprovacao" and self.servico is not None):
            from .servico import TransicaoInvalida

            try:
                self.servico.aprovar(pid)
            except TransicaoInvalida as e:
                aviso = str(e)
        with self._banco() as banco:
            banco.registrar_revisao(pid, item, decisao, comentario or None)
        r = {"ok": True, "item": item, "decisao": decisao}
        if aviso:
            r["aviso"] = aviso
        return r

    def novo(self, dados):
        """Formulário simples do painel → pedido no contrato 1.0 (spec 08) → fila."""
        if self.servico is None:
            raise ErroPainel("a fila não está ligada neste servidor", 503)
        if not isinstance(dados, dict):
            raise ErroPainel("envie um objeto com o tema")
        tema = str(dados.get("tema") or "").strip()
        if not 3 <= len(tema) <= 500:
            raise ErroPainel("escreva o tema (de 3 a 500 caracteres)")
        tipo = str(dados.get("tipo") or "video_curto")
        if tipo not in TIPOS_PECA:
            raise ErroPainel("tipo inválido (vídeo curto, story ou imagem)")
        proporcao = str(dados.get("proporcao") or ("1:1" if tipo == "imagem" else "9:16"))
        if proporcao not in FORMATOS:
            raise ErroPainel("formato inválido (9:16, 4:5, 1:1 ou 16:9)")
        texto = str(dados.get("texto_tela") or "").strip()[:200] or tema[:80]
        paleta = str(dados.get("paleta") or "").strip()[:200] or "livre, com bom contraste para ler no celular"
        pedido = {
            "versao_contrato": "1.0", "origem": {"sistema": "painel"},
            "briefing": {"tipo_peca": TIPOS_PECA[tipo], "conceito_visual": tema, "paleta_cores": paleta,
                         "formato_dimensoes": FORMATOS[proporcao], "texto_overlay": texto,
                         "ferramenta_sugerida": "Torralles Studio"},
            "entregaveis": [tipo], "aprovacao_humana": True,
            "orcamento": {"custo_maximo_usd": dados.get("teto_usd", 1.5), "modo": "economico"},
        }
        if tipo != "imagem":
            pedido["duracao_s"] = dados.get("duracao_s", 15 if tipo == "story" else 30)
        if dados.get("perfil"):
            if str(dados["perfil"]) not in {p["id"] for p in self.perfis()[0]}:
                raise ErroPainel(f"perfil {dados['perfil']!r} não existe", 422)
            pedido["perfil"] = dados["perfil"]
        from .servico import FilaCheia, PedidoInvalido

        try:
            return self.servico.enviar(pedido)
        except PedidoInvalido as e:
            raise ErroPainel("pedido inválido: " + "; ".join(e.problemas), 422) from None
        except FilaCheia as e:
            raise ErroPainel(str(e), 429) from None

    # -- biblioteca e controle ------------------------------------------------
    def biblioteca(self, busca=None, tipo=None, limite=60):
        tipo = tipo if tipo in ("imagem", "video", "audio") else None
        busca = (busca or "").strip()[:100] or None
        with self._banco() as banco:
            bib = self._biblioteca(banco)
            ativos = bib.buscar(tipo=tipo, texto=busca, limite=max(1, min(int(limite), 200)))
        campos = ("hash", "tipo", "titulo", "fonte", "autor", "licenca", "link", "tags", "provedor", "criado_em")
        return [{**{k: a.get(k) for k in campos}, "link": link_seguro(a.get("link"))} for a in ativos]

    def perfis(self):
        """(lista de {id, nome}, erros). Perfil quebrado não derruba o painel."""
        from .config import carregar_perfis

        try:
            perfis = carregar_perfis(self.config)
            return [{"id": p.id, "nome": getattr(p, "nome", None) or p.id} for p in perfis], dict(perfis.erros)
        except Exception as e:
            return [], {"perfis": str(e)[:200]}

    def resumo(self):
        from .config import carregar_roteador
        from .cotas import Cotas, config_cota, conta_de, hora_local

        with self._banco() as banco:
            roteador = carregar_roteador(self.config, banco=banco)
            provedores = {t: [{"nome": n, "pronto": m is None, "motivo": m} for n, m in itens]
                          for t, itens in roteador.status().items()}
            cotas = roteador.cotas or Cotas(banco)
            contas = {}
            for nome, prov in roteador.provedores.items():
                contas.setdefault(conta_de(nome, prov), (nome, prov))
            lista_cotas = []
            for conta, (nome, prov) in sorted(contas.items()):
                cota = config_cota(prov)
                if not cota:
                    continue
                estado = cotas.estado(conta, cota)
                lista_cotas.append({
                    "conta": conta, "usado": estado["usado"], "limite": cota.get("limite"),
                    "esgotado_ate": hora_local(estado["esgotado_ate"]) if estado["esgotado_ate"] else None,
                    "renova_em": hora_local(estado["renova_em"]) if estado["renova_em"] else None})
            fila = {}
            for linha in banco.con.execute("SELECT status, COUNT(*) AS n FROM pedidos GROUP BY status"):
                fila[linha["status"]] = linha["n"]
            pendentes = sum(1 for r in self._ultimas_por_item(banco.revisoes()).values()
                            if r["decisao"] == "alterar" and not r["atendida"])
        lista_perfis, erros_perfis = self.perfis()
        mes = datetime.now(timezone.utc).strftime("%Y-%m")  # as datas gravadas são UTC
        gasto = 0.0
        for p in self.projetos():
            if (p.get("atualizado_em") or "")[:7] == mes and isinstance(p.get("custo_usd"), (int, float)):
                gasto += p["custo_usd"]
        return {"provedores": provedores, "cotas": lista_cotas, "fila": fila, "perfis": lista_perfis,
                "erros_perfis": erros_perfis, "gasto_mes_usd": round(gasto, 4), "mes": mes,
                "teto_video_usd": 1.5, "alteracoes_pendentes": pendentes}

    @staticmethod
    def _ultimas_por_item(revisoes):
        ultimas = {}
        for r in revisoes:
            ultimas.setdefault((r["projeto"], r["item"]), r)
        return ultimas

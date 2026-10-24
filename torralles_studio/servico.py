"""Fila de pedidos de peça (K28, spec 08): o Ops, o Hermes ou outro sistema pede, o Studio produz em segundo plano.

ServicoPecas.enviar() valida o pedido (contrato.py), guarda no SQLite e devolve o job_id na hora.
Um trabalhador (thread) pega um pedido por vez, produz na pasta `saidas/pedidos/<job_id>` e guarda o resultado.
Se o Studio parar no meio, o pedido volta para a fila e a produção retoma sem pagar de novo (producao.py).
"""

import hashlib
import secrets
import subprocess
import sys
import tempfile
import threading
import traceback
from pathlib import Path

from .contrato import estimativa_custo, tema_do_pedido, validar_pedido
from .seguranca import mascarar


class PedidoInvalido(Exception):
    def __init__(self, problemas):
        super().__init__("; ".join(problemas))
        self.problemas = problemas


def _sha256(arquivo):
    h = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _ass_texto(texto, largura, altura, proporcao, fonte="Arial"):
    """Legenda ASS só com o texto do post, grande, centralizado na parte de baixo da área segura."""
    from .montagem import _texto_ass, estilo_legenda, linhas_tela

    e = estilo_legenda(largura, altura, proporcao)
    tamanho = round(e["tamanho_tela"] * 1.2)
    linhas = "\\N".join(map(_texto_ass, linhas_tela(texto, proporcao)))
    return ("[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
            f"PlayResX: {largura}\nPlayResY: {altura}\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Post,{fonte},{tamanho},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,"
            f"{max(4, tamanho // 6)},0,2,{round(largura * 0.07)},{round(largura * 0.07)},{e['margem_baixo']},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,0:00:10.00,Post,,0,0,0,,{linhas}\n")


def compor_imagem(imagem, texto, proporcao, saida, fonte="Arial"):
    """Imagem no tamanho do formato com o texto do briefing por cima (caixa escura para ler em qualquer fundo)."""
    from .provedores.video import tamanho_do_formato
    from .rede import ErroProvedor

    largura, altura = tamanho_do_formato(proporcao)
    with tempfile.TemporaryDirectory() as pasta:
        Path(pasta, "texto.ass").write_text(_ass_texto(texto, largura, altura, proporcao, fonte), encoding="utf-8")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(Path(imagem).resolve()), "-vf",
             f"scale={largura}:{altura}:force_original_aspect_ratio=increase,crop={largura}:{altura},setsar=1,"
             "ass=texto.ass", "-frames:v", "1", str(Path(saida).resolve())],
            capture_output=True, text=True, cwd=pasta)
    if proc.returncode != 0:
        raise ErroProvedor(f"ffmpeg falhou ao compor a imagem: {proc.stderr.strip()[-200:]}")
    return Path(saida)


def fabricar_peca(pedido, pasta, *, config=None, aviso=None):
    """Produz o entregável do pedido e devolve o resultado no formato da spec 08 (sem job_id/status)."""
    from .config import carregar_biblioteca, carregar_config, carregar_loop, carregar_perfis, carregar_roteador
    from .seguranca import Orcamento

    avisar = aviso or (lambda texto: None)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    roteador = carregar_roteador(config)
    perfil = carregar_perfis(config).obter(pedido["perfil"]) if pedido.get("perfil") else None
    if perfil:
        roteador = perfil.roteador(roteador)
    roteador.orcamento = Orcamento(pedido["orcamento"]["custo_maximo_usd"])  # teto do pedido (nunca acima de 1,50)
    roteador.aviso = avisar
    biblioteca = carregar_biblioteca(config)
    tema = tema_do_pedido(pedido)

    if pedido["entregavel"] in ("video_curto", "story"):
        from .producao import produzir_video

        rel = produzir_video(roteador, carregar_loop(roteador, config), tema, pasta, duracao=pedido["duracao_s"],
                             perfil=perfil, biblioteca=biblioteca, capcut=True, fatos=pedido["fatos_travados"],
                             proporcao=pedido["proporcao"], cfg_montagem=carregar_config(config).get("montagem"),
                             aviso=avisar)
        roteiro = next((e for e in rel["etapas"] if e["etapa"] == "roteiro"), {})
        problemas = list(rel["problemas"]) + list(roteiro.get("problemas") or [])
        fatos_ok = not any("não autorizad" in p or "proibid" in p for p in problemas)
        arquivos = [{"tipo": "video", "caminho": rel["video"], "sha256": _sha256(rel["video"]),
                     "licenca": "comercial_ok", "provedor": "torralles_studio"}]
        return {
            "arquivos": arquivos, "exportacao_capcut": rel.get("capcut"),
            "qualidade": {"nota_estrutural": max(0, 100 - 10 * len(rel["problemas"])),
                          "nota_criativa": roteiro.get("nota"), "aprovado": rel["aprovado"] and fatos_ok,
                          "fatos_travados_ok": fatos_ok, "problemas": problemas[:10]},
            "creditos": rel.get("creditos"), "custo_usd": rel["custo_usd"],
            "tentativas": sum(1 for e in rel["etapas"] if not e["reaproveitado"]),
            "revisar_manual": not rel["aprovado"] or roteiro.get("aprovado") is False,
        }

    # imagem (post estático): IA de imagem ou foto gratuita licenciada + texto do briefing por cima
    from . import funcoes
    from .producao import ErroProducao, _foto_gratuita, _gerar, prompt_da_imagem
    from .roteador import TodosFalharam

    cena = {"prompt_imagem": f"{pedido['briefing']['conceito_visual']}. Cores: {pedido['briefing']['paleta_cores']}"}
    base, foto = pasta / "base.png", None
    try:
        r = _gerar(base, lambda saida: funcoes.gerar_imagem(roteador, prompt_da_imagem(cena, pedido["proporcao"]), saida,
                                                            perfil=perfil, proporcao=pedido["proporcao"]))
        provedor = r.provedor
    except (TodosFalharam, ErroProducao):
        foto = _foto_gratuita(roteador, biblioteca, cena, base, pedido["proporcao"], perfil, avisar)
        provedor = f"foto gratuita ({foto['fonte']})"
    final = compor_imagem(base, pedido["briefing"]["texto_overlay"], pedido["proporcao"], pasta / "peca.png")
    creditos = biblioteca.creditos([foto]) if foto else None
    return {
        "arquivos": [{"tipo": "imagem", "caminho": str(final), "sha256": _sha256(final),
                      "licenca": foto["licenca"] if foto else "comercial_ok", "provedor": provedor}],
        "exportacao_capcut": None,
        "qualidade": {"nota_estrutural": 100, "nota_criativa": None, "aprovado": True, "fatos_travados_ok": True,
                      "problemas": ["sem juiz de imagem ainda: confira antes de publicar"]},
        "creditos": creditos, "custo_usd": round(roteador.orcamento.gasto_usd, 4), "tentativas": 1,
        "revisar_manual": True,
    }


class ServicoPecas:
    """Fila de pedidos no SQLite + um trabalhador em segundo plano."""

    def __init__(self, caminho_banco, *, pasta_base="saidas/pedidos", fabricar=fabricar_peca, config=None):
        self.caminho_banco = str(caminho_banco)
        self.pasta_base = Path(pasta_base)
        self.fabricar = fabricar
        self.config = config
        self._parar = threading.Event()
        self._acordar = threading.Event()
        self._thread = None
        with self._banco() as banco:
            banco.retomar_pedidos()

    def _banco(self):
        from .banco import Banco

        return Banco(self.caminho_banco)

    # -- portas (HTTP e MCP chamam estas) --------------------------------------
    def enviar(self, dados):
        pedido, problemas = validar_pedido(dados)
        if problemas:
            raise PedidoInvalido(problemas)
        job_id = "stu_" + secrets.token_hex(8)
        with self._banco() as banco:
            banco.criar_pedido(job_id, pedido)
        self._acordar.set()
        return {"job_id": job_id, "status": "na_fila", "estimativa_custo_usd": estimativa_custo(pedido)}

    def consultar(self, job_id):
        with self._banco() as banco:
            p = banco.pedido(str(job_id))
        if not p:
            return None
        return {"job_id": p["id"], "status": p["status"], **(p["resultado"] or {}),
                **({"erro": p["erro"]} if p["erro"] else {})}

    # -- trabalhador -----------------------------------------------------------
    def processar_proximo(self):
        """Produz o pedido mais antigo da fila. Devolve o job_id processado ou None se a fila estava vazia."""
        with self._banco() as banco:
            p = banco.proximo_pedido()
        if not p:
            return None
        pasta = self.pasta_base / p["id"]
        try:
            resultado = self.fabricar(p["pedido"], pasta, config=self.config)
            status = "aguardando_aprovacao" if p["pedido"].get("aprovacao_humana") else "concluido"
            with self._banco() as banco:
                banco.atualizar_pedido(p["id"], status, resultado)
        except Exception as e:  # o pedido falha sozinho; a fila continua
            detalhe = mascarar(f"{type(e).__name__}: {e}")
            with self._banco() as banco:
                banco.atualizar_pedido(p["id"], "falhou", erro=detalhe[:500])
            print(mascarar(traceback.format_exc()), file=sys.stderr)  # detalhe para quem cuida, sem chaves
        return p["id"]

    def _laco(self):
        while not self._parar.is_set():
            if self.processar_proximo() is None:
                self._acordar.wait(timeout=5)
                self._acordar.clear()

    def iniciar(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._laco, name="studio-trabalhador", daemon=True)
            self._thread.start()
        return self

    def parar(self, esperar=True):
        self._parar.set()
        self._acordar.set()
        if esperar and self._thread:
            self._thread.join(timeout=30)

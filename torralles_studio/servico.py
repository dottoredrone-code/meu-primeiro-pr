"""Fila de pedidos de peça (K28, spec 08): o Ops, o Hermes ou outro sistema pede, o Studio produz em segundo plano.

ServicoPecas.enviar() valida o pedido (contrato.py), guarda no SQLite e devolve o job_id na hora.
Um trabalhador (thread) pega um pedido por vez, produz na pasta `saidas/pedidos/<job_id>` e guarda o resultado.
Se o Studio parar no meio, o pedido volta para a fila e a produção retoma sem pagar de novo (producao.py).
"""

import hashlib
import inspect
import os
import secrets
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import ff
from .contrato import estimativa_custo, tema_do_pedido, validar_pedido
from .seguranca import mascarar


LIMITE_FILA = 20  # pedidos esperando ao mesmo tempo (protege o bolso se algo enviar pedidos sem parar)


class FilaCheia(Exception):
    """Muitos pedidos esperando: o Ops deve tentar de novo depois."""


class PedidoInvalido(Exception):
    def __init__(self, problemas):
        super().__init__("; ".join(problemas))
        self.problemas = problemas


class TransicaoInvalida(Exception):
    """Aprovar ou cancelar um pedido num status que não permite (ex.: cancelar um pedido já concluído)."""


class PedidoCancelado(BaseException):
    """A produção deve parar: o pedido foi cancelado ou passou para outro processo.

    É BaseException de propósito: os `except Exception` da produção (fallback, trilha, efeitos) não a engolem.
    """


TRAVA = ".produzindo.trava"  # arquivo exclusivo na pasta do pedido: um processo por pasta
TRAVA_VELHA_S = 180  # trava sem toque há 3 min é de processo travado ou morto (mesmo prazo do pedido órfão)


def _processo_vivo(pid):
    """True se o processo `pid` existe. No Windows, os.kill(pid, 0) MATARIA o processo: usa a API do sistema."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes

        k32 = ctypes.windll.kernel32
        alca = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not alca:
            return ctypes.GetLastError() == 5  # acesso negado: existe, mas é de outro usuário
        try:
            codigo = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(alca, ctypes.byref(codigo)):
                return True
            return codigo.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(alca)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def travar_pasta(pasta, dono):
    """Cria a trava exclusiva da pasta do pedido (O_CREAT|O_EXCL). Devolve o caminho, ou None se outro processo
    vivo está produzindo nela. Trava de processo morto (ou sem toque há TRAVA_VELHA_S) é recuperada."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    trava = pasta / TRAVA
    conteudo = f"{os.getpid()}\n{dono}\n".encode()
    for _ in range(3):
        try:
            fd = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                pid = int(trava.read_text(encoding="utf-8").split()[0])
            except (OSError, ValueError, IndexError):
                pid = -1  # trava ilegível (queda no meio da escrita): conta como morta
            try:
                velha = time.time() - trava.stat().st_mtime > TRAVA_VELHA_S
            except OSError:
                continue  # sumiu entre uma olhada e outra: tenta criar de novo
            if _processo_vivo(pid) and not velha:
                return None
            try:
                trava.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                return None
            continue
        try:
            os.write(fd, conteudo)
        finally:
            os.close(fd)
        return trava
    return None


def soltar_pasta(trava, dono):
    """Remove a trava só se ainda for deste dono (outro processo pode tê-la recuperado)."""
    try:
        if Path(trava).read_text(encoding="utf-8").split()[1:2] == [dono]:
            Path(trava).unlink()
    except OSError:
        pass


def _aviso_que_cancela(aviso, continuar):
    """Envolve o `aviso` do andamento: a cada etapa avisada, se não for para continuar, para a produção.

    A produção (producao.py, roteador.py) chama o aviso antes de cada etapa e antes de cada provedor, ou seja,
    antes de gastar: é o ponto seguro para parar sem pagar de novo.
    """
    avisar = aviso or (lambda texto: None)
    if continuar is None:
        return avisar

    def checar(texto):
        if not continuar():
            raise PedidoCancelado("pedido cancelado ou passou para outro processo")
        return avisar(texto)

    return checar


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
        proc = ff.rodar(
            ["ffmpeg", "-y", "-v", "error", "-i", str(Path(imagem).resolve()), "-vf",
             f"scale={largura}:{altura}:force_original_aspect_ratio=increase,crop={largura}:{altura},setsar=1,"
             "ass=texto.ass", "-frames:v", "1", str(Path(saida).resolve())], cwd=pasta)
    if proc.returncode != 0:
        raise ErroProvedor(f"ffmpeg falhou ao compor a imagem: {proc.stderr.strip()[-200:]}")
    return Path(saida)


class OrcamentoDoPedido:
    """Teto do pedido que vale também nas retomadas: o gasto já feito fica em gasto.json e é descontado."""

    def __new__(cls, teto, arquivo):
        import json

        from .seguranca import Orcamento

        class _Orcamento(Orcamento):
            def registrar(self, provedor, valor):
                super().registrar(provedor, valor)
                if valor:  # grava em arquivo provisório e troca: queda no meio não zera o gasto anotado
                    tmp = Path(str(arquivo) + ".tmp")
                    tmp.write_text(json.dumps({"gasto_usd": round(self.anterior + self.gasto_usd, 6)}),
                                   encoding="utf-8")
                    os.replace(tmp, arquivo)

        try:
            anterior = float(json.loads(Path(arquivo).read_text(encoding="utf-8")).get("gasto_usd", 0))
        except (OSError, ValueError, AttributeError):
            anterior = 0.0
        o = _Orcamento(max(0.0, teto - anterior))
        o.anterior = anterior
        return o


def fabricar_peca(pedido, pasta, *, config=None, aviso=None, continuar=None):
    """Produz o entregável do pedido e devolve o resultado no formato da spec 08 (sem job_id/status).

    `continuar()` (opcional) é consultada a cada aviso de etapa; se devolver False, a produção para com
    PedidoCancelado (antes de chamar o próximo provedor, sem gastar mais).
    """
    from .config import carregar_biblioteca, carregar_config, carregar_loop, carregar_perfis, carregar_roteador

    avisar = _aviso_que_cancela(aviso, continuar)
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    roteador = carregar_roteador(config)
    perfil = carregar_perfis(config).obter(pedido["perfil"]) if pedido.get("perfil") else None
    if perfil:
        roteador = perfil.roteador(roteador)
    roteador.orcamento = OrcamentoDoPedido(pedido["orcamento"]["custo_maximo_usd"], pasta / "gasto.json")
    roteador.aviso = avisar
    biblioteca = carregar_biblioteca(config)
    tema = tema_do_pedido(pedido)

    if pedido["entregavel"] in ("video_curto", "story"):
        from .producao import produzir_video

        rel = produzir_video(roteador, carregar_loop(roteador, config), tema, pasta, duracao=pedido["duracao_s"],
                             perfil=perfil, biblioteca=biblioteca, capcut=True, fatos=pedido["fatos_travados"],
                             proporcao=pedido["proporcao"], cfg_montagem=carregar_config(config).get("montagem"),
                             aviso=avisar)
        rel["custo_usd"] = round(roteador.orcamento.anterior + roteador.orcamento.gasto_usd, 4)
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
    import json

    from .fatos import checar_fatos
    from .producao import _ler_json, _pronto

    base, foto = pasta / "base.png", _ler_json(pasta / "foto.json")
    if _pronto(base):  # retomada: a imagem já foi gerada (e paga)
        provedor = f"foto gratuita ({foto['fonte']})" if foto else "reaproveitada"
    else:
        try:
            r = _gerar(base, lambda saida: funcoes.gerar_imagem(roteador, prompt_da_imagem(cena, pedido["proporcao"]),
                                                                saida, perfil=perfil, proporcao=pedido["proporcao"]))
            provedor, foto = r.provedor, None
        except (TodosFalharam, ErroProducao):
            foto = _foto_gratuita(roteador, biblioteca, cena, base, pedido["proporcao"], perfil, avisar)
            (pasta / "foto.json").write_text(json.dumps(foto, ensure_ascii=False), encoding="utf-8")
            provedor = f"foto gratuita ({foto['fonte']})"
    avisar("== texto por cima da imagem")  # ponto de parada se o pedido foi cancelado
    erros_fatos = checar_fatos(pedido["briefing"]["texto_overlay"], pedido["fatos_travados"]) \
        if pedido["fatos_travados"] else []
    final = compor_imagem(base, pedido["briefing"]["texto_overlay"], pedido["proporcao"], pasta / "peca.png")
    creditos = biblioteca.creditos([foto]) if foto else None
    return {
        "arquivos": [{"tipo": "imagem", "caminho": str(final), "sha256": _sha256(final),
                      "licenca": foto["licenca"] if foto else "comercial_ok", "provedor": provedor}],
        "exportacao_capcut": None,
        "qualidade": {"nota_estrutural": 100, "nota_criativa": None, "aprovado": not erros_fatos,
                      "fatos_travados_ok": not erros_fatos,
                      "problemas": erros_fatos + ["sem juiz de imagem ainda: confira antes de publicar"]},
        "creditos": creditos, "custo_usd": round(roteador.orcamento.anterior + roteador.orcamento.gasto_usd, 4),
        "tentativas": 1,
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
        self.dono = f"{os.getpid()}-{secrets.token_hex(4)}"  # este processo (outros podem usar a mesma fila)
        with self._banco() as banco:
            banco.retomar_pedidos()  # só pedidos órfãos (sem batimento recente); os de outro processo vivo ficam

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
            # Contar e inserir numa transação só (BEGIN IMMEDIATE reserva a escrita): dois processos (HTTP e MCP)
            # não passam juntos do limite.
            banco.con.execute("BEGIN IMMEDIATE")
            try:
                if banco.pedidos_na_fila() >= LIMITE_FILA:
                    raise FilaCheia(f"já há {LIMITE_FILA} pedidos esperando; tente de novo depois")
                banco.criar_pedido(job_id, pedido)  # o commit sai daqui
            finally:
                if banco.con.in_transaction:
                    banco.con.rollback()
        self._acordar.set()
        return {"job_id": job_id, "status": "na_fila", "estimativa_custo_usd": estimativa_custo(pedido)}

    def consultar(self, job_id):
        with self._banco() as banco:
            p = banco.pedido(str(job_id))
        if not p:
            return None
        return {"job_id": p["id"], "status": p["status"], **(p["resultado"] or {}),
                **({"erro": p["erro"]} if p["erro"] else {})}

    def aprovar(self, job_id):
        """Aprovação humana: 'aguardando_aprovacao' → 'concluido'. None se o pedido não existe."""
        return self._mudar_status(job_id, ("aguardando_aprovacao",), "concluido")

    def cancelar(self, job_id):
        """Cancela: pedido na fila não é produzido; em produção, o trabalhador para na próxima etapa e não grava;
        aguardando aprovação, fica recusado. None se o pedido não existe."""
        return self._mudar_status(job_id, ("na_fila", "produzindo", "avaliando", "aguardando_aprovacao"), "cancelado")

    def _mudar_status(self, job_id, de, para):
        job_id = str(job_id)
        marcas = ", ".join("?" * len(de))
        with self._banco() as banco:
            with banco.con:  # dono = NULL: o trabalhador que produzia perde o pedido (batimento falha, não grava)
                mudou = banco.con.execute(
                    f"UPDATE pedidos SET status = ?, dono = NULL, atualizado_em = ? WHERE id = ? AND status IN ({marcas})",
                    (para, datetime.now(timezone.utc).isoformat(timespec="seconds"), job_id, *de)).rowcount
            if not mudou:
                p = banco.pedido(job_id)
                if not p:
                    return None
                if p["status"] != para:  # repetir a mesma ação não é erro
                    raise TransicaoInvalida(f"o pedido está '{p['status']}' e não pode passar para '{para}'")
        return self.consultar(job_id)

    # -- trabalhador -----------------------------------------------------------
    INTERVALO_BATIMENTO = 30  # s; o pedido vira órfão depois de 180 s sem batimento (banco.retomar_pedidos)
    ESPERA_TRAVA = 600  # s esperando outro processo largar a pasta do pedido antes de devolvê-lo à fila

    def _aceita(self, nome):
        try:
            parametros = inspect.signature(self.fabricar).parameters.values()
        except (TypeError, ValueError):
            return False
        return any(x.name == nome or x.kind is inspect.Parameter.VAR_KEYWORD for x in parametros)

    def processar_proximo(self):
        """Produz o pedido mais antigo da fila. Devolve o job_id processado ou None se a fila estava vazia."""
        with self._banco() as banco:
            p = banco.proximo_pedido(self.dono)
        if not p:
            return None
        pasta = self.pasta_base / p["id"]
        vivo, perdido = threading.Event(), threading.Event()
        trava = None

        def bater():  # batimento: outros processos sabem que este pedido não está órfão
            while not vivo.wait(self.INTERVALO_BATIMENTO):
                if trava is not None:
                    try:
                        os.utime(trava)  # a trava da pasta segue "fresca" enquanto este processo trabalha nela
                    except OSError:
                        pass
                if perdido.is_set():
                    continue
                try:
                    with self._banco() as banco:
                        if not banco.batimento(p["id"], self.dono):
                            perdido.set()  # cancelado ou retomado por outro processo: a produção para
                            print(f"⚠ o pedido {p['id']} foi cancelado ou passou para outro processo; "
                                  "a produção aqui para na próxima etapa", file=sys.stderr)
                except Exception as e:  # banco ocupado etc.: tenta de novo na próxima batida
                    print(mascarar(f"⚠ batimento falhou: {e}"), file=sys.stderr)

        def continuar():
            return not perdido.is_set()

        threading.Thread(target=bater, daemon=True).start()
        try:
            limite = time.monotonic() + self.ESPERA_TRAVA
            while (trava := travar_pasta(pasta, self.dono)) is None:
                if perdido.is_set() or self._parar.is_set() or time.monotonic() > limite:
                    break
                time.sleep(min(2.0, self.INTERVALO_BATIMENTO))
            if trava is None:
                if not perdido.is_set():  # outro processo ainda usa a pasta: o pedido volta para a fila
                    with self._banco() as banco:
                        banco.atualizar_pedido(p["id"], "na_fila", dono=self.dono)
                    print(f"⚠ a pasta do pedido {p['id']} está em uso por outro processo; o pedido voltou para a "
                          "fila", file=sys.stderr)
                return p["id"]
            with self._banco() as banco:  # cancelado enquanto esperava a pasta? então nem começa
                if not banco.batimento(p["id"], self.dono):
                    raise PedidoCancelado("o pedido foi cancelado ou passou para outro processo")
            extras = {"continuar": continuar} if self._aceita("continuar") else {}
            resultado = self.fabricar(p["pedido"], pasta, config=self.config, **extras)
            if perdido.is_set():
                raise PedidoCancelado("o pedido foi cancelado ou passou para outro processo")
            status = "aguardando_aprovacao" if p["pedido"].get("aprovacao_humana") else "concluido"
            with self._banco() as banco:
                banco.atualizar_pedido(p["id"], status, resultado, dono=self.dono)
        except PedidoCancelado:
            print(f"⚠ produção do pedido {p['id']} interrompida aqui; nada foi gravado por este processo",
                  file=sys.stderr)
        except Exception as e:  # o pedido falha sozinho; a fila continua
            detalhe = mascarar(f"{type(e).__name__}: {e}")
            with self._banco() as banco:
                banco.atualizar_pedido(p["id"], "falhou", erro=detalhe[:500], dono=self.dono)
            print(mascarar(traceback.format_exc()), file=sys.stderr)  # detalhe para quem cuida, sem chaves
        finally:
            vivo.set()
            if trava is not None:
                soltar_pasta(trava, self.dono)
        return p["id"]

    def _laco(self):
        while not self._parar.is_set():
            if self.processar_proximo() is None:
                with self._banco() as banco:
                    banco.retomar_pedidos()  # pedido de um processo que morreu volta para a fila
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

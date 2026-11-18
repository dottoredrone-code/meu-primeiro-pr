"""Portas do Studio para outros sistemas (K28, spec 08, D13): HTTP local e MCP, as duas sobre a mesma fila.

- HTTP (Torralles Ops): POST /v1/pecas → {"job_id", "status", "estimativa_custo_usd"} (202);
  GET /v1/pecas/{job_id} → status e resultado; GET /v1/saude;
  POST /v1/pecas/{job_id}/aprovar e /cancelar (aprovação humana e cancelamento).
  Painel no navegador (K43, spec 15): GET / abre /painel/; a API do painel fica em /painel/api/.
  Escuta só em 127.0.0.1 por padrão. Com a variável TORRALLES_STUDIO_TOKEN definida, todo pedido precisa do
  cabeçalho "Authorization: Bearer <token>" (obrigatório se escutar fora do próprio PC).
- MCP por stdio (Hermes e agentes): ferramentas produzir_peca, consultar_peca, aprovar_peca e cancelar_peca
  (JSON-RPC 2.0, uma mensagem por linha).
"""

import hmac
import json
import os
import re
import secrets
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .seguranca import mascarar
from .servico import FilaCheia, PedidoInvalido, TransicaoInvalida

LIMITE_CORPO = 1_000_000  # 1 MB: um pedido é texto; nada de upload por aqui
_LOCAL = ("127.0.0.1", "localhost", "[::1]")
# Origem de navegador aceita: só páginas deste PC (o painel do Ops em localhost). Site de fora → 403 (CSRF).
_ORIGEM_LOCAL = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$")
VERSOES_MCP = ("2025-06-18", "2025-03-26", "2024-11-05")
_ROTA_PECA = re.compile(r"^/v1/pecas/([A-Za-z0-9_-]{1,64})$")
_ROTA_ACAO = re.compile(r"^/v1/pecas/([A-Za-z0-9_-]{1,64})/(aprovar|cancelar)$")
MAX_CONEXOES = 8  # conexões atendidas ao mesmo tempo; acima disso responde 503 (cada uma é uma thread)
# Painel (K43, spec 15): página sem dados + API JSON + arquivos por nome de lista fechada.
PASTA_WEB = Path(__file__).resolve().parent / "painel_web"
ESTATICOS = {"/painel/": ("index.html", "text/html; charset=utf-8"),
             "/painel/app.js": ("app.js", "text/javascript; charset=utf-8"),
             "/painel/estilo.css": ("estilo.css", "text/css; charset=utf-8")}
SEGURANCA_PAINEL = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self'; "
                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                               "form-action 'self'",
    "X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
COOKIE = "torralles_token"
_ROTA_PROJETO = re.compile(r"^/painel/api/projetos/([a-z0-9][a-z0-9_-]{0,79})$")
_ROTA_REVISAO = re.compile(r"^/painel/api/projetos/([a-z0-9][a-z0-9_-]{0,79})/revisao$")
_ROTA_ARQUIVO = re.compile(r"^/painel/arquivo/([a-z0-9][a-z0-9_-]{0,79})/([A-Za-z0-9_.-]{1,40})$")
_ROTA_MIDIA = re.compile(r"^/painel/midia/([0-9a-f]{64})$")
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
ERROS_DE_JSON = (UnicodeDecodeError, json.JSONDecodeError, RecursionError)  # JSON muito aninhado estoura a pilha


def _acao(servico, job_id, acao):
    """(código, corpo) de aprovar/cancelar um pedido."""
    try:
        r = servico.aprovar(job_id) if acao == "aprovar" else servico.cancelar(job_id)
    except TransicaoInvalida as e:
        return 409, {"erro": str(e)}
    return (200, r) if r else (404, {"erro": "pedido não encontrado"})


def _manipulador(servico, token, so_local, painel=None):
    vagas = threading.BoundedSemaphore(MAX_CONEXOES)
    sessoes, trava_sessoes = set(), threading.Lock()  # sessões do painel (só na memória; reiniciar pede o token)

    class Manipulador(BaseHTTPRequestHandler):
        server_version = "TorrallesStudio/1"
        timeout = 30  # conexão parada não prende o servidor

        def log_message(self, *args):  # silencioso: o terminal mostra só o andamento da produção
            pass

        def handle_one_request(self):
            if not vagas.acquire(blocking=False):  # muitas conexões ao mesmo tempo: recusa sem criar fila
                self.raw_requestline = self.rfile.readline(65537)
                if self.raw_requestline and self.parse_request():
                    self._responder(503, {"erro": "servidor ocupado; tente de novo em instantes"})
                self.close_connection = True
                return
            try:
                return super().handle_one_request()
            finally:
                vagas.release()

        def _responder(self, codigo, corpo, extras=None):
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            for nome, valor in (extras or {}).items():
                self.send_header(nome, valor)
            self.end_headers()
            self.wfile.write(dados)

        def _cookie_sessao(self):
            """Valor do cookie do painel. Lido à mão: o navegador manda junto os cookies de outros apps deste PC
            (cookie não separa por porta) e um valor fora do padrão faria o leitor da biblioteca desistir."""
            for parte in (self.headers.get("Cookie") or "").split(";"):
                nome, _, valor = parte.strip().partition("=")
                if nome == COOKIE:
                    return valor.strip()
            return ""

        def _autorizado(self):
            self._via_cookie = False
            if not token:
                return True
            recebido = self.headers.get("Authorization", "")
            if hmac.compare_digest(recebido.encode("utf-8", "replace"), f"Bearer {token}".encode("utf-8", "replace")):
                return True
            # painel no navegador: o token entra uma vez e vira uma sessão aleatória num cookie HttpOnly
            # (o token de verdade nunca vai para o cookie, que outros servidores deste PC também recebem)
            valor = self._cookie_sessao()
            with trava_sessoes:
                ok = bool(valor) and any(hmac.compare_digest(valor.encode("utf-8", "replace"), s.encode())
                                         for s in sessoes)
            self._via_cookie = ok
            return ok

        def _origem_propria(self):
            """Pedido com cookie que muda algo precisa vir desta mesma página (mesmo host e porta): o cookie
            SameSite também vai para páginas de outras portas deste PC."""
            origem = self.headers.get("Origin") or ""
            host = self.headers.get("Host") or ""
            return bool(host) and origem.lower() == f"http://{host}".lower()

        def _ler_corpo(self):
            """(dados, None) ou (None, (código, corpo do erro)). Exige JSON de verdade."""
            tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if tipo != "application/json":  # formulário de site (text/plain) não passa: exige JSON de verdade
                return None, (415, {"erro": "envie o pedido com Content-Type: application/json"})
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                tamanho = -1
            if not 0 < tamanho <= LIMITE_CORPO:
                return None, (413 if tamanho > LIMITE_CORPO else 400, {"erro": "corpo vazio ou grande demais"})
            try:
                return json.loads(self.rfile.read(tamanho).decode("utf-8")), None
            except ERROS_DE_JSON:
                return None, (400, {"erro": "JSON inválido"})

        # -- painel (K43) -----------------------------------------------------
        def _estatico(self, rota):
            nome, tipo = ESTATICOS[rota]
            try:
                dados = (PASTA_WEB / nome).read_bytes()
            except OSError:
                return self._responder(404, {"erro": "página do painel não encontrada"})
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(dados)))
            for nome_cab, valor in SEGURANCA_PAINEL.items():
                self.send_header(nome_cab, valor)
            self.end_headers()
            self.wfile.write(dados)

        def _arquivo(self, caminho):
            """Envia um arquivo do projeto ou da biblioteca, com Range (o player avança e volta no vídeo)."""
            from .painel import TIPOS_ARQUIVO

            tamanho = caminho.stat().st_size
            inicio, fim, codigo = 0, tamanho - 1, 200
            pedido_range = (self.headers.get("Range") or "").strip()
            if pedido_range and tamanho:
                m = _RANGE.fullmatch(pedido_range)
                if not m or (not m.group(1) and not m.group(2)):
                    return self._range_invalido(tamanho)
                if m.group(1):
                    inicio = int(m.group(1))
                    fim = min(int(m.group(2)), tamanho - 1) if m.group(2) else tamanho - 1
                else:  # últimos N bytes
                    inicio = max(0, tamanho - int(m.group(2)))
                if inicio > fim or inicio >= tamanho:
                    return self._range_invalido(tamanho)
                codigo = 206
            self.send_response(codigo)
            self.send_header("Content-Type", TIPOS_ARQUIVO.get(caminho.suffix.lower(), "application/octet-stream"))
            self.send_header("Content-Length", str(fim - inicio + 1 if tamanho else 0))
            self.send_header("Accept-Ranges", "bytes")
            if codigo == 206:
                self.send_header("Content-Range", f"bytes {inicio}-{fim}/{tamanho}")
            for nome_cab, valor in SEGURANCA_PAINEL.items():
                self.send_header(nome_cab, valor)
            self.end_headers()
            if not tamanho:
                return None
            with open(caminho, "rb") as f:
                f.seek(inicio)
                falta = fim - inicio + 1
                while falta > 0:
                    bloco = f.read(min(1 << 16, falta))
                    if not bloco:
                        break
                    try:
                        self.wfile.write(bloco)
                    except OSError:  # o player fechou a conexão (pulou para outro trecho) ou passou do prazo
                        self.close_connection = True
                        break
                    falta -= len(bloco)
            return None

        def _range_invalido(self, tamanho):
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{tamanho}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _painel_get(self, rota, consulta):
            """True se a rota é do painel (já respondida)."""
            from .painel import ErroPainel

            if rota == "/" or rota == "/painel":
                self.send_response(302)
                self.send_header("Location", "/painel/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return True
            if rota in ESTATICOS:
                self._estatico(rota)
                return True
            if not rota.startswith("/painel/"):
                return False
            if not self._autorizado():
                self._responder(401, {"erro": "token ausente ou errado", "precisa_token": True})
                return True
            try:
                if rota == "/painel/api/resumo":
                    self._responder(200, painel.resumo())
                elif rota == "/painel/api/perfis":
                    self._responder(200, {"perfis": painel.perfis()[0]})
                elif rota == "/painel/api/projetos":
                    self._responder(200, {"projetos": painel.projetos()})
                elif rota == "/painel/api/biblioteca":
                    q = parse_qs(consulta)
                    self._responder(200, {"ativos": painel.biblioteca((q.get("busca") or [""])[0],
                                                                       (q.get("tipo") or [""])[0])})
                elif m := _ROTA_PROJETO.fullmatch(rota):
                    self._responder(200, painel.projeto(m.group(1)))
                elif m := _ROTA_ARQUIVO.fullmatch(rota):
                    self._arquivo(painel.arquivo(m.group(1), m.group(2)))
                elif m := _ROTA_MIDIA.fullmatch(rota):
                    self._arquivo(painel.midia(m.group(1)))
                else:
                    self._responder(404, {"erro": "rota não encontrada"})
            except ErroPainel as e:
                self._responder(e.codigo, {"erro": str(e)})
            except Exception as e:  # nunca derruba a conexão sem resposta
                self._responder(500, {"erro": mascarar(f"{type(e).__name__}: {e}")[:300]})
            return True

        def _painel_post(self, rota):
            from .painel import ErroPainel

            if rota == "/painel/entrar":
                dados, erro = self._ler_corpo()
                if erro:
                    return self._responder(*erro)
                recebido = str((dados or {}).get("token") or "") if isinstance(dados, dict) else ""
                if not token:
                    return self._responder(200, {"ok": True})
                if not hmac.compare_digest(recebido.encode("utf-8", "replace"), token.encode("utf-8", "replace")):
                    return self._responder(401, {"erro": "token errado"})
                sessao = secrets.token_urlsafe(32)
                with trava_sessoes:
                    if len(sessoes) >= 100:  # nunca cresce sem limite: entrar de novo derruba as mais antigas
                        sessoes.clear()
                    sessoes.add(sessao)
                biscoito = f"{COOKIE}={sessao}; HttpOnly; SameSite=Strict; Path=/"
                return self._responder(200, {"ok": True}, {"Set-Cookie": biscoito})
            if not self._autorizado():
                return self._responder(401, {"erro": "token ausente ou errado", "precisa_token": True})
            if self._via_cookie and not self._origem_propria():
                return self._responder(403, {"erro": "origem não permitida"})
            dados, erro = self._ler_corpo()
            if erro:
                return self._responder(*erro)
            try:
                if rota == "/painel/api/novo":
                    return self._responder(202, painel.novo(dados))
                m = _ROTA_REVISAO.fullmatch(rota)
                if m:
                    return self._responder(200, painel.revisar(m.group(1), dados))
                return self._responder(404, {"erro": "rota não encontrada"})
            except ErroPainel as e:
                return self._responder(e.codigo, {"erro": str(e)})
            except Exception as e:
                return self._responder(500, {"erro": mascarar(f"{type(e).__name__}: {e}")[:300]})

        def _barrar(self, exigir_token=True):
            """Resposta de recusa (ou None se pode seguir): host, origem de navegador e token."""
            cabecalho = (self.headers.get("Host") or "").lower()
            host = cabecalho.split("]")[0] + "]" if cabecalho.startswith("[") else cabecalho.rsplit(":", 1)[0]
            if so_local and host not in _LOCAL:  # contra "DNS rebinding": nome de outro site apontando para cá
                return 403, {"erro": "host não permitido"}
            origem = self.headers.get("Origin")
            if origem is not None and not _ORIGEM_LOCAL.fullmatch(origem):
                return 403, {"erro": "origem não permitida"}
            if exigir_token and not self._autorizado():
                return 401, {"erro": "token ausente ou errado"}
            return None

        def do_GET(self):
            partes = urlsplit(self.path)
            if painel is not None and (partes.path in ("/", "/painel") or partes.path.startswith("/painel/")):
                barrado = self._barrar(exigir_token=False)  # o painel confere o token por rota (a página abre sem)
                if barrado:
                    return self._responder(*barrado)
                if self._painel_get(partes.path, partes.query):
                    return None
            barrado = self._barrar()
            if barrado:
                return self._responder(*barrado)
            if self.path == "/v1/saude":
                return self._responder(200, {"ok": True})
            m = _ROTA_PECA.fullmatch(self.path)
            if not m:
                return self._responder(404, {"erro": "rota não encontrada"})
            r = servico.consultar(m.group(1))
            return self._responder(200, r) if r else self._responder(404, {"erro": "pedido não encontrado"})

        def do_POST(self):
            if painel is not None and self.path.startswith("/painel/"):
                barrado = self._barrar(exigir_token=False)
                if barrado:
                    return self._responder(*barrado)
                return self._painel_post(urlsplit(self.path).path)
            barrado = self._barrar()
            if barrado:
                return self._responder(*barrado)
            if getattr(self, "_via_cookie", False) and not self._origem_propria():
                return self._responder(403, {"erro": "origem não permitida"})  # cookie só da própria página
            acao = _ROTA_ACAO.fullmatch(self.path)
            if acao:
                return self._responder(*_acao(servico, acao.group(1), acao.group(2)))
            if self.path != "/v1/pecas":
                return self._responder(404, {"erro": "rota não encontrada"})
            dados, erro = self._ler_corpo()
            if erro:
                return self._responder(*erro)
            try:
                return self._responder(202, servico.enviar(dados))
            except PedidoInvalido as e:
                return self._responder(422, {"erro": "pedido inválido", "problemas": e.problemas})
            except FilaCheia as e:
                return self._responder(429, {"erro": str(e)})
            except Exception as e:  # nunca derruba a conexão sem resposta
                return self._responder(500, {"erro": mascarar(f"{type(e).__name__}: {e}")[:300]})

    return Manipulador


def criar_servidor_http(servico, host="127.0.0.1", porta=8765, token=None, painel=None):
    token = token if token is not None else os.environ.get("TORRALLES_STUDIO_TOKEN") or None
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise ValueError("para escutar fora deste PC, defina TORRALLES_STUDIO_TOKEN (proteção do servidor)")
    classe = ThreadingHTTPServer
    if ":" in host:  # IPv6 (ex.: ::1)
        classe = type("ServidorIPv6", (ThreadingHTTPServer,), {"address_family": socket.AF_INET6})
    return classe((host, porta), _manipulador(servico, token, so_local=host in ("127.0.0.1", "localhost", "::1"),
                                              painel=painel))


# ---------------------------------------------------------------- MCP (stdio)

FERRAMENTAS = [
    {"name": "produzir_peca",
     "description": "Pede uma peça ao Torralles Studio (contrato da spec 08: briefing, contexto, fatos travados, "
                    "orçamento). Devolve o job_id na hora; a produção roda em segundo plano.",
     "inputSchema": {"type": "object", "properties": {"pedido": {"type": "object",
                                                                  "description": "pedido no contrato 1.0"}},
                     "required": ["pedido"]}},
    {"name": "consultar_peca",
     "description": "Consulta o status e o resultado (arquivos, nota, custo) de um pedido pelo job_id.",
     "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
    {"name": "aprovar_peca",
     "description": "Aprovação humana de uma peça em 'aguardando_aprovacao' (passa a 'concluido').",
     "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
    {"name": "cancelar_peca",
     "description": "Cancela um pedido na fila, em produção ou aguardando aprovação (não é produzido nem gravado).",
     "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
]


def responder_mcp(servico, mensagem):
    """Uma mensagem JSON-RPC → resposta (dict) ou None para notificações."""
    metodo, ident = mensagem.get("method"), mensagem.get("id")
    if ident is None:  # notificação (ex.: notifications/initialized): sem resposta
        return None

    def ok(resultado):
        return {"jsonrpc": "2.0", "id": ident, "result": resultado}

    params = mensagem.get("params")
    if params is not None and not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": "params precisa ser um objeto"}}
    if metodo == "initialize":
        pedida = (params or {}).get("protocolVersion")
        versao = pedida if pedida in VERSOES_MCP else VERSOES_MCP[0]
        return ok({"protocolVersion": versao, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "torralles-studio", "version": "1.0"}})
    if metodo == "ping":
        return ok({})
    if metodo == "tools/list":
        return ok({"tools": FERRAMENTAS})
    if metodo == "tools/call":
        nome, args = (params or {}).get("name"), (params or {}).get("arguments") or {}
        if not isinstance(args, dict):
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": "arguments precisa ser um objeto"}}
        try:
            if nome == "produzir_peca":
                corpo, erro = servico.enviar(args.get("pedido")), False
            elif nome == "consultar_peca":
                corpo = servico.consultar(str(args.get("job_id", "")))
                corpo, erro = (corpo, False) if corpo else ({"erro": "pedido não encontrado"}, True)
            elif nome in ("aprovar_peca", "cancelar_peca"):
                codigo, corpo = _acao(servico, str(args.get("job_id", "")), nome.split("_")[0])
                erro = codigo != 200
            else:
                return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": f"ferramenta {nome!r}"}}
        except PedidoInvalido as e:
            corpo, erro = {"erro": "pedido inválido", "problemas": e.problemas}, True
        except FilaCheia as e:
            corpo, erro = {"erro": str(e)}, True
        return ok({"content": [{"type": "text", "text": json.dumps(corpo, ensure_ascii=False)}], "isError": erro})
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"método desconhecido: {metodo}"}}


def isolar_stdin():
    """Entrega o canal JSON-RPC (stdin original) e põe 'nada' no lugar do stdin do processo.

    Assim nenhum programa filho (FFmpeg) lê bytes das mensagens do Hermes.
    """
    canal = os.dup(0)
    nulo = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nulo, 0)
    os.close(nulo)
    return os.fdopen(canal, "r", encoding="utf-8", errors="replace")  # byte inválido não derruba o servidor


def saida_utf8(fluxo=None):
    """stdout para o JSON-RPC sempre em UTF-8 e com fim de linha LF (no Windows, com pipe, saía em cp1252:
    "é" chegava corrompido ao Hermes e "✓" derrubava o servidor)."""
    fluxo = fluxo or sys.stdout
    try:
        fluxo.reconfigure(encoding="utf-8", errors="strict", newline="\n", write_through=True)
    except (AttributeError, ValueError):
        pass  # fluxo trocado (testes)
    return fluxo


def servir_mcp(servico, entrada=None, saida=None):
    """Lê mensagens JSON-RPC (uma por linha) da entrada e escreve as respostas na saída."""
    entrada, saida = entrada or sys.stdin, saida or sys.stdout
    for linha in entrada:
        linha = linha.strip()
        if not linha:
            continue
        mensagem = None
        try:
            mensagem = json.loads(linha)
            resposta = responder_mcp(servico, mensagem) if isinstance(mensagem, dict) else {
                "jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "mensagem inválida"}}
        except (json.JSONDecodeError, RecursionError):
            resposta = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON inválido"}}
        except Exception as e:  # o processo MCP nunca morre por causa de uma mensagem
            ident = mensagem.get("id") if isinstance(mensagem, dict) else None
            resposta = {"jsonrpc": "2.0", "id": ident,
                        "error": {"code": -32603, "message": mascarar(f"{type(e).__name__}: {e}")[:300]}}
        if resposta is not None:
            # Só ASCII: caractere inválido ecoado do pedido (ex.: "\ud800" solto) nunca derruba o servidor.
            saida.write(json.dumps(resposta) + "\n")
            saida.flush()

"""Portas do Studio para outros sistemas (K28, spec 08, D13): HTTP local e MCP, as duas sobre a mesma fila.

- HTTP (Torralles Ops): POST /v1/pecas → {"job_id", "status", "estimativa_custo_usd"} (202);
  GET /v1/pecas/{job_id} → status e resultado; GET /v1/saude.
  Escuta só em 127.0.0.1 por padrão. Com a variável TORRALLES_STUDIO_TOKEN definida, todo pedido precisa do
  cabeçalho "Authorization: Bearer <token>" (obrigatório se escutar fora do próprio PC).
- MCP por stdio (Hermes e agentes): ferramentas produzir_peca e consultar_peca (JSON-RPC 2.0, uma mensagem por linha).
"""

import hmac
import json
import os
import re
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .seguranca import mascarar
from .servico import FilaCheia, PedidoInvalido

LIMITE_CORPO = 1_000_000  # 1 MB: um pedido é texto; nada de upload por aqui
_LOCAL = ("127.0.0.1", "localhost", "[::1]")
# Origem de navegador aceita: só páginas deste PC (o painel do Ops em localhost). Site de fora → 403 (CSRF).
_ORIGEM_LOCAL = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$")
VERSOES_MCP = ("2025-06-18", "2025-03-26", "2024-11-05")
_ROTA_PECA = re.compile(r"^/v1/pecas/([A-Za-z0-9_-]{1,64})$")


def _manipulador(servico, token, so_local):
    class Manipulador(BaseHTTPRequestHandler):
        server_version = "TorrallesStudio/1"
        timeout = 30  # conexão parada não prende o servidor

        def log_message(self, *args):  # silencioso: o terminal mostra só o andamento da produção
            pass

        def _responder(self, codigo, corpo):
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _autorizado(self):
            if not token:
                return True
            recebido = self.headers.get("Authorization", "")
            return hmac.compare_digest(recebido.encode(), f"Bearer {token}".encode())

        def _barrar(self):
            """Resposta de recusa (ou None se pode seguir): host, origem de navegador e token."""
            cabecalho = (self.headers.get("Host") or "").lower()
            host = cabecalho.split("]")[0] + "]" if cabecalho.startswith("[") else cabecalho.rsplit(":", 1)[0]
            if so_local and host not in _LOCAL:  # contra "DNS rebinding": nome de outro site apontando para cá
                return 403, {"erro": "host não permitido"}
            origem = self.headers.get("Origin")
            if origem is not None and not _ORIGEM_LOCAL.match(origem):
                return 403, {"erro": "origem não permitida"}
            if not self._autorizado():
                return 401, {"erro": "token ausente ou errado"}
            return None

        def do_GET(self):
            barrado = self._barrar()
            if barrado:
                return self._responder(*barrado)
            if self.path == "/v1/saude":
                return self._responder(200, {"ok": True})
            m = _ROTA_PECA.match(self.path)
            if not m:
                return self._responder(404, {"erro": "rota não encontrada"})
            r = servico.consultar(m.group(1))
            return self._responder(200, r) if r else self._responder(404, {"erro": "pedido não encontrado"})

        def do_POST(self):
            barrado = self._barrar()
            if barrado:
                return self._responder(*barrado)
            if self.path != "/v1/pecas":
                return self._responder(404, {"erro": "rota não encontrada"})
            tipo = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if tipo != "application/json":  # formulário de site (text/plain) não passa: exige JSON de verdade
                return self._responder(415, {"erro": "envie o pedido com Content-Type: application/json"})
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                tamanho = -1
            if not 0 < tamanho <= LIMITE_CORPO:
                return self._responder(413 if tamanho > LIMITE_CORPO else 400, {"erro": "corpo vazio ou grande demais"})
            try:
                dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._responder(400, {"erro": "JSON inválido"})
            try:
                return self._responder(202, servico.enviar(dados))
            except PedidoInvalido as e:
                return self._responder(422, {"erro": "pedido inválido", "problemas": e.problemas})
            except FilaCheia as e:
                return self._responder(429, {"erro": str(e)})
            except Exception as e:  # nunca derruba a conexão sem resposta
                return self._responder(500, {"erro": mascarar(f"{type(e).__name__}: {e}")[:300]})

    return Manipulador


def criar_servidor_http(servico, host="127.0.0.1", porta=8765, token=None):
    token = token if token is not None else os.environ.get("TORRALLES_STUDIO_TOKEN") or None
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise ValueError("para escutar fora deste PC, defina TORRALLES_STUDIO_TOKEN (proteção do servidor)")
    classe = ThreadingHTTPServer
    if ":" in host:  # IPv6 (ex.: ::1)
        classe = type("ServidorIPv6", (ThreadingHTTPServer,), {"address_family": socket.AF_INET6})
    return classe((host, porta), _manipulador(servico, token, so_local=host in ("127.0.0.1", "localhost", "::1")))


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
        except json.JSONDecodeError:
            resposta = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON inválido"}}
        except Exception as e:  # o processo MCP nunca morre por causa de uma mensagem
            ident = mensagem.get("id") if isinstance(mensagem, dict) else None
            resposta = {"jsonrpc": "2.0", "id": ident,
                        "error": {"code": -32603, "message": mascarar(f"{type(e).__name__}: {e}")[:300]}}
        if resposta is not None:
            # Só ASCII: caractere inválido ecoado do pedido (ex.: "\ud800" solto) nunca derruba o servidor.
            saida.write(json.dumps(resposta) + "\n")
            saida.flush()

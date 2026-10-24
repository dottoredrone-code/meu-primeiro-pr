import io
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from torralles_studio.banco import Banco
from torralles_studio.contrato import entregavel_do_tipo, proporcao_do_formato, validar_pedido
from torralles_studio.servico import PedidoInvalido, ServicoPecas, compor_imagem
from torralles_studio.servidor import criar_servidor_http, responder_mcp, servir_mcp

# Exemplo no formato do Ops (spec 08), com dados genéricos (D9).
PEDIDO = {
    "versao_contrato": "1.0",
    "origem": {"sistema": "torralles-ops", "peca_id": 4, "campanha_id": 6},
    "briefing": {"tipo_peca": "post estático", "conceito_visual": "xícara de chá verde numa mesa clara",
                 "paleta_cores": "verde e branco", "formato_dimensoes": "1080x1080",
                 "texto_overlay": "Chá verde: leve e natural", "ferramenta_sugerida": "Canva"},
    "contexto_campanha": {"canal": "Instagram", "objetivo": "apresentar o produto", "cta": "Peça já"},
    "fatos_travados": {"preco": "R$ 19,90", "nome_produto": "Chá Verde Leve"},
    "orcamento": {"custo_maximo_usd": 5, "modo": "economico"},
}


class TestContrato(unittest.TestCase):
    def test_pedido_do_ops_e_normalizado(self):
        p, problemas = validar_pedido(PEDIDO)
        self.assertEqual(problemas, [])
        self.assertEqual((p["entregavel"], p["proporcao"]), ("imagem", "1:1"))
        self.assertEqual(p["orcamento"]["custo_maximo_usd"], 1.5)  # nunca acima do teto do Studio (D20)
        self.assertEqual(p["fatos_travados"]["preco"], "R$ 19,90")

    def test_campos_vazios_ou_provisorios_recusam(self):
        ruim = json.loads(json.dumps(PEDIDO))
        ruim["briefing"]["paleta_cores"] = "…"
        del ruim["briefing"]["texto_overlay"]
        p, problemas = validar_pedido(ruim)
        self.assertIsNone(p)
        self.assertEqual(len(problemas), 2)

    def test_mapeamentos(self):
        self.assertEqual(entregavel_do_tipo("Reels de lançamento"), "video_curto")
        self.assertEqual(entregavel_do_tipo("stories"), "story")
        self.assertEqual(entregavel_do_tipo("carrossel 5 cards"), "carrossel")
        self.assertEqual(proporcao_do_formato("1920 x 1080", "video_curto"), "16:9")
        self.assertEqual(proporcao_do_formato("4:5", "imagem"), "4:5")
        self.assertEqual(proporcao_do_formato("", "story"), "9:16")
        self.assertIsNone(proporcao_do_formato("1000x300", "imagem"))

    def test_carrossel_ainda_nao_e_produzido(self):
        p = json.loads(json.dumps(PEDIDO))
        p["entregaveis"] = ["carrossel"]
        self.assertIn("ainda não é produzido", " ".join(validar_pedido(p)[1]))


def _pegar(caminho):
    import os
    import time

    with Banco(caminho) as banco:
        time.sleep(0.2)  # todos tentam juntos
        p = banco.proximo_pedido(str(os.getpid()))
    return p["id"] if p else None


class Fabrica:
    def __init__(self, falhar=False):
        self.falhar, self.chamadas = falhar, []

    def __call__(self, pedido, pasta, config=None):
        self.chamadas.append((pedido["entregavel"], Path(pasta).name))
        if self.falhar:
            raise RuntimeError("deu ruim com a chave sk-1234567890abcdefghij")
        return {"arquivos": [{"tipo": "imagem", "caminho": "peca.png"}], "custo_usd": 0.05,
                "qualidade": {"aprovado": True}, "revisar_manual": False}


class TestFila(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)

    def tearDown(self):
        self._d.cleanup()

    def test_pedido_vai_para_a_fila_e_volta_com_resultado(self):
        fabrica = Fabrica()
        s = ServicoPecas(self.d / "b.db", pasta_base=self.d / "pedidos", fabricar=fabrica)
        r = s.enviar(PEDIDO)
        self.assertTrue(r["job_id"].startswith("stu_"))
        self.assertEqual(s.consultar(r["job_id"])["status"], "na_fila")
        self.assertEqual(s.processar_proximo(), r["job_id"])
        c = s.consultar(r["job_id"])
        self.assertEqual(c["status"], "aguardando_aprovacao")  # aprovação humana é o padrão
        self.assertEqual(c["custo_usd"], 0.05)
        self.assertEqual(fabrica.chamadas, [("imagem", r["job_id"])])
        self.assertIsNone(s.processar_proximo())
        self.assertIsNone(s.consultar("stu_nao_existe"))

    def test_falha_marca_o_pedido_sem_vazar_chave_e_a_fila_segue(self):
        from contextlib import redirect_stderr

        s = ServicoPecas(self.d / "b.db", pasta_base=self.d / "pedidos", fabricar=Fabrica(falhar=True))
        a, b = s.enviar(PEDIDO), s.enviar(PEDIDO)
        with redirect_stderr(io.StringIO()) as log:
            s.processar_proximo()
        self.assertNotIn("1234567890abcdefghij", log.getvalue())  # nem no log do terminal
        c = s.consultar(a["job_id"])
        self.assertEqual(c["status"], "falhou")
        self.assertNotIn("1234567890abcdefghij", c["erro"])
        self.assertEqual(s.processar_proximo(), b["job_id"])

    def test_pedido_em_producao_volta_para_a_fila_ao_reiniciar(self):
        s = ServicoPecas(self.d / "b.db", pasta_base=self.d / "pedidos", fabricar=Fabrica())
        r = s.enviar(PEDIDO)
        with Banco(self.d / "b.db") as banco:
            banco.proximo_pedido("outro-processo")
        # outro processo vivo (batimento recente): abrir um segundo servidor NÃO tira o pedido dele
        s2 = ServicoPecas(self.d / "b.db", pasta_base=self.d / "pedidos", fabricar=Fabrica())
        self.assertEqual(s2.consultar(r["job_id"])["status"], "produzindo")
        with Banco(self.d / "b.db") as banco:  # o processo morreu: sem batimento há 10 minutos
            banco.con.execute("UPDATE pedidos SET atualizado_em = '2000-01-01T00:00:00+00:00'")
            banco.con.commit()
        s3 = ServicoPecas(self.d / "b.db", pasta_base=self.d / "pedidos", fabricar=Fabrica())
        self.assertEqual(s3.consultar(r["job_id"])["status"], "na_fila")

    def test_dois_processos_nunca_pegam_o_mesmo_pedido(self):  # verificador K28: pagaria duas vezes
        import multiprocessing as mp

        s = ServicoPecas(self.d / "b.db", fabricar=Fabrica())
        s.enviar(PEDIDO)
        with mp.get_context("spawn").Pool(4) as pool:
            pegos = pool.map(_pegar, [str(self.d / "b.db")] * 4)
        self.assertEqual(sum(1 for p in pegos if p), 1)

    def test_processo_que_perdeu_o_pedido_nao_sobrescreve_o_resultado(self):  # verificador K28
        s = ServicoPecas(self.d / "b.db", fabricar=Fabrica())
        r = s.enviar(PEDIDO)
        with Banco(self.d / "b.db") as banco:
            banco.proximo_pedido("antigo")
            banco.con.execute("UPDATE pedidos SET status = 'na_fila', dono = NULL")  # foi retomado por outro
            banco.con.commit()
            banco.proximo_pedido("novo")
            self.assertFalse(banco.batimento(r["job_id"], "antigo"))
            self.assertFalse(banco.atualizar_pedido(r["job_id"], "concluido", {"x": 1}, dono="antigo"))
            self.assertTrue(banco.atualizar_pedido(r["job_id"], "concluido", {"x": 2}, dono="novo"))
            self.assertEqual(banco.pedido(r["job_id"])["resultado"], {"x": 2})

    def test_fila_tem_limite(self):
        from torralles_studio import servico as mod

        s = ServicoPecas(self.d / "b.db", fabricar=Fabrica())
        for _ in range(mod.LIMITE_FILA):
            s.enviar(PEDIDO)
        with self.assertRaises(mod.FilaCheia):
            s.enviar(PEDIDO)

    def test_pedido_invalido_nao_entra_na_fila(self):
        s = ServicoPecas(self.d / "b.db", fabricar=Fabrica())
        with self.assertRaises(PedidoInvalido):
            s.enviar({"briefing": {}})


class TestHTTP(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.servico = ServicoPecas(Path(self._d.name) / "b.db", fabricar=Fabrica())

    def tearDown(self):
        self._d.cleanup()

    def iniciar(self, token=None):
        http = criar_servidor_http(self.servico, "127.0.0.1", 0, token=token)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        return f"http://127.0.0.1:{http.server_address[1]}"

    def pedir(self, url, corpo=None, token=None, extra=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method="POST" if dados else "GET",
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {token}"} if token else {}),
                                              **(extra or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_post_e_get(self):
        base = self.iniciar()
        codigo, r = self.pedir(f"{base}/v1/pecas", PEDIDO)
        self.assertEqual(codigo, 202)
        codigo, c = self.pedir(f"{base}/v1/pecas/{r['job_id']}")
        self.assertEqual((codigo, c["status"]), (200, "na_fila"))
        self.assertEqual(self.pedir(f"{base}/v1/pecas/stu_x")[0], 404)
        codigo, erro = self.pedir(f"{base}/v1/pecas", {"briefing": {}})
        self.assertEqual(codigo, 422)
        self.assertTrue(erro["problemas"])
        self.assertEqual(self.pedir(f"{base}/v1/saude"), (200, {"ok": True}))

    def test_token(self):
        base = self.iniciar(token="segredo-de-teste")
        self.assertEqual(self.pedir(f"{base}/v1/pecas", PEDIDO)[0], 401)
        self.assertEqual(self.pedir(f"{base}/v1/pecas", PEDIDO, token="segredo-de-teste")[0], 202)

    def test_site_de_fora_nao_poe_pedido_na_fila(self):  # verificador K28: CSRF e DNS rebinding
        base = self.iniciar()
        url = f"{base}/v1/pecas"
        self.assertEqual(self.pedir(url, PEDIDO, extra={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.pedir(url, PEDIDO, extra={"Origin": "https://site-estranho.example"})[0], 403)
        self.assertEqual(self.pedir(url, PEDIDO, extra={"Host": "site-estranho.example"})[0], 403)
        self.assertEqual(self.pedir(url, PEDIDO, extra={"Origin": "http://localhost:3000"})[0], 202)  # painel do Ops
        porta = base.rsplit(":", 1)[1]
        self.assertEqual(self.pedir(url, PEDIDO, extra={"Host": f"LOCALHOST:{porta}"})[0], 202)

    def test_fila_cheia_responde_429(self):
        from torralles_studio import servico as mod

        base = self.iniciar()
        for _ in range(mod.LIMITE_FILA):
            self.servico.enviar(PEDIDO)
        self.assertEqual(self.pedir(f"{base}/v1/pecas", PEDIDO)[0], 429)

    def test_fora_do_pc_exige_token(self):
        with self.assertRaises(ValueError):
            criar_servidor_http(self.servico, "0.0.0.0", 0, token="")


class TestMCP(unittest.TestCase):
    def test_mensagens_estranhas_nao_derrubam(self):  # verificador K28
        with tempfile.TemporaryDirectory() as d:
            servico = ServicoPecas(Path(d) / "b.db", fabricar=Fabrica())
            ruins = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1]},
                     {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": "produzir_peca", "arguments": "texto"}},
                     {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                      "params": {"name": "produzir_peca", "arguments": {"pedido": {**PEDIDO, "duracao_s": "abc"}}}},
                     {"jsonrpc": "2.0", "id": 4, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}]
            saida = io.StringIO()
            servir_mcp(servico, io.StringIO("\n".join(json.dumps(m) for m in ruins) + "\n"), saida)
            r = [json.loads(l) for l in saida.getvalue().splitlines()]
            self.assertEqual([x["id"] for x in r], [1, 2, 3, 4])
            self.assertEqual(r[0]["error"]["code"], -32602)
            self.assertEqual(r[1]["error"]["code"], -32602)
            self.assertTrue(r[2]["result"]["isError"])  # pedido inválido volta explicado
            self.assertEqual(r[3]["result"]["protocolVersion"], "2025-06-18")  # versão que o Studio suporta

    def test_erro_inesperado_vira_resposta_32603(self):
        class Quebrado:
            def enviar(self, dados):
                raise RuntimeError("falha com sk-abcdefghijklmnopqrstu")

        saida = io.StringIO()
        servir_mcp(Quebrado(), io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                                       "params": {"name": "produzir_peca",
                                                                  "arguments": {"pedido": {}}}}) + "\n"), saida)
        r = json.loads(saida.getvalue())
        self.assertEqual(r["error"]["code"], -32603)
        self.assertNotIn("abcdefghijklmnopqrstu", r["error"]["message"])

    def test_ffmpeg_nao_le_as_mensagens_do_hermes(self):  # verificador K28: stdin isolado
        import sys

        roteiro = (
            "import subprocess, sys\n"
            "from torralles_studio.servidor import isolar_stdin\n"
            "canal = isolar_stdin()\n"
            "filho = subprocess.run([sys.executable, '-c', 'import sys; print(len(sys.stdin.read()))'],"
            " capture_output=True, text=True)\n"
            "print(filho.stdout.strip(), canal.read().strip())\n")
        r = subprocess.run([sys.executable, "-c", roteiro], input='{"jsonrpc": "2.0"}\n', capture_output=True,
                           text=True, cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual(r.stdout.split(" ", 1), ["0", '{"jsonrpc": "2.0"}\n'])

    def test_caractere_invalido_nao_derruba(self):  # verificador: "\ud800" ecoado no erro matava o processo
        with tempfile.TemporaryDirectory() as d:
            servico = ServicoPecas(Path(d) / "b.db", fabricar=Fabrica())
            entrada = io.StringIO('{"jsonrpc":"2.0","id":7,"method":"x\\ud800"}\n'
                                  '{"jsonrpc":"2.0","id":8,"method":"ping"}\n')
            bruto = io.BytesIO()
            saida = io.TextIOWrapper(bruto, encoding="utf-8", errors="strict", newline="\n", write_through=True)
            servir_mcp(servico, entrada=entrada, saida=saida)
            linhas = bruto.getvalue().decode("utf-8").splitlines()
            self.assertEqual([json.loads(l)["id"] for l in linhas], [7, 8])

    def test_byte_invalido_na_entrada_nao_derruba(self):  # verificador: UnicodeDecodeError matava o processo
        import sys

        roteiro = ("from torralles_studio.servidor import isolar_stdin\n"
                   "print(len(isolar_stdin().read().splitlines()))\n")
        r = subprocess.run([sys.executable, "-c", roteiro], input=b'{"m":"x\xed\xa0\x80"}\n{"m":"ping"}\n',
                           capture_output=True, cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, b"2"), r.stderr)

    def test_resposta_sai_em_utf8_no_windows(self):  # verificador: cp1252 corrompia "é" e caía no "✓"
        import os
        import sys

        roteiro = ("from torralles_studio.servidor import saida_utf8\n"
                   "saida_utf8().write('m\\u00e9todo \\u2713\\n')\n")
        r = subprocess.run([sys.executable, "-c", roteiro], capture_output=True,
                           cwd=Path(__file__).resolve().parent.parent,
                           env={**os.environ, "PYTHONIOENCODING": "cp1252"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "método ✓\n".encode("utf-8"))

    def test_conversa_completa(self):
        with tempfile.TemporaryDirectory() as d:
            servico = ServicoPecas(Path(d) / "b.db", fabricar=Fabrica())
            entrada = io.StringIO("\n".join(json.dumps(m) for m in [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "produzir_peca", "arguments": {"pedido": PEDIDO}}},
            ]) + "\nnão é json\n")
            saida = io.StringIO()
            servir_mcp(servico, entrada, saida)
            respostas = [json.loads(l) for l in saida.getvalue().splitlines()]
            self.assertEqual([r.get("id") for r in respostas], [1, 2, 3, None])  # notificação não tem resposta
            self.assertEqual(respostas[0]["result"]["protocolVersion"], "2025-06-18")
            self.assertEqual({t["name"] for t in respostas[1]["result"]["tools"]}, {"produzir_peca", "consultar_peca"})
            job = json.loads(respostas[2]["result"]["content"][0]["text"])["job_id"]
            consulta = responder_mcp(servico, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                               "params": {"name": "consultar_peca", "arguments": {"job_id": job}}})
            self.assertFalse(consulta["result"]["isError"])
            self.assertEqual(respostas[3]["error"]["code"], -32700)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestImagemComTexto(unittest.TestCase):
    def test_compoe_no_formato_com_texto(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "base.png"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=800x600",
                            "-frames:v", "1", str(img)], check=True)
            saida = compor_imagem(img, "Chá verde: leve e natural", "1:1", Path(d) / "peca.png")
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                                str(saida)], capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "1080,1080")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestFabricarPost(unittest.TestCase):
    def test_post_estatico_com_ia_de_imagem(self):
        from unittest import mock

        from torralles_studio.biblioteca import Biblioteca
        from torralles_studio.provedores.base import Provedor
        from torralles_studio.roteador import Roteador
        from torralles_studio.servico import fabricar_peca

        class Img(Provedor):
            tipo = "imagem"

            def configurado(self):
                return None

            def executar(self, prompt, saida, proporcao=None):
                self.pedido = (prompt, proporcao)
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=green:s=1024x1024",
                                "-frames:v", "1", str(saida)], check=True)
                return Path(saida)

        img = Img("img", {"custo_usd": 0.06})
        pedido, _ = validar_pedido(PEDIDO)
        with tempfile.TemporaryDirectory() as d, Banco(Path(d) / "b.db") as banco:
            with mock.patch("torralles_studio.config.carregar_roteador",
                            return_value=Roteador({"img": img}, {"imagem": ["img"]})), \
                    mock.patch("torralles_studio.config.carregar_biblioteca",
                               return_value=Biblioteca(Path(d) / "bib", banco)):
                r = fabricar_peca(pedido, Path(d) / "job")
            self.assertTrue(Path(r["arquivos"][0]["caminho"]).is_file())
            self.assertEqual(len(r["arquivos"][0]["sha256"]), 64)
            self.assertEqual(img.pedido[1], "1:1")
            self.assertIn("sem nenhum texto", img.pedido[0])  # o texto entra depois, sem erro de digitação da IA
            self.assertAlmostEqual(r["custo_usd"], 0.06)
            self.assertTrue(r["revisar_manual"])

"""K43 (spec 15): painel do Studio no navegador — dados, arquivos, decisões, pedido novo e proteção HTTP."""

import json
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from torralles_studio.banco import Banco
from torralles_studio.painel import ErroPainel, Painel
from torralles_studio.servico import ServicoPecas
from torralles_studio.servidor import PASTA_WEB, criar_servidor_http

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _projeto(pasta):
    pasta.mkdir(parents=True)
    (pasta / "roteiro.json").write_text(json.dumps({
        "tema": "chá verde", "proporcao": "9:16", "aprovado": True, "nota": 82,
        "roteiro": {"titulo": "Chá verde de verdade", "cta": "Siga para mais",
                    "cenas": [{"narracao": "Primeira fala.", "texto_tela": "Chá", "clima": "calmo", "duracao": 5,
                               "prompt_imagem": "xícara de chá"},
                              {"narracao": "Segunda fala.", "duracao": 5}]}}, ensure_ascii=False), encoding="utf-8")
    (pasta / "relatorio.json").write_text(json.dumps({
        "tema": "chá verde", "titulo": "Chá verde de verdade", "proporcao": "9:16", "duracao_s": 10.2,
        "aprovado": False, "problemas": ["legenda fora da área segura"], "medidas": {"lufs": -14.0},
        "custo_usd": 0.12, "etapas": [{"etapa": "cena 1: imagem", "provedor": "flux", "reaproveitado": False}],
        "creditos": "Foto: Fulano (CC-BY)"}, ensure_ascii=False), encoding="utf-8")
    (pasta / "fotos.json").write_text(json.dumps({"2": {"fonte": "Openverse", "autor": "Fulano", "licenca": "cc-by",
                                                        "link": "https://exemplo.org/f"}}), encoding="utf-8")
    (pasta / "cena_01.png").write_bytes(PNG)
    (pasta / "cena_02.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
    (pasta / "voz_01.mp3").write_bytes(b"ID3" + b"\x00" * 10)
    (pasta / "video_final.mp4").write_bytes(bytes(range(256)) * 4)  # 1024 bytes
    (pasta / "capa.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
    (pasta / "post.txt").write_text("Texto do post\n#chaverde", encoding="utf-8")
    (pasta / "segredo.txt").write_text("não pode sair", encoding="utf-8")


def _fabricar(pedido, pasta, **_):
    return {"arquivos": [], "custo_usd": 0.0}


class BaseePainel(unittest.TestCase):
    def setUp(self):
        # o servidor de teste atende em threads que podem fechar o banco um instante depois do fim do teste
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        raiz = Path(self.tmp.name)
        self.saidas = raiz / "saidas"
        _projeto(self.saidas / "cha-verde")
        (self.saidas / "teste-voz").mkdir()
        (self.saidas / "teste-voz" / "roteiro.json").write_text("{}", encoding="utf-8")
        (self.saidas / "sem-nada").mkdir()
        self.banco = raiz / "t.db"
        self.servico = ServicoPecas(self.banco, pasta_base=self.saidas / "pedidos", fabricar=_fabricar)
        self.painel = Painel(self.saidas, self.banco, servico=self.servico, pasta_biblioteca=raiz / "bib")

    def tearDown(self):
        self.tmp.cleanup()


class TestDados(BaseePainel):
    def test_lista_so_projetos_de_verdade(self):
        ids = [p["id"] for p in self.painel.projetos()]
        self.assertEqual(ids, ["cha-verde"])
        p = self.painel.projetos()[0]
        self.assertEqual((p["titulo"], p["status"], p["nota"], p["capa"]),
                         ("Chá verde de verdade", "pronto_com_avisos", 82, "capa.jpg"))

    def test_detalhe_com_cenas_origem_e_post(self):
        d = self.painel.projeto("cha-verde")
        self.assertEqual(d["video"]["nome"], "video_final.mp4")
        self.assertEqual([c["imagem"]["nome"] for c in d["cenas"]], ["cena_01.png", "cena_02.jpg"])
        self.assertEqual(d["cenas"][0]["voz"]["nome"], "voz_01.mp3")
        self.assertEqual(d["cenas"][0]["origem"]["fonte"], "flux")
        self.assertEqual(d["cenas"][1]["origem"]["licenca"], "cc-by")
        self.assertIn("#chaverde", d["post"])
        self.assertEqual(d["problemas"], ["legenda fora da área segura"])

    def test_arquivo_so_da_lista_fechada(self):
        self.assertTrue(self.painel.arquivo("cha-verde", "video_final.mp4").is_file())
        for nome in ("segredo.txt", "relatorio.json", "../cha-verde/capa.jpg", "cena_1.png", "post.txt"):
            with self.assertRaises(ErroPainel, msg=nome):
                self.painel.arquivo("cha-verde", nome)
        for pid in ("..", "pedidos", "Cha-Verde", "a/b", "", "teste-voz"):
            with self.assertRaises(ErroPainel, msg=pid):
                self.painel.projeto(pid)

    def test_link_simbolico_recusado(self):
        fora = Path(self.tmp.name) / "fora"
        fora.mkdir()
        (fora / "capa.jpg").write_bytes(b"x")
        try:
            (self.saidas / "atalho").symlink_to(fora, target_is_directory=True)
            (self.saidas / "cha-verde" / "cena_09.png").symlink_to(fora / "capa.jpg")
        except OSError:
            self.skipTest("este sistema não cria link simbólico sem permissão")
        with self.assertRaises(ErroPainel):
            self.painel.arquivo("atalho", "capa.jpg")
        with self.assertRaises(ErroPainel):
            self.painel.arquivo("cha-verde", "cena_09.png")
        self.assertNotIn("atalho", [p["id"] for p in self.painel.projetos()])

    def test_revisao_grava_e_a_ultima_vale(self):
        with self.assertRaises(ErroPainel):
            self.painel.revisar("cha-verde", {"item": "cena_01", "decisao": "alterar", "comentario": "  "})
        with self.assertRaises(ErroPainel):
            self.painel.revisar("cha-verde", {"item": "../x", "decisao": "aprovado"})
        with self.assertRaises(ErroPainel):
            self.painel.revisar("cha-verde", {"item": "video", "decisao": "talvez"})
        self.painel.revisar("cha-verde", {"item": "cena_01", "decisao": "alterar", "comentario": "tirar a cerveja"})
        self.painel.revisar("cha-verde", {"item": "video", "decisao": "aprovado"})
        d = self.painel.projeto("cha-verde")
        self.assertEqual(d["cenas"][0]["decisao"]["comentario"], "tirar a cerveja")
        self.assertEqual(d["decisao"], "aprovado")
        self.assertEqual(d["alteracoes_pendentes"], 1)
        self.painel.revisar("cha-verde", {"item": "cena_01", "decisao": "aprovado"})
        self.assertEqual(self.painel.projeto("cha-verde")["alteracoes_pendentes"], 0)
        for ruim in ({"item": "video\n", "decisao": "aprovado"}, {"item": "video", "decisao": "aprovado\n"}):
            with self.assertRaises(ErroPainel, msg=ruim):  # "$" aceitaria a quebra de linha no fim
                self.painel.revisar("cha-verde", ruim)
        with self.assertRaises(ErroPainel):  # pasta sem roteiro nem relatório não é projeto
            self.painel.revisar("sem-nada", {"item": "video", "decisao": "aprovado"})

    def test_link_so_http(self):
        from torralles_studio.painel import link_seguro

        self.assertEqual(link_seguro("https://exemplo.org/f"), "https://exemplo.org/f")
        for ruim in ("javascript:alert(1)", " JavaScript:x", "data:text/html,x", "//exemplo.org", None, "https://a b"):
            self.assertIsNone(link_seguro(ruim), ruim)
        fotos = self.saidas / "cha-verde" / "fotos.json"
        fotos.write_text(json.dumps({"2": {"fonte": "X", "licenca": "cc0", "link": "javascript:alert(1)"}}),
                         encoding="utf-8")
        self.assertIsNone(self.painel.projeto("cha-verde")["cenas"][1]["origem"]["link"])

    def test_novo_vira_pedido_valido_e_aprovar_o_video_aprova_o_pedido(self):
        r = self.painel.novo({"tema": "3 dicas de sono", "tipo": "story", "duracao_s": 15, "teto_usd": 9})
        with Banco(self.banco) as banco:
            p = banco.pedido(r["job_id"])
        self.assertEqual((p["status"], p["pedido"]["entregavel"], p["pedido"]["proporcao"]), ("na_fila", "story", "9:16"))
        self.assertEqual(p["pedido"]["orcamento"]["custo_maximo_usd"], 1.5)  # D20: nunca acima do teto
        self.assertIn(r["job_id"], [x["id"] for x in self.painel.projetos()])
        self.servico.processar_proximo()
        self.assertEqual(self.servico.consultar(r["job_id"])["status"], "aguardando_aprovacao")
        self.painel.revisar(r["job_id"], {"item": "video", "decisao": "aprovado"})
        self.assertEqual(self.servico.consultar(r["job_id"])["status"], "concluido")
        img = self.painel.novo({"tema": "promoção de inverno", "tipo": "imagem"})
        with Banco(self.banco) as banco:
            self.assertEqual(banco.pedido(img["job_id"])["pedido"]["proporcao"], "1:1")
        for ruim in ({"tema": "x"}, {"tema": "tema bom", "tipo": "carrossel"}, {"tema": "tema bom", "proporcao": "3:2"},
                     {"tema": "tema bom", "duracao_s": 500}, {"tema": "tema bom", "perfil": "nao-existe"}):
            with self.assertRaises(ErroPainel, msg=ruim):
                self.painel.novo(ruim)

    def test_biblioteca_e_midia_por_hash(self):
        from torralles_studio.biblioteca import Biblioteca

        origem = Path(self.tmp.name) / "foto.png"
        origem.write_bytes(PNG + b"1")
        with Banco(self.banco) as banco:
            ativo = Biblioteca(Path(self.tmp.name) / "bib", banco).adicionar(
                origem, "cc0", "Openverse", titulo="Xícara", tags=["chá"])
        achados = self.painel.biblioteca("Xíc")
        self.assertEqual([a["hash"] for a in achados], [ativo["hash"]])
        self.assertTrue(self.painel.midia(ativo["hash"]).is_file())
        with self.assertRaises(ErroPainel):
            self.painel.midia("0" * 64)

    def test_resumo(self):
        r = self.painel.resumo()
        self.assertIn("voz", r["provedores"])
        self.assertEqual(r["teto_video_usd"], 1.5)
        self.assertIsInstance(r["cotas"], list)


def _pedir(url, metodo="GET", dados=None, cabecalhos=None):
    corpo = json.dumps(dados).encode() if dados is not None else None
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos or {})
    if corpo is not None and "Content-Type" not in (cabecalhos or {}):
        req.add_header("Content-Type", "application/json")

    class SemRedirecionar(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    try:
        r = urllib.request.build_opener(SemRedirecionar).open(req, timeout=10)
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        with e:
            return e.code, dict(e.headers), e.read()


class TestHTTP(BaseePainel):
    def _subir(self, token=None):
        http = criar_servidor_http(self.servico, porta=0, token=token, painel=self.painel)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        return f"http://127.0.0.1:{http.server_address[1]}"

    def test_pagina_api_e_arquivos(self):
        base = self._subir()
        codigo, cab, _ = _pedir(base + "/")
        self.assertEqual((codigo, cab.get("Location")), (302, "/painel/"))
        codigo, cab, html = _pedir(base + "/painel/")
        self.assertEqual(codigo, 200)
        self.assertIn("script-src 'self'", cab["Content-Security-Policy"])
        self.assertEqual(cab["X-Frame-Options"], "DENY")
        self.assertIn(b"Torralles", html)
        codigo, _, corpo = _pedir(base + "/painel/api/projetos")
        self.assertEqual((codigo, json.loads(corpo)["projetos"][0]["id"]), (200, "cha-verde"))
        codigo, cab, corpo = _pedir(base + "/painel/arquivo/cha-verde/video_final.mp4", cabecalhos={"Range": "bytes=10-19"})
        self.assertEqual((codigo, cab["Content-Range"], corpo), (206, "bytes 10-19/1024", bytes(range(10, 20))))
        codigo, _, corpo = _pedir(base + "/painel/arquivo/cha-verde/video_final.mp4", cabecalhos={"Range": "bytes=-4"})
        self.assertEqual((codigo, corpo), (206, bytes(range(252, 256))))
        codigo, _, _ = _pedir(base + "/painel/arquivo/cha-verde/video_final.mp4", cabecalhos={"Range": "bytes=5000-"})
        self.assertEqual(codigo, 416)
        codigo, cab, corpo = _pedir(base + "/painel/arquivo/cha-verde/video_final.mp4")
        self.assertEqual((codigo, cab["Content-Type"], len(corpo)), (200, "video/mp4", 1024))
        for rota in ("/painel/arquivo/cha-verde/segredo.txt", "/painel/arquivo/cha-verde/..%2Fsegredo.txt",
                     "/painel/arquivo/../cha-verde/capa.jpg", "/painel/api/projetos/nao-existe"):
            self.assertEqual(_pedir(base + rota)[0], 404, rota)

    def test_revisao_por_http_e_protecoes(self):
        base = self._subir()
        url = base + "/painel/api/projetos/cha-verde/revisao"
        codigo, _, corpo = _pedir(url, "POST", {"item": "capa", "decisao": "alterar", "comentario": "título maior"})
        self.assertEqual((codigo, json.loads(corpo)["ok"]), (200, True))
        codigo, _, _ = _pedir(url, "POST", {"item": "capa", "decisao": "alterar"})
        self.assertEqual(codigo, 400)
        codigo, _, _ = _pedir(url, "POST", {"item": "capa", "decisao": "aprovado"}, {"Content-Type": "text/plain"})
        self.assertEqual(codigo, 415)
        codigo, _, _ = _pedir(url, "POST", {"item": "capa", "decisao": "aprovado"},
                              {"Content-Type": "application/json", "Origin": "https://site-mau.example"})
        self.assertEqual(codigo, 403)
        codigo, _, _ = _pedir(base + "/painel/api/projetos", cabecalhos={"Host": "site-mau.example"})
        self.assertEqual(codigo, 403)
        codigo, _, corpo = _pedir(base + "/painel/api/novo", "POST", {"tema": "dicas de sono", "tipo": "video_curto"},
                                  {"Content-Type": "application/json", "Origin": base})
        self.assertEqual(codigo, 202)
        self.assertTrue(json.loads(corpo)["job_id"].startswith("stu_"))

    def test_token_com_cookie(self):
        base = self._subir(token="segredo-de-teste")
        self.assertEqual(_pedir(base + "/painel/")[0], 200)  # a página abre (não tem dados)
        codigo, _, corpo = _pedir(base + "/painel/api/projetos")
        self.assertEqual((codigo, json.loads(corpo).get("precisa_token")), (401, True))
        self.assertEqual(_pedir(base + "/painel/arquivo/cha-verde/capa.jpg")[0], 401)
        self.assertEqual(_pedir(base + "/painel/entrar", "POST", {"token": "errado"})[0], 401)
        codigo, cab, _ = _pedir(base + "/painel/entrar", "POST", {"token": "segredo-de-teste"})
        self.assertEqual(codigo, 200)
        self.assertIn("HttpOnly", cab["Set-Cookie"])
        self.assertIn("SameSite=Strict", cab["Set-Cookie"])
        sessao = cab["Set-Cookie"].split(";")[0]
        self.assertNotIn("segredo-de-teste", cab["Set-Cookie"])  # o token de verdade nunca vai para o cookie
        biscoito = {"Cookie": sessao}
        self.assertEqual(_pedir(base + "/painel/api/projetos", cabecalhos=biscoito)[0], 200)
        self.assertEqual(_pedir(base + "/v1/pecas/stu_00000000", cabecalhos=biscoito)[0], 404)  # autorizado
        self.assertEqual(_pedir(base + "/painel/api/projetos", cabecalhos={"Cookie": "torralles_token=x"})[0], 401)
        self.assertEqual(_pedir(base + "/painel/api/projetos", cabecalhos={"Cookie": "segredo-de-teste"})[0], 401)
        # cookies de outros apps deste PC chegam juntos (não separa por porta) e não podem atrapalhar
        outros = {"Cookie": 'prefs={"a":1}; a=b c; ' + sessao + "; x=y"}
        self.assertEqual(_pedir(base + "/painel/api/projetos", cabecalhos=outros)[0], 200)
        # com cookie, o que muda algo só vale da própria página (outra porta deste PC também recebe o cookie)
        url = base + "/painel/api/projetos/cha-verde/revisao"
        voto = {"item": "capa", "decisao": "aprovado"}
        self.assertEqual(_pedir(url, "POST", voto, {**biscoito, "Content-Type": "application/json",
                                                    "Origin": "http://127.0.0.1:9999"})[0], 403)
        self.assertEqual(_pedir(url, "POST", voto, {**biscoito, "Content-Type": "application/json"})[0], 403)
        self.assertEqual(_pedir(url, "POST", voto, {**biscoito, "Content-Type": "application/json",
                                                    "Origin": base})[0], 200)
        self.assertEqual(_pedir(base + "/v1/pecas/stu_00000000/cancelar", "POST", {},
                                {**biscoito, "Origin": "http://localhost:9999"})[0], 403)
        self.assertEqual(_pedir(base + "/v1/pecas/stu_00000000/cancelar", "POST", {},
                                {"Authorization": "Bearer segredo-de-teste"})[0], 404)  # o Ops segue igual

    def test_sem_painel_as_rotas_antigas_seguem(self):
        http = criar_servidor_http(self.servico, porta=0)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        base = f"http://127.0.0.1:{http.server_address[1]}"
        self.assertEqual(_pedir(base + "/v1/saude")[0], 200)
        self.assertEqual(_pedir(base + "/painel/")[0], 404)


class TestPagina(unittest.TestCase):
    def test_sem_script_em_linha_nem_innerhtml(self):
        html = (PASTA_WEB / "index.html").read_text(encoding="utf-8")
        for tag in re.findall(r"<script[^>]*>", html):
            self.assertIn("src=", tag)
        self.assertNotRegex(html, r"\son[a-z]+=")
        self.assertNotRegex(html, r"https?://")  # nada de CDN: funciona sem internet
        js = (PASTA_WEB / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("outerHTML", js)
        self.assertNotIn("eval(", js)
        self.assertNotIn("insertAdjacentHTML", js)


if __name__ == "__main__":
    unittest.main()

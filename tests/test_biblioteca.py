import tempfile
import unittest
from pathlib import Path

from torralles_studio.banco import Banco
from torralles_studio.biblioteca import Biblioteca, ErroLicenca, conferir_licenca, normalizar_licenca


class BaseBiblioteca(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.banco = Banco(self.dir / "t.db")
        self.bib = Biblioteca(self.dir / "biblioteca", self.banco)

    def tearDown(self):
        self.banco.fechar()
        self.tmp.cleanup()

    def arquivo(self, nome, conteudo):
        caminho = self.dir / "entrada" / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)
        return caminho


class TestSemDuplicatas(BaseBiblioteca):
    def test_mesmo_conteudo_entra_uma_vez_e_soma_etiquetas(self):
        a = self.bib.adicionar(self.arquivo("chuva.wav", b"som de chuva"), "CC0", "Freesound", tags=["chuva"])
        b = self.bib.adicionar(self.arquivo("outra-copia.WAV", b"som de chuva"), "cc0", "pacote local",
                               tags=["Natureza", "chuva"])
        self.assertFalse(a["duplicado"])
        self.assertTrue(b["duplicado"])
        self.assertEqual(a["hash"], b["hash"])
        self.assertEqual(b["tags"], ["chuva", "natureza"])
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM ativos").fetchone()[0], 1)
        self.assertEqual(len(list((self.dir / "biblioteca" / "ativos").rglob("*.wav"))), 1)

    def test_arquivo_guardado_pelo_hash_e_intacto(self):
        a = self.bib.adicionar(self.arquivo("Foto Café.JPG", b"jpeg"), "pexels", "Pexels")
        caminho = self.bib.caminho(a)
        self.assertEqual(caminho.name, f"{a['hash']}.jpg")
        self.assertEqual(caminho.parent.name, a["hash"][:2])
        self.assertEqual(caminho.read_bytes(), b"jpeg")
        self.assertEqual(a["tipo"], "imagem")
        self.assertEqual(self.bib.verificar(), [])
        caminho.write_bytes(b"mexeram")
        self.assertIn("alterado", self.bib.verificar()[0])
        caminho.unlink()
        self.assertIn("sumiu", self.bib.verificar()[0])

    def test_destino_corrompido_e_copiado_de_novo(self):
        import hashlib
        conteudo = b"conteudo certo"
        digest = hashlib.sha256(conteudo).hexdigest()
        destino = self.dir / "biblioteca" / "ativos" / digest[:2] / f"{digest}.png"
        destino.parent.mkdir(parents=True)
        destino.write_bytes(b"corrompido")
        a = self.bib.adicionar(self.arquivo("a.png", conteudo), "cc0", "x")
        self.assertEqual(self.bib.caminho(a).read_bytes(), conteudo)

    def test_falha_no_banco_nao_deixa_arquivo_orfao(self):
        from unittest import mock
        arq = self.arquivo("b.png", b"orfao?")
        real = self.bib.con

        class ConFalha:
            def __getattr__(self, nome):
                return getattr(real, nome)

            def __enter__(self):
                return real.__enter__()

            def __exit__(self, *a):
                return real.__exit__(*a)

            def execute(self, sql, *a):
                if sql.startswith("INSERT INTO ativos"):
                    raise RuntimeError("disco cheio")
                return real.execute(sql, *a)

        with mock.patch.object(self.bib, "con", ConFalha()):
            with self.assertRaisesRegex(RuntimeError, "disco cheio"):
                self.bib.adicionar(arq, "cc0", "x")
        self.assertEqual(list((self.dir / "biblioteca" / "ativos").rglob("*.png")), [])

    def test_duplicata_corrige_tipo_desconhecido(self):
        a = self.bib.adicionar(self.arquivo("x.bin", b"png bytes"), "cc0", "x")
        self.assertEqual(a["tipo"], "outro")
        self.assertEqual(self.bib.adicionar(self.arquivo("x.png", b"png bytes"), "cc0", "x")["tipo"], "imagem")

    def test_original_pode_ser_apagado(self):
        origem = self.arquivo("v.mp4", b"video")
        a = self.bib.adicionar(origem, "pixabay", "Pixabay")
        origem.unlink()
        self.assertEqual(self.bib.caminho(a).read_bytes(), b"video")


class TestLicencaObrigatoria(BaseBiblioteca):
    def test_sem_licenca_ou_bloqueada_nao_entra(self):
        arq = self.arquivo("trilha.mp3", b"musica")
        casos = {None: "obrigatória", "": "obrigatória", "CC BY-NC 4.0": "não permite uso comercial",
                 "CC-BY-ND": "não permite edição", "CC BY-SA 3.0": "mesma licença", "uso pessoal": "só uso pessoal",
                 "desconhecida": "sem licença clara", "licença da loja X": "desconhecida"}
        for licenca, motivo in casos.items():
            with self.subTest(licenca=licenca), self.assertRaisesRegex(ErroLicenca, motivo):
                self.bib.adicionar(arq, licenca, "site")
        self.assertEqual(self.banco.con.execute("SELECT COUNT(*) FROM ativos").fetchone()[0], 0)
        self.assertFalse((self.dir / "biblioteca" / "ativos").exists())

    def test_cc_by_exige_autor_e_gera_credito(self):
        arq = self.arquivo("passos.wav", b"passos")
        with self.assertRaisesRegex(ErroLicenca, "exige crédito"):
            self.bib.adicionar(arq, "CC BY 4.0", "Freesound")
        a = self.bib.adicionar(arq, "CC BY 4.0", "Freesound", autor="Ana", link="https://freesound.org/s/1",
                               titulo="Passos na madeira")
        b = self.bib.adicionar(self.arquivo("x.png", b"img"), "cc0", "Openverse")
        creditos = self.bib.creditos([a, b, a])
        self.assertEqual(creditos, "Créditos:\n- Passos na madeira — por Ana — CC BY — Freesound — https://freesound.org/s/1")
        self.assertEqual(self.bib.creditos([b]), "")

    def test_fonte_obrigatoria(self):
        with self.assertRaisesRegex(ErroLicenca, "fonte"):
            self.bib.adicionar(self.arquivo("a.png", b"a"), "cc0", "  ")

    def test_nomes_oficiais_de_licenca(self):
        aceitas = {"Pixabay Content License": "pixabay", "Pexels License": "pexels", "CC0 1.0 Universal": "cc0",
                   "CC BY 4.0 International": "cc-by", "Attribution 4.0 International": "cc-by",
                   "próprio": "proprio", "CC BY 3.0 BR": "cc-by"}
        for nome, codigo in aceitas.items():
            with self.subTest(nome=nome):
                self.assertEqual(conferir_licenca(nome)[0], codigo)
        for nome in ("Attribution-NonCommercial 4.0 International", "CC BY‐NC 4.0", "ＣＣ ＢＹ-NC", "personal use",
                     "Attribution-ShareAlike 4.0"):
            with self.subTest(nome=nome), self.assertRaises(ErroLicenca):
                conferir_licenca(nome)

    def test_creditos_limpos_e_link_so_http(self):
        with self.assertRaisesRegex(ErroLicenca, "http"):
            self.bib.adicionar(self.arquivo("s.wav", b"s"), "cc-by", "x", autor="Ana", link="javascript:alert(1)")
        a = self.bib.adicionar(self.arquivo("som da porta.wav", b"porta"), "cc-by", "Freesound", autor="Ana\nSilva")
        self.assertEqual(self.bib.creditos([a]), "Créditos:\n- som da porta — por Ana Silva — CC BY — Freesound")

    def test_normalizacao_de_licencas(self):
        self.assertEqual(normalizar_licenca("CC BY 4.0"), "cc-by")
        self.assertEqual(normalizar_licenca("cc_by_nc_sa_3.0"), "cc-by-nc-sa")
        self.assertEqual(normalizar_licenca("Public Domain"), "cc0")
        self.assertEqual(conferir_licenca("Gerado IA")[0], "gerado_ia")

    def test_ativo_guarda_origem_completa(self):
        a = self.bib.adicionar(self.arquivo("cena1.png", b"png"), "gerado_ia", "fal_flux", provedor="fal_flux",
                               modelo="flux-schnell", prompt="pôr do sol na praia", parametros={"seed": 7})
        self.assertEqual((a["licenca"], a["uso_comercial"], a["provedor"], a["modelo"]),
                         ("gerado_ia", True, "fal_flux", "flux-schnell"))
        self.assertEqual(a["parametros"], {"seed": 7})
        self.assertTrue(a["criado_em"])


class TestBusca(BaseBiblioteca):
    def setUp(self):
        super().setUp()
        self.chuva = self.bib.adicionar(self.arquivo("chuva.wav", b"1"), "cc0", "pacote", tags=["chuva", "calmo"])
        self.vento = self.bib.adicionar(self.arquivo("vento.wav", b"2"), "cc0", "pacote", tags=["vento", "calmo"])
        self.foto = self.bib.adicionar(self.arquivo("praia.jpg", b"3"), "pexels", "Pexels", tags=["calmo"],
                                       prompt="praia ao entardecer")

    def test_todas_as_etiquetas_pedidas(self):
        self.assertEqual({a["hash"] for a in self.bib.buscar(["calmo"])},
                         {self.chuva["hash"], self.vento["hash"], self.foto["hash"]})
        self.assertEqual([a["hash"] for a in self.bib.buscar(["Calmo", "chuva"])], [self.chuva["hash"]])
        self.assertEqual(self.bib.buscar(["chu"]), [])  # etiqueta inteira, não pedaço

    def test_busca_ignora_ativo_sem_licenca_aceita(self):
        with self.banco.con:
            self.banco.con.execute("UPDATE ativos SET licenca = 'cc-by-nc' WHERE hash = ?", (self.vento["hash"],))
        self.assertEqual(len(self.bib.buscar(["calmo"])), 2)
        self.assertIsNone(self.bib.obter(self.vento["hash"]))

    def test_tipo_e_texto(self):
        self.assertEqual(len(self.bib.buscar(["calmo"], tipo="audio")), 2)
        self.assertEqual([a["hash"] for a in self.bib.buscar(texto="entardecer")], [self.foto["hash"]])
        self.assertEqual(self.bib.buscar(texto="%"), [])

    def test_ativo_de_um_perfil_nao_aparece_para_outro(self):
        logo = self.bib.adicionar(self.arquivo("logo.png", b"logo A"), "proprio", "produção própria",
                                  tags=["logo"], perfil="canal-a")
        self.assertEqual([a["hash"] for a in self.bib.buscar(["logo"], perfil="canal-a")], [logo["hash"]])
        self.assertEqual(self.bib.buscar(["logo"], perfil="loja-b"), [])
        self.assertEqual(self.bib.buscar(["logo"]), [])
        self.assertEqual(len(self.bib.buscar(["calmo"], perfil="loja-b")), 3)  # compartilhados aparecem
        self.assertIsNone(self.bib.obter(logo["hash"], perfil="loja-b"))
        self.assertNotIn("perfil", logo)  # o dono não é exposto

    # Regressões da verificação independente (K25)
    def test_etiquetas_de_um_perfil_nao_vazam_para_outro(self):
        self.bib.adicionar(self.arquivo("copia-chuva.wav", b"1"), "cc0", "pacote", tags=["segredo-a"], perfil="canal-a")
        self.assertEqual(self.bib.obter(self.chuva["hash"], perfil="loja-b")["tags"], ["calmo", "chuva"])
        self.assertEqual(self.bib.obter(self.chuva["hash"], perfil="canal-a")["tags"], ["calmo", "chuva", "segredo-a"])
        self.assertEqual(self.bib.buscar(["segredo-a"], perfil="loja-b"), [])
        self.assertEqual(len(self.bib.buscar(["segredo-a", "chuva"], perfil="canal-a")), 1)

    def test_mesmo_arquivo_em_dois_perfis_sem_erro_e_sem_revelar_o_outro(self):
        a = self.bib.adicionar(self.arquivo("mar.mp4", b"video do mar"), "pexels", "Pexels", tags=["mar"],
                               perfil="canal-a")
        b = self.bib.adicionar(self.arquivo("mar2.mp4", b"video do mar"), "pexels", "Pexels", tags=["oceano"],
                               perfil="loja-b")
        self.assertEqual(a["hash"], b["hash"])
        self.assertTrue(b["duplicado"])
        self.assertEqual(b["tags"], ["oceano"])
        self.assertEqual(self.bib.obter(a["hash"], perfil="canal-a")["tags"], ["mar"])
        self.assertEqual(self.bib.buscar(["mar"], perfil="loja-b"), [])


class TestConfigDaBiblioteca(unittest.TestCase):
    def test_carregar_biblioteca(self):
        from torralles_studio.config import carregar_biblioteca

        with tempfile.TemporaryDirectory() as d:
            banco = Banco(Path(d) / "t.db")
            bib = carregar_biblioteca(banco=banco)
            self.assertTrue(str(bib.raiz).endswith("dados/biblioteca"))
            banco.fechar()


if __name__ == "__main__":
    unittest.main()

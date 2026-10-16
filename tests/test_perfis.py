import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from torralles_studio import funcoes
from torralles_studio.banco import Banco
from torralles_studio.perfis import ErroPerfil, Perfis, criar_perfil
from torralles_studio.provedores.base import Provedor
from torralles_studio.roteador import Roteador
from torralles_studio.seguranca import Orcamento

# Perfis fictícios: não representam nenhum projeto real (D9).
CURIOSIDADES = '''
id = "canal-curiosidades"
nome = "Canal de Curiosidades"
categoria = "A"
hermes_perfil = "curiosidades"
teto_custo_usd = 0.50
[estilo]
publico = "jovens curiosos"
tom = "animado e rápido"
cta_padrao = "siga para mais fatos"
palavras_evitar = ["chocante"]
[formato]
proporcao = "9:16"
duracao_s = 30
[kit_visual]
estilo_imagem = "ilustração colorida"
paleta = ["#FF5500"]
logo = "logo.png"
[provedores.voz_falsa]
voz = "voz-animada"
'''

LOJA = '''
id = "loja-cha"
nome = "Loja de Chás"
categoria = "D"
hermes_perfil = "loja"
[estilo]
publico = "adultos que gostam de chá"
tom = "calmo e acolhedor"
cta_padrao = "visite a loja"
palavras_evitar = ["barato"]
[formato]
proporcao = "1:1"
[kit_visual]
estilo_imagem = "fotografia natural"
paleta = ["#2E7D32"]
'''


class VozFalsa(Provedor):
    tipo = "voz"

    def __init__(self):
        super().__init__("voz_falsa", {"voz": "voz-padrao", "modelo": "v1", "custo_usd": 0.01})
        self.vozes = []

    def configurado(self):
        return None

    def executar(self, texto, saida):
        self.vozes.append(self.cfg["voz"])
        Path(saida).parent.mkdir(parents=True, exist_ok=True)
        Path(saida).write_bytes(f"{self.cfg['voz']}:{texto}".encode())
        return Path(saida)


class TextoFalso(Provedor):
    tipo = "texto"

    def __init__(self):
        super().__init__("texto_falso", {"modelo": "t1"})
        self.sistemas = []

    def configurado(self):
        return None

    def executar(self, prompt, sistema=None):
        self.sistemas.append(sistema)
        return '{"titulo": "x", "cenas": [{"narracao": "a", "prompt_imagem": "b", "duracao": 5}]}'


def pasta_com(**arquivos):
    d = tempfile.TemporaryDirectory()
    for nome, texto in arquivos.items():
        (Path(d.name) / nome).write_text(texto, encoding="utf-8")
    return d


class TestPerfisNaoSeMisturam(unittest.TestCase):
    def setUp(self):
        self.tmp = pasta_com(**{"canal-curiosidades.toml": CURIOSIDADES, "loja-cha.toml": LOJA})
        self.perfis = Perfis(self.tmp.name)
        self.a, self.b = self.perfis.obter("canal-curiosidades"), self.perfis.obter("loja-cha")

    def tearDown(self):
        self.tmp.cleanup()

    def test_obter_por_id_ou_pelo_perfil_do_hermes(self):
        self.assertIs(self.perfis.obter("loja"), self.b)
        with self.assertRaisesRegex(ErroPerfil, "não encontrado"):
            self.perfis.obter("outro")

    def test_contexto_do_prompt_so_tem_dados_do_proprio_perfil(self):
        ca, cb = self.a.contexto("imagem"), self.b.contexto("imagem")
        for valor in ("Loja de Chás", "calmo e acolhedor", "visite a loja", "barato", "fotografia natural", "#2E7D32"):
            self.assertNotIn(valor, ca)
            self.assertIn(valor, cb)
        for valor in ("Canal de Curiosidades", "animado e rápido", "chocante", "ilustração colorida", "9:16"):
            self.assertNotIn(valor, cb)
            self.assertIn(valor, ca)

    def test_palavras_proibidas_valem_so_no_perfil_que_as_define(self):
        texto = "Um fato chocante sobre chá barato"
        self.assertEqual(len(self.a.checar_texto(texto)), 1)
        self.assertIn("chocante", self.a.checar_texto(texto)[0])
        self.assertIn("barato", self.b.checar_texto(texto)[0])
        self.assertEqual(self.a.checar_texto("Chocantemente simples"), [])  # palavra inteira só

    def test_voz_do_perfil_nao_vaza_para_o_roteador_base_nem_para_outro_perfil(self):
        voz = VozFalsa()
        with tempfile.TemporaryDirectory() as d:
            db = Banco(Path(d) / "t.db")
            base = Roteador({"voz_falsa": voz}, {"voz": ["voz_falsa"]}, orcamento=Orcamento(1.5), cache=db)
            ra, rb = self.a.roteador(base), self.b.roteador(base)
            ra.executar("voz", texto="olá", saida=Path(d) / "a.mp3")
            rb.executar("voz", texto="olá", saida=Path(d) / "b.mp3")  # mesmo texto: não pode vir do cache de A
            r = base.executar("voz", texto="olá", saida=Path(d) / "c.mp3")  # mesma voz que B: cache serve
            self.assertEqual((Path(d) / "a.mp3").read_bytes(), "voz-animada:olá".encode())
            self.assertEqual((Path(d) / "b.mp3").read_bytes(), "voz-padrao:olá".encode())
            self.assertEqual(r.tentativas[-1].status, "cache")
            db.fechar()
        self.assertEqual(voz.cfg["voz"], "voz-padrao")
        self.assertEqual(voz.vozes, ["voz-animada", "voz-padrao"])

    def test_teto_proprio_do_perfil_nao_mistura_gastos(self):
        base = Roteador({}, {}, orcamento=Orcamento(1.5))
        ra, rb = self.a.roteador(base), self.b.roteador(base)
        self.assertEqual(ra.orcamento.teto_usd, 0.5)
        self.assertIsNot(ra.orcamento, base.orcamento)
        self.assertIs(rb.orcamento, base.orcamento)  # sem teto próprio, vale o do config

    def test_memoria_e_projetos_separados_por_perfil(self):
        db = Banco()
        mid = db.lembrar(self.a.id, "aprendizado", "ganchos com pergunta funcionam")
        db.lembrar(self.b.id, "perfil", "fotos com luz natural")
        self.assertEqual([m["conteudo"] for m in db.memorias(self.a.id)], ["ganchos com pergunta funcionam"])
        self.assertEqual([m["conteudo"] for m in db.memorias(self.b.id, busca="luz")], ["fotos com luz natural"])
        self.assertEqual(db.memorias(self.b.id, busca="ganchos"), [])
        self.assertFalse(db.esquecer(self.b.id, mid))  # B não apaga memória de A
        self.assertTrue(db.esquecer(self.a.id, mid))
        with self.assertRaises(ValueError):
            db.lembrar(None, "aprendizado", "sem dono")
        pa = db.criar_projeto("vídeo 1", perfil=self.a.id)
        db.criar_projeto("post 1", perfil=self.b.id)
        self.assertEqual([p["id"] for p in db.projetos(self.a.id)], [pa])

    def test_busca_na_memoria_trata_curinga_como_texto(self):
        db = Banco()
        db.lembrar(self.a.id, "historico", "100% de retenção")
        db.lembrar(self.a.id, "historico", "outra coisa")
        self.assertEqual(len(db.memorias(self.a.id, busca="%")), 1)

    def test_kit_visual_so_usa_arquivos_da_propria_pasta(self):
        self.assertEqual(self.a.arquivo("logo.png"), (Path(self.tmp.name) / "canal-curiosidades" / "logo.png").resolve())
        with self.assertRaisesRegex(ErroPerfil, "própria pasta"):
            self.a.arquivo("../loja-cha/logo.png")
        invasor = CURIOSIDADES.replace('logo = "logo.png"', 'logo = "../loja-cha/logo.png"')
        with pasta_com(**{"canal-curiosidades.toml": invasor}) as d:
            with self.assertRaisesRegex(ErroPerfil, "própria pasta"):
                Perfis(d)

    def test_roteiro_e_imagem_recebem_o_contexto_do_perfil(self):
        texto = TextoFalso()
        rt = Roteador({"texto_falso": texto}, {"roteiro": ["texto_falso"]})
        funcoes.gerar_roteiro(rt, "chá verde", perfil=self.b)
        funcoes.gerar_roteiro(rt, "chá verde")
        self.assertIn("Loja de Chás", texto.sistemas[0])
        self.assertNotIn("Loja de Chás", texto.sistemas[1])


class TestValidacao(unittest.TestCase):
    def carregar(self, nome, texto, provedores=None):
        with pasta_com(**{nome: texto}) as d:
            return Perfis(d, provedores_conhecidos=provedores)

    def test_erros_claros(self):
        casos = [
            ("outro-nome.toml", LOJA, "igual ao id"),
            ("loja-cha.toml", LOJA.replace('categoria = "D"', 'categoria = "Z"'), "categoria"),
            ("loja-cha.toml", LOJA.replace('proporcao = "1:1"', 'proporcao = "3:2"'), "proporção"),
            ("loja-cha.toml", LOJA.replace('nome = "Loja de Chás"', 'nome = ""'), "falta 'nome'"),
            ("loja-cha.toml", LOJA + '[provedores.voz_falsa]\nchave_env = "OUTRA_CHAVE"\n', "não pode mudar"),
            ("loja-cha.toml", LOJA + "[provedores.inexistente]\nvoz = 'x'\n", "provedor desconhecido"),
            ("loja-cha.toml", "id = ", "TOML inválido"),
        ]
        for nome, texto, msg in casos:
            with self.subTest(msg=msg), self.assertRaisesRegex(ErroPerfil, msg):
                self.carregar(nome, texto, provedores={"voz_falsa"})

    def test_mesmo_perfil_do_hermes_em_dois_perfis(self):
        dup = CURIOSIDADES.replace('hermes_perfil = "curiosidades"', 'hermes_perfil = "loja"')
        with pasta_com(**{"canal-curiosidades.toml": dup, "loja-cha.toml": LOJA}) as d:
            with self.assertRaisesRegex(ErroPerfil, "ligado a dois perfis"):
                Perfis(d)

    def test_arquivos_com_sublinhado_e_pasta_inexistente_sao_ignorados(self):
        with pasta_com(**{"_rascunho.toml": "id = "}) as d:
            self.assertEqual(list(Perfis(d)), [])
        self.assertEqual(list(Perfis("/caminho/que/nao/existe")), [])


class TestCriarPerfil(unittest.TestCase):
    def test_modelo_gera_perfil_valido_e_comando_lista(self):
        from torralles_studio.__main__ import main
        from torralles_studio.config import CONFIG_PADRAO, MODELO_PERFIL

        with tempfile.TemporaryDirectory() as d:
            texto = Path(CONFIG_PADRAO).read_text(encoding="utf-8").replace(
                'pasta = "dados/perfis"', f'pasta = "{Path(d).as_posix()}/perfis"')
            cfg = Path(d) / "c.toml"
            cfg.write_text(texto, encoding="utf-8")
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                self.assertEqual(main(["--config", str(cfg), "perfil-novo", "meu-canal", "Meu Canal"]), 0)
                self.assertEqual(main(["--config", str(cfg), "perfis"]), 0)
            self.assertIn("meu-canal", saida.getvalue())
            self.assertTrue((Path(d) / "perfis" / "meu-canal").is_dir())
            with self.assertRaisesRegex(ErroPerfil, "já existe"):
                criar_perfil(Path(d) / "perfis", "meu-canal", "x", MODELO_PERFIL)
            with self.assertRaisesRegex(ErroPerfil, "id inválido"):
                criar_perfil(Path(d) / "perfis", "Meu Canal", "x", MODELO_PERFIL)


if __name__ == "__main__":
    unittest.main()

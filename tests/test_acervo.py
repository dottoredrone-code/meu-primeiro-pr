import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio import acervo
from torralles_studio.banco import Banco
from torralles_studio.biblioteca import Biblioteca, ErroLicenca
from torralles_studio.efeitos import escolher_efeitos, importar_pasta as importar_sons


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _som(arq, dur=4.0, volume=0.05, freq=440):
    Path(arq).parent.mkdir(parents=True, exist_ok=True)
    _ff("-f", "lavfi", "-i", f"sine=f={freq}:d={dur}", "-af", f"volume={volume}", "-ar", "44100", str(arq))
    return Path(arq)


def _imagem(arq, largura, altura):
    _ff("-f", "lavfi", "-i", f"color=c=green:s={largura}x{altura}", "-frames:v", "1", str(arq))
    return Path(arq)


class TestPuras(unittest.TestCase):
    def test_nivel_energia_e_orientacao(self):
        self.assertEqual([acervo.nivel_energia(e) for e in (0.1, 0.5, 0.9, None)], ["baixa", "media", "alta", None])
        self.assertEqual(acervo.orientacao(1080, 1920), "vertical")
        self.assertEqual(acervo.orientacao(1920, 1080), "horizontal")
        self.assertEqual(acervo.orientacao(1000, 1000), "quadrado")

    def test_clima_pelo_nome_em_portugues_e_ingles(self):
        self.assertEqual(acervo.clima_do_nome(["epic", "trailer"]), "epico")
        self.assertEqual(acervo.clima_do_nome(["piano", "suave"]), "reflexivo")
        self.assertEqual(acervo.clima_do_nome(["calma"]), "calmo")
        self.assertIsNone(acervo.clima_do_nome(["track", "01"]))

    def test_etiquetas_usam_pasta_nome_e_medidas(self):
        pasta = Path("/acervo")
        tags, clima = acervo.etiquetas(pasta / "Suspense" / "dark-loop 2.mp3", pasta, "trilha",
                                       {"energia": 0.8, "loop": False})
        self.assertEqual(clima, "tenso")
        for t in ("tipo-trilha", "clima-tenso", "energia-alta", "loop", "suspense", "dark"):
            self.assertIn(t, tags)
        self.assertNotIn("2", tags)
        tags, _ = acervo.etiquetas(pasta / "whoosh.mp3", pasta, "efeito", {"energia": 0.3})
        self.assertIn("som-whoosh", tags)  # compatível com a escolha de efeitos da montagem

    def test_clima_informado_vale_mais_que_o_nome(self):
        tags, clima = acervo.etiquetas(Path("/a/epic.mp3"), Path("/a"), "trilha", {}, clima="calmo")
        self.assertEqual(clima, "calmo")
        self.assertIn("clima-calmo", tags)
        self.assertNotIn("clima-epico", tags)


class _ComBiblioteca(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)
        self.banco = Banco(self.d / "b.db").__enter__()
        self.bib = Biblioteca(self.d / "bib", self.banco)
        self.pasta = self.d / "entrada"
        self.pasta.mkdir()

    def tearDown(self):
        self.banco.__exit__(None, None, None)
        self._d.cleanup()


class TestImportarSemFFmpeg(_ComBiblioteca):
    """Regras da importação com medidas falsas (rodam sem FFmpeg)."""

    def _arq(self, nome, conteudo=b"x"):
        arq = self.pasta / nome
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(conteudo + nome.encode())
        return arq

    def test_tipo_e_clima_desconhecidos(self):
        with self.assertRaises(acervo.ErroAcervo):
            acervo.importar_pasta(self.bib, self.pasta, "musica", "cc0", "X")
        with self.assertRaises(acervo.ErroAcervo):
            acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "X", clima="triste")

    def test_licenca_bloqueada_nao_abre_a_pasta(self):  # D2
        self._arq("calm.mp3")
        with self.assertRaises(ErroLicenca):
            acervo.importar_pasta(self.bib, self.pasta, "trilha", "CC BY-NC 4.0", "Freesound",
                                  medir_arquivo=lambda a, t: {"duracao_s": 30})
        self.assertEqual(self.bib.buscar(), [])
        self.assertFalse((self.bib.raiz / "licencas").exists())

    def test_arquivo_ilegivel_nao_para_os_outros(self):
        self._arq("calm-a.mp3")
        self._arq("calm-b.mp3")

        def medir(arq, tipo):
            if arq.name == "calm-a.mp3":
                raise acervo.ErroProvedor("áudio em silêncio")
            return {"duracao_s": 30.0, "energia": 0.2, "loop": False, "bpm": None}
        importados, problemas = acervo.importar_pasta(self.bib, self.pasta, "trilha", "pixabay", "Pixabay",
                                                      medir_arquivo=medir)
        self.assertEqual([a["titulo"] for a in importados], ["calm-b"])
        self.assertIn("silêncio", problemas[0])

    def test_so_o_tipo_de_arquivo_certo_e_subpastas(self):
        self._arq("calm.mp3")
        self._arq("Epic/hero.wav")
        self._arq("capa.png")
        self._arq("leia.txt")
        importados, _ = acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "Kenney",
                                              medir_arquivo=lambda a, t: {"duracao_s": 10.0, "energia": 0.5})
        self.assertEqual(sorted(a["titulo"] for a in importados), ["calm", "hero"])
        hero = next(a for a in importados if a["titulo"] == "hero")
        self.assertIn("clima-epico", hero["tags"])  # o nome da pasta sugere o clima

    def test_medidas_ficam_guardadas_e_licenca_anotada(self):
        self._arq("calm.mp3")
        medidas = {"duracao_s": 31.5, "energia": 0.21, "loop": True, "bpm": 72.0}
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "pixabay", "Pixabay",
                              link="https://pixabay.com/service/license-summary/",
                              medir_arquivo=lambda a, t: dict(medidas))
        ativo = self.bib.buscar(["tipo-trilha"])[0]
        self.assertEqual(ativo["medidas"], medidas)  # lido do banco, não medido de novo
        nota = (self.bib.raiz / "licencas" / "pixabay.txt").read_text(encoding="utf-8")
        self.assertIn("Licença Pixabay", nota)
        self.assertIn("uso comercial: sim", nota)
        self.assertIn("https://pixabay.com/service/license-summary/", nota)

    def test_copia_o_texto_da_licenca(self):
        self._arq("calm.mp3")
        texto = self.d / "LICENSE.txt"
        texto.write_text("termos da fonte", encoding="utf-8")
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "Kenney", arquivo_licenca=texto,
                              medir_arquivo=lambda a, t: {"duracao_s": 5.0})
        self.assertEqual((self.bib.raiz / "licencas" / "kenney-cc0.txt").read_text(encoding="utf-8"),
                         "termos da fonte")

    def test_busca_por_clima_energia_e_duracao(self):
        dados = {"calm-curta.mp3": (12.0, 0.2), "calm-longa.mp3": (95.0, 0.25), "calm-certa.mp3": (40.0, 0.2),
                 "epic.mp3": (60.0, 0.9)}
        for nome in dados:
            self._arq(nome)
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "X",
                              medir_arquivo=lambda a, t: {"duracao_s": dados[a.name][0], "energia": dados[a.name][1]})
        calmas = acervo.buscar(self.bib, tipo="trilha", clima="calmo", duracao=30)
        self.assertEqual([a["titulo"] for a in calmas], ["calm-certa", "calm-longa", "calm-curta"])
        self.assertEqual([a["titulo"] for a in acervo.buscar(self.bib, energia="alta")], ["epic"])
        self.assertEqual(acervo.buscar(self.bib, tipo="efeito"), [])
        with self.assertRaises(acervo.ErroAcervo):
            acervo.buscar(self.bib, clima="triste")

    def test_efeito_curto_prefere_a_duracao_mais_proxima(self):
        dados = {"whoosh-a.mp3": 0.4, "whoosh-b.mp3": 1.1, "whoosh-c.mp3": 2.5}
        for nome in dados:
            self._arq(nome)
        acervo.importar_pasta(self.bib, self.pasta, "efeito", "cc0", "X",
                              medir_arquivo=lambda a, t: {"duracao_s": dados[a.name], "energia": 0.5})
        achados = acervo.buscar(self.bib, tipo="efeito", duracao=1.0)
        self.assertEqual(achados[0]["titulo"], "whoosh-b")

    def test_busca_ignora_o_que_veio_pelo_importar_sons_e_respeita_o_perfil(self):
        self._arq("calm.mp3")
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "X", perfil="canal-a",
                              medir_arquivo=lambda a, t: {"duracao_s": 30.0})
        self.assertEqual(acervo.buscar(self.bib, tipo="trilha", perfil="canal-b"), [])
        self.assertEqual(len(acervo.buscar(self.bib, tipo="trilha", perfil="canal-a")), 1)
        self.bib.adicionar(self._arq("solto.mp3"), "cc0", "X", tags=["calmo"])  # sem tipo- do acervo
        self.assertEqual(len(acervo.buscar(self.bib, perfil="canal-a")), 1)

    def test_mesmo_arquivo_com_outro_tipo_soma_as_medidas(self):
        self._arq("calm.mp3")
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "X",
                              medir_arquivo=lambda a, t: {"duracao_s": 30.0, "bpm": 90.0})
        acervo.importar_pasta(self.bib, self.pasta, "efeito", "cc0", "X", clima="tenso",
                              medir_arquivo=lambda a, t: {"duracao_s": 30.0, "energia": 0.8})
        achado = acervo.buscar(self.bib, tipo="trilha", clima="calmo")[0]
        self.assertEqual(achado["medidas"]["bpm"], 90.0)  # o BPM da trilha não some
        r = acervo.resumo(achado, "trilha", "calmo")
        self.assertEqual((r["tipo"], r["clima"]), ("trilha", "calmo"))

    def test_arquivo_de_licenca_inexistente_nada_entra(self):  # D18
        self._arq("calm.mp3")
        with self.assertRaises(FileNotFoundError):
            acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "X", arquivo_licenca=self.d / "nao.txt",
                                  medir_arquivo=lambda a, t: {"duracao_s": 5.0})
        self.assertEqual(self.bib.buscar(), [])

    def test_reimportar_com_a_copia_da_licenca(self):
        self._arq("calm.mp3")
        texto = self.d / "LICENSE.txt"
        texto.write_text("termos", encoding="utf-8")
        medir = lambda a, t: {"duracao_s": 5.0}  # noqa: E731
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "Kenney", arquivo_licenca=texto,
                              medir_arquivo=medir)
        copia = self.bib.raiz / "licencas" / "kenney-cc0.txt"
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "Kenney", arquivo_licenca=copia,
                              medir_arquivo=medir)  # a própria cópia: sem erro
        self.assertEqual(copia.read_text(encoding="utf-8"), "termos")

    def test_fonte_com_quebra_de_linha_fica_numa_linha(self):
        self._arq("calm.mp3")
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "Kenney\nfalsa", medir_arquivo=lambda a, t: {})
        nota = (self.bib.raiz / "licencas" / "kenney-falsa.txt").read_text(encoding="utf-8")
        self.assertEqual(len(nota.splitlines()), 1)

    def test_limite_e_palavras_compostas(self):
        self._arq("xicara grande calm.mp3")
        acervo.importar_pasta(self.bib, self.pasta, "sonoplastia", "cc0", "X", medir_arquivo=lambda a, t: {})
        self.assertEqual(len(acervo.buscar(self.bib, palavras=["xícara grande"])), 1)
        with self.assertRaises(acervo.ErroAcervo):
            acervo.buscar(self.bib, limite=0)

    def test_trilha_importada_serve_ao_produzir(self):
        self._arq("calm.mp3")
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "X", medir_arquivo=lambda a, t: {})
        self.assertEqual(len(self.bib.buscar(["trilha", "calmo"], tipo="audio")), 1)  # busca do trilha.py

    def test_resumo_para_agentes(self):
        self._arq("calm.mp3")
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "X",
                              medir_arquivo=lambda a, t: {"duracao_s": 30.0, "energia": 0.2})
        r = acervo.resumo(acervo.buscar(self.bib)[0])
        self.assertEqual((r["tipo"], r["clima"], r["licenca"], r["medidas"]["duracao_s"]),
                         ("trilha", "calmo", "cc0", 30.0))
        json.dumps(r)  # serializável


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestMedirDeVerdade(_ComBiblioteca):
    def test_audio_baixo_e_alto(self):
        baixo = acervo.medir(_som(self.pasta / "baixo.wav", volume=0.05), "ambiente")
        alto = acervo.medir(_som(self.pasta / "alto.wav", volume=5), "ambiente")
        self.assertAlmostEqual(baixo["duracao_s"], 4.0, delta=0.1)
        self.assertEqual(acervo.nivel_energia(baixo["energia"]), "baixa")
        self.assertEqual(acervo.nivel_energia(alto["energia"]), "alta")
        self.assertTrue(alto["loop"])  # tom contínuo: começo e fim no mesmo nível
        self.assertNotIn("bpm", alto)  # BPM só em trilha

    def test_trilha_tem_bpm_mesmo_que_vazio(self):
        m = acervo.medir(_som(self.pasta / "t.wav", dur=5, volume=0.3), "trilha")
        self.assertIn("bpm", m)  # tom contínuo não tem batida: None

    def test_silencio_nao_entra(self):
        _ff("-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3", str(self.pasta / "mudo.wav"))
        importados, problemas = acervo.importar_pasta(self.bib, self.pasta, "ambiente", "cc0", "X")
        self.assertEqual(importados, [])
        self.assertIn("silêncio", problemas[0])

    def test_imagem_vertical(self):
        m = acervo.medir(_imagem(self.pasta / "v.png", 108, 192), "imagem")
        self.assertEqual((m["largura"], m["altura"], m["orientacao"]), (108, 192, "vertical"))

    def test_efeito_importado_serve_para_a_montagem(self):
        _som(self.pasta / "whoosh.mp3", dur=0.5, volume=0.5)
        importados, problemas = acervo.importar_pasta(self.bib, self.pasta, "efeito", "pixabay", "Pixabay")
        self.assertEqual(problemas, [])
        escolhas = escolher_efeitos(self.bib, ["calmo", "calmo"])
        self.assertEqual(escolhas[1]["nome"], "whoosh")
        self.assertIn("tipo-efeito", importados[0]["tags"])

    def test_importar_sons_continua_igual(self):
        _som(self.pasta / "pop.mp3", dur=0.3)
        importados, _ = importar_sons(self.bib, self.pasta, "cc0", "X")
        self.assertEqual(len(importados), 1)
        self.assertEqual(acervo.buscar(self.bib), [])  # não tem as medidas nem o tipo do acervo


class TestComandos(_ComBiblioteca):
    def _rodar(self, *argv):
        from torralles_studio.__main__ import main
        saida, erro = io.StringIO(), io.StringIO()
        with mock.patch("torralles_studio.config.carregar_biblioteca", return_value=self.bib), \
                contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = main(list(argv))
        return codigo, saida.getvalue(), erro.getvalue()

    def test_buscar_em_json(self):
        (self.pasta / "calm.mp3").write_bytes(b"abc")
        acervo.importar_pasta(self.bib, self.pasta, "trilha", "cc0", "X",
                              medir_arquivo=lambda a, t: {"duracao_s": 30.0, "energia": 0.2})
        codigo, saida, _ = self._rodar("acervo", "buscar", "--tipo", "trilha", "--clima", "calmo", "--json")
        self.assertEqual(codigo, 0)
        itens = json.loads(saida)
        self.assertEqual(itens[0]["titulo"], "calm")
        self.assertTrue(Path(itens[0]["arquivo"]).is_file())

    def test_importar_com_licenca_bloqueada(self):
        codigo, _, erro = self._rodar("importar-acervo", str(self.pasta), "--tipo", "trilha",
                                      "--licenca", "cc-by-nc", "--fonte", "X")
        self.assertEqual(codigo, 1)
        self.assertIn("não permite uso comercial", erro)

    def test_importar_pasta_vazia(self):
        codigo, _, erro = self._rodar("importar-acervo", str(self.pasta), "--tipo", "efeito",
                                      "--licenca", "cc0", "--fonte", "X")
        self.assertEqual(codigo, 1)
        self.assertIn("nenhum arquivo de efeito", erro)


if __name__ == "__main__":
    unittest.main()

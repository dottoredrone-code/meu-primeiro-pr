import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from torralles_studio.config import CONFIG_PADRAO, carregar_roteador, validar_cadeias
from torralles_studio.funcoes import gerar_roteiro, pesquisar
from torralles_studio.provedores.base import Provedor
from torralles_studio.provedores.video import KenBurnsVideo
from torralles_studio.rede import ErroProvedor
from torralles_studio.roteador import Roteador, TodosFalharam


class Falso(Provedor):
    """Provedor de teste: devolve (ou lança) cada item de `respostas` em sequência."""

    def __init__(self, nome, respostas=(), tipo="texto", motivo=None):
        super().__init__(nome, {})
        self.tipo = tipo
        self.respostas = list(respostas)
        self.motivo = motivo
        self.chamadas = 0

    def configurado(self):
        return self.motivo

    def executar(self, **kwargs):
        self.chamadas += 1
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora


def roteador(*provedores, tarefa="t", relogio=None):
    return Roteador(
        {p.nome: p for p in provedores},
        {tarefa: [p.nome for p in provedores]},
        dormir=lambda s: None,
        relogio=relogio or Relogio(),
    )


class TestRoteador(unittest.TestCase):
    def test_usa_o_primeiro_que_funciona(self):
        a, b = Falso("a", ["A"]), Falso("b", ["B"])
        r = roteador(a, b).executar("t")
        self.assertEqual((r.valor, r.provedor), ("A", "a"))
        self.assertEqual(b.chamadas, 0)

    def test_pula_provedor_sem_chave(self):
        a, b = Falso("a", motivo="falta CHAVE"), Falso("b", ["B"])
        r = roteador(a, b).executar("t")
        self.assertEqual(r.provedor, "b")
        self.assertEqual(r.tentativas[0].status, "pulado")
        self.assertEqual(a.chamadas, 0)

    def test_erro_temporario_repete_antes_de_trocar(self):
        a = Falso("a", [ErroProvedor("503", status=503, temporario=True), "A"])
        r = roteador(a, Falso("b", ["B"])).executar("t")
        self.assertEqual((r.provedor, a.chamadas), ("a", 2))

    def test_erro_temporario_persistente_vai_para_o_proximo(self):
        erro = ErroProvedor("rede", temporario=True)
        a = Falso("a", [erro, erro])
        r = roteador(a, Falso("b", ["B"])).executar("t")
        self.assertEqual((r.provedor, a.chamadas), ("b", 2))

    def test_erro_definitivo_nao_repete(self):
        a = Falso("a", [ErroProvedor("400", status=400)])
        r = roteador(a, Falso("b", ["B"])).executar("t")
        self.assertEqual((r.provedor, a.chamadas), ("b", 1))

    def test_limite_429_coloca_em_descanso(self):
        relogio = Relogio()
        a = Falso("a", [ErroProvedor("429", status=429, temporario=True), "A"])
        b = Falso("b", ["B1", "B2"])
        rt = roteador(a, b, relogio=relogio)
        self.assertEqual(rt.executar("t").provedor, "b")
        self.assertEqual(a.chamadas, 1)  # 429 não repete no mesmo provedor
        self.assertEqual(rt.executar("t").provedor, "b")  # ainda em descanso
        relogio.agora = 61
        self.assertEqual(rt.executar("t").provedor, "a")  # descanso acabou

    def test_validacao_invalida_tenta_o_proximo(self):
        def validar(v):
            if v != "bom":
                raise ValueError("ruim")
            return v

        r = roteador(Falso("a", ["lixo"]), Falso("b", ["bom"])).executar("t", validar=validar)
        self.assertEqual(r.provedor, "b")

    def test_excecao_inesperada_nao_derruba_a_cadeia(self):
        r = roteador(Falso("a", [KeyError("choices")]), Falso("b", ["B"])).executar("t")
        self.assertEqual(r.provedor, "b")

    def test_todos_falharam_lista_os_motivos(self):
        rt = roteador(Falso("a", motivo="falta X"), Falso("b", [ErroProvedor("400", status=400)]))
        with self.assertRaises(TodosFalharam) as ctx:
            rt.executar("t")
        self.assertIn("falta X", str(ctx.exception))
        self.assertEqual(len(ctx.exception.tentativas), 2)


class TestFuncoes(unittest.TestCase):
    def test_roteiro_cai_para_o_proximo_quando_json_e_invalido(self):
        bom = '```json\n{"titulo": "Café", "cenas": [{"narracao": "Oi", "prompt_imagem": "coffee"}]}\n```'
        r = gerar_roteiro(roteador(Falso("a", ["não sei"]), Falso("b", [bom]), tarefa="roteiro"), "café")
        self.assertEqual((r.provedor, r.valor["titulo"]), ("b", "Café"))

    def test_pesquisa_sem_busca_ainda_responde(self):
        rt = Roteador(
            {"busca": Falso("busca", tipo="busca", motivo="falta chave"), "llm": Falso("llm", ["resumo"])},
            {"busca": ["busca"], "pesquisa": ["llm"]},
        )
        r = pesquisar(rt, "café")
        self.assertEqual(r.valor, {"resumo": "resumo", "fontes": []})


class TestConfig(unittest.TestCase):
    def test_config_padrao_e_valida(self):
        rt = carregar_roteador(CONFIG_PADRAO)
        for tarefa in ("ideias", "roteiro", "pesquisa", "busca", "imagem", "voz", "video"):
            self.assertIn(tarefa, rt.cadeias)
        self.assertEqual(rt.tipo_da_tarefa("video"), "video")

    def test_rejeita_cadeia_com_tipos_misturados(self):
        provs = {"t": Falso("t"), "i": Falso("i", tipo="imagem")}
        with self.assertRaises(ValueError):
            validar_cadeias(provs, {"x": ["t", "i"]})


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestKenBurns(unittest.TestCase):
    def test_gera_video_a_partir_de_imagem(self):
        with tempfile.TemporaryDirectory() as d:
            img, saida = Path(d) / "img.png", Path(d) / "out.mp4"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=800x600", "-frames:v", "1", str(img)],
                check=True,
            )
            KenBurnsVideo("kb", {"largura": 320, "altura": 180}).executar(img, "", saida, duracao=1)
            self.assertGreater(saida.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()

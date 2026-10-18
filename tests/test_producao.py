import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from torralles_studio.config import carregar_config
from torralles_studio.loop import LoopCorrecao
from torralles_studio.producao import ErroProducao, pasta_do_tema, prompt_da_imagem, produzir_video
from torralles_studio.provedores.base import Provedor
from torralles_studio.provedores.video import KenBurnsVideo
from torralles_studio.qualidade import Avaliador
from torralles_studio.roteador import Roteador
from torralles_studio.seguranca import Orcamento

ROTEIRO = {
    "titulo": "Chá verde", "cta": "Siga para mais.",
    "cenas": [
        {"narracao": "Chá verde tem antioxidantes.", "duracao": 4, "prompt_imagem": "cup of green tea",
         "prompt_movimento": "slow zoom in", "clima": "curioso", "sons": [], "texto_tela": "Antioxidantes"},
        {"narracao": "Siga para mais curiosidades.", "duracao": 4, "prompt_imagem": "tea field",
         "prompt_movimento": "pan right", "clima": "alegre", "sons": [], "texto_tela": "Siga!"},
    ],
}
CRITERIOS = ["gancho", "precisao", "aderencia", "clareza", "ritmo", "cta"]


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


class Texto(Provedor):
    tipo = "texto"

    def __init__(self, nome, respostas, familia):
        super().__init__(nome, {"familia": familia, "custo_usd": 0.01, "modelo": nome})
        self.respostas, self.pedidos = list(respostas), []

    def configurado(self):
        return None

    def executar(self, **kw):
        self.pedidos.append(kw)
        return self.respostas.pop(0)


class Imagem(Provedor):
    tipo = "imagem"

    def __init__(self):
        super().__init__("img", {"custo_usd": 0.06})
        self.pedidos = []

    def configurado(self):
        return None

    def executar(self, prompt, saida, proporcao=None):
        self.pedidos.append({"prompt": prompt, "proporcao": proporcao})
        _ff("-f", "lavfi", "-i", "testsrc=size=540x960", "-frames:v", "1", str(saida))
        return Path(saida)


class Voz(Provedor):
    tipo = "voz"

    def __init__(self):
        super().__init__("voz", {})
        self.chamadas = 0

    def configurado(self):
        return None

    def executar(self, texto, saida):
        self.chamadas += 1
        _ff("-f", "lavfi", "-i", "sine=f=300:d=1.4", "-af", "adelay=200,apad=pad_dur=0.3", str(saida))
        return Path(saida)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestProduzirVideo(unittest.TestCase):
    def montar(self, roteiros=None):
        juiz = json.dumps({"criterios": {c: {"evidencia": "ok", "nota": 85} for c in CRITERIOS}, "problemas": []})
        self.redator = Texto("redator", roteiros or [json.dumps(ROTEIRO)], "deepseek")
        self.juiz = Texto("juiz", [juiz] * 3, "anthropic")
        self.img, self.voz = Imagem(), Voz()
        provs = {"redator": self.redator, "juiz": self.juiz, "img": self.img, "voz": self.voz,
                 "ken_burns": KenBurnsVideo("ken_burns", {"fps": 25})}
        cadeias = {"roteiro": ["redator"], "juiz": ["juiz"], "imagem": ["img"], "voz": ["voz"], "video": ["ken_burns"]}
        rt = Roteador(provs, cadeias, dormir=lambda s: None, orcamento=Orcamento(1.5))
        return rt, LoopCorrecao(rt, Avaliador(rt, carregar_config()["avaliacao"]))

    def test_tema_vira_video_e_rodar_de_novo_nao_refaz(self):
        rt, loop = self.montar()
        with tempfile.TemporaryDirectory() as d:
            rel = produzir_video(rt, loop, "chá verde", Path(d) / "v", duracao=8, cfg_montagem={"preset": "ultrafast"})
            self.assertTrue(Path(rel["video"]).is_file())
            self.assertEqual(rel["medidas"]["resolucao"], "1080x1920")
            self.assertEqual(self.voz.chamadas, 2)
            self.assertEqual([p["proporcao"] for p in self.img.pedidos], ["9:16", "9:16"])
            self.assertIn("sem nenhum texto", self.img.pedidos[0]["prompt"])
            roteiro = next(e for e in rel["etapas"] if e["etapa"] == "roteiro")
            self.assertEqual((roteiro["provedor"], roteiro["nota"]), ("redator", 85))
            self.assertGreater(rel["custo_usd"], 0)
            self.assertTrue((Path(d) / "v" / "relatorio.json").is_file())

            rt2, loop2 = self.montar(roteiros=[])  # sem respostas: se tentar gerar de novo, quebra
            rel2 = produzir_video(rt2, loop2, "chá verde", Path(d) / "v", duracao=8,
                                  cfg_montagem={"preset": "ultrafast"})
            self.assertEqual(self.voz.chamadas, 0)
            self.assertEqual(self.img.pedidos, [])
            self.assertTrue(all(e["reaproveitado"] for e in rel2["etapas"]))
            self.assertEqual(rel2["custo_usd"], 0)

    def test_roteiro_que_nao_sai_para_com_mensagem(self):
        rt, loop = self.montar(roteiros=["não é JSON"] * 4)
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ErroProducao):
            produzir_video(rt, loop, "chá verde", Path(d) / "v", duracao=8)


class TestAjudantes(unittest.TestCase):
    def test_pasta_do_tema(self):
        self.assertEqual(pasta_do_tema("Benefícios do Chá Verde!"), Path("saidas") / "beneficios-do-cha-verde")

    def test_prompt_pede_formato_e_nenhum_texto(self):
        p = prompt_da_imagem({"prompt_imagem": "xícara de chá"}, "9:16")
        self.assertIn("vertical 9:16", p)
        self.assertIn("sem nenhum texto", p)


if __name__ == "__main__":
    unittest.main()

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from torralles_studio import benchmark as bm


def _video(caminho, tamanho="1080x1920", dur=30, som=True):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=blue:s={tamanho}:r=5:d={dur}"]
    if som:
        cmd += ["-f", "lavfi", "-i", f"sine=f=300:d={dur}", "-af", "volume=7.8dB", "-shortest"]
    subprocess.run(cmd + ["-pix_fmt", "yuv420p", "-preset", "ultrafast", str(caminho)], check=True)
    return caminho


def _avaliacao(nota):
    return SimpleNamespace(nota=nota, aprovado=nota is not None and nota >= 70, sem_juiz=nota is None,
                           juizes=["gemini_video"] if nota is not None else [], criterios={},
                           problemas=[] if nota is not None else ["nenhum juiz disponível"])


class TestDados(unittest.TestCase):
    def test_nome_da_ferramenta(self):
        self.assertEqual(bm.nome_ferramenta("Google Flow"), "google-flow")
        self.assertEqual(bm.nome_ferramenta("InVídeo AI!"), "invideo-ai")
        self.assertEqual(bm.nome_ferramenta("../x"), "x")
        with self.assertRaises(ValueError):
            bm.nome_ferramenta("!!!")

    def test_registrar_e_completar(self):
        with tempfile.TemporaryDirectory() as d:
            arq = bm.registrar_dados(d, "a", "CapCut", {"tempo_min": 12, "custo_usd": 0}, "travou | uma vez")
            bm.registrar_dados(d, "A", "capcut", {"nota_diego": 7.5})
            self.assertEqual(arq, Path(d) / "A" / "capcut.json")
            self.assertEqual(json.loads(arq.read_text(encoding="utf-8")),
                             {"tempo_min": 12.0, "custo_usd": 0.0, "observacoes": "travou | uma vez", "nota_diego": 7.5,
                              "anotado_a_mao": ["custo_usd", "nota_diego", "tempo_min"]})
            for briefing, valores in (("D", {"tempo_min": 1}), ("A", {}), ("A", {"nota_diego": 11}),
                                      ("A", {"tempo_min": float("nan")}), ("A", {"tentativas": True}),
                                      ("A", {"inventado": 1})):
                with self.assertRaises(ValueError):
                    bm.registrar_dados(d, briefing, "capcut", valores)

    def test_inteiros_onde_precisa(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                bm.registrar_dados(d, "A", "capcut", {"intervencoes": 2.5})
            bm.registrar_dados(d, "A", "capcut", {"intervencoes": 2})

    def test_execucoes_do_studio_se_somam(self):  # verificador: retomar não pode zerar o que foi gasto
        with tempfile.TemporaryDirectory() as d:
            origem = Path(d) / "final.mp4"
            origem.write_bytes(b"x")
            pasta = Path(d) / "bm"
            bm.registrar_execucao(pasta, "B", custo_usd=0.9, tempo_s=600)  # 1ª: parou no meio
            rel = {"video": str(origem), "tempo_s": 120, "custo_usd": 0.3, "aprovado": True,
                   "etapas": [{"etapa": "roteiro", "tentativas": 3}, {"etapa": "voz", "reaproveitado": True}]}
            destino = bm.registrar_execucao(pasta, "B", custo_usd=0.3, tempo_s=120,
                                            tentativas=bm.tentativas_do_relatorio(rel), relatorio=rel)
            self.assertEqual(destino.name, "torralles-studio.mp4")
            self.assertTrue(destino.is_file())
            dados = json.loads(destino.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual((dados["custo_usd"], dados["tempo_min"], dados["tentativas"], dados["intervencoes"]),
                             (1.2, 12.0, 3.0, 1.0))  # a retomada contou como intervenção
            self.assertFalse(dados["acima_do_teto"])
            bm.registrar_dados(pasta, "B", "torralles-studio", {"intervencoes": 0, "nota_diego": 8})
            bm.registrar_execucao(pasta, "B", custo_usd=0.4, tempo_s=60, relatorio=rel)
            dados = json.loads(destino.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(dados["intervencoes"], 0.0)  # o que você anotou fica
            # roteiro feito numa execução que parou: as tentativas vêm do roteiro.json reaproveitado
            reuso = {"video": str(origem), "etapas": [{"etapa": "roteiro", "reaproveitado": True, "tentativas": 3}]}
            bm.registrar_execucao(pasta, "C", custo_usd=0.5, tempo_s=60)
            bm.registrar_execucao(pasta, "C", custo_usd=0, tempo_s=30, tentativas=bm.tentativas_do_relatorio(reuso),
                                  relatorio=reuso)
            c = json.loads((pasta / "C" / "torralles-studio.json").read_text(encoding="utf-8"))
            self.assertEqual((c["tentativas"], c["intervencoes"], c["aprovado_pelo_studio"]), (3.0, 1.0, False))
            self.assertEqual(dados["nota_diego"], 8.0)
            self.assertEqual(dados["custo_usd"], 1.6)
            self.assertTrue(dados["acima_do_teto"])

    def test_listar_ignora_ocultos_e_avisa_duplicados(self):
        with tempfile.TemporaryDirectory() as d:
            for nome in ("._capcut.mp4", "capcut.mp4", "Google Flow.mp4", "google-flow.webm", "notas.txt"):
                (Path(d) / "A").mkdir(exist_ok=True)
                (Path(d) / "A" / nome).write_bytes(b"x")
            avisos = []
            achados = bm.listar_videos(d, aviso=avisos.append)
            self.assertEqual([(f, v.name) for _, f, v in achados], [("capcut", "capcut.mp4"),
                                                                     ("google-flow", "Google Flow.mp4")])
            self.assertEqual(len(avisos), 1)
            self.assertIn("google-flow.webm", avisos[0])


class TestRelatorio(unittest.TestCase):
    def test_ranking_e_markdown(self):
        resultados = [
            {"briefing": "A", "ferramenta": "torralles-studio", "nota_juiz": 82, "medidas": {"duracao_s": 30},
             "problemas": [], "manual": {"custo_usd": 0.05, "tempo_min": 5, "nota_diego": 7}},
            {"briefing": "B", "ferramenta": "torralles-studio", "nota_juiz": 78, "problemas": [],
             "manual": {"custo_usd": 0.04}},
            {"briefing": "A", "ferramenta": "capcut", "nota_juiz": 85, "problemas": ["volume -20 LUFS"],
             "manual": {"intervencoes": 6, "observacoes": "editei | à mão\nduas vezes"}},
            {"briefing": "A", "ferramenta": "canva", "nota_juiz": None, "sem_juiz": True, "problemas_juiz": ["x"],
             "problemas": [], "manual": {}},
        ]
        r = bm.ranking(resultados)
        self.assertEqual([x["ferramenta"] for x in r], ["capcut", "torralles-studio", "canva"])
        estudio = r[1]
        self.assertEqual((estudio["nota_juiz"], estudio["custo_usd"], estudio["videos"]), (80.0, 0.09, 2))
        md = bm.relatorio_markdown(resultados)
        self.assertIn("| capcut | A | 85 |", md)
        self.assertIn("| torralles-studio | AB | 80 |", md)
        self.assertIn("história do café no Brasil", md)
        self.assertIn("editei / à mão duas vezes", md)  # barra vertical e quebra de linha não quebram a tabela
        self.assertIn("D15", md)  # exceção do juiz da mesma família explicada no relatório
        self.assertNotIn("Briefing C", md)
        self.assertIn("Nenhum vídeo", bm.relatorio_markdown([]))


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestAvaliar(unittest.TestCase):
    def test_mesma_regua_para_todos(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            _video(pasta / "A" / "torralles-studio.mp4", dur=4)
            _video(pasta / "A" / "CapCut.mov", tamanho="720x720", dur=4, som=False)
            (pasta / "A" / "capcut.json").write_text('{"nota_diego": 6}', encoding="utf-8")
            (pasta / "B" / "lixo.mp4").parent.mkdir()
            (pasta / "B" / "lixo.mp4").write_bytes(b"isso nao e video")
            (pasta / "A" / "_studio").mkdir()  # pasta de trabalho do Studio não entra
            criados, chamadas = [], []

            def novo():
                criados.append(1)
                return object()

            def avaliar(avaliador, video, contexto=None, percepcao=None):
                chamadas.append((Path(video).name, contexto))
                if Path(video).name == "lixo.mp4":
                    raise RuntimeError("chave sk-abcdefghijklmnopqrstuvwx inválida")
                return _avaliacao(80)

            res = bm.avaliar_benchmark(pasta, novo, checar=lambda v: bm.checar_video(v, duracao_alvo=4),
                                       avaliar=avaliar)
            self.assertEqual(len(criados), 2)  # um avaliador (e um teto) por briefing
            por = {(r["briefing"], r["ferramenta"]): r for r in res}
            self.assertEqual(set(por), {("A", "capcut"), ("A", "torralles-studio"), ("B", "lixo")})
            self.assertEqual(por[("A", "torralles-studio")]["problemas"], [])
            capcut = por[("A", "capcut")]
            self.assertTrue(any("resolução 720x720" in p for p in capcut["problemas"]))
            self.assertTrue(any("sem áudio" in p for p in capcut["problemas"]))
            self.assertEqual(capcut["manual"], {"nota_diego": 6})
            lixo = por[("B", "lixo")]
            self.assertTrue(lixo["sem_juiz"])
            self.assertNotIn("abcdefghijklmnop", json.dumps(lixo))  # erro mascarado
            self.assertTrue(all("história do café" in c for n, c in chamadas if n != "lixo.mp4"))
            self.assertTrue((pasta / "resultados.json").is_file())
            self.assertNotIn(str(pasta), json.dumps(res))  # sem caminho do PC no relatório

            antes = len(chamadas)  # 2ª rodada: vídeos já julgados não pagam de novo
            (pasta / "A" / "capcut.json").write_text('{"nota_diego": 9}', encoding="utf-8")
            res2 = bm.avaliar_benchmark(pasta, novo, checar=lambda v: bm.checar_video(v, duracao_alvo=4),
                                        avaliar=avaliar)
            self.assertEqual(len(chamadas) - antes, 1)  # só o que ficou sem nota (lixo)
            self.assertEqual({(r["ferramenta"], r["manual"].get("nota_diego")) for r in res2
                              if r["briefing"] == "A"}, {("capcut", 9), ("torralles-studio", None)})
            bm.avaliar_benchmark(pasta, novo, checar=lambda v: bm.checar_video(v, duracao_alvo=4),
                                 avaliar=avaliar, refazer=True)
            self.assertEqual(len(chamadas) - antes, 4)

    def test_checagens_de_rotacao_formato_e_so_audio(self):
        with tempfile.TemporaryDirectory() as d:
            deitado = Path(d) / "celular.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-display_rotation", "90", "-i",
                            str(_video(Path(d) / "base.mp4", tamanho="1920x1080", dur=2)), "-c", "copy",
                            str(deitado)], check=True)
            r = bm.checar_video(deitado, duracao_alvo=2)
            self.assertEqual(r["medidas"]["resolucao"], "1080x1920")  # rotação do celular respeitada
            self.assertFalse(any("resolução" in p for p in r["problemas"]))
            audio = Path(d) / "so_audio.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=d=2", "-c:a", "aac",
                            str(audio)], check=True)
            self.assertEqual(bm.checar_video(audio)["problemas"], ["o arquivo não tem imagem (só áudio)"])
            mudo = _video(Path(d) / "mudo.mp4", dur=2, som=False)
            probs = bm.checar_video(mudo, duracao_alvo=2)["problemas"]
            self.assertEqual(probs, ["sem áudio medível"])  # sem áudio não vira também "formato"
            webm = Path(d) / "x.webm"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=s=1080x1920:d=2:r=5",
                            "-f", "lavfi", "-i", "sine=d=2", "-shortest", str(webm)], check=True)
            self.assertTrue(any("formato" in p for p in bm.checar_video(webm, duracao_alvo=2)["problemas"]))

    def test_cli_dados_e_avaliar_sem_videos(self):
        from torralles_studio.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["benchmark", "dados", "C", "canva", "--nota", "8", "--pasta", d]), 0)
            self.assertEqual(main(["benchmark", "dados", "C", "canva", "--nota", "80", "--pasta", d]), 1)
            self.assertEqual(main(["benchmark", "avaliar", "--pasta", d]), 1)
            self.assertFalse((Path(d) / "resultados.json").exists())


if __name__ == "__main__":
    unittest.main()

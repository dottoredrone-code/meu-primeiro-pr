import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from torralles_studio.montagem import (
    ErroMontagem, alinhar_ao_tempo, checar_legendas, distribuir_legendas, estilo_legenda, gerar_ass, gerar_srt,
    montar, planejar_tempos, quebrar_texto, verificar_montagem,
)


class TestTempos(unittest.TestCase):
    def test_cena_acompanha_a_fala(self):
        t = planejar_tempos([2.0, 3.0])
        self.assertEqual([x["duracao"] for x in t], [2.55, 3.55])  # 0,2 antes + fala + 0,35 depois
        self.assertEqual(t[1]["inicio"], 2.55)

    def test_roteiro_mais_longo_so_cresce_um_pouco(self):  # evita os silêncios longos do teste local
        t = planejar_tempos([2.0], [5])
        self.assertEqual(t[0]["duracao"], 2.85)

    def test_cena_sem_fala_usa_o_roteiro_e_o_minimo(self):
        t = planejar_tempos([0, None], [3, None])
        self.assertEqual([x["duracao"] for x in t], [3.0, 1.5])

    def test_corte_na_batida_sem_cortar_a_fala(self):
        t = alinhar_ao_tempo(planejar_tempos([2.0, 2.0, 2.0]), bpm=120)  # batida a cada 0,5 s
        for x in t[:-1]:
            fim = x["inicio"] + x["duracao"]
            self.assertAlmostEqual(fim * 2, round(fim * 2), places=6)  # caiu na batida
            self.assertGreaterEqual(x["duracao"], x["fala_em"] + x["fala_s"] + 0.1)
        self.assertEqual(sum(1 for x in t if x.get("na_batida")), 2)

    def test_completa_ate_a_duracao_pedida(self):
        from torralles_studio.montagem import completar_duracao

        t = completar_duracao(planejar_tempos([2.0, 2.0, 2.0]), 10)  # 7,65 s → falta 2,35 s
        self.assertEqual(t[-1]["duracao"], 2.55 + 1.5)
        self.assertEqual([x["duracao"] for x in t[:-1]], [2.85, 2.85])
        self.assertEqual(t[2]["inicio"], 5.7)
        self.assertEqual(completar_duracao(planejar_tempos([2.0]), 2.6)[0]["duracao"], 2.55)  # já dentro de 10%

    def test_batida_longe_demais_nao_move(self):
        t = alinhar_ao_tempo(planejar_tempos([2.0, 2.0]), bpm=30, cfg={"max_ajuste_batida_s": 0.1})
        self.assertEqual(t[0]["duracao"], 2.55)
        self.assertNotIn("na_batida", t[0])


class TestLegendas(unittest.TestCase):
    def test_quebra_em_ate_duas_linhas(self):
        blocos = quebrar_texto("A luz do Sol parece branca, mas mistura todas as cores do arco-íris inteiro.", 28)
        for b in blocos:
            self.assertLessEqual(len(b), 2)
            self.assertTrue(all(len(linha) <= 28 for linha in b))
        self.assertEqual(" ".join(" ".join(b) for b in blocos),
                         "A luz do Sol parece branca, mas mistura todas as cores do arco-íris inteiro.")

    def test_frase_nova_comeca_bloco_novo(self):
        self.assertEqual(quebrar_texto("Olá, pessoal. Tudo bem com vocês?", 14),
                         [["Olá, pessoal."], ["Tudo bem com", "vocês?"]])
        self.assertEqual(quebrar_texto("Gostou? Siga para mais curiosidades.", 28),  # frase curta segue junto
                         [["Gostou? Siga para mais", "curiosidades."]])

    def test_palavra_solta_nao_fica_sozinha(self):  # visto no vídeo do chá verde: "hábitos." sozinho
        blocos = quebrar_texto("Mas não faz milagre: funciona junto com bons hábitos.", 28)
        self.assertEqual(blocos, [["Mas não faz milagre:"], ["funciona junto com bons", "hábitos."]])

    def test_bloco_curto_demais_junta_com_o_vizinho(self):
        legendas = distribuir_legendas("Primeira frase bem comprida aqui. Fim.", 0.0, 2.2, max_chars=20)
        self.assertEqual(len(legendas), 1)
        self.assertEqual(checar_legendas(legendas, 20), [])

    def test_fala_rapida_divide_o_tempo_entre_blocos(self):  # chá verde: "O que uma xícara de chá" a 17,9 car./s
        legendas = distribuir_legendas("O que uma xícara de chá verde pode fazer pelo seu corpo?", 0.2, 3.22,
                                       max_chars=28, fim_cena=4.1)
        self.assertEqual(len(legendas), 2)
        self.assertEqual(checar_legendas(legendas, 28), [])
        self.assertEqual(legendas[0][1], legendas[1][0])

    def test_fala_rapida_no_fim_junta_ou_estica(self):  # chá verde: legendas 5 e 10
        for texto, fim in [("Pode auxiliar no metabolismo e na perda de peso — mas não é solução mágica.", 4.6),
                           ("Consuma com moderação e converse com um profissional.", 3.2)]:
            legendas = distribuir_legendas(texto, 0.2, fim, max_chars=28, fim_cena=fim + 0.9)
            self.assertEqual(checar_legendas(legendas, 28), [], texto)

    def test_fronteira_de_pausa_so_anda_para_depois_dela(self):  # chá verde: "— mas não" a 19,9 car./s
        texto = "Pode auxiliar no metabolismo e na perda de peso — mas não é solução mágica."
        legendas = distribuir_legendas(texto, 0.0, 4.6, [(2.5, 3.0)], max_chars=28, fim_cena=5.5)
        self.assertEqual(checar_legendas(legendas, 28), [])
        self.assertGreaterEqual(legendas[1][0], 2.9)  # nunca entra dentro da pausa

    def test_corte_vai_para_a_pausa_real(self):
        texto = "Primeira parte da frase aqui, segunda parte da frase ali."
        legendas = distribuir_legendas(texto, 1.0, 5.0, [(3.4, 3.7)], max_chars=16)
        self.assertEqual(len(legendas), 2)
        self.assertAlmostEqual(legendas[0][1], 3.6)   # sai quando a seguinte entra (pausa curta)
        self.assertAlmostEqual(legendas[1][0], 3.6)   # entra quando a fala volta (0,1 s antes)
        self.assertEqual(legendas[0][0], 1.0)

    def test_pausa_curta_nao_sobrepoe_legendas(self):  # verificador, 2ª rodada
        legendas = distribuir_legendas("Primeira frase completa. Segunda frase completa.", 0.2, 3.5,
                                       [(1.7, 2.0)], 28, 3.85)
        self.assertEqual(len(legendas), 2)
        self.assertLessEqual(legendas[0][1], legendas[1][0])
        self.assertEqual(checar_legendas(legendas, 28), [])

    def test_frase_curta_fica_ao_menos_1_s(self):  # verificador: "Sim, claro." ficava 0,9 s
        legendas = distribuir_legendas("Sim, claro.", 0.2, 0.7, fim_cena=1.5, max_chars=28)
        self.assertEqual(legendas, [(0.2, 1.2, ["Sim, claro."])])
        self.assertEqual(checar_legendas(legendas), [])

    def test_texto_na_tela_quebra_linhas(self):
        from torralles_studio.montagem import linhas_tela

        linhas = linhas_tela("Um texto na tela bem mais comprido que o normal", "9:16")
        self.assertGreater(len(linhas), 1)
        self.assertTrue(all(len(linha) <= 24 for linha in linhas))

    def test_checa_legibilidade(self):
        ruins = [(0.0, 0.5, ["curta demais"]), (0.4, 2.0, ["a" * 50]), (2.0, 3.0, ["um", "dois", "tres"]),
                 (3.0, 4.0, ["texto longo demais para um segundo"])]
        problemas = " | ".join(checar_legendas(ruins))
        for trecho in ("só 0.50 s", "50 caracteres", "3 linhas", "caracteres/s", "antes da anterior"):
            self.assertIn(trecho, problemas)
        self.assertEqual(checar_legendas([(0.0, 2.0, ["Tudo certo aqui"])]), [])

    def test_area_segura_no_vertical(self):
        e = estilo_legenda(1080, 1920, "9:16")
        base, topo = 1920 - e["margem_baixo"], 1920 - e["margem_baixo"] - 2 * e["tamanho"] * 1.25
        self.assertLessEqual(base, 1920 * 0.8)
        self.assertGreaterEqual(topo, 1920 * 0.1)
        self.assertGreaterEqual(e["margem_cima"], 192)
        self.assertLessEqual(e["max_chars"], 42)

    def test_karaoke_acende_cada_palavra_no_tempo_do_bloco(self):
        from torralles_studio.montagem import transicao_da_cena

        ass = gerar_ass([(0.0, 2.0, ["Chá verde tem", "antioxidantes."])], [], 1080, 1920, "9:16", karaoke=True)
        linha = ass.strip().splitlines()[-1]
        tempos = [int(x) for x in __import__("re").findall(r"\\k(\d+)", linha)]
        self.assertEqual(len(tempos), 4)
        self.assertEqual(sum(tempos), 170)  # 85% de 2 s: a última palavra acende antes do bloco sair
        self.assertIn("\\N{\\k", linha)  # a segunda linha também acende palavra por palavra
        self.assertEqual(transicao_da_cena("Curioso"), "slideleft")
        self.assertEqual(transicao_da_cena("desconhecido"), "fade")

    def test_ass_sem_comandos_injetados_e_srt(self):
        ass = gerar_ass([(0, 1.5, ["{\\b1}oi\\N", "tudo"])], [], 1080, 1920, "9:16")
        ultima = ass.strip().splitlines()[-1]
        self.assertTrue(ultima.endswith("(/b1)oi/N\\Ntudo"))
        self.assertEqual(gerar_srt([(1.0, 2.5, ["oi", "tudo"])]), "1\n00:00:01,000 --> 00:00:02,500\noi\ntudo\n")


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class TestMontagem(unittest.TestCase):
    RAPIDO = {"preset": "ultrafast"}

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)

    def tearDown(self):
        self._d.cleanup()

    def voz(self, nome, fala_s, pausa_inicio=0.3):
        """Voz sintética: silêncio, tom (a "fala") e silêncio no fim."""
        arq = self.d / nome
        _ff("-f", "lavfi", "-i", f"sine=f=300:d={fala_s}", "-af",
            f"adelay={int(pausa_inicio * 1000)},apad=pad_dur=0.4,volume=-8dB", "-ar", "48000", str(arq))
        return arq

    def clipe(self, nome, dur, tamanho="320x240"):
        arq = self.d / nome
        _ff("-f", "lavfi", "-i", f"testsrc=size={tamanho}:rate=25:d={dur}", "-pix_fmt", "yuv420p", str(arq))
        return arq

    def test_video_final_passa_nos_eliminatorios(self):
        trilha = self.d / "trilha.wav"
        _ff("-f", "lavfi", "-i", "sine=f=110:d=2", "-ar", "48000", str(trilha))  # curta: precisa repetir
        cenas = [
            {"video": self.clipe("a.mp4", 1.0), "voz": self.voz("v1.wav", 1.6), "narracao": "Primeira cena curta.",
             "texto_tela": "Olá", "duracao": 4},
            {"video": self.clipe("b.mp4", 3.0, "640x360"), "voz": self.voz("v2.wav", 1.8),
             "narracao": "Segunda cena com fala."},
        ]
        r = montar(cenas, self.d / "final.mp4", proporcao="9:16", trilha=trilha, bpm=120, cfg=self.RAPIDO,
                   pasta_trabalho=self.d / "trabalho")
        v = verificar_montagem(r, duracao_pedida=5)
        self.assertEqual(v["problemas"], [])
        self.assertEqual(v["medidas"]["resolucao"], "1080x1920")
        self.assertLessEqual(abs(v["medidas"]["lufs"] + 14), 1)
        self.assertLessEqual(v["medidas"]["pico_dbtp"], -1)
        self.assertTrue(10 <= r["trilha"]["voz_menos_trilha_lu"] <= 13.5, r["trilha"])
        self.assertLessEqual(v["medidas"]["sincronia_max_s"], 0.3)
        self.assertEqual(r["cortes_na_batida"], 1)
        self.assertGreater(r["congelado_s"][0], 0)  # clipe de 1 s esticado: fica registrado
        for arq in ("legendas.ass", "legendas.srt", "voz.wav", "trilha.wav", "clipe_01.mp4"):
            self.assertTrue((self.d / "trabalho" / arq).is_file(), arq)
        self.assertEqual(r["legendas"][0]["inicio"], 0.2)  # começa junto com a fala

    def test_verificacao_reprova_volume_e_resolucao(self):
        cenas = [{"video": self.clipe("a.mp4", 2), "voz": self.voz("v1.wav", 1.5), "narracao": "Teste."}]
        r = montar(cenas, self.d / "f.mp4", tamanho=(320, 568), cfg={**self.RAPIDO, "lufs": -24},
                   pasta_trabalho=self.d / "t")
        problemas = " | ".join(verificar_montagem(r, duracao_pedida=10)["problemas"])
        self.assertIn("resolução 320x568", problemas)
        self.assertIn("volume", problemas)
        self.assertIn("duração", problemas)

    def test_imagem_sem_voz_e_sem_trilha(self):
        img = self.d / "img.png"
        _ff("-f", "lavfi", "-i", "testsrc=size=400x300", "-frames:v", "1", str(img))
        r = montar([{"video": img, "duracao": 1.5}], self.d / "f.mp4", tamanho=(180, 320), cfg=self.RAPIDO)
        self.assertAlmostEqual(r["duracao_s"], 1.5)
        self.assertEqual(r["legendas"], [])
        self.assertTrue(Path(r["arquivo"]).is_file())

    def test_sincronia_reprova_legenda_fora_da_fala(self):
        cenas = [{"video": self.clipe("a.mp4", 3), "voz": self.voz("v1.wav", 1.5), "narracao": "Teste de fala."}]
        r = montar(cenas, self.d / "f.mp4", tamanho=(180, 320), cfg=self.RAPIDO, pasta_trabalho=self.d / "t")
        r["legendas"][0]["inicio"] -= 0.15  # legenda antes da fala, ainda dentro da tolerância
        self.assertNotIn("longe da fala", " ".join(verificar_montagem(r)["problemas"]))
        r["legendas"][0]["inicio"] = 1.9  # aparece depois que a fala acabou
        self.assertIn("longe da fala", " ".join(verificar_montagem(r)["problemas"]))

    def voz_com_pausa(self, nome, silencio_inicio, fala1, pausa, fala2, volume_db=-8):
        arq = self.d / nome
        _ff("-f", "lavfi", "-i", f"sine=f=300:d={fala1}", "-f", "lavfi", "-i", f"sine=f=300:d={fala2}",
            "-filter_complex", f"[0:a]adelay={int(silencio_inicio * 1000)},apad=pad_dur={pausa}[a];"
                               f"[a][1:a]concat=n=2:v=0:a=1,apad=pad_dur=0.4,volume={volume_db}dB",
            "-ar", "48000", str(arq))
        return arq

    def test_silencio_no_comeco_da_voz_e_pausa_entre_frases(self):  # verificador: itens 1 e 3
        cenas = [
            {"video": self.clipe("a.mp4", 4), "voz": self.voz_com_pausa("v1.wav", 1.0, 1.5, 0.8, 1.5),
             "narracao": "Primeira frase completa. Segunda frase completa."},
            {"video": self.clipe("b.mp4", 3), "voz": self.voz("v2.wav", 2.0, pausa_inicio=0.5),
             "narracao": "Terceira frase depois."},
        ]
        r = montar(cenas, self.d / "f.mp4", cfg=self.RAPIDO, pasta_trabalho=self.d / "t")
        v = verificar_montagem(r)
        self.assertEqual(v["problemas"], [])
        self.assertLessEqual(v["medidas"]["sincronia_max_s"], 0.3)
        self.assertEqual(len(r["legendas"]), 3)
        self.assertEqual(r["legendas"][0]["inicio"], 0.2)  # o silêncio de 1 s do arquivo foi cortado
        self.assertAlmostEqual(r["tempos"][0]["duracao"], 0.2 + 3.8 + 0.35, places=1)

    def test_voz_baixa_ainda_conta_como_fala(self):  # verificador: item 7 (pico perto de −48 dBFS)
        cenas = [{"video": self.clipe("a.mp4", 2), "voz": self.voz("forte.wav", 1.5), "narracao": "Fala forte."},
                 {"video": self.clipe("b.mp4", 2), "voz": self.voz_com_pausa("baixa.wav", 0.3, 1.5, 0.1, 0.1, -30),
                  "narracao": "Fala bem baixa."}]
        r = montar(cenas, self.d / "f.mp4", tamanho=(180, 320), cfg=self.RAPIDO, pasta_trabalho=self.d / "t")
        self.assertEqual(len(r["legendas"]), 2)
        self.assertNotIn("longe da fala", " ".join(verificar_montagem(r)["problemas"]))

    def test_voz_muda_com_narracao_e_erro(self):
        muda = self.d / "muda.wav"
        _ff("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "1", str(muda))
        with self.assertRaises(ErroMontagem):
            montar([{"video": self.clipe("a.mp4", 1), "voz": muda, "narracao": "Oi."}], self.d / "f.mp4",
                   tamanho=(180, 320), cfg=self.RAPIDO)

    def test_sem_faixa_de_voz_nao_aprova_sem_medir(self):  # verificador: item 2
        cenas = [{"video": self.clipe("a.mp4", 2), "voz": self.voz("v.wav", 1.5), "narracao": "Teste.",
                  "texto_tela": "Um texto na tela bem mais comprido que o normal, sem quebra nenhuma aqui"}]
        r = montar(cenas, self.d / "f.mp4", tamanho=(180, 320), cfg=self.RAPIDO)  # pasta temporária apagada
        self.assertIsNotNone(r["sincronia"])  # medida durante a montagem
        problemas = " ".join(verificar_montagem(r)["problemas"])
        self.assertNotIn("não medida", problemas)
        self.assertRegex(problemas, r"texto na tela 1 com \d linhas \(máx\. 2\)")  # verificador: item 5
        r["sincronia"] = None
        self.assertIn("não medida", " ".join(verificar_montagem(r)["problemas"]))

    def test_comando_montar(self):
        import io
        import json
        from contextlib import redirect_stdout

        from torralles_studio.__main__ import main

        self.clipe("a.mp4", 2)
        self.voz("v.wav", 1.2)
        projeto = self.d / "projeto.json"
        projeto.write_text(json.dumps({"proporcao": "9:16", "duracao": 2,
                                       "cenas": [{"video": "a.mp4", "voz": "v.wav", "narracao": "Olá."}]}))
        with redirect_stdout(io.StringIO()) as saida:
            codigo = main(["montar", str(projeto), "-o", str(self.d / "final.mp4")])
        self.assertEqual(codigo, 0, saida.getvalue())
        medidas = json.loads(saida.getvalue().splitlines()[0])
        self.assertLessEqual(medidas["sincronia_max_s"], 0.3)  # a voz ficou até conferir, mesmo sem --trabalho

    def test_entrada_invalida(self):
        with self.assertRaises(ErroMontagem):
            montar([], self.d / "f.mp4")
        with self.assertRaises(ErroMontagem):
            montar([{"video": self.d / "nao_existe.mp4"}], self.d / "f.mp4")


if __name__ == "__main__":
    unittest.main()

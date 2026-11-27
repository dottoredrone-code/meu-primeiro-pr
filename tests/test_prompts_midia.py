"""K35 (spec 14 §A e §F.1): prompts por serviço e checagem antes de gastar cota."""

import unittest
from types import SimpleNamespace

from torralles_studio.prompts_midia import (PromptReprovado, carregar_moldes, checar, molde_do_servico, montar,
                                            neutro_da_cena, preparar)

CENA = {"prompt_imagem": "A cup of green tea on a wooden table, steam rising, morning kitchen",
        "prompt_movimento": "slow pan to the right", "clima": "calmo", "narracao": "..."}


class TestMoldes(unittest.TestCase):
    def setUp(self):
        self.cfg = carregar_moldes()

    def test_mesma_cena_gera_prompts_diferentes_por_molde_e_no_limite(self):
        neutro = neutro_da_cena(CENA, "imagem", proporcao="9:16")
        prompts = {}
        for servico in ("pollinations", "nano_banana"):
            nome, molde = molde_do_servico(servico, "imagem", self.cfg)
            prompts[nome] = montar(neutro, molde)
            self.assertLessEqual(len(prompts[nome]["prompt"]), molde["limite"])
        self.assertNotEqual(prompts["flux"]["prompt"], prompts["padrao"]["prompt"])
        self.assertNotIn("Avoid", prompts["flux"]["prompt"])  # FLUX: sem prompt negativo
        self.assertIn("Avoid: text", prompts["padrao"]["prompt"])
        self.assertIn("vertical 9:16", prompts["padrao"]["prompt"].lower())
        self.assertIn("soft diffused light", prompts["padrao"]["prompt"].lower())

    def test_etiquetas_e_negativo_separado(self):
        _, molde = molde_do_servico("qualquer", "imagem", {**self.cfg, "modalidades": {"imagem": "etiquetas"}})
        r = montar(neutro_da_cena(CENA, "imagem"), molde)
        self.assertNotIn(". ", r["prompt"])
        self.assertIn("watermark", r["negativo"])

    def test_corta_campos_do_fim_ate_caber(self):
        neutro = neutro_da_cena({**CENA, "prompt_imagem": "tea " * 150}, "imagem", proporcao="9:16")
        molde = {"forma": "frase", "limite": 200, "negativo": "embutido", "ordem": ["descricao", "luz", "proporcao"]}
        r = montar(neutro, molde)
        self.assertLessEqual(len(r["prompt"]), 200)
        self.assertIn("proporcao", r["cortados"])

    def test_animar_usa_camera_do_movimento_e_perfil(self):
        perfil = SimpleNamespace(kit_visual={"estilo_imagem": "natural photography", "paleta": ["#1E3A5F"]},
                                 formato={"proporcao": "9:16"}, estilo={})
        r = preparar("fal_kling", neutro_da_cena(CENA, "animar", perfil=perfil), perfil=perfil)
        self.assertTrue(r["prompt"].startswith("Smooth pan to the right"))
        self.assertEqual(r["molde"], "video")
        r = preparar("pollinations", neutro_da_cena(CENA, "imagem", perfil=perfil), perfil=perfil)
        self.assertIn("natural photography", r["prompt"].lower())
        self.assertIn("#1e3a5f", r["prompt"].lower())


class TestChecagem(unittest.TestCase):
    def test_reprova_texto_na_imagem_salvo_quando_a_cena_pede(self):
        cena = {**CENA, "prompt_imagem": "A poster with the words BUY NOW in bold typography"}
        with self.assertRaises(PromptReprovado) as erro:
            preparar("pollinations", neutro_da_cena(cena, "imagem"))
        self.assertIn("texto escrito", str(erro.exception))
        preparar("pollinations", neutro_da_cena({**cena, "texto_na_imagem": True}, "imagem"))

    def test_reprova_nomes_que_o_perfil_evita_e_campos_faltando(self):
        perfil = SimpleNamespace(kit_visual={"evitar_nomes": ["Coca-Cola"]}, formato={}, estilo={})
        cena = {**CENA, "prompt_imagem": "A bottle of coca-cola on the table"}
        with self.assertRaises(PromptReprovado):
            preparar("pollinations", neutro_da_cena(cena, "imagem", perfil=perfil), perfil=perfil)
        with self.assertRaises(PromptReprovado):
            preparar("pollinations", neutro_da_cena({"prompt_imagem": ""}, "imagem"))
        with self.assertRaises(PromptReprovado):  # editar sem instrução
            preparar("x", neutro_da_cena(CENA, "editar_imagem"))

    def test_checar_aprova_cena_normal(self):
        cfg = carregar_moldes()
        neutro = neutro_da_cena(CENA, "animar", cfg=cfg)
        _, molde = molde_do_servico("fal_wan", "animar", cfg)
        self.assertEqual(checar(neutro, montar(neutro, molde), molde, cfg=cfg), [])


if __name__ == "__main__":
    unittest.main()


class TestNoRoteador(unittest.TestCase):
    def _falso(self, nome, cfg=None):
        from torralles_studio.provedores.base import Provedor

        class Falso(Provedor):
            tipo = "imagem"
            recebidos = []

            def configurado(self):
                return None

            def executar(self, **kw):
                self.recebidos.append(kw)
                return "ok"

        p = Falso(nome, cfg or {})
        p.recebidos = []
        return p

    def test_cada_servico_recebe_o_prompt_do_molde_e_reprovado_nao_chama(self):
        from torralles_studio.roteador import Roteador, TodosFalharam

        flux = self._falso("pollinations")
        rt = Roteador({"pollinations": flux}, {"imagem": ["pollinations"]}, dormir=lambda s: None)
        rt.executar("imagem", neutro=neutro_da_cena(CENA, "imagem"), prompt="original")
        self.assertNotIn("neutro", flux.recebidos[0])
        self.assertTrue(flux.recebidos[0]["prompt"].startswith("A cup of green tea"))
        self.assertNotIn("Avoid", flux.recebidos[0]["prompt"])
        ruim = neutro_da_cena({**CENA, "prompt_imagem": "a sign that says HELLO"}, "imagem")
        with self.assertRaises(TodosFalharam) as erro:
            rt.executar("imagem", neutro=ruim, prompt="x", usar_cache=False)
        self.assertEqual(len(flux.recebidos), 1)  # não chegou ao serviço
        self.assertIn("prompt reprovado", erro.exception.tentativas[0].detalhe)

    def test_zoom_local_nunca_e_barrado(self):
        from torralles_studio.roteador import Roteador

        local = self._falso("ken_burns", {"prompt_por_molde": False})
        rt = Roteador({"ken_burns": local}, {"animar": ["ken_burns"]}, dormir=lambda s: None)
        ruim = neutro_da_cena({**CENA, "prompt_imagem": "a sign that says HELLO"}, "animar")
        rt.executar("animar", neutro=ruim, prompt="slow pan to the right")
        self.assertEqual(local.recebidos[0]["prompt"], "slow pan to the right")

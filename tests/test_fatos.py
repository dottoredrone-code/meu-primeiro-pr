import unittest

from torralles_studio.fatos import checar_fatos

FATOS = {"preco": "R$ 49,90", "link": "https://loja.exemplo.com/p/123", "nome_produto": "Luminária Lua 30 cm",
         "desconto": "15%", "obrigatorios": ["nome_produto"]}


class TestFatosTravados(unittest.TestCase):
    def test_texto_fiel_passa(self):
        texto = "A Luminária Lua 30 cm sai por R$ 49,90 com 15% de desconto: loja.exemplo.com/p/123"
        self.assertEqual(checar_fatos(texto, FATOS), [])

    def test_caso_real_preco_inventado_em_faixa(self):
        texto = "Luminária Lua 30 cm por apenas R$ 22 a 28!"
        problemas = checar_fatos(texto, FATOS)
        self.assertTrue(any("faixa de preço" in p for p in problemas))
        self.assertTrue(any("preço não autorizado" in p for p in problemas))

    def test_preco_diferente_reprova(self):
        self.assertTrue(checar_fatos("Luminária Lua 30 cm por R$ 39,90", FATOS))

    def test_formatos_equivalentes_de_preco(self):
        fatos = {"preco": "R$ 1.249,00"}
        self.assertEqual(checar_fatos("Só R$1249,00 hoje", fatos), [])
        self.assertEqual(checar_fatos("Só R$ 1.249 hoje", fatos), [])

    def test_link_e_percentual_inventados(self):
        problemas = checar_fatos("Luminária Lua 30 cm com 50% off em https://outra.com/x", FATOS)
        self.assertTrue(any("link não autorizado" in p for p in problemas))
        self.assertTrue(any("percentual não autorizado" in p for p in problemas))

    def test_obrigatorio_alterado(self):
        problemas = checar_fatos("Luminária Lunar de 30cm por R$ 49,90", FATOS)
        self.assertTrue(any("obrigatório" in p for p in problemas))

    def test_acentos_nao_atrapalham_obrigatorio(self):
        self.assertEqual(checar_fatos("LUMINARIA LUA 30 CM", {"nome_produto": "Luminária Lua 30 cm",
                                                             "obrigatorios": ["nome_produto"]}), [])

    def test_sem_fatos_nao_checa(self):
        self.assertEqual(checar_fatos("R$ 10 em https://x.com/y", {}), [])

    # Regressões da verificação independente (K08)
    def test_frases_comuns_de_anuncio_nao_sao_faixa(self):
        for texto in ["Luminária Lua 30 cm por R$ 49,90 até 31/10",
                      "Luminária Lua 30 cm por R$ 49,90 ou 12 parcelas",
                      "Luminária Lua 30 cm: só R$ 49,90 - 30 cm de pura luz",
                      "Luminária Lua 30 cm, R$ 49,90 a 1 clique"]:
            self.assertEqual(checar_fatos(texto, FATOS), [], texto)

    def test_faixa_com_moeda_nos_dois_lados(self):
        problemas = checar_fatos("Luminária Lua 30 cm de R$ 49,90 a R$ 59,90", FATOS)
        self.assertTrue(any("faixa de preço" in p for p in problemas))

    def test_preco_sem_simbolo_tambem_e_checado(self):
        for texto in ["Luminária Lua 30 cm por 39,90 reais", "Luminária Lua 30 cm por 49 reais",
                      "Luminária Lua 30 cm por 10 dólares", "Luminária Lua 30 cm por BRL 39,90"]:
            self.assertTrue(any("preço não autorizado" in p for p in checar_fatos(texto, FATOS)), texto)
        self.assertEqual(checar_fatos("Luminária Lua 30 cm por 49,90 reais", FATOS), [])

    def test_link_sem_caminho_ou_com_outro_dominio_reprova(self):
        for texto in ["Luminária Lua 30 cm em outraloja.com", "Luminária Lua 30 cm em outraloja.com.br",
                      "Luminária Lua 30 cm: golpe.xyz/pagar", "Luminária Lua 30 cm: ftp://x.org"]:
            self.assertTrue(any("link não autorizado" in p for p in checar_fatos(texto, FATOS)), texto)

    def test_citar_so_o_dominio_autorizado_passa(self):
        self.assertEqual(checar_fatos("Luminária Lua 30 cm em loja.exemplo.com.", FATOS), [])

    def test_preco_do_briefing_sem_moeda(self):
        for preco in ["49,90", 49.9]:
            self.assertEqual(checar_fatos("Por R$ 49,90", {"preco": preco}), [], preco)
            self.assertTrue(checar_fatos("Por R$ 39,90", {"preco": preco}), preco)

    def test_percentual_em_formatos_equivalentes(self):
        self.assertEqual(checar_fatos("Luminária Lua 30 cm com 15,0 % off", FATOS), [])


if __name__ == "__main__":
    unittest.main()

import tomllib
import unittest
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "config" / "referencias.toml"


class TestReferencias(unittest.TestCase):
    def setUp(self):
        self.dados = tomllib.loads(ARQUIVO.read_text(encoding="utf-8"))["categorias"]

    def test_seis_categorias_da_spec_09(self):
        self.assertEqual(sorted(self.dados), ["A", "B", "C", "D", "E", "F"])

    def test_categoria_a_completa(self):
        canais = self.dados["A"]["canais"]
        self.assertEqual(len([c for c in canais if c["status"] != "pendente"]), 5)
        self.assertEqual(self.dados["A"]["negativos"], 2)

    def test_campos_validos(self):
        for cat, d in self.dados.items():
            for c in d["canais"]:
                self.assertIn(c["status"], ("aprovado", "sugestao", "pendente"), (cat, c))
                self.assertIn(c["idioma"], ("en", "pt-BR"), (cat, c))
                if "url" in c:
                    self.assertTrue(c["url"].startswith("https://www.youtube.com/"), (cat, c))


if __name__ == "__main__":
    unittest.main()

"""K42 (D26): voz Kokoro em português, em processo separado, como última reserva da cadeia de voz."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio.config import CONFIG_PADRAO, carregar_roteador
from torralles_studio.pronuncia import taxa_erro
from torralles_studio.provedores import voz as voz_mod
from torralles_studio.rede import ErroProvedor

TEM_FFMPEG = shutil.which("ffmpeg") is not None


class TestKokoro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        self.modelo, self.vozes = self.pasta / "m.onnx", self.pasta / "v.bin"
        self.modelo.write_bytes(b"x")
        self.vozes.write_bytes(b"x")
        self.cfg = {"voz": "pm_alex", "velocidade": 1.1, "modelo_arquivo": str(self.modelo),
                    "vozes_arquivo": str(self.vozes), "timeout": 30}

    def tearDown(self):
        self.tmp.cleanup()

    def test_ultima_reserva_da_cadeia_de_voz(self):
        rt = carregar_roteador(CONFIG_PADRAO)
        self.assertEqual(rt.cadeias["voz"][-1], "kokoro")
        self.assertEqual(rt.provedores["kokoro"].cfg["licenca"], "comercial")

    def test_sem_pacote_ou_sem_modelo_explica(self):
        prov = voz_mod.KokoroVoz("kokoro", {**self.cfg, "modelo_arquivo": str(self.pasta / "falta.onnx")})
        with mock.patch.object(voz_mod.importlib.util, "find_spec", return_value=None):
            self.assertIn("pip install kokoro-onnx", prov.configurado())
        with mock.patch.object(voz_mod.importlib.util, "find_spec", return_value=object()), \
                mock.patch.object(voz_mod, "_kokoro_no_isolado", return_value=False):
            self.assertIn("sem --user", prov.configurado())  # instalado só para o usuário: o -I não acha
        with mock.patch.object(voz_mod.importlib.util, "find_spec", return_value=object()), \
                mock.patch.object(voz_mod, "_kokoro_no_isolado", return_value=True):
            self.assertIn("falta.onnx", prov.configurado())
            self.assertIsNone(voz_mod.KokoroVoz("kokoro", self.cfg).configurado())

    def test_roda_em_processo_separado_com_os_parametros_do_config(self):
        vistos = {}

        def rodar(args, prazo=None, cwd=None):
            vistos.update(args=args, prazo=prazo)
            saida = Path(args[args.index("--saida") + 1])
            vistos["texto"] = Path(args[args.index("--texto-arquivo") + 1]).read_text(encoding="utf-8")
            import wave

            with wave.open(str(saida), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(b"\x00\x00" * 2400)
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch("torralles_studio.ff.rodar", rodar):
            saida = voz_mod.KokoroVoz("kokoro", self.cfg).executar("Olá, vizinho!", self.pasta / "voz.wav")
        self.assertTrue(saida.is_file())
        self.assertEqual(vistos["args"][0], sys.executable)
        self.assertIn("-I", vistos["args"])  # processo isolado: não importa nada da pasta atual
        self.assertTrue(vistos["args"][2].endswith("kokoro_tts.py"))
        self.assertEqual(vistos["args"][vistos["args"].index("--voz") + 1], "pm_alex")
        self.assertEqual(vistos["texto"], "Olá, vizinho!")
        self.assertEqual(vistos["prazo"], 30)

    def test_falha_do_processo_vira_erro_do_provedor(self):
        with mock.patch("torralles_studio.ff.rodar",
                        return_value=subprocess.CompletedProcess([], 1, "", "ModuleNotFoundError: kokoro_onnx")):
            with self.assertRaises(ErroProvedor) as erro:
                voz_mod.KokoroVoz("kokoro", self.cfg).executar("oi", self.pasta / "voz.mp3")
        self.assertIn("kokoro_onnx", str(erro.exception))

    def test_studio_nao_importa_o_kokoro(self):
        import torralles_studio.provedores.voz as modulo

        texto = Path(modulo.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import kokoro_onnx", texto)
        self.assertNotIn("from kokoro_onnx", texto)


class TestHifenNaConferencia(unittest.TestCase):
    def test_junto_ou_separado_nao_e_erro(self):
        self.assertEqual(taxa_erro("ação anti-inflamatória", "ação antiinflamatória"), 0.0)
        self.assertEqual(taxa_erro("guarda-chuva aberto", "guarda chuva aberto"), 0.0)
        self.assertEqual(taxa_erro("o filho", "o filo"), 0.5)
        self.assertEqual(taxa_erro("guarda-chuva e anti-inflamatório", "guarda chuva e antiinflamatório"), 0.0)
        self.assertEqual(taxa_erro("bem-vindo, vinte e um", "bem-vindo vinte e um"), 0.0)


@unittest.skipUnless(os.environ.get("TESTES_KOKORO"), "usa o modelo de verdade: rode com TESTES_KOKORO=1")
class TestKokoroDeVerdade(unittest.TestCase):
    def test_fala_frase_curta(self):
        prov = carregar_roteador(CONFIG_PADRAO).provedores["kokoro"]
        if prov.configurado():
            self.skipTest(prov.configurado())
        with tempfile.TemporaryDirectory() as pasta:
            self.assertGreater(prov.executar("Olha o vizinho.", Path(pasta) / "v.wav").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()

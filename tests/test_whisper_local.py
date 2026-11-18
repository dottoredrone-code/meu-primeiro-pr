"""K39: transcrição grátis no PC (faster-whisper) antes do Gemini."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from torralles_studio import percepcao, pronuncia
from torralles_studio.producao import _conferir
from torralles_studio.seguranca import Orcamento


class TestWhisperLocalPrimeiro(unittest.TestCase):
    def test_fala_vai_primeiro_ao_whisper_sem_chamar_o_gemini(self):
        def gemini(arquivo):
            raise AssertionError("não devia chamar o Gemini")

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x", "TRANSCRICAO_ORDEM": ""}), \
                mock.patch.object(percepcao, "whisper_disponivel", return_value=True), \
                mock.patch.object(percepcao, "transcrever_whisper",
                                  return_value=[{"inicio": 0, "fim": 1, "texto": "Olha o filho"}]), \
                mock.patch.object(pronuncia, "_transcrever_fala_gemini", gemini):
            r = pronuncia.transcrever_fala("x.mp3")
        self.assertEqual(r, {"texto": "Olha o filho", "motor": "faster-whisper:fala"})

    def test_ordem_pode_por_o_gemini_primeiro(self):
        with mock.patch.dict(os.environ, {"TRANSCRICAO_ORDEM": "gemini, whisper"}):
            self.assertEqual(percepcao.ordem_transcricao(), ["gemini", "whisper"])
        with mock.patch.dict(os.environ, {"TRANSCRICAO_ORDEM": "qualquer"}):
            self.assertEqual(percepcao.ordem_transcricao(), ["whisper", "gemini"])

    def test_whisper_quebrado_cai_no_gemini_da_percepcao(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x", "TRANSCRICAO_ORDEM": ""}), \
                mock.patch.object(percepcao, "whisper_disponivel", return_value=True), \
                mock.patch.object(percepcao, "_transcrever_whisper", side_effect=RuntimeError("modelo não baixou")), \
                mock.patch.object(percepcao, "_transcrever_gemini", return_value={"texto": "oi", "motor": "gemini:x"}):
            self.assertEqual(percepcao.transcrever("v.mp4", None)["motor"], "gemini:x")

    def test_sem_whisper_explica_como_instalar(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "TRANSCRICAO_ORDEM": ""}), \
                mock.patch.object(percepcao, "whisper_disponivel", return_value=False):
            self.assertIn("pip install faster-whisper", percepcao.transcrever("v.mp4", None)["motivo"])

    def test_conferencia_local_nao_entra_no_orcamento(self):
        rt = mock.Mock(orcamento=Orcamento(1.5))
        with mock.patch.object(percepcao, "whisper_disponivel", return_value=True), \
                mock.patch.dict(os.environ, {"TRANSCRICAO_ORDEM": ""}):
            _conferir(lambda a, t: {"ok": True, "motor": "faster-whisper:fala"}, rt, "x.mp3", "oi")
            self.assertEqual(rt.orcamento.gasto_usd, 0)
            _conferir(lambda a, t: {"ok": True, "motor": "gemini:fala:m"}, rt, "x.mp3", "oi")
            self.assertGreater(rt.orcamento.gasto_usd, 0)

    def test_transcricao_local_da_fala_nao_corta_a_palavra_sons(self):
        r = pronuncia.conferir_voz("x.mp3", "Ouça os sons: pássaros cantando.",
                                   transcrever=lambda a, p: {"texto": "Ouça os sons: pássaros cantando.",
                                                             "motor": "faster-whisper:fala"})
        self.assertEqual(r["erros"], 0)


class TestWhisperFalhando(unittest.TestCase):
    def test_whisper_que_falha_nao_e_tentado_duas_vezes(self):
        chamadas = []

        def quebrado(arquivo, palavras=False):
            chamadas.append(1)
            raise RuntimeError("modelo não baixou")

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "", "TRANSCRICAO_ORDEM": ""}), \
                mock.patch.object(percepcao, "whisper_disponivel", return_value=True), \
                mock.patch.object(percepcao, "transcrever_whisper", quebrado), \
                mock.patch("sys.stderr"):
            r = pronuncia.transcrever_fala("x.mp3")
        self.assertEqual(len(chamadas), 1)
        self.assertIsNone(r["texto"])
        self.assertIn("gemini: falta GEMINI_API_KEY", r["motivo"])

    def test_sem_folga_no_teto_nunca_chama_o_gemini(self):
        rt = mock.Mock(orcamento=Orcamento(0.001))
        rt.orcamento.registrar("outro", 0.001)  # teto cheio
        vista = {}

        def conferir(arquivo, texto):
            vista["chave"] = os.environ.get("GEMINI_API_KEY")
            return None

        with mock.patch.object(percepcao, "whisper_disponivel", return_value=True), \
                mock.patch.dict(os.environ, {"TRANSCRICAO_ORDEM": "", "GEMINI_API_KEY": "chave"}):
            _conferir(conferir, rt, "x.mp3", "oi")
            self.assertEqual(os.environ["GEMINI_API_KEY"], "chave")  # volta depois
        self.assertIsNone(vista["chave"])
        self.assertAlmostEqual(rt.orcamento.gasto_usd, 0.001)

    def test_modelo_que_nao_carrega_e_lembrado(self):
        import types

        tentativas = []

        class Modelo:
            def __init__(self, *a, **kw):
                tentativas.append(1)
                raise OSError("sem internet")

        falso = types.SimpleNamespace(WhisperModel=Modelo)
        with mock.patch.dict("sys.modules", {"faster_whisper": falso}), \
                mock.patch.dict(os.environ, {"WHISPER_MODELO": "modelo-teste-inexistente"}):
            for _ in range(2):
                with self.assertRaises(Exception):
                    percepcao.modelo_whisper()
        percepcao._MODELOS_WHISPER.pop("modelo-teste-inexistente", None)
        self.assertEqual(len(tentativas), 1)


@unittest.skipUnless(os.environ.get("TESTES_WHISPER"), "baixa o modelo (~460 MB): rode com TESTES_WHISPER=1")
class TestWhisperDeVerdade(unittest.TestCase):
    def test_transcreve_e_devolve_tempo_das_palavras(self):
        if not shutil.which("ffmpeg") or not percepcao.whisper_disponivel():
            self.skipTest("sem FFmpeg ou faster-whisper")
        with tempfile.TemporaryDirectory() as pasta:
            audio = Path(pasta) / "tom.wav"
            percepcao.ff.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(audio)])
            self.assertIsInstance(percepcao.transcrever_whisper(audio, palavras=True), list)


if __name__ == "__main__":
    unittest.main()

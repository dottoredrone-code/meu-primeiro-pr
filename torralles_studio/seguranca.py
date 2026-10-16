"""Proteções transversais: esconder chaves em mensagens e controlar o gasto (D8, D20)."""

import os
import re

_PADROES = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),          # OpenAI, Anthropic, DeepSeek, OpenRouter
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),         # Google
    re.compile(r"(?i)(bearer|key)\s+[A-Za-z0-9_\-\.:]{16,}"),
]
_SUFIXOS_SECRETOS = ("_KEY", "_TOKEN", "_SECRET")


def _encurtar(valor):
    return f"…{valor[-4:]}" if len(valor) >= 16 else "…"


def mascarar(texto):
    """Troca valores de chaves (do ambiente ou com formato conhecido) por uma versão encurtada."""
    if not texto:
        return texto
    texto = str(texto)
    for nome, valor in os.environ.items():
        if nome.upper().endswith(_SUFIXOS_SECRETOS) and len(valor) >= 6 and valor in texto:
            texto = texto.replace(valor, _encurtar(valor))
    for padrao in _PADROES:
        texto = padrao.sub(lambda m: _encurtar(m.group(0)), texto)
    return texto


class Orcamento:
    """Teto de gasto por execução (ex.: por vídeo). Falha fechada: o que não cabe não é chamado.

    O custo de cada chamada é uma estimativa do config (`custo_usd` por chamada e/ou
    `custo_usd_por_segundo` para vídeo). Cada tentativa enviada ao provedor é lançada,
    inclusive as que falham, para errar a favor do bolso.
    """

    def __init__(self, teto_usd=None):
        self.teto_usd = teto_usd
        self.gasto_usd = 0.0
        self.lancamentos = []

    DURACAO_PADRAO_S = 5  # mesma duração padrão dos provedores de vídeo

    @classmethod
    def estimar(cls, provedor, kwargs):
        cfg = provedor.cfg
        por_segundo = float(cfg.get("custo_usd_por_segundo", 0))
        try:
            duracao = float(kwargs.get("duracao") or cls.DURACAO_PADRAO_S)
        except (TypeError, ValueError):
            duracao = cls.DURACAO_PADRAO_S
        return float(cfg.get("custo_usd", 0)) + por_segundo * duracao

    def cabe(self, valor):
        return self.teto_usd is None or self.gasto_usd + valor <= self.teto_usd + 1e-9

    def registrar(self, provedor, valor):
        if valor:
            self.gasto_usd += valor
            self.lancamentos.append((provedor, round(valor, 4)))

    def reiniciar(self, teto_usd=None):
        """Começa um orçamento novo (ex.: a cada vídeo), mantendo o teto atual se nenhum for dado."""
        if teto_usd is not None:
            self.teto_usd = teto_usd
        self.gasto_usd = 0.0
        self.lancamentos = []

    @property
    def restante(self):
        return None if self.teto_usd is None else max(self.teto_usd - self.gasto_usd, 0)

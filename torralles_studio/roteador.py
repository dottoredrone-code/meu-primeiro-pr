"""Roteador com fallback: tenta cada provedor da cadeia de uma tarefa, em ordem.

Regras:
- Provedor sem chave/configuração é pulado.
- Erro temporário (429, 5xx, rede) → repete no mesmo provedor com espera
  crescente; se continuar falhando, passa para o próximo.
- Erro definitivo (400, resposta inválida...) → passa direto para o próximo.
- 429 (limite) e 401/403 (chave inválida) colocam o provedor em "descanso"
  por um tempo, para as próximas chamadas nem tentarem nele.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from .rede import ErroProvedor

DESCANSO_LIMITE = 60  # segundos após um 429
DESCANSO_CHAVE = 3600  # segundos após 401/403


@dataclass
class Tentativa:
    provedor: str
    status: str  # "ok", "pulado" ou "falhou"
    detalhe: str = ""


@dataclass
class Resultado:
    valor: Any
    provedor: str
    tentativas: list = field(default_factory=list)


class TodosFalharam(Exception):
    def __init__(self, tarefa, tentativas):
        linhas = "\n".join(f"  - {t.provedor}: {t.status} ({t.detalhe})" for t in tentativas)
        super().__init__(f"nenhum provedor conseguiu executar '{tarefa}':\n{linhas}")
        self.tarefa = tarefa
        self.tentativas = tentativas


class Roteador:
    def __init__(self, provedores, cadeias, repeticoes=1, espera_base=1.0, dormir=time.sleep, relogio=time.monotonic):
        self.provedores = provedores
        self.cadeias = cadeias
        self.repeticoes = repeticoes
        self.espera_base = espera_base
        self._dormir = dormir
        self._relogio = relogio
        self._descanso_ate = {}

    def tipo_da_tarefa(self, tarefa):
        return self.provedores[self.cadeias[tarefa][0]].tipo

    def executar(self, tarefa, *, validar=None, **kwargs):
        """Executa a tarefa no primeiro provedor que funcionar.

        validar: função opcional que recebe a resposta e devolve o valor final,
        ou lança ValueError para tratar a resposta como falha e tentar o próximo.
        """
        if tarefa not in self.cadeias:
            raise KeyError(f"tarefa desconhecida: {tarefa}")
        tentativas = []
        for nome in self.cadeias[tarefa]:
            provedor = self.provedores[nome]
            motivo = provedor.configurado() or self._em_descanso(nome)
            if motivo:
                tentativas.append(Tentativa(nome, "pulado", motivo))
                continue
            try:
                valor = self._chamar(nome, provedor, kwargs)
                if validar:
                    valor = validar(valor)
            except (ErroProvedor, ValueError) as e:
                tentativas.append(Tentativa(nome, "falhou", str(e)))
                continue
            except Exception as e:  # resposta em formato inesperado, bug no provedor...
                tentativas.append(Tentativa(nome, "falhou", f"{type(e).__name__}: {e}"))
                continue
            tentativas.append(Tentativa(nome, "ok"))
            return Resultado(valor, nome, tentativas)
        raise TodosFalharam(tarefa, tentativas)

    def _chamar(self, nome, provedor, kwargs):
        for n in range(self.repeticoes + 1):
            try:
                return provedor.executar(**kwargs)
            except ErroProvedor as e:
                if e.status == 429:
                    self._descansar(nome, DESCANSO_LIMITE)
                    raise  # limite atingido: melhor ir logo para o próximo
                if e.status in (401, 403):
                    self._descansar(nome, DESCANSO_CHAVE)
                    raise
                if not e.temporario or n == self.repeticoes:
                    raise
                self._dormir(self.espera_base * 2**n)

    def _descansar(self, nome, segundos):
        self._descanso_ate[nome] = self._relogio() + segundos

    def _em_descanso(self, nome):
        restante = self._descanso_ate.get(nome, 0) - self._relogio()
        return f"em descanso por mais {int(restante)}s" if restante > 0 else None

    def status(self):
        """Mapa tarefa → [(provedor, motivo ou None se pronto)]."""
        return {
            tarefa: [(n, self.provedores[n].configurado() or self._em_descanso(n)) for n in cadeia]
            for tarefa, cadeia in self.cadeias.items()
        }

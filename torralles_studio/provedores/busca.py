import urllib.parse

from ..rede import ErroProvedor, get_json, post_json
from .base import Provedor


def _exigir_resultados(resultados):
    if not resultados:
        raise ErroProvedor("busca sem resultados")
    return resultados


class TavilyBusca(Provedor):
    tipo = "busca"

    def executar(self, consulta, max_resultados=5):
        r = post_json(
            "https://api.tavily.com/search",
            {"query": consulta, "max_results": max_resultados},
            {"Authorization": f"Bearer {self.chave}"},
            self.timeout,
        )
        return _exigir_resultados(
            [{"titulo": x["title"], "url": x["url"], "trecho": x.get("content", "")} for x in r.get("results", [])]
        )


class BraveBusca(Provedor):
    tipo = "busca"

    def executar(self, consulta, max_resultados=5):
        q = urllib.parse.urlencode({"q": consulta, "count": max_resultados})
        r = get_json(
            f"https://api.search.brave.com/res/v1/web/search?{q}",
            {"X-Subscription-Token": self.chave, "Accept": "application/json"},
            self.timeout,
        )
        return _exigir_resultados(
            [
                {"titulo": x["title"], "url": x["url"], "trecho": x.get("description", "")}
                for x in r.get("web", {}).get("results", [])
            ]
        )

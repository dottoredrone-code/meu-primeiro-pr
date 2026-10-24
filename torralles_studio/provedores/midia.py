"""Busca de mídia gratuita com licença clara (K20, spec 11, D18 — camada 2).

Cada provedor devolve uma lista de candidatos no mesmo formato:
  {"url": link para baixar, "licenca": texto da licença, "autor", "link" (página da obra), "titulo",
   "fonte", "tipo" (imagem|video|audio), "largura", "altura", "duracao", "tags": [..]}
O filtro de licença e o download ficam em midia.py (fora do provedor), para valer igual para todos.
"""

import urllib.parse

from ..rede import ErroProvedor, get_json
from .base import Provedor

TIPOS = ("imagem", "video", "audio")


def _exigir(candidatos):
    if not candidatos:
        raise ErroProvedor("busca de mídia sem resultados")
    return candidatos


def _orientacao(proporcao):
    return {"9:16": "portrait", "16:9": "landscape", "1:1": "square", "4:5": "portrait"}.get(proporcao or "")


class PexelsMidia(Provedor):
    tipo = "midia"

    def executar(self, consulta, tipo="imagem", max_resultados=5, proporcao=None):
        if tipo not in ("imagem", "video"):
            raise ErroProvedor("Pexels só tem imagem e vídeo")
        params = {"query": consulta, "per_page": max_resultados, "locale": "pt-BR"}
        if _orientacao(proporcao):
            params["orientation"] = _orientacao(proporcao)
        base = "https://api.pexels.com/v1/search" if tipo == "imagem" else "https://api.pexels.com/videos/search"
        r = get_json(f"{base}?{urllib.parse.urlencode(params)}", {"Authorization": self.chave}, self.timeout)
        candidatos = []
        if tipo == "imagem":
            for f in r.get("photos", []):
                candidatos.append({"url": f["src"].get("large2x") or f["src"]["original"], "licenca": "pexels",
                                   "autor": f.get("photographer"), "link": f.get("url"), "titulo": f.get("alt"),
                                   "fonte": "Pexels", "tipo": "imagem", "largura": f.get("width"),
                                   "altura": f.get("height"), "tags": []})
        else:
            for v in r.get("videos", []):
                arquivos = sorted((a for a in v.get("video_files", []) if a.get("link") and a.get("width")
                                   and a.get("file_type", "video/mp4") == "video/mp4"),
                                  key=lambda a: abs((a.get("height") or 0) - 1920) if proporcao == "9:16"
                                  else abs((a.get("width") or 0) - 1920))
                if not arquivos:
                    continue
                a = arquivos[0]
                candidatos.append({"url": a["link"], "licenca": "pexels", "autor": (v.get("user") or {}).get("name"),
                                   "link": v.get("url"), "titulo": None, "fonte": "Pexels", "tipo": "video",
                                   "largura": a.get("width"), "altura": a.get("height"),
                                   "duracao": v.get("duration"), "tags": []})
        return _exigir(candidatos)


class PixabayMidia(Provedor):
    tipo = "midia"

    def executar(self, consulta, tipo="imagem", max_resultados=5, proporcao=None):
        if tipo not in ("imagem", "video"):
            raise ErroProvedor("Pixabay (API) só tem imagem e vídeo")
        params = {"key": self.chave, "q": consulta, "per_page": max(3, max_resultados), "lang": "pt",
                  "safesearch": "true"}
        if tipo == "imagem":
            params["image_type"] = "photo"
            if proporcao in ("9:16", "4:5"):
                params["orientation"] = "vertical"
            elif proporcao == "16:9":
                params["orientation"] = "horizontal"
        base = "https://pixabay.com/api/" if tipo == "imagem" else "https://pixabay.com/api/videos/"
        r = get_json(f"{base}?{urllib.parse.urlencode(params)}", None, self.timeout)
        candidatos = []
        for h in r.get("hits", [])[:max_resultados]:
            tags = [t.strip() for t in str(h.get("tags", "")).split(",") if t.strip()]
            comum = {"licenca": "pixabay", "autor": h.get("user"), "link": h.get("pageURL"), "titulo": None,
                     "fonte": "Pixabay", "tags": tags}
            if tipo == "imagem":
                candidatos.append({**comum, "url": h.get("largeImageURL"), "tipo": "imagem",
                                   "largura": h.get("imageWidth"), "altura": h.get("imageHeight")})
            else:
                videos = h.get("videos") or {}
                # "medium" costuma ser 1920 px; "large" (4K) pode vir vazio ({"url": ""}) e é pesado demais
                v = next((videos[k] for k in ("medium", "large", "small") if (videos.get(k) or {}).get("url")), {})
                if v.get("url"):
                    candidatos.append({**comum, "url": v["url"], "tipo": "video", "largura": v.get("width"),
                                       "altura": v.get("height"), "duracao": h.get("duration")})
        return _exigir([c for c in candidatos if c.get("url")])


class OpenverseMidia(Provedor):
    """Obras Creative Commons agregadas (imagem e áudio). Funciona sem chave, com limite menor."""

    tipo = "midia"

    def configurado(self):
        return None  # chave é opcional

    def executar(self, consulta, tipo="imagem", max_resultados=5, proporcao=None, categoria=None):
        if tipo not in ("imagem", "audio"):
            raise ErroProvedor("Openverse só tem imagem e áudio")
        params = {"q": consulta, "page_size": max_resultados, "license_type": "commercial,modification"}
        if tipo == "audio":  # fontes cujos arquivos ficam em domínios liberados e com licença clara
            params["source"] = "jamendo,freesound,wikimedia_audio" if categoria == "music" else "freesound,wikimedia_audio"
            if categoria:
                params["category"] = categoria  # "music" para trilha; efeitos sonoros: "sound_effect"
        if tipo == "imagem" and proporcao in ("9:16", "4:5"):
            params["aspect_ratio"] = "tall"
        elif tipo == "imagem" and proporcao == "16:9":
            params["aspect_ratio"] = "wide"
        rota = "images" if tipo == "imagem" else "audio"
        cab = {"Authorization": f"Bearer {self.chave}"} if self.chave else None
        r = get_json(f"https://api.openverse.org/v1/{rota}/?{urllib.parse.urlencode(params)}", cab, self.timeout)
        candidatos = []
        for x in r.get("results", []):
            lic = str(x.get("license") or "").strip().lower()
            # sem licença = fonte sem licença clara (bloqueada); nunca vira CC0 por padrão
            licenca = "cc0" if lic in ("cc0", "pdm") else (f"cc-{lic}" if lic else None)
            candidatos.append({"url": x.get("url"), "licenca": licenca, "autor": x.get("creator"),
                               "link": x.get("foreign_landing_url"), "titulo": x.get("title"),
                               "fonte": f"Openverse ({x.get('source') or x.get('provider') or 'origem'})",
                               "tipo": tipo, "largura": x.get("width"), "altura": x.get("height"),
                               "duracao": (x.get("duration") or 0) / 1000 or None,
                               "tags": [t.get("name") for t in x.get("tags") or [] if t.get("name")]})
        return _exigir([c for c in candidatos if c.get("url")])


class FreesoundMidia(Provedor):
    """Efeitos sonoros. Baixa a prévia em alta qualidade (MP3), que não exige login OAuth.

    Atenção (D22): a API do Freesound é grátis só para uso NÃO comercial; uso comercial exige licença deles.
    Por isso só é usado em projetos não comerciais (perfil com `comercial = false`); nos demais é pulado.
    """

    tipo = "midia"

    def executar(self, consulta, tipo="audio", max_resultados=5, proporcao=None):
        if tipo != "audio":
            raise ErroProvedor("Freesound só tem áudio")
        params = {"query": consulta, "page_size": max_resultados,
                  "fields": "id,name,username,license,previews,url,duration,tags",
                  "filter": 'license:("Creative Commons 0" OR "Attribution")'}
        r = get_json(f"https://freesound.org/apiv2/search/text/?{urllib.parse.urlencode(params)}",
                     {"Authorization": f"Token {self.chave}"}, self.timeout)  # chave no cabeçalho, não na URL
        candidatos = []
        for s in r.get("results", []):
            previa = (s.get("previews") or {}).get("preview-hq-mp3")
            if not previa:
                continue
            candidatos.append({"url": previa, "licenca": s.get("license"), "autor": s.get("username"),
                               "link": s.get("url"), "titulo": s.get("name"), "fonte": "Freesound",
                               "tipo": "audio", "duracao": s.get("duration"), "tags": s.get("tags") or []})
        return _exigir(candidatos)

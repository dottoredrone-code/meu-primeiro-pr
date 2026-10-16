"""Biblioteca de mídia (K25, spec 05 seção 3, spec 11 "Regras de licença", D2, D18).

- Cada arquivo é guardado **uma vez só**, pelo hash do conteúdo: `ativos/ab/abcdef….ext`.
- **Licença obrigatória**: sem licença aceita, o arquivo não entra. Cada ativo guarda fonte, autor, link,
  licença, data e se permite uso comercial.
- **Busca por etiqueta** (todas as etiquetas pedidas), tipo e texto.
- Ativos podem ser de um perfil de projeto (não aparecem para outro perfil, D11) ou compartilhados.
- Créditos automáticos para itens que exigem atribuição (CC-BY).
"""

import hashlib
import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Licenças conhecidas (spec 11). comercial: pode usar em conteúdo monetizado; credito: exige atribuição.
LICENCAS = {
    "cc0":            {"nome": "CC0 (domínio público)", "comercial": True, "credito": False},
    "pexels":         {"nome": "Licença Pexels", "comercial": True, "credito": False},
    "pixabay":        {"nome": "Licença Pixabay", "comercial": True, "credito": False},
    "cc-by":          {"nome": "CC BY", "comercial": True, "credito": True},
    "gerado_ia":      {"nome": "Gerado por IA (termos do provedor permitem uso comercial)", "comercial": True,
                       "credito": False},
    "comprado":       {"nome": "Comprado com direito de uso comercial", "comercial": True, "credito": False},
    "proprio":        {"nome": "Produção própria", "comercial": True, "credito": False},
}
# Bloqueadas sempre, com o motivo (spec 11 e D2).
BLOQUEADAS = {
    "cc-by-nc": "não permite uso comercial",
    "cc-by-nc-sa": "não permite uso comercial",
    "cc-by-nc-nd": "não permite uso comercial nem edição",
    "cc-by-nd": "não permite edição (o vídeo edita o arquivo)",
    "cc-by-sa": "obriga a publicar o vídeo com a mesma licença",
    "uso_pessoal": "só uso pessoal",
    "desconhecida": "fonte sem licença clara",
}
_APELIDOS = {"cc-zero": "cc0", "public-domain": "cc0", "dominio-publico": "cc0", "pdm": "cc0",
             "by": "cc-by", "by-nc": "cc-by-nc", "by-nd": "cc-by-nd", "by-sa": "cc-by-sa",
             "by-nc-sa": "cc-by-nc-sa", "by-nc-nd": "cc-by-nc-nd", "personal": "uso_pessoal"}
TIPOS = {
    "imagem": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
    "video": {".mp4", ".mov", ".webm", ".mkv"},
    "audio": {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"},
}


class ErroLicenca(ValueError):
    pass


def normalizar_licenca(licenca):
    """'CC BY 4.0' → 'cc-by'; 'CC-BY-NC-SA 3.0' → 'cc-by-nc-sa'. Devolve '' se vazio."""
    if not licenca:
        return ""
    t = str(licenca).strip().lower().replace("_", "-").replace(" ", "-")
    t = re.sub(r"-\d+(\.\d+)*$", "", t)             # versão: "-4.0", "-3" (sem tocar no "0" de cc0)
    t = re.sub(r"-+", "-", t).strip("-")
    t = t.replace("uso-pessoal", "uso_pessoal").replace("gerado-ia", "gerado_ia")
    return _APELIDOS.get(t, t)


def conferir_licenca(licenca):
    """Devolve (código, regras) de uma licença aceita; senão lança ErroLicenca com o motivo em pt-BR."""
    codigo = normalizar_licenca(licenca)
    if not codigo:
        raise ErroLicenca("licença obrigatória: sem licença o arquivo não entra na biblioteca")
    if codigo in BLOQUEADAS:
        raise ErroLicenca(f"licença {licenca!r} bloqueada: {BLOQUEADAS[codigo]}")
    if codigo not in LICENCAS:
        raise ErroLicenca(f"licença {licenca!r} desconhecida: confira antes de usar "
                          f"(aceitas: {', '.join(sorted(LICENCAS))})")
    return codigo, LICENCAS[codigo]


def _etiqueta(t):
    t = "".join(c for c in unicodedata.normalize("NFD", str(t)) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def _etiquetas(tags):
    if isinstance(tags, str):
        tags = [tags]
    return sorted({e for e in (_etiqueta(t) for t in tags or ()) if e})


def _hash(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def tipo_do_arquivo(caminho):
    ext = Path(caminho).suffix.lower()
    return next((t for t, exts in TIPOS.items() if ext in exts), "outro")


class Biblioteca:
    def __init__(self, raiz, banco):
        self.raiz = Path(raiz)
        self.banco = banco
        self.con = banco.con

    # -- entrada --------------------------------------------------------------
    def adicionar(self, arquivo, licenca, fonte, *, autor=None, link=None, tags=(), perfil=None,
                  provedor=None, modelo=None, prompt=None, parametros=None, titulo=None):
        """Guarda o arquivo (uma vez só) com a licença conferida. Devolve o ativo (dict).

        Arquivo já presente (mesmo conteúdo): não duplica; as etiquetas novas são somadas e o ativo
        devolvido tem `duplicado=True`.
        """
        arquivo = Path(arquivo)
        if not arquivo.is_file():
            raise FileNotFoundError(f"arquivo não encontrado: {arquivo}")
        codigo, regras = conferir_licenca(licenca)
        if not str(fonte or "").strip():
            raise ErroLicenca("informe a fonte do arquivo (site, provedor ou 'produção própria')")
        if regras["credito"] and not (autor and str(autor).strip()):
            raise ErroLicenca(f"a licença {regras['nome']} exige crédito: informe o autor")
        digest = _hash(arquivo)
        existente = self.obter(digest)
        etiquetas = _etiquetas(tags)
        if existente:
            if existente["perfil"] and existente["perfil"] != perfil:
                # já é de outro perfil: não muda o dono nem mostra ao perfil novo (D11)
                raise ErroLicenca(f"este arquivo já está na biblioteca de outro perfil ({existente['perfil']})")
            self.adicionar_tags(digest, etiquetas)
            ativo = self.obter(digest)
            ativo["duplicado"] = True
            return ativo
        relativo = Path("ativos") / digest[:2] / f"{digest}{arquivo.suffix.lower()}"
        destino = self.raiz / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists():
            temporario = destino.with_suffix(destino.suffix + ".parcial")
            shutil.copyfile(arquivo, temporario)
            temporario.replace(destino)  # nunca deixa arquivo pela metade com nome final
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.con:
            self.con.execute(
                "INSERT INTO ativos (hash, tipo, caminho, provedor, modelo, prompt, parametros_json, licenca, "
                "uso_comercial, fonte, tags, criado_em, autor, link, titulo, perfil) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (digest, tipo_do_arquivo(arquivo), relativo.as_posix(), provedor, modelo, prompt,
                 json.dumps(parametros or {}, ensure_ascii=False, default=str), codigo, int(regras["comercial"]),
                 str(fonte).strip(), self._tags_texto(etiquetas), agora, autor, link, titulo, perfil))
        ativo = self.obter(digest)
        ativo["duplicado"] = False
        return ativo

    def adicionar_tags(self, digest, tags):
        ativo = self.obter(digest)
        if not ativo:
            raise KeyError(digest)
        novas = sorted(set(ativo["tags"]) | set(_etiquetas(tags)))
        with self.con:
            self.con.execute("UPDATE ativos SET tags = ? WHERE hash = ?", (self._tags_texto(novas), digest))

    # -- consulta -------------------------------------------------------------
    def obter(self, digest):
        linha = self.con.execute("SELECT * FROM ativos WHERE hash = ?", (digest,)).fetchone()
        return self._como_dict(linha) if linha else None

    def buscar(self, tags=(), tipo=None, texto=None, perfil=None, limite=50):
        """Ativos com TODAS as etiquetas pedidas. Mostra os compartilhados e os do perfil, nunca os de outro."""
        sql, args = "SELECT * FROM ativos WHERE (perfil IS NULL OR perfil = ?)", [perfil]
        for e in _etiquetas(tags):
            sql, args = sql + " AND tags LIKE ?", args + [f"%,{e},%"]
        if tipo:
            sql, args = sql + " AND tipo = ?", args + [tipo]
        if texto:
            alvo = "%" + str(texto).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            sql += (" AND (COALESCE(prompt,'') LIKE ? ESCAPE '\\' OR COALESCE(titulo,'') LIKE ? ESCAPE '\\'"
                    " OR COALESCE(autor,'') LIKE ? ESCAPE '\\' OR fonte LIKE ? ESCAPE '\\')")
            args += [alvo] * 4
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(int(limite))
        return [self._como_dict(l) for l in self.con.execute(sql, args)]

    def caminho(self, ativo):
        return self.raiz / ativo["caminho"]

    def creditos(self, ativos):
        """Texto para a descrição do vídeo com os itens que exigem crédito (spec 11)."""
        linhas = []
        for a in ativos:
            if not LICENCAS.get(a["licenca"], {}).get("credito"):
                continue
            partes = [a.get("titulo") or Path(a["caminho"]).name, f"por {a['autor']}",
                      LICENCAS[a["licenca"]]["nome"], a["fonte"]]
            if a.get("link"):
                partes.append(a["link"])
            linha = " — ".join(partes)
            if linha not in linhas:
                linhas.append(linha)
        return ("Créditos:\n" + "\n".join(f"- {l}" for l in linhas)) if linhas else ""

    def verificar(self):
        """Confere a biblioteca: arquivo sumido ou alterado (hash diferente). Devolve a lista de problemas."""
        problemas = []
        for linha in self.con.execute("SELECT hash, caminho FROM ativos"):
            arq = self.raiz / linha["caminho"]
            if not arq.is_file():
                problemas.append(f"arquivo sumiu: {linha['caminho']}")
            elif _hash(arq) != linha["hash"]:
                problemas.append(f"arquivo alterado: {linha['caminho']}")
        return problemas

    # -- interno --------------------------------------------------------------
    @staticmethod
    def _tags_texto(etiquetas):
        return "," + ",".join(etiquetas) + "," if etiquetas else ","

    @staticmethod
    def _como_dict(linha):
        d = dict(linha)
        d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
        d["parametros"] = json.loads(d.pop("parametros_json") or "{}")
        d["uso_comercial"] = bool(d["uso_comercial"])
        return d

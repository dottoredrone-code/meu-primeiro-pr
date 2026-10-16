"""Biblioteca de mídia (K25, spec 05 seção 3, spec 11 "Regras de licença", D2, D18).

- Cada arquivo é guardado **uma vez só**, pelo hash do conteúdo: `ativos/ab/abcdef….ext`.
- **Licença obrigatória**: sem licença aceita, o arquivo não entra. Cada ativo guarda fonte, autor, link,
  licença, data e se permite uso comercial.
- **Busca por etiqueta** (todas as etiquetas pedidas), tipo e texto.
- Visibilidade e etiquetas ficam por perfil (tabela ativo_perfil): o mesmo arquivo pode servir a vários
  perfis, cada um com suas etiquetas, e nenhum vê as etiquetas nem a existência do uso do outro (D11).
  Perfil vazio ('') = compartilhado com todos.
- Créditos automáticos para itens que exigem atribuição (CC-BY).
"""

import hashlib
import json
import re
import shutil
import sqlite3
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
             "by-nc-sa": "cc-by-nc-sa", "by-nc-nd": "cc-by-nc-nd", "personal": "uso_pessoal",
             "personal-use": "uso_pessoal", "attribution": "cc-by", "attribution-sharealike": "cc-by-sa",
             "attribution-noderivs": "cc-by-nd", "attribution-noderivatives": "cc-by-nd",
             "attribution-noncommercial": "cc-by-nc", "attribution-noncommercial-sharealike": "cc-by-nc-sa",
             "attribution-noncommercial-noderivs": "cc-by-nc-nd",
             "attribution-noncommercial-noderivatives": "cc-by-nc-nd"}
# Palavras de nome oficial que não mudam a licença ("Pixabay Content License", "CC0 1.0 Universal").
_RUIDO = {"license", "licence", "licenca", "content", "universal", "international", "internacional", "br",
          "brasil", "unported", "deed", "public-domain-dedication"}
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
    t = unicodedata.normalize("NFKD", str(licenca))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").strip().lower()
    t = re.sub(r"[\s_‐-―]+", "-", t)                  # espaços, sublinhado e hífens unicode
    pedacos = [p for p in t.split("-") if p and p not in _RUIDO and not re.fullmatch(r"\d+(\.\d+)*", p)]
    t = "-".join(pedacos)                              # tira versão ("4.0") sem tocar no "0" de cc0
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


def _limpo(texto):
    """Texto de uma linha só (créditos): sem quebras de linha nem caracteres de controle."""
    return re.sub(r"\s+", " ", "".join(c if c.isprintable() else " " for c in str(texto))).strip() if texto else texto


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
        """Guarda o arquivo (uma vez só) com a licença conferida e o liga ao perfil. Devolve o ativo (dict).

        Arquivo já presente (mesmo conteúdo): não duplica; passa a ser visível para este perfil com as
        etiquetas dele, e o ativo devolvido tem `duplicado=True`.
        """
        arquivo = Path(arquivo)
        if not arquivo.is_file():
            raise FileNotFoundError(f"arquivo não encontrado: {arquivo}")
        codigo, regras = conferir_licenca(licenca)
        if not str(fonte or "").strip():
            raise ErroLicenca("informe a fonte do arquivo (site, provedor ou 'produção própria')")
        autor, titulo = _limpo(autor), _limpo(titulo) or arquivo.stem
        if regras["credito"] and not autor:
            raise ErroLicenca(f"a licença {regras['nome']} exige crédito: informe o autor")
        if link and not re.match(r"^https?://\S+$", str(link).strip(), re.I):
            raise ErroLicenca("o link da fonte precisa começar com http:// ou https://")
        dono = perfil or ""
        digest = _hash(arquivo)
        if self._linha(digest):
            return self._duplicata(digest, arquivo, dono, tags)
        relativo = Path("ativos") / digest[:2] / f"{digest}{arquivo.suffix.lower()}"
        destino = self.raiz / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        criado = False
        if not destino.exists() or _hash(destino) != digest:  # ausente ou corrompido: copia de novo
            temporario = destino.with_suffix(destino.suffix + ".parcial")
            shutil.copyfile(arquivo, temporario)
            temporario.replace(destino)  # nunca deixa arquivo pela metade com nome final
            criado = True
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            with self.con:
                self.con.execute(
                    "INSERT INTO ativos (hash, tipo, caminho, provedor, modelo, prompt, parametros_json, licenca, "
                    "uso_comercial, fonte, tags, criado_em, autor, link, titulo, perfil) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ',', ?, ?, ?, ?, NULL)",
                    (digest, tipo_do_arquivo(arquivo), relativo.as_posix(), provedor, modelo, prompt,
                     json.dumps(parametros or {}, ensure_ascii=False, default=str), codigo,
                     int(regras["comercial"]), str(fonte).strip(), agora, autor, link, titulo))
                self.con.execute("INSERT INTO ativo_perfil (hash, perfil, tags) VALUES (?, ?, ?)",
                                 (digest, dono, self._tags_texto(_etiquetas(tags))))
        except sqlite3.IntegrityError:  # outro processo guardou o mesmo conteúdo agora
            return self._duplicata(digest, arquivo, dono, tags)
        except Exception:
            if criado:
                destino.unlink(missing_ok=True)  # sem linha no banco, não deixa arquivo órfão
            raise
        ativo = self.obter(digest, perfil)
        ativo["duplicado"] = False
        return ativo

    def _duplicata(self, digest, arquivo, dono, tags):
        linha = self._linha(digest)
        tipo = tipo_do_arquivo(arquivo)
        with self.con:
            if linha["tipo"] == "outro" and tipo != "outro":
                self.con.execute("UPDATE ativos SET tipo = ? WHERE hash = ?", (tipo, digest))
            self.con.execute("INSERT OR IGNORE INTO ativo_perfil (hash, perfil, tags) VALUES (?, ?, ',')",
                             (digest, dono))
        self.adicionar_tags(digest, tags, perfil=dono or None)
        ativo = self.obter(digest, dono or None)
        ativo["duplicado"] = True
        return ativo

    def adicionar_tags(self, digest, tags, perfil=None):
        """Soma etiquetas ao ativo **só para este perfil** (ou ao compartilhado, sem perfil)."""
        dono = perfil or ""
        linha = self.con.execute("SELECT tags FROM ativo_perfil WHERE hash = ? AND perfil = ?",
                                 (digest, dono)).fetchone()
        if not linha:
            raise KeyError(digest)
        atuais = [t for t in linha["tags"].split(",") if t]
        novas = sorted(set(atuais) | set(_etiquetas(tags)))
        with self.con:
            self.con.execute("UPDATE ativo_perfil SET tags = ? WHERE hash = ? AND perfil = ?",
                             (self._tags_texto(novas), digest, dono))

    # -- consulta -------------------------------------------------------------
    _SELECT = ("SELECT a.*, group_concat(l.tags, '') AS tags_visiveis FROM ativos a "
               "JOIN ativo_perfil l ON l.hash = a.hash WHERE l.perfil IN ('', ?) AND a.licenca IN ({}) ")

    def _sql_base(self):
        return self._SELECT.format(",".join("?" * len(LICENCAS)))

    def obter(self, digest, perfil=None):
        """Ativo visível para o perfil (compartilhado ou dele), com as etiquetas que ele pode ver."""
        sql = self._sql_base() + "AND a.hash = ? GROUP BY a.id"
        linha = self.con.execute(sql, [perfil or "", *LICENCAS, digest]).fetchone()
        return self._como_dict(linha) if linha else None

    def _linha(self, digest):
        return self.con.execute("SELECT * FROM ativos WHERE hash = ?", (digest,)).fetchone()

    def buscar(self, tags=(), tipo=None, texto=None, perfil=None, limite=50):
        """Ativos com TODAS as etiquetas pedidas. Mostra os compartilhados e os do perfil, nunca os de outro."""
        sql, args = self._sql_base(), [perfil or "", *LICENCAS]
        if tipo:
            sql, args = sql + "AND a.tipo = ? ", args + [tipo]
        if texto:
            alvo = "%" + str(texto).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            sql += ("AND (COALESCE(a.prompt,'') LIKE ? ESCAPE '\\' OR COALESCE(a.titulo,'') LIKE ? ESCAPE '\\'"
                    " OR COALESCE(a.autor,'') LIKE ? ESCAPE '\\' OR a.fonte LIKE ? ESCAPE '\\') ")
            args += [alvo] * 4
        sql += "GROUP BY a.id "
        etiquetas = _etiquetas(tags)
        if etiquetas:
            sql += "HAVING " + " AND ".join("tags_visiveis LIKE ?" for _ in etiquetas) + " "
            args += [f"%,{e},%" for e in etiquetas]
        sql += "ORDER BY a.id DESC LIMIT ?"
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
            partes = [_limpo(a.get("titulo")) or Path(a["caminho"]).name, f"por {_limpo(a['autor'])}",
                      LICENCAS[a["licenca"]]["nome"], _limpo(a["fonte"])]
            if a.get("link"):
                partes.append(_limpo(a["link"]))
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
        d.pop("perfil", None)  # o dono não é exposto: a visibilidade fica em ativo_perfil
        d["tags"] = sorted({t for t in (d.pop("tags_visiveis", None) or "").split(",") if t})
        d["parametros"] = json.loads(d.pop("parametros_json") or "{}")
        d["uso_comercial"] = bool(d["uso_comercial"])
        return d

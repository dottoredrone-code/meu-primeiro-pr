"""Biblioteca de mídia (K25, spec 05 seção 3, spec 11 "Regras de licença", D2, D18).

- Cada arquivo é guardado **uma vez só**, pelo hash do conteúdo: `ativos/ab/abcdef….ext`.
- **Licença obrigatória**: sem licença aceita, o arquivo não entra. Cada ativo guarda fonte, autor, link,
  licença, data e se permite uso comercial.
- **Busca por etiqueta** (todas as etiquetas pedidas), tipo e texto.
- Visibilidade e etiquetas ficam por perfil (tabela ativo_perfil): o mesmo arquivo pode servir a vários
  perfis, cada um com suas etiquetas e sua procedência (fonte, autor, licença, prompt), e nenhum vê o que o
  outro declarou nem que o outro usa o arquivo (D11). A tabela `ativos` guarda só hash, caminho e tipo.
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
             "personal-use": "uso_pessoal", "cc-pdm": "cc0", "attribution": "cc-by", "attribution-sharealike": "cc-by-sa",
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
    # só quando o campo inteiro é o link (texto misto como "CC BY-NC, veja …/by/" segue a regra do texto)
    url = re.fullmatch(r"\s*https?://(?:www\.)?creativecommons\.org/(publicdomain/(?:zero|mark)|licenses/([a-z\-]+))"
                       r"(?:/[\w./-]*)?\s*", str(licenca).lower())
    if url:  # Freesound e outros devolvem a licença como link
        return "cc0" if url.group(1).startswith("publicdomain") else _APELIDOS.get(url.group(2), "cc-" + url.group(2))
    if re.fullmatch(r"\s*creative[\s_-]*commons[\s_-]*(0|zero)\s*", str(licenca), re.I):
        return "cc0"  # nome usado pelo Freesound
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
        procedencia = {
            "licenca": codigo, "uso_comercial": int(regras["comercial"]), "fonte": str(fonte).strip(),
            "autor": autor, "link": link, "titulo": titulo, "provedor": provedor, "modelo": modelo,
            "prompt": prompt, "parametros_json": json.dumps(parametros or {}, ensure_ascii=False, default=str),
            "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        digest = _hash(arquivo)
        if self._linha(digest):
            return self._duplicata(digest, arquivo, dono, tags, procedencia)
        relativo = Path("ativos") / digest[:2] / f"{digest}{arquivo.suffix.lower()}"
        destino = self.raiz / relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        criado = False
        if not destino.exists() or _hash(destino) != digest:  # ausente ou corrompido: copia de novo
            temporario = destino.with_suffix(destino.suffix + ".parcial")
            shutil.copyfile(arquivo, temporario)
            temporario.replace(destino)  # nunca deixa arquivo pela metade com nome final
            criado = True
        try:
            with self.con:
                self.con.execute("INSERT INTO ativos (hash, tipo, caminho, tags, criado_em) VALUES (?, ?, ?, ',', ?)",
                                 (digest, tipo_do_arquivo(arquivo), relativo.as_posix(), procedencia["criado_em"]))
                self._ligar(digest, dono, tags, procedencia)
        except sqlite3.IntegrityError:  # outro processo guardou o mesmo conteúdo agora
            return self._duplicata(digest, arquivo, dono, tags, procedencia)
        except Exception:
            if criado:
                destino.unlink(missing_ok=True)  # sem linha no banco, não deixa arquivo órfão
            raise
        ativo = self.obter(digest, perfil)
        ativo["duplicado"] = False
        return ativo

    _COLUNAS = ("licenca", "uso_comercial", "fonte", "autor", "link", "titulo", "provedor", "modelo", "prompt",
                "parametros_json", "criado_em")

    def _ligar(self, digest, dono, tags, procedencia):
        """Liga o ativo ao perfil com a procedência que ESTE perfil declarou (não sobrescreve a existente)."""
        cols = ", ".join(self._COLUNAS)
        self.con.execute(
            f"INSERT OR IGNORE INTO ativo_perfil (hash, perfil, tags, {cols}) "
            f"VALUES (?, ?, ?, {', '.join('?' * len(self._COLUNAS))})",
            (digest, dono, self._tags_texto(_etiquetas(tags)), *(procedencia[c] for c in self._COLUNAS)))

    def _duplicata(self, digest, arquivo, dono, tags, procedencia):
        linha = self._linha(digest)
        tipo = tipo_do_arquivo(arquivo)
        with self.con:
            if linha["tipo"] == "outro" and tipo != "outro":
                self.con.execute("UPDATE ativos SET tipo = ? WHERE hash = ?", (tipo, digest))
            self._ligar(digest, dono, tags, procedencia)
            atual = self.con.execute("SELECT licenca FROM ativo_perfil WHERE hash = ? AND perfil = ?",
                                     (digest, dono)).fetchone()
            if atual["licenca"] not in LICENCAS:  # linha antiga sem licença aceita: vale a nova, já conferida
                sets = ", ".join(f"{c} = ?" for c in self._COLUNAS)
                self.con.execute(f"UPDATE ativo_perfil SET {sets} WHERE hash = ? AND perfil = ?",
                                 (*(procedencia[c] for c in self._COLUNAS), digest, dono))
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
    def _linhas_visiveis(self, digest, perfil):
        sql = (f"SELECT l.*, a.id, a.tipo, a.caminho FROM ativo_perfil l JOIN ativos a ON a.hash = l.hash "
               f"WHERE l.hash = ? AND l.perfil IN ('', ?) AND l.licenca IN ({','.join('?' * len(LICENCAS))})")
        return self.con.execute(sql, [digest, perfil or "", *LICENCAS]).fetchall()

    def obter(self, digest, perfil=None):
        """Ativo visível para o perfil: procedência do próprio perfil (ou a compartilhada) e etiquetas que ele vê."""
        linhas = self._linhas_visiveis(digest, perfil)
        if not linhas:
            return None
        propria = next((l for l in linhas if l["perfil"] == (perfil or "")), linhas[0])
        d = {k: propria[k] for k in ("id", "hash", "tipo", "caminho", *self._COLUNAS)}
        d["tags"] = sorted({t for l in linhas for t in l["tags"].split(",") if t})
        d["parametros"] = json.loads(d.pop("parametros_json") or "{}")
        d["uso_comercial"] = bool(d["uso_comercial"])
        return d

    def _linha(self, digest):
        return self.con.execute("SELECT * FROM ativos WHERE hash = ?", (digest,)).fetchone()

    def buscar(self, tags=(), tipo=None, texto=None, perfil=None, limite=50):
        """Ativos com TODAS as etiquetas pedidas. Mostra os compartilhados e os do perfil, nunca os de outro."""
        sql = (f"SELECT a.hash, group_concat(l.tags, '') AS tags_visiveis FROM ativos a "
               f"JOIN ativo_perfil l ON l.hash = a.hash "
               f"WHERE l.perfil IN ('', ?) AND l.licenca IN ({','.join('?' * len(LICENCAS))}) ")
        args = [perfil or "", *LICENCAS]
        if tipo:
            sql, args = sql + "AND a.tipo = ? ", args + [tipo]
        sql += "GROUP BY a.id "
        filtros = []
        for e in _etiquetas(tags):
            filtros.append("tags_visiveis LIKE ?")
            args.append(f"%,{e},%")
        if texto:
            alvo = "%" + str(texto).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            campos = ("prompt", "titulo", "autor", "fonte")
            filtros.append("(" + " OR ".join(
                f"group_concat(COALESCE(l.{c}, ''), char(10)) LIKE ? ESCAPE '\\'" for c in campos) + ")")
            args += [alvo] * len(campos)
        if filtros:
            sql += "HAVING " + " AND ".join(filtros) + " "
        sql += "ORDER BY a.id DESC LIMIT ?"
        args.append(int(limite))
        return [self.obter(l["hash"], perfil) for l in self.con.execute(sql, args)]

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


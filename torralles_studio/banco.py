"""Banco local (K24, spec 05 seção 2, D6): projetos, cenas, peças, tentativas, avaliações, custo e cache.

SQLite num arquivo só (backup = copiar o arquivo). O esquema evolui por migrações numeradas
(PRAGMA user_version). Resolve:
1. Retomar sem pagar de novo: peça já aprovada (ou à espera de revisão) não é refeita.
2. Cache: mesmo provedor + modelo + parâmetros → reaproveita o resultado em vez de gerar de novo.
3. Custo real por projeto, etapa, provedor e mês.
"""

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRACOES = [
    # 1 — esquema inicial (spec 05, 2.3)
    """
    CREATE TABLE projetos (
        id INTEGER PRIMARY KEY,
        titulo TEXT NOT NULL,
        perfil TEXT,
        formato TEXT,
        briefing_json TEXT,
        status TEXT NOT NULL DEFAULT 'em_andamento',
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL
    );
    CREATE TABLE cenas (
        id INTEGER PRIMARY KEY,
        projeto_id INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
        ordem INTEGER NOT NULL,
        narracao TEXT,
        prompt_imagem TEXT,
        prompt_movimento TEXT,
        duracao REAL,
        dados_json TEXT,
        UNIQUE (projeto_id, ordem)
    );
    CREATE TABLE pecas (
        id INTEGER PRIMARY KEY,
        projeto_id INTEGER NOT NULL REFERENCES projetos(id) ON DELETE CASCADE,
        etapa TEXT NOT NULL,
        chave TEXT NOT NULL,
        status TEXT NOT NULL,
        valor_json TEXT,
        provedor TEXT,
        nota REAL,
        revisar_manual INTEGER NOT NULL DEFAULT 0,
        motivo TEXT,
        custo_usd REAL NOT NULL DEFAULT 0,
        atualizado_em TEXT NOT NULL,
        UNIQUE (projeto_id, etapa, chave)
    );
    CREATE TABLE ativos (
        id INTEGER PRIMARY KEY,
        hash TEXT NOT NULL UNIQUE,
        tipo TEXT,
        caminho TEXT NOT NULL,
        provedor TEXT,
        modelo TEXT,
        prompt TEXT,
        parametros_json TEXT,
        licenca TEXT,
        uso_comercial INTEGER,
        fonte TEXT,
        tags TEXT,
        criado_em TEXT NOT NULL
    );
    CREATE TABLE tentativas (
        id INTEGER PRIMARY KEY,
        peca_id INTEGER NOT NULL REFERENCES pecas(id) ON DELETE CASCADE,
        numero INTEGER NOT NULL,
        etapa TEXT NOT NULL,
        provedor TEXT,
        ativo_id INTEGER REFERENCES ativos(id),
        status TEXT NOT NULL,
        custo_usd REAL NOT NULL DEFAULT 0,
        custos_json TEXT,
        valor_json TEXT,
        criado_em TEXT NOT NULL
    );
    CREATE TABLE avaliacoes (
        id INTEGER PRIMARY KEY,
        tentativa_id INTEGER NOT NULL REFERENCES tentativas(id) ON DELETE CASCADE,
        juizes_json TEXT,
        nota_final REAL,
        criterios_json TEXT,
        problemas_json TEXT,
        eliminatorios_json TEXT,
        aprovado INTEGER NOT NULL,
        revisar_manual INTEGER NOT NULL DEFAULT 0,
        sem_juiz INTEGER NOT NULL DEFAULT 0,
        nota_humana REAL
    );
    CREATE TABLE cache (
        chave TEXT PRIMARY KEY,
        provedor TEXT NOT NULL,
        modelo TEXT,
        valor_json TEXT NOT NULL,
        usos INTEGER NOT NULL DEFAULT 0,
        criado_em TEXT NOT NULL,
        ultimo_uso TEXT
    );
    CREATE TABLE memoria (
        id INTEGER PRIMARY KEY,
        tipo TEXT NOT NULL,
        chave TEXT,
        conteudo TEXT NOT NULL,
        origem TEXT,
        relevancia REAL,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL
    );
    CREATE INDEX idx_tentativas_peca ON tentativas(peca_id);
    CREATE INDEX idx_pecas_projeto ON pecas(projeto_id);
    """,
]

# Parâmetros que não mudam o resultado (caminho de saída) e parâmetros que são arquivos (vale o conteúdo).
_FORA_DA_CHAVE = {"saida"}
_ARQUIVOS = {"imagem", "audio", "video"}
_PRONTOS = ("aprovado", "revisar")


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _codificar(valor):
    """Valor de provedor → JSON. Arquivos viram {"__arquivo__": caminho}. Devolve None se não der."""
    def conv(v):
        if isinstance(v, Path):
            return {"__arquivo__": str(v)}
        if isinstance(v, dict):
            return {str(k): conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if v is None or isinstance(v, (str, int, float, bool)):
            return v
        raise TypeError(type(v).__name__)

    try:
        return json.dumps(conv(valor), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return None


def _decodificar(texto):
    if texto is None:
        return None

    def conv(v):
        if isinstance(v, dict):
            if set(v) == {"__arquivo__"}:
                return Path(v["__arquivo__"])
            return {k: conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v

    return conv(json.loads(texto))


def chave_cache(provedor, modelo, kwargs):
    """Hash de provedor + modelo + parâmetros (spec 05, 2.2). Arquivos de entrada entram pelo conteúdo."""
    partes = {}
    for nome, valor in sorted(kwargs.items()):
        if nome in _FORA_DA_CHAVE:
            continue
        if nome in _ARQUIVOS and valor and Path(valor).is_file():
            valor = {"sha256": _hash_arquivo(valor)}
        elif isinstance(valor, Path):
            valor = str(valor)
        partes[nome] = valor
    bruto = json.dumps({"provedor": provedor, "modelo": modelo or "", "kwargs": partes},
                       ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(bruto.encode()).hexdigest()


class Banco:
    def __init__(self, caminho=":memory:", pasta_cache=None):
        self.caminho = str(caminho)
        if self.caminho != ":memory:":
            Path(self.caminho).parent.mkdir(parents=True, exist_ok=True)
        self.pasta_cache = Path(pasta_cache) if pasta_cache else (
            Path(self.caminho).parent / "cache" if self.caminho != ":memory:" else None)
        self.con = sqlite3.connect(self.caminho)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        if self.caminho != ":memory:":
            self.con.execute("PRAGMA journal_mode = WAL")
        self.migrar()

    # -- esquema ------------------------------------------------------------
    @property
    def versao(self):
        return self.con.execute("PRAGMA user_version").fetchone()[0]

    def migrar(self):
        """Aplica, em ordem, as migrações que faltam. Cada uma roda inteira ou não roda."""
        for numero in range(self.versao, len(MIGRACOES)):
            with self.con:
                self.con.execute("BEGIN")
                for comando in MIGRACOES[numero].split(";"):
                    if comando.strip():
                        self.con.execute(comando)
                self.con.execute(f"PRAGMA user_version = {numero + 1}")

    def fechar(self):
        self.con.close()

    # -- projetos e cenas ---------------------------------------------------
    def criar_projeto(self, titulo, briefing=None, formato=None, perfil=None):
        agora = _agora()
        with self.con:
            cur = self.con.execute(
                "INSERT INTO projetos (titulo, perfil, formato, briefing_json, criado_em, atualizado_em) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (titulo, perfil, formato, json.dumps(briefing or {}, ensure_ascii=False), agora, agora))
        return cur.lastrowid

    def projeto(self, projeto_id):
        linha = self.con.execute("SELECT * FROM projetos WHERE id = ?", (projeto_id,)).fetchone()
        if not linha:
            return None
        dados = dict(linha)
        dados["briefing"] = json.loads(dados.pop("briefing_json") or "{}")
        dados["custo_total_usd"] = self.custo_projeto(projeto_id)["total"]
        return dados

    def mudar_status(self, projeto_id, status):
        with self.con:
            self.con.execute("UPDATE projetos SET status = ?, atualizado_em = ? WHERE id = ?",
                             (status, _agora(), projeto_id))

    def salvar_cenas(self, projeto_id, cenas):
        with self.con:
            for ordem, c in enumerate(cenas, 1):
                extras = {k: v for k, v in c.items()
                          if k not in ("narracao", "prompt_imagem", "prompt_movimento", "duracao")}
                self.con.execute(
                    "INSERT INTO cenas (projeto_id, ordem, narracao, prompt_imagem, prompt_movimento, duracao, dados_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (projeto_id, ordem) DO UPDATE SET "
                    "narracao = excluded.narracao, prompt_imagem = excluded.prompt_imagem, "
                    "prompt_movimento = excluded.prompt_movimento, duracao = excluded.duracao, "
                    "dados_json = excluded.dados_json",
                    (projeto_id, ordem, c.get("narracao"), c.get("prompt_imagem"), c.get("prompt_movimento"),
                     c.get("duracao"), json.dumps(extras, ensure_ascii=False)))
            self.con.execute("DELETE FROM cenas WHERE projeto_id = ? AND ordem > ?", (projeto_id, len(cenas)))

    def cenas(self, projeto_id):
        linhas = self.con.execute("SELECT * FROM cenas WHERE projeto_id = ? ORDER BY ordem", (projeto_id,))
        saida = []
        for linha in linhas:
            d = dict(linha)
            extras = json.loads(d.pop("dados_json") or "{}")
            saida.append({**extras, **{k: d[k] for k in ("ordem", "narracao", "prompt_imagem",
                                                          "prompt_movimento", "duracao")}})
        return saida

    # -- peças (checkpoint) -------------------------------------------------
    def peca(self, projeto_id, etapa, chave):
        linha = self.con.execute("SELECT * FROM pecas WHERE projeto_id = ? AND etapa = ? AND chave = ?",
                                 (projeto_id, etapa, chave)).fetchone()
        if not linha:
            return None
        d = dict(linha)
        d["valor"] = _decodificar(d.pop("valor_json"))
        d["revisar_manual"] = bool(d["revisar_manual"])
        return d

    def peca_pronta(self, projeto_id, etapa, chave, aceitar_revisar=True):
        """Peça que não deve ser refeita: aprovada, ou à espera da sua revisão (já foi paga)."""
        p = self.peca(projeto_id, etapa, chave)
        if not p or p["status"] not in (_PRONTOS if aceitar_revisar else ("aprovado",)):
            return None
        if isinstance(p["valor"], Path) and not p["valor"].exists():
            return None  # arquivo sumiu: precisa refazer
        return p

    def registrar_peca(self, projeto_id, etapa, chave, resultado):
        """Guarda o resultado do loop de correção (K09): peça, tentativas e avaliações, numa transação."""
        if resultado.aprovado:
            status = "aprovado"
        elif resultado.valor is not None:
            status = "revisar"
        else:
            status = "falhou"
        custo = sum(t.custo_usd for t in resultado.tentativas)
        agora = _agora()
        with self.con:
            self.con.execute(
                "INSERT INTO pecas (projeto_id, etapa, chave, status, valor_json, provedor, nota, revisar_manual, "
                "motivo, custo_usd, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (projeto_id, etapa, chave) DO UPDATE SET status = excluded.status, "
                "valor_json = excluded.valor_json, provedor = excluded.provedor, nota = excluded.nota, "
                "revisar_manual = excluded.revisar_manual, motivo = excluded.motivo, "
                "custo_usd = pecas.custo_usd + excluded.custo_usd, atualizado_em = excluded.atualizado_em",
                (projeto_id, etapa, chave, status, _codificar(resultado.valor), resultado.provedor,
                 resultado.nota, int(resultado.revisar_manual), resultado.motivo, custo, agora))
            peca_id = self.con.execute("SELECT id FROM pecas WHERE projeto_id = ? AND etapa = ? AND chave = ?",
                                       (projeto_id, etapa, chave)).fetchone()[0]
            base = self.con.execute("SELECT COALESCE(MAX(numero), 0) FROM tentativas WHERE peca_id = ?",
                                    (peca_id,)).fetchone()[0]
            for t in resultado.tentativas:
                av = t.avaliacao
                cur = self.con.execute(
                    "INSERT INTO tentativas (peca_id, numero, etapa, provedor, status, custo_usd, custos_json, "
                    "valor_json, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (peca_id, base + t.numero, etapa, t.provedor, "aprovado" if av.aprovado else "reprovado",
                     t.custo_usd, json.dumps(t.custos), _codificar(t.valor), agora))
                self.con.execute(
                    "INSERT INTO avaliacoes (tentativa_id, juizes_json, nota_final, criterios_json, problemas_json, "
                    "eliminatorios_json, aprovado, revisar_manual, sem_juiz) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (cur.lastrowid, json.dumps(av.juizes), av.nota, json.dumps(av.criterios, ensure_ascii=False),
                     json.dumps(av.problemas, ensure_ascii=False), json.dumps(av.eliminatorios, ensure_ascii=False),
                     int(av.aprovado), int(av.revisar_manual), int(av.sem_juiz)))
            self.con.execute("UPDATE projetos SET atualizado_em = ? WHERE id = ?", (agora, projeto_id))
        return self.peca(projeto_id, etapa, chave)

    def produzir(self, projeto_id, etapa, chave, fazer, aceitar_revisar=True):
        """Checkpoint: devolve a peça pronta sem chamar `fazer`; senão roda `fazer()` (o loop) e guarda.

        Devolve (peça, reaproveitada).
        """
        pronta = self.peca_pronta(projeto_id, etapa, chave, aceitar_revisar)
        if pronta:
            return pronta, True
        return self.registrar_peca(projeto_id, etapa, chave, fazer()), False

    def tentativas(self, projeto_id, etapa=None, chave=None):
        sql = ("SELECT t.*, p.chave, a.nota_final, a.aprovado AS aval_aprovado, a.problemas_json FROM tentativas t "
               "JOIN pecas p ON p.id = t.peca_id LEFT JOIN avaliacoes a ON a.tentativa_id = t.id "
               "WHERE p.projeto_id = ?")
        args = [projeto_id]
        if etapa:
            sql, args = sql + " AND p.etapa = ?", args + [etapa]
        if chave:
            sql, args = sql + " AND p.chave = ?", args + [chave]
        return [dict(l) for l in self.con.execute(sql + " ORDER BY t.id", args)]

    # -- custo --------------------------------------------------------------
    def custo_projeto(self, projeto_id):
        por_etapa, por_provedor, total = {}, {}, 0.0
        for t in self.tentativas(projeto_id):
            total += t["custo_usd"]
            por_etapa[t["etapa"]] = por_etapa.get(t["etapa"], 0.0) + t["custo_usd"]
            for prov, valor in json.loads(t["custos_json"] or "{}").items():
                por_provedor[prov] = por_provedor.get(prov, 0.0) + valor
        arred = lambda d: {k: round(v, 4) for k, v in d.items()}
        return {"total": round(total, 4), "por_etapa": arred(por_etapa), "por_provedor": arred(por_provedor)}

    def custo_mes(self, ano_mes):
        """Gasto do mês, ex.: custo_mes("2026-10")."""
        linha = self.con.execute("SELECT COALESCE(SUM(custo_usd), 0) FROM tentativas WHERE criado_em LIKE ?",
                                 (f"{ano_mes}-%",)).fetchone()
        return round(linha[0], 4)

    # -- cache --------------------------------------------------------------
    def cache_buscar(self, chave, saida=None):
        """Resultado guardado para a chave, ou None. Arquivo é copiado para `saida` (se dada)."""
        linha = self.con.execute("SELECT valor_json FROM cache WHERE chave = ?", (chave,)).fetchone()
        if not linha:
            return None
        valor = _decodificar(linha[0])
        if isinstance(valor, Path):
            if not valor.is_file():
                with self.con:
                    self.con.execute("DELETE FROM cache WHERE chave = ?", (chave,))
                return None
            if saida:
                saida = Path(saida)
                saida.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(valor, saida)
                valor = saida
        with self.con:
            self.con.execute("UPDATE cache SET usos = usos + 1, ultimo_uso = ? WHERE chave = ?", (_agora(), chave))
        return valor

    def cache_guardar(self, chave, provedor, modelo, valor):
        """Guarda o resultado. Arquivos são copiados para a pasta do cache (o original pode ser apagado)."""
        if isinstance(valor, Path):
            if self.pasta_cache is None or not valor.is_file():
                return False
            self.pasta_cache.mkdir(parents=True, exist_ok=True)
            copia = self.pasta_cache / f"{chave}{valor.suffix}"
            shutil.copyfile(valor, copia)
            valor = copia.resolve()
        texto = _codificar(valor)
        if texto is None:
            return False
        with self.con:
            self.con.execute(
                "INSERT INTO cache (chave, provedor, modelo, valor_json, criado_em) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (chave) DO UPDATE SET valor_json = excluded.valor_json",
                (chave, provedor, modelo, texto, _agora()))
        return True

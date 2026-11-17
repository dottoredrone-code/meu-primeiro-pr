"""Cotas gratuitas que duram entre uma execução e outra (K34, spec 14 §B) e licença por modalidade (D24, §C).

Config de um provedor com cota (tudo opcional, em [provedores.X.cota]):
    conta = "pollinations"          # créditos são da conta: provedores da mesma conta somam juntos
    limite = 100                    # créditos por período; sem limite, só o aviso do serviço esgota
    renova = "00:00 UTC"            # "HH:MM UTC" (horário fixo), "24h corridas" ou "mensal:D" (dia do mês)
    padroes = ["daily quota"]       # trechos da mensagem de erro que significam "créditos acabaram"
    creditos = { imagem = 1, animar = 10 }   # quanto cada modalidade gasta (padrão 1)

Horários ficam em UTC no banco e aparecem no horário de Brasília (UTC−3, sem horário de verão desde 2019).
"""

import re
from datetime import datetime, timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3), "Brasília")
RETRY_AFTER_COTA_S = 3600  # Retry-After maior que isso conta como cota esgotada
ESGOTADO_SEM_RENOVACAO = timedelta(hours=24)  # esgotou e o config não diz quando renova

# Modalidades da fila de mídia (spec 14): a licença por modalidade vale só para elas.
MODALIDADES = ("imagem", "editar_imagem", "animar", "video_texto", "editar_video")
REGRAS_LICENCA = ("comercial", "como_freesound")
APELIDOS_MODALIDADE = {"video": "animar"}  # nome antigo da tarefa imagem → vídeo


def modalidade(tarefa):
    return APELIDOS_MODALIDADE.get(tarefa, tarefa)
LICENCAS = ("comercial", "nao_comercial", "a_conferir")


def agora_utc():
    return datetime.now(timezone.utc)


def hora_local(quando):
    """dd/mm às HH:MM no horário de Brasília."""
    return quando.astimezone(BRASILIA).strftime("%d/%m às %H:%M")


def config_cota(provedor):
    cota = provedor.cfg.get("cota")
    return cota if isinstance(cota, dict) else {}


def conta_de(nome, provedor):
    return str(config_cota(provedor).get("conta") or nome)


def creditos_de(provedor, tarefa):
    creditos = config_cota(provedor).get("creditos")
    if isinstance(creditos, dict):
        valor = creditos.get(modalidade(tarefa), creditos.get(tarefa, 1))
    elif isinstance(creditos, (int, float)) and not isinstance(creditos, bool):
        valor = creditos
    else:
        valor = 1
    return float(valor)


def validar_renova(renova):
    """Erro (texto) se o formato de `renova` não for reconhecido; None se estiver certo."""
    if renova is None:
        return None
    if not isinstance(renova, str):
        return "renova precisa ser texto"
    r = renova.strip().lower()
    if r == "24h corridas":
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2}) utc", r)
    if m and int(m[1]) < 24 and int(m[2]) < 60:
        return None
    m = re.fullmatch(r"mensal:(\d{1,2})", r)
    if m and 1 <= int(m[1]) <= 28:
        return None
    return f"renova {renova!r} inválido (use 'HH:MM UTC', '24h corridas' ou 'mensal:D', com D de 1 a 28)"


def proxima_renovacao(renova, inicio):
    """Quando o período que começou em `inicio` acaba. None = sem período (só o aviso do serviço esgota)."""
    if renova is None or validar_renova(renova):
        return None
    inicio = inicio.astimezone(timezone.utc)
    r = renova.strip().lower()
    if r == "24h corridas":
        return inicio + timedelta(hours=24)
    m = re.fullmatch(r"(\d{1,2}):(\d{2}) utc", r)
    if m:
        alvo = inicio.replace(hour=int(m[1]), minute=int(m[2]), second=0, microsecond=0)
        return alvo if alvo > inicio else alvo + timedelta(days=1)
    dia = int(r.split(":")[1])
    alvo = inicio.replace(day=dia, hour=0, minute=0, second=0, microsecond=0)
    if alvo > inicio:
        return alvo
    ano, mes = (inicio.year + 1, 1) if inicio.month == 12 else (inicio.year, inicio.month + 1)
    return alvo.replace(year=ano, month=mes)


def _iso(quando):
    """Texto ISO em UTC (ordena certo como texto no SQLite)."""
    return quando.astimezone(timezone.utc).isoformat() if quando is not None else None


def _ler(texto):
    if not texto:
        return None
    quando = datetime.fromisoformat(texto)
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


class Cotas:
    """Contador de créditos por conta, guardado no banco (tabela `cotas`, migração 9)."""

    def __init__(self, banco, relogio=agora_utc):
        self.banco = banco
        self._relogio = relogio

    def agora(self):
        return self._relogio()

    def _linha(self, conta):
        return self.banco.con.execute("SELECT * FROM cotas WHERE conta = ?", (conta,)).fetchone()

    def estado(self, conta, cota=None):
        """{usado, inicio, renova_em, esgotado_ate, motivo} já considerando a virada do período."""
        linha = self._linha(conta)
        agora = self.agora()
        if linha is None:
            return {"usado": 0.0, "inicio": None, "renova_em": None, "esgotado_ate": None, "motivo": None}
        estado = {"usado": float(linha["usado"]), "inicio": _ler(linha["inicio"]),
                  "renova_em": _ler(linha["renova_em"]), "esgotado_ate": _ler(linha["esgotado_ate"]),
                  "motivo": linha["motivo"]}
        if estado["renova_em"] is not None and estado["renova_em"] <= agora:
            estado.update(usado=0.0, inicio=None, renova_em=None)
        if estado["esgotado_ate"] is not None and estado["esgotado_ate"] <= agora:
            estado.update(esgotado_ate=None, motivo=None)
        return estado

    def _gravar(self, conta, estado):
        iso = _iso
        with self.banco.con:
            self.banco.con.execute(
                "INSERT INTO cotas (conta, usado, inicio, renova_em, esgotado_ate, motivo, atualizado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(conta) DO UPDATE SET usado = excluded.usado, "
                "inicio = excluded.inicio, renova_em = excluded.renova_em, esgotado_ate = excluded.esgotado_ate, "
                "motivo = excluded.motivo, atualizado_em = excluded.atualizado_em",
                (conta, estado["usado"], iso(estado["inicio"]), iso(estado["renova_em"]), iso(estado["esgotado_ate"]),
                 estado["motivo"], iso(self.agora())))

    def bloqueio(self, conta, cota, creditos=1.0):
        """Motivo para pular (texto) ou None se ainda há crédito."""
        estado = self.estado(conta, cota)
        if estado["esgotado_ate"] is not None:
            return f"cota acabou, volta {hora_local(estado['esgotado_ate'])}"
        limite = cota.get("limite")
        if isinstance(limite, (int, float)) and not isinstance(limite, bool) and estado["usado"] + creditos > limite:
            volta = estado["renova_em"]
            return (f"cota acabou ({estado['usado']:g} de {limite:g} créditos), "
                    + (f"volta {hora_local(volta)}" if volta else "sem data de renovação no config"))
        return None

    def gastar(self, conta, cota, creditos=1.0):
        """Soma créditos de forma atômica: dois processos gastando juntos não perdem um gasto."""
        agora = self.agora()
        renova = proxima_renovacao(cota.get("renova"), agora)
        a, r = _iso(agora), _iso(renova)
        with self.banco.con:
            self.banco.con.execute(
                "INSERT INTO cotas (conta, usado, inicio, renova_em, atualizado_em) VALUES (?, 0, ?, ?, ?) "
                "ON CONFLICT(conta) DO NOTHING", (conta, a, r, a))
            # período vencido ou ainda não começado: começa outro (zera o gasto) na mesma transação
            self.banco.con.execute(
                "UPDATE cotas SET usado = 0, inicio = ?, renova_em = ? WHERE conta = ? AND "
                "(inicio IS NULL OR (renova_em IS NOT NULL AND renova_em <= ?))", (a, r, conta, a))
            self.banco.con.execute("UPDATE cotas SET usado = usado + ?, atualizado_em = ? WHERE conta = ?",
                                   (float(creditos), a, conta))

    def esgotar(self, conta, cota, motivo, segundos=None):
        """Marca a conta como esgotada até a renovação (ou por `segundos`, se o serviço disse quanto esperar)."""
        estado = self.estado(conta, cota)
        agora = self.agora()
        if segundos is not None:
            ate = agora + timedelta(seconds=segundos)
        else:
            ate = estado["renova_em"] or proxima_renovacao(cota.get("renova"), agora) or agora + ESGOTADO_SEM_RENOVACAO
        if estado["inicio"] is None:
            estado["inicio"] = agora
            estado["renova_em"] = proxima_renovacao(cota.get("renova"), agora)
        estado.update(esgotado_ate=ate, motivo=str(motivo)[:200])
        self._gravar(conta, estado)
        return ate

    def liberar(self, conta):
        with self.banco.con:
            self.banco.con.execute("DELETE FROM cotas WHERE conta = ?", (conta,))

    def listar(self):
        contas = [r["conta"] for r in self.banco.con.execute("SELECT conta FROM cotas ORDER BY conta")]
        return {c: self.estado(c) for c in contas}


def cota_esgotada(erro, cota):
    """O erro do serviço diz que os créditos acabaram? Só por padrão declarado ou Retry-After longo.

    Um 429 comum ("rate limit", excesso por minuto) não esgota: continua com o descanso curto do roteador.
    """
    texto = str(erro).lower()
    padroes = cota.get("padroes") or []
    if isinstance(padroes, str):
        padroes = [padroes]
    if any(str(p).strip() and str(p).lower() in texto for p in padroes):
        return True
    retry = getattr(erro, "retry_after", None)
    return retry is not None and retry > RETRY_AFTER_COTA_S


# ---------------------------------------------------------------- licença (D24)

def licenca_do_provedor(provedor):
    """'comercial', 'nao_comercial' ou 'a_conferir'. Sem o campo: o antigo somente_nao_comercial (Freesound)
    vale como não comercial; pagos e locais (Ken Burns) contam como comerciais (spec 14 §C)."""
    licenca = provedor.cfg.get("licenca")
    if licenca is None:
        return "nao_comercial" if provedor.cfg.get("somente_nao_comercial") else "comercial"
    return str(licenca)


def bloqueio_de_licenca(provedor, tarefa, *, comercial=True, regras=None):
    """Motivo para pular o provedor nesta modalidade (texto) ou None.

    `a_conferir` nunca entra, em nenhuma tarefa. Marca d'água e licença só valem nas modalidades da fila de
    mídia; as buscas de mídia (midia_*) seguem com a regra própria delas (midia.py, D22).
    """
    licenca = licenca_do_provedor(provedor)
    if licenca == "a_conferir":
        return "licença a conferir: leia os termos e anote no config antes de usar (D24)"
    tarefa = modalidade(tarefa)
    if tarefa not in MODALIDADES:
        return None
    if provedor.cfg.get("marca_dagua"):
        return "o plano grátis põe marca d'água (D24)"
    if licenca == "nao_comercial":
        regra = (regras or {}).get(tarefa, "comercial")
        if regra != "como_freesound":
            return f"licença só não comercial; a regra de '{tarefa}' no perfil é 'comercial' (D24)"
        if comercial:
            return "licença só não comercial e o perfil é comercial (D24)"
    return None

"""Sites gratuitos de imagem e vídeo operados pelo Claude no navegador do Claude (K37, spec 14 §E e §F.4).

O Studio não abre site nenhum: ele grava os pedidos (`saidas/<tema>/navegador/pedidos.json`), a skill
`.claude/skills/midia-navegador` cola o prompt no site, baixa o resultado como `<id>.<ext>` na mesma pasta, e o
`importar-midia` confere cada arquivo e o registra com o serviço e a licença do config (nunca do arquivo).

Estados do pedido (no banco, tabela pedidos_navegador): pendente → importado → aprovado | refazer.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .cotas import MODALIDADES, bloqueio_de_licenca, modalidade as _modalidade
from .prompts_midia import PromptReprovado, neutro_da_cena, preparar

PASTA = "navegador"
ARQUIVO_PEDIDOS = "pedidos.json"
# Assinatura dos primeiros bytes → tipo (a extensão não vale: o arquivo pode mentir)
_ASSINATURAS = [
    (b"\x89PNG\r\n\x1a\n", "imagem", ".png"),
    (b"\xff\xd8\xff", "imagem", ".jpg"),
]
EXTENSOES = {".png": "imagem", ".jpg": "imagem", ".jpeg": "imagem", ".webp": "imagem",
             ".mp4": "video", ".mov": "video", ".webm": "video"}


class ErroNavegador(Exception):
    pass


class _Site:
    """Site como 'provedor' só para reaproveitar as regras de licença e cota (cotas.py)."""

    def __init__(self, nome, cfg):
        self.nome, self.cfg = nome, cfg


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sites_do_config(dados):
    return {nome: _Site(nome, cfg) for nome, cfg in (dados.get("sites") or {}).items() if isinstance(cfg, dict)}


def fila_de_sites(sites, modalidade, *, cotas=None, comercial=True, regras=None):
    """[(site, motivo ou None)] na ordem do config: motivo diz por que o site está fora agora."""
    from .cotas import config_cota, conta_de, creditos_de

    modalidade = _modalidade(modalidade)
    fila = []
    for nome, site in sites.items():
        if modalidade not in (site.cfg.get("modalidades") or []):
            continue
        motivo = bloqueio_de_licenca(site, modalidade, comercial=comercial, regras=regras)
        if not motivo and cotas is not None:
            motivo = cotas.bloqueio(conta_de(nome, site), config_cota(site), creditos_de(site, modalidade))
        fila.append((nome, motivo))
    return fila


def tipo_pelos_bytes(cabeca):
    """'imagem' ou 'video' pelos primeiros bytes; None se não reconhecer."""
    for assinatura, tipo, _ in _ASSINATURAS:
        if cabeca.startswith(assinatura):
            return tipo
    if cabeca[:4] == b"RIFF" and cabeca[8:12] == b"WEBP":
        return "imagem"
    if cabeca[4:8] == b"ftyp":  # MP4 / MOV
        return "video"
    if cabeca[:4] == b"\x1aE\xdf\xa3":  # WebM / Matroska
        return "video"
    return None


def _sondar(arquivo):
    """Fluxo de imagem do arquivo pelo ffprobe comum (percepcao.sondar: prazo, UTF-8, sem capa embutida)."""
    from .percepcao import sondar
    from .rede import ErroProvedor

    try:
        fluxos = sondar(arquivo, "stream=codec_type,width,height:stream_disposition=attached_pic").get("streams") or []
    except ErroProvedor as e:
        raise ErroNavegador(f"o arquivo não abre como imagem ou vídeo ({e})") from None
    video = next((f for f in fluxos if f.get("codec_type") == "video"), None)
    if not video or not video.get("width"):
        raise ErroNavegador("o arquivo não tem imagem")
    return video


class Navegador:
    def __init__(self, banco, sites, *, cotas=None, tamanho_maximo_mb=300):
        self.banco = banco
        self.sites = sites
        self.cotas = cotas
        self.tamanho_maximo = int(tamanho_maximo_mb * 1024 * 1024)

    # -- pedidos ---------------------------------------------------------------
    def criar_pedidos(self, pasta_tema, cenas, modalidade="imagem", *, perfil=None, proporcao=None,
                      feedback=None):
        """Grava um pedido por cena (dict com 'indice' e os campos do roteiro) com o prompt de cada site da fila.

        feedback: {indice: texto do juiz} para refazer (o prompt seguinte leva a correção).
        """
        modalidade = _modalidade(modalidade)
        if modalidade not in MODALIDADES:
            raise ErroNavegador(f"modalidade {modalidade!r} não existe (use {', '.join(MODALIDADES)})")
        comercial = getattr(perfil, "comercial", True)
        regras = getattr(perfil, "licenca_por_modalidade", None) or {}
        fila = fila_de_sites(self.sites, modalidade, cotas=self.cotas, comercial=comercial, regras=regras)
        disponiveis = [nome for nome, motivo in fila if not motivo]
        pasta = Path(pasta_tema) / PASTA
        pasta.mkdir(parents=True, exist_ok=True)
        pedidos = []
        for cena in cenas:
            indice = int(cena["indice"])
            correcao = (feedback or {}).get(indice)
            base = dict(cena)
            if correcao:  # a correção do juiz vai num campo próprio (não passa pela checagem de texto pedido)
                base["correcao"] = correcao
            neutro = neutro_da_cena(base, modalidade, perfil=perfil, proporcao=proporcao)
            prompts, problemas = {}, []
            for nome in disponiveis:
                molde = self.sites[nome].cfg.get("molde")
                try:
                    pronto = preparar(molde or nome, neutro, perfil=perfil)
                except PromptReprovado as e:
                    problemas.append(str(e))
                    continue
                prompts[nome] = {"prompt": pronto["prompt"], "negativo": pronto["negativo"]}
            pid = f"c{indice:02d}-{modalidade}"
            anterior = self.pedido(pid, pasta_tema)
            reabrir = anterior is None or anterior["estado"] in ("pendente", "refazer") or bool(correcao)
            if anterior is not None and not reabrir:  # já importado/aprovado: não volta a pendente nem gasta de novo
                pedidos.append({"id": pid, "cena": indice, "modalidade": modalidade, "estado": anterior["estado"]})
                continue
            tentativas = (anterior["tentativas"] + 1) if anterior and anterior["estado"] == "refazer" else \
                (anterior or {}).get("tentativas", 1)
            with self.banco.con:
                self.banco.con.execute(
                    "INSERT INTO pedidos_navegador (id, pasta, cena, modalidade, estado, tentativas, prompts_json, "
                    "entrada, motivo, criado_em, atualizado_em) VALUES (?, ?, ?, ?, 'pendente', ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id, pasta) DO UPDATE SET estado = 'pendente', tentativas = excluded.tentativas, "
                    "prompts_json = excluded.prompts_json, entrada = excluded.entrada, motivo = excluded.motivo, "
                    "atualizado_em = excluded.atualizado_em",
                    (pid, str(Path(pasta_tema).resolve()), indice, modalidade, tentativas,
                     json.dumps(prompts, ensure_ascii=False), cena.get("entrada"),
                     "; ".join(problemas) or None, _agora(), _agora()))
            pedidos.append({"id": pid, "cena": indice, "modalidade": modalidade, "tentativa": tentativas,
                            "entrada": cena.get("entrada"), "prompts": prompts,
                            "arquivo_esperado": f"{pid}.<png|jpg|webp|mp4>",
                            **({"problemas": problemas} if problemas else {})})
        dados = {"modalidade": modalidade, "fila": [{"site": n, "fora": m} for n, m in fila],
                 "sites": {n: {"endereco": self.sites[n].cfg.get("endereco"),
                               "licenca": self.sites[n].cfg.get("licenca")} for n in disponiveis},
                 "pedidos": pedidos}
        (pasta / ARQUIVO_PEDIDOS).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return dados

    def pedido(self, pid, pasta_tema=None):
        sql, args = "SELECT * FROM pedidos_navegador WHERE id = ?", [pid]
        if pasta_tema is not None:
            sql += " AND pasta = ?"
            args.append(str(Path(pasta_tema).resolve()))
        linha = self.banco.con.execute(sql, args).fetchone()
        return dict(linha) if linha else None

    def pedidos(self, pasta_tema, estado=None):
        sql, args = "SELECT * FROM pedidos_navegador WHERE pasta = ?", [str(Path(pasta_tema).resolve())]
        if estado:
            sql += " AND estado = ?"
            args.append(estado)
        return [dict(r) for r in self.banco.con.execute(sql + " ORDER BY cena", args)]

    def marcar(self, pasta_tema, pid, estado, *, nota=None, motivo=None):
        if estado not in ("pendente", "importado", "aprovado", "refazer", "revisar"):
            raise ErroNavegador(f"estado inválido: {estado}")
        with self.banco.con:
            self.banco.con.execute(
                "UPDATE pedidos_navegador SET estado = ?, nota = COALESCE(?, nota), motivo = COALESCE(?, motivo), "
                "atualizado_em = ? WHERE id = ? AND pasta = ?",
                (estado, nota, motivo, _agora(), pid, str(Path(pasta_tema).resolve())))

    # -- importação segura -----------------------------------------------------------
    def importar(self, pasta_tema, biblioteca=None, *, site=None, perfil=None):
        """Confere e registra os arquivos baixados. Devolve (importados, problemas).

        site: de qual site veio (obrigatório quando a fila tem mais de um disponível; a licença vem dele).
        """
        raiz = (Path(pasta_tema) / PASTA).resolve()
        if not raiz.is_dir():
            raise ErroNavegador(f"pasta não encontrada: {raiz}")
        importados, problemas = [], []
        for arquivo in sorted(raiz.iterdir()):
            if arquivo.name == ARQUIVO_PEDIDOS or arquivo.name.startswith("."):
                continue
            try:
                importados.append(self._importar_um(raiz, arquivo, pasta_tema, biblioteca, site, perfil))
            except ErroNavegador as e:
                problemas.append(f"{arquivo.name}: {e}")
        return importados, problemas

    def _importar_um(self, raiz, arquivo, pasta_tema, biblioteca, site, perfil):
        if arquivo.is_symlink() or not arquivo.is_file():
            raise ErroNavegador("não é um arquivo comum (atalho ou pasta): ignorado")
        real = arquivo.resolve()
        if not real.is_relative_to(raiz):
            raise ErroNavegador("fora da pasta do navegador: ignorado")
        pid, ext = arquivo.stem, arquivo.suffix.lower()
        pedido = self.pedido(pid, pasta_tema)
        if pedido is None:
            raise ErroNavegador("nome não corresponde a nenhum pedido (use <id do pedido>.<ext>)")
        if pedido["estado"] != "pendente":
            raise ErroNavegador(f"pedido já está '{pedido['estado']}'")
        tamanho = os.stat(real).st_size  # antes de abrir: arquivo gigante nem é lido
        if tamanho == 0 or tamanho > self.tamanho_maximo:
            raise ErroNavegador(f"tamanho fora do limite ({tamanho} bytes)")
        with open(real, "rb") as f:
            tipo = tipo_pelos_bytes(f.read(16))
        if tipo is None or EXTENSOES.get(ext) != tipo:
            raise ErroNavegador("o conteúdo não é a imagem ou vídeo que a extensão diz")
        esperado = "imagem" if pedido["modalidade"] in ("imagem", "editar_imagem") else "video"
        if tipo != esperado:
            raise ErroNavegador(f"o pedido é de {esperado}, chegou {tipo}")
        sonda = _sondar(real)
        prompts = json.loads(pedido["prompts_json"] or "{}")
        if site is None:
            if len(prompts) != 1:
                raise ErroNavegador("informe de qual site veio (--site); a licença vem do config do site")
            site = next(iter(prompts))
        if site not in self.sites:
            raise ErroNavegador(f"site {site!r} não está no config")
        if site not in prompts:  # o serviço vem do config E do pedido (spec 14 §E)
            raise ErroNavegador(f"o pedido não foi feito para {site!r} (sites do pedido: {', '.join(prompts) or 'nenhum'})")
        cfg = self.sites[site].cfg
        motivo = bloqueio_de_licenca(self.sites[site], pedido["modalidade"], comercial=getattr(perfil, "comercial", True),
                                     regras=getattr(perfil, "licenca_por_modalidade", None))
        if motivo:
            raise ErroNavegador(f"{site}: {motivo}")
        ativo = None
        prompt = (prompts.get(site) or {}).get("prompt")
        # A biblioteca só guarda licença comercial; a não comercial (perfil não comercial, D22/D24) fica registrada
        # no próprio pedido (site, licença e prompt), que é a procedência dela (D18).
        if biblioteca is not None and cfg.get("licenca") == "comercial":
            from .biblioteca import ErroLicenca

            try:
                ativo = biblioteca.adicionar(
                    real, "gerado_ia", cfg.get("nome") or site, link=cfg.get("endereco"),
                    perfil=getattr(perfil, "id", None), tags=["navegador", site, pedido["modalidade"]], provedor=site,
                    modelo=cfg.get("modelo"), prompt=prompt,
                    parametros={"pedido": pid, "licenca_site": cfg.get("licenca"), "termos": cfg.get("termos"),
                                "conferido_em": cfg.get("licenca_conferida")})
            except (ErroLicenca, OSError) as e:
                raise ErroNavegador(f"não entrou na biblioteca: {e}") from None
        if self.cotas is not None:
            from .cotas import config_cota, conta_de, creditos_de

            self.cotas.gastar(conta_de(site, self.sites[site]), config_cota(self.sites[site]),
                              creditos_de(self.sites[site], pedido["modalidade"]))
        with self.banco.con:
            self.banco.con.execute(
                "UPDATE pedidos_navegador SET estado = 'importado', site = ?, licenca = ?, prompt = ?, arquivo = ?, "
                "arquivo_hash = ?, "
                "atualizado_em = ? WHERE id = ? AND pasta = ?",
                (site, cfg.get("licenca"), prompt, str(real), (ativo or {}).get("hash"), _agora(), pid, str(Path(pasta_tema).resolve())))
        return {"id": pid, "site": site, "arquivo": str(real), "tipo": tipo, "largura": sonda.get("width"),
                "altura": sonda.get("height"), "ativo": (ativo or {}).get("hash"), "licenca": cfg.get("licenca")}

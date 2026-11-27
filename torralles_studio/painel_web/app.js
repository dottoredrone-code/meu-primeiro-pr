"use strict";
// Painel do Torralles Studio (K43, spec 15). Sem framework; todo texto entra com textContent (nunca como HTML).

const conteudo = document.getElementById("conteudo");
const STATUS = {
  na_fila: ["Na fila", "info"], produzindo: ["Produzindo", "info"], avaliando: ["Avaliando", "info"],
  aguardando_aprovacao: ["Esperando você", "alerta"], concluido: ["Concluído", "ok"], falhou: ["Falhou", "erro"],
  cancelado: ["Cancelado", ""], pronto: ["Pronto", "ok"], pronto_com_avisos: ["Pronto com avisos", "alerta"],
  incompleto: ["Incompleto", ""],
};
const DECISAO = { aprovado: ["Aprovado por você", "ok"], alterar: ["Alteração pedida", "alerta"] };
const TIPOS = { video: "Vídeo", imagem: "Imagem" };
let filtroAtual = "todos";
let relogio = null;

// ---------------------------------------------------------------- utilidades
function el(tag, atributos, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(atributos || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "classe") n.className = v;
    else if (k === "texto") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const f of filhos.flat()) {
    if (f === null || f === undefined || f === false) continue;
    n.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return n;
}

function avisar(texto, erro) {
  const a = document.getElementById("aviso");
  a.textContent = texto;
  a.className = "visivel" + (erro ? " erro" : "");
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => { a.className = ""; }, erro ? 6000 : 3000);
}

async function api(caminho, opcoes) {
  const r = await fetch(caminho, { credentials: "same-origin", ...(opcoes || {}) });
  let corpo = {};
  try { corpo = await r.json(); } catch (_) { corpo = {}; }
  if (r.status === 401 && corpo.precisa_token !== undefined) {
    mostrarEntrada();
    throw new Error("precisa do token");
  }
  if (!r.ok) throw new Error(corpo.erro || `erro ${r.status}`);
  return corpo;
}

function enviar(caminho, dados) {
  return api(caminho, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dados || {}) });
}

function data(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit",
    hour: "2-digit", minute: "2-digit" });
}

function dinheiro(v) {
  return typeof v === "number" ? "US$ " + v.toFixed(2).replace(".", ",") : "—";
}

function selo(mapa, chave) {
  const [texto, classe] = mapa[chave] || [chave || "—", ""];
  return el("span", { classe: "selo " + classe, texto });
}

function arquivo(id, info) {
  return info ? `/painel/arquivo/${encodeURIComponent(id)}/${encodeURIComponent(info.nome)}?v=${info.versao}` : null;
}

function linkSeguro(u) {
  try { const url = new URL(u); return ["http:", "https:"].includes(url.protocol) ? url.href : null; }
  catch (_) { return null; }
}

// Atualiza sozinho só quando você não está no meio de algo (comentário escrito ou vídeo tocando).
function agendarAtualizacao(hash) {
  relogio = setTimeout(() => {
    if (location.hash !== hash && !(hash === "#/projetos" && !location.hash)) return;
    const ocupado = [...document.querySelectorAll("textarea")].some(c => !c.hidden && c.value.trim())
      || [...document.querySelectorAll("video, audio")].some(m => !m.paused)
      || (document.activeElement && ["TEXTAREA", "INPUT"].includes(document.activeElement.tagName));
    if (ocupado) agendarAtualizacao(hash); else rota();
  }, 10000);
}

function marcarMenu(secao) {
  document.querySelectorAll(".menu a").forEach(a => a.classList.toggle("ativo", a.dataset.secao === secao));
}

function trocar(...filhos) {
  conteudo.replaceChildren(...filhos);
  conteudo.focus({ preventScroll: true });
}

function falha(e) {
  if (e.message === "precisa do token") return;
  trocar(el("p", { classe: "erro", texto: "Não deu para carregar: " + e.message }));
}

// ---------------------------------------------------------------- entrada (token)
function mostrarEntrada() {
  marcarMenu("");
  const campo = el("input", { type: "password", autocomplete: "current-password", required: true });
  const form = el("form", { classe: "formulario cartao", onsubmit: async ev => {
    ev.preventDefault();
    try {
      await enviar("/painel/entrar", { token: campo.value });
      campo.value = "";
      rota();
    } catch (e) { avisar(e.message, true); }
  } },
  el("h1", { texto: "Entrar no painel" }),
  el("p", { classe: "meta", texto: "Este servidor está protegido. Use o TORRALLES_STUDIO_TOKEN do seu .env." }),
  el("label", {}, "Token", campo),
  el("div", {}, el("button", { classe: "primario", type: "submit", texto: "Entrar" })));
  trocar(form);
}

// ---------------------------------------------------------------- projetos
const FILTROS = [
  ["todos", "Todos", () => true],
  ["revisar", "Para revisar", p => !p.decisao && ["aguardando_aprovacao", "pronto", "pronto_com_avisos"].includes(p.status)],
  ["alterar", "Alteração pedida", p => p.decisao === "alterar" || p.alteracoes_pendentes > 0],
  ["aprovados", "Aprovados", p => p.decisao === "aprovado" || p.status === "concluido"],
  ["andamento", "Em andamento", p => ["na_fila", "produzindo", "avaliando"].includes(p.status)],
  ["falhas", "Falhas", p => ["falhou", "cancelado", "incompleto"].includes(p.status)],
];

async function telaProjetos() {
  marcarMenu("projetos");
  const { projetos } = await api("/painel/api/projetos");
  const grade = el("div", { classe: "grade" });
  const filtros = el("div", { classe: "filtros", role: "group", "aria-label": "Filtrar projetos" });
  const desenhar = () => {
    const regra = FILTROS.find(f => f[0] === filtroAtual)[2];
    const lista = projetos.filter(regra);
    grade.replaceChildren(...(lista.length ? lista.map(cartaoProjeto)
      : [el("p", { classe: "vazio", texto: "Nada por aqui." })]));
    filtros.querySelectorAll("button").forEach(b => b.classList.toggle("selecionado", b.dataset.f === filtroAtual));
  };
  for (const [chave, nome, regra] of FILTROS) {
    const n = projetos.filter(regra).length;
    filtros.append(el("button", { type: "button", "data-f": chave, onclick: () => { filtroAtual = chave; desenhar(); } },
      `${nome} (${n})`));
  }
  trocar(
    el("div", { classe: "linha entre" }, el("h1", { texto: "Projetos" }),
      el("a", { classe: "botao", href: "#/novo", texto: "+ Novo vídeo" })),
    filtros, grade);
  desenhar();
  if (projetos.some(p => ["na_fila", "produzindo", "avaliando"].includes(p.status))) {
    agendarAtualizacao("#/projetos");
  }
}

function cartaoProjeto(p) {
  const capa = p.capa ? el("img", { src: `/painel/arquivo/${encodeURIComponent(p.id)}/${p.capa}`, alt: "",
    loading: "lazy" }) : el("span", { texto: TIPOS[p.tipo] || "Projeto" });
  return el("a", { classe: "cartao projeto-cartao", href: "#/projeto/" + encodeURIComponent(p.id) },
    el("div", { classe: "miniatura" }, capa),
    el("div", { classe: "corpo" },
      el("span", { classe: "titulo", texto: p.titulo || p.id }),
      el("div", { classe: "linha" }, selo(STATUS, p.status), p.decisao ? selo(DECISAO, p.decisao) : null),
      el("span", { classe: "meta numero" },
        [TIPOS[p.tipo], p.duracao_s ? Math.round(p.duracao_s) + " s" : null,
          typeof p.nota === "number" ? "nota " + p.nota : null, dinheiro(p.custo_usd), data(p.atualizado_em)]
          .filter(Boolean).join(" · "))));
}

// ---------------------------------------------------------------- um projeto
function caixaDecisao(id, item, atual, rotulo) {
  const comentario = el("textarea", { placeholder: "O que mudar? (obrigatório para pedir alteração)",
    "aria-label": "Comentário sobre " + rotulo, maxlength: 2000, hidden: true });
  const estado = el("div", { classe: "estado" });
  const mostrarEstado = d => {
    estado.replaceChildren();
    if (!d) { estado.append(el("span", { classe: "meta", texto: "Sem decisão ainda." })); return; }
    estado.append(selo(DECISAO, d.decisao), " ", el("span", { classe: "meta", texto: data(d.criado_em) }));
    if (d.comentario) estado.append(el("div", { classe: "meta", texto: "“" + d.comentario + "”" }));
  };
  mostrarEstado(atual);
  const decidir = async (decisao, botao) => {
    if (decisao === "alterar" && comentario.hidden) { comentario.hidden = false; comentario.focus(); return; }
    if (decisao === "alterar" && !comentario.value.trim()) { avisar("Escreva o que alterar.", true); comentario.focus(); return; }
    botao.disabled = true;
    try {
      const r = await enviar(`/painel/api/projetos/${encodeURIComponent(id)}/revisao`,
        { item, decisao, comentario: decisao === "alterar" ? comentario.value : "" });
      mostrarEstado({ decisao, comentario: decisao === "alterar" ? comentario.value.trim() : null,
        criado_em: new Date().toISOString() });
      comentario.value = ""; comentario.hidden = true;
      avisar(r.aviso ? "Decisão salva. " + r.aviso : (decisao === "aprovado" ? "Aprovado." : "Alteração registrada."));
    } catch (e) { avisar(e.message, true); }
    botao.disabled = false;
  };
  const aprovar = el("button", { type: "button", classe: "primario", texto: "Aprovar",
    onclick: ev => decidir("aprovado", ev.currentTarget) });
  const alterar = el("button", { type: "button", texto: "Pedir alteração",
    onclick: ev => decidir("alterar", ev.currentTarget) });
  return el("div", { classe: "decisao" }, estado, comentario, el("div", { classe: "linha" }, aprovar, alterar));
}

function lista(itens, vazio) {
  return itens && itens.length ? el("ul", { classe: "lista" }, itens.map(i => el("li", { texto: String(i) })))
    : el("p", { classe: "meta", texto: vazio || "Nenhum." });
}

function origemTexto(o) {
  if (!o) return "Gerada pelo Studio";
  const partes = [o.video_banco ? "Vídeo de banco" : null, o.fonte, o.autor ? "por " + o.autor : null,
    o.licenca ? "licença " + o.licenca : null].filter(Boolean);
  return partes.join(" · ");
}

function cartaoCena(id, c) {
  const midia = c.video
    ? el("video", { classe: "midia-cena", src: arquivo(id, c.video), poster: arquivo(id, c.imagem), controls: true,
      preload: "none", playsinline: true, muted: true })
    : c.imagem ? el("img", { classe: "midia-cena", src: arquivo(id, c.imagem), alt: "Imagem da cena " + c.numero, loading: "lazy" })
      : el("div", { classe: "midia-cena miniatura", texto: "Sem imagem ainda" });
  const origem = c.origem && linkSeguro(c.origem.link)
    ? el("a", { href: linkSeguro(c.origem.link), target: "_blank", rel: "noopener noreferrer", texto: origemTexto(c.origem) })
    : el("span", { texto: origemTexto(c.origem) });
  return el("div", { classe: "cartao" },
    el("div", { classe: "linha entre" }, el("h3", { texto: "Cena " + c.numero }),
      el("span", { classe: "meta", texto: [c.clima, c.duracao ? c.duracao + " s" : null].filter(Boolean).join(" · ") })),
    midia,
    c.voz ? el("audio", { src: arquivo(id, c.voz), controls: true, preload: "none", "aria-label": "Fala da cena " + c.numero }) : null,
    c.narracao ? el("p", { texto: c.narracao }) : null,
    c.texto_tela ? el("p", { classe: "meta" }, el("strong", { texto: "Na tela: " }), c.texto_tela) : null,
    el("p", { classe: "meta pequeno" }, origem),
    c.prompt_imagem ? el("details", {}, el("summary", { texto: "Prompt da imagem" }), el("p", { classe: "pequeno", texto: c.prompt_imagem })) : null,
    caixaDecisao(id, c.item, c.decisao, "cena " + c.numero));
}

async function telaProjeto(id) {
  marcarMenu("projetos");
  const p = await api("/painel/api/projetos/" + encodeURIComponent(id));
  const principal = p.tipo === "imagem" ? "peca" : "video";
  const midia = p.video
    ? el("video", { src: arquivo(id, p.video), controls: true, preload: "metadata", playsinline: true,
      poster: arquivo(id, p.capa_arquivo) })
    : p.imagem_final ? el("img", { src: arquivo(id, p.imagem_final), alt: "Peça final" })
      : el("div", { classe: "miniatura cartao", texto: "O arquivo final ainda não está pronto." });

  const cabecalho = el("div", { classe: "cartao" },
    el("div", { classe: "linha" }, selo(STATUS, p.status), p.decisao ? selo(DECISAO, p.decisao) : null,
      p.alteracoes_pendentes ? el("span", { classe: "selo alerta", texto: p.alteracoes_pendentes + " alteração(ões) pedida(s)" }) : null),
    el("h1", { texto: p.titulo || id }),
    el("p", { classe: "meta numero", texto: [TIPOS[p.tipo], p.proporcao, typeof p.duracao_s === "number" ? p.duracao_s.toFixed(1) + " s" : null,
      typeof p.nota === "number" ? "nota do roteiro " + p.nota : null, "custo " + dinheiro(p.custo_usd),
      data(p.atualizado_em)].filter(Boolean).join(" · ") }),
    p.cta ? el("p", {}, el("strong", { texto: "Chamada final: " }), p.cta) : null,
    el("h2", { texto: p.tipo === "imagem" ? "A peça" : "O vídeo" }),
    caixaDecisao(id, principal, p.decisoes[principal], p.tipo === "imagem" ? "a peça" : "o vídeo"),
    el("h2", { texto: "Régua de qualidade" }),
    p.aprovado_regua === true ? el("p", {}, el("span", { classe: "selo ok", texto: "Passou na régua" }))
      : p.aprovado_regua === false ? el("p", {}, el("span", { classe: "selo alerta", texto: "Com problemas na régua" })) : null,
    lista(p.problemas, "Nenhum problema encontrado."),
    p.referencia && p.referencia.alertas && p.referencia.alertas.length
      ? el("div", {}, el("h3", { texto: "Fora da faixa da categoria " + p.referencia.categoria }), lista(p.referencia.alertas)) : null,
    acoesPedido(id, p));

  const blocos = [
    el("a", { classe: "voltar", href: "#/projetos", texto: "← Projetos" }),
    el("div", { classe: "topo-projeto" }, el("div", { classe: "player" }, midia), cabecalho),
  ];
  if (p.pedido) blocos.push(blocoPedido(p.pedido));
  if (p.cenas.length) blocos.push(el("h2", { texto: "Cenas" }), el("div", { classe: "grade-cenas" }, p.cenas.map(c => cartaoCena(id, c))));
  if (p.capa_arquivo || p.post) {
    const capaPost = el("div", { classe: "duas" });
    if (p.capa_arquivo) capaPost.append(el("div", { classe: "cartao" }, el("h3", { texto: "Capa" }),
      el("img", { classe: "midia-cena", src: arquivo(id, p.capa_arquivo), alt: "Capa do vídeo" }),
      caixaDecisao(id, "capa", p.decisoes.capa, "a capa")));
    if (p.post) {
      const texto = el("div", { classe: "texto-post", texto: p.post });
      capaPost.append(el("div", { classe: "cartao" },
        el("div", { classe: "linha entre" }, el("h3", { texto: "Texto para postar" }),
          el("button", { type: "button", texto: "Copiar", onclick: async () => {
            try { await navigator.clipboard.writeText(p.post); avisar("Texto copiado."); }
            catch (_) { avisar("Não deu para copiar; selecione o texto.", true); }
          } })),
        texto, caixaDecisao(id, "post", p.decisoes.post, "o post")));
    }
    blocos.push(el("h2", { texto: "Capa e post" }), capaPost);
  }
  if (p.creditos) blocos.push(el("h2", { texto: "Créditos" }), el("div", { classe: "texto-post", texto: p.creditos }));
  blocos.push(detalhesTecnicos(p));
  if (p.historico.length) {
    blocos.push(el("h2", { texto: "Histórico de decisões" }), el("div", { classe: "tabela cartao" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { texto: "Quando" }), el("th", { texto: "Item" }), el("th", { texto: "Decisão" }), el("th", { texto: "Comentário" }))),
      el("tbody", {}, p.historico.map(r => el("tr", {}, el("td", { texto: data(r.criado_em) }), el("td", { texto: r.item.replace("_", " ") }),
        el("td", {}, selo(DECISAO, r.decisao)), el("td", { texto: r.comentario || "" })))))));
  }
  trocar(...blocos);
  if (["na_fila", "produzindo", "avaliando"].includes(p.status)) {
    agendarAtualizacao("#/projeto/" + encodeURIComponent(id));
  }
}

function acoesPedido(id, p) {
  if (!p.pedido || !["na_fila", "produzindo", "avaliando", "aguardando_aprovacao"].includes(p.status)) return null;
  return el("div", { classe: "linha", style: null },
    el("button", { type: "button", classe: "perigo", texto: "Cancelar pedido", onclick: async ev => {
      const botao = ev.currentTarget;
      if (!confirm("Cancelar este pedido? Ele não será produzido nem gravado.")) return;
      botao.disabled = true;
      try { await enviar(`/v1/pecas/${encodeURIComponent(id)}/cancelar`, {}); avisar("Pedido cancelado."); rota(); }
      catch (e) { avisar(e.message, true); botao.disabled = false; }
    } }));
}

function blocoPedido(ped) {
  const b = ped.briefing || {};
  return el("details", { classe: "cartao", style: null },
    el("summary", { texto: "Pedido e briefing" }),
    el("div", { classe: "tabela" }, el("table", {}, el("tbody", {},
      [["Pedido em", data(ped.criado_em)], ["Entregável", ped.entregavel], ["Teto", dinheiro(ped.teto_usd)],
        ["Tema", b.conceito_visual], ["Texto na tela", b.texto_overlay], ["Paleta", b.paleta_cores],
        ["Formato", b.formato_dimensoes], ["Erro", ped.erro]]
        .filter(([, v]) => v).map(([k, v]) => el("tr", {}, el("th", { texto: k }), el("td", { texto: v })))))));
}

function detalhesTecnicos(p) {
  const medidas = Object.entries(p.medidas || {});
  return el("details", { classe: "cartao" }, el("summary", { texto: "Detalhes técnicos (etapas, medidas, trilha e efeitos)" }),
    p.etapas.length ? el("div", { classe: "tabela" }, el("table", {},
      el("thead", {}, el("tr", {}, el("th", { texto: "Etapa" }), el("th", { texto: "Provedor" }), el("th", { texto: "Observação" }))),
      el("tbody", {}, p.etapas.map(e => el("tr", {}, el("td", { texto: e.etapa }), el("td", { texto: e.provedor || "—" }),
        el("td", { texto: [e.reaproveitado ? "reaproveitado" : null, e.licenca ? "licença " + e.licenca : null, e.aviso].filter(Boolean).join(" · ") })))))) : null,
    medidas.length ? el("div", {}, el("h3", { texto: "Medidas" }), lista(medidas.map(([k, v]) => `${k.replaceAll("_", " ")}: ${Array.isArray(v) ? v.join("–") : (v && typeof v === "object" ? JSON.stringify(v) : v)}`))) : null,
    p.trilha ? el("p", { classe: "pequeno", texto: "Trilha: " + [p.trilha.titulo, p.trilha.fonte, p.trilha.licenca].filter(Boolean).join(" · ") }) : null,
    p.efeitos.length ? el("p", { classe: "pequeno", texto: `Efeitos nos cortes: ${p.efeitos.length}` }) : null,
    p.capcut ? el("p", { classe: "pequeno", texto: "Pasta do CapCut pronta (capcut/ dentro do projeto)." }) : null);
}

// ---------------------------------------------------------------- novo
async function telaNovo() {
  marcarMenu("novo");
  let perfis = [];
  try { perfis = (await api("/painel/api/perfis")).perfis; } catch (e) { if (e.message === "precisa do token") return; }
  const campos = {
    tema: el("textarea", { required: true, minlength: 3, maxlength: 500, placeholder: "Ex.: 3 benefícios do chá verde que a ciência confirma" }),
    tipo: el("select", {}, el("option", { value: "video_curto", texto: "Vídeo curto (Reels, Shorts, TikTok)" }),
      el("option", { value: "story", texto: "Story" }), el("option", { value: "imagem", texto: "Post de imagem" })),
    proporcao: el("select", {}, ["9:16", "4:5", "1:1", "16:9"].map(v => el("option", { value: v, texto: v }))),
    duracao_s: el("input", { type: "number", min: 5, max: 90, value: 30 }),
    perfil: el("select", {}, el("option", { value: "", texto: "Sem perfil" }), perfis.map(p => el("option", { value: p.id, texto: p.nome }))),
    texto_tela: el("input", { maxlength: 200, placeholder: "Opcional" }),
    paleta: el("input", { maxlength: 200, placeholder: "Opcional (ex.: verde e creme)" }),
    teto_usd: el("input", { type: "number", min: 0.01, max: 1.5, step: 0.01, value: 1.5 }),
  };
  campos.tipo.addEventListener("change", () => {
    const imagem = campos.tipo.value === "imagem";
    campos.duracao_s.disabled = imagem;
    campos.proporcao.value = imagem ? "1:1" : "9:16";
    if (campos.tipo.value === "story") campos.duracao_s.value = 15;
  });
  const botao = el("button", { classe: "primario", type: "submit", texto: "Pedir" });
  const form = el("form", { classe: "formulario", onsubmit: async ev => {
    ev.preventDefault();
    botao.disabled = true;
    const dados = { tema: campos.tema.value, tipo: campos.tipo.value, proporcao: campos.proporcao.value,
      perfil: campos.perfil.value || null, texto_tela: campos.texto_tela.value, paleta: campos.paleta.value,
      teto_usd: Number(campos.teto_usd.value) };
    if (campos.tipo.value !== "imagem") dados.duracao_s = Number(campos.duracao_s.value);
    try {
      const r = await enviar("/painel/api/novo", dados);
      avisar(`Pedido na fila. Estimativa: ${dinheiro(r.estimativa_custo_usd)}.`);
      location.hash = "#/projeto/" + encodeURIComponent(r.job_id);
    } catch (e) { avisar(e.message, true); botao.disabled = false; }
  } },
  el("label", {}, "Tema ou ideia", campos.tema),
  el("div", { classe: "duas" }, el("label", {}, "Tipo", campos.tipo), el("label", {}, "Formato", campos.proporcao)),
  el("div", { classe: "duas" }, el("label", {}, "Duração (segundos)", campos.duracao_s), el("label", {}, "Perfil", campos.perfil)),
  el("label", {}, "Texto na tela", el("span", { classe: "ajuda", texto: "Frase que precisa aparecer. Sem nada, usa o começo do tema." }), campos.texto_tela),
  el("label", {}, "Cores", campos.paleta),
  el("label", {}, "Teto de gasto (US$)", el("span", { classe: "ajuda", texto: "Nunca passa de US$ 1,50. Serviços pagos que não couberem são pulados." }), campos.teto_usd),
  el("div", {}, botao));
  trocar(el("h1", { texto: "Novo pedido" }),
    el("p", { classe: "meta", texto: "O Studio produz em segundo plano e avisa aqui quando estiver esperando você aprovar." }),
    el("div", { classe: "cartao" }, form));
}

// ---------------------------------------------------------------- biblioteca
async function telaBiblioteca() {
  marcarMenu("biblioteca");
  const busca = el("input", { type: "search", placeholder: "Buscar por título, autor, fonte ou prompt", "aria-label": "Buscar" });
  const tipo = el("select", { "aria-label": "Tipo" }, el("option", { value: "", texto: "Todos os tipos" }),
    el("option", { value: "imagem", texto: "Imagens" }), el("option", { value: "video", texto: "Vídeos" }),
    el("option", { value: "audio", texto: "Sons e músicas" }));
  const grade = el("div", { classe: "grade" });
  const carregar = async () => {
    try {
      const q = new URLSearchParams({ busca: busca.value, tipo: tipo.value });
      const { ativos } = await api("/painel/api/biblioteca?" + q);
      grade.replaceChildren(...(ativos.length ? ativos.map(cartaoAtivo) : [el("p", { classe: "vazio", texto: "Nada encontrado." })]));
    } catch (e) { falha(e); }
  };
  let espera;
  busca.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(carregar, 300); });
  tipo.addEventListener("change", carregar);
  trocar(el("h1", { texto: "Biblioteca" }),
    el("p", { classe: "meta", texto: "Toda mídia guardada tem fonte e licença. As de licença CC-BY vão nos créditos." }),
    el("div", { classe: "duas" }, busca, tipo), el("div", { style: null }, el("br")), grade);
  await carregar();
}

function cartaoAtivo(a) {
  const src = "/painel/midia/" + a.hash;
  const midia = a.tipo === "imagem" ? el("img", { src, alt: a.titulo || "", loading: "lazy" })
    : a.tipo === "video" ? el("video", { src, controls: true, preload: "none", muted: true })
      : el("audio", { src, controls: true, preload: "none" });
  return el("div", { classe: "cartao projeto-cartao" },
    el("div", { classe: "miniatura" }, midia),
    el("div", { classe: "corpo" },
      el("span", { classe: "titulo", texto: a.titulo || "Sem título" }),
      el("span", { classe: "meta", texto: [a.fonte, a.autor ? "por " + a.autor : null].filter(Boolean).join(" · ") }),
      el("div", { classe: "linha" }, el("span", { classe: "selo", texto: a.licenca || "?" }),
        linkSeguro(a.link) ? el("a", { classe: "pequeno", href: linkSeguro(a.link), target: "_blank", rel: "noopener noreferrer", texto: "origem" }) : null),
      a.tags && a.tags.length ? el("span", { classe: "meta pequeno", texto: a.tags.join(", ") }) : null));
}

// ---------------------------------------------------------------- controle
async function telaControle() {
  marcarMenu("controle");
  const r = await api("/painel/api/resumo");
  const total = Object.values(r.fila).reduce((a, b) => a + b, 0);
  const indicadores = el("div", { classe: "indicadores" },
    indicador("Gasto nos projetos do mês", dinheiro(r.gasto_mes_usd)),
    indicador("Teto por vídeo", dinheiro(r.teto_video_usd)),
    indicador("Na fila agora", String((r.fila.na_fila || 0) + (r.fila.produzindo || 0))),
    indicador("Esperando você", String(r.fila.aguardando_aprovacao || 0)),
    indicador("Alterações pedidas", String(r.alteracoes_pendentes)),
    indicador("Pedidos no total", String(total)));
  const cotas = r.cotas.length ? el("div", { classe: "tabela" }, el("table", {},
    el("thead", {}, el("tr", {}, el("th", { texto: "Serviço" }), el("th", { texto: "Uso" }), el("th", { texto: "Situação" }))),
    el("tbody", {}, r.cotas.map(c => el("tr", {}, el("td", { texto: c.conta }),
      el("td", { classe: "numero", texto: c.limite ? `${c.usado} de ${c.limite}` : `${c.usado} usados` }),
      el("td", {}, c.esgotado_ate ? el("span", { classe: "selo alerta", texto: "acabou, volta " + c.esgotado_ate })
        : el("span", { classe: "meta", texto: c.renova_em ? "renova " + c.renova_em : "sem uso no período" })))))))
    : el("p", { classe: "meta", texto: "Nenhum serviço com cota grátis no config." });
  const provedores = Object.entries(r.provedores).map(([tarefa, itens]) => el("div", { classe: "cartao" },
    el("h3", { texto: tarefa.replaceAll("_", " ") }),
    el("ul", { classe: "lista" }, itens.map((i, n) => el("li", {},
      el("span", { classe: "selo " + (i.pronto ? "ok" : ""), texto: i.pronto ? "pronto" : "fora" }), ` ${n + 1}. ${i.nome}`,
      i.motivo ? el("div", { classe: "meta pequeno", texto: i.motivo }) : null)))));
  const perfis = r.perfis.length ? lista(r.perfis.map(p => `${p.nome} (${p.id})`)) : el("p", { classe: "meta", texto: "Nenhum perfil. Crie com: python -m torralles_studio perfil-novo" });
  trocar(el("h1", { texto: "Controle" }), indicadores,
    el("h2", { texto: "Cotas grátis" }), el("div", { classe: "cartao" }, cotas),
    el("h2", { texto: "Perfis" }), el("div", { classe: "cartao" }, perfis,
      Object.keys(r.erros_perfis).length ? lista(Object.entries(r.erros_perfis).map(([k, v]) => `${k}: ${v}`)) : null),
    el("h2", { texto: "Provedores por tarefa (na ordem do fallback)" }), el("div", { classe: "grade" }, provedores));
}

function indicador(nome, valor) {
  return el("div", { classe: "cartao indicador" }, el("div", { classe: "meta", texto: nome }), el("div", { classe: "valor numero", texto: valor }));
}

// ---------------------------------------------------------------- rotas
async function rota() {
  clearTimeout(relogio);
  const h = location.hash || "#/projetos";
  if (rota.anterior !== h) conteudo.replaceChildren(el("p", { classe: "carregando", texto: "Carregando…" }));
  rota.anterior = h;
  try {
    if (h.startsWith("#/projeto/")) await telaProjeto(decodeURIComponent(h.slice("#/projeto/".length)));
    else if (h === "#/novo") await telaNovo();
    else if (h === "#/biblioteca") await telaBiblioteca();
    else if (h === "#/controle") await telaControle();
    else await telaProjetos();
  } catch (e) { falha(e); }
}

window.addEventListener("hashchange", rota);
rota();

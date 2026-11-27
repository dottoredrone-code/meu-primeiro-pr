# 08 — Proposta: contrato Torralles Ops → Torralles Studio

> Status: **rascunho para revisão**. Depende das decisões D13–D16 (propostas).
> Base: o briefing real de peça criativa do Ops ([07](07-estudo-torralles-ops-cerebro.md#confirmação-pelo-código-15102026)).

## Princípios
1. **JSON validado por esquema** nas duas direções. Nada de texto para garimpar.
2. **Assíncrono**: o pedido devolve um `job_id` em segundos; a produção roda em segundo plano.
3. **O Studio não depende do Ops**: o mesmo contrato serve para pedidos vindos do Hermes, da linha de comando ou de outro sistema.
4. **Compatível com o que o Ops já tem**: os 6 campos do briefing entram como estão; o resto é opcional.

## Como o Ops chama o Studio
Duas portas para a mesma função:
- **HTTP local** (o painel do Ops é Next.js e já faz chamadas HTTP): `POST /v1/pecas`, `GET /v1/pecas/{job_id}`.
- **MCP** (para o Hermes e agentes): ferramentas `produzir_peca` e `consultar_peca`.

No Ops, a mudança seria pequena: um botão **"Produzir no Studio"** na peça em `rascunho`/`aprovada`, que envia o
pedido e depois guarda o resultado em colunas novas da tabela `peca_criativa` (`studio_job_id`, `studio_status`,
`arquivos_json`, `nota_qualidade`, `custo_usd`).

## Pedido (Ops → Studio)

```json
{
  "versao_contrato": "1.0",
  "origem": {"sistema": "torralles-ops", "peca_id": 4, "campanha_id": 6, "workspace": "<id do workspace>"},
  "perfil": "<id do perfil do projeto no Studio>",
  "briefing": {
    "tipo_peca": "post estático",
    "conceito_visual": "…",
    "paleta_cores": "…",
    "formato_dimensoes": "1080x1080",
    "texto_overlay": "…",
    "ferramenta_sugerida": "Canva"
  },
  "contexto_campanha": {
    "canal": "Instagram",
    "objetivo": "…",
    "publico_alvo": "…",
    "copy_principal": "…",
    "cta": "…"
  },
  "fatos_travados": {
    "preco": "R$ 49,90",
    "nome_produto": "…",
    "link": "…"
  },
  "referencias": [{"tipo": "imagem_produto", "url_ou_caminho": "…"}],
  "orcamento": {"custo_maximo_usd": 1.00, "modo": "economico"},
  "entregaveis": ["imagem"],
  "aprovacao_humana": true
}
```

Regras de validação:
- `briefing`: os 6 campos obrigatórios (igual ao Ops). `formato_dimensoes` precisa ser interpretável (ex.: `1080x1920`).
- `fatos_travados`: opcional, mas se vier, **todo texto gerado** (overlay, legenda, narração) é checado contra ele. Qualquer número, preço, nome ou link que não esteja ali reprova (D15).
- `entregaveis`: `imagem`, `carrossel`, `video_curto`, `story`. Derivado de `tipo_peca` quando omitido.
- `orcamento.modo`: `economico`, `misto` ou `premium` (spec 04, seção 4).

## Resposta imediata

```json
{"job_id": "stu_01H…", "status": "na_fila", "estimativa_custo_usd": 0.12}
```

## Resultado (consulta ou aviso de conclusão)

```json
{
  "job_id": "stu_01H…",
  "status": "concluido",
  "arquivos": [
    {"tipo": "imagem", "caminho": "biblioteca/projetos/…/peca.png", "sha256": "…",
     "licenca": "comercial_ok", "provedor": "fal_flux", "modelo": "…"}
  ],
  "exportacao_capcut": "biblioteca/exportar/…/",
  "qualidade": {
    "nota_estrutural": 100, "nota_criativa": 82, "aprovado": true,
    "fatos_travados_ok": true,
    "problemas": []
  },
  "custo_usd": 0.09,
  "tentativas": 2,
  "revisar_manual": false
}
```

Status possíveis: `na_fila`, `produzindo`, `avaliando`, `aguardando_aprovacao`, `concluido`, `falhou`, `cancelado`.
Ao estourar o limite de tentativas ou de custo, o Studio devolve a melhor tentativa com `revisar_manual: true`, sem travar.

## Escala de notas (alinhada ao Ops, D15)
| Nota | Régua | Mínimo |
|---|---|---|
| `nota_estrutural` | Igual ao gate v2 do Ops (campos preenchidos, sem placeholder) + checagens técnicas do arquivo | 95 |
| `nota_criativa` | Juízes da spec 03 (aderência, artefatos, consistência, composição) | 70 |

## Critérios de pronto (para o Kanban)
- [ ] Esquemas JSON do pedido e do resultado, com testes de validação (inclui o exemplo real do Ops)
- [ ] `POST /v1/pecas` e `GET /v1/pecas/{job_id}` locais + ferramentas MCP equivalentes
- [ ] Execução assíncrona com estado no SQLite do Studio (retomada sem pagar duas vezes)
- [ ] Checador de fatos travados (teste com o caso real de preço inventado)
- [ ] Mapeamento `tipo_peca` → entregável e `formato_dimensoes` → resolução
- [ ] No Ops (fora deste repositório, tarefa separada): botão "Produzir no Studio" e colunas novas em `peca_criativa`

## Questões em aberto
1. O Ops deve chamar o Studio só depois de "Aprovar" o briefing, ou também em `rascunho`?
2. O resultado volta por consulta periódica do Ops ou por aviso (webhook) do Studio?
3. As imagens do produto (fotos reais) entram sempre como referência obrigatória para peças de produto?

# Servidor do Studio para o Torralles Ops e o Hermes (K28)

O mesmo pedido (contrato da [spec 08](sdd/08-contrato-ops-studio.md)) entra por duas portas. Os pedidos ficam
numa fila no banco do Studio e são produzidos um por vez, em segundo plano. Se o PC desligar no meio, o pedido
volta para a fila e continua sem pagar de novo.

## HTTP local (Torralles Ops)
```bash
python -m torralles_studio servidor            # http://127.0.0.1:8765, só este PC
```
- `POST /v1/pecas` com o pedido em JSON → `202 {"job_id": "stu_…", "status": "na_fila", "estimativa_custo_usd": 0.08}`
- `GET /v1/pecas/{job_id}` → status (`na_fila`, `produzindo`, `aguardando_aprovacao`, `concluido`, `falhou`) e,
  quando pronto, `arquivos` (caminho e sha256), `qualidade`, `custo_usd`, `creditos`, `exportacao_capcut`.
- Pedido com problema → `422 {"erro": "pedido inválido", "problemas": [...]}` (diz o campo e o porquê).
- Proteção:
  - o pedido precisa ir com `Content-Type: application/json` (formulário de site é recusado: 415);
  - pedido vindo de página de outro site (cabeçalho `Origin` fora de `localhost`/`127.0.0.1`) é recusado (403),
    assim como nome de host diferente de `127.0.0.1`/`localhost` (403);
  - até 20 pedidos esperando ao mesmo tempo; acima disso, 429 (tente de novo depois);
  - defina `TORRALLES_STUDIO_TOKEN` no `.env` e mande `Authorization: Bearer <token>`. Para escutar fora deste PC
    (`--host`), o token é obrigatório.
- Servidor e MCP podem rodar juntos na mesma fila: cada pedido é produzido por um só deles; se um processo cair,
  o pedido dele volta para a fila depois de 3 minutos sem sinal de vida. O teto do pedido vale também nas retomadas
  (o gasto já feito é descontado).

Exemplo (PowerShell):
```powershell
$pedido = Get-Content pedido.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/v1/pecas -ContentType "application/json" -Body $pedido
Invoke-RestMethod http://127.0.0.1:8765/v1/pecas/stu_xxxxxxxx
```

## MCP (Hermes e agentes)
```bash
python -m torralles_studio mcp
```
Ferramentas: `produzir_peca` (`{"pedido": {...}}`) e `consultar_peca` (`{"job_id": "stu_…"}`).
Configuração típica de um cliente MCP (stdio): comando `python`, argumentos `-m torralles_studio mcp`,
pasta de trabalho = pasta do repositório.

## O que cada entregável produz hoje
| Entregável (derivado do `tipo_peca`) | O Studio faz |
|---|---|
| `imagem` (post estático) | Imagem por IA (ou foto gratuita licenciada) no formato pedido + o `texto_overlay` por cima, com caixa para ler em qualquer fundo. Sem juiz de imagem ainda: volta com `revisar_manual: true` |
| `video_curto`, `story` | O `produzir` completo (roteiro com juiz e fatos travados, cenas, narração, trilha, montagem e pasta do CapCut) |
| `carrossel` | Ainda não (recusado com explicação) |

Teto por pedido: `orcamento.custo_maximo_usd`, nunca acima de US$ 1,50 (D20). `aprovacao_humana` (padrão) deixa o
pedido em `aguardando_aprovacao` quando fica pronto.

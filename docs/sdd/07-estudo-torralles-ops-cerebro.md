# 07 — Estudo: Torralles Ops e o Cérebro Centralizado

> Fonte original: trechos do `CEREBRO_MESTRE.md` (26/08/2026).
> **Atualização 15/10/2026:** confirmado e detalhado por leitura direta do código, do banco e do Cérebro,
> feita por uma sessão local no PC do Diego, só leitura. Ver a seção [Confirmação pelo código](#confirmação-pelo-código-15102026)
> no fim deste arquivo e o contrato proposto em [08-contrato-ops-studio](08-contrato-ops-studio.md).

## O Cérebro Centralizado

- Arquivo mestre: `Cerebro_Centralizado/CEREBRO_MESTRE.md`, editado só ali e sincronizado por script para
  **Cerebro Claude, Cerebro Gemini, Obsidian Vault** e **Supabase**.
- Regra registrada para qualquer IA: **antes de agir num projeto, ler o `CLAUDE.md`/README do projeto e o Cérebro**.
- Tem uma seção **"Padrão de engenharia de prompt"**: instruções positivas ("faça X"), uma pergunta por vez,
  e **anti-alucinação** (pedir fonte, permitir "não sei", temperatura baixa).

**Para o Studio:** a fase 9 do protocolo (registrar aprendizados) deve ir para o **Cérebro**, e não para uma
memória paralela. O Studio guarda só os dados operacionais dele (biblioteca, custos, notas) e exporta um
resumo para o Cérebro.

## O Torralles Ops (como estava em ago/2026)

| Aspecto | O que o Cérebro registra |
|---|---|
| O que é | Plataforma própria de **agentes por departamento**, rodando num painel local (`Diego Torralles Ai Labs/dashboard`, TypeScript) |
| Estrutura | **Diretor + 6 Chefes de Equipe**: Inteligência de Mercado, Criação de Produto, Marketing & Propaganda, Comunicação Visual, Relações Públicas, Engenharia/Dev |
| Motor | Os Chefes executam pelo **Hermes** (`executarHermes()`), e as respostas em texto são lidas por um parser de rótulos |
| Fluxo já rodado | referência de mercado → ficha de produto → campanha → **briefing de peça criativa** → publicação (ex.: Facebook) |
| Qualidade | **Gate v2**: nota 0–100 por registro (vazio = 0, "a definir"/"tbd" = 0, raso = 50%), **mínimo 95** para aprovar; escape `?forcar=true`. Claude como diretor de revisão final |
| Robustez | Retry com espera crescente (2s/4s/8s), logs estruturados, prompts centralizados com teste que trava se prompt e parser divergirem, **86 testes** |
| Problemas reais encontrados | Hermes **inventou um preço** (fato fixo do produto); confundiu "registrar" com salvar na própria memória; parser de texto frágil (o "rascunho" do raciocínio vencia a resposta final) |

## Como o Studio se encaixa

O Torralles Ops **termina no briefing da peça criativa**. O Torralles Studio **começa exatamente aí**:

```
Torralles Ops (Diretor + Chefes, via Hermes)
  Inteligência de Mercado → Produto → Marketing → Comunicação Visual
                                                     │ briefing da peça
                                                     ▼
                        Torralles Studio (motor via MCP/HTTP, JSON)
                        roteiro → imagens → voz → vídeo → qualidade → montagem
                                                     │ peça pronta + relatório (custo, notas)
                                                     ▼
                        Relações Públicas / publicação → aprendizados → Cérebro
```

## O que reaproveitar do Ops (padrões já validados por você)

1. **Nota mínima com escape manual**: o `?forcar=true` vira, no Studio, "aprovar manualmente" com registro de quem aprovou e por quê.
2. **Mesma escala**: usar **0–100** no Studio também (em vez de 0–10), para o ecossistema falar a mesma língua. Proposta: checagens estruturais com mínimo 95 (igual ao Ops) e avaliação criativa com mínimo 70 (o "razoável" da spec 03).
3. **Prompts centralizados + teste de contrato**: no Studio, cada formato de resposta tem um esquema JSON único, e um teste falha se o prompt e o leitor divergirem.
4. **Retry com espera crescente e logs estruturados**: o Studio já tem retry; adicionar logs em JSON no mesmo estilo.
5. **TDD e "verificado, não só afirmado"**: mesma disciplina no Kanban do Studio (coluna "Em verificação").

## Lições do Ops que viram requisitos do Studio

| Problema no Ops | Requisito no Studio |
|---|---|
| Hermes inventou um preço | **Fatos travados**: preço, nome, datas e links do briefing entram como campos fixos. Um checador **eliminatório** confere se o roteiro/legenda os mantém intactos e não inventa outros |
| Parser de texto frágil | **Interface estruturada**: o Studio recebe e devolve **JSON** (via MCP/HTTP), nunca texto para ser "garimpado" |
| Agente confundiu tarefas com a própria memória | O Studio **não usa a memória do agente** como banco: estado fica no SQLite do Studio; o Hermes só chama ferramentas |
| Instabilidade do provedor | Já coberto: fallback por mídia + descanso de provedor (spec do roteador) |

## Impacto nas specs

| Spec | Ajuste proposto |
|---|---|
| 03 Parâmetros | Escala 0–100; novo eliminatório **"fatos travados"** em roteiro, legendas e textos na imagem |
| 05 Memória | Perfil e histórico ficam nos perfis do Hermes; aprendizados vão para o **Cérebro** |
| 06 Hermes | Confirma a opção **C (híbrida)**: o Ops/Hermes orquestra e o Studio é o motor de produção |
| Nova | **Contrato do briefing**: formato JSON que o Chefe de Comunicação Visual envia ao Studio (campos, fatos travados, perfil do projeto, formato, orçamento) |

## Pendências para confirmar com acesso direto

- Estado atual do Ops (os registros vão até 24/08/2026).
- Formato real do "briefing de peça criativa" gerado hoje.
- O conteúdo de `PADRAO_QUALIDADE_CRIATIVO.md` (citado como padrão de nota mínima), para alinhar com a spec 03.
- Como o Ops chama o Hermes (CLI ou API) e se já existe servidor MCP configurado.

---

## Confirmação pelo código (15/10/2026)

Leitura direta, só leitura, de `dashboard/` (Next.js 16.3, React 19.2, TypeScript, Tailwind 4, SQLite via
`node:sqlite`, Vitest 4), do banco local e do Cérebro. Último commit do Ops: **26/08/2026** (gate v2,
parser unificado, retry e logging). Nada mudou depois disso.

### O que se confirmou
- **Diretor + 6 Chefes**. O Diretor aloca por regra (`tipo` → área) e usa a API do Claude só para escrever a justificativa da alocação. Os Chefes executam pelo **Hermes via CLI** (`hermes chat -q "<instrução>"`), sem perfil nem modelo explícitos (usam a configuração global do Hermes).
- **Fluxo síncrono numa única requisição HTTP**, sem fila: tarefa → Diretor → Chefe/Hermes → parser → rascunho → revisão humana ("Aprovar"/"Polir") → próxima etapa. Encadeamento: referência de mercado → produto → campanha aprovada → **peça criativa**.
- **Gate de qualidade v2** (`qualidade.ts`): nota 0–100 dividida igualmente entre os campos; vazio ou placeholder = 0; prosa com menos de 20 caracteres = 50%; **aprova com ≥ 95**; reprovação devolve HTTP 422 com os problemas; escape `?forcar=true`.
- **Retry**: 3 tentativas com espera de 2 s e 4 s; timeout de 600 s por chamada.

### O que se corrigiu
- A worktree `torralles-ops-criacao-produto` **não existe mais** (há `fase2-marketing` e `redesign-visual`).
- **`PADRAO_QUALIDADE_CRIATIVO.md` não existe** no PC: é citado no código e no Cérebro, mas os critérios nunca foram escritos ou se perderam. A régua criativa da spec 03 passa a ser a referência.
- O Ops **não tem documentação própria** além das specs em `dashboard/docs/superpowers/` e do Cérebro.

### O achado mais importante: o Ops para no texto
O "briefing de peça criativa" é **só texto, com 6 campos**:

| Campo | Exemplo de conteúdo |
|---|---|
| `tipo_peca` | post estático, story, carrossel, vídeo curto |
| `conceito_visual` | ideia central da peça em 1–2 frases |
| `paleta_cores` | cores sugeridas |
| `formato_dimensoes` | 1080x1080, 1080x1920 |
| `texto_overlay` | texto curto para sobrepor |
| `ferramenta_sugerida` | CapCut, Canva |

A partir daí **a produção é manual** (CapCut/Canva), e o status `aprovada` significa "produzida e revisada fora
do sistema". **Nenhuma imagem ou vídeo é gerado nem rastreado.** Esse é exatamente o espaço do Torralles Studio:
transformar esse briefing em peça pronta, com qualidade verificada.

### Pontos fracos do Ops que o Studio não deve repetir
| Ponto fraco no Ops | Como o Studio evita |
|---|---|
| Até 3 × 600 s numa única requisição HTTP | **Trabalho assíncrono**: o Studio devolve um `job_id` na hora e o Ops consulta o andamento |
| Hermes instável (erros de stream, picos de 2–4 min) e configuração global compartilhada com outro sistema | Fallback por provedor e "descanso" (já existe no roteador); o Studio não depende da configuração do Hermes |
| Parser de texto "RÓTULO: valor" com 3 classes de bug já vistas | Entrada e saída em **JSON validado por esquema** |
| Preço inventado e campo cortado; o gate não checa veracidade | Eliminatório **"fatos travados"** (D15) |
| Gate só estrutural (vazio, placeholder, tamanho); `?forcar=true` aprova qualquer coisa | Juiz criativo da spec 03 + aprovação manual registrada com motivo |
| Prompt da peça fixo num único negócio, não parametrizado por workspace | **Perfil por projeto** (D11) vindo no pedido |
| Peça sem arquivo | Biblioteca com hash, licença e relatório por peça (spec 05) |

### Estado do banco do Ops (referência de volume)
7 pesquisas, 7 fichas de produto, 6 campanhas e 4 peças criativas, todas ainda em texto.

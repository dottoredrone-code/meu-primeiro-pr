# 07 — Estudo: Torralles Ops e o Cérebro Centralizado

> Fonte: trechos do `CEREBRO_MESTRE.md` lidos numa sessão de 26/08/2026 (seção "Histórico de implementações"
> e base de conhecimento). **Não** tive acesso direto ao código do Torralles Ops, que fica no computador
> do Diego: o que está aqui pode estar desatualizado e precisa ser confirmado antes de integrar.

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

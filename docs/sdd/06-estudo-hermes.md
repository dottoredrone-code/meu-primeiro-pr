# 06 — Estudo: Hermes Agent e integração com o Torralles Studio

> Estudo feito em 15/10/2026 sobre o código público do Hermes Agent (Nous Research, licença **MIT**),
> versão de 15/10/2026. O **Torralles Ops** e a ponte/memória do Hermes rodam no computador do Diego e
> **não estão acessíveis** desta sessão na nuvem: esta parte do estudo fica pendente (ver "Próximos passos").

## O que o Hermes já oferece (relevante para o Studio)

| Capacidade do Hermes | Como funciona | Relação com o nosso plano |
|---|---|---|
| **Kanban de agentes** (`hermes kanban`, painel `hermes dashboard`) | Tarefas atribuídas a perfis de agente, com comentários, re-execução e monitoramento | Cobre o "Kanban" de **produção de conteúdo** |
| **Skill `kanban-video-orchestrator`** (MIT) | Descoberta → brief → montagem da equipe → execução em kanban → monitoramento. Papéis: diretor (só delega), roteirista, diretor de arte, storyboarder, gerador de imagem, imagem→vídeo, editor, **revisor** (portão de qualidade) | Quase o fluxo inteiro do Studio, já pronto como orquestração |
| **Perfis** (`hermes profile`, `SOUL.md` por perfil) | Cada perfil tem personalidade, ferramentas, skills e memória próprias | Encaixa na decisão **D11** (um perfil por projeto/canal, sem misturar) |
| **Memória e aprendizado** | Memória curada pelo agente, busca FTS5 nas conversas, modelagem do usuário, skills que se auto-aperfeiçoam | Substitui boa parte da memória "perfil e histórico" da spec 05 |
| **Geração de imagem** (`image_generate`) | Catálogo FAL: Nano Banana 2/Pro, FLUX 2, GPT Image 2/2.5, Ideogram, Recraft, Qwen… | Mesmo ecossistema que escolhemos (fal.ai) |
| **Geração de vídeo** (`video_generate`) | Plugins: fal, xAI, OpenRouter, DeepInfra | **Um provedor ativo por vez**, sem fallback entre eles |
| **Voz e transcrição** | TTS (OpenAI, local, plugins) e Whisper (local, whisper.cpp, nuvem) | Cobre voz e as checagens de WER da spec 03 |
| **Visão** (`vision_analyze`, `video_analyze`) | Envia quadros/clipes para modelo multimodal | Base do juiz de IA |
| **Fallback de modelo de texto** | Cadeia ordenada de provedores quando o principal falha | Equivalente ao nosso, mas **só para texto** |
| **Agendamento (cron)** e **gateway** | Tarefas recorrentes; conversa por Telegram, WhatsApp, Discord etc. | Pedir vídeos pelo celular; publicar em série |
| **MCP** (cliente e servidor) | Usa qualquer servidor MCP como ferramenta | Caminho de integração com o Studio |
| Outras skills úteis | `youtube-content` (transcrição/resumo), `creative-ideation` (ideação com métodos, anti-clichê), `social-media-content-calendar`, `ai-presenter-video` (apresentador com lip-sync e checagem), `humanizer` (tira o "jeito de IA" do texto) | Pesquisa, criatividade e calendário editorial |

## O que o Hermes **não** tem (o diferencial do Studio)

1. **Fallback entre provedores de imagem, vídeo e voz**: no Hermes há um provedor ativo por ferramenta.
2. **Controle de qualidade numérico com loop**: o revisor do Hermes é um papel qualitativo. Faltam régua com pesos, eliminatórios, pisos, 2 juízes, calibração e refazer só a peça reprovada (specs 01 e 03).
3. **Teto de custo por vídeo** que interrompe a execução e **custo real** por etapa.
4. **Biblioteca de mídia com licença por peça**, cache por hash e retomada sem pagar duas vezes (spec 05).
5. **Exportação para CapCut**.

## Opções de integração

| Opção | Como seria | Prós | Contras |
|---|---|---|---|
| **A. Studio independente** (rumo atual) | App próprio com orquestração, memória e kanban | Controle total | **Refaz o que o Hermes já faz** (kanban, perfis, memória, gateway) |
| **B. Studio dentro do Hermes** | Só skills e plugins do Hermes | Máximo reaproveitamento | Fica preso ao Hermes; mais difícil de vender separado |
| **C. Híbrido (recomendado)** | O **motor do Studio** (fallback por mídia + qualidade + custo + biblioteca) vira um pacote Python com **servidor MCP**. O Hermes/Torralles Ops orquestra (kanban, perfis, memória, agenda, Telegram) e chama o Studio como ferramenta | Cada um faz o que faz melhor; o Studio continua utilizável sozinho e vendável; nada é duplicado | Duas peças para manter (mitigado: o Hermes já está instalado e é MIT) |

### Como ficaria a opção C

```
Você (CLI, Telegram, WhatsApp)
   │
Hermes / Torralles Ops ── perfis por projeto (Conexão Família Torralles, Empório Oriental, …)
   │  kanban-video-orchestrator: diretor → roteirista → arte → revisor …
   │  memória, skills, agenda
   │
   └──► MCP: torralles-studio
          ├─ gerar_imagem / gerar_voz / gerar_video  (com fallback e teto de custo)
          ├─ avaliar_peca  (régua da spec 03, 2 juízes, loop)
          ├─ montar_video / exportar_capcut
          └─ biblioteca e relatório de custo/qualidade
```

## Impacto nas specs

| Spec | Mudança se a opção C for aprovada |
|---|---|
| 01/03 Qualidade | Continua no Studio; o revisor do Hermes passa a usar a ferramenta `avaliar_peca` |
| 05 Memória | "Perfil e estilo" e "histórico" ficam nos **perfis e na memória do Hermes**; o Studio guarda só aprendizados de qualidade e a biblioteca |
| 05 Banco/biblioteca | Sem mudança (é o diferencial) |
| Kanban | **Produção de conteúdo** no kanban do Hermes; **desenvolvimento do Studio** no GitHub (Projects ou `KANBAN.md`) |
| Fallback | Mantido e estendido para imagem, vídeo e voz; texto pode usar o do próprio Hermes |

## Próximos passos

1. **Ver o Torralles Ops**: os agentes criadores e a agência já devem ser perfis/skills do Hermes. Para estudá-lo, uma destas:
   - abrir no computador uma sessão do Claude Code com **Remote Control** na pasta do Torralles Ops/Hermes (as sessões de ponte aparecem como desconectadas agora); ou
   - enviar o Torralles Ops para um repositório GitHub privado e liberar o acesso a esta sessão; ou
   - exportar os arquivos principais (`SOUL.md` dos perfis, skills próprias, configuração, sem chaves) para uma pasta do Google Drive.
2. Confirmar quais perfis e skills já existem, para mapear o que o Studio reaproveita e o que ele fornece.
3. Decidir entre A, B e C (recomendação: **C**).

## Fontes
- Repositório: https://github.com/NousResearch/hermes-agent (MIT), commit `db44c462`
- Documentação: https://hermes-agent.nousresearch.com/docs/
- Skill `kanban-video-orchestrator` (adaptada de https://github.com/NousResearch/kanban-video-pipeline)

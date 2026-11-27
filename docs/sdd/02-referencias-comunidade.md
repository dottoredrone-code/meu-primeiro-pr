# 02 — O que a comunidade já fez

> Pesquisa feita em 15/10/2026. Os números de estrelas variam entre as fontes e servem só como referência.

## Projetos parecidos com o app

| Projeto | O que faz | Licença | O que aproveitar | O que falta em relação ao nosso plano |
|---|---|---|---|---|
| **MoneyPrinterTurbo** (~112 mil ⭐, ativo em ago/2026) | Tema → roteiro → narração → vídeos de banco (Pexels/Pixabay) → legendas → música | **MIT** (pode usar comercialmente) | Já suporta DeepSeek, Gemini, OpenAI e mais LLMs; Edge TTS, Gemini TTS, ElevenLabs; interface web pronta | Usa vídeos de banco em vez de imagem/vídeo gerados por IA; sem fallback automático; sem controle de qualidade |
| **OpenMontage** (criado em mar/2026) | Roda **dentro do Claude Code**: pesquisa → proposta → roteiro → plano de cenas → assets → edição → composição (Remotion + FFmpeg) | **AGPLv3** (se virar serviço online, o seu código também precisa ser aberto) | O mais próximo da nossa visão: Kling, Veo, FLUX, ElevenLabs, e um **caminho grátis sem chaves**; propõe o tratamento antes de gastar | Sem versão estável; licença restritiva para um produto comercial fechado |
| **short-video-maker** (gyoridavid) | Servidor MCP/REST: Kokoro (voz) + Whisper (legendas) + Pexels + Remotion; exemplos com n8n | MIT | 100% grátis e local; integra com agentes via MCP | Vídeo de banco; sem IA generativa visual |
| **AutoShorts** | Pacote modular: roteiro (Ollama/OpenAI/Gemini/Claude), voz (ElevenLabs/local), imagens (Pexels) | aberto | Arquitetura modular por provedor | Sem fallback nem controle de qualidade |
| **OpenShorts** | Corta vídeos longos em shorts com reenquadramento 9:16 e legendas por palavra | aberto | Legendas por palavra e reenquadramento | Outro foco (corte de vídeo existente) |

## Projetos com loop de qualidade (o que mais nos interessa)

| Projeto | Como faz o controle de qualidade |
|---|---|
| **Agentic Video Editor** (poseljacob, Gemini + FFmpeg) | Um agente **Revisor** dá nota para aderência, ritmo, qualidade visual e "assistibilidade". Abaixo do limite, devolve feedback **com marcação de tempo** ao Diretor, que refaz o plano. Cada tentativa vira um arquivo versionado, e há limite de tentativas. É o modelo mais próximo da nossa spec 01. |
| **Kubrick** (artigo CVPR 2025) | Diretor → Programador → **Revisor** que analisa capturas de tela e corrige em loop. |
| **Tutorial Google ADK (CAI 2026)** | Agente "Supervisor de Continuidade" que verifica consistência de personagens, cenário e estilo entre os clipes. |

## Fallback entre modelos

**LiteLLM Router** (open source) faz o que o nosso roteador faz para texto: novas tentativas, fallback
para outro grupo de modelos e "descanso" após N falhas por minuto (`allowed_fails`, `cooldown_time`),
com estado compartilhado via Redis em produção. Isso **confirma o nosso desenho**. Para imagem, voz e
vídeo não encontramos nada equivalente pronto, então ali o nosso roteador continua necessário.

## Pesquisas sobre juiz de IA (afetam a spec 01)

- Juízes com visão concordam com humanos sobretudo nos **casos claramente ruins**. Para detalhes finos, erram mais.
- **Média de vários juízes** correlaciona melhor com humanos (~0,85) do que um juiz sozinho.
- Juízes podem ser **enganados** por imagens com truques visuais ou texto embutido.
- Um juiz aberto e pequeno (Qwen3-VL-8B) teve boa concordância com humanos (κ = 0,81).

## SDD e Kanban

- **GitHub Spec Kit** (MIT, ~115 mil ⭐): CLI de spec-driven development que funciona com o Claude Code. Fluxo: requisitos → design → tarefas → implementação → validação.
- **Kiro** (Amazon): IDE que gera requisitos, design e tarefas a partir de um prompt. Fica preso ao ecossistema dele.
- **OpenSpec** (mais leve, focado em mudanças) e **BMAD-METHOD** (vários agentes com papéis).
- **Vibe Kanban**: quadro Kanban em que cada cartão roda um agente (Claude Code etc.) na sua própria branch. **Está sendo descontinuado**, então não convém depender dele.

## Conclusões

1. **Ninguém junta as três coisas**: fallback por função + loop de qualidade + exportação para CapCut. Esse é o nosso diferencial.
2. **Não reinventar o que já existe:**
   - montagem e legendas: estudar o MoneyPrinterTurbo (MIT, pode copiar trechos com atribuição);
   - fluxo "propor antes de gastar": copiar a ideia do OpenMontage (sem copiar código, por causa da AGPL);
   - loop do revisor: seguir o padrão do Agentic Video Editor (feedback com marcação de tempo, tentativas versionadas).
3. **Ajustes na spec 01:** usar 2 juízes em média para imagem e vídeo, priorizar checagens objetivas e calibrar a nota mínima comparando com a sua avaliação nos primeiros ~20 vídeos.
4. **Processo:** adotar o formato do Spec Kit (requisitos → design → tarefas) nos documentos `docs/sdd/` e usar GitHub Projects ou `KANBAN.md` como quadro, em vez do Vibe Kanban.

## Fontes

- [MoneyPrinterTurbo review 2026](https://wavect.io/blog/moneyprinterturbo-review-2026.md), [MoneyPrinterTurbo (verdent)](https://www.verdent.ai/guides/moneyprinterturbo-github), [SourcePulse](https://www.sourcepulse.org/projects/1843149)
- [OpenMontage (Pinggy)](https://pinggy.io/blog/openmontage_agentic_video_production/), [OpenMontage (silenceper)](https://silenceper.com/en/article/2026-07-31-openmontage-agent-video-production/), [landscape](https://landscape.jimmysong.io/projects/open-montage/)
- [short-video-maker (Glama)](https://glama.ai/mcp/servers/gyoridavid/short-video-maker), [Docker Hub](https://hub.docker.com/r/gyoridavid/short-video-maker)
- [AutoShorts](https://www.sourcepulse.org/projects/1839779), [OpenShorts](https://mcpservers.org/servers/mutonby/openshorts), [clipgen](https://pypi.org/project/clipgen/)
- [Agentic Video Editor (pyshine)](https://pyshine.com/Agentic-Video-Editor-AI-Powered-Video-Production/), [gittrend](https://gittrend.io/repo/poseljacob/agentic-video-editor)
- [Kubrick (arXiv)](https://arxiv.org/abs/2408.10453), [Tutorial CAI 2026](https://www.ieeesmc.org/cai-2026/tutorial-10-a-human-ai-collaborative-framework/)
- [LiteLLM Routing](https://docs.litellm.ai/docs/routing)
- [MLLM-as-a-judge calibration](https://arxiv.org/pdf/2509.08777), [Fooling LVLM judges](https://arxiv.org/html/2505.15249v2), [LEGO-Puzzles](https://arxiv.org/pdf/2503.19990)
- [Spec Kit vs Kiro vs Claude Code](https://glukhov.org/ai-devtools/ai-coding-assistants/spec-kit-vs-kiro-vs-claude-code/), [Ferramentas SDD](https://ssojet.com/blog/best-spec-driven-development-tools)
- [Vibe Kanban](https://jimmysong.io/en/ai/vibe-kanban), [fork com aviso de descontinuação](https://github.com/MrEggs/vibe-kanban-fork)

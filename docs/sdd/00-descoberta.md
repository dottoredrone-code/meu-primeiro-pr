# 00 — Descoberta e verificação de ferramentas

> Fase 1–2 do protocolo (objetivo + entendimento). Verificado em **15/10/2026**.
> Preços e limites mudam com frequência: reconfirmar nas páginas oficiais antes de cada decisão de custo.

## Objetivo (rascunho, aguardando confirmação)

Um app que transforma **uma ideia em um vídeo curto completo** (pesquisa → roteiro → imagens →
narração → vídeo com legendas), escolhendo automaticamente o melhor modelo disponível para cada
etapa e caindo para alternativas gratuitas quando o preferido falhar ou não estiver configurado.

## Ambiente de desenvolvimento verificado

| Ferramenta | Situação |
|---|---|
| Python 3.13 | ok (o app usa só a biblioteca padrão) |
| Node 22 / npm 10 | ok (útil se o frontend for Next.js / Remotion) |
| FFmpeg 6.1 | ok, com `zoompan`, `xfade`, `subtitles`, `drawtext` (montagem, transições e legendas) |
| Docker 29 | ok |
| Git | ok |
| GPU | não há neste ambiente → modelos locais de vídeo/imagem (Wan, FLUX local) inviáveis aqui |
| Ollama, edge-tts, Whisper | não instalados (opcionais) |

## Serviços externos

Legenda: 🟢 ok · 🟡 funciona com ressalvas · 🔴 quebrado/precisa mudar no código atual

| Etapa | Serviço | Situação | O que muda |
|---|---|---|---|
| Texto | **DeepSeek** | 🔴 | Os nomes `deepseek-chat`/`deepseek-reasoner` (usados no config) foram aposentados em 24/07/2026. Atual: `deepseek-flash` (V4.1-Flash); `deepseek-v4-pro` com status a confirmar. Continua muito barato e compatível com OpenAI. |
| Texto | **Gemini** | 🔴 | `gemini-2.5-flash` desliga em 16/10/2026. Família atual: Gemini 3.x Flash (`gemini-3-flash-preview` tem cota grátis). |
| Texto | **Claude** | 🟢 | API ok. Haiku 5.5 (~US$ 0,10/0,50 por 1M tokens) é barato para fallback; Sonnet 5.5 (US$ 2/10) para revisão. Assinatura Pro/Max ≠ créditos de API. |
| Texto | **OpenAI** | 🟡 | Snapshot `gpt-5-mini-2025-08-07` desliga em 11/12/2026; substituto indicado: `gpt-5.4-mini`. |
| Texto | **OpenRouter grátis** | 🟡 | 20 req/min e **50 req/dia** (1.000/dia após comprar US$ 10 uma vez). Modelos `:free` somem sem aviso; o DeepSeek grátis pode ter virado pago. |
| Texto | **Ollama local** | 🟡 | Funciona no PC do usuário; não neste ambiente (sem GPU/sem instalação). |
| Busca | **Tavily** | 🟢 | ~1.000 créditos/mês grátis, sem cartão. |
| Busca | **Brave** | 🟡 | Plano grátis acabou para novos usuários: US$ 5/mês de crédito (~1.000 buscas), exige cartão. |
| Imagem | **Nano Banana (Gemini)** | 🔴 | `gemini-2.5-flash-image` foi desligado em 02/10/2026. Atual: `gemini-3.1-flash-image` (Nano Banana 2). A cota grátis de imagem na API é provavelmente **zero**: tratar como pago (~US$ 0,05–0,10/imagem). |
| Imagem | **fal.ai FLUX schnell** | 🟢 | Pago por uso, barato. |
| Imagem | **OpenAI GPT Image** | 🔴 | `gpt-image-1` desliga em 23/10/2026 → migrar para `gpt-image-2`. |
| Imagem | **Pollinations** | 🟡 | Endpoint antigo sem chave ainda existe, mas limitado (~1 req/15 s, pode ter marca d'água); o novo exige chave grátis. Bloqueado na rede deste ambiente. |
| Voz | **ElevenLabs** | 🟡 | Grátis: ~10.000 créditos/mês, **sem uso comercial** e com atribuição. Comercial a partir do Starter (~US$ 5–6/mês). |
| Voz | **OpenAI TTS** | 🟡 | Snapshot antigo do `gpt-4o-mini-tts` já desligado; confirmar o alias atual. |
| Voz | **Edge TTS** | 🟢 | Pacote mantido (v7.2.8, 2026), grátis, mas usa acesso **não oficial** à Microsoft. |
| Voz | **Gemini TTS** | 🟢 novo | `gemini-3.1-flash-tts-preview`: candidato extra para a cadeia de voz. |
| Vídeo | **Kling (fal.ai)** | 🔴 | Versão atual é a **v3** (`fal-ai/kling-video/v3/...`), que usa o parâmetro `start_image_url`; nosso código envia `image_url`. ~US$ 0,11/s (sem áudio). Concorrência padrão: 1. |
| Vídeo | **Wan (fal.ai)** | 🔴 | O endpoint configurado está desatualizado; atual: `fal-ai/wan-25-preview/image-to-video` (`image_url` aceita data URI). |
| Vídeo | **Ken Burns (FFmpeg)** | 🟢 | Testado: gera 1280×720 localmente, grátis. |
| Edição | **FFmpeg** | 🟢 | Corte, concatenação, transições (`xfade`), legendas queimadas. Base do "CapCut". |
| Edição | **Remotion** | 🟡 | Grátis para empresas de até 3 pessoas; para automação em escala, ~US$ 0,01/render com mínimo de US$ 100/mês. |
| Legendas | **Whisper** | 🟢 | Open source, roda local (CPU serve para vídeos curtos). |
| Design | **Canva** | 🟡 | A API do Canva é limitada para isso; alternativa: editor próprio com Fabric.js/Konva ou templates em HTML → imagem. |

## Conclusões

1. **O mecanismo de fallback está certo, mas o catálogo envelheceu.** 7 itens 🔴 no config/código:
   isso prova que os nomes de modelo precisam ser tratados como dado vivo (config + verificação periódica),
   não como código.
2. **"Grátis" encolheu em 2026**: imagem no Gemini, Brave e OpenRouter ficaram pagos ou muito limitados.
   A espinha dorsal gratuita confiável hoje é: Tavily (busca), Gemini 3 Flash preview (texto),
   Edge TTS (voz), Ken Burns/FFmpeg (vídeo), Whisper (legendas). Imagem grátis é o elo mais fraco.
3. **Custo dominante é o vídeo com IA** (~US$ 0,55 por cena de 5 s no Kling v3). Precisa de orçamento por projeto.
4. **Uso comercial** exige atenção às licenças (ElevenLabs grátis, Pollinations, Edge TTS não oficial).

## Fontes

- DeepSeek: [Change Log](https://api-docs.deepseek.com/updates/), [V4.1-Flash](https://api-docs.deepseek.com/news/news260910/), [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- Gemini: [Deprecations](https://ai.google.dev/gemini-api/docs/deprecations?hl=en), [Gemini 3](https://ai.google.dev/gemini-api/docs/gemini-3), [Models](https://ai.google.dev/gemini-api/docs/models), [Flash TTS](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-tts-preview), [Nano Banana free limit](https://blog.laozhang.ai/en/posts/gemini-image-generation-free-limit-2026)
- OpenAI: [Deprecations](https://developers.openai.com/docs/deprecations), [Aviso de desligamentos 2026](https://community.openai.com/t/deprecation-notice-upcoming-model-shutdowns-in-2026/1379553)
- Claude: [Pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Models overview](https://platform.claude.com/docs/en/models/overview)
- OpenRouter: [limites grátis](https://benchlm.ai/md/free-tier/openrouter.md), [TrueFoundry](https://www.truefoundry.com/pt/blog/openrouter-rate-limits-your-free-tier-depends-on-what-youve-already-paid)
- Busca: [Brave sem plano grátis](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing.md), [APIs de busca grátis](https://parallel.ai/articles/best-free-web-search-api)
- fal.ai: [Kling v3 Pro i2v](https://fal.ai/models/fal-ai/kling-video/v3/pro/image-to-video/api), [Wan 2.5 i2v](https://fal.ai/models/fal-ai/wan-25-preview/image-to-video/api)
- ElevenLabs: [preços 2026](https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs/)
- Pollinations: [API sem chave](https://blogs.novita.ai/free-ai-image-generation-api-no-key-required/), [free tier](https://agentdeals.dev/vendor/pollinations-ai)
- Edge TTS: [DepScope](https://depscope.dev/pkg/pypi/edge_tts)
- Remotion: [licença e preços](https://www.remotion.dev/docs/license/pricing)

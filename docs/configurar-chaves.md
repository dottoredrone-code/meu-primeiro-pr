# Como obter e configurar as chaves de API

## Ordem sugerida (comece pelo mínimo)

| Prioridade | Serviço | Para quê | Custo para começar | Onde criar a chave | Variável |
|---|---|---|---|---|---|
| 1 | **Google AI Studio (Gemini)** | Texto grátis, juiz de qualidade, imagem (pago) | Grátis (imagem exige faturamento ativo) | aistudio.google.com → *Get API key* | `GEMINI_API_KEY` |
| 1 | **DeepSeek** | Roteiro, ideias, pesquisa | Recarga mínima de poucos dólares | platform.deepseek.com → *API keys* (recarregar em *Top up*) | `DEEPSEEK_API_KEY` |
| 1 | **Tavily** | Busca na web | Grátis (~1.000 créditos/mês, sem cartão) | app.tavily.com → *API Keys* | `TAVILY_API_KEY` |
| 2 | **fal.ai** | Imagens FLUX e vídeos Kling/Wan | Pré-pago (recarga de créditos) | fal.ai → *Dashboard* → *Keys* | `FAL_KEY` |
| 2 | **Anthropic (Claude)** | Revisão, juiz, fallback de texto | Pré-pago | platform.claude.com → *API keys* (créditos em *Billing*) | `ANTHROPIC_API_KEY` + `CLAUDE_MODEL` |
| 3 | **ElevenLabs** | Voz premium | Grátis ~10 mil créditos/mês, **sem uso comercial** | elevenlabs.io → perfil → *API Keys* | `ELEVENLABS_API_KEY` |
| 3 | **OpenAI** | Fallback de texto, imagem e voz | Pré-pago | platform.openai.com → *API keys* | `OPENAI_API_KEY` |
| 3 | **OpenRouter** | Modelos grátis (50 pedidos/dia) | Grátis | openrouter.ai → *Keys* | `OPENROUTER_API_KEY` |
| 2 | **Pexels** | Fotos e vídeos gratuitos (licença Pexels) | Grátis | pexels.com/api → *Your API key* | `PEXELS_API_KEY` |
| 2 | **Pixabay** | Fotos e vídeos gratuitos (licença Pixabay) | Grátis | pixabay.com/api/docs (logado) | `PIXABAY_API_KEY` |
| 2 | **Freesound** | Efeitos sonoros (CC0 e CC-BY) | Grátis | freesound.org/apiv2/apply → *API key* | `FREESOUND_API_KEY` |
| — | **Openverse** | Imagens e sons Creative Commons | Grátis, funciona sem chave (com limite menor) | api.openverse.org (opcional) | `OPENVERSE_TOKEN` |
| — | **Edge TTS** | Voz grátis | Grátis, sem chave | `pip install edge-tts` | — |
| — | **FFmpeg** | Vídeo grátis e montagem | Grátis, sem chave | já instalado | — |

Com só as 3 de prioridade 1 (duas grátis + recarga pequena no DeepSeek), o modo econômico já funciona:
pesquisa, roteiro, voz (Edge) e vídeo (Ken Burns). Imagem precisa de pelo menos uma opção paga
(fal.ai é a mais barata) ou do Pollinations.

## Cuidados de segurança

- **Nunca** cole uma chave no chat, em issues ou em commits. O arquivo `.env` já está no `.gitignore`.
- Configure **limite de gastos** em cada painel (DeepSeek, fal.ai, Anthropic e OpenAI permitem pré-pago ou limite mensal).
- Crie uma chave **só para o Torralles Studio**, assim dá para revogar sem afetar outros usos.
- Se uma chave vazar, **revogue no painel e crie outra** na hora.
- No plano grátis do Gemini, o Google pode usar os dados enviados para melhorar os produtos: não envie nada sigiloso por ali.

## Onde colocar as chaves

### No seu computador
```bash
cp .env.example .env    # depois preencha as chaves no .env
python -m torralles_studio status
```

### No ambiente de nuvem do Claude Code (para os testes aqui)
1. No título da sessão, abra o menu do ambiente de nuvem → **Edit**.
2. Em **Network secrets** (ou *API credentials*, ou como variável de ambiente), adicione cada chave com o **mesmo nome da variável** da tabela acima.
3. Em **Network access**, libere os domínios dos serviços (o Google e a Anthropic já funcionam):
   `api.deepseek.com`, `api.tavily.com`, `fal.run`, `fal.media`, `api.elevenlabs.io`, `api.openai.com`,
   `openrouter.ai`, `image.pollinations.ai`, `speech.platform.bing.com` (Edge TTS).
   Mantenha marcada a opção de permitir gerenciadores de pacotes (para instalar `edge-tts` e Whisper).
4. Abra uma **nova sessão** para as mudanças valerem.

Passo a passo oficial do acesso à rede: https://code.claude.com/docs/en/cloud-environments#network-access

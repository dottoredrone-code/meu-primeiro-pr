# Revisão de modelos, preços e limites (KR1)

Revisão mensal. Os preços entram em `config/fallbacks.toml` como **estimativa por chamada** (a favor do bolso),
usada pelo teto de US$ 1,50 por vídeo (D20). Confirmar sempre na página oficial quando possível.

## 24/10/2026 (feita da nuvem; páginas oficiais do Google e de alguns provedores inacessíveis daqui)

| Provedor (config) | Modelo | Preço encontrado | Custo por chamada no config | Antes | Confiança |
|---|---|---|---|---|---|
| deepseek_chat | deepseek-flash (V4 Flash) | US$ 0,14 / 0,28 por 1M tokens | 0,001 | 0,001 | média (agregadores) |
| deepseek_reasoner | deepseek-v4-pro | US$ 1,74 / 3,48 por 1M (promoção de 75% citada, talvez encerrada) | 0,014 | 0,003 | média |
| gemini_flash | gemini-3.6-flash | US$ 1,50 / 7,50 por 1M (3.8 Flash citado a 0,75 / 3,75) | 0,015 | 0,003 | média — **testar 3.8 Flash** |
| gemini_video | gemini-3.6-flash | ~290 tokens/s de vídeo + áudio | 0,003 + 0,0009/s (30 s ≈ 0,03; sem duração conhecida, conta 60 s) | 0,05 | média |
| gemini_voz | gemini-3.8-flash-tts | não encontrado | 0,01 (mantido) | — | baixa — confirmar no teste real |
| nano_banana | gemini-3.1-flash-image | não encontrado (exige faturamento) | 0,06 (mantido) | 0,06 | baixa |
| claude | CLAUDE_MODEL (claude-sonnet-5-5) | US$ 2 / 10 por 1M (Haiku 5.5: 0,10 / 0,50) | 0,02 | 0,02 | alta (referência oficial) |
| openai_mini | gpt-5.4-mini | US$ 0,75 / 4,50 por 1M (página oficial) | 0,009 | 0,003 | alta |
| openai_imagem / openai_voz | gpt-image-2 / gpt-4o-mini-tts | não confirmado | mantidos | — | baixa (sem chave em uso) |
| fal_flux | flux/schnell | US$ 0,003 por megapixel | 0,004 | 0,004 | média |
| fal_kling | kling v3 standard | US$ 0,112–0,14 por segundo (v3) | 0,14/s | 0,084/s | média |
| fal_wan | wan-25-preview | US$ 0,05 / 0,10 / 0,15 por s (480p / 720p / 1080p) | 0,10/s | 0,05/s | média |
| tavily | busca | 1.000 créditos grátis/mês; depois US$ 0,008 por crédito | 0 (dentro do grátis) | 0 | alta (docs oficiais) |

**Mudanças de API que importam:**
- Claude: desde 21/10/2026 a API recusa `temperature`/`top_p`/`top_k` (o Studio não envia). Modelos atuais pensam
  antes de responder e o raciocínio conta no `max_tokens`: o provedor agora pede 16.000 e trata "resposta cortada"
  e "recusa" como falha (vai para o próximo da cadeia).
- ElevenLabs grátis não permite uso comercial (D2): só com plano pago.

**Para a próxima revisão:** testar `gemini-3.8-flash` no lugar do 3.6 (mais barato, se confirmado); confirmar
TTS e imagem do Gemini; preço real da promoção do DeepSeek V4 Pro; resolução que o fal usa no Wan sem parâmetro.

**Fontes:** [DeepSeek API Pricing (Puter)](https://developer.puter.com/tutorials/deepseek-api-pricing/) ·
[DeepSeek V4 Pro (Trevor Fox)](https://trevorfox.com/tools/calculators/llm-cost/deepseek/deepseek-v4-pro/) ·
[Gemini API Pricing 2026 (Morph)](https://www.morphllm.com/gemini-api-pricing) ·
[Gemini 3.8 Flash Pricing](https://anotherwrapper.com/llm-pricing/gemini-3.8-flash) ·
[Gemini API pricing 2026 (Hashnode)](https://hashnode.com/blog/gemini-api-pricing-2026) ·
[OpenAI API Pricing](https://openai.com/api/pricing/) ·
[fal.ai pricing (Wireflow)](https://www.wireflow.ai/fal-ai-pricing) ·
[Kling API vs fal (CostBench)](https://costbench.com/compare/fal-vs-kling-api/) ·
[Tavily API credits](https://docs.tavily.com/documentation/api-credits.md)

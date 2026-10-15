# 04 — Benchmark prévio: Torralles Studio vs. o mercado

> Fase 1 (pesquisa de mesa), feita em 15/10/2026. Preços vêm em sua maioria de comparadores de terceiros,
> que divergem entre si: os valores são **faixas aproximadas**. Confirmar nas páginas oficiais antes de assinar.
> A fase 2 (teste prático) está descrita na seção [Protocolo do teste prático](#protocolo-do-teste-prático).

## 1. Quem são os concorrentes

| Grupo | Ferramentas | Para que servem |
|---|---|---|
| **Ideia → vídeo completo** | InVideo AI, Revid, AutoShorts, Pictory, Fliki | Do texto ao vídeo pronto, quase sempre com **vídeos de banco** + narração |
| **Geradores de vídeo por IA** | Kling, Runway, Pika, Higgsfield, Google Flow (Veo) | Geram **clipes** de poucos segundos; não montam o vídeo inteiro |
| **Editores** | CapCut, Canva | Montagem e acabamento manual, com alguns recursos de IA |
| **Open source** | MoneyPrinterTurbo, OpenMontage, short-video-maker | Pipelines automáticos para rodar por conta própria |

## 2. Comparação de recursos

Legenda: ✅ tem · 🟡 parcial/limitado · ❌ não tem

| Recurso | InVideo AI | Revid / AutoShorts | Pictory / Fliki | Kling / Runway / Pika / Higgsfield | Google Flow (Veo) | CapCut | Canva | MoneyPrinterTurbo | OpenMontage | **Torralles Studio (plano)** |
|---|---|---|---|---|---|---|---|---|---|---|
| Ideia → vídeo completo | ✅ | ✅ | ✅ | ❌ só clipes | ❌ só clipes | ❌ | 🟡 | ✅ | ✅ | ✅ |
| Pesquisa com fontes | ❌ | ❌ | 🟡 resume textos | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Imagens geradas por IA | ✅ | 🟡 | 🟡 | ✅ | ✅ | 🟡 | ✅ | ❌ banco | ✅ | ✅ |
| Vídeo gerado por IA | ✅ | 🟡 | ❌ | ✅ | ✅ | ❌ | 🟡 Veo (pago) | ❌ | ✅ | ✅ |
| Narração pt-BR | ✅ | ✅ | ✅ (Fliki: 2.000+ vozes) | 🟡 | 🟡 | ✅ | 🟡 | ✅ Edge TTS | ✅ | ✅ |
| Escolhe o modelo por etapa | ❌ | ❌ | ❌ | 🟡 (Higgsfield agrega vários) | ❌ | ❌ | ❌ | 🟡 escolha manual | 🟡 | ✅ |
| **Fallback automático** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Controle de qualidade com loop** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 propõe antes de gerar | ✅ |
| Limite de custo por vídeo | ❌ | ❌ | ❌ | ❌ | ❌ | — | — | — | ❌ | ✅ |
| Editor manual (linha do tempo) | ✅ | 🟡 | 🟡 | ❌ | 🟡 | ✅ | ✅ | ❌ | ❌ | 🟡 via exportação para CapCut |
| Funciona grátis | 🟡 marca d'água | ❌ | 🟡 | 🟡 poucos créditos | 🟡 50 créditos/dia | ✅ | 🟡 | ✅ | ✅ caminho grátis | ✅ modo econômico |
| Você controla os dados e o código | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Licença p/ produto próprio | — | — | — | — | — | — | — | ✅ MIT | ⚠️ AGPL | ✅ código próprio |

## 3. Preços de referência (faixas, out/2026)

| Ferramenta | Grátis | Planos pagos | Observação |
|---|---|---|---|
| InVideo AI | fraco/incerto (marca d'água, 720p) | ~US$ 17–28 a US$ 900+/mês | Créditos não acumulam; um curta de 70 s documentado consumiu ~US$ 750 em créditos |
| Revid / AutoShorts | ❌ | ~US$ 15–49/mês | Muito vídeo de banco |
| Pictory / Fliki | Fliki tem plano grátis | ~US$ 19–79/mês | Foco em narração + banco de imagens |
| Higgsfield | sem uso comercial | ~US$ 15–129/mês | Revisão independente estima **3–5 tentativas por clipe aproveitável** |
| Runway | — | ~US$ 12–15/mês (Standard ≈ 52 s de Gen-4.5) | Créditos expiram |
| Pika | limitado | ~US$ 8–95/mês | Aumentou preço em abr/2026 |
| Google Flow (Veo) | 50 créditos/dia | US$ 4,99–199,99/mês | API: ~US$ 0,05–0,60 por segundo |
| CapCut | ✅ bom | ~US$ 10–20/mês | Sem geração de vídeo por texto |
| Canva | 5 clipes de 4 s **na vida** | Pro ~US$ 13–18/mês (~20 clipes Veo/mês) | |
| MoneyPrinterTurbo / OpenMontage | ✅ | custo só das APIs que você usar | |

## 4. Custo estimado do Torralles Studio por vídeo

Vídeo de 30 s, 6 cenas de 5 s, com folga de 50% para as repetições do loop de qualidade:

| Etapa | Modo econômico | Modo premium |
|---|---|---|
| Pesquisa (Tavily) + roteiro (DeepSeek) | ~US$ 0,00–0,01 | ~US$ 0,01 |
| 6 imagens | FLUX schnell ~US$ 0,02 | Nano Banana 2 ~US$ 0,30 |
| Narração | Edge TTS: grátis | ElevenLabs Starter (assinatura ~US$ 5–6/mês) |
| 6 cenas de vídeo | Ken Burns/FFmpeg: grátis | Kling v3 (30 s × ~US$ 0,11) ~US$ 3,40 |
| Controle de qualidade | ~US$ 0,05 | ~US$ 0,10 |
| **Total (com folga do loop)** | **~US$ 0,10–0,15** | **~US$ 5–6** |

Dá para **misturar**: Kling só nas 1–2 cenas mais importantes (gancho) e Ken Burns no resto,
o que fica perto de **US$ 1–1,50** por vídeo.

## 5. Leitura do benchmark

**Onde o Torralles Studio pode ganhar**
1. **Fallback + controle de qualidade com loop + limite de custo**: nenhuma ferramenta do mercado combina os três. Os concorrentes cobram por tentativa, e a Higgsfield, por exemplo, precisa de 3–5 tentativas por clipe bom. O nosso loop rejeita o ruim **antes** de gastar na etapa cara (avaliar a imagem antes de virar vídeo).
2. **Pesquisa com fontes antes do roteiro**, que quase ninguém faz e que importa para conteúdo informativo.
3. **Custo**: o modo econômico sai ~100× mais barato que assinaturas de US$ 20–100/mês, e você escolhe o modelo de cada etapa.
4. **Dados e código seus**, sem depender de uma plataforma que muda preço (InVideo, Pika e Canva mudaram em 2026).

**Onde o Torralles Studio perde (e como compensar)**
1. **Editor visual**: CapCut e Canva são imbatíveis → não competir; **exportar para o CapCut**.
2. **Acabamento e templates prontos**: o InVideo tem anos de templates → começar com 2–3 estilos próprios bem feitos.
3. **Facilidade**: as ferramentas comerciais são "clicar e pronto" → no início é aceitável, pois o uso é pessoal; uma interface simples vira prioridade só se partirmos para a venda.
4. **Manutenção**: os modelos mudam todo mês (vimos 7 desatualizados) → cartão fixo de verificação mensal no Kanban.

**Decisão sugerida**: seguir com o Torralles Studio, sem reinventar o que já existe: montagem inspirada no
MoneyPrinterTurbo (MIT), acabamento no CapCut, vídeos de IA via fal.ai/Kling.

## Protocolo do teste prático

Para confirmar a pesquisa de mesa com resultados reais, antes de construir a versão completa:

1. **3 briefings iguais para todos**, em pt-BR, 9:16, ~30 s:
   - A. Informativo: *"história do café no Brasil"* (testa a pesquisa e a precisão)
   - B. Explicativo: *"como funciona a fotossíntese"* (testa clareza e fidelidade)
   - C. Visual/emocional: *"amanhecer numa fazenda de café"* (testa imagem e vídeo)
2. **Ferramentas testadas nos planos grátis**: CapCut, InVideo AI, Canva, Google Flow, MoneyPrinterTurbo e o protótipo atual do Torralles Studio (modo econômico).
3. **Avaliação** com os parâmetros da [spec 03](03-parametros-avaliacao.md), a mesma régua para todos, mais:
   - tempo até o vídeo pronto;
   - custo real (ou créditos gastos);
   - número de intervenções manuais;
   - número de tentativas até um resultado aceitável;
   - qualidade da voz e da legenda em pt-BR.
4. **Notas dadas por você** (é também a primeira rodada de calibração dos juízes de IA).
5. Resultado registrado em `docs/sdd/04b-benchmark-pratico.md`.

## Fontes

- InVideo: [Creatify](https://creatify.ai/blog/invideo-pricing-(2026)-plans-credits-and-what-you-ll-actually-pay), [Magic Hour](https://magichour.ai/blog/invideo-ai-pricing), [CostBench](https://costbench.com/software/ai-video-generators/invideo-ai/free-plan/), [Toolradar](https://toolradar.com/tools/invideo-ai/pricing)
- Faceless: [Argil (AutoShorts)](https://www.argil.ai/blog/autoshorts-ai-review-2026-features-pricing-and-better-alternatives), [Subclip (Revid)](https://www.subclip.app/blogs/top-10-revid-ai-alternatives), [Aituber](https://aituber.app/blog/best-ai-faceless-video-generators/), [FlowShorts](https://flowshorts.app/alternatives/pictory)
- Fliki/Pictory: [Capterra](https://www.capterra.com/p/246351/Fliki/pricing/), [Toolquestor](https://toolquestor.com/vs/pictory-vs-fliki-ai), [Vivideo](https://vivideo.ai/bg/sravnenie/fliki-vs-pictory)
- Higgsfield: [Creatify](https://creatify.ai/blog/higgsfield-pricing-(2026)-plans-and-what-you-ll-actually-pay), [Recurdash](https://recurdash.com/subscription-pricing/higgsfield), [Luma (custo por clipe)](https://lumalabs.ai/news/higgsfield-pricing)
- Runway: [Creatify](https://creatify.ai/blog/runway-pricing-(2026)-plans-credits-and-what-you-ll-actually-pay), [Magic Hour](https://magichour.ai/blog/runway-gen-45-pricing)
- Pika: [gptprompts](https://gptprompts.ai/pika-pricing), [CostBench](https://costbench.com/changelog/pika-price-increase-2026-04/)
- Veo/Flow: [diyai](https://diyai.io/ai-tools/video-generation/google-veo-pricing/), [Magic Hour](https://magichour.ai/blog/veo-3-pricing)
- Canva: [eesel](https://eesel.ai/blog/canva-ai-pricing), [Morphed](https://morphed.app/blog/canva-ai-video-generator-pricing)
- Demais referências: [00-descoberta](00-descoberta.md) e [02-referencias-comunidade](02-referencias-comunidade.md)

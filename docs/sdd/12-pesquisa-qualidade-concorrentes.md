# 12 — Pesquisa: como o mercado mede qualidade e escolhe trilhas

> Pesquisa feita em 16/10/2026 para a decisão D17 (referência mais concreta e técnica) e D19 (trilhas escolhidas pelo Studio).
> Fontes no fim. Números de blogs de fornecedores estão marcados como **direção**; os de artigos científicos, como **base**.

## 1. Como os concorrentes avaliam

| Quem | O que mede | Como | O que aproveitar |
|---|---|---|---|
| **OpusClip — Virality Score** | Nota 0–99 com 4 critérios: **Gancho** (prende e tem relação com o tema), **Fluxo** (sequência lógica e final satisfatório), **Valor** (útil, emociona, cria conexão), **Tendência** (combina com o que está em alta) | Modelo treinado com pares (clipe, desempenho real nas redes); detalhes não publicados. Avaliações independentes: bom para priorizar, "não é verdade absoluta"; um teste descartou ~40% dos cortes | Adotar os **4 critérios como nota de "potencial"**, separada da nota técnica; depois calibrar com o **desempenho real dos seus vídeos** |
| **VBench** (CVPR 2024, referência acadêmica para vídeo gerado por IA) | 16 dimensões; as automatizáveis para nós: **consistência do personagem**, **consistência do fundo**, **tremulação**, **suavidade do movimento**, **grau de movimento**, **qualidade estética**, **qualidade de imagem** | Estética: preditor LAION por quadro (0–10), média no vídeo | Usar essas dimensões como **critérios técnicos objetivos** dos vídeos gerados (Kling/Wan) |
| **DOVER** | Qualidade técnica (distorções) + estética do vídeo inteiro, sem precisar de vídeo de referência | Rede treinada; concorda bem com humanos dentro do tipo de vídeo em que foi treinada (~0,85), mas **cai fora dele** | Útil como sinal extra, **nunca sozinho** |

**Conclusão:** nenhum concorrente publica uma régua completa. O mais sólido é combinar
(a) métricas técnicas objetivas no estilo VBench, (b) os 4 critérios de potencial no estilo OpusClip e
(c) **calibração com desempenho real** (retenção dos seus vídeos no YouTube Studio).

## 2. Números técnicos encontrados

| Parâmetro | Valor | Força da fonte | Impacto na spec 03 |
|---|---|---|---|
| Diferença de volume **voz × música** | **≥ 10 LU** (teste de escuta acadêmico); ambiência ≥ 15 LU; leigos preferem diferenças ~4 LU maiores que especialistas | **Base** | Trocar "música 12 dB abaixo" por **voz ≥ 10 LU acima da música (alvo 12)** e **≥ 15 LU acima da ambiência** |
| Velocidade de narração | Documentário **135–150 palavras/min** (2,25–2,5 por s); conversa 130–160 | Direção | Faixa por formato: explicativo 2,2–2,5 p/s; curto 2,5–3,0 p/s (a confirmar medindo referências) |
| Ritmo de cortes | MrBeast reduziu de **~38 para ~23 cortes/min** ao focar em história, e a audiência subiu (amostra pequena; não prova causa) | Direção | **Mais cortes não é melhor**: a meta de cortes/min é por categoria, medida nas referências |
| Gancho em Shorts | ~80% de retenção nos 3 primeiros segundos; 11–30 s é a faixa com melhores resultados | Direção | Mantido como alerta, não como meta |

## 3. Como as ferramentas escolhem trilha

- Ferramentas de sincronia analisam **andamento (BPM), marcação dos tempos e curva de energia** e colocam os cortes **no tempo da música**.
- Editores como Filmora analisam o **clima do vídeo** e sugerem trilhas com o mesmo tom emocional.
- Pesquisa em música usa **energia (arousal)** e **positividade (valence)** para classificar o clima: energia alta ≈ empolgante/tenso; positividade alta ≈ alegre/divertido.

### Regra de escolha proposta para o Studio (D19)
1. O roteiro define o **clima de cada parte** (ex.: abertura curiosa → desenvolvimento calmo → final inspirador).
2. Candidatas vêm do acervo/APIs com etiquetas de clima; o Studio mede **BPM e energia** de cada uma.
3. Pontuação da trilha (0–100):
   - **Clima** compatível com o roteiro (juiz ouvindo a prévia): 35
   - **Curva de energia** acompanha o arco do vídeo (sobe no gancho e no final): 25
   - **Sem vocal** competindo com a narração (instrumental): 20 (eliminatório se tiver letra durante a fala)
   - **Duração** suficiente ou com loop sem emenda audível: 10
   - **Licença** comercial clara: 10 (eliminatório se faltar)
4. Na montagem: **transições caem no tempo da música**, trilha abaixa sozinha quando a voz entra (≥ 10 LU de diferença).
5. **Você aprova o vídeo completo** no fim (D19).

### Ferramentas para medir música (atenção às licenças)
| Ferramenta | Serve para | Licença |
|---|---|---|
| **librosa** | BPM, marcação dos tempos, energia | ISC (permissiva) ✅ |
| **Juiz Gemini ouvindo** | Clima, vocal, adequação | Pago por uso ✅ |
| Essentia (+ modelos de clima) | Energia/positividade prontas | Biblioteca **AGPL** e modelos **CC BY-NC-SA** ⚠️: evitar no produto (D2) |

## 4. Base de referência concreta (como D17 pediu)
1. **Canais reconhecidos** por categoria (spec 09), 5 vídeos bons + 2 ruins cada, aprovados por você.
2. Cada vídeo passa pela **percepção** (spec 10): cortes/min, duração de plano, fala por segundo, LU voz × música, estrutura do roteiro, tipo de gancho, critérios de potencial (gancho, fluxo, valor, tendência).
   - Com a chave do Gemini, os vídeos do YouTube são analisados **pelo link**, sem baixar.
3. Resultado: **faixas medidas por categoria** (25º–75º percentil) que substituem os números estimados da spec 03 — é isso que tira a margem de erro.
4. Seus vídeos publicados entram depois como **referência própria**, com a retenção real do YouTube Studio.

## Fontes
- OpusClip: [Virality Score (oficial)](https://help.opus.pro/docs/article/virality-score), [API de momentos virais](https://www.opus.pro/blog/viral-moment-detection-api), [teste 2026 (BigVU)](https://bigvu.tv/blog/opus-clip-tested-2026-where-ai-wins-40-percent-discard/), [análise do score](https://marcandrews.com/?p=6263)
- VBench: [artigo CVPR 2024](https://openaccess.thecvf.com/content/CVPR2024/html/Huang_VBench_Comprehensive_Benchmark_Suite_for_Video_Generative_Models_CVPR_2024_paper.html), [VBench++](https://arxiv.org/pdf/2411.13503)
- DOVER: [artigo](https://arxiv.org/abs/2211.04894v3), [glossário](https://www.forasoft.com/learn/video-quality/glossary/terms-vqm/dover)
- Volume voz × música: [Univ. de Salford](https://salford-repository.worktribe.com/OutputFile/1488623)
- Narração: [Syllaby](https://syllaby.io/blog/voiceover-pacing-silence-trimming-retention-editing/), [CapCut](https://www.capcut.com/create/ai-voiceovers-natural-explainer-videos)
- Ritmo MrBeast: [Tubefilter](https://tubefilter.com/2024/03/04/mrbeast-editing-style-number-of-cuts-per-video/), [Passionfruit](https://passionfru.it/youtube-editing-mrbeast-54202/)
- Trilhas: [InVideo](https://invideo.io/blog/add-music-to-ai-generated-videos/), [Freebeat (beat sync)](https://freebeat.ai/auto-beat-sync-video), [Essentia](https://essentia.upf.edu/demos.html), [modelo arousal/valence](https://replicate.com/mtg/music-arousal-valence), [preferência musical (arXiv)](https://arxiv.org/pdf/2010.10276)

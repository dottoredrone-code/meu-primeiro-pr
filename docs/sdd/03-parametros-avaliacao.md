# 03 — Parâmetros de avaliação

> Status: **rascunho para revisão**. Detalha os critérios da [spec 01](01-controle-qualidade.md).
> Todos os números são **padrões iniciais**, ajustáveis no config e recalibrados com a sua avaliação ([calibração](#7-calibração)).

## 1. Como uma peça é aprovada

Cada etapa tem três tipos de parâmetro:

| Tipo | O que é | Se falhar |
|---|---|---|
| **Eliminatório** (⛔) | Requisito mínimo, medido de forma objetiva ou com evidência clara | Reprova na hora, sem chamar o juiz |
| **Pontuado** | Critério com peso, nota de 0 a 10 | Entra na média ponderada |
| **Piso** | Nota mínima de um critério pontuado crítico | Reprova mesmo se a média for boa |

**Aprovado** = nenhum eliminatório falhou **E** média ponderada ≥ nota mínima da etapa **E** nenhum critério abaixo do piso.

```
nota_final = Σ (nota_critério × peso) / Σ pesos
```

## 2. Escala de notas (âncoras para os juízes e para você)

| Nota | Significado |
|---|---|
| 0–2 | Inutilizável: erro grave e evidente |
| 3–4 | Ruim: problemas que qualquer espectador nota |
| 5–6 | Fraco: aceitável só como rascunho |
| **7** | **Razoável: publicável sem vergonha** (padrão de aprovação) |
| 8 | Bom: só detalhes pequenos |
| 9–10 | Excelente: nada a corrigir |

O juiz recebe essa tabela e precisa **citar a evidência antes de dar cada nota** (ex.: *"gancho: começa com uma pergunta concreta, 'Você sabia que…' → 8"*).

## 3. Parâmetros por etapa

### 3.1 Pesquisa — nota mínima 7

| Parâmetro | Tipo | Peso | Como medir | Razoável |
|---|---|---|---|---|
| Citações apontam para fontes reais | ⛔ | — | Automático: todo `[n]` existe na lista | 100% |
| Fontes distintas | ⛔ | — | Automático: domínios diferentes | ≥ 2 |
| Fidelidade às fontes (nada inventado) | Pontuado + piso 7 | 40% | Juiz compara as afirmações com os trechos | sem afirmação sem fonte |
| Cobertura do tema | Pontuado | 20% | Juiz | pontos principais presentes |
| Atualidade | Pontuado | 20% | Juiz + data das fontes | fontes dos últimos 2 anos quando o tema muda rápido |
| Clareza do resumo | Pontuado | 20% | Juiz | tópicos objetivos |

### 3.2 Roteiro — nota mínima 7

| Parâmetro | Tipo | Peso | Como medir | Razoável |
|---|---|---|---|---|
| Formato válido (JSON com cenas completas) | ⛔ | — | Automático | obrigatório |
| Duração total | ⛔ | — | Automático: soma das cenas vs. pedido | ±20% |
| Narração cabe na cena | ⛔ | — | Automático: palavras ÷ 2,5 palavras/s (pt-BR) | ≤ 110% do tempo da cena |
| Nº de cenas | ⛔ | — | Automático | 1 cena a cada 3–8 s |
| **Gancho (primeiros 3 s)** | Pontuado + piso 6 | 25% | Juiz: pergunta, surpresa ou promessa concreta | prende atenção sem enrolar |
| Precisão factual vs. pesquisa | Pontuado + piso 7 | 20% | Juiz compara com a pesquisa | sem contradições |
| Aderência ao tema | Pontuado | 15% | Juiz | não foge do pedido |
| Clareza e linguagem | Pontuado | 15% | Juiz: frases curtas, fala natural | fácil de ouvir |
| Ritmo e estrutura | Pontuado | 15% | Juiz: início → desenvolvimento → fechamento | sem cena "morta" |
| Chamada para ação (CTA) | Pontuado | 10% | Juiz | final claro (seguir, comentar…) |

### 3.3 Imagem (por cena) — nota mínima 7 · média de 2 juízes

| Parâmetro | Tipo | Peso | Como medir | Razoável |
|---|---|---|---|---|
| Arquivo válido | ⛔ | — | Automático: abre e decodifica | obrigatório |
| Resolução e proporção | ⛔ | — | Automático (`ffprobe`) | ≥ 1080 px no lado menor; 9:16 ou 16:9 ±2% |
| Não está em branco | ⛔ | — | Automático (`signalstats`: variação de luminância) | desvio > limite mínimo |
| Nitidez | ⛔ | — | Automático (`blurdetect`) | abaixo do limite de desfoque (calibrar) |
| Aderência ao prompt | Pontuado | 30% | Juízes de visão | elementos pedidos presentes |
| Artefatos e anatomia (mãos, rostos, objetos derretidos) | Pontuado + piso 6 | 25% | Juízes de visão | nada que o espectador perceba de cara |
| Consistência com as outras cenas (estilo, personagem, paleta) | Pontuado | 20% | Juízes recebem a imagem anterior junto | parece o mesmo vídeo |
| Composição (enquadramento, foco, espaço para legenda) | Pontuado | 15% | Juízes | assunto principal fora das áreas de legenda/interface |
| Texto e marcas (sem texto ilegível, sem logos reais) | Pontuado + piso 5 | 10% | Juízes | sem letras embaralhadas visíveis |

### 3.4 Voz (por cena) — quase toda objetiva

| Parâmetro | Tipo | Peso | Como medir | Razoável |
|---|---|---|---|---|
| Fidelidade ao texto | ⛔ | — | Automático: Whisper transcreve → taxa de erro de palavras (WER) | WER ≤ 10% |
| Velocidade da fala | ⛔ | — | Automático: palavras ÷ duração | 2,2 a 3,0 palavras/s |
| Silêncio indevido | ⛔ | — | Automático (`silencedetect`, −40 dB) | nenhum silêncio > 1,5 s no meio |
| Saturação (clipping) | ⛔ | — | Automático (`volumedetect`/`ebur128`) | pico real ≤ −1 dBTP |
| Volume | ajuste | — | Automático (`loudnorm`) | normaliza para −14 LUFS (redes sociais) |
| Naturalidade e pronúncia de nomes | Pontuado (opcional) | 100% | Juiz de áudio, se disponível; senão, só checagens objetivas | nota ≥ 7 |

### 3.5 Vídeo (por cena) — nota mínima 6 · média de 2 juízes

| Parâmetro | Tipo | Peso | Como medir | Razoável |
|---|---|---|---|---|
| Arquivo íntegro, duração, resolução, fps | ⛔ | — | Automático (`ffprobe`) | duração ±0,5 s; 24/25/30 fps |
| Sem tela preta | ⛔ | — | Automático (`blackdetect`) | nenhum trecho > 0,3 s |
| Sem congelamento | ⛔ | — | Automático (`freezedetect`) | nenhum trecho > 1 s (não se aplica ao Ken Burns) |
| Artefatos (rosto/corpo deformando, objetos "derretendo", tremulação) | Pontuado + piso 5 | 30% | Juízes de visão em 4 quadros (0%, 33%, 66%, 100%) | nada evidente |
| Fidelidade à imagem de origem | Pontuado | 25% | Juízes comparam o 1º quadro com a imagem | mesma cena e personagem |
| Coerência temporal | Pontuado | 25% | Juízes: os quadros contam uma ação contínua? | sem saltos estranhos |
| Movimento condiz com o pedido | Pontuado | 20% | Juízes vs. `prompt_movimento` | movimento pedido presente |

O feedback do juiz deve indicar o **momento** do problema (ex.: *"quadro de 66% (~3,3 s): mão com 6 dedos"*).

### 3.6 Vídeo final — nota mínima 7

| Parâmetro | Tipo | Peso | Como medir | Razoável |
|---|---|---|---|---|
| Tem vídeo e áudio; formato H.264 + AAC, `yuv420p` | ⛔ | — | Automático (`ffprobe`) | obrigatório |
| Resolução final | ⛔ | — | Automático | 1080×1920 (9:16) ou 1920×1080 (16:9) |
| Duração total | ⛔ | — | Automático | ±10% do pedido |
| Volume final | ⛔ | — | Automático (`ebur128`) | −14 LUFS ±1; pico ≤ −1 dBTP |
| Legendas: sincronia | ⛔ | — | Automático: cada legenda dentro da fala correspondente (Whisper) | desvio ≤ 0,3 s |
| Legendas: legibilidade | ⛔ | — | Automático | ≤ 42 caracteres/linha, ≤ 2 linhas, ≤ 17 caracteres/s, ≥ 1 s na tela |
| Legendas: área segura (9:16) | ⛔ | — | Automático pela posição | fora dos 20% de baixo e 10% de cima (interface das redes) |
| Gancho visual nos 3 primeiros s | Pontuado | 30% | Juízes nos quadros iniciais | imagem forte logo no início |
| Fluidez das transições | Pontuado | 25% | Juízes + `scdet` (cortes muito bruscos ou muito frequentes) | sem cortes estranhos |
| Coesão geral (parece um vídeo só) | Pontuado | 25% | Juízes em quadros de todas as cenas | estilo consistente |
| Música (se houver) não cobre a voz | Pontuado | 20% | Automático: música ≥ 12 dB abaixo da voz | voz sempre clara |
| **Sua aprovação** | Humano (opcional) | — | Nota de 1 a 5 no app | ≥ 4 |

## 4. Protocolo do juiz de IA

1. **Nunca é o mesmo provedor** que gerou a peça.
2. **Dois juízes** de provedores diferentes para imagem, vídeo e vídeo final; um juiz basta para texto.
3. **Divergência > 2 pontos** entre os juízes em um critério → chama um terceiro juiz; se não houver, marca `revisar_manual`.
4. Temperatura baixa (respostas consistentes) e resposta **obrigatória em JSON**:
   ```json
   {
     "criterios": {"gancho": {"evidencia": "...", "nota": 8}},
     "problemas": [{"momento": "3.3s", "descricao": "mão com 6 dedos", "gravidade": "alta"}],
     "correcao_sugerida": "regerar a cena com as mãos fora do quadro"
   }
   ```
5. A **média ponderada é calculada pelo código**, não pelo juiz, para evitar conta errada ou nota "arredondada para cima".
6. O prompt manda **ignorar qualquer instrução escrita dentro da imagem ou do texto avaliado** (proteção contra juiz enganado).
7. JSON inválido → tenta o próximo juiz; nenhum juiz disponível → vale só o automático e a peça é marcada `sem_juiz`.

## 5. Como o feedback volta no loop

Só os critérios **reprovados ou abaixo do piso** voltam para o gerador, em ordem de gravidade:

> A tentativa anterior foi reprovada (nota 6,1 / mínimo 7). Corrija:
> 1. [eliminatório] narração da cena 2 tem 19 palavras para 5 s (máx. 13).
> 2. [gancho 5/10] começa com contexto histórico; comece com um fato surpreendente.
> Mantenha o que estava bom: aderência ao tema (9), clareza (8).

Dizer **o que manter** evita que a correção estrague o que já estava bom.

## 6. Configuração (exemplo)

```toml
[avaliacao.roteiro]
nota_minima = 7
juizes = ["claude_haiku", "gemini_flash", "openai_mini"]
num_juizes = 1
pesos = { gancho = 25, precisao = 20, aderencia = 15, clareza = 15, ritmo = 15, cta = 10 }
pisos = { gancho = 6, precisao = 7 }
palavras_por_segundo = 2.5
tolerancia_duracao = 0.20

[avaliacao.imagem]
nota_minima = 7
juizes = ["gemini_flash", "claude_haiku", "openai_mini"]
num_juizes = 2
divergencia_maxima = 2
pesos = { aderencia = 30, artefatos = 25, consistencia = 20, composicao = 15, texto = 10 }
pisos = { artefatos = 6, texto = 5 }
lado_minimo_px = 1080

[avaliacao.voz]
wer_maximo = 0.10
palavras_por_segundo = [2.2, 3.0]
silencio_maximo_s = 1.5
lufs_alvo = -14
pico_maximo_dbtp = -1
```

## 7. Calibração

1. Nos **primeiros 20 vídeos**, você dá nota (mesma escala de 0 a 10) a uma amostra de peças: roteiros, imagens e cenas.
2. O sistema compara as suas notas com as dos juízes:
   - juízes **mais generosos** que você → sobe a `nota_minima`;
   - juízes **mais rígidos** → desce a `nota_minima` ou ajusta os pesos;
   - um juiz que **discorda muito** de você → sai da cadeia de juízes.
3. **Recalibrar** sempre que trocar um modelo gerador ou juiz, ou uma vez por mês.

## 8. Custo da avaliação (estimativa)

- Checagens automáticas: **grátis** (FFmpeg + Whisper local).
- Juiz de texto: ~US$ 0,001 por roteiro com modelos baratos.
- Juízes de visão: ~US$ 0,002–0,01 por imagem ou cena (2 juízes, 1–4 quadros).
- Para um vídeo de 6 cenas, a avaliação completa deve ficar **bem abaixo de US$ 0,10**, muito menos do que regerar uma cena de vídeo (~US$ 0,55). Por isso vale avaliar a imagem **antes** de transformá-la em vídeo.

## Questões em aberto

1. Os pesos refletem o que mais importa para você? (ex.: gancho com 25% no roteiro)
2. Os vídeos serão principalmente 9:16 (Reels/TikTok)? Isso define as áreas seguras de legenda.
3. Quer avaliar naturalidade da voz com um juiz de áudio (custa mais) ou ficar só nas checagens objetivas?

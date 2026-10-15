# 01 — Spec: Controle de qualidade com loop de correção

> Status: **rascunho para revisão** (não implementado).
> Depende de: [00-descoberta](00-descoberta.md). Parâmetros detalhados em [03-parametros-avaliacao](03-parametros-avaliacao.md). Relaciona-se com o roteador de fallback (`estudio_ia/roteador.py`).

## Objetivo

Nenhum resultado (roteiro, imagem, voz, vídeo) segue no fluxo sem passar por uma verificação.
Se não atingir o nível **razoável de aceitação**, é refeito com o feedback da verificação, em loop,
até ser aprovado ou até o limite de tentativas ou de custo.

## Princípios

1. **Quem verifica ≠ quem gerou.** Se o DeepSeek escreveu o roteiro, quem avalia é outro modelo (ex.: Claude Haiku ou Gemini Flash). Isso evita viés de confirmação.
2. **Primeiro o barato, depois o caro.** As checagens automáticas (grátis e determinísticas) rodam antes do juiz de IA. Se a checagem automática reprovar, o juiz nem é chamado.
3. **O loop refaz só a peça que falhou** (ex.: a imagem da cena 3), nunca o vídeo inteiro.
4. **O loop nunca é infinito.** Há limite de tentativas e de custo. Ao estourar, o sistema fica com a **melhor tentativa** e a marca para revisão humana, sem travar o fluxo.
5. **"Razoável" é configurável** por tarefa (nota mínima no `config/fallbacks.toml`), não fica fixo no código.

## Fluxo

```
gerar ──► checagem automática ──reprova──► feedback ──► regenerar (mesmo provedor)
              │ aprova                                     │ após N falhas → próximo provedor da cadeia
              ▼                                            │ estourou limite → melhor tentativa + "revisar"
          juiz de IA (outro modelo) ──reprova──► feedback ─┘
              │ aprova (nota ≥ mínima)
              ▼
          aceito → próxima etapa
```

O feedback do verificador entra no prompt da nova tentativa. Exemplo: *"a tentativa anterior foi
reprovada: narração da cena 2 longa demais para 5 s; gancho fraco. Corrija isso."*

## Critérios de aceitação por etapa

### Roteiro
| Tipo | Critério | Razoável |
|---|---|---|
| Automático | JSON válido, cenas com narração + prompt de imagem | obrigatório |
| Automático | Duração total vs. pedida | ±20% |
| Automático | Narração cabe no tempo da cena (~2,5 palavras/s em pt-BR) | ≤ 110% do tempo |
| Juiz IA | Gancho nos 3 primeiros segundos, clareza, aderência ao tema, coerência com a pesquisa | nota ≥ 7/10 |

### Pesquisa
| Tipo | Critério | Razoável |
|---|---|---|
| Automático | Citações `[n]` existem e apontam para fontes reais da busca | 100% |
| Automático | Mínimo de fontes distintas | ≥ 2 |
| Juiz IA | Resumo fiel às fontes (sem afirmações inventadas) | nota ≥ 7/10 |

### Imagem
| Tipo | Critério | Razoável |
|---|---|---|
| Automático | Arquivo válido, resolução e proporção (9:16 ou 16:9) corretas | obrigatório |
| Automático | Não está em branco nem corrompida (variação de pixels) | obrigatório |
| Juiz IA (visão) | Aderência ao prompt, sem deformações (mãos, rostos), sem texto ilegível, estilo consistente com as outras cenas | nota ≥ 7/10 |

### Voz
| Tipo | Critério | Razoável |
|---|---|---|
| Automático | Duração compatível com o texto | ±25% |
| Automático | Sem silêncio longo nem clipping (FFmpeg `silencedetect`/`volumedetect`) | sem silêncio > 1,5 s |
| Automático | **Transcrição com Whisper comparada ao texto** (taxa de erro de palavras, WER) | WER ≤ 10% |

### Vídeo (cena)
| Tipo | Critério | Razoável |
|---|---|---|
| Automático | `ffprobe`: duração, resolução e fps corretos; arquivo íntegro | obrigatório |
| Automático | Sem congelamento (`freezedetect`) | sem trecho parado > 1 s (exceto Ken Burns) |
| Juiz IA (visão) | Amostra de 3–4 quadros: coerência com a imagem de origem, sem deformações | nota ≥ 6/10 |

### Vídeo final
| Tipo | Critério | Razoável |
|---|---|---|
| Automático | Tem áudio e vídeo; duração total ±10% da soma das cenas | obrigatório |
| Automático | Legendas sincronizadas (cada fala dentro da cena certa) | 100% |
| Humano (opcional) | Aprovação final antes de publicar | configurável |

## Limites do loop (padrões, configuráveis)

| Parâmetro | Padrão |
|---|---|
| Tentativas por provedor | 2 |
| Tentativas totais por peça | 4 (percorrendo a cadeia de fallback) |
| Custo máximo por vídeo | definido pelo usuário (ex.: US$ 1,00) |
| Ao estourar | usa a melhor nota e marca `revisar_manual` |

## Juiz de IA

- Usa **modelos baratos com visão**, com cadeia própria de fallback (ex.: Gemini Flash → Claude Haiku → GPT mini).
- O juiz é **sempre de outro provedor** que não o gerador daquela peça. O roteador remove o gerador da cadeia do juiz.
- Resposta obrigatória em JSON:
  `{"nota": 0-10, "criterios": {"nome": nota}, "problemas": [str], "correcao_sugerida": str}`
- Resposta inválida do juiz → tenta o próximo juiz; se nenhum responder, vale só a checagem automática e a peça é marcada `sem_juiz`.

### Ajustes pela pesquisa da comunidade ([02](02-referencias-comunidade.md))

- Juízes com visão acertam bem os casos claramente ruins e erram mais nos detalhes. Por isso, para imagem e vídeo, usar a **média de 2 juízes** de provedores diferentes, e dar prioridade às checagens objetivas (WER, ffprobe, proporção).
- Juízes podem ser enganados por texto embutido na imagem: o prompt do juiz deve mandar ignorar instruções que apareçam dentro da imagem.
- **Calibração:** nos primeiros ~20 vídeos, comparar a nota do juiz com a sua avaliação e ajustar `nota_minima`.
- Feedback com **marcação de tempo** ("aos 0:12 o rosto deforma") e cada tentativa salva como versão (padrão do Agentic Video Editor).

## Exemplo de configuração

```toml
[qualidade.roteiro]
nota_minima = 7
juizes = ["claude_haiku", "gemini_flash", "openai_mini"]

[qualidade.imagem]
nota_minima = 7
juizes = ["gemini_flash", "claude_haiku"]

[qualidade.loop]
tentativas_por_provedor = 2
tentativas_totais = 4
custo_maximo_usd = 1.00
```

## Registro (aprendizado)

Cada projeto gera um `relatorio_qualidade.json` com tentativas, notas, problemas, provedor e custo
por peça. Com o tempo isso mostra **quais provedores mais reprovam**, para reordenar as cadeias com base
em dados.

## Critérios de pronto desta spec (para o Kanban)

- [ ] Checagens automáticas de roteiro, pesquisa, imagem, voz e vídeo, com testes
- [ ] Juiz de IA com cadeia própria, nunca o mesmo provedor do gerador (com teste)
- [ ] Loop com feedback no prompt, limite de tentativas e custo (com testes usando provedores falsos)
- [ ] Melhor tentativa + `revisar_manual` ao estourar o limite (com teste)
- [ ] Relatório de qualidade por projeto
- [ ] Limiares no `config/fallbacks.toml`

## Questões em aberto

1. A nota mínima padrão de 7/10 é o "razoável" que você quer, ou prefere mais rigor (8) ou menos (6)?
2. O vídeo final deve sempre esperar a sua aprovação antes de ser considerado pronto?
3. Qual o custo máximo aceitável por vídeo, contando as tentativas extras do loop?

## Mesmo princípio no desenvolvimento

O Kanban do projeto segue a mesma regra: cada cartão passa pela coluna **Em verificação**, revisado por
um agente diferente do que implementou, e volta para **Em andamento** com o feedback se for reprovado.

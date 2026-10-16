# 09 — Spec: Base de referência para os avaliadores

> Status: **rascunho para revisão**. Complementa a régua da [spec 03](03-parametros-avaliacao.md).
> Os canais listados são **candidatos**: precisam da escolha do Diego e da conferência de que continuam ativos e no padrão.

## Objetivo
Dar aos juízes de IA (e aos números da spec 03) uma **base concreta do que é um vídeo e um roteiro bons**,
tirada de canais reconhecidos, em vez de critérios só abstratos. A base serve para três coisas:
1. **Âncoras**: "nota 90 em gancho = como o vídeo X aos 0:03"; "nota 40 = como o exemplo ruim Y".
2. **Números-alvo por formato**: medir as referências (ritmo, cortes, duração, fala por segundo…) e usar as faixas medidas como metas, no lugar de números fixos.
3. **Calibração**: comparar a nota dos juízes com a sua nota nos mesmos vídeos de referência.

## Categorias (ligadas aos perfis por projeto, D11)

| Cat. | Formato | Para que tipo de conteúdo |
|---|---|---|
| A | **Curto informativo / curiosidade** (15–60 s, vertical) | Shorts, Reels, TikTok de fatos e curiosidades |
| B | **Explicativo / documental** (5–20 min, horizontal) | Vídeos longos de YouTube com pesquisa e narrativa |
| C | **Reflexão / relacionamentos / valores** (curto ou longo) | Conteúdo emocional, família, comportamento |
| D | **Produto / oferta** (15–45 s) | Divulgação de produtos, afiliados, lojas |
| E | **Educação / aula** (3–15 min) | Ensino de habilidades, tutoriais |
| F | **Institucional / B2B** (30–90 s) | Apresentação de serviços e propostas |

## Canais candidatos

| Cat. | Referências internacionais | Referências em português | Por que servem de régua |
|---|---|---|---|
| A | Zack D. Films; TED-Ed (cortes curtos) | Manual do Mundo; Ciência Todo Dia | Gancho imediato, um fato por vídeo, visual que explica sozinho |
| B | Kurzgesagt; Johnny Harris; Vox; Veritasium | Nerdologia; Meteoro Brasil | Roteiro com pergunta central, pesquisa com fontes, narração que dita o ritmo da animação |
| C | The School of Life; BBC Ideas | **Indicação do Diego** | Narrativa emocional sem apelação, ritmo calmo, mensagem clara |
| D | Apple (anúncios curtos); Marques Brownlee (MKBHD) | **Indicação do Diego** | Produto como protagonista, benefício antes da especificação, CTA claro |
| E | Khan Academy; Ali Abdaal | Me Salva! | Clareza didática, estrutura em passos, recapitulação |
| F | **Indicação do Diego** | **Indicação do Diego** | Credibilidade, objetividade, prova social |

**Exemplos negativos** (para ensinar o que reprovar): 5 a 10 vídeos típicos de "fábrica de conteúdo com IA",
com voz robótica, imagens deformadas, gancho genérico ("Você não vai acreditar…"), fatos errados e legenda
ilegível. Escolhidos por você ou pelo juiz e marcados como "referência negativa".

## Como escolher os vídeos de referência
- **5 positivos + 2 negativos por categoria** no início (~40 vídeos no total).
- Publicados nos **últimos 2 anos**, de preferência em pt-BR, com bom engajamento (comentários e visualizações altos em relação ao tamanho do canal).
- No **formato** da categoria (não usar vídeo longo como régua de Short).
- **Você aprova cada vídeo** antes de entrar na base.

## O que medir em cada referência

### Vídeo (medido com FFmpeg e Whisper, sem custo)
| Parâmetro | Como medir |
|---|---|
| Duração total | `ffprobe` |
| Tempo até o primeiro corte e duração média de plano | `scdet` (detecção de cortes) |
| Cortes por minuto | `scdet` |
| Fala por segundo e pausas | Whisper (palavras com marcação de tempo) |
| Volume e relação voz/música | `ebur128` |
| Legenda: presença, linhas, caracteres por linha, posição | Leitura de quadros (juiz de visão) |
| Texto na tela nos 3 primeiros segundos | Juiz de visão |

### Roteiro (transcrição analisada por um juiz de texto)
| Parâmetro | O que observar |
|---|---|
| **Tipo de gancho** | pergunta concreta, fato surpreendente, promessa de resultado, ação já em andamento, contraste/contradição |
| Momento da promessa | quando o vídeo diz o que você vai ganhar assistindo |
| **Laços abertos** | perguntas abertas que seguram a atenção e são respondidas depois |
| Ritmo de virada | conexões do tipo "mas… então…" em vez de "e depois… e depois…" |
| Densidade | ideias por minuto; uma ideia central por vídeo curto |
| Fontes | se cita de onde vêm os fatos (categoria B e E) |
| Fechamento e CTA | tipo e momento da chamada para ação |

### Resultado: um "perfil de referência" por categoria
Para cada parâmetro numérico, guardar a **faixa típica** das referências positivas (do 25º ao 75º percentil).
Exemplo do formato (números ilustrativos, a serem medidos):

```toml
[referencia.curto_informativo]
duracao_s = [20, 45]
primeiro_corte_s = [0.5, 2.0]
cortes_por_minuto = [18, 40]
palavras_por_segundo = [2.4, 3.1]
gancho_tipos_aceitos = ["fato_surpreendente", "pergunta_concreta", "acao_em_andamento"]
```

Esses perfis **substituem os números fixos da spec 03** quando estiverem medidos. Até lá, valem os padrões da spec 03.

## Como os juízes usam a base
1. O prompt do juiz recebe, para cada critério, **descrições textuais das âncoras** ("nota 90: gancho como em [ref A3], fato surpreendente com número concreto no 1º segundo"; "nota 40: como [ref negativa A-N2], frase genérica sem informação"). Não é preciso enviar os vídeos ao juiz a cada avaliação, o que mantém o custo baixo.
2. Checagens numéricas comparam a peça com o **perfil da categoria** (ex.: cortes por minuto fora da faixa = alerta).
3. **Calibração**: você e os juízes dão nota às mesmas referências; se o juiz diverge muito de você, ajustam-se as âncoras ou troca-se o juiz (spec 03, seção 7).

## Direitos e ética
- A base é **só para análise interna**: guardar link, métricas, marcações de tempo e trechos curtos de transcrição. **Não** baixar vídeos para reutilizar imagens, áudio ou texto.
- **Inspiração, não cópia**: um checador compara cada roteiro gerado com as transcrições de referência e reprova se a semelhança passar de um limite (ex.: frases idênticas ou estrutura copiada).
- Respeitar os termos de uso das plataformas na coleta de transcrições.

## Referências externas de mercado (só direção, não meta)
Blogs de mercado de 2026 citam, para Shorts: manter cerca de **80% do público nos 3 primeiros segundos**, retenção média
em torno de **70%**, e a faixa de **11 a 30 segundos** com melhores resultados. São números de terceiros, sem dado oficial
do YouTube; a meta real virá dos perfis de referência e, depois, dos **dados dos seus próprios canais** (YouTube Studio).

## Ferramentas para montar a base
- Transcrições: skill `youtube-content` do Hermes (já existe), ou ferramenta equivalente.
- Medições: FFmpeg (`ffprobe`, `scdet`, `ebur128`) + Whisper.
- Nova tarefa no Studio: `analisar_referencia(url, categoria)` → métricas + análise de roteiro + rascunho de âncoras para você aprovar.

## Critérios de pronto (para o Kanban)
- [ ] Lista final de canais e ~40 vídeos aprovados pelo Diego
- [ ] Tarefa `analisar_referencia` com medições de vídeo e análise de roteiro (com testes)
- [ ] Perfil de referência por categoria gerado e revisado
- [ ] Âncoras textuais por critério incluídas nos prompts dos juízes
- [ ] Checador de semelhança com as referências (anti-cópia)
- [ ] Rodada de calibração: suas notas × notas dos juízes nas referências

## Questões em aberto
1. Quais canais você admira e quer como régua para as categorias C, D e F (e para cada projeto seu)?
2. Os formatos acima cobrem o que você precisa? Falta algum (ex.: podcast em vídeo, apresentação com avatar)?
3. Prefere começar só pela categoria A (vídeos curtos), que é a mais usada, e ampliar depois?

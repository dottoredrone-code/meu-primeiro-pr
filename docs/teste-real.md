# Teste real com chaves (no seu PC)

Este ambiente na nuvem não tem chaves nem acesso às APIs. O teste real roda no seu PC, onde as chaves já
existem. **Nunca cole chaves no chat nem em arquivos do repositório**: elas ficam só no `.env` (ignorado pelo Git).

## 1. Preparar
```bash
git clone https://github.com/dottoredrone-code/meu-primeiro-pr.git   # ou: git pull, se já tiver
cd meu-primeiro-pr
git checkout claude/multi-model-integration-app-g1697x
```
Crie `.env` na raiz (veja `docs/configurar-chaves.md`) com as chaves que você já tem:
`DEEPSEEK_API_KEY`, `TAVILY_API_KEY`, `GEMINI_API_KEY` (e, se tiver, `ANTHROPIC_API_KEY` + `CLAUDE_MODEL`,
`OPENAI_API_KEY`).

## 2. Rodar (na ordem)
```bash
python -m unittest discover -s tests                 # deve passar (os testes normais não gastam nada)
python -m torralles_studio status                    # quais provedores ficaram "pronto"
python -m torralles_studio pesquisa "benefícios do chá verde" -q
python -m torralles_studio roteiro "benefícios do chá verde" -d 30 -q
python -m torralles_studio avaliar-video exemplos/demo_torralles_studio_v2.mp4 --percepcao -c "vídeo demonstrativo do Torralles Studio"
python -m torralles_studio avaliar-video "https://www.youtube.com/watch?v=<um vídeo curto>"   # sem baixar
```

Teste real pago do juiz de vídeo dentro da suíte (uns US$ 0,05): defina `TORRALLES_TESTE_REAL=1` antes
(PowerShell: `$env:TORRALLES_TESTE_REAL="1"`; Linux/Mac: `export TORRALLES_TESTE_REAL=1`) e rode
`python -m unittest tests.test_juiz_video -v`.

Cada comando é uma linha só (funciona no PowerShell, no cmd e no terminal do Linux/Mac).
Se o juiz de vídeo não conseguir avaliar, ele mostra o motivo real (ex.: modelo inexistente, chave, bloqueio).

## 2a. Vozes (K18)
```bash
python -m torralles_studio testar-voz
```
Grava em `saidas/teste-voz/` a mesma frase (com lh, nh, r e rr) em cada voz pronta e mostra o erro de palavras.
Ouça os arquivos: a voz do Gemini (`gemini_voz`) deve falar "olha" e "vermelho" certinho. Se aparecer 404, o nome
do modelo TTS em `config/fallbacks.toml` precisa de ajuste (KR1).

## 2b. Vídeo completo (K32)
Precisa de uma voz: `pip install edge-tts` (grátis) ou chave da ElevenLabs/OpenAI.
```bash
python -m torralles_studio produzir "benefícios do chá verde" -d 30 --pesquisa
```
O vídeo sai em `saidas/beneficios-do-cha-verde/video_final.mp4`, com `relatorio.json` (custo, provedores, notas).
Se parar no meio, rode o mesmo comando: o que já ficou pronto é reaproveitado sem pagar de novo.
Para refazer do zero, apague a pasta do tema.

## 2c. Vídeos de referência (K12)
```bash
python -m torralles_studio analisar-referencia "https://www.youtube.com/shorts/<id>" -c A
```
Escolha 3 a 5 vídeos por canal da categoria A (`config/referencias.toml`). O Gemini assiste pelo link, sem baixar.
Cada análise vira um JSON em `dados/referencias/A/` (fora do Git): números, partes do roteiro, gancho, notas com
evidência e âncoras sugeridas. Guarda só o link e trechos curtos, nunca o vídeo ou a transcrição inteira.
Exemplo do que **não** fazer (vídeo de "fábrica de conteúdo"): acrescente `--negativo`. Reanalisar sem a marca mantém o que
estava; para desfazer, use `--positivo`.

Depois de pelo menos 3 vídeos positivos na categoria:
```bash
python -m torralles_studio perfil-referencia -c A --salvar
```
Mostra as faixas típicas (25º–75º percentil) e grava em `config/perfis_referencia.toml`. Confira os números e
commite o arquivo: a partir daí, o relatório do `produzir` avisa quando o vídeo sai da faixa da categoria do perfil.

## 2d. Calibração: suas notas × juiz (K14)
Assista a cada vídeo analisado e dê sua nota de 0 a 10 (pode dar só alguns critérios):
```bash
python -m torralles_studio nota-referencia "https://www.youtube.com/shorts/<id>" -c A --gancho 8 --fluxo 7 --valor 6 --tendencia 9
python -m torralles_studio calibrar -c A
```
Com 3 vídeos ou mais, mostra se o juiz é mais generoso, mais rígido ou discorda de você, e o que ajustar. A nota
mínima recomendada já sai na escala do config (0 a 100). Para
ajustar as âncoras, escreva-as em `config/ancoras.toml` (parta das "ancoras_sugeridas" dos JSON), rode o
`analisar-referencia` de novo nos mesmos vídeos (suas notas são mantidas) e o `calibrar` outra vez.

## 2e. Benchmark prático (K31)
```bash
python -m torralles_studio benchmark briefings
python -m torralles_studio benchmark produzir
```
O primeiro mostra os 3 briefings e onde salvar os vídeos; o segundo faz os 3 vídeos do Studio (cada um com o
próprio teto de US$ 1,50; se parar, rode de novo: o custo e o tempo se somam e cada retomada conta como
intervenção; briefing que já tem vídeo do Studio é pulado; `--refazer` faz de novo do zero e paga de novo). Gere os mesmos 3 vídeos nas outras ferramentas (planos
grátis) e salve como `dados/benchmark/A/capcut.mp4`, `dados/benchmark/A/invideo.mp4`… Para cada um, anote:
```bash
python -m torralles_studio benchmark dados A capcut --tempo-min 15 --custo 0 --intervencoes 4 --tentativas 2 --nota 7 --voz 6 --legenda 8 --obs "travou uma vez"
```
Faça o mesmo para o Studio (`torralles-studio`; tempo, custo e tentativas já vêm anotados: só as suas notas).
No fim:
```bash
python -m torralles_studio benchmark avaliar --doc
```
Passa todos pela mesma régua e grava o comparativo em `dados/benchmark/relatorio.md` e em
`docs/sdd/04b-benchmark-pratico.md` (revise e commite). O juiz custa ~US$ 0,03–0,06 por vídeo; vídeo já
julgado que não mudou não paga de novo (`--refazer` força). Os vídeos do Google (Flow/Veo) e o do Studio, se usou
Gemini, são julgados pelo Gemini, da mesma família: suas notas servem para conferir esse viés.

## 3. O que anotar (para ajustar o config)
| O que | Onde aparece | O que fazer |
|---|---|---|
| Modelo não existe (HTTP 404 / "model not found") | mensagem do provedor | corrigir o nome em `config/fallbacks.toml` (KR1) |
| Provedor pulado por chave | `status` | conferir o nome da variável no `.env` |
| Nota, motivo e custo | 1ª linha de `pesquisa -q` / `roteiro -q` | conferir se a nota faz sentido |
| Custo real | painel de cada serviço | comparar com `custo_usd` do config e ajustar |
| JSON do juiz de vídeo | saída do `avaliar-video` | nota na régua 0–100 e problemas com o momento (ex.: "aos 3.3s") |

Os resultados podem ser colados no chat **sem** chaves (as mensagens de erro já saem mascaradas).

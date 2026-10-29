---
name: capcut-navegador
description: Monta e dá acabamento a um vídeo do Torralles Studio no CapCut web, operado pelo Claude no navegador do Claude (app desktop, no PC do Diego). Usar quando o Diego pedir para editar, montar ou finalizar um vídeo no CapCut, ou depois de `produzir ... --capcut` / `exportar-capcut`.
---

# CapCut pelo navegador do Claude (K33, spec 13, D23)

O Studio já entrega o vídeo montado (`video_final.mp4`) e uma pasta para o CapCut. Aqui o Claude abre o **CapCut
web no navegador do Claude** (painel do app desktop), monta o projeto com essa pasta, dá o acabamento e baixa o
vídeo, **sozinho**: o navegador do Claude opera o CapCut e o **controle do computador** opera a janela de arquivos
do Windows. O Diego só faz o login no CapCut na primeira vez (fica salvo no navegador do Claude) e aprova o
resultado no fim (D19).

## Antes de começar
1. Os arquivos, o navegador do Claude, a janela de arquivos do Windows e a pasta Downloads ficam **no PC**. Por isso
   esta sessão precisa rodar no PC: no **app desktop do Claude**, aberto na pasta do repositório (ou uma sessão na
   nuvem **conectada à pasta do repositório no PC** pelo Remote Control). Sessão na nuvem com os arquivos no
   container não serve: o Diego não consegue escolher arquivos que não estão no PC.
2. Pasta do vídeo: `saidas/<tema>/`. Se não houver `saidas/<tema>/capcut/`, rode
   `python -m torralles_studio exportar-capcut saidas/<tema>`.
3. Leia `capcut/linha_do_tempo.json` (ordem, início e duração de cada cena, clima, narração, texto na tela, título,
   CTA, créditos, duração total), `capcut/LEIA-ME.txt` e `saidas/<tema>/relatorio.json`. Pergunte ao Diego se ele
   quer algum acabamento especial; sem pedido, use o padrão da seção "Acabamento".
4. Carregue as ferramentas do navegador do Claude de uma vez: ToolSearch com o prefixo completo
   (`mcp__Claude_Browser__` no app desktop; `mcp__remote-devices__Claude_Browser__` numa sessão conectada ao PC) e
   `max_results: 64`. Se só houver `enable__mcp__remote-devices__Claude_Browser`, chame-a antes. Siga a skill
   `built-in-browser`.
5. Carregue o **controle do computador** (ToolSearch `{ query: "computer", max_results: 60 }`; se só houver
   `enable__mcp__remote-devices__computer`, chame-a antes) e siga a skill `computer-use`. Peça acesso **só** ao app
   que abre a janela de arquivos (o app desktop do Claude, dono do navegador do Claude); nada de Explorer, outros
   apps ou navegadores comuns. Se o controle do computador não estiver disponível (desligado em Configurações →
   Este computador → Controle do computador) ou o Diego negar, siga com ele escolhendo os arquivos (passo 3, plano B).

## Regras que não podem ser quebradas
- **Controle do computador só para a janela de arquivos** (abrir e salvar) dos arquivos de `saidas\<tema>\`.
  Nunca para outra coisa: o CapCut é operado pelo navegador do Claude, os comandos pelo terminal da sessão.
- **Conta do Diego:** ele faz o login no CapCut. Nunca digite senha, nunca saia da conta, nunca aceite termos novos,
  assine plano, pague, publique ou compartilhe nada pelo CapCut. Precisou de algo assim: pare e peça ao Diego.
- **Licenças (D2, D18):** use só a mídia da pasta exportada. **Não** use músicas, sons, vídeos de banco, figurinhas,
  modelos (templates) nem fontes da biblioteca do CapCut: a licença vale só dentro dele e o uso comercial não é
  garantido. Pode usar recursos de edição: transições, filtros, efeitos de imagem, animação de texto e ajustes.
- **Nada pago:** item com coroa, "Pro" ou cadeado não entra (exportaria com marca d'água ou cobraria).
- **Leia antes de clicar:** os nomes dos botões do CapCut mudam. Use `get_page_text`, `find` e `read_page` para achar
  o botão certo; `computer` com a ação "screenshot" só quando a posição na tela importa (linha do tempo). Diga no
  chat o que fez, porque o Diego pode não estar olhando o painel.
- **Não invente:** se a tela não for a esperada, descreva o que está vendo e pergunte.

## Passo a passo
1. Abra `https://www.capcut.com/` com `preview_start`. Se pedir login, chame `tabs_context` (o painel precisa
   estar visível; se estiver escondido, peça Ctrl+Shift+B) e peça ao Diego para entrar na conta dele.
2. Crie um projeto novo em branco **9:16 (1080×1920)** — ou a proporção que estiver em `linha_do_tempo.json`.
3. **Envie os arquivos**, uma pasta por vez. Descubra o caminho completo com `(Resolve-Path saidas\<tema>\capcut).Path`.
   Para cada pasta — (1) `...\capcut\01_clipes\`; (2) `...\capcut\02_audio\`; (3) `...\capcut\03_legendas\`, se o
   CapCut aceitar legenda — clique em enviar/upload no navegador do Claude e, na janela de arquivos do Windows, com
   o controle do computador: clique no campo "Nome", digite o caminho da pasta e Enter (a janela entra na pasta);
   clique na lista de arquivos, Ctrl+A e "Abrir". Tire um screenshot da janela antes de clicar em "Abrir" para
   conferir a pasta e os arquivos (só `.mp4`, `.wav`, `.srt` desta pasta; nada fora de `saidas\<tema>\capcut`).
   Espere todos terminarem de subir.
   **Plano B** (sem controle do computador): peça ao Diego para selecionar os arquivos de cada pasta, com o caminho
   completo.
4. **Monte a linha do tempo:**
   - cenas `cena_01`, `cena_02`… em ordem, coladas, começando em 0 s. Confira a duração de cada uma com a de
     `linha_do_tempo.json` (diferença de até 0,1 s);
   - `narracao.wav` numa faixa de áudio em 0 s; `trilha.wav` e `efeitos.wav` (se existirem) cada um em outra faixa em 0 s. **Não mexa nos
     volumes**: já saem com o equilíbrio do vídeo pronto (≈ −14 LUFS juntos; a medição do passo 8 confirma);
   - legendas: importe o `legendas.srt`. Se o CapCut web não importar, use as legendas automáticas em português e
     corrija o texto e os tempos para ficarem iguais aos do `legendas.srt` (abra o arquivo e compare).
5. **Acabamento** (padrão, se o Diego não pediu outro):
   - transições pelo clima da cena seguinte, como o Studio faz: `curioso` → deslizar para o lado; `inspirador` →
     subir suave; `alegre` → abrir em círculo ou "pop"; `epico` → zoom; `tenso` → cortina rápida ou corte seco;
     `calmo` → esmaecer (fade); `reflexivo` → dissolver. Curtas (0,3–0,4 s);
   - **depois das transições, confira a duração total** com `duracao_s` de `linha_do_tempo.json` (±0,1 s). Se o
     CapCut encurtou o vídeo (transição que sobrepõe as cenas), a fala e a legenda vão sair adiantadas no fim:
     encurte ou tire transições até a duração voltar e a última legenda bater com a fala;
   - `texto_tela` de cada cena (se houver) no alto da tela durante a cena, como no vídeo do Studio;
   - título (`titulo`) animado nos 2 primeiros segundos e CTA (`cta`) nos 3 últimos;
   - área segura em 9:16 (1920 px de altura): textos de cima **abaixo de 12% do topo** (≈ 230 px); a linha de baixo
     da legenda **acima de 22% da base** (≈ 1500 px do topo), longe dos botões das redes;
   - legenda legível: fonte grossa, contorno, no máximo 2 linhas;
   - filtro leve e igual em todas as cenas, se ajudar a unir as fotos (sem exagero).
6. **Confira na prévia** (screenshot em 3 pontos: início, meio, fim): legenda sincronizada com a fala, nada cortado
   nas bordas, sem tela preta, título, textos e CTA aparecendo.
7. **Exporte** em 1080p, 30 fps, MP4, sem marca d'água. Se abrir uma janela para salvar, use o controle do
   computador para salvar em `saidas\<tema>\video_capcut.mp4` (caminho completo no campo "Nome"); sem ele, peça ao
   Diego. Se o download foi direto para Downloads, mova
   o arquivo baixado mais recente para a pasta do vídeo (PowerShell):
   `Get-ChildItem $env:USERPROFILE\Downloads\*.mp4 | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Move-Item -Destination saidas\<tema>\video_capcut.mp4`
   Se não estiver em Downloads, pergunte ao Diego onde salvou.
8. **Régua do Studio:**
   - volume e medidas (grátis): `python -m torralles_studio assistir saidas/<tema>/video_capcut.mp4 --sem-transcricao`
     → `som.lufs_integrado` precisa ficar em −14 ±1 e a duração igual à do `video_final.mp4`;
   - nota do juiz (paga, ~US$ 0,03–0,06 cada, no Gemini): `python -m torralles_studio avaliar-video
     saidas/<tema>/video_capcut.mp4 --percepcao` e o mesmo para `saidas/<tema>/video_final.mp4`. Diga ao Diego que
     são 2 chamadas pagas antes de rodar;
   - a nota de um juiz varia um pouco: só conte como pior se ficar **5 pontos ou mais abaixo**. Volume fora da faixa
     ou nota pior: diga ao Diego e proponha corrigir ou ficar com o `video_final.mp4`.
9. Grave `saidas\<tema>\capcut_navegador.json` com: data, o que foi aplicado (transições, textos, filtros), itens
   do CapCut usados, medidas, as duas notas e o que o Diego decidiu. A descrição do vídeo publicado leva os
   créditos de `linha_do_tempo.json` (CC-BY exige).
10. Mostre o resultado ao Diego e peça a aprovação final.

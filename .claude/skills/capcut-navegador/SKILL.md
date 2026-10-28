---
name: capcut-navegador
description: Monta e dá acabamento a um vídeo do Torralles Studio no CapCut web, operado pelo Claude no navegador do Claude (app desktop, no PC do Diego). Usar quando o Diego pedir para editar, montar ou finalizar um vídeo no CapCut, ou depois de `produzir ... --capcut` / `exportar-capcut`.
---

# CapCut pelo navegador do Claude (K33, spec 13, D23)

O Studio já entrega o vídeo montado (`video_final.mp4`) e uma pasta para o CapCut. Aqui o Claude abre o **CapCut
web no navegador do Claude** (painel do app desktop), monta o projeto com essa pasta, dá o acabamento e baixa o
vídeo. O Diego aprova o resultado no fim (D19).

## Antes de começar
1. Esta sessão precisa rodar **no PC do Diego, no app desktop do Claude**, na pasta do repositório: é onde estão os
   arquivos e onde fica o navegador do Claude. Sessão na nuvem sem o PC conectado não faz este trabalho.
2. Pasta do vídeo: `saidas/<tema>/`. Se não houver `saidas/<tema>/capcut/`, rode
   `python -m torralles_studio exportar-capcut saidas/<tema>`.
3. Leia `capcut/linha_do_tempo.json` (ordem, início e duração de cada cena, clima, narração, título, CTA, créditos),
   `capcut/LEIA-ME.txt` e `saidas/<tema>/relatorio.json`. Pergunte ao Diego se ele quer algum acabamento especial;
   sem pedido, use o padrão da seção "Acabamento".
4. Carregue as ferramentas do navegador do Claude de uma vez (ToolSearch com o prefixo `Claude_Browser__`) e siga a
   skill `built-in-browser`.

## Regras que não podem ser quebradas
- **Conta do Diego:** ele faz o login no CapCut. Nunca digite senha, nunca saia da conta, nunca aceite termos novos,
  assine plano, pague, publique ou compartilhe nada pelo CapCut. Precisou de algo assim: pare e peça ao Diego.
- **Licenças (D2, D18):** use só a mídia da pasta exportada. **Não** use músicas, sons, vídeos de banco, figurinhas,
  modelos (templates) nem fontes da biblioteca do CapCut: a licença vale só dentro dele e o uso comercial não é
  garantido. Pode usar recursos de edição: transições, filtros, efeitos de imagem, animação de texto e ajustes.
- **Nada pago:** item com coroa, "Pro" ou cadeado não entra (exportaria com marca d'água ou cobraria).
- **Leia antes de clicar:** os nomes dos botões do CapCut mudam. Use `get_page_text`/`find`/`read_page` para achar o
  botão certo; screenshot só quando a posição na tela importa (linha do tempo). Diga no chat o que fez, porque o
  Diego pode não estar olhando o painel.
- **Não invente:** se a tela não for a esperada, descreva o que está vendo e pergunte.

## Passo a passo
1. Abra `https://www.capcut.com/` com `preview_start`. Se pedir login, chame `tabs_context` (o painel precisa
   estar visível; se estiver escondido, peça Ctrl+Shift+B) e peça ao Diego para entrar na conta dele.
2. Crie um projeto novo em branco **9:16 (1080×1920)** — ou a proporção que estiver em `linha_do_tempo.json`.
3. **Envie os arquivos:** clique em enviar/upload. Se abrir a janela de arquivos do Windows, o Claude não consegue
   escolher nela: peça ao Diego para selecionar, com o caminho completo, todos os arquivos de
   `saidas\<tema>\capcut\01_clipes\` e de `02_audio\` (e `03_legendas\legendas.srt`, se o CapCut aceitar legenda).
   Espere todos terminarem de subir.
4. **Monte a linha do tempo:**
   - cenas `cena_01`, `cena_02`… em ordem, coladas, começando em 0 s. Confira a duração de cada uma com a de
     `linha_do_tempo.json` (diferença de até 0,1 s);
   - `narracao.wav` numa faixa de áudio em 0 s; `trilha.wav` (se existir) em outra faixa em 0 s. **Não mexa nos
     volumes**: já estão como no vídeo pronto (−14 LUFS juntos);
   - legendas: importe o `legendas.srt`. Se o CapCut web não importar, use as legendas automáticas em português e
     corrija o texto para ficar igual à `narracao` de cada cena.
5. **Acabamento** (padrão, se o Diego não pediu outro):
   - transições pelo clima da cena seguinte, como o Studio faz: `curioso` → deslizar para o lado; `inspirador` →
     subir suave; `alegre` → abrir em círculo ou "pop"; `epico` → zoom; `tenso` → cortina rápida ou corte seco;
     `reflexivo`/`calmo` → dissolver. Até 0,5 s cada;
   - título (`titulo`) animado nos 2 primeiros segundos e CTA (`cta`) nos 3 últimos, dentro da área segura
     (longe das bordas de cima e de baixo, onde ficam os botões das redes);
   - legenda legível: fonte grossa, contorno, no máximo 2 linhas, no terço de baixo acima da área dos botões;
   - filtro leve e igual em todas as cenas, se ajudar a unir as fotos (sem exagero).
6. **Confira na prévia** (screenshot em 3 pontos: início, meio, fim): legenda sincronizada com a fala, nada cortado
   nas bordas, sem tela preta, título e CTA aparecendo.
7. **Exporte** em 1080p, 30 fps, MP4, sem marca d'água. Baixe e mova o arquivo da pasta Downloads para
   `saidas\<tema>\video_capcut.mp4` (no PowerShell: `Move-Item`).
8. **Régua do Studio:** rode
   `python -m torralles_studio avaliar-video saidas/<tema>/video_capcut.mp4 --percepcao` e compare com a nota do
   `video_final.mp4` (mesmo comando). Volume fora de −14 ±1 LUFS ou nota menor que a do vídeo do Studio: diga ao
   Diego e proponha corrigir ou ficar com o `video_final.mp4`.
9. Grave `saidas\<tema>\capcut_navegador.json` com: data, o que foi aplicado (transições, textos, filtros), itens
   do CapCut usados, as duas notas e o que o Diego decidiu. A descrição do vídeo publicado leva os créditos de
   `linha_do_tempo.json` (CC-BY exige).
10. Mostre o resultado ao Diego e peça a aprovação final.

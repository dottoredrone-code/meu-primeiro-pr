# 13 — CapCut operado pelo Claude no navegador do Claude (K33, D23)

> Pedido do Diego em 28/10/2026: "o CapCut deve ser operado pelo Claude no navegador do Claude". Escolha: o Claude
> **monta e dá acabamento** no CapCut web; a pasta exportada pelo Studio (K23) continua sendo a base.

## Por que assim
- O CapCut não tem API pública (D18). O caminho é a interface web, operada pelo Claude no **navegador do Claude**
  (painel do app desktop), que fica no PC do Diego, com o login dele e acesso aos arquivos de `saidas/`.
- A montagem do Studio continua sendo a referência medida (`video_final.mp4`, régua da spec 03 §3.6). O CapCut
  entra para o acabamento que o Studio não tem (transições, textos animados e filtros do editor) e para o Diego
  poder mexer depois no projeto.

## Como funciona
1. `produzir ... --capcut` (ou `exportar-capcut`) gera `saidas/<tema>/capcut/` com clipes cortados por cena,
   áudios no volume final, legenda `.srt` e `linha_do_tempo.json`, que agora leva também **clima e narração por
   cena, título, CTA e créditos**.
2. Numa sessão do Claude no app desktop, na pasta do repositório, o Diego pede o acabamento. O Claude segue a skill
   `.claude/skills/capcut-navegador/SKILL.md`: abre o CapCut web, o Diego faz o login, o Claude cria o projeto
   9:16, pede ao Diego para escolher os arquivos na janela do Windows (o navegador do Claude não opera essa janela),
   monta cenas, narração, trilha e legendas, aplica o acabamento, exporta e salva `saidas/<tema>/video_capcut.mp4`.
3. O vídeo do CapCut passa pela mesma régua (`avaliar-video --percepcao`) e é comparado com o `video_final.mp4`.
   O Diego aprova o final (D19). Fica um registro em `saidas/<tema>/capcut_navegador.json`.

## Regras
- Conta do Diego: login, termos, planos, pagamento, publicação e compartilhamento são sempre dele.
- Licenças (D2, D18): só a mídia da pasta exportada; nada de música, som, banco de vídeo, figurinha, modelo ou fonte
  da biblioteca do CapCut. Recursos de edição (transições, filtros, efeitos, animação de texto) podem.
- Nada marcado como pago ("Pro", coroa, cadeado).
- Volume não é mexido no CapCut (as faixas já saem a −14 LUFS juntas).

## Limites conhecidos
- A interface do CapCut web muda: a skill manda ler a página antes de clicar e perguntar quando a tela for outra.
- Arrastar na linha do tempo é a parte mais frágil; conferir durações com `linha_do_tempo.json` e prévia em 3 pontos.
- Só funciona com o app desktop aberto no PC (o navegador do Claude roda lá). Uma sessão na nuvem conectada ao PC
  também usa esse navegador, desde que o app esteja aberto.
- Escolher arquivos na janela do sistema é com o Diego.

## Critérios de pronto
- [x] `linha_do_tempo.json` com clima, narração, título, CTA e créditos (testado)
- [x] Skill do passo a passo com as regras de conta, licença e régua
- [ ] Teste real no PC: um vídeo montado no CapCut web pelo Claude, exportado, medido e aprovado pelo Diego

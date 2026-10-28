# 13 — CapCut operado pelo Claude no navegador do Claude (K33, D23)

> Pedido do Diego em 28/10/2026: "o CapCut deve ser operado pelo Claude no navegador do Claude". Escolha: o Claude
> **monta e dá acabamento** no CapCut web; a pasta exportada pelo Studio (K23) continua sendo a base.
> Depois ("você não consegue fazer automatizado?"): **automatizado com o controle do computador** do app desktop
> para a janela de arquivos do Windows; o Diego só faz o primeiro login e a aprovação final.

## Por que assim
- O CapCut não tem API pública (D18). O caminho é a interface web, operada pelo Claude no **navegador do Claude**
  (painel do app desktop), que fica no PC do Diego, com o login dele e acesso aos arquivos de `saidas/`.
- A montagem do Studio continua sendo a referência medida (`video_final.mp4`, régua da spec 03 §3.6). O CapCut
  entra para o acabamento que o Studio não tem (transições, textos animados e filtros do editor) e para o Diego
  poder mexer depois no projeto.

## Como funciona
1. `produzir ... --capcut` (ou `exportar-capcut`) gera `saidas/<tema>/capcut/` com clipes cortados por cena,
   áudios no volume final, legenda `.srt` e `linha_do_tempo.json`, que agora leva também **clima, narração e texto
   na tela por cena, título, CTA e créditos**.
2. Numa sessão do Claude no app desktop, na pasta do repositório, o Diego pede o acabamento. O Claude segue a skill
   `.claude/skills/capcut-navegador/SKILL.md`: abre o CapCut web, o Diego faz o login, o Claude cria o projeto
   9:16, escolhe os arquivos na janela do Windows com o controle do computador (o navegador do Claude não opera essa
   janela; sem o controle do computador, o Diego escolhe),
   monta cenas, narração, trilha e legendas, aplica o acabamento, exporta e salva `saidas/<tema>/video_capcut.mp4`.
3. O vídeo do CapCut passa pela mesma régua: medidas grátis (`assistir`: volume, duração) e nota do juiz
   (`avaliar-video --percepcao`, 2 chamadas pagas de ~US$ 0,03–0,06, avisadas ao Diego antes), comparada com a do
   `video_final.mp4` (só conta como pior com 5 pontos ou mais de diferença: a nota do juiz varia).
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
- Só funciona com a sessão rodando no PC: app desktop do Claude aberto na pasta do repositório, ou sessão na nuvem
  conectada à pasta do repositório no PC (Remote Control). Uma sessão na nuvem com os arquivos no container não
  serve: o navegador, a janela de arquivos e a pasta Downloads ficam no PC.
- Janela de arquivos (uma pasta por vez) e de salvar: controle do computador, que precisa estar ligado no app
  desktop (Configurações → Este computador → Controle do computador; vem desligado) e com acesso aprovado pelo
  Diego. Sem ele, o Diego escolhe os arquivos. O acesso é pedido só para essa janela.
- Primeiro login no CapCut é do Diego; depois fica salvo no navegador do Claude.
- **Transições do CapCut podem encurtar o vídeo** (sobrepõem as cenas) e adiantar a fala e a legenda no fim. Os
  clipes saem com a duração exata da cena; a skill confere a duração total depois das transições e encurta ou tira
  transições até bater. O teste real mostra qual é o comportamento do CapCut web.
- **Enviar para o CapCut põe a mídia na nuvem dele**, sob os termos de uso dele para conteúdo enviado (inclusive as
  fotos CC-BY de terceiros). O Diego sabe e decide; nada é publicado pelo CapCut.

## Critérios de pronto
- [x] `linha_do_tempo.json` com clima, narração, texto na tela, título, CTA e créditos (testado)
- [x] Skill do passo a passo com as regras de conta, licença e régua
- [ ] Teste real no PC: um vídeo montado no CapCut web pelo Claude, exportado, medido e aprovado pelo Diego

# Passagem de bastão — Torralles Studio (atualizada em 24/10/2026)

Leia este arquivo antes de continuar. O trabalho vinha numa sessão na nuvem e continua numa sessão local no PC
do Diego (`C:\Users\Oem\meu-primeiro-pr`, branch **`claude/multi-model-integration-app-g1697x`**).
Leia também `CLAUDE.md`, `KANBAN.md`, `docs/sdd/decisoes.md` e o fim de `docs/sdd/aprendizados.md`.

## Como falar com o Diego
- Português do Brasil, simples e direto; ele acompanha pelo celular e pelo PC.
- Escolhas sempre em perguntas com opções clicáveis, com a recomendada marcada.

## Regras que não podem ser quebradas
- Nunca mostrar, copiar ou repetir chaves do `.env` (nem no chat, nem em commits). O `.env` é ignorado pelo Git.
- D9: o Studio é independente dos outros projetos (nada jurídico em código, testes ou specs).
- D2: nada AGPL ou "não comercial" no produto. D18: cada mídia guarda fonte e licença. D20: teto US$ 1,50 por vídeo.
- Protocolo: plano → implementação → **verificação por um agente diferente** → correção. Um cartão por commit
  (`tipo(Kxx): descrição`); `python -m unittest discover -s tests` antes de cada commit; push só nessa branch;
  PR só se o Diego pedir. Rodapé dos commits:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` e
  `Claude-Session: https://claude.ai/code/session_01NAT84JQjJ937ynY1rQbLgm`.

## Onde paramos
- **K32 (primeiro vídeo real)** rodou no PC em 21/10 com `produzir`. Diego: "não ficou tão ruim, faltam
  animações e efeitos". Já feito depois: legenda palavra por palavra, título animado, transição pelo clima,
  movimento grátis com aceleração suave e efeitos por clima, foto gratuita licenciada quando a IA de imagem falha.
- **Chaves no `.env` do PC:** Gemini, Claude, DeepSeek (recarregado), Tavily. Sem OpenAI e sem fal.ai.
  Gemini não gera imagem (falta faturamento); Pollinations cobra (402) → imagens vêm de fotos gratuitas (Openverse).
- **Voz:** edge-tts (`pip install edge-tts`). A Piper de teste fala "lh" como "l" (não usar como voz principal).
- **Placa de vídeo:** Intel HD Graphics 4600 → IA de vídeo local inviável; Diego escolheu movimento grátis sem IA.

## Próximos passos
1. `git pull origin claude/multi-model-integration-app-g1697x`.
2. Refazer o vídeo do chá verde com os efeitos novos, sem gastar: apagar só `saidas\beneficios-do-cha-verde\cena_*.mp4`
   e `video_final.mp4` (manter `cena_*.png`, `voz_*.mp3`, `roteiro.json`, `fotos.json`) e rodar
   `python -m torralles_studio produzir "benefícios do chá verde" -d 30 --pesquisa`; abrir com
   `start saidas\beneficios-do-cha-verde\video_final.mp4` e perguntar ao Diego o que achou.
3. **K21 — trilha e efeitos sonoros gratuitos** (pedido do Diego): trilha por clima de fontes com licença comercial
   (acervo, Openverse áudio, Pixabay se houver chave; Freesound só com perfil `comercial = false`, D22), ligada ao
   `produzir` (`montar(trilha=...)` já deixa a música 12 LU abaixo da voz e abaixa sob a fala); opcional: sons curtos
   por cena (campo `sons` do roteiro, ≥ 15 LU abaixo da voz); licença de cada som em `creditos.txt`.
   Spec: `docs/sdd/12-pesquisa-qualidade-concorrentes.md` §3.
4. O K32 só fecha com a aprovação do Diego no vídeo completo.

---

## Histórico (passagem anterior, 15–16/10/2026)

Leia este arquivo antes de continuar. O trabalho até aqui foi feito numa sessão na nuvem e continua numa sessão local no PC do Diego.

## Onde está tudo
- Repositório: `dottoredrone-code/meu-primeiro-pr`, branch **`claude/multi-model-integration-app-g1697x`**
- Specs (SDD): `docs/sdd/00` a `07` + `decisoes.md` (D1–D16)
- Protótipo: pacote `torralles_studio/` (antes `estudio_ia`) (roteador de fallback, provedores, CLI, testes: `python -m unittest discover -s tests`)

## Estado
- Fase do protocolo: **planejamento** (nada novo deve ser construído antes do plano aprovado).
- Specs prontas para revisão: qualidade (01, 03), comunidade (02), benchmark (04), dados/segurança/memória (05), Hermes (06), Torralles Ops + Cérebro (07).
- **Propostas aguardando aprovação do Diego:** D13 (integração híbrida via MCP com Hermes/Ops), D14 (Studio começa no briefing da peça criativa, interface JSON), D15 (escala 0–100 + eliminatório "fatos travados"), D16 (aprendizados vão para o Cérebro).
- Correção pendente no código (cartão futuro): 7 modelos desatualizados no `config/fallbacks.toml` (ver 00-descoberta) e download sem lista de domínios (D8).

## Atualização 16/10/2026 (2)
- D13–D16, D18 aprovadas; D17 ajustada; D19–D20 novas. Pesquisa de qualidade na spec 12.
- **Kanban montado em `KANBAN.md`** (raiz). Próximo: Camada 0 (K01–K05), sem chaves.

## Atualização 16/10/2026
- Estudo do Ops **concluído** pela sessão local (só leitura) e incorporado ao `07` (seção "Confirmação pelo código").
- Proposta de contrato Ops → Studio em `08-contrato-ops-studio.md`.
- Falta: decisão do Diego sobre D13–D16 e as questões do `08`; depois, montar o Kanban.

## Próximo passo (original, já cumprido nos itens 1–3)
1. Estudar o Torralles Ops **com autorização direta do Diego nesta conversa**: `dashboard\` (Next 16, React 19, SQLite), `dashboard\src\lib\torralles-ops\` (diretor, 6 chefes, qualidade, prompt-formato, parser-ficha, hermes-client, repo, db), `dashboard\docs\superpowers\`, worktrees `torralles-ops-fase2-marketing` e `torralles-ops-redesign-visual`, e as partes do `CEREBRO_MESTRE.md` sobre Ops, Hermes e qualidade.
2. Atualizar `docs/sdd/07-estudo-torralles-ops-cerebro.md` com o que for confirmado ou corrigido (o estudo atual veio de trechos do Cérebro até 24/08/2026). Já se sabe: a worktree `torralles-ops-criacao-produto` não existe mais; `PADRAO_QUALIDADE_CRIATIVO.md` não foi encontrado.
3. Registrar o formato real do briefing de peça criativa e propor o **contrato JSON** Ops → Studio.
4. Com D13–D16 decididos, montar o **Kanban** (spec → plano → tarefa → implementação → verificação por agente diferente → correção).

## Regras
- **D9:** Torralles é a marca de todos os projetos; o Studio é independente. Não usar exemplos de outros projetos (nada jurídico) nas specs do Studio.
- Sem chaves, senhas ou dados pessoais em arquivos do repositório.
- Seguir o protocolo de execução (skill `protocolo-execucao-ia`) e registrar aprendizados no Cérebro ao fim da fase.

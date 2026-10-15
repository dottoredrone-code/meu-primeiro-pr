# Passagem de bastão — Torralles Studio (15/10/2026)

Leia este arquivo antes de continuar. O trabalho até aqui foi feito numa sessão na nuvem e continua numa sessão local no PC do Diego.

## Onde está tudo
- Repositório: `dottoredrone-code/meu-primeiro-pr`, branch **`claude/multi-model-integration-app-g1697x`**
- Specs (SDD): `docs/sdd/00` a `07` + `decisoes.md` (D1–D16)
- Protótipo: pacote `estudio_ia/` (roteador de fallback, provedores, CLI, testes: `python -m unittest discover -s tests`)

## Estado
- Fase do protocolo: **planejamento** (nada novo deve ser construído antes do plano aprovado).
- Specs prontas para revisão: qualidade (01, 03), comunidade (02), benchmark (04), dados/segurança/memória (05), Hermes (06), Torralles Ops + Cérebro (07).
- **Propostas aguardando aprovação do Diego:** D13 (integração híbrida via MCP com Hermes/Ops), D14 (Studio começa no briefing da peça criativa, interface JSON), D15 (escala 0–100 + eliminatório "fatos travados"), D16 (aprendizados vão para o Cérebro).
- Correção pendente no código (cartão futuro): 7 modelos desatualizados no `config/fallbacks.toml` (ver 00-descoberta) e download sem lista de domínios (D8).

## Próximo passo (nesta sessão local)
1. Estudar o Torralles Ops **com autorização direta do Diego nesta conversa**: `dashboard\` (Next 16, React 19, SQLite), `dashboard\src\lib\torralles-ops\` (diretor, 6 chefes, qualidade, prompt-formato, parser-ficha, hermes-client, repo, db), `dashboard\docs\superpowers\`, worktrees `torralles-ops-fase2-marketing` e `torralles-ops-redesign-visual`, e as partes do `CEREBRO_MESTRE.md` sobre Ops, Hermes e qualidade.
2. Atualizar `docs/sdd/07-estudo-torralles-ops-cerebro.md` com o que for confirmado ou corrigido (o estudo atual veio de trechos do Cérebro até 24/08/2026). Já se sabe: a worktree `torralles-ops-criacao-produto` não existe mais; `PADRAO_QUALIDADE_CRIATIVO.md` não foi encontrado.
3. Registrar o formato real do briefing de peça criativa e propor o **contrato JSON** Ops → Studio.
4. Com D13–D16 decididos, montar o **Kanban** (spec → plano → tarefa → implementação → verificação por agente diferente → correção).

## Regras
- **D9:** Torralles é a marca de todos os projetos; o Studio é independente. Não usar exemplos de outros projetos (nada jurídico) nas specs do Studio.
- Sem chaves, senhas ou dados pessoais em arquivos do repositório.
- Seguir o protocolo de execução (skill `protocolo-execucao-ia`) e registrar aprendizados no Cérebro ao fim da fase.

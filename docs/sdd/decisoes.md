# Registro de decisões — Torralles Studio

| # | Data | Decisão | Motivo / consequência |
|---|---|---|---|
| D1 | 15/10/2026 | O app se chama **Torralles Studio** | Renomear o pacote `estudio_ia` → `torralles_studio` vira cartão no Kanban |
| D2 | 15/10/2026 | **Uso próprio primeiro**, venda como possibilidade futura | Desde já: evitar código com licença restritiva (AGPL, ex.: OpenMontage), registrar a licença de cada serviço e dependência, e preferir provedores que permitam uso comercial. Login, cobrança e interface ficam para depois de validar. |
| D3 | 15/10/2026 | **Benchmark antes de construir** | Pesquisa de mesa em [04-benchmark](04-benchmark.md); teste prático com 3 briefings antes da versão completa |
| D4 | 15/10/2026 | Fallback por etapa + controle de qualidade com loop | Diferencial confirmado pelo benchmark: nenhum concorrente combina os dois |
| D5 | 15/10/2026 | Edição manual via **exportação para CapCut**, sem editor próprio | CapCut grátis já resolve; reconstruir editor não compensa |
| D6 | 15/10/2026 | Dados locais na fase 1: **SQLite + pastas**; PostgreSQL + nuvem só se for vender | Zero custo e instalação; esquema pensado para migrar ([05](05-dados-seguranca-memoria.md)) |
| D7 | 15/10/2026 | Memória do app em 3 níveis (perfil, histórico, aprendizados) com busca textual | Embeddings só se a busca textual não bastar |
| D8 | 15/10/2026 | Segurança "falha fechada": teto de custo para a execução; downloads só de domínios permitidos | Encontrado no código atual um download sem restrição de domínio → cartão |
| D9 | 15/10/2026 | **Torralles é a marca padrão de todos os projetos**; o Torralles Studio é um projeto independente | Nenhum exemplo, briefing, memória ou configuração deste projeto deve ser associado a outros projetos da marca |
| D10 | 15/10/2026 | Sem conteúdo confidencial | Remove a restrição de provedores por sigilo da spec 05 |
| D11 | 15/10/2026 | O Torralles Studio atenderá **todas as demandas de conteúdo** dos projetos da marca (atuais e futuros) | Precisa de **perfis por projeto/canal** (estilo, público, formato, voz, kit visual, memória separados), escolhidos a cada pedido. Os perfis não se misturam entre si (ver D9) |
| D12 | 15/10/2026 | Continuar planejando, com foco em análise, pesquisa, comparação e criatividade | Antes de construir: estudar o Torralles Ops (agentes criadores/agência) para reaproveitar, integrar ou trabalhar em conjunto |
| D13 | 15/10/2026 | **Proposta (aguardando aprovação)**: integração híbrida com o Hermes — motor do Studio como servidor MCP; Hermes/Torralles Ops orquestra | Evita refazer kanban, perfis, memória e gateway que o Hermes já tem ([06](06-estudo-hermes.md)) |
| D14 | 15/10/2026 | **Proposta**: o Studio começa onde o Torralles Ops termina (briefing da peça criativa), recebendo e devolvendo **JSON** | Lições do Ops: evitar parser de texto frágil e fatos inventados ([07](07-estudo-torralles-ops-cerebro.md)) |
| D15 | 15/10/2026 | **Proposta**: escala de notas 0–100 (igual ao Ops) e eliminatório "fatos travados" | Uma só régua no ecossistema |
| D16 | 15/10/2026 | **Proposta**: aprendizados do Studio vão para o Cérebro Centralizado, não para memória paralela | Fase 9 do protocolo; evita duas fontes da verdade |

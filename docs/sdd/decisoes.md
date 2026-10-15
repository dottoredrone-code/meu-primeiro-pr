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

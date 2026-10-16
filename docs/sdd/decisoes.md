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
| D13 | 15/10/2026 | ✅ **Aprovada 16/10**: integração híbrida com o Hermes — motor do Studio como servidor MCP; Hermes/Torralles Ops orquestra | Evita refazer kanban, perfis, memória e gateway que o Hermes já tem ([06](06-estudo-hermes.md)) |
| D14 | 15/10/2026 | ✅ **Aprovada 16/10**: o Studio começa onde o Torralles Ops termina (briefing da peça criativa), recebendo e devolvendo **JSON**, de forma **assíncrona** | Confirmado pelo código em 15/10: o Ops para no briefing em texto e a produção é manual. Contrato em [08](08-contrato-ops-studio.md) |
| D15 | 15/10/2026 | ✅ **Aprovada 16/10**: escala de notas 0–100 (igual ao Ops) e eliminatório "fatos travados" | Uma só régua no ecossistema |
| D16 | 15/10/2026 | ✅ **Aprovada 16/10**: aprendizados do Studio vão para o Cérebro Centralizado, não para memória paralela | Fase 9 do protocolo; evita duas fontes da verdade |
| D17 | 16/10/2026 | 🔄 **Ajustada 16/10**: a base de referência precisa ser **mais concreta e técnica**: primeiro pesquisar **como os concorrentes avaliam qualidade**, depois ancorar em **canais reconhecidos pela qualidade**, com métricas medidas, para reduzir a margem de erro | Pesquisa em andamento ([09](09-referencias-qualidade.md)) |
| D18 | 16/10/2026 | ✅ **Aprovada 16/10**: mídia em 3 camadas (acervo local → APIs gratuitas → geração por IA), com licença registrada por arquivo; CapCut só para acabamento manual | CapCut não tem API e a licença vale dentro dele ([11](11-banco-midia-gratuita.md)) |
| D19 | 16/10/2026 | **Trilhas e efeitos escolhidos pelo Studio** em fontes gratuitas, com critérios baseados em como os concorrentes escolhem; **o Diego aprova o vídeo completo** no fim | Aprovação humana final obrigatória (spec 03, vídeo final) |
| D20 | 16/10/2026 | **Teto de custo: US$ 1,50 por vídeo de ~30 s (modo misto)**, incluindo as tentativas do controle de qualidade | Kling só nas cenas principais; zoom nas demais; IA para som só quando faltar no acervo |
| D21 | 16/10/2026 | **Régua do vídeo final para o juiz que assiste com som (K06):** gancho 30, fluidez 20, coesão 20, áudio 20, sincronia 10; **1 juiz** por enquanto | Spec 03 (3.6) previa 30/25/25 + música 20 (medida automática) e 2 juízes; só o Gemini assiste vídeo com som pela API, então áudio e sincronia entram na régua do juiz. Volta a 2 juízes quando houver outro juiz de vídeo ou o juiz de quadros (nível 3) |
| D22 | 16/10/2026 | ✅ **Aprovada 16/10:** Freesound **só em projetos não monetizados** (perfil com `comercial = false`); nos demais, efeitos pelo acervo local e Openverse | A API do Freesound é grátis só para uso **não comercial**; aplicação comercial exige licença deles (canal monetizado conta como comercial). Padrão seguro: perfil sem o campo conta como comercial |

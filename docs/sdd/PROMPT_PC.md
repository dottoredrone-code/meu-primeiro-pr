Continue o Torralles Studio aqui no meu PC (Windows, PowerShell), na pasta C:\Users\Oem\meu-primeiro-pr, branch claude/multi-model-integration-app-g1697x. Uma sessão na nuvem trabalhou até 28/10/2026; você assume daqui.

1. Atualize e confira:
   - git pull origin claude/multi-model-integration-app-g1697x
   - python -m unittest discover -s tests   (deve passar; se algo falhar no Windows, me mostre e corrija)
2. Leia antes de agir: CLAUDE.md, KANBAN.md, docs/sdd/PASSAGEM.md, docs/sdd/decisoes.md (até D23), docs/sdd/aprendizados.md e docs/teste-real.md.
3. O que foi feito na nuvem desde a última passagem (tudo verificado por agente independente e já na branch):
   - KR1: preços e modelos revisados em 24/10 (config/fallbacks.toml, docs/sdd/revisao-modelos.md).
   - K12 analisar-referencia, K13 perfil-referencia, K14 nota-referencia + calibrar (régua medida com vídeos de referência).
   - K31 benchmark (briefings, produzir, dados, avaliar --doc).
   - K33 (em andamento): o CapCut é operado pelo Claude no navegador do Claude, pela skill .claude/skills/capcut-navegador/SKILL.md (decisão D23, spec docs/sdd/13-capcut-navegador.md). Precisa de sessão rodando no PC (esta). Controle do computador para a janela de arquivos do Windows: não apareceu nas Configurações do app 4.29.0; sem ele, eu escolho os arquivos quando você pedir.
4. Primeira tarefa: com o meu ok, cole docs/cerebro/2026-10-28-studio.md na seção do Torralles Studio do Cerebro_Centralizado\CEREBRO_MESTRE.md (editar só lá) e rode o script de sincronização do Cérebro.
5. Depois, siga os testes reais nesta ordem (passo a passo em docs/teste-real.md, seções 2a a 2f), me mostrando o resultado de cada um:
   a. testar-voz (ouvir a voz do Gemini: "olha", "vermelho"; se der 404, corrigir o nome do modelo TTS no config).
   b. Refazer o vídeo do chá verde com trilha e --capcut, como está na PASSAGEM, para eu aprovar o K32.
   c. K33: montar e finalizar esse vídeo no CapCut web pela skill capcut-navegador (eu faço o login no CapCut na primeira vez).
   d. Régua medida: analisar-referencia em 3 a 5 Shorts por canal da categoria A (config/referencias.toml), perfil-referencia -c A --salvar, minhas notas com nota-referencia e calibrar -c A.
   e. Benchmark: benchmark produzir; eu gero os 3 briefings nas outras ferramentas; benchmark dados; benchmark avaliar --doc.
   f. Opcional: servidor com o Ops e o Hermes; depois K29 (Ops) e K30 (Hermes), que dependem do repositório do Torralles Ops neste PC, só com a minha autorização.
6. Regras de trabalho:
   - Protocolo de cada cartão: plano → implementação → verificação por um agente diferente → correção → Pronto no KANBAN e aprendizados.
   - Quando eu precisar escolher, me dê opções clicáveis, com a recomendada marcada "(Recomendado)".
   - Fale comigo em português do Brasil, simples e direto; eu leio muitas vezes pelo celular.
   - Nunca me peça para colar chaves no chat e nunca as repita; chaves só no .env (fora do Git). Erros passam por mascarar().
   - Avise antes de qualquer coisa paga (teto de US$ 1,50 por vídeo, D20). Nada AGPL ou "não comercial" (D2); cada mídia com fonte e licença (D18).
   - O Studio é independente dos meus outros projetos (D9): nada de dados de outros projetos em código, testes ou specs.
   - Commits pequenos, um cartão por commit, "tipo(Kxx): descrição" em português; push só nesta branch; sem PR sem eu pedir.

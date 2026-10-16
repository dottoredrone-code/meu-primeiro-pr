# Aprendizados por camada (para exportar ao Cérebro — D16)

## Camada 0 — Fundação (16/10/2026)
- **Verificador independente encontrou o que os testes não pegaram:** o download seguia redirecionamentos
  antes de conferir o destino (requisição a endereço interno era feita, mesmo com a resposta recusada).
  Correção: conferir o destino *antes* de seguir. Lição: testes de segurança devem simular o servidor real,
  não só a resposta final.
- **Teste de contrato por família, não por nome exato:** bloquear `kling-video/v2.x` inteiro, não só uma variante.
- **Modelos e custos como dados** (config) facilitam a revisão mensal e a troca sem mexer no código.
- **Fontes não confirmadas** (`deepseek-v4-pro`, `gemini-3.6-flash`) ficaram marcadas; a cadeia de fallback
  protege se algum nome não existir. Confirmar no primeiro teste com chaves reais.
- Processo que funcionou: 1 commit por cartão → suíte de testes → verificador diferente → correções → Pronto.

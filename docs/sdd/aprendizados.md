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

## Camada 1 — Qualidade sem chaves: K07, K08, K10 (16/10/2026)
- **Eliminatório precisa errar pouco para os dois lados:** a 1ª versão do checador de fatos deixava passar
  preço sem símbolo ("39,90 reais") e link sem caminho, e reprovava frase comum ("R$ 49,90 até 31/10").
  Num loop de correção, falso positivo custa caro: refaz peça boa até o limite e gasta o orçamento.
  Lição: para cada regra, testar casos que devem reprovar **e** textos comuns de anúncio que devem passar.
- **Regras positivas vencem listas negativas:** "faixa só quando o 2º valor tem moeda ou fecha a frase"
  funcionou melhor que listar unidades (cm, dias, parcelas…), que nunca fica completa.
- **Família do juiz é a do modelo, não a do serviço:** OpenRouter rodando DeepSeek é DeepSeek. Agora há
  teste de contrato comparando o nome do modelo com a família.
- **Texto do modelo chega com tipos errados** ("5s", NaN, cena como texto): checagens automáticas não podem
  quebrar; devolvem o problema como reprovação.
- **Conteúdo avaliado não pode fechar a marca `<conteudo>`:** neutralizar as marcas antes de montar o prompt.
- Foram 2 rodadas de verificação independente até aprovar (K10 aprovado na 1ª, K07 na 2ª, K08 na 3ª correção).

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

## Camada 1 — Loop de correção: K09 (16/10/2026)
- **"Sem juiz" não é aprovação quando já houve tentativa julgada:** o teto de custo cortava o juiz na
  2ª tentativa e uma peça não avaliada saía como aprovada no lugar de uma já avaliada. Regra: sem juiz só
  vale na 1ª tentativa (só checagem automática + revisar); depois disso, encerra e escolhe a melhor julgada.
- **O relatório precisa da decisão final, não da última tentativa:** senão peças que estouraram o loop
  não aparecem como "revisar".
- **Erro de checagem não pode jogar fora o que já foi pago:** encerra com a melhor tentativa até ali.
- **Texto que volta do juiz também é entrada não confiável:** delimitar e trocar marcas por colchetes
  (remover numa passada deixa remontar `</feedback>` com fragmentos).
- Verificador encontrou 6 problemas na 1ª rodada que os 11 testes iniciais não pegavam; todos viraram testes.

## Camada 4 — Banco local: K24 (16/10/2026)
- **Cache precisa de porta de saída:** sem `usar_cache=False`, refazer uma peça rejeitada devolvia o mesmo
  resultado de graça e em silêncio. Toda peça refeita vai ao gerador; o juiz pode usar cache porque recebe
  o conteúdo (ou o hash do arquivo) no prompt.
- **A chave do cache é tudo o que muda o resultado:** modelo, parâmetros e o config do provedor (voz,
  tamanho, base_url). Fora: caminho de saída, chaves, timeout, custo.
- **Cache vale para a cadeia inteira:** consultar todos os provedores antes de pagar o primeiro disponível.
- **Custo pago nunca some:** até a tentativa cuja avaliação deu erro é gravada com o gasto.
- **Arquivos por tentativa:** cada tentativa grava o seu (`saida.tN`), a escolhida é copiada para a saída;
  senão "a melhor tentativa" aponta para o conteúdo da última.
- **Migrações:** listas de comandos (partir por ";" quebra textos) e erro claro se o banco for mais novo.
- 2 rodadas de verificação; os testes iniciais não pegavam o cache ligado no caminho de refazer.

## Camada 4 — Perfis por projeto: K26 (16/10/2026)
- **Isolamento se prova com testes de vazamento nos quatro caminhos:** prompt, arquivos do kit, ajustes de
  provedor (roteador próprio do perfil, sem mexer no original) e memória no banco. O cache não mistura porque
  o contexto do perfil e o config do provedor fazem parte da chave.
- **Perfil é dado do usuário, mas não pode furar regra do produto:** a 1ª versão deixava o perfil zerar o
  custo, trocar o modelo e subir o teto. Agora o perfil ajusta estilo (voz, tamanho), nunca modelo, custo,
  chaves ou endereços; o teto do perfil só pode ser menor que o do config.
- **Um arquivo com defeito não derruba os outros:** vai para `Perfis.erros` com o motivo em pt-BR.
- **Perfis ficam em `dados/perfis/` (fora do Git):** nenhum dado de projeto real entra no repositório (D9).
- 2 rodadas de verificação.

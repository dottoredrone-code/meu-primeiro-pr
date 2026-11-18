# 14 — Fila de serviços gratuitos de imagem e vídeo, com prompts por serviço (K34–K38, D24)

> Pedido do Diego em 13/11/2026: "uma ferramenta ou habilidade que faz prompt para vídeo e imagem, ou para animar ou
> alterar uma imagem ou vídeo, para usar apps, sistemas ou sites online com serviços gratuitos, com fallback para
> outros da fila quando um limite acaba".
> Escolhas do Diego: **APIs e sites** (os sites operados pelo Claude no navegador do Claude) e, na licença, **as duas
> regras, com opção para cada modalidade** (D24).

## Por que assim
- O roteador já faz fallback e põe em "descanso" quem devolve 429, mas o descanso dura **60 s e some quando o
  programa fecha**. Cota gratuita costuma ser **diária ou mensal**: o Studio precisa lembrar disso entre uma
  execução e outra, senão gasta tempo batendo em quem já acabou.
- Cada serviço entende o prompt de um jeito: frase natural ou etiquetas curtas, limite de tamanho, prompt negativo
  separado ou não, câmera escrita em palavras ou em parâmetro. Um prompt único rende menos em todos.
- Vários serviços gratuitos só existem como **site** (créditos diários, sem API). O caminho é o mesmo da D23: o Claude
  opera o site no navegador do Claude, com o login do Diego.

## Modalidades
A modalidade é o **nome da tarefa** em `[tarefas.*]`. É assim que o roteador sabe qual fila usar.

| Modalidade (tarefa) | Entra | Sai | Hoje no Studio |
|---|---|---|---|
| `imagem` | texto | imagem | cadeia `imagem` (Pollinations é o grátis) |
| `editar_imagem` | imagem + instrução | imagem | não tem |
| `animar` | imagem + movimento | vídeo curto | é a tarefa `video` de hoje (Kling/Wan pagos, Ken Burns grátis). O K34 a **renomeia** para `animar`, mantendo `video` como apelido até o fim do K37 |
| `video_texto` | texto | vídeo curto | não tem |
| `editar_video` | vídeo + instrução | vídeo | não tem (poucos grátis; pode ficar sem fila) |

## Peças

### A. Prompts por serviço (`prompts_midia.py`, K35)
1. Da cena do roteiro (`prompt_imagem`, movimento, clima, kit visual do perfil) sai um **prompt neutro** com campos:
   sujeito, ação, cenário, estilo, luz, câmera e movimento, proporção, o que evitar.
2. Cada serviço tem um **molde** em `config/prompts_midia.toml` (dados, não código): ordem dos campos, frase ou
   etiquetas, idioma (a maioria rende melhor em inglês), limite de caracteres, prompt negativo separado ou embutido,
   palavras de câmera (ex.: "slow push-in", "orbit left").
3. Sem modelo pago: o molde é preenchido por regra. Opcional: a cadeia `texto` (grátis primeiro) só reescreve em
   inglês natural quando a regra não bastar.
4. Comando: `python -m torralles_studio prompt-midia "ideia" -m animar [-s servico] [-p perfil]` mostra o prompt
   pronto de cada serviço da fila, para copiar à mão em qualquer app.

### B. Cotas que duram (`cotas` no banco, K34 ✅ 17/11/2026)
Config: `[provedores.X.cota]` com `conta`, `limite` (exige `renova`), `renova`, `padroes` e `creditos`
(veja o cabeçalho de `torralles_studio/cotas.py`).

- Nova migração em `MIGRACOES` cria a tabela `cotas`. A chave é **serviço + conta**, não a modalidade, porque os
  créditos são da conta. Campos: créditos gastos no período, limite em **créditos**, período e `renova_em`. Cada
  modalidade declara no config quantos créditos gasta (ex.: imagem 1, vídeo 10).
- **Relógio:** o descanso curto de hoje continua no `time.monotonic`. Já o `renova_em` usa um relógio de parede
  injetável (para os testes) e é **gravado em UTC**; na tela aparece no horário de São Paulo. Cada serviço declara
  como renova:
  - `renova = "00:00 UTC"` (horário fixo);
  - `"24h corridas"` (a partir do primeiro uso);
  - `"mensal:1"` (dia do mês).
- O roteador consulta a cota antes de tentar: **esgotado até `renova_em`** (aviso: "pollinations: cota do dia
  acabou, volta 18/11 às 21:00") e vai para o próximo da fila.
- **Cota esgotada × excesso por minuto:**
  - Cada serviço declara `cota_padroes`, os trechos de mensagem que significam "créditos acabaram". O `ErroProvedor`
    passa a levar também o texto e o `Retry-After`.
  - Só um padrão declarado, ou um `Retry-After` maior que 1 h, marca como esgotado até a renovação.
  - Na dúvida ("rate limit", 429 sem padrão), vale o descanso curto de hoje.
- **Contagem:** **cada chamada ao serviço** gasta crédito, inclusive as repetições do `_chamar` e as tentativas
  reprovadas pelo juiz. Um acerto do cache não gasta, e a cota é conferida **depois** do cache. Quando o limite está
  no config, o Studio para antes de levar o erro.
- Roteador sem banco (`cache=None`, como nos testes antigos): tudo funciona como hoje, sem cota que dura.
- Comando `python -m torralles_studio cotas` lista quanto falta e quando renova; `cotas --esgotar <serviço>` marca à
  mão, e a skill do navegador usa esse comando.

### C. Licença por modalidade (D24, K34)
- No perfil: `[licenca_por_modalidade]`, um valor por modalidade:
  - `"comercial"` (**padrão**): só entra serviço cujo plano gratuito libera uso comercial **e** não põe marca d'água;
  - `"como_freesound"`: serviços "só não comercial" entram **apenas** se o perfil tiver `comercial = false` (mesma
    regra da D22). Num perfil comercial eles continuam de fora, mesmo com essa opção.
- Cada serviço **gratuito novo** (K36/K37) declara no config:
  - `licenca`: `comercial`, `nao_comercial` ou `a_conferir`;
  - `marca_dagua`;
  - `familia` do modelo que gera (ex.: um site que usa Veo é da família `google`, então o Gemini não pode julgá-lo).

  `a_conferir` **nunca** entra na fila. Ele só sai desse estado depois que alguém lê os termos e anota a data e o
  link.
- Compatibilidade:
  - o `somente_nao_comercial = true` de hoje (Freesound) passa a ser lido como `licenca = "nao_comercial"`, com teste;
  - provedores pagos e o `ken_burns`, que não têm o campo, contam como `comercial`: os termos pagos já foram
    conferidos no KR1, e o Ken Burns é local;
  - a cadeia atual não muda.
- Toda mídia gerada guarda serviço, licença, data e prompt na biblioteca (D18). Os créditos do vídeo citam o serviço
  quando os termos pedem.

### D. Novos serviços de API gratuitos (K36)
- Candidatos (licença, cota e termos **a conferir** no cartão, um por um, antes de entrar no config):
  Cloudflare Workers AI (FLUX com cota diária grátis), Hugging Face (créditos mensais gratuitos), Gemini grátis
  (bloqueado hoje pelo saldo em aberto). Pollinations já está.
- Vídeo por API gratuita é raro. O **Ken Burns continua sempre no fim** da fila de `animar`, para sempre sair vídeo.
- Download só por `rede.baixar()`, com o domínio novo em `[seguranca]`.

### E. Sites no navegador (skill `midia-navegador`, K37)
- Config `[sites.X]`: endereço, modalidades, licença, marca d'água, cota estimada e período, molde de prompt.
- Fluxo da skill:
  1. `produzir ... --navegador` (ou `pedidos-navegador saidas/<tema>`) grava `navegador/pedidos.json`: uma linha por
     cena que ficou sem mídia boa, com modalidade, prompt pronto e imagem de entrada.
  2. Numa sessão do app desktop, o Claude lê a fila e as cotas, abre o primeiro site disponível no navegador do
     Claude, cola o prompt, espera, baixa o resultado e passa para o próximo pedido.
  3. Quando o site avisa que os créditos acabaram, o Claude marca o site como esgotado até a renovação
     (`cotas --esgotar site`) e segue no próximo site da fila.
  4. `importar-midia saidas/<tema> --site <site>` confere cada arquivo (é imagem ou vídeo de verdade, pelo `ffprobe`;
     tamanho máximo do `[seguranca]`) e registra na biblioteca com serviço e licença. Depois o `produzir` retoma
     (sem pagar de novo) usando essas mídias.
- Regras (as mesmas da D23):
  - o Diego faz o login, aceita os termos e escolhe plano;
  - o Claude não cria conta, não paga, não resolve CAPTCHA e não envia mídia de terceiros;
  - um CAPTCHA ou pedido de pagamento para o pedido e passa para o próximo site.
- **Pedidos que esperam o navegador.** O loop de hoje espera a resposta na hora; o site não. Por isso:
  - cada pedido fica no banco com estado `pendente → importado → aprovado | refazer | revisar`, e as tentativas por
    serviço continuam contando de uma sessão para outra;
  - a peça ganha o status `aguardando_navegador`;
  - quando o `produzir` retoma, ele avalia o que foi importado, decide entre aprovar ou refazer (com o prompt
    corrigido de volta no `pedidos.json`) e segue o loop de onde parou.
- **Imagem de entrada no `animar` e no `editar_imagem`.** Só pode ser enviada ao site uma imagem gerada pelo
  próprio Studio ou da biblioteca com licença que permita derivados (CC0, Pixabay, Pexels, CC-BY). Nunca uma
  CC-BY-ND nem um arquivo de terceiros sem licença, o que mantém a regra da D23.
- **`importar-midia`: exceção ao `rede.baixar()`.** O arquivo chega pelo download do navegador, não por um link do
  provedor. Por isso ele só entra por este comando, com as conferências abaixo:
  - aceita só arquivos dentro de `saidas/<tema>/navegador/`, sem atalhos (symlinks) e sem `..` no caminho;
  - cada arquivo se chama `<id_pedido>.<ext>` e só entra se o pedido existe e está `pendente`;
  - o tamanho máximo do `[seguranca]` é conferido **antes** de abrir o arquivo;
  - o tipo é conferido pelos primeiros bytes (PNG, JPEG, WebP, MP4/MOV), não pela extensão, e depois pelo `ffprobe`
    com tempo limite;
  - a cópia vai para a biblioteca pelo hash;
  - **serviço e licença vêm do config e do pedido**, nunca do arquivo nem do nome dele.

### F. Qualidade: prompts, imagens e vídeos passam pela mesma régua (pedido do Diego, 17/11)
Nada da fila gratuita entra no vídeo sem passar pelos procedimentos de qualidade do Studio (spec 01 e spec 03,
`qualidade.py`, `loop.py`). Ser grátis não muda a régua.

1. **Prompt revisado antes de gastar cota** (K35):
   - Checagem grátis, por regra, **antes** de qualquer chamada:
     - os campos obrigatórios estão presentes (sujeito, cenário, estilo e, em `animar`/`video`, movimento);
     - cabe no limite do molde;
     - não pede texto escrito dentro da imagem, a não ser que a cena peça;
     - não usa nomes da lista `evitar_nomes` do perfil (pessoas reais, marcas, obras). Uma regra não descobre
       sozinha todo nome próprio, então o juiz confere o resto;
     - respeita o "evitar" do kit visual do perfil;
     - em `animar`, o movimento combina com o da cena.
     Prompt reprovado é corrigido por regra ou vai para o loop; nunca segue para o serviço.
   - Juiz de texto **opcional** (rubrica nova `[avaliacao.prompt_midia]`):
     - critérios: fidelidade à cena, clareza visual, coerência de câmera e movimento, estilo do perfil;
     - sempre de **família diferente** de quem reescreveu o prompt;
     - liga com `-q`, como no roteiro.
2. **Imagem e vídeo avaliados como os de qualquer provedor** (K36, K37):
   - Checagens grátis primeiro:
     - proporção e resolução mínima. A spec 03 pede ≥ 1080 px, e as saídas grátis costumam ter ~1024 px; por isso
       o perfil define o piso (`resolucao_minima`, padrão 1024), e a montagem amplia com o `lanczos` do FFmpeg;
     - duração;
     - quadro congelado e cortes, pela `percepcao.py`;
     - arquivo íntegro;
     - **marca d'água**: compara os cantos do quadro com o resto, com um limiar em `[avaliacao.marca_dagua]`; a
       suspeita vai para o juiz.
   - Depois o **juiz de visão**, com as rubricas da spec 03. Hoje o Studio ainda **não tem** juiz de imagem: não
     existem `[avaliacao.imagem]` nem `[avaliacao.cena]`, e a cadeia `juiz` só manda texto. Por isso o novo cartão
     **K38** cria esse juiz antes do K36 e do K37. Rubricas:
     - `imagem` (aderência, artefatos com piso, consistência com a cena anterior, composição, texto);
     - cena animada (fidelidade à imagem de origem, movimento, artefatos);
     - vídeo final (D21).
   - Regras dos juízes iguais às de sempre: de **família diferente** de quem gerou (pela `familia` do serviço),
     resposta em JSON com evidência, e instrução para ignorar texto dentro da mídia.
   - **1 juiz** por enquanto, como na D21. Volta a 2 quando houver duas famílias com visão disponíveis.
   - **Imagem é avaliada antes de animar**: animar uma imagem ruim gasta cota de vídeo à toa (spec 03).
3. **Loop de correção com a fila**:
   - Reprovou → o `LoopCorrecao` junta o feedback do juiz ao prompt (dentro do molde) e tenta de novo.
   - No mesmo serviço: até `tentativas_por_provedor`, se ainda houver cota. Depois disso, ou se a cota acabou, vai
     para o próximo da fila.
   - Cada tentativa gasta cota e fica registrada (serviço, prompt, nota, motivo). Fica a melhor nota.
   - O teto de custo (D20) continua valendo para os juízes pagos, **somado entre as retomadas** do mesmo vídeo. O
     gasto já fica no banco (`tentativas`); hoje o orçamento vale só por execução.
4. **Sites no navegador** (K37):
   - O que vem do site passa pelo `importar-midia` e pelos mesmos juízes.
   - O Claude da skill pode descartar na hora um resultado claramente errado (outra cena, marca d'água visível),
     mas **não aprova sozinho**: a nota é dos juízes.
   - Se o loop pedir nova tentativa, a skill recebe o prompt corrigido em `navegador/pedidos.json`.
5. **Sem juiz de visão disponível** (hoje o Gemini está bloqueado):
   - a peça entra com o status `revisar`, o mesmo do banco e do `aceitar_revisar` (é o que a spec 03 chama de
     `sem_juiz`; vale o nome do banco), com as checagens grátis feitas;
   - o relatório lista o que ficou sem nota;
   - o Diego aprova o vídeo final (D19).
6. **Relatório e calibração**:
   - O relatório de qualidade e custo ganha, por mídia: serviço, licença, prompt usado, notas, tentativas e cota
     gasta.
   - As notas do Diego para imagens e cenas entram no `calibracao.py`, para conferir se o juiz concorda com ele.

## Critérios de aceite
- K34:
  - uma cota esgotada continua esgotada numa nova execução até `renova_em`, e o roteador pula o serviço sem chamá-lo;
  - `cotas` mostra quanto resta;
  - um serviço `nao_comercial` nunca entra num perfil comercial;
  - `a_conferir` nunca entra.
- K35:
  - o mesmo roteiro gera prompts diferentes por molde, dentro do limite de caracteres de cada serviço;
  - `prompt-midia` funciona sem chave nenhuma;
  - um prompt reprovado na checagem por regra nunca chega ao serviço e não gasta cota.
- Qualidade (K36 e K37):
  - uma mídia reprovada volta ao loop com o feedback do juiz no prompt seguinte e, depois do limite, passa para o
    próximo serviço;
  - nenhuma mídia entra no vídeo sem nota dos juízes ou sem estar marcada "a revisar" no relatório;
  - a imagem é avaliada antes de ser animada.
- K36: cada serviço novo tem licença, cota e data de conferência no config, com teste de contrato.
- K37:
  - automático: o `importar-midia` recusa caminho fora da pasta, tipo falso, arquivo grande demais e pedido
    inexistente;
  - automático: o estado do pedido sobrevive entre execuções;
  - **teste manual** (no PC do Diego): um vídeo real com pelo menos uma cena feita num site, importada com licença,
    e o fallback testado (site esgotado → próximo).
- K38: uma imagem com defeito conhecido (fora do tema, com texto, com marca d'água) recebe nota baixa com evidência;
  o juiz nunca é da família de quem gerou.

## Ordem
K34 (cotas + licença) → K35 (prompts) → K38 (juiz de imagem e cena) → K36 (APIs) e K37 (sites) em paralelo.
O K37 precisa do Diego para os logins. O K38 precisa de uma chave com visão (Claude ou OpenAI), ou do Gemini
desbloqueado; sem ela, as peças ficam como `revisar`.

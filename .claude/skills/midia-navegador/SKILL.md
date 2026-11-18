---
name: midia-navegador
description: Gera imagens e vídeos curtos para cenas do Torralles Studio em sites gratuitos, operados pelo Claude no navegador do Claude (app desktop, no PC do Diego), com fallback para o próximo site quando os créditos acabam. Usar quando o Diego pedir para fazer cenas "nos sites grátis", depois de `pedidos-navegador`, ou quando `produzir` deixar cenas aguardando o navegador.
---

# Mídia gratuita pelo navegador do Claude (K37, spec 14 §E, D24)

O Studio grava os pedidos; o Claude cola o prompt em cada site, baixa o resultado e o Studio confere e registra.
**Quem dá a nota é o juiz do Studio**, não o Claude da skill (spec 14 §F.4).

## Antes de começar
1. Precisa rodar **no PC do Diego**, no app desktop do Claude aberto na pasta do repositório (o navegador do Claude e a
   pasta `saidas/` ficam lá). Sessão na nuvem sem acesso ao PC não serve.
2. Gere ou atualize os pedidos:
   ```bash
   python -m torralles_studio pedidos-navegador saidas/<tema> -m imagem      # ou animar, editar_imagem...
   ```
   Ele grava `saidas/<tema>/navegador/pedidos.json`: a fila de sites (com o motivo de quem está fora: licença,
   marca d'água ou cota) e, por pedido, o **prompt pronto de cada site** e o nome do arquivo esperado.
3. Se a fila não tiver site disponível, pare e diga ao Diego por quê (ex.: todos `a_conferir` — alguém precisa ler os
   termos e anotar `licenca`, `licenca_conferida` e `termos` em `[sites.X]` no `config/fallbacks.toml`).
4. Carregue as ferramentas do navegador do Claude de uma vez (ToolSearch com o prefixo `mcp__Claude_Browser__`).

## Para cada pedido (na ordem)
1. Abra o **primeiro site disponível** da fila (`endereco`). Na primeira vez, o **Diego faz o login** e aceita os
   termos; o Claude nunca cria conta, nunca aceita termos, nunca escolhe plano nem paga.
2. Cole **exatamente** o prompt daquele site (`prompts.<site>.prompt`). Se houver `negativo` e o site tiver campo para
   isso, cole lá. No `animar`/`editar_imagem`, envie só a `entrada` indicada no pedido (imagem do Studio ou da
   biblioteca com licença que permite derivados); **nunca** envie arquivo de terceiros.
3. Espere gerar. Descarte na hora um resultado **claramente** errado (outra cena, marca d'água visível, texto na
   imagem) e gere de novo **uma** vez; se repetir, siga para o próximo site.
4. Baixe e salve como `saidas/<tema>/navegador/<id do pedido>.<png|jpg|webp|mp4>` (o nome é obrigatório: é ele que
   liga o arquivo ao pedido). Arquivos baixados na pasta Downloads: mova para lá com esse nome.
5. Créditos acabaram, limite diário, fila "volte amanhã": marque o site e passe para o próximo da fila:
   ```bash
   python -m torralles_studio cotas --esgotar <site> --motivo "créditos do dia acabaram"
   ```
6. **CAPTCHA, pedido de pagamento, de telefone ou de dados pessoais: pare nesse site** e siga para o próximo; ao
   final, conte ao Diego. Nunca tente contornar.

## Depois
1. Importe (confere tipo pelos bytes, tamanho, se abre no ffprobe, se o pedido existe; a licença vem do config):
   ```bash
   python -m torralles_studio importar-midia saidas/<tema> --site <site>
   ```
2. Rode de novo o `produzir` do tema (ele retoma sem pagar de novo): as mídias importadas passam pelas checagens
   grátis e pelo juiz; reprovadas voltam como pedido `refazer`, com o prompt corrigido no `pedidos.json`.
3. Sem juiz de visão disponível, a cena fica `revisar` e entra no relatório; o Diego aprova o vídeo final (D19).

## Regras
- Só sites com `licenca` conferida no config entram (D24); `a_conferir` nunca. Perfil comercial: só `comercial` e sem
  marca d'água. Não comercial só em perfil `comercial = false` com a regra `como_freesound` na modalidade.
- Conta, termos, planos, pagamento e publicação são sempre do Diego.
- Nada de outros projetos do Diego (D9): só cenas do Studio.
- Ao terminar, diga: pedidos feitos (por site), os que ficaram de fora e por quê, créditos gastos (`cotas`).

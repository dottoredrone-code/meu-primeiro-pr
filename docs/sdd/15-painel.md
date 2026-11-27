# Spec 15 — Painel do Studio no navegador (K43)

Aprovado pelo Diego em 18/11/2026 (etapa 1 de 2). O Studio ganha uma tela: uma página local, servida pelo mesmo
`python -m torralles_studio servidor`, para ver os projetos, assistir aos vídeos, conferir imagens, capa e post,
aprovar ou pedir alteração, pedir vídeos novos e acompanhar fila, cotas e gasto.

## Objetivo
- Abrir `http://127.0.0.1:8765/` e ver tudo o que o Studio produziu, sem linha de comando.
- Decidir por item: **aprovar** ou **pedir alteração** (com comentário) no vídeo, em cada cena, na capa e no post.
- Pedir um vídeo novo (ou um post de imagem) e cancelar pedidos na fila.

Fora desta etapa (etapa 2, outro cartão): refazer **sozinho** só a cena, a voz, a trilha, a capa ou o post que
recebeu "pedir alteração". Nesta etapa o pedido fica registrado (com o comentário) e aparece na lista de
alterações pedidas. Anúncios: cartão próprio depois (regras de chamada para ação e formatos por plataforma).

## Regras
- **Só biblioteca padrão** (`http.server`) e uma página sem framework (HTML, CSS e JS próprios, sem CDN): funciona
  sem internet e não acrescenta dependência.
- **Mesma proteção do servidor** (spec 08): host local, origem local, token opcional. Com `TORRALLES_STUDIO_TOKEN`, a
  página pede o token uma vez e guarda num cookie `HttpOnly`, `SameSite=Strict`; a API aceita o cabeçalho ou o
  cookie. A página em si (HTML, CSS, JS) não tem dados e abre sem token.
- **Cabeçalhos de segurança** em tudo do painel: `Content-Security-Policy` só com `'self'` (sem script em linha),
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- **Nenhum caminho vem do navegador**: arquivo de projeto só por nome numa lista fechada (`video_final.mp4`,
  `cena_NN.png|jpg|mp4`, `voz_NN.mp3|wav`, `capa.jpg`, `peca.png`); mídia da biblioteca só pelo hash. A pasta
  resolvida precisa estar dentro de `saidas/` (link simbólico recusado).
- **Texto do navegador nunca vira HTML**: a página monta tudo com `textContent`.
- Vídeo com `Range` (206) para poder avançar e voltar no player.
- Mensagens em português do Brasil, simples. Datas na tela em Brasília (UTC−3); no banco, UTC.

## O que aparece
| Tela | Conteúdo |
|---|---|
| **Projetos** | cada pasta de `saidas/` com `roteiro.json` ou `relatorio.json` e cada pedido da fila: título, tipo, status, nota, custo, data, capa em miniatura e a última decisão. Filtro por status |
| **Projeto** | player do vídeo final; problemas e medidas da régua; etapas com provedor e custo; cenas (imagem ou trecho, fala, texto na tela, clima, fonte e licença); capa; post (com botão copiar); créditos; trilha e efeitos; briefing do pedido; histórico de decisões |
| **Novo** | tema, tipo (vídeo curto, story, post de imagem), duração, perfil, texto na tela, paleta e teto (até US$ 1,50). Vira um pedido no contrato da spec 08 |
| **Biblioteca** | mídia guardada (busca por texto e tipo), com fonte, autor, licença e link |
| **Controle** | provedores prontos por tarefa, cotas grátis (quanto falta e quando renova), gasto do mês, fila e perfis |

## Decisões (revisões)
Tabela nova `revisoes` (migração 11): `projeto`, `item` (`video`, `capa`, `post`, `cena_NN`), `decisao`
(`aprovado` ou `alterar`), `comentario`, `criado_em`, `atendida`. Pedir alteração exige comentário (até 2000
caracteres). A última decisão de cada item vale. Num pedido da fila em `aguardando_aprovacao`, aprovar o **vídeo**
(ou a peça de imagem) também aprova o pedido (`ServicoPecas.aprovar`).

## API do painel (JSON)
- `GET /painel/api/resumo`, `GET /painel/api/projetos`, `GET /painel/api/projetos/{id}`,
  `GET /painel/api/biblioteca?busca=&tipo=`
- `POST /painel/api/projetos/{id}/revisao` `{"item", "decisao", "comentario"}`
- `POST /painel/api/novo` (formulário simples → contrato 1.0 → `ServicoPecas.enviar`)
- `POST /painel/entrar` `{"token"}` (só quando há token)
- Arquivos: `GET /painel/arquivo/{id}/{nome}` e `GET /painel/midia/{hash}`
- Cancelar continua em `POST /v1/pecas/{job_id}/cancelar`.

## Aceite
- Testes: lista e detalhe a partir de pastas falsas; nome de arquivo fora da lista, `..`, link simbólico e id
  inválido recusados; Range; revisão grava e a aprovação do vídeo aprova o pedido; pedido novo vira contrato válido;
  host/origem/token valem também no painel; a página não tem script em linha.
- Teste no navegador do Claude com o projeto real `saidas/beneficios-do-cha-verde`.

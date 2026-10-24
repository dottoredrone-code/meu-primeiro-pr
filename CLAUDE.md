# Torralles Studio — guia para agentes

App que transforma ideias ou briefings em **imagens e vídeos prontos para publicar**, escolhendo o melhor
modelo de IA por etapa, com fallback, controle de qualidade com loop e teto de custo.

## Antes de agir
1. Leia `KANBAN.md` (o que está em andamento e o próximo cartão) e `docs/sdd/decisoes.md` (D1–D20).
2. A spec de cada cartão está em `docs/sdd/` (o cartão aponta qual). **Não implemente fora de um cartão.**
3. Siga o protocolo de execução: plano → implementação → **verificação por um agente diferente** → correção.

## Regras do projeto
- **D9 — marca:** "Torralles" é a marca de todos os projetos do Diego; o Studio é **independente**. Não use
  exemplos, briefings ou dados de outros projetos (nada jurídico) em código, testes ou specs.
- **Sem segredos no repositório:** chaves só em variáveis de ambiente ou no `.env` (ignorado pelo Git).
  Mensagens de erro passam por `mascarar()`.
- **Modelos são dados, não código:** nomes e custos ficam em `config/fallbacks.toml`. O teste
  `tests/test_contratos.py` impede modelos aposentados. Revisão mensal: cartão KR1.
- **Downloads** de arquivos devolvidos por provedores só via `rede.baixar()` (lista de domínios em `[seguranca]`).
- **Teto de custo** (D20): US$ 1,50 por vídeo; provedores pagos que não couberem são pulados.
- **Licenças:** nada AGPL ou "não comercial" no produto (D2). Cada mídia guarda fonte e licença (D18).
- **Dependências:** o núcleo usa só a biblioteca padrão do Python + FFmpeg. Nova dependência só com motivo registrado.
- Textos e mensagens ao usuário em **português do Brasil**, simples e diretos.

## Estrutura
```
torralles_studio/
  roteador.py     fallback por tarefa, descanso de provedores, teto de custo
  provedores/     texto, busca, imagem, voz, vídeo (um arquivo por tipo)
  funcoes.py      ideias, roteiro, pesquisa, imagem, voz, vídeo
  roteiro.py      roteiro JSON com clima e sons por cena (esquema + régua); pesquisa.py fontes e citações
  percepcao.py    "assistir" um vídeo: quadros, cortes, som, transcrição
  seguranca.py    mascarar chaves, orçamento
  qualidade.py    avaliador 0–100 (juízes de outra família); fatos.py fatos travados
  loop.py         loop de correção; relatorio.py relatório de qualidade e custo
  producao.py     vídeo completo de um tema: pesquisa → roteiro → imagem, voz e cena → montagem (retoma sem pagar de novo)
  trilha.py       trilha pelo clima do roteiro (BPM e energia pelo FFmpeg, voz eliminatória); exportar.py pasta para o CapCut
  contrato.py     pedido Ops → Studio (spec 08); servico.py fila de pedidos; servidor.py HTTP local e MCP
  montagem.py     vídeo final: tempo da fala, transições na batida, legendas na área segura, trilha sob a voz, −14 LUFS
  banco.py        SQLite: projetos, peças, tentativas, custo, retomada e cache (dados/, fora do Git)
  biblioteca.py   mídia por hash (sem duplicatas), licença obrigatória, busca por etiqueta, créditos CC-BY
  cerebro.py      resumo dos aprendizados de produção para colar no Cérebro (D16)
  perfis.py       perfis por projeto (dados/perfis/<id>.toml, fora do Git; modelo em config/perfil_modelo.toml)
  rede.py         HTTP com erros padronizados e downloads seguros
  config.py       carrega config/fallbacks.toml e o .env
config/fallbacks.toml   cadeias, modelos, custos, segurança
docs/sdd/               specs (SDD) e decisões
exemplos/               vídeos de teste da percepção
```

## Comandos
```bash
python -m unittest discover -s tests          # testes (rodar antes de todo commit)
python -m torralles_studio status             # cadeias e provedores prontos
python -m torralles_studio assistir video.mp4 # relatório de percepção
python -m torralles_studio avaliar-video video.mp4   # juiz que assiste com som (Gemini); aceita link do YouTube
python -m torralles_studio perfil-novo meu-canal "Meu canal"   # cria perfil de projeto; 'perfis' lista
python -m torralles_studio cerebro --desde 2026-10-01          # aprendizados para colar no CEREBRO_MESTRE.md
python -m torralles_studio roteiro "tema" -p meu-canal          # gera com o perfil do projeto
python -m torralles_studio roteiro "tema" -q                    # com juiz e loop de correção (também em pesquisa)
python -m torralles_studio produzir "tema" -d 30 --pesquisa      # vídeo completo (saidas/<tema>/video_final.mp4); --capcut, --sem-trilha
python -m torralles_studio exportar-capcut saidas/<tema>         # pasta para editar no CapCut
python -m torralles_studio testar-voz                          # frase com lh, nh, rr em cada voz pronta (ouvir + erro de palavras)
python -m torralles_studio servidor                           # HTTP local para o Ops (docs/servidor.md); 'mcp' para o Hermes
python -m torralles_studio montar projeto.json -o final.mp4   # montagem final + régua (docs/montagem.md)
python -m torralles_studio --config outro.toml status   # config alternativo (ou TORRALLES_CONFIG)
```
- O `.env` é lido da **raiz do repositório** e nunca sobrescreve variáveis já definidas.
- Teste real com chaves (no PC do Diego): `docs/teste-real.md`.
- **FFmpeg** é necessário para `percepcao`, o vídeo `ken_burns` e alguns testes (pulados se faltar).

## Git
- Branch de trabalho: `claude/multi-model-integration-app-g1697x`.
- Commits pequenos, um cartão por commit, mensagem `tipo(Kxx): descrição` em português.
- Ao concluir um cartão: atualizar `KANBAN.md` e, ao fim de cada camada, registrar aprendizados para o Cérebro (D16).

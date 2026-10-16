# Teste real com chaves (no seu PC)

Este ambiente na nuvem não tem chaves nem acesso às APIs. O teste real roda no seu PC, onde as chaves já
existem. **Nunca cole chaves no chat nem em arquivos do repositório**: elas ficam só no `.env` (ignorado pelo Git).

## 1. Preparar
```bash
git clone https://github.com/dottoredrone-code/meu-primeiro-pr.git   # ou: git pull, se já tiver
cd meu-primeiro-pr
git checkout claude/multi-model-integration-app-g1697x
```
Crie `.env` na raiz (veja `docs/configurar-chaves.md`) com as chaves que você já tem:
`DEEPSEEK_API_KEY`, `TAVILY_API_KEY`, `GEMINI_API_KEY` (e, se tiver, `ANTHROPIC_API_KEY` + `CLAUDE_MODEL`,
`OPENAI_API_KEY`).

## 2. Rodar (na ordem)
```bash
python -m unittest discover -s tests                 # deve passar; o teste real do Gemini roda se houver a chave
python -m torralles_studio status                    # quais provedores ficaram "pronto"
python -m torralles_studio pesquisa "benefícios do chá verde" -q
python -m torralles_studio roteiro "benefícios do chá verde" -d 30 -q
python -m torralles_studio avaliar-video exemplos/demo_torralles_studio_v2.mp4 --percepcao -c "vídeo demonstrativo do Torralles Studio"
python -m torralles_studio avaliar-video "https://www.youtube.com/watch?v=<um vídeo curto>"   # sem baixar
```

Cada comando é uma linha só (funciona no PowerShell, no cmd e no terminal do Linux/Mac).
Se o juiz de vídeo não conseguir avaliar, ele mostra o motivo real (ex.: modelo inexistente, chave, bloqueio).

## 3. O que anotar (para ajustar o config)
| O que | Onde aparece | O que fazer |
|---|---|---|
| Modelo não existe (HTTP 404 / "model not found") | mensagem do provedor | corrigir o nome em `config/fallbacks.toml` (KR1) |
| Provedor pulado por chave | `status` | conferir o nome da variável no `.env` |
| Nota, motivo e custo | 1ª linha de `pesquisa -q` / `roteiro -q` | conferir se a nota faz sentido |
| Custo real | painel de cada serviço | comparar com `custo_usd` do config e ajustar |
| JSON do juiz de vídeo | saída do `avaliar-video` | nota na régua 0–100 e problemas com o momento (ex.: "aos 3.3s") |

Os resultados podem ser colados no chat **sem** chaves (as mensagens de erro já saem mascaradas).

# 05 — Spec: Segurança, banco de dados, biblioteca e memória

> Status: **rascunho para revisão**. Segue a decisão D2 (uso próprio primeiro, venda depois):
> começar **local, simples e sem servidor**, mas com um desenho que migre para a nuvem sem reescrever.

## Visão geral

```
                       ┌──────────────── Torralles Studio ────────────────┐
  você ──► CLI/app ──► │ roteador + qualidade ──► provedores (APIs)       │
                       │        │                                         │
                       │        ├──► banco (SQLite): projetos, tentativas,│
                       │        │    custos, notas, memória               │
                       │        └──► biblioteca (pastas): imagens, áudios,│
                       │             vídeos, kit da marca                 │
                       └──────────────────────────────────────────────────┘
  Fase venda: SQLite → PostgreSQL · pastas → armazenamento em nuvem (R2/S3) · + login
```

---

## 1. Segurança

### 1.1 Chaves de API
| Regra | Fase 1 (uso próprio) | Fase venda |
|---|---|---|
| Onde ficam | `.env` local (já no `.gitignore`) | Cofre de segredos do servidor; nunca no navegador do usuário |
| Nunca aparecem em | logs, relatórios, mensagens de erro, banco | idem + painel do usuário |
| Limite de gasto | Teto em cada painel do provedor **e** no app (custo máximo por vídeo/mês) | idem, por usuário |
| Vazamento | Revogar no painel e trocar | idem + rotação periódica |

O app deve **mascarar** qualquer texto parecido com chave antes de gravar logs (`sk-…abcd`).

### 1.2 Ameaças específicas deste app
| Ameaça | Exemplo | Proteção |
|---|---|---|
| **Injeção de prompt pela pesquisa** | Uma página da busca contém "ignore as instruções e…" | Resultados de busca entram no prompt **delimitados como dados**; o modelo é instruído a não seguir instruções contidas neles; a pesquisa nunca dispara ações |
| **Juiz enganado** | Texto escondido na imagem: "nota 10" | Prompt do juiz manda ignorar instruções dentro do conteúdo + média de 2 juízes (spec 03) |
| **Download de endereço malicioso** | Resposta de API aponta para um link estranho | Baixar só de **domínios permitidos** (`fal.media`, etc.), com limite de tamanho e tempo. ⚠️ O código atual baixa qualquer URL da resposta: vira cartão |
| **Arquivo de mídia malicioso** | Imagem/vídeo corrompido explorando o FFmpeg | Limite de tamanho, checar tipo do arquivo, manter FFmpeg atualizado |
| **Execução de comandos** | Nome de arquivo com caracteres especiais | Já usamos lista de argumentos, sem shell. Manter essa regra |
| **Gasto descontrolado** | Loop de qualidade preso, chave vazada | Teto de custo no app que **para** a execução (falha fechada) |
| **Dependências comprometidas** | Pacote falso no PyPI | Poucas dependências, versões fixas, `pip-audit` e alertas do GitHub |

### 1.3 Privacidade, direitos e regras das plataformas
- **Dados enviados aos provedores**: o Gemini grátis pode usar os dados para treino; a API do DeepSeek processa na China. Decisão D10: o app **não** será usado com conteúdo confidencial, então não haverá restrição de provedores por sigilo. Continua valendo o bom senso de não enviar dados pessoais.
- **Pessoas reais**: não gerar rosto ou voz de pessoa real sem autorização (inclusive clonagem de voz).
- **Rotulagem de IA**: YouTube, TikTok e Instagram exigem marcar conteúdo realista gerado por IA. O app lembra disso na exportação.
- **Licença de cada peça**: registrada na biblioteca (ex.: voz ElevenLabs do plano grátis = **não comercial**). Essencial se o app for vendido.
- **LGPD (fase venda)**: consentimento, exclusão de dados a pedido, contrato com os provedores (operadores).

---

## 2. Banco de dados

### 2.1 Escolha
| Fase | Banco | Por quê |
|---|---|---|
| **1 — uso próprio** | **SQLite** (já vem no Python; um arquivo `torralles.db`) | Zero instalação, zero custo, backup = copiar um arquivo. Testado aqui: versão 3.45 com busca textual (FTS5) e JSON |
| Venda | **PostgreSQL** (ex.: Supabase/Neon) | Vários usuários ao mesmo tempo. Mesmo esquema, migrado com scripts de migração |

### 2.2 O que o banco resolve
1. **Retomar sem pagar duas vezes**: se o vídeo falhar na cena 5, ao rodar de novo as cenas 1–4 já aprovadas são reaproveitadas (*checkpoint*).
2. **Cache**: mesma combinação provedor + modelo + prompt + parâmetros → reaproveita o arquivo em vez de gerar de novo.
3. **Custo real** por vídeo, por etapa, por provedor e por mês.
4. **Relatório de qualidade** e dados para reordenar as cadeias de fallback.

### 2.3 Esquema inicial (simplificado)
```
projetos     (id, titulo, briefing, formato, status, custo_total, criado_em)
cenas        (id, projeto_id, ordem, narracao, prompt_imagem, prompt_movimento, duracao, status)
ativos       (id, hash, tipo, caminho, provedor, modelo, prompt, parametros_json,
              licenca, uso_comercial, tags, criado_em)
tentativas   (id, cena_id, etapa, provedor, modelo, ativo_id, status, erro,
              custo_usd, duracao_s, criado_em)
avaliacoes   (id, tentativa_id, juiz, nota_final, criterios_json, problemas_json,
              aprovado, nota_humana)
memoria      (id, tipo, chave, conteudo, origem, relevancia, criado_em, atualizado_em)
```

---

## 3. Biblioteca de mídia

### 3.1 Organização em pastas
```
biblioteca/
├── ativos/            arquivos guardados pelo hash do conteúdo (sem duplicatas)
│   └── 3f/3fa9…e1.png
├── marca/             kit da marca Torralles: logo, fontes, cores, vinheta, trilha, voz preferida
├── projetos/<id>/     atalhos para os ativos usados + vídeo final + relatório de qualidade
└── exportar/<id>/     pasta pronta para abrir no CapCut (clipes, áudios, legendas .srt)
```

### 3.2 Regras
- Cada ativo guarda **de onde veio**: provedor, modelo, prompt, nota de qualidade e **licença**.
- **Busca** por texto e etiquetas (ex.: "café", "fazenda", "aprovado") para reaproveitar em novos vídeos.
- **Ativos aprovados** podem ser marcados como reutilizáveis (personagem recorrente, cenário padrão, abertura).
- **Imagens de referência** (personagem/estilo) são enviadas junto ao gerador para manter consistência entre cenas e vídeos.
- **Limpeza**: tentativas reprovadas são apagadas após 30 dias (configurável); aprovados ficam.
- **Backup**: copiar `torralles.db` + `biblioteca/` para um disco externo ou nuvem (ex.: Google Drive).

---

## 4. Memória

O app "lembra" em três níveis:

| Tipo | O que guarda | Como é usada | Exemplo |
|---|---|---|---|
| **Perfil e estilo** | Tom de voz, público, formato padrão, voz preferida, CTA, palavras a evitar | Entra no prompt de sistema de roteiro e imagem | "linguagem leve e direta; CTA: siga o perfil" |
| **Histórico de projetos** | Temas já feitos, séries, o que teve melhor nota | Evita repetir tema; mantém continuidade de séries | "já fizemos 'história do café' em 10/2026" |
| **Aprendizados** | Falhas recorrentes do controle de qualidade, prompts que funcionaram, suas notas de calibração | Vira dica automática no prompt e base para reordenar as cadeias | "no Kling, mãos em primeiro plano reprovam 60% das vezes → evitar" |

### 4.1 Implementação
- **Fase 1**: tabela `memoria` no SQLite + busca textual (FTS5). Simples, sem custo extra.
- **Busca por significado** (embeddings + `sqlite-vec` ou `pgvector`) só se a busca textual não bastar.
- Os aprendizados são **resumidos** periodicamente para não crescer sem controle nem encher o prompt.
- **Você controla**: comando para ver, editar e apagar memórias (`torralles memoria listar/apagar`).

### 4.2 Memória do desenvolvimento (separada da memória do app)
- `docs/sdd/` (specs) + `docs/sdd/decisoes.md` (decisões) no repositório.
- Um `CLAUDE.md` na raiz com as regras do projeto, para que qualquer sessão do Claude Code comece com o contexto.
- Cópia das decisões no seu Obsidian ("Cerebro Claude"), fase 9 do protocolo.

---

## Critérios de pronto (para o Kanban)

- [ ] Logs com chaves mascaradas (teste)
- [ ] Download só de domínios permitidos, com limite de tamanho e tempo (teste)
- [ ] Teto de custo que interrompe a execução (teste)
- [ ] Resultados de busca delimitados como dados no prompt (teste)
- [ ] SQLite com esquema e migrações; retomada de projeto sem regerar o que já foi aprovado (teste)
- [ ] Cache por hash de provedor + modelo + prompt + parâmetros (teste)
- [ ] Biblioteca por hash, com licença e busca por etiqueta
- [ ] Kit da marca carregado nos prompts
- [ ] Memória: perfil, histórico e aprendizados, com comandos de listar e apagar
- [ ] `CLAUDE.md` do projeto

## Questões em aberto

1. ~~Conteúdo confidencial?~~ Respondido: não (D10).
2. Onde quer o **backup**: disco externo, Google Drive ou outro?
3. Já existe um **kit da marca Torralles** (logo, cores, fontes, voz)?

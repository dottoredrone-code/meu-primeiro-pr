# 16 — Spec: Acervo de mídia para os agentes (imagens, vídeos, trilhas, efeitos e sonoplastia)

> Status: **aprovada pelo Diego em 21/11/2026** (pedido de 19/11/2026); K47 pronto. Amplia a [spec 11](11-banco-midia-gratuita.md)
> e a biblioteca da [spec 05](05-dados-seguranca-memoria.md). Licenças mudam: reconfirmar no site oficial antes
> de importar cada fonte.

## Objetivo
Ter no Studio um **acervo local** de imagens, vídeos, trilhas, efeitos e sons de ambiente, com licença conferida, que
**qualquer agente** (produção do Studio, Remotion, HyperFrames, CapCut no navegador) consiga **achar pelo que o
projeto pede** (clima, energia, tipo, duração, ritmo) e **inserir** com o crédito certo, sem baixar de novo e sem
pagar.

## O que já existe (não refazer)
| Peça | O que faz hoje |
|---|---|
| `biblioteca.py` + tabela `ativos` | Guarda cada arquivo uma vez (hash), com licença obrigatória, fonte, autor, link, etiquetas e perfil; `buscar(tags, tipo, texto)`; créditos CC-BY |
| `efeitos.py` / `importar-sons` | Importa uma pasta de sons com licença; etiquetas **só pelo nome do arquivo**; escolhe um som por corte pelo clima |
| `trilha.py` | Mede BPM e energia pelo FFmpeg **na hora de escolher** (não guarda); recusa trilha com voz |
| K20 / K40 | Fotos e vídeos de banco (Openverse, Pexels, Pixabay) baixados por cena, com licença |

## O que falta
1. **O acervo está vazio.** Por isso os testes de motion saíram sem som e o `produzir` sai sem efeitos.
2. **Etiquetas pobres:** só o nome do arquivo. Não há clima, energia, duração, BPM, "faz loop?", orientação.
3. **Medidas não ficam guardadas:** cada escolha mede de novo.
4. **Agentes de fora do Python não acham nada:** Remotion e HyperFrames não têm como perguntar "uma trilha calma de
   30 s" ao Studio.
5. **Tipos de som misturados:** efeito de corte, sonoplastia (passos, xícara), ambiente (chuva, cidade) e trilha
   precisam de buscas diferentes.

## Proposta

### 1. Tipos e etiquetas (taxonomia)
| Campo | Valores | Como é preenchido |
|---|---|---|
| `tipo` | `imagem`, `video`, `trilha`, `efeito` (cortes: whoosh, impacto, pop), `sonoplastia` (ação: passos, porta, xícara), `ambiente` (fundo contínuo: chuva, cidade) | Na importação (`--tipo`) |
| `clima` | os mesmos do roteiro: calmo, alegre, épico, tenso, inspirador, curioso, reflexivo | Importação + sugestão pelo nome/pasta; o Diego corrige no painel |
| `energia` | baixa, média, alta | **Medida** (FFmpeg) em áudio; manual em vídeo |
| `duracao_s`, `bpm`, `loop` | número, número, sim/não | **Medidos** (FFmpeg); `loop` quando o fim emenda no começo |
| `orientacao`, `resolucao` | vertical, horizontal, quadrado; largura x altura | **Medidos** (ffprobe) em imagem e vídeo |
| `palavras` | livre: "xícara", "vento", "praia" | Nome do arquivo + pasta + o que vier da fonte |

As medidas ficam guardadas (coluna nova `medidas_json` em `ativos`, migração simples), sem medir de novo.

### 2. Importação (generaliza o `importar-sons`)
```
python -m torralles_studio importar-acervo <pasta> --tipo trilha --licenca pixabay --fonte Pixabay [--clima calmo]
```
- Confere a licença antes de abrir a pasta (regra atual), mede cada arquivo, sugere etiquetas e mostra um resumo.
- Copia o texto da licença da fonte para `dados/acervo/licencas/` (D18).
- `importar-sons` continua funcionando (vira atalho de `--tipo efeito`).
- Vídeos e fotos que o K40 já baixa por cena passam a ficar no acervo com as mesmas etiquetas, para reaproveitar.

### 3. Busca para os agentes
- **Linha de comando (qualquer agente, inclusive Remotion e HyperFrames):**
  ```
  python -m torralles_studio acervo buscar --tipo trilha --clima calmo --energia baixa --duracao 30 --json
  ```
  Devolve os melhores itens com caminho, medidas, licença e crédito.
- **Copiar para um projeto de animação:** `acervo usar <hash> --para motion/remotion/public` copia o arquivo e
  acrescenta a linha em `creditos.txt` da pasta.
- **MCP / HTTP:** ferramenta `buscar_midia` no `servidor.py` (mesmos filtros), para o Hermes e o Ops.
- **Painel (K43):** a aba Biblioteca ganha os filtros acima e permite corrigir clima e energia.
- **`produzir`:** `trilha.py` e `efeitos.py` passam a usar as medidas guardadas e os tipos novos (sonoplastia pelos
  "sons" de cada cena do roteiro; ambiente embaixo da cena inteira).

### 4. Fontes para começar (download manual pelo Diego; nada pago)
| Fonte | Tipo | Licença (a reconfirmar) | Situação |
|---|---|---|---|
| Pixabay (música e efeitos) | trilha, efeito, sonoplastia | Licença Pixabay: uso comercial, sem crédito obrigatório | ✅ já aceita pelo Studio |
| Pexels / Pixabay (vídeos e fotos) | video, imagem | Uso comercial | ✅ já aceita (K40) |
| Mixkit | efeito, trilha, video | Licença própria gratuita; música tem regras próprias | ⚠️ ler os termos antes |
| Freesound — só CC0, baixado à mão | sonoplastia, ambiente | CC0 | ⚠️ D22 trata da API; confirmar com você o uso do site |
| Biblioteca de Áudio do YouTube | trilha | Pensada para vídeos do YouTube | ⚠️ conferir uso fora do YouTube (Instagram, TikTok) |
| MusicGen, CC-BY-NC, "uso pessoal" | — | Não comercial | ❌ bloqueadas (D2) |

### 5. Limites
- Só biblioteca padrão + FFmpeg (as medidas já usam o FFmpeg).
- Acervo e banco ficam em `dados/` (fora do Git); só o código e esta spec vão para o repositório.
- Nenhuma fonte paga; IA para som continua só quando faltar no acervo e com aviso (D20).

## Cartões propostos
| ID | Cartão | Depende de | Aceite |
|---|---|---|---|
| K47 | Taxonomia, medidas guardadas e `importar-acervo` (tipos, clima, energia, BPM, duração, loop, orientação; licença copiada) | — | Importar uma pasta de 10 trilhas da Pixabay grava as medidas e `acervo buscar --clima calmo` acha as calmas |
| K48 | Busca para agentes: `acervo buscar --json`, `acervo usar --para`, ferramenta MCP `buscar_midia`, filtros no painel | K47 | Um agente monta o teste do Remotion com trilha e efeito do acervo, e o `creditos.txt` sai certo |
| K49 | `produzir` usa o acervo novo: sonoplastia pelos "sons" do roteiro e ambiente por cena | K47 | Vídeo de teste com trilha, efeitos de corte e um som de ação no tempo certo |
| K50 | Primeiro acervo (com o Diego): ~20 trilhas por clima, ~40 efeitos, ~20 sonoplastias e ambientes | K47 · termos conferidos | `acervo` lista os itens com licença e medidas |

## Perguntas para o Diego
Respostas assumidas ao começar o K47 (21/11): 1 — tipos e etiquetas como estão; 2 — o Diego baixa os primeiros da Pixabay; os termos de Mixkit, Freesound e YouTube são lidos antes do K50; 3 — agentes de motion só com o acervo (sem os serviços pagos da `media-use`).

1. Aprovar os tipos e etiquetas da seção 1?
2. Você baixa os primeiros arquivos à mão (Pixabay primeiro) ou prefere que eu leia os termos de Mixkit, Freesound
   e YouTube antes?
3. A skill `media-use` do HyperFrames pode gerar sons com serviços pagos (ElevenLabs, HeyGen). Deixamos **só o acervo**
   para os agentes de motion, como está proposto?

# 11 — Spec: Banco de imagens, vídeos, efeitos sonoros e trilhas gratuitos

> Status: **rascunho para revisão**. Complementa a biblioteca da [spec 05](05-dados-seguranca-memoria.md).
> Limites e licenças mudam: reconfirmar nos sites oficiais antes de usar cada fonte.

## Por que não o CapCut
O CapCut tem um acervo grande, mas **não oferece API** para buscar e baixar automaticamente, e a licença dos
itens vale para uso **dentro do CapCut**. O Studio precisa de fontes que possam ser **buscadas e baixadas por código**,
com licença clara para uso comercial. O CapCut continua como opção de acabamento manual (D5).

## Três camadas, do mais barato ao mais flexível

```
1. Acervo local (baixado uma vez, offline, licença conferida)  →  rápido, grátis, previsível
2. Busca por API em bancos gratuitos                           →  variedade, grátis, com limite de uso
3. Geração por IA (efeito ou trilha sob medida)                →  exato para a cena, custa centavos
```
Mesma lógica de fallback do resto do Studio: tenta o acervo, depois as APIs, depois a geração.

## Fontes candidatas

### Imagens e vídeos de banco (b-roll)
| Fonte | Acesso automático | Licença / observações |
|---|---|---|
| **Pexels** | API gratuita (200 pedidos/h, 20 mil/mês; ampliável de graça com atribuição) | Uso comercial sem atribuição obrigatória; a API pede link para a Pexels |
| **Pixabay** | API gratuita (imagens e vídeos) | Licença própria, uso comercial permitido; conferir restrições (ex.: marcas, pessoas) |
| **Unsplash** | API gratuita (50/h no modo demo; mais após aprovação) | Exige crédito ao fotógrafo e à Unsplash e registrar o "download" pela API |
| **Openverse** (WordPress) | API gratuita | Agrega obras Creative Commons; filtrar por licenças que permitem uso comercial |
| **Wikimedia Commons** | API gratuita | Licenças variadas (CC0, CC-BY, CC-BY-SA); filtrar com cuidado |

### Efeitos sonoros
| Fonte | Acesso automático | Licença / observações |
|---|---|---|
| **Freesound** | API com chave gratuita; download em qualidade total exige login OAuth2 (prévia em MP3 sem OAuth) | Filtrar por **CC0** (sem atribuição) ou CC-BY (com crédito); evitar CC-BY-NC |
| **Openverse** (áudio) | API gratuita | Agrega Freesound, Jamendo e outros; mesmo filtro de licença |
| **Pacotes CC0 / royalty-free** (ex.: Kenney, pacotes anuais da Sonniss) | Download único para o **acervo local** | Uso comercial; guardar o arquivo de licença junto |
| **ElevenLabs – efeitos por texto** | API (paga, com créditos grátis limitados) | Gera o efeito exato ("passos na madeira, 2 s"); conferir licença do plano |

### Trilhas (música)
| Fonte | Acesso automático | Licença / observações |
|---|---|---|
| **Biblioteca de Áudio do YouTube** | ❌ Sem API (download manual) | Grátis para vídeos no YouTube; bom para formar o **acervo local** de trilhas por clima |
| **Incompetech (Kevin MacLeod)** | Download manual para o acervo | CC-BY: exige crédito na descrição |
| **Openverse / Jamendo** | API | Jamendo: uso comercial costuma exigir licença paga; filtrar com cuidado |
| **ElevenLabs – música** | API paga | Modelo treinado com dados licenciados, liberado para uso comercial (segundo o fornecedor) |
| **Stable Audio** | API paga; versão aberta para rodar local | Uso comercial exige plano/licença; conferir termos |
| ⚠️ **MusicGen (Meta)** | Local | Pesos com licença **não comercial**: não usar |

## Como o Studio escolhe o material
1. O roteiro já indica, por cena, o **clima** (calmo, épico, alegre, tenso) e os **sons** pedidos ("vento", "xícara sendo apoiada").
2. Busca no acervo por etiquetas; se não achar, nas APIs; se não achar, gera.
3. Um **juiz** confere se o material combina com a cena (ouvindo a prévia via percepção da [spec 10](10-percepcao.md)).
4. Mixagem automática: **trilha abaixa sozinha quando a voz entra** (FFmpeg `sidechaincompress`), voz a −14 LUFS no total, música pelo menos 12 dB abaixo da voz (spec 03).

## Regras de licença (obrigatórias)
- Cada arquivo guarda na biblioteca: **fonte, autor, link, licença, data do download** e se permite uso comercial.
- **Aceitas por padrão:** CC0, licença Pexels, licença Pixabay, itens comprados/gerados com direito comercial.
- **Com crédito automático na descrição:** CC-BY.
- **Bloqueadas:** CC-BY-NC, CC-BY-ND quando houver edição, "uso pessoal", fonte sem licença clara.
- O Studio gera um **arquivo de créditos** por vídeo para colar na descrição quando houver itens CC-BY.

## Acervo local inicial (sugestão)
- ~40 trilhas por clima (calmo, inspirador, épico, alegre, reflexivo, tenso), da Biblioteca do YouTube e de pacotes CC0.
- ~150 efeitos essenciais: transições (whoosh, swipe), interface (pop, clique), natureza (vento, chuva, pássaros), casa (xícara, porta, passos), impacto, "sino de chamada para ação".
- Organizado em `biblioteca/acervo/{trilhas,efeitos}/<clima ou categoria>/` com um `licencas.json`.

## Critérios de pronto (para o Kanban)
- [ ] Provedores `busca_midia` (Pexels, Pixabay, Openverse) e `busca_som` (Freesound, Openverse) com fallback e filtro de licença (testes)
- [ ] Acervo local com `licencas.json` e busca por etiqueta/clima
- [ ] Provedor de geração de efeito/trilha (ElevenLabs) como último recurso
- [ ] Mixagem com abaixamento automático da trilha sob a voz (teste de nível)
- [ ] Arquivo de créditos por vídeo
- [ ] Domínios das fontes liberados na lista de downloads permitidos (D8)

## Questões em aberto
1. Prefere montar o acervo local de trilhas manualmente (você escolhe as músicas que gosta na Biblioteca do YouTube) ou deixar a escolha para o Studio?
2. Topa um pequeno custo com efeitos/trilhas gerados por IA quando o acervo não tiver o som certo?

# meu-primeiro-pr

Repositório de exemplo para praticar o fluxo de Pull Request com Claude Code.

## O que é isso?

Um projeto simples de calculadora em Python para demonstrar como:
- Criar um repositório no GitHub
- Abrir branches de feature
- Enviar Pull Requests

## Como usar

```bash
python calculadora.py
```

## Funcionalidades

- Soma
- Subtração
- Multiplicação
- Divisão

---

# Torralles Studio (fallback entre modelos)

Gera ideias, roteiros, pesquisas, imagens, vozes e vídeos. Cada função tem uma
**cadeia de fallback**: se o modelo preferido não tiver chave, atingir o limite
ou der erro, o próximo da lista assume automaticamente.

| Função | Cadeia (em ordem) |
|---|---|
| ideias | DeepSeek → Gemini → Claude → GPT → OpenRouter (grátis) → Ollama (local) |
| roteiro | DeepSeek → Claude → Gemini → GPT → OpenRouter (grátis) → Ollama (local) |
| pesquisa | Busca (Tavily → Brave) + síntese DeepSeek Reasoner → DeepSeek → Gemini → Claude → … |
| imagem | Nano Banana (Gemini) → FLUX (fal.ai) → GPT Image → Cloudflare FLUX (grátis, comercial) → Pollinations (fora: marca d'água) |
| voz | ElevenLabs → OpenAI TTS → Gemini TTS → Edge TTS (grátis) |
| animar (imagem → vídeo) | Kling (fal.ai) → Wan (fal.ai) → Ken Burns com FFmpeg (grátis, local) |
| juízes | texto: Claude → Gemini → GPT → …; imagem: modelos com visão; vídeo final: Gemini (assiste com som) |

As cadeias e os modelos ficam em [`config/fallbacks.toml`](config/fallbacks.toml):
para mudar a ordem ou trocar um modelo, edite esse arquivo, sem tocar no código.

## Como funciona o fallback

- Provedor **sem chave** → pulado.
- **Erro temporário** (429, 5xx, rede) → tenta de novo com espera; persistindo, vai para o próximo.
- **Erro definitivo** (400, resposta inválida) → vai direto para o próximo.
- **Limite (429)** ou **chave inválida (401/403)** → o provedor fica "em descanso" e é evitado nas próximas chamadas.
- **Cota grátis acabou** (padrão de mensagem do config ou Retry-After longo) → o serviço fica fora até a cota
  renovar, mesmo numa nova execução (`python -m torralles_studio cotas`).
- **Licença** (D24): serviço com termos não conferidos, só não comercial ou com marca d'água fica fora dos vídeos
  comerciais; cada mídia guarda fonte e licença.
- **Prompt por serviço**: cada serviço recebe o prompt no formato dele, conferido antes de gastar cota.
- Roteiro que não vem em JSON válido conta como falha e passa para o próximo modelo.

## Uso

Requer Python 3.11+ e nenhuma biblioteca extra (FFmpeg opcional, para o vídeo local;
`pip install edge-tts` opcional, para voz grátis).

```bash
cp .env.example .env              # preencha só as chaves que tiver
python -m torralles_studio status       # mostra cada cadeia e o que está pronto
python -m torralles_studio ideias "história do café"
python -m torralles_studio roteiro "história do café" -d 30
python -m torralles_studio pesquisa "origem do café no Brasil"
python -m torralles_studio imagem "coffee farm at sunrise, cinematic" -o saidas/cena1.png
python -m torralles_studio voz "O café chegou ao Brasil em 1727." -o saidas/cena1.mp3
python -m torralles_studio video saidas/cena1.png "slow camera push-in" -o saidas/cena1.mp4
python -m torralles_studio produzir "benefícios do chá verde" -d 30 --pesquisa   # vídeo completo + capa + post.txt
python -m torralles_studio prompt-midia "a cup of green tea" -m animar --movimento "pan to the right"
```

A lista completa de comandos está no [`CLAUDE.md`](CLAUDE.md).

## Testes

```bash
python -m unittest discover -s tests -v
```

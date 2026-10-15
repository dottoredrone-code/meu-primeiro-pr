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

# Estúdio IA (fallback entre modelos)

Gera ideias, roteiros, pesquisas, imagens, vozes e vídeos. Cada função tem uma
**cadeia de fallback**: se o modelo preferido não tiver chave, atingir o limite
ou der erro, o próximo da lista assume automaticamente.

| Função | Cadeia (em ordem) |
|---|---|
| ideias | DeepSeek → Gemini → Claude → GPT → OpenRouter (grátis) → Ollama (local) |
| roteiro | DeepSeek → Claude → Gemini → GPT → OpenRouter (grátis) → Ollama (local) |
| pesquisa | Busca (Tavily → Brave) + síntese DeepSeek Reasoner → DeepSeek → Gemini → Claude → … |
| imagem | Nano Banana (Gemini) → FLUX (fal.ai) → GPT Image → Pollinations (grátis) |
| voz | ElevenLabs → OpenAI TTS → Edge TTS (grátis) |
| vídeo | Kling (fal.ai) → Wan (fal.ai) → Ken Burns com FFmpeg (grátis, local) |

As cadeias e os modelos ficam em [`config/fallbacks.toml`](config/fallbacks.toml):
para mudar a ordem ou trocar um modelo, edite esse arquivo, sem tocar no código.

## Como funciona o fallback

- Provedor **sem chave** → pulado.
- **Erro temporário** (429, 5xx, rede) → tenta de novo com espera; persistindo, vai para o próximo.
- **Erro definitivo** (400, resposta inválida) → vai direto para o próximo.
- **Limite (429)** ou **chave inválida (401/403)** → o provedor fica "em descanso" e é evitado nas próximas chamadas.
- Roteiro que não vem em JSON válido conta como falha e passa para o próximo modelo.

## Uso

Requer Python 3.11+ e nenhuma biblioteca extra (FFmpeg opcional, para o vídeo local;
`pip install edge-tts` opcional, para voz grátis).

```bash
cp .env.example .env              # preencha só as chaves que tiver
python -m estudio_ia status       # mostra cada cadeia e o que está pronto
python -m estudio_ia ideias "história do café"
python -m estudio_ia roteiro "história do café" -d 30
python -m estudio_ia pesquisa "origem do café no Brasil"
python -m estudio_ia imagem "coffee farm at sunrise, cinematic" -o saidas/cena1.png
python -m estudio_ia voz "O café chegou ao Brasil em 1727." -o saidas/cena1.mp3
python -m estudio_ia video saidas/cena1.png "slow camera push-in" -o saidas/cena1.mp4
```

## Testes

```bash
python -m unittest discover -s tests -v
```

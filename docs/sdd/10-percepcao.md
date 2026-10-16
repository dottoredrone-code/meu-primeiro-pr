# 10 — Percepção: como a IA assiste e ouve os vídeos

> Status: **nível 1 implementado** (`estudio_ia/percepcao.py`, comando `python -m estudio_ia assistir`); níveis 2–4 especificados.

Sem assistir e ouvir, não há avaliação. A percepção tem quatro níveis, do mais barato ao mais completo,
e o juiz usa todos os disponíveis (fallback, como no resto do Studio).

| Nível | O que faz | Ferramenta | Custo | Situação |
|---|---|---|---|---|
| 1. **Olhos e ouvidos técnicos** | Quadros com tempo marcado (incluindo um logo após cada corte), folha de contato, cortes secos e transições suaves, telas pretas, congelamentos, volume (LUFS), pico, silêncios | FFmpeg local | Grátis | ✅ Implementado e testado |
| 2. **Transcrição** | Fala com marcação de tempo + sons percebidos (música, efeitos) | Gemini (áudio) → Whisper local (`faster-whisper`) | Centavos / grátis | ✅ Implementado; precisa de `GEMINI_API_KEY` ou do Whisper instalado (funciona no PC; bloqueado na nuvem) |
| 3. **Juiz que vê os quadros** | Avalia imagem, legenda, composição e consistência a partir da folha de contato e dos quadros de corte | Modelo com visão (Claude, Gemini, GPT) | ~US$ 0,01 | Especificado (spec 03); usado manualmente nesta sessão |
| 4. **Juiz que assiste o vídeo inteiro** | Recebe o vídeo com áudio e avalia ritmo, narração, música, efeitos e sincronia como um espectador | Gemini (entende vídeo + áudio, aceita também link do YouTube) ou `video_analyze` do Hermes | ~US$ 0,02–0,10 por vídeo curto | Especificado; próximo a implementar |

## Uso
```bash
python -m estudio_ia assistir saidas/video.mp4 -o saidas/percepcao
# gera percepcao.json, folha_contato.jpg e quadros/
```

## Também serve para as referências (spec 09)
O nível 4 com link do YouTube permite analisar os vídeos dos canais de referência **sem baixá-los**,
gerando as métricas e as âncoras para os juízes.

## Calibração aprendida no teste
- Transições suaves (fade, slide) não aparecem na detecção quadro a quadro; foi preciso comparar quadros
  espaçados (2 por segundo, limiar 5). Os cortes secos continuam detectados quadro a quadro (limiar 10).

## Critérios de pronto
- [x] Nível 1 com testes (corte, silêncio, volume, quadros, folha de contato)
- [x] Nível 2 com fallback Gemini → Whisper e motivo explícito quando nenhum está disponível
- [ ] Nível 4: juiz Gemini com vídeo inteiro, resposta JSON na régua da spec 03
- [ ] Juiz combinando níveis 1–4 (spec 01) e relatório de qualidade por peça

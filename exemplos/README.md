# Exemplos

- `demo_torralles_studio_v2.mp4`: demonstração da montagem (imagens desenhadas por código, zoom, transições,
  narração offline Piper, efeitos sintetizados, legendas). Serve de caso de teste para a percepção e os juízes.

Avaliar com percepção completa (precisa de `GEMINI_API_KEY` no ambiente ou no `.env` da raiz, que não vai para o Git):

```bash
python -m estudio_ia assistir exemplos/demo_torralles_studio_v2.mp4 -o saidas/percepcao_demo
```

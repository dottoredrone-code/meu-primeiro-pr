# Montagem final (K22)

Junta as cenas prontas num vídeo para publicar e confere a régua da spec 03 §3.6.

```bash
python -m torralles_studio montar projeto.json -o saidas/final.mp4 --trabalho saidas/trabalho
```

## Arquivo do projeto (`projeto.json`)
Caminhos relativos valem a partir da pasta do JSON.

```json
{
  "proporcao": "9:16",
  "duracao": 30,
  "trilha": "trilha.mp3",
  "bpm": 100,
  "cenas": [
    {"video": "cena1.mp4", "voz": "fala1.wav", "narracao": "Texto falado na cena.",
     "texto_tela": "Frase curta no alto", "duracao": 4}
  ]
}
```
- `video` pode ser um vídeo ou uma imagem (vira cena parada).
- `voz`, `narracao`, `texto_tela`, `trilha` e `bpm` são opcionais.

## O que a montagem faz
| Etapa | Regra |
|---|---|
| Voz | silêncio do começo de cada arquivo é cortado; falas igualadas em −18 LUFS antes da mistura; voz muda numa cena com narração é erro |
| Tempo da cena | fala + 0,2 s antes + 0,35 s depois; cresce no máximo 0,3 s até a duração do roteiro (sem silêncios longos) |
| Duração pedida | se a fala ficar curta, a última cena segura até 1,5 s a mais e as outras ganham até 0,3 s |
| Cortes | caem na batida mais próxima da trilha (até 0,35 s), nunca antes do fim da fala |
| Clipe curto | desacelera até 1,5×; se ainda faltar, segura o último quadro (fica em `congelado_s`) |
| Legendas | até 2 linhas; 28 caracteres por linha no 9:16 (42 no 16:9); numa pausa real da voz, o bloco seguinte entra quando a fala volta e o anterior sai até 0,4 s depois; bloco com menos de 1 s junta com o vizinho; cada bloco fica ≥ 1 s e o bastante para ≤ 17 caracteres/s, se couber |
| Efeitos | legenda acende palavra por palavra no ritmo da fala (`karaoke`); legenda entra e sai suave; título da tela cresce ao entrar; transição de cada cena pelo clima do roteiro (`transicao = "auto"`: curioso desliza, inspirador sobe, alegre abre em círculo, épico dá zoom…) |
| Texto na tela | quebrado em linhas; mais de 2 linhas reprova (encurte o `texto_tela`) |
| Área segura (9:16) | legenda acima dos 20% de baixo; `texto_tela` abaixo dos 10% de cima |
| Trilha | medida e ajustada para 12 LU abaixo da voz (mínimo 10), abaixando quando a voz entra |
| Volume | −14 LUFS e pico −1,5 dBTP (loudnorm em duas passadas) |

A pasta `--trabalho` guarda clipes, `voz.wav`, `trilha.wav`, `legendas.ass` e `legendas.srt` (base da exportação para o CapCut, K23).

## Conferência automática
`verificar_montagem()` mede o arquivo pronto: H.264 + AAC + yuv420p, resolução, duração ±10%, −14 LUFS ±1,
pico ≤ −1 dBTP, legibilidade das legendas, área segura, trilha ≥ 10 LU abaixo da voz e sincronia (cada legenda
começa até 0,3 s de uma entrada real de fala e nenhuma fica mais de 1 s na tela durante silêncio longo). A
sincronia é medida já na montagem; sem essa medida e sem a faixa de voz, a conferência reprova. O comando sai
com código 2 se algum eliminatório falhar.

**Limite conhecido:** dentro de uma mesma fala, a divisão entre blocos de legenda segue as pausas da voz ou a
proporção de letras. A conferência palavra por palavra com transcrição fica para quando houver chave (Gemini)
ou Whisper instalado. A trilha pelo clima (K21) é escolhida no `produzir` (`torralles_studio/trilha.py`); os efeitos sonoros por cena,
também depois.

---
name: "Sin fluidsynth ni ffmpeg"
description: "Sacar las dos dependencias externas del audio si lo que usamos de ellas es poco"
type: refactor
---

Parte de la meta de taro de que el pipeline sean binarios Rust estáticos sin
dependencias (ver la memoria del proyecto). **Poca prioridad**, 2026-09-26: si
lo que usamos de fluidsynth es muy poco, evaluarlo; no tendría sentido
terminar haciendo un port de fluidsynth.

Para qué se usan hoy (`git grep -n 'fluidsynth\|ffmpeg' tools/ pruebas/`):
**fluidsynth** renderiza cada MIDI con el SoundFont a WAV, para las pistas de
MSU-1 (`tools/audio/msu.py`) y como referencia en las mediciones de calidad;
**ffmpeg** decodifica los reemplazos de audio (`.mp3`, `.ogg`, `.flac`) de las
pistas de MSU-1.

Lo que habría que mirar: si `rustysynth` (un sintetizador SF2 en Rust, sin
dependencias) da un render suficientemente parecido al de fluidsynth para las
pistas de MSU-1 —las pistas cambiarían de bytes: se decide escuchando—, y si
`symphonia` (decodificadores en Rust) alcanza para los reemplazos. Y dónde
viviría: probablemente en `gunter`, que ya lee el SoundFont.

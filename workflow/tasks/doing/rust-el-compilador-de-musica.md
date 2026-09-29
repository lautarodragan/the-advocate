---
name: "Rust: el compilador de música"
description: "La cadena de audio del MIDI al stream del S-DSP y el paquete de audio por mapa, en Rust (rm2k-snes-audio), con las ROMs byte por byte iguales; msu y ceilings quedan en Python por ahora"
type: refactor
assignee: Chingolo
---

Tercer paso del camino a Rust de `docs/research/las-herramientas-hoy.md`,
en paralelo con Carancho. Lo decidió Hornero: el audio va por partes, y ésta
es la primera, el compilador de música —`midi`, `music`, `sdsp`, `spc700`,
`snes_music`, `snes_samples`, `brr_samples`, `msu_effects`—. `msu.py` y
`ceilings.py` (las pistas PCM y la medición de techos, que usan fluidsynth y
ffmpeg) quedan en Python para una segunda parte. Los puentes a `gunter`
(`brr_samples`, `snes_samples`) desaparecen: el crate nuevo usa `gunter`
como biblioteca.

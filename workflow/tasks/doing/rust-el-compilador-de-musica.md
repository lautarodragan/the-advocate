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

## Cómo quedó

**El crate es `tools/rm2k-snes-audio/`**, biblioteca y ejecutable, y usa
`gunter` (el SoundFont y el BRR) y `rm2k-project` (el archivo de proyecto)
como bibliotecas por `path`. Para eso Gunter pasó a tener `lib.rs`, y la
extracción de `sf2 --extract` —selector, zona, contrato, PCM— salió de su
`main.rs` a `gunter::extract`; su binario dice lo mismo que antes. Y
`protocol` aprendió `--rust`: `rm2k-snes-audio/src/music_opcodes.rs` sale de
`music.toml` como los otros dos lados, y la receta `protocol` lo chequea.

**El conversor le pasa un pedido y lee lo que escribe.** Arma el pedido
—temas, efectos, paquetes con sus salidas y aparte, herencia, el aire de
medición, las canciones de `System` y lo que va a `musicdata.inc`—, lo deja
en `audio-job.json` al lado del cartucho y corre `rm2k-snes-audio compile`,
que escribe `musicdata.inc`, `musica.json` y `audio.json`. De ahí el
conversor saca lo que le falta: el arranque contra `BOOT_FRAMES` (que sigue
leyendo él de `far_ram.s`) y las versiones de calidad de los efectos para el
`.msu`, que sigue armando él porque lleva también los fondos de batalla.

**La comparación, primera corrida**: `NO_CACHE=1 just cartuchos` en `release`
y `test-special`, contra la foto de `main` mergeado (`fdae002f`): los 991
archivos de `rom/build/` que había salen iguales byte por byte —los `.sfc`,
el `.msu`, los 43 `.pcm`, `musicdata.inc`, `musica.json`, `efectos.json`—, y
aparecen los cuatro nuevos (`audio-job.json` y `audio.json` de cada uno). El
log del conversor tiene las mismas líneas, en otro orden: el informe de temas
y banco lo imprime ahora el ejecutable, antes que las líneas del conversor.

El audio de `release` entero tarda **2,3 s** en Rust, en un hilo y sin caché
en disco.

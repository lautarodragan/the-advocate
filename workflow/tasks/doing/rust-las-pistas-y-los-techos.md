---
name: "Rust: las pistas de MSU-1 y los techos"
description: "La segunda parte del audio: tools/audio/msu.py y ceilings.py a Rust, siguiendo con fluidsynth y ffmpeg por el PATH, con las pistas byte por byte iguales"
type: refactor
assignee: Hocó
---

Segunda parte del audio del camino a Rust. Lo decidió Hornero: `msu.py`
(`rm2k-snes-msu`, las pistas PCM de MSU-1) y `ceilings.py`
(`rm2k-snes-volume-ceilings`, la medición de techos) pasan a Rust, dentro
del crate `rm2k-snes-audio` o al lado. Siguen llamando a `fluidsynth` y a
`ffmpeg` por el PATH: otro sintetizador no daría las pistas byte por byte
iguales, y eso es lo que se verifica.

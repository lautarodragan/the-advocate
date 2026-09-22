---
name: "Ataque y decaimiento"
description: "Las envolventes de cada instrumento, leídas del SoundFont"
---

# Qué

Leer el **ataque y el decaimiento** de cada instrumento del SoundFont, en vez de
sacarlos de las ocho familias de `sdsp.py`.

# Status

Anotado, sin empezar. Pasó de `wishlist/` a tarea el 2026-09-21.

# Por qué

Las ocho familias de `sdsp.py` se eligieron **a ojo, cuando el banco era
sintético**. El SoundFont trae los suyos por instrumento y todavía no se leen.

Y hay un segundo motivo, que es el que lo convirtió en tarea: la SoundFont
reducida de `el-audio-en-dos-pasos-lossy.md` **se va a abrir en un DAW** para
juzgar cómo suena sin armar la ROM. Si las envolventes que usa la ROM no son
las del SoundFont, lo que se oye ahí no es lo que va a salir de la consola,
justo en los ataques —que es donde más se nota—.

**El release no entra acá**, y no por olvido: el del ADSR del DSP no se puede
configurar y la nota se suelta por GAIN, que es un problema resuelto y con su
propia explicación —"Cómo se suelta una nota", en `README.md`—.

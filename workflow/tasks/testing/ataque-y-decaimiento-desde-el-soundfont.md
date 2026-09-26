---
name: "Ataque y decaimiento"
description: "Las envolventes de cada instrumento, leídas del SoundFont"
type: feature
---

# Qué

Leer el **ataque y el decaimiento** de cada instrumento del SoundFont, en vez de
sacarlos de las ocho familias de `sdsp.py`.

# Status

Hecho el 2026-09-25, junto con el release y el aire de la mezcla: es el
punto 2 de `todo/la-calidad-de-la-musica.md`, que tiene los números. Está en
`testing/` porque taro tiene que escucharlo: las grabaciones, en
`/shared/audio/2026-09-25-pasos-1-y-2/` (las `-2-`).

`gunter sf2 --extract --json` devuelve la envolvente de volumen de la zona
—generadores 33 a 40—, y `sdsp.envelope` la traduce a lo que el DSP sabe
hacer. **Pide `just herramientas`** antes de armar.

# Por qué

Las ocho familias de `sdsp.py` se eligieron **a ojo, cuando el banco era
sintético**. El SoundFont trae los suyos por instrumento y todavía no se leen.

Y hay un segundo motivo, que es el que lo convirtió en tarea: la SoundFont
reducida de `el-audio-en-dos-pasos-lossy.md` **se va a abrir en un DAW** para
juzgar cómo suena sin armar la ROM. Si las envolventes que usa la ROM no son
las del SoundFont, lo que se oye ahí no es lo que va a salir de la consola,
justo en los ataques —que es donde más se nota—.

**El release entró también**, aunque cuando se anotó no iba: el mecanismo
sigue siendo el de "Cómo se suelta una nota", en `README.md` —apagar el ADSR
y pedir GAIN—, pero la velocidad del GAIN ahora sale del SoundFont en vez de
la familia, porque con la de la familia el bajo arrastraba 2,4 s de cola
donde el SoundFont pide 30 ms. Ese párrafo del README —"el valor por familia
está en `sdsp.py`"— quedó viejo, y no se tocó porque taro lo está editando.

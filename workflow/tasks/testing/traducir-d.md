---
name: "Traducir las herramientas al inglés, fase 1: el runtime"
description: "Comentarios, docstrings, mensajes y prosa al inglés, sin tocar nombres de código: tools/runtime/, los comentarios de los .s y .inc escritos a mano"
type: refactor
assignee: taro
---

De taro, el 2026-09-29: "traducir las herramientas a inglés". Es la regla de
AGENTS.md para los proyectos aparte, que ahora alcanza a todo `tools/`
(ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`).

**Fase 1**, repartida entre cuatro agentes por área: comentarios, docstrings,
mensajes de error, `help=` y prosa. **Los nombres de código no se tocan** —
módulos, funciones, variables, símbolos del runtime, flags—: eso es la fase
2, de a un área por vez, porque un nombre cambia en todos los que lo
importan. Los términos salen de `tools/GLOSSARY.md`.

Alcance de esta parte: tools/runtime/, los comentarios de los .s y .inc escritos a mano.

## Cómo se hizo

El 2026-09-29, Palmar. Son 93 `.s` escritos a mano y unas 44.000 líneas; los
dos `.inc` de al lado (`event_opcodes.inc`, `music_opcodes.inc`) salen de
`tools/protocol/` y **ya tenían el encabezado en inglés**: no se tocaron.

Se repartió en nueve grupos de unos diez archivos, uno por ayudante, cada uno
en su worktree; cada grupo es un commit. Qué se traduce: todo lo que sigue al
`;`, y el mensaje de los `.assert ..., error, "…"`, que es texto que imprime
`ca65` cuando falla el armado y no un dato. Qué no: nada a la izquierda del
`;`, ni los strings de `.byte`/`.asciiz`, ni los identificadores que los
comentarios citan.

Dos redes por grupo:

* un comparador que saca comentarios y mensajes de `.assert` —respetando
  `"…"` y `'x'`— y exige que el resto sea línea por línea lo de `HEAD`;
* `SIN_CACHE=1 just cartuchos` y el sha256 de los `.sfc`, `.msu` y `.pcm` de
  `rom/build/`, que tienen que salir iguales a los de antes de empezar.

## Qué quedó

Los 93 `.s`, en nueve commits de grupo y uno que alinea los grupos entre
sí: unas 10.700 líneas de comentario reescritas. Los `.sfc`, `.msu` y
`.pcm` de `rom/build/` salieron con el mismo sha256 después de cada commit,
y sobre el árbol mergeado con `main` pasan las dos tandas.

**Lo que quedó en castellano a propósito**, dentro de los comentarios:

* los identificadores, rutas y nombres de Python que se citan: son la fase 2;
* títulos de secciones de archivos que no son del runtime, que se citan
  entre comillas para que se puedan buscar: "Cuánto tarda"
  (`docs/port/msu-datos.md`), "Qué fondos hay" y "El respaldo liviano"
  (`tools/port/escena.py`), "el formato por nota" (`tools/audio/snes_music.py`),
  "lo que depende del actor" (`titulo.py`), y el título de sección de
  `workflow/tasks/done/audio-bgm.md` que cita `paquete_de_audio.s`. **Si la
  fase 1 de esos archivos traduce el título, la cita queda colgando**: hay
  que hacer grep de cada uno;
* una frase de taro citada textual en `nivel.s`, con la traducción al lado;
* el único dato: el `.byte "S-MSU1"` de `msu1.s`.

Lo que no se puede ver con las dos redes es la calidad de la prosa: el
comparador sólo dice que el código no cambió.

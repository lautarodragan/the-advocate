---
name: "Velocidad: colores por tile"
description: "Guardar los colores de cada tile en vez de recalcularlos"
---

# Qué

Guardar los colores de cada tile del primer recorrido en vez de recalcularlos
en el segundo: un diccionario de una línea en la conversión de la capa de
encima.

# Status

Anotado, sin empezar. Apareció midiendo, no buscándolo.

# Por qué

La capa de encima llamaba a `tile_colors` **894.000 veces** —medido el
2026-09-16 sobre `abl` con `SIN_CACHE=1`, un día antes de que Voodoo se hiciera
cargo de convertir esa capa; el recálculo sigue en `snes_convert.py`, del lado
que decide los colores, así que el número hay que volver a medirlo— porque los colores de cada tile se
recalculan en el segundo recorrido en vez de guardarse del primero.

Es una mejora gratis: no cambia ninguna decisión de color, así que la ROM tiene
que salir byte por byte igual. Ése es el criterio de aceptación, y con
`SIN_CACHE=1`, que es donde se mide.

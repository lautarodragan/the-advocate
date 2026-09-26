---
name: "Reducir el README"
description: "taro está reescribiendo README.md a mano para que sea mucho más corto"
type: docs
assignee: taro
---

taro lo está reescribiendo a mano desde el 2026-09-25. **Mientras esté en
`wip/`, nadie más toca `README.md`**: lo que haya que cambiarle se anota acá
abajo y lo resuelve él.

Anotado para él:

* `README.md` enlaza a una sección "El MSU-1" (`#el-msu-1`, en el índice de
  arriba) que no existe, y el docstring de `tools/audio/msu.py` la cita.
* El flag `--inicio` se sacó el 2026-09-25: la línea de `README.md` que lo
  menciona ("sigue existiendo para las recetas") se va.
* El párrafo "Cómo se suelta una nota" (~líneas 851-853) dice que "el valor por familia está en `sdsp.py`": desde el 2026-09-25 las envolventes salen del SoundFont y las familias se fueron.
* "Cómo está armado", en el audio (~líneas 777-785): "en la consola sólo un
  intérprete de un stream de escrituras" ya no es así desde el 2026-09-26 —el
  stream es por nota y el 65816 lo expande a escrituras: ver "el formato por
  nota" en `tools/audio/snes_music.py`—. Lo del driver del SPC700, que espera
  pares (registro, valor), sigue valiendo: el driver no cambió.

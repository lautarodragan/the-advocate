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
* `README.md` dice que el `--inicio TX TY` del conversor "sigue existiendo
  para las recetas": ninguna receta lo usa desde el 2026-09-24 (0ed910d). El
  flag sigue en `snes_convert.py` para la receta de la carrera guardada en
  `workflow/tasks/wishlist/la-carrera-en-release.md`.

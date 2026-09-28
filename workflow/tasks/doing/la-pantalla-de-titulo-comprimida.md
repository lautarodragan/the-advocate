---
name: "La pantalla de título comprimida"
description: "El título ocupa 31,7 KB sin comprimir; en LZ2, por el mismo camino que el Game Over, serían 15,2 KB sin cambiar un pixel"
type: refactor
assignee: Chajá
---

De taro, el 2026-09-28, después de la pantalla de Game Over
(`testing/la-pantalla-de-game-over.md`). Carpincho dejó `pantalla_subir` y
`tools/port/pantalla_completa.py` sin saber qué pantalla suben, para que el
título los use, y midió:

    hoy, sin comprimir                  31.744 B
    LZ2, sin cambiar un pixel           15.241 B   (ahorra 16,5 KB)
    liviana en la ROM + calidad en .msu  2.483 B   (ahorra 29 KB)

taro eligió la segunda: sólo comprimir. La pantalla de título tiene que salir
igual pixel por pixel: la golden `titulo` no cambia.

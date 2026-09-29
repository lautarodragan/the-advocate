---
name: "just video con jugadas"
description: "just video está roto con jugadas desde 991bf935: la fábrica de recorrido de video.py no acepta caso, y sin el mapa de debug talan se traba en el 900"
type: bug
assignee: Ñandubay
---

Lo encontró Irupé el 2026-09-29 (`testing/las-pruebas-sin-agujeros-callados.md`):
desde `991bf935` (2026-09-27), `just video … apertura` da `TypeError`
porque la fábrica de `recorrido` de `rom/pruebas/arnes/video.py` no acepta
`caso`, y `talan` se traba en el mapa 900 porque no elige la página sin el
mapa de debug. `quieto:120` graba bien. taro usa `just video` para pedir
videos de un build.

Se arregla la regresión. Sacar `video.py` de las pruebas —que las jugadas
sean funciones de un módulo de escenarios que llaman las pruebas y el
video— es otra tarea, más grande.

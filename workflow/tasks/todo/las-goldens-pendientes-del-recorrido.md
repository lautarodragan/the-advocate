---
name: "Las goldens pendientes del recorrido"
description: "127 de las 135 fotos del recorrido no tienen golden: sacarlas, que taro las mire, y aprobarlas o arreglar lo que muestren"
type: test
---

Lo midió Irupé el 2026-09-29 (`testing/las-pruebas-sin-agujeros-callados.md`):
de las 135 fotos que sacan las pruebas de recorrido, sólo las 8 de
`apertura/` y `talan/` tenían golden. Las otras 127 están en
`rom/pruebas/golden/playthrough/pendientes.txt`, agrupadas por prueba. Hasta
ahora esas pruebas miraban el estado del juego, pero ningún pixel.

Aprobar una golden es de taro (AGENTS.md, "Cambiar una golden es un acto
deliberado"). Lo que hay que hacer:

- sacar las 127 capturas de un build de `main`, tramo por tramo;
- mostrárselas a taro lado a lado con el original cuando haya captura del
  original, o solas; una golden nueva hornea el bug que tenga, así que se
  miran antes de aprobarlas;
- las que apruebe salen de `pendientes.txt` y entran a git; las que no,
  son una tarea cada una.

Una decisión de taro antes de empezar: las 14 `debug-*` de
`test_mapa_de_debug.py` van sin golden **a propósito** según su docstring.
¿Son pendientes o permanentes? Si son permanentes, conviene que la lista
las distinga, para que no queden como deuda.

---
name: "Los colores de la ventana, en el pedido de Wally"
description: "WINDOW_COLORS es una constante de wally (13 desde la flecha y la barra) y rompió la prueba que compara las capas contra el Python; que venga en el pedido, del System del juego"
type: refactor
agents: [Hornero]
---

`wally::the_layers_are_the_ones_the_python_made` está en rojo en `main`
desde el merge de la flecha y la barra (`60b61b9c`, Tijereta): verde en su
primer padre, rojo en él. La causa es `WINDOW_COLORS` de
`wally/src/background/layers.rs`, que pasó de 8 a 13 —la ventana reserva
esos colores de la paleta 0 en cada mapa—. Comprobado el 2026-10-04: con la
constante en 8, la prueba vuelve a dar exactamente los hashes del Python.

Lo de fondo: cuántos colores se lleva la ventana depende del System del
juego, no del motor. Que llegue en el pedido de `wally` (y de `mapdata`, que
tiene su propio `WINDOW_COLORS`), calculado de una sola fuente; la prueba le
pide 8 y sigue contra el Python, y una prueba nueva fija los 13 de ABL.

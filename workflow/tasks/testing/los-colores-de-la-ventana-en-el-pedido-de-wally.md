---
name: "Los colores de la ventana, en el pedido de Wally"
description: "WINDOW_COLORS es una constante de wally (13 desde la flecha y la barra) y rompió la prueba que compara las capas contra el Python; que venga en el pedido, del System del juego"
type: refactor
agents: [Hornero, Tijereta]
assignee: taro
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

## Hecho (Tijereta)

Worktree de las herramientas desde `c8d5064f`; ABL en el clon
`/extras/scratch/tijereta/abl` desde `c76157d`, rama
`colores-de-la-ventana`.

### De dónde sale el número

`rm2k-snes-screens window` lo cuenta del System: los colores de la ventana
vacía, la flecha, el cursor, el texto y la sombra —`message_window::colors`,
lo mismo que `convert` ya juntaba para armar la paleta, partido en una
`draw` que usan los dos—. Contesta `{"colors": n}`. Con ABL da 13.

El conversor lo pregunta **una vez**, antes de los mapas
(`screens::window_colors`), y lo reparte:

* a cada mapa de `wally`, como `window_colors` en el pedido (`MapRequest`
  y `LayersRequest`); `wally` ya no tiene `WINDOW_COLORS` ni
  `CGRAM_RESERVED`, sino `cgram_reserved(window_colors)`;
* a las pantallas, como `cgram_reserved` = 1 + n, como antes;
* a la emisión, como `window_colors` en el pedido de `emit`;
  `rm2k-snes-mapdata` tampoco tiene la constante: `cgram_reserved(n)` en
  `cgram.rs`. `rm2k-snes-mapdata vram` dejó de publicar `cgram_reserved`
  —no lo leía nadie: el arnés de ABL sólo lee `slots`—.

Las preguntas de `wally` (`bakeable`, `split`) no convierten las capas, así
que el pedido parcial pone `window_colors: 0` y el arnés de ABL no cambia.

### Las pruebas

* `wally::the_layers_are_the_ones_the_python_made` pide 8
  (`PYTHON_WINDOW_COLORS`) y vuelve a verde **sin tocar sus hashes**; las
  de bloques y de los dibujos del mismo archivo, también con 8.
* Las demás de `wally` y las dos de `emit` de `mapdata` llevan 13 en el
  pedido: sus hashes ya eran con 13 y no se movieron.
* La nueva, en ABL: `pruebas/herramientas/test_colores_de_la_ventana.py`
  fija los 13 del System de ABL. Roja con las herramientas globales (no
  existía `window`), verde con las locales.
* `cargo test --workspace` entero en verde: era rojo sólo por la de Python.

### Verificado

* `cargo test --workspace`, entero: verde.
* La tanda de ABL con las herramientas de esta rama: 1095, las 1094 y la
  nueva. `abl.sfc` byte por byte igual, `924c33ea3b51c958…`, armado de
  nuevo con estas herramientas (`release: built` en el log).

No hay nada que jugar: la ROM es la misma.

### Al mergear

Reinstalar en el global `screens`, `mapdata`, `wally` y `convert`, los
cuatro juntos: el conversor le pregunta `window` a las pantallas y les pasa
`window_colors` a `wally` y a la emisión, y uno nuevo con otro viejo se
niega por un campo que falta. Y traer la rama `colores-de-la-ventana` de
`/extras/scratch/tijereta/abl`, con la prueba nueva.

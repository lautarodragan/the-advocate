---
name: "El espaciado entre letras, como perilla"
description: "[text] letter_spacing en el archivo de proyecto: pixeles que se suman al avance de cada letra de una fuente de ancho variable, para que taro compare +0, +1 y +2 jugando"
type: feature
assignee: taro
---

De taro, el 2026-10-03, después de ver el ancho variable: "se puede agregar
una perilla para ajustar el espaciado entre letras, en pixels? … me gustaría
probar en uno o dos… pero si agrega mucha complejidad, lo dejamos para otro
momento". Hoy cada letra ya lleva un pixel de aire adentro de su avance
(`tools/rm2k-snes/text/fonts/README.md`): la perilla suma a eso.

## Hecho (Tordo)

Worktree de las herramientas desde `c69955b4`; ABL en un clon desde
`e660d18`, rama `espaciado`.

### Dónde se lee y dónde se aplica

* **Se lee** al lado de `[text] font`, en `FontChoice::of`
  (`convert/src/font.rs`), con `Project::int_or` —nuevo en `rm2k-project`:
  un entero que puede faltar, sólo para una perilla cuyo "no está" quiere
  decir "como si no existiera"; los demás siguen fallando si falta—.
  Opcional, 0 por omisión; de otro tipo, error.
* **Se aplica** en `Font::with_spacing`, del crate `text`, que suma a cada
  avance —el espacio y los dígitos también, así los números siguen
  encolumnados—. Los glifos no cambian. De ahí sale todo lo que mide: el
  `refit` de las cajas, las pantallas que dibuja `rm2k-snes-screens`, la
  tabla `font_advance` que lleva el cartucho y la ventana con que el
  compilador de eventos rearma las páginas de tropa.
* **Viaja** a `rm2k-snes-screens` como `letter_spacing` en sus pedidos
  `boxes` y `convert`, al lado de `font`; sin la clave es 0.
* **El rango**, con el porqué en el error: de 0 a 3 (`SPACING_MAX`, el
  número de taro); negativo, no, porque el aire de cada letra es donde cae
  su sombra. Y **ninguna letra puede quedar avanzando más de una celda**
  (`SPACED_ADVANCE_MAX`, 8): la pelea revisa sus renglones de victoria
  contando letras, una por celda, sin saber la fuente. Con `low-variable`,
  cuyas más anchas (`#`, `M`, `W`, `m`) avanzan 6, **el tope real es 2**.
* **Con `rm2k` aplica igual**: es una fuente más, de avance fijo, y sigue
  fija (6 + lo que se sume). No hay caso especial que avisar.

### Avances escritos a mano en la ROM: ninguno

Revisados `messages.s` (el compositor de la ventana), `text_layer.s` (el
ajuste a celdas, `tl_right` con los dígitos, `TL_FIGURE`, el texto
compuesto, `tl_strip`), `battle.s` (`ba_fit`) y `battle_troop.s`: todos
leen `font_advance`, también los dígitos y el espacio. Lo único que da algo
por sentado es el final de `tl_strip`, `(TL_X + 6) >> 3`: supone que la
tinta y la sombra de la última letra terminan antes de su avance, que con
más espaciado se cumple con más razón; a lo sumo cuenta una columna de
más, y el conversor (`strip_tiles`) cuenta igual.

### Qué deja de entrar

Medido con `rm2k-snes-screens boxes` sobre las cajas de los mapas (240 px,
4 renglones) y con el conversor armando `release`:

    espaciado   cajas rearmadas   partidas   cajas de más   banco del menú
    +0          1                 0          0              314 tiles; los nombres piden 78 de 134
    +1          154               37         37             355 tiles; piden 94 de 92   NO ENTRA
    +2          1736              447        457            368 tiles; piden 106 de 80  NO ENTRA

* **El banco del menú es lo que se rompe**, y el conversor se niega a
  armar: con +1 por 2 tiles, con +2 por 26. Crecen las dos cosas a la vez:
  lo horneado del banco (encabezados, "File N", comandos, términos) pierde
  tiles repetidos porque las letras caen en otras fases, y los nombres
  compuestos piden más (el peor caso: los cuatro nombres más largos y la
  medicina más larga a la vez). El banco termina en el tilemap
  (`SLOT_MAP`), y en la ROM `tl_strip` no tiene tope: pasado eso pisa el
  tilemap. Arreglarlo es mover `SLOT_MAP` —todas las disposiciones dejan
  libre el BG1 hasta `$4C00`— o componer también lo horneado: no se hizo.
* Las cajas: los mensajes pasan de 3351 a 3377 cajas con +1 y a 3625 con
  +2 en el conversor (que cuenta también las de las páginas de tropa).
* Nombres, contra el tope de celdas de cada lugar (cuenta a mano con los
  avances de la hoja, no corrida en la ROM): los ítems entran en la lista y
  en el equipo con +2; de los 13 actores del cartucho, "Gang Member" deja
  de entrar en la ranura (7 celdas) con +1; de las 367 habilidades con
  nombre, en la pelea (11 celdas) no entran 6 con +0, 38 con +1 y 91 con
  +2 ("Electric Shock", "Paralysis Pollen", "Mist of Silence"…).
* La tienda y la pelea: el conversor no dice nada. El pozo de pares de
  `text_layer.s` no lo cuenta el conversor; la ROM, cuando se le acaba,
  cambia de juego antes (`TL_FLUSH`).

### Verificado

* Con 0 —y sin la clave—, `abl.sfc` sale byte por byte igual:
  `37dde95f59acb79eb6bc432aaa32128b9afbf2bb3179b2f2c5569cae5ec1ae08`.
* La tanda de ABL con las herramientas de la rama (`convert` y `screens`
  en local) y la clave en 0: 1045 en verde.
* `cargo test` de `text`, `project`, `screens` y `convert`, y
  `just -f tools/justfile test`.
* Lo que **ninguna prueba cubre**: la ROM con espaciado mayor que 0. La
  tanda corrida contra la +1 y la +2 da 105 y 108 en rojo, y lo mirado son
  goldens que cambian sólo letras y las `_dibujo`, que le piden la pantalla
  a `rm2k-snes-screens` sin `letter_spacing` y por eso esperan +0. Las dos
  ROMs se armaron con el chequeo del banco del menú apagado (ver abajo).

## Para taro

Las tres ROMs en `/shared/builds/espaciado/` (`abl-espaciado-0.sfc`, `-1`,
`-2`) con su `LEEME.txt`, y las capturas lado a lado en
`/shared/capturas/2026-10-03-espaciado/`. **La +1 y la +2 se armaron con el
chequeo del banco del menú apagado** —un `screens` local, sin commitear—:
con el grupo de siempre no debería pasar nada, pero si el menú se ve con
basura, es eso.

Si queda una, el banco del menú hay que arreglarlo antes de ponerla en
`rm2k-snes.toml`.

Ramas: herramientas, `worktree-agent-abceeff6ccfffd250`; ABL, `espaciado`
del clon `/extras/scratch/tordo/abl` (`e700650`): sólo la perilla con su
comentario, en 0.
Al mergear, reinstalar `convert` y `screens`, que cambian de
comportamiento; y como se tocó `project` —se agregó `int_or`, que sólo usa
`convert`—, la regla de `tools/justfile` pide reinstalar todo.

---
name: "Rust: el dominio de las pantallas"
description: "Los menús, el título, la tienda, la ventana de mensajes y el reparto de textos del conversor (menus, screens, texts, font, message_window, end_game, title) a un crate de dominio en Rust, con las ROMs byte por byte iguales"
type: refactor
assignee: Tataupá
---

De taro, el 2026-09-30, en la migración del conversor a Rust: el dominio de
las pantallas, que ya usa `rm2k-render` para las caras y el System. Es un
crate de dominio en `tools/rm2k-snes/`, con la forma de
`tools/rm2k-snes/battle/README.md` ("One stage of a converter"), como hizo
Mara con los mapas.

Sale de `main` en `52156e5b`. Base medida ahí, con `cartridge` instalado en
el `bin/` local —la huella lo va a necesitar, y el `.dbg` cambia según qué
ensamblador arma; ver la trampa que anotó Mara—: `NO_CACHE=1 just
cartuchos`, 1032 archivos en `rom/build/` (sin el caché, los `.o`,
`sello.txt` ni `conversor.log`; los PNG decodificados), sus sha256 en
`<scratchpad>/tataupa/sha-base.txt`.

## Inventario: qué hace hoy el Python

Leído el 2026-09-30:

| módulo | qué hace | de qué dominio es |
|---|---|---|
| `font.py` | las dos fuentes de 6x12 de easyrpg (ttyp0 y rmg2000), generadas de sus `bitmapfont_*.h`, y cuál pide el `font_id` del System | la fuente |
| `window.py` | el System del juego (`skin`, que busca el PNG y recuerda lo que dibujó `rm2k-render system`), y `draw_line`/`page`: una línea de texto con su sombra sobre los bloques de color del System, como `Font::Render` | la fuente; `skin` lo usa también `map_convert` para el cronómetro |
| `texts.py` | `refit`: reparte una caja de `ShowMessage` al ancho de la ventana de la consola (TeX en miniatura, con costos a gusto de taro), y `refit_commands`, que lo aplica a una lista de comandos | los textos; lo usan `compiler.boxes` —la tabla de cajas que recibe `rm2k-snes-events`— y `lcf.REFIT_TEXTS`, con que el Python lee las páginas |
| `message_window.py` | la ventana de mensajes como la lleva la ROM: los tiles de la ventana vacía, su paleta, sus celdas, los 240 tiles del área de texto, el color de cada fila del glifo y el de la sombra (`convert_window`); la fuente invertida (`font_bytes`) y las cuatro tablas precompuestas por fase (`font_prerender`) | la ventana; sus constantes (`WINDOW_*`, `FONT_*`) las emite `mapdata` |
| `title.py` | el menú del título en BG2 a 4bpp (`menu`: tiles, paleta, un tilemap por opción) y el dibujo del título entero para las pruebas (`render`) | el título; la imagen de fondo la convierte `palette.convert` + `fullscreen`, que usan también el Game Over, las imágenes, las animaciones y los fondos de pelea |
| `menus.py` | el banco de las ranuras y del menú de pausa (`slots_screen`: textos pre-dibujados, glifos, caras con su paleta —Adeleine si pasan de quince colores, y prestada si no quedan paletas—), el banco de la fuente de las pantallas de texto (`items_screen`, cuatro colores), los marcos del System en BG1 de ítems, equipo, tienda y elección de actor (`borders`, `*_layers`, `compact_target`), las reglas de texto de esas pantallas (`item_text`, `split_description`, `name_text`, `level_text`, `max_text`, `name_in_lines`, `digits_of`) y los dibujos para las pruebas (`render_menu`, `render_items`, `render_target`, `render_slots`) | las pantallas; la geometría y las reglas de texto las lee también `mapdata` al emitir |
| `screens.py` | el equipo y la tienda: la geometría (`EQ_*`, `TI_*`), sus ventanas y barras, lo que cada una escribe (`equipment_screen`, `shop_screen`, sobre una `TextGrid`) y lo que hace (`equip`, `candidates`, `can_buy`), `compact_shop`; y **la pantalla de texto de la pelea** (`BA_*`, `victory_lines`, `command_text`, las líneas de la victoria) | el equipo y la tienda son de las pantallas; lo de la pelea no: ver la frontera |
| `end_game.py` | `Scene_End`: el dibujo a 320x240 o 256x224 (`draw`), la pantalla como la sube la ROM —un índice por par de colores, dos paletas— (`convert`), la rampa del fundido y su dibujo para las pruebas (`render`) | las pantallas |

Y lo que usan de afuera: `rm2k-render` (`system`, `face`) por
`render/render_map.draw`, `port/adeleine.py` (`merge_least_visible`,
`luma_distance`), `port/experience.py` y `port/rules.py` (`level_of`,
`param_of`, `equipped_params`, `initial_level`, `next_exp`), `port/palette.py`
(`BLACK`, y `convert` en el título), `port/snes_format.py` (`pack_tile`,
`cgram_word`), `port/map_layers.py` (`CGRAM_RESERVED`), `port/constants.py`
(`COLUMNS`, `LINES`, la pantalla, `MENU_CGRAM`), `port/events.py`
(`escape_tail`, `CannotCompile`, los códigos de `ShowMessage`, `ITEM_MAX`),
`rpgmaker/lcf.py` (la base, los términos) y Pillow y numpy.

Quién lo llama: `snes_convert.py` —una vez por cartucho: la ventana, las
ranuras y el menú, los cuatro marcos, End Game, el menú del título—,
`mapdata.py` —la emisión: geometría, reglas de texto, `compact_*`,
`end_game.ramp`—, `vram.py` —los cuatro chequeos de dónde caen las
pantallas—, `compiler.py` —`texts.refit`—, y las pruebas de ABL que dibujan
con el modelo de Python: `render_menu`, `render_items`, `render_target`,
`render_slots`, `equipment_screen`, `shop_screen`, `end_game.render`, y las
de los textos (`test_textos_del_juego`, `tools/tests/test_texts.py`).

## La frontera

**Lo que el dominio recibe del orquestador** —decisiones del cartucho,
nunca datos que el volcado ya tiene—:

* qué actores pueden estar en el grupo (`possible_members`) y qué ítems
  conoce la ROM (`possible_items`): son del cartucho;
* cuántas ranuras de guardado hay, y si el cartucho lleva título;
* los repartos de VRAM, como datos: dónde empieza cada banco del BG1 de
  cada reparto (`vram.LAYOUTS`), y `SLOT_VRAM` y `SLOT_MAP`. Mara dejó los
  repartos en Python porque los leen también la emisión y los mapas; los
  chequeos de dónde caen las pantallas (`_check_slots`,
  `_check_items_border`, `_check_target`, `_check_shop`) son de este
  dominio, y se mudan con él;
* el ancho de la ventana de mensajes (`constants.COLUMNS`, `LINES`), que
  hoy recibe también `rm2k-snes-events`.

**Lo que lee del juego él mismo**, con la biblioteca de Ditto: los
términos, los actores, los ítems y el System de la base —la fuente, el
estirado, el título—, y el PNG del System, las caras y el título de la
carpeta del juego.

**Lo que devuelve**, que hoy leen `snes_convert` y `mapdata`:

* la ventana de mensajes: tiles, paleta, celdas, fondo del texto, colores
  de fila y sombra, la fuente y sus cuatro tablas precompuestas;
* el menú del título: tiles, paleta y un tilemap por opción;
* el banco de las ranuras y el menú: tiles, paletas, cabeceras, filas,
  caras, y los bloques del menú con sus glifos;
* el banco de la fuente de las pantallas de texto, con sus cuatro paletas y
  sus glifos;
* los marcos de ítems y equipo, de la tienda y de la elección de actor,
  **ya compactados** como los guarda la ROM (`compact_target`,
  `compact_shop` se mudan con ellos);
* End Game: tiles, tilemap, fila, las dos paletas y la rampa;
* los textos de las pantallas que la ROM compone —las tiras de cada actor,
  los nombres de las medicinas en dos líneas, los mensajes de la tienda en
  líneas—, y **la geometría** con que dibujó, para que la emisión no tenga
  una segunda copia de cada número;
* la tabla de cajas repartidas, que va al pedido de `rm2k-snes-events` y a
  `lcf.REFIT_TEXTS`.

**Lo que es de otro dominio y se queda afuera:**

* **la emisión** —`mapdata`—: el dominio devuelve datos y la emisión los
  escribe. El `item_texts` que arma `mapdata` mezcla los textos de las
  pantallas con los de la pelea, y es de la emisión;
* **la pantalla de texto de la pelea** (`screens.BA_*`, `victory_lines`,
  `command_text`, `revived_text`, las líneas de la victoria): no dibuja
  nada al convertir; es geometría y textos que emite `mapdata` y que la ROM
  compone con la fuente de las pantallas. Es de la pelea, y se queda en
  Python con ella;
* **el reparto de VRAM** (`vram.py`): de los mapas y la emisión; acá llega
  como datos;
* **la imagen del título y el Game Over** (`palette.convert`,
  `fullscreen.compressed`): los usan también las imágenes, las animaciones
  y los fondos de pelea, y el escalado es el `LANCZOS` de Pillow. El
  dominio hace el menú del título; la imagen de fondo sigue en Python;
* **qué compila y cómo se parte en cajas lo que compila**: del compilador.
  Acá se decide cómo se reparte una caja al ancho de la ventana; la regla
  de la cola de escapes (`\|`, `\^`) es del compilador, y el reparto
  necesita conocerla: es la misma regla, con las mismas pruebas
  (`rm2k-snes/events/tests/escapes.json`), como hoy entre `events.py` y el
  crate;
* **las reglas de RM2k** —el nivel, los parámetros, la curva de
  experiencia—: de `rm2k-rules`; **qué colores se pierden** en una cara: de
  Adeleine; **qué es cada pieza del System y cómo se arma una ventana**: de
  `rm2k-render`. Los tres como bibliotecas.

## Un crate o varios

Dos, para que Cargo haga cumplir lo que hoy sólo cumple el orden de los
imports:

* `rm2k-snes/text/` (`rm2k-snes-text`, biblioteca): la fuente, una línea de
  texto dibujada sobre el System, y el reparto de las cajas al ancho de la
  ventana. No sabe que existen los menús: lo usan las pantallas y podría
  usarlo el compilador.
* `rm2k-snes/screens/` (`rm2k-snes-screens`, la etapa): lee el juego, y
  hace la ventana de mensajes, el título, las ranuras y el menú, las
  pantallas de texto con sus marcos, End Game, los dibujos para las pruebas
  y la tabla de cajas. Depende del de arriba, de `rm2k-render`,
  `rm2k-rules`, `adeleine` y `ditto`.

## El plan

Por partes, cada una en su commit, con las ROMs iguales:

1. **La fuente y los textos**: `rm2k-snes-text`, y la tabla de cajas por la
   etapa.
2. **La ventana de mensajes y el título.**
3. **Las ranuras, el menú, la fuente de las pantallas, los marcos y End
   Game**: `snes_convert` llama a la etapa una vez.
4. **La geometría y los textos que la emisión lee**, publicados por la
   etapa.
5. **Los dibujos de las pruebas**, pedidos a la etapa.
6. Borrar el Python que ya no use nadie, y la prosa.

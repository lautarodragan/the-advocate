---
name: "Rust: el dominio de las pantallas"
description: "Los menús, el título, la tienda, la ventana de mensajes y el reparto de textos del conversor (menus, screens, texts, font, message_window, end_game, title) a un crate de dominio en Rust, con las ROMs byte por byte iguales"
type: refactor
assignee: taro
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

## Hecho

**Todo el dominio de las pantallas está en Rust**, en dos crates, y el
Python que lo hacía se borró. Las tres ROMs, los `.sym`, los `.inc` y todo
`rom/build/` salen byte por byte iguales a los de `main` con el Python; la
única diferencia es de la prosa del último commit: un comentario del
`.inc` y el tamaño de los fuentes del runtime que nombran los `.dbg`, ver
abajo.

| commit | qué |
|---|---|
| `40963731` | la tarea: inventario y frontera |
| `1083d4c7` | merge de `main` (`248c0134`, los parches de Yacutoro) |
| `2b017b2e` | `rm2k-snes-text` y la etapa `rm2k-snes-screens`; `snes_convert` la llama una vez, y `compiler.boxes` y `lcf.REFIT_TEXTS` le piden las cajas |
| `7ef985d1` | la emisión lee la geometría y los textos de la etapa; la pantalla de texto de la pelea, a `battle_screen.py` |
| `ea8eb3c3` | las pruebas de ABL piden los dibujos a la etapa (`pruebas/arnes/pantallas.py`) |
| `44cae8e1` | las pruebas de los dos crates contra los hashes del Python, con su juego chico |
| `04e31c5e` | el borrado, sólo borrado |
| `d431b9e3` | `luma_distance` de adeleine.py, que quedó sin uso |
| `eab433fa` | la prosa que nombraba lo borrado |

El plan se hizo en menos commits que las seis partes: la conversión entera
en uno, porque las piezas comparten el System, el banco y la fuente, y
partirla dejaba commits intermedios con las dos mitades a la vez.

**Los crates** (`wc -l` de `src/`, sin las pruebas):

* `rm2k-snes/text/` (`rm2k-snes-text`, biblioteca, ~990 líneas):
  `glyphs.rs` (las dos fuentes, generado de easyrpg), `font.rs`,
  `line.rs` (una línea sobre los bloques del System, `Font::Render`) y
  `refit.rs` (el reparto de las cajas, con su copia de la cola de
  escapes). Depende de `rm2k-render`.
* `rm2k-snes/screens/` (`rm2k-snes-screens`, la etapa, ~4550 líneas):
  `game.rs` (el volcado y el System), `cells.rs` (cortar una pantalla
  dibujada en celdas, bancos y paletas), `layout.rs` (la geometría, y
  `publish`), `texts.rs`, `message_window.rs`, `title.rs`, `slots.rs` (el
  banco de las ranuras y el menú, con las caras), `items.rs` (la fuente de
  las pantallas de texto), `borders.rs` (los marcos y sus compactados),
  `end_game.rs`, `checks.rs` (dónde caen en la VRAM), `boxes.rs`,
  `convert.rs`, `render.rs` (los dibujos de las pruebas, con las reglas
  del equipo y la tienda), `request.rs`, `main.rs`. Depende de
  `rm2k-snes-text`, `rm2k-render`, `rm2k-rules`, `adeleine`, `voodoo` y
  `ditto`. Su README dice los subcomandos, el pedido y lo que escribe.

Subcomandos: `convert` —el del conversor, uno por cartucho—, `boxes` —la
tabla de cajas, para `compiler.boxes` y `lcf.REFIT_TEXTS`—, `render` —las
pantallas para las pruebas de ABL—, `refit` —rearmar cajas sueltas, para
`test_textos_del_juego`— y `layout`.

Del lado de Python quedan `port/screen_stage.py` (el pedido y la forma de
la respuesta que `mapdata` emite), `port/battle_screen.py` (la pantalla de
texto de la pelea, movida tal cual de screens.py) y `window.py` reducido al
System y el cronómetro, que son de los mapas.

**Lo que cambió de la frontera planeada:**

* **La lista de ítems no es una sola.** La emisión escribe los textos de
  `items_rom` más lo que sueltan los enemigos (`drop_items`), y el banco
  del menú lleva las letras de las medicinas de `items_rom` solo. El
  pedido lleva las dos (`items` y `bank_items`), y la larga se arma antes
  de llamar a la etapa. Ver "Lo que falta".
* **La geometría la publica la etapa** (`layout.rs`, `publish`), y
  `mapdata` la lee por los mismos nombres (`screen_stage.layout()`): no
  quedó una segunda copia de ningún número de las pantallas. Las pruebas
  de ABL la piden igual (`pantallas.disposicion()`).
* **`compact_target`, `compact_shop` y `font_prerender` se mudaron a la
  etapa**, que devuelve lo que guarda la ROM.
* **La cola de escapes quedó en Rust dos veces**: en el compilador y en
  `rm2k-snes-text`, con los mismos casos (`escapes.json`); la de Python
  se fue con `texts.py`.
* **`equip`** —`Game_Actor::ChangeEquipment`— quedó en dos lados: en
  `render.rs`, para dibujar la lista, y en `pruebas/arnes/pantallas.py`,
  para que la prueba sepa qué esperar de la RAM.
* **La imagen del título** siguió en Python (`palette.convert` y
  `fullscreen`), como estaba planeado; el menú encima es de la etapa.
* **Los colores del cronómetro** siguen saliendo de `window.py`: son de los
  mapas (ya lo anotó Mara).

## Cómo se verificó

Con scripts descartables en `<scratchpad>/tataupa/`:

* **Pieza por pieza, Python contra Rust** (`compara_convert.py`): un
  conversor que corre el Python de siempre y compara cada pieza contra
  `rm2k-snes-screens` con las mismas entradas —la ventana, la fuente y sus
  cuatro tablas, el menú del título, el banco de las ranuras y el menú con
  las caras (cinco prestadas en `release`), la fuente de las pantallas, los
  tres marcos y sus compactados, End Game, los textos, cada número de la
  geometría contra su constante de Python y las 1245 cajas del juego—:
  todo igual en `release`, `test-special` y `test-encounter-every-step`.
* **Los dibujos** (`compara_render.py`): 297 pantallas del modelo de Python
  contra `render`, a ocho bits —el menú con cuatro grupos, cada cursor y
  los dos permisos, con HP, niveles y experiencia; la elección de actor
  con y sin medicina; los ítems con la lista corrida; las ranuras en los
  dos modos con partidas; el equipo en cada ranura y fila; la tienda en
  sus siete modos, tres tipos y tres juegos de mensajes, con los errores
  en los mismos casos; End Game—: todas iguales.
* **Los cartuchos**: `NO_CACHE=1 just cartuchos` y el sha256 de todo
  `rom/build/` —menos el caché, los `.o`, `sello.txt` y `conversor.log`;
  el `.dbg` sin `mtime`; los PNG decodificados—: 1032 archivos, iguales a
  los de `main` (`248c0134`, con el Python) después de cada commit hasta
  el borrado; lo que imprime el conversor, igual línea por línea. Después
  de la prosa, iguales salvo los tres `mapdata.inc` —puesto el comentario
  viejo, el mismo sha256— y los tres `.dbg` —puestos los tamaños viejos de
  los fuentes, el mismo sha256—.
* **Los sha256 de las ROMs**, iguales en `main` y acá:
  * `release/abl.sfc` `cdcc323197ee6c66d82b1304ce20c3c37f4124d13a6867e851fd13226046b7df`
  * `tests/special/prueba.sfc` `15e4f331fe8ff8123803ae3819a2212a5b84d71cd0a053b7261a9188bbab84b9`
  * `tests/encounter-every-step/prueba.sfc` `dc83ed698b348032514dbb76eaf5f535b6296944075fcba786087533ed5b8a4b`
* **Las tandas**: `just pruebas`, 878 —las mismas que `main`—;
  `just -f tools/justfile test`, 49 —eran 85: las 36 de `test_texts.py` y
  `test_escapes.py` pasaron a `rm2k-snes-text`—; `cargo test` de `text`,
  `screens`, `events` y `cartridge`, en verde.
* **Las pruebas de los crates no dependen de ABL**: `rm2k-snes-screens`
  compara contra los sha256 de lo que daba el Python sobre un juego chico
  que vive en `tests/game/` —la respuesta entera de `convert`, diecinueve
  pantallas y la tabla de cajas—, y `rm2k-snes-text` sobre trescientos
  cuadros que arma una congruencia y una línea en las dos fuentes; más las
  reglas del reparto una por una, que eran `test_texts.py`. Los hizo
  `referencia.py`, antes de borrar.
* `cargo test --workspace` (`just -f tools/justfile rust-test`) da rojo en
  tres pruebas de **Adeleine**, que no se tocó: comparan el JSON que
  escribe como texto, y con todo el workspace junto `serde_json` sale con
  `preserve_order` —lo prende `rm2k-snes-audio`— y las claves cambian de
  orden. Está así en `main`: las dos cosas son del 2026-09-29. Las pruebas
  de `rm2k-snes-screens` comparan la respuesta ordenando las claves, y
  pasan con y sin.

## Al mergear

* Instalar en el global `screens` —el binario nuevo— y `cartridge` —la
  huella de los cartuchos lo nombra—: `just -f tools/justfile install
  screens cartridge`. `text` es biblioteca. Sin `rm2k-snes-screens` en el
  PATH el conversor para y dice cómo instalarlo, y las pruebas de las
  pantallas también.
* No mueve goldens ni la ROM.

## Lo que falta

* **Las letras de las medicinas que sólo sueltan los enemigos no van al
  banco del menú.** Es lo que hacía el Python —`medicine_letters` salía de
  `items_rom`, antes de sumar `drop_items`— y se conservó para que la ROM
  saliera igual, pero la elección de actor escribe el nombre de cualquier
  medicina de la lista larga con esos glifos: una que sólo se consigue
  peleando y tiene una letra que nadie más usa se vería con un hueco. No
  se averiguó si es a propósito: `git log -S` llega sólo hasta la
  traducción. Arreglarlo es pasar la misma lista en los dos campos, y
  mueve la ROM.
* **`equip` está dos veces**, en la etapa y en el arnés de las pruebas.
* **La cola de escapes está dos veces en Rust**: el compilador podría usar
  la de `rm2k-snes-text`, que es la biblioteca de abajo.
* **`lcf.REFIT_TEXTS` busca en la tabla del juego que se convierte**
  (`resources.GAME_DIR`): Python sólo lee de las cajas cuántos comandos
  son, pero si un día lee otro juego sin convertirlo, lo lee sin rearmar.
* **La imagen del título y la de Game Over** siguen en Python
  (`palette.convert`, el `LANCZOS` de Pillow): son de las pantallas
  completas, junto con las imágenes y los fondos de pelea.
* El rojo de Adeleine en `rust-test`, de arriba.

---
name: "Las responsabilidades de snes_convert.py"
description: "Un archivo de ~8.200 líneas y ~140 funciones: repasar qué hace y partirlo por responsabilidad"
type: refactor
assignee: Ñacurutú
---

`tools/port/snes_convert.py` es enorme (cuántas líneas y funciones: `wc -l` y
`grep -c '^def '`). taro quiere repasar sus responsabilidades, el
2026-09-26, sin urgencia.

Primero un inventario: qué partes tiene (la conversión de mapas, gráficos,
paletas, eventos, audio, el reparto de la VRAM, la escritura de los `.inc`,
los casos de prueba, la línea de comandos, …), cuáles ya tienen su módulo
(`eventos.py`, `escena.py`, `asignador.py`, `batalla.py`, `tools/audio/`) y
qué quedó en el archivo grande que es de otra cosa. Después, una propuesta de
partición con el criterio del corte de `main.s`: primero lo mecánico (mover
sin cambiar), verificado con los cartuchos byte por byte iguales, y después
lo de criterio.

**Va después de la optimización de tiempo del conversor** (en curso el
2026-09-26), que no tiene que refactorizar nada para no mezclar las dos
cosas.

Relacionado: taro quiere que todas las herramientas terminen en Rust, no por
velocidad; cuando se encare eso se decide qué partes tienen sentido.

El inventario por secciones, con rangos de líneas y qué es motor y qué es
herramienta de RM2k, está en
`docs/research/el-mapa-de-las-herramientas-de-python.md` (§2), con una foto
del 2026-09-28.

## Tomada el 2026-09-29

Para el paso 4 del camino a Rust (`docs/research/las-herramientas-hoy.md`):
el conversor se migra por partes, y antes hay que partirlo. La optimización
de tiempo que la frenaba ya pasó. El archivo se sigue llamando
`tools/port/snes_convert.py`, pero ahora está en inglés y usa `rm2k-render`
y `rm2k-snes-audio` por el PATH.

## El inventario

Sobre `d4811ece`: 9.680 líneas y 135 funciones de nivel superior. Las
dependencias salen de un script de AST que mira, para cada función o
constante, a qué otros nombres del archivo se refiere; se tiró. Los rangos
son de ese commit.

| líneas | parte | qué hace | depende de | quién la usa |
|---|---|---|---|---|
| 1-101 | imports y ganchos | le pone a `lcf` `DECORATE_TRANSLUCENT` y `REFIT_TEXTS` **al importarse** | — | todo el proceso, y cualquier prueba que importe `snes_convert` |
| 102-386 | las capas del fondo, 1 | el reparto de la CGRAM entre el fondo de 8 bpp y la capa de encima de 4 bpp, la cuantización a 15 bits, la capa de encima como PNG indexado | `allocator`, `tiles_bin` | `_convert_layers`, `convert_window`, `emit` (constantes) |
| 387-723 | el personaje como sprite | colores, poses, paleta de cada CharSet, qué poses muestra cada gráfico en el mapa, el peso para el reparto | `allocator`, `rm2k`, `settings` | `drawable_npcs`, `build_characters`, `convert_map`, `emit` |
| 724-940 | eventos horneados | qué eventos opacos se pintan en la capa de encima, y sólo si no mueven la CGRAM | las capas convertidas, `render_map`, `events` | `convert_map`, `_map_layers`, `test_horneados` |
| 941-1338 | NPCs dibujables y banco de sprites | qué NPCs entran en las ocho paletas de OBJ y el banco de poses de la VRAM | lo del personaje | `convert_map`, pruebas del cronómetro y del destello |
| 1339-1716 | los extras del banco de sprites | cronómetro, lluvia, la imagen de `ShowPicture`, el recuadro de animación de pelea, y cuántas paletas quedan; `npc_table`, `maps_per_character` y `has_rain` quedaron acá por vecindad | lo del personaje, `picture`, `animation` | `convert_map`, `main` |
| 1718-2121 | las capas del fondo, 2 | la paleta, la conversión de las dos capas con Voodoo, y el caché en disco y en paralelo de las capas | lo de 102-386, `render_map`, `tiles_bin`, `disk_cache` | `convert_map`, `main` (`precompute_layers`) |
| 2123-2612 | la ventana del tilemap y los repartos de VRAM | los seis repartos, las ranuras de partida, y los controles de que cada pantalla cae donde la ROM supone | `menus`, `screens` | `convert_map`, `main`, `emit`, `test_vram_layouts` |
| 2613-2812 | la ventana de mensajes y la fuente | tiles, paleta y celdas de la ventana, la fuente y su prerender por fase | `window`, `font`, `constants` | `main`, `emit` |
| 2814-3088 | los bloques de 16x16 | el mapa como índices a bloques con pasabilidad, y `TileSubstitution` traducido a bloques | `rm2k`, `events` | `convert_map`, `main`, `test_substitutions` |
| 3089-3340 | el registro de cada mapa | los campos del registro de 128 bytes, sus desplazamientos, y la tabla de mapas | los tamaños de NPC, eventos y terreno | `emit`, `main` |
| 3341-3417 | las animaciones del ChipSet | las corridas de agua y de las familias animadas, por mapa | `FAMILIES` | `convert_map`, `emit` |
| 3418-3572 | las animaciones de pelea | qué animaciones pide el bytecode, y sus cuadros como los guarda el cartucho | `animation`, `events` | `main`, `emit`, `test_animacion_cuadros` |
| 3573-3654 | la experiencia | las tablas de experiencia por actor | `experience`, `lcf` | `emit` |
| 3655-4069 | los fondos y los battlers | cuáles lleva el cartucho, quién los pide, y su emisión con los fondos livianos | `scene`, `events` | `main`, `emit`, `test_msu_datos` |
| 4070-4100 | `block` | la primitiva de emisión: un bloque `.byte` con su `.block` o `.align` | — | casi todos los que emiten |
| 4101-4246 | la tabla de páginas | las páginas de eventos de un mapa, con el puntero a su código | `events` | `map_data`, `test_paginas` |
| 4247-4500 | el material y la compresión | los bloques con identidad propia (`Materials`), qué va comprimido, en cuántos flujos, los topes de la WRAM, y los crudos | `compress` (el `lz2` del PATH) | `emit`, `main`, `test_lz2` |
| 4501-4633 | los datos de cada mapa, encuentros, identidad | los bloques de un mapa, los encuentros aleatorios, el título de la cabecera | lo de NPCs y páginas, `settings` | `emit`, `main` |
| 4634-6868 | **`emit()`** | el `mapdata.inc` entero, en una función de 2.234 líneas | casi todo lo de arriba | `main` |
| 6869-7288 | tablas de NPC y eventos | tamaños de NPC y eventos, el orden de dibujo, el orden de mapas, qué eventos se mueven, la firma de la partida, el seno, las tablas de NPC y de actores | `events`, `rm2k` | `emit`, `convert_map`, `main` |
| 7289-7396 | la línea de comandos | `flags_parser` | `environment`, `project` | `main` |
| 7398-8360 | **`main()`** | orquesta todo | todo | el ejecutable |
| 8361-8692 | la música | el trabajo para `rm2k-snes-audio`, los temas separados, el tope del arranque, el `.msu` de datos, qué temas heredan los paquetes | `msu_data`, `settings`, `project` | `main`, `test_inherited_songs` |
| 8693-9012 | el análisis del juego | dónde arranca el héroe, qué actores pueden liderar, qué ítems y miembros pueden estar, qué deja caer cada tropa; con la global `args_game_dir` | `events`, `lcf`, `resources` | `main`, `convert_map`, `test_lideres` y las del cronómetro y el destello |
| 9013-9133 | los casos de prueba | partir la línea de comandos en `--case`, la página de cada caso, en qué mapa corre | `events`, `lcf` | `main`, `convert_map` |
| 9134-9677 | **`convert_map()`** | un mapa entero: capas, sprites, bloques, reparto | casi todo lo de las capas, sprites, bloques, VRAM y casos | `main`, `_map_layers` |

Lo que ya tiene su módulo y **no** está acá: el bytecode (`events.py`), la
escena (`scene.py`), el asignador (`allocator.py`), la pelea (`battle.py`),
los menús y pantallas, el título, la imagen, la ventana de RM2k
(`window.py`), las fuentes (`font.py`), las animaciones como imagen
(`animation.py`), las reglas de RM2k (`rules.py`), el formato de la PPU
(`snes_format.py`), y la música en sí (`rm2k-snes-audio`).

Lo que quedó acá y es de otra cosa: **tres partes que no convierten nada**
—el análisis del juego, los casos de prueba y la línea de comandos—, **las
emisiones que no son del mapa** —experiencia, fondos, animaciones de pelea,
música y `.msu`—, y **los planes de recursos** —CGRAM, VRAM, banco de
sprites, compresión— mezclados con sus emisiones.

## La propuesta

Un módulo por pieza que se pueda reemplazar sola cuando se migre a Rust: cada
uno con una entrada que se puede escribir como datos —el mapa leído, las
imágenes, los números del plan— y una salida que también. `snes_convert.py`
queda con `main()`, los ganchos a `lcf` y los imports.

Las cuentas de líneas salen de simular la mudanza entera sobre una copia, con
el mismo script que la hace. Todos en `tools/port/`, en inglés.

| módulo | qué tiene | entra | sale | líneas |
|---|---|---|---|---|
| `snes_format.py` (ya existe) | `COLORS_PER_PALETTE` y `BYTES_PER_TILE` | — | — | +2 |
| `asm.py` | `block` y `pointer`, las primitivas de emisión | bytes | texto de ca65 | 38 |
| `map_layers.py` | las dos capas del fondo: el reparto de la CGRAM, la cuantización, la conversión con Voodoo, y su caché | las capas dibujadas | tiles, CGRAM, tilemaps | 615 |
| `sprites.py` | los personajes como OBJ: poses, paletas, qué NPCs se dibujan, el banco de poses, qué se mueve, el héroe que destella | el mapa, los CharSets, los líderes | el banco de sprites y su reparto de paletas | 897 |
| `obj_extras.py` | lo que va al final del banco de sprites: cronómetro, lluvia, imagen, animación de pelea, y el tope de paletas | el System, la imagen, la animación | tiles y la paleta de cada uno | 315 |
| `baking.py` | los eventos horneados en la capa de encima | el mapa y su render | el mapa con los tiles puestos | 224 |
| `vram.py` | los repartos de la VRAM, las ranuras, y sus controles | cuánto gasta cada capa | qué reparto le toca | 472 |
| `message_window.py` | la ventana de mensajes y la fuente | el System, la fuente | tiles, paleta, celdas, prerender | 238 |
| `blocks.py` | los bloques de 16x16 y las sustituciones | tilemaps y pasabilidad | índices y la tabla de bloques | 280 |
| `materials.py` | `Materials`, qué va comprimido, los flujos, los topes de la WRAM, los crudos | los datos de cada mapa | flujos LZ2 y los crudos | 245 |
| `map_record.py` | el registro de cada mapa, páginas, NPCs, actores, animaciones del ChipSet, y los bloques de datos de un mapa | lo que devuelve `convert_map` | texto de ca65 | 865 |
| `battle_animations.py` | las animaciones de pelea | el bytecode emitido | cuadros y su texto | 161 |
| `battle_scenes.py` | los fondos y los battlers | tropas, mapas, árbol | qué lleva el cartucho y su texto | 429 |
| `battle_tables.py` | la experiencia y los encuentros | la base de datos, los mapas | tablas | 137 |
| `music.py` | el trabajo para `rm2k-snes-audio`, los temas, la herencia, el arranque y el `.msu` de datos | los mapas y el árbol | el trabajo, y el `.msu` | 348 |
| `game_scan.py` | lo que se deduce del juego entero: líderes, ítems, miembros, arranque, lluvia | los mapas y la base de datos | conjuntos de ids | 294 |
| `options.py` | `flags_parser` y `map_order` | `argv` | `args` | 127 |
| `cases.py` | los casos de prueba | `argv` y los archivos de casos | las páginas y sus mapas | 158 |
| `mapdata.py` | `emit()`, con la identidad de la ROM, la firma de la partida y el seno | los mapas convertidos y todo lo demás | `mapdata.inc` | 2.366 |
| `map_convert.py` | `convert_map()` y su precómputo en paralelo | un id de mapa y `args` | el `map_info` | 627 |
| `snes_convert.py` | `main()` y los ganchos a `lcf` | — | — | 1.077 |

**El porqué del corte.** Sigue las etapas que proponía
`docs/research/inspeccion-integral-del-repo.md` —entrada y opciones,
planificación, emisión, diagnóstico—, pero no las junta en cuatro módulos:
las junta por **recurso de la consola**, porque eso es lo que una pieza de
Rust puede tomar entera. La CGRAM y la VRAM del fondo son `map_layers`; la
CGRAM y la VRAM de los objetos, `sprites` y `obj_extras`; el orden de la
VRAM, `vram`; la WRAM de lo comprimido, `materials`. Y las emisiones van
aparte de los planes cuando lo que cruza entre los dos son datos: `map_record`
y `mapdata` sólo leen lo que `convert_map` ya dejó en el `map_info`. El
diagnóstico no tiene módulo propio porque no es una etapa: son los
`SystemExit` y los `print` de cada parte, y se van con ella.

**Lo que no se parte ahora, a propósito:** `emit()`. Sus tramos comparten
decenas de locales, así que partirlo es decidir qué pasa de uno a otro, y eso
es criterio. Se muda entero a `mapdata.py`, y partirlo queda para otro
commit. Lo mismo `main()` y `convert_map()`.

**Cómo se muda.** Un script que corta los nodos de nivel superior con los
comentarios que tienen arriba, arma los imports del módulo nuevo copiando los
de `snes_convert`, y le agrega a éste un `from port.<módulo> import …` con lo
que le quedó faltando. El orden de los commits es el de las dependencias —un
módulo sólo importa de los anteriores—, así que no puede quedar un ciclo, y
ninguno importa de `snes_convert`. Sin re-exports: las pruebas importan del
módulo nuevo. Los nombres no cambian, tampoco los privados que cruzan de
módulo (`_check_slots`, `_tile_alphas`): renombrarlos es otro commit.

**Lo que ya se ve que no se puede partir sin cambiar lógica**, y se anota en
vez de arreglarse:

* **los ganchos a `lcf`** se ponen al importar `snes_convert`. Una prueba que
  importe sólo `sprites` o `game_scan` lee los mapas sin ellos. Las que hoy
  importan `snes_convert` y dejan de usarlo lo siguen importando por eso;
* **`_layers_in_memory`** es un diccionario de `map_layers` que llena
  `precompute_layers`, en `map_convert`: estado mutable entre dos módulos;
* **`args_game_dir`** es una lista global de `game_scan` que `main` escribe;
* **los textos del `.inc` que nombran `snes_convert.py`** —el encabezado,
  `anim_table`, `escribir_msu`— siguen diciendo eso: corregirlos cambia el
  `.inc`, y cada commit de éstos lo deja igual.

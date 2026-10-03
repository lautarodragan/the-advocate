---
name: "Rust: el dominio de los mapas"
description: "Las capas, los sprites, la VRAM, los bloques y el horneado del conversor (map_layers, sprites, vram, blocks, baking, map_convert) a un crate de dominio en Rust, con las ROMs byte por byte iguales"
type: refactor
assignee: taro
---

De taro, el 2026-09-30: seguir con la migración del conversor a Rust, por
el dominio de los mapas, que ya usa `rm2k-render`, Adeleine y `voodoo`. Es
un crate de dominio en `tools/rm2k-snes/`, con la forma de
`tools/rm2k-snes/battle/README.md` ("One stage of a converter"), que el
orquestador en Python (`snes_convert.py`) llama por el PATH.

Sale de `main` en `3d83de68`. Base medida ahí: `NO_CACHE=1 just cartuchos`,
1032 archivos en `rom/build/` (sin el caché, los `.o`, `sello.txt` ni
`conversor.log`), sus sha256 en `<scratchpad>/mara/sha-base.txt`.

## Inventario: qué hace hoy el Python

Las seis piezas y lo que usan, leídas el 2026-09-30:

| módulo | qué hace | de qué dominio es |
|---|---|---|
| `map_layers.py` | cuantiza a 15 bits las dos capas que dibuja `rm2k-render`, reparte la CGRAM baja entre el fondo (8bpp) y la capa de encima (4bpp), le pide a Adeleine qué colores fusionar y cómo agruparlos, arma las imágenes indexadas y se las da a Voodoo; y el caché en disco de todo eso | el fondo del mapa |
| `baking.py` | qué eventos opacos de un tile del ChipSet se pintan en la capa de encima, y sólo si eso no mueve el reparto de la CGRAM | los dos: mira el tile como sprite y convierte las capas dos veces |
| `sprites.py` | los personajes como OBJ: qué poses muestra cada gráfico, el reparto de las ocho paletas (`drawable_npcs`), el banco de VRAM (`build_characters`), el de poses del cartucho (`pose_bank`), qué eventos caminan (`movable_events`) y la copia del gráfico del héroe que destella | los objetos del mapa |
| `obj_extras.py` | lo que va al final del banco de sprites —dígitos del cronómetro, gotas, la imagen de `ShowPicture`, el recuadro de la animación de pelea— y el tope de paletas | los objetos, con píxeles que vienen de otros dominios |
| `vram.py` | los seis repartos de la VRAM, `vram_layout`, y los chequeos de que las pantallas del menú caen en el banco del BG1 | el mapa elige su reparto; los chequeos son de las pantallas |
| `blocks.py` | el mapa como índices a bloques de 16x16 con pasabilidad y terreno, y `Substitutions`, `TileSubstitution` traducido a bloques | el fondo; `Substitutions` corre durante la compilación |
| `map_convert.py` | `convert_map`: arma todo lo de arriba en el `map_info`, y el precómputo en paralelo de las capas | el orquestador del dominio |

Y lo que usan de afuera: `rpgmaker/rm2k.py` (`collect_npcs`,
`passability_map`, `cell_passability`, `terrain_of`, `tile_name`,
`hero_start`), `render/render_map.py` (el `Renderer`, los `Charsets`,
`build_passability`), `port/adeleine.py` y `port/tiles_bin.py` (los dos
binarios), `port/compiler.py` (la respuesta del primer llamado al
compilador), `port/events.py` (constantes, `MapEvents.route_target`,
`route_targets`), `port/map_record.py` (`npc_table`, `anim_bytes`,
`ev_pos_bytes`), `port/game_scan.py` (`map_start`, `images_of`),
`port/cases.py`, `port/window.py` (el System, para el cronómetro),
`port/picture.py` y `port/animation.py`, y `common/settings.py`
(`graphics.palette_weight`).

## La frontera

**Lo que el dominio recibe del orquestador** —decisiones del cartucho y
parches sobre el volcado, nunca datos que el volcado ya tiene—:

* qué mapa, y de dónde leer lo que el proyecto cambió: los archivos de los
  forks de mapas y de ChipSets (`map_files`, `chipset_files`, como ya los
  recibe `rm2k-snes-events`), y dónde buscar los gráficos (el juego, el RTP
  y las imágenes armadas de los ChipSets del fork);
* los candidatos a líder (`game_scan`), el evento vacío de la página de
  prueba en el mapa de arranque, y los comandos de los casos que corren ahí;
* si el cartucho lleva cronómetro en ese mapa, lluvia, la imagen de
  `ShowPicture` y cuántos mapas usan cada gráfico (`maps_per_character`).

**Lo que recibe de otros dominios, como datos y no como código:**

* del compilador de eventos, la respuesta de su primer llamado: qué páginas
  compilan, cuáles giran, qué gráficos numeran los comandos 34 y en qué
  orden (`movable_events` la lee);
* del System, los once dígitos del cronómetro como píxeles (`window`);
* de `picture`, las celdas de la imagen; de `animation`, si alguna página
  del mapa muestra una animación de pelea que se dibuja y cuántos tiles
  lleva su recuadro;
* del juego, dónde arranca el héroe (`tree.start_*`), que hoy lee
  `map_start`.

**Lo que devuelve**, que es lo que hoy lleva el `map_info` y leen
`map_record`, `mapdata`, `materials` y `patches`:

* el fondo: tiles de 8bpp, las palabras de CGRAM, el tilemap, las corridas
  de la animación del ChipSet con sus dibujos, y el resumen (colores,
  presupuesto, fusiones);
* la capa de encima: tiles de 4bpp, su CGRAM, tilemap, en qué paleta
  empieza y cuántos colores fusionó;
* las imágenes indexadas de lo que decidió Adeleine, para `rom/build/<cartucho>/adeleine/`;
* los objetos: el banco de VRAM, las paletas, dónde quedó cada ranura, el
  banco de poses del cartucho por personaje, las bases y paletas del
  cronómetro, las gotas, la imagen y el recuadro, y la tabla del comando 34;
* los bloques: las celdas, la tabla de bloques, pasabilidad y terreno por
  bloque, y las combinaciones `(tile bajo, tile alto) -> bloque`;
* la colisión, el arranque y el reparto de VRAM que le toca;
* lo que el orquestador necesita para compilar y emitir: qué eventos giran,
  cambian, aparecen, quedaron afuera.

**Lo que es de otro dominio y se queda afuera:**

* **la emisión** —`map_record` y `mapdata`—: el dominio devuelve datos y
  la emisión los escribe. `npc_table` es el borde: arma la fila de cada NPC
  con lo que el dominio decidió, y es de la emisión;
* **los chequeos de las pantallas** de `vram.py` (`_check_slots`,
  `_check_items_border`, `_check_target`, `_check_shop`): miran dónde caen
  el menú, la tienda y las ranuras, que son de `menus` y `screens`, contra
  los repartos. El dominio de los mapas es dueño de los repartos, y los
  publica; quién los mira es de las pantallas;
* **`Substitutions`**: corre mientras se compilan las páginas y crea
  bloques nuevos en el `map_info` de un mapa ya convertido. Es el puente
  entre el compilador y los bloques, y se muda con el orquestador del
  cartucho, no con el mapa;
* **qué eventos se compilan, qué ruta llevan y a quién apunta un comando**:
  es del compilador, que ya está en Rust; acá llega su respuesta;
* **el dibujo como RM2k** de capas y CharSets: es de `rm2k-render`, y el
  dominio lo usa como biblioteca;
* **qué colores se pierden y cómo se agrupan**: de Adeleine; **cómo se
  cortan los tiles**: de Voodoo. Las dos como biblioteca.

## Un crate o varios

Tres, para que Cargo cuide lo que hoy sólo cuida el orden de los imports:

* `rm2k-snes/map-background/` (`rm2k-snes-map-background`, biblioteca):
  la mitad baja de la CGRAM y el BG1/BG2. Las dos capas cuantizadas, el
  reparto entre ellas, la conversión, y los bloques de 16x16. No sabe que
  existen los objetos.
* `rm2k-snes/map-sprites/` (`rm2k-snes-map-sprites`, biblioteca): la mitad
  alta de la CGRAM y el banco de OBJ. No sabe que existen las capas.
* `rm2k-snes/maps/` (`rm2k-snes-maps`, la etapa): lee el juego, aplica lo
  que pide el pedido, y hace lo que necesita a los dos: el horneado —que
  mira el tile como sprite y convierte las capas dos veces— y el reparto
  de VRAM —que suma lo que gasta cada uno—. Depende de los dos de arriba.

El criterio: las dos mitades no comparten nada salvo el mapa, y lo único
que las cruza —el horneado y la VRAM— es justo lo que hoy obliga a
`map_convert` a importar de todos. Con tres crates, el día que alguien
quiera que los sprites miren una capa, `Cargo.toml` lo dice.

Lo que no justifica un crate propio: la VRAM (una tabla y una función de
tres números) y el horneado, que no tienen sentido fuera de la etapa.

**Las variables globales.** Ñacurutú anotó dos que tocan esto:
`_layers_in_memory`, que llena `precompute_layers` y lee `map_layers`, y
los ganchos a `lcf`. La primera existe porque convertir las capas en Python
es caro y se reparte en procesos; en Rust, si convertir un mapa cuesta
milisegundos, el caché en memoria y el precómputo se van con ella.
`las-variables-globales-chocan.md` es de la RAM de la ROM y no de esto.

## El plan

Por partes, cada una en su commit, con las ROMs iguales:

1. **Las capas**: `map_layers` a `rm2k-snes-map-background`, y la etapa
   `rm2k-snes-maps layers`, que `converted_layers` llama en vez de
   `rm2k-render` + Pillow + numpy + los dos binarios.
2. **Los bloques y la VRAM.**
3. **Los sprites**: el reparto de paletas, el banco de VRAM y el de poses.
4. **El orquestador**: `convert_map` entero, con el horneado, una sola
   llamada por mapa.
5. Borrar el Python que ya no use nadie.

## Hecho

**Todo el dominio de los mapas está en Rust**, en tres crates, y el Python
que lo hacía se borró. La ROM, los `.inc`, los `.sym` y todo `rom/build/`
salen byte por byte iguales a los de `main` con el Python; los PNG de
`adeleine/`, iguales decodificados.

| commit | qué |
|---|---|
| `90c6ff35` | la tarea: inventario y frontera |
| `7db8c984` | las capas: `rm2k-snes-map-background` y `rm2k-snes-maps layers` |
| `5a16e0c7` | merge de `main` (`591855c0`, lo de Cachirla) |
| `f046e563` | los bloques de 16x16, con las capas |
| `d96f565d` | la tarea al día |
| `756fe507` | el mapa entero: `rm2k-snes-map-sprites` y `rm2k-snes-maps map` |
| `df133150` | las pruebas de Rust contra el Python, y la del mapa entero |
| `eb8624c9` | las tres pruebas de ABL que miraban el Python le preguntan a la etapa (`bakeable`, `split`) |
| `dde35b1a` | el borrado, sólo borrado |
| `890d5587` | la prosa que nombraba lo borrado, y los README |

**Los crates** (`wc -l` de `src/`, sin las pruebas):

* `rm2k-snes/map-background/`, biblioteca: `layers.rs` (el reparto de la
  CGRAM baja, la cuantización, las dos conversiones), `grid.rs`,
  `blocks.rs`. Depende de `adeleine`, `voodoo` y `rm2k-render`.
* `rm2k-snes/map-sprites/`, biblioteca: `character.rs` (colores, paleta,
  poses), `npc.rs` (qué poses muestra cada gráfico), `split.rs` (el reparto
  de las ocho paletas), `bank.rs` (el banco de VRAM y el de poses),
  `extras.rs` (cronómetro, gotas, imagen, recuadro). Depende de `adeleine`,
  `voodoo` y `rm2k-render`. **No depende del fondo, ni el fondo de él.**
* `rm2k-snes/maps/`, la etapa `rm2k-snes-maps`: `game.rs` (el volcado y los
  forks), `events.rs` (los eventos y `collect_npcs`), `sheets.rs` (las
  hojas de CharSet con lo del port: translúcidos horneados, tramados, la
  copia aparte), `baking.rs`, `layers.rs`, `map.rs` (el mapa entero),
  `inspect.rs` (las dos preguntas para las pruebas), `request.rs`,
  `main.rs`. Depende de los dos de arriba, de `ditto`, `rm2k-rules`,
  `rm2k-render`, `adeleine` y `voodoo`. Su README dice el pedido y lo que
  escribe.

Subcomandos: `map` —el que usa el conversor, uno por mapa, en paralelo con
hilos—, `layers` —sólo las capas; hoy lo usan sus pruebas—, y `bakeable` y
`split`, que contestan lo que las pruebas de ABL miran y una captura no
muestra.

**Lo que cambió de la frontera planeada:**

* **`movable_events` se quedó en Python.** Quién camina es lo que el
  bytecode compilado manda a caminar, y eso se sabe recorriendo el
  bytecode con los tamaños de los opcodes, que son del compilador. La etapa
  recibe el resultado —`movable`, `route_graphics`, `animates_still`,
  `turning`—. Lo limpio es que `rm2k-snes-events scan` conteste los blancos
  de ruta de cada página; es un cambio en el compilador.
* **Los nombres de los gráficos translúcidos y de los separados del héroe
  los sigue poniendo Python** (`lcf.DECORATE_TRANSLUCENT`,
  `separate_from_hero`), y llegan en `names`, igual que al compilador.
* **El reparto de VRAM se quedó en Python** (`vram.py`): la tabla la leen
  también las pantallas y la emisión, y tenerla dos veces era peor. La
  etapa devuelve cuántos tiles gasta cada cosa, y Python elige y chequea el
  recuadro de la animación contra el reparto.
* **Dónde arranca el héroe pasó a Rust**, con la colisión.
* La imagen de `ShowPicture` la elige y la corta Python (`events.Pictures`,
  `picture.cells`), y viaja ya cortada.
* `npc_table`, `ev_pos_bytes` y `Substitutions` quedaron donde estaban:
  son de la emisión y de la compilación.

**Las globales de Ñacurutú:** `_layers_in_memory` y `precompute_layers` se
fueron, y con ellos el caché en disco de las capas: la etapa convierte un
mapa entero sin caché, y los mapas van en paralelo. `NO_CACHE=1 just
cartuchos` bajó de 54 s a 39 s. Los ganchos a `lcf` siguen.

## Cómo se verificó

Con scripts descartables en `<scratchpad>/mara/`:

* **Mapa por mapa, Python contra Rust**:
  * las capas y los bloques de los 93 mapas de `release` —`test-special`
    usa un subconjunto—, sin hornear y con los horneados de los cuatro que
    tienen, campo por campo: 0 diferencias (`comparar_capas.py`);
  * el mapa entero: un `rm2k-snes-convert` descartable
    (`convert_compara.py`) que en cada cartucho convierte cada mapa con el
    `convert_map` de Python y con la etapa, y compara el `map_info` entero
    y lo que imprime: iguales los 93 de `release`, los 7 de `test-special`
    y los 2 de `test-encounter-every-step`, y la salida igual línea por
    línea.
* **Los cartuchos**: `NO_CACHE=1 just cartuchos` y el sha256 de todo
  `rom/build/` —menos el caché, los `.o`, `sello.txt` y `conversor.log`;
  el `.dbg` sin `mtime`—: 766 archivos, más los 266 PNG de `adeleine/`
  decodificados. Después de cada paso, iguales al anterior; y al final,
  **el árbol entero contra el Python de `main` (`591855c0`)** —los `.py` de
  `tools/port`, `render`, `rpgmaker` y `common` de `main` puestos en el
  árbol, armado, y vueltos—: los 766 iguales y los 266 PNG iguales
  decodificados. Con el caché prendido, frío y tibio, también iguales.
* **Los sha256 de las ROMs**, iguales en `main` y acá:
  * `release/abl.sfc` `e97a574b5a2c8205f4a527f747499f0f122cabaacc94c36ace119ed3db2080a0`
  * `tests/special/prueba.sfc` `08862e741912ace6f6f5614c5520240b81d4973ab27c7ddb194cfe266c9162b5`
  * `tests/encounter-every-step/prueba.sfc` `ad16736073318221ae418dc7b103e18edc7a2b98d9bbd856e7d1549e27f73a30`
* **Las tandas**: `just pruebas`, 879 —eran 883: las cuatro de
  `test_timer_paleta` que probaban el mecanismo con paletas inventadas
  pasaron a `extras.rs`, porque no necesitan el juego—;
  `just -f tools/justfile test`, 90; `cargo test` de los tres crates y de
  `cartridge`, en verde.
* **Las pruebas de los crates no dependen de ABL**: las de las capas, los
  bloques y los sprites comparan contra los sha256 de lo que daba el Python
  para entradas armadas adentro de la prueba, sacados antes de borrarlo
  (`referencia_capas.py`, `referencia_sprites.py`); las de la etapa arman
  un juego chico.

**Los PNG de `adeleine/` cambian de bytes y no de pixeles**: los escribe
el crate `png` y no Pillow, que comprime distinto.

**Una trampa de la verificación**: el `.dbg` cambia según qué
`rm2k-snes-assemble` arma, porque nombra los fuentes relativos a su
checkout. Con `cartridge` instalado en el `bin/` local —hace falta, porque
la huella nombra a `rm2k-snes-maps`— la base hay que armarla también con
el local, o los tres `.dbg` salen distintos sin que cambie nada.

## Al mergear

* Instalar en el global `maps` —el binario nuevo— y `cartridge` —la huella
  de los cartuchos lo nombra—: `just -f tools/justfile install maps
  cartridge`. Sin `rm2k-snes-maps` en el PATH el conversor para y dice
  cómo instalarlo.
* `rom/build/cache/capas/` queda viejo: nadie lo lee más, y se puede
  borrar.
* No mueve goldens ni la ROM.

## Lo que falta

* **Que el compilador conteste quién camina** —los blancos de las rutas de
  cada página compilada— y `movable_events` se vaya de Python.
* **Los repartos de VRAM en un solo lado**: hoy los elige y chequea
  `vram.py`. Si se mudan a la etapa, que los publique para las pantallas,
  como `rm2k-snes-cartridges --list --json`.
* **Los colores del cronómetro están dos veces**: `timer_colors_of` en
  Python, para la máscara que emite `snes_convert`, y `timer_colors` en
  `extras.rs`. Es la misma regla; la máscara podría salir de la etapa.
* **`voodoo` en la huella**: el conversor ya no corre el binario —la etapa
  lo usa como biblioteca—, pero sigue en `CONVERTER_TOOLS`. Sacarlo es un
  cambio de `cartridge`.
* **`rm2k-snes-maps layers`** sólo lo usan sus pruebas: decidir si se
  queda como entrada o se va.
* El camino de los translúcidos tramados (`TRANSLUCENT_MODE=dither`) no lo
  ejercita ningún cartucho; está portado, sin prueba contra el juego.
* Los avisos de `clippy` de los tres crates.

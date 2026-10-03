---
name: "Rust: la emisión"
description: "Lo que escribe mapdata.inc (mapdata, map_record, materials, blocks, vram, map_layers, compress) a Rust, con mapdata.inc igual línea por línea y las ROMs byte por byte"
type: refactor
assignee: taro
---

De taro, el 2026-10-01: "en paralelo, ¿podemos avanzar con alguna migración
de Python a Rust?". Todos los dominios que alimentan la emisión ya son Rust
(eventos, mapas, pantallas, pelea, imágenes, música, parches); lo que queda
en `tools/port/` es casi todo emisión y pegamento. Era lo último del plan,
junto con el orquestador (`snes_convert.py`), que va después.

Base: `main` en el commit que lanza la tarea, `abl.sfc` `8f8bf5b3c5facf51…`,
`just pruebas` 923, `just -f tools/justfile test` 46.

Medido en la base, con `cartridge` instalado en el `bin/` local —la huella
de los cartuchos va a nombrar el binario nuevo, y el `.dbg` cambia según
qué ensamblador arma (la trampa de Mara)—: `NO_CACHE=1 just cartuchos`,
1035 archivos en `rom/build/` sin el caché, los `.o`, `sello.txt` ni
`conversor.log`; sus sha256 y los tres `mapdata.inc` en
`<scratchpad>/timbo-emision/`.

* `release/abl.sfc` `8f8bf5b3c5facf517fdf3a758326d2fddafcfe9f16ab88fb3bf5c139c1b29c87`
* `tests/special/prueba.sfc` `007c02045ba39d719dc4e8796a6f1fce8c08e0419e3410affc836dac0cda9e6e`
* `tests/encounter-every-step/prueba.sfc` `c236bdc0e7765f8dd2f5292a6062ffe57b98da0618aaf59e867bb9e173d349c1`

## Inventario: qué hace hoy el Python

Leído el 2026-10-01:

| módulo | qué hace | qué es |
|---|---|---|
| `compress.py` | corre `lz2 compress --no-increasing` por el PATH, cuenta los comandos de un flujo y se niega a los dos que `lz2_decompress` no lee | hoja; lo usa también `fullscreen.py` (título y Game Over), que es de las imágenes |
| `materials.py` | los bloques de datos con nombre propio y su deduplicación (`Materials`), qué clases van en LZ2, en cuántos flujos y con qué topes de WRAM (`compressed_parts`, `check_streams`), el costo de descomprimir el mapa de arranque (`decompress_frames`, que va al pedido de la música) y los crudos que leen las pruebas (`write_raw`) | emisión |
| `vram.py` | los seis repartos de la VRAM, cuál le toca a un mapa (`vram_layout`), sus chequeos de hardware (`_check_splits`), las bases de la ventana y las direcciones de la pantalla de ranuras | el contrato con el runtime: lo leen los mapas (`map_convert`, para elegir), las pantallas (`screen_stage`, los bancos del BG1) y la emisión |
| `map_layers.py` | `layers_answer` —lee la respuesta de `rm2k-snes-maps` en la forma del `map_info`— y las constantes de la CGRAM baja (`CGRAM_RESERVED`, `PRIORITY_ABOVE`, `BACKDROP`, `window_palette`) | `layers_answer` es pegamento del orquestador; las constantes, de la emisión |
| `blocks.py` | `Substitutions`: `TileSubstitution` traducido a bloques de 16x16, armando los que faltan antes de compilar; y `substitution_triples` | no es emisión: es el puente entre el compilador y los bloques del mapa |
| `map_record.py` | el registro de cada mapa (`map_table`, `offsets`), la animación del ChipSet (`anim_table`, `anim_bytes`), las páginas (`page_table`), los bloques de datos de cada mapa (`map_data`), las tablas de NPC (`npc_table`, `npc_bytes`), de poses y de líderes, y las posiciones de los eventos (`ev_pos_bytes`) | emisión; `npc_table` y `ev_pos_bytes` los llama hoy `map_convert` |
| `mapdata.py` | `emit`: el encabezado de constantes, las poses, cada mapa, la ventana y la fuente, la imagen, las animaciones, el título, las pantallas, el menú, los ítems, el equipo, la pelea, las habilidades, las tropas, la escena, y las tablas de banco 0 | emisión |

Y de los cuatro que el encargo pidió mirar: de `sprites.py` sólo son de la
emisión las constantes (`OBJ_PRIORITY*`, `OBJ_COLORS`, `SPRITE_POSES`,
`POSE_BYTES`, `block_tile`); `separate_from_hero` y `maps_per_character`
son elección y van al pedido de los mapas. De `picture.py`, `cells` y
`reserved_tiles` son del pedido de los mapas y `OBJ_SIDE`/`GRID` de la
emisión. De `battle_animations.py`, `rom_animations` es elección (qué
animaciones lleva el cartucho) y `animations_asm` emisión. De
`battle_scenes.py`, `rom_scene` y los usos de parches son elección, y
`scenes_asm` emisión.

## La frontera

**Un crate nuevo, `tools/rm2k-snes/mapdata/` (`rm2k-snes-mapdata`)**, con
la forma de "One stage of a converter": biblioteca y binario. Es la
emisión: recibe lo que los otros dominios ya decidieron y escribe
`mapdata.inc`. No elige nada que no sea de cómo se escribe —qué bloques se
comparten, cómo se parten los flujos, en qué segmento va cada tabla—.

* **Recibe del orquestador**, en un pedido: lo que cada dominio contestó,
  como datos —los mapas (tiles, CGRAM, bloques, sprites, páginas
  compiladas), la ventana y las pantallas, la imagen, las animaciones, la
  escena, las tablas de la pelea, el modelo de la pelea, las páginas de
  tropas, los eventos comunes del equipo— y lo que es del cartucho —el
  mapa de arranque, el grupo inicial, las perillas—.
* **Lee del juego él mismo**, con Ditto, lo que hoy `emit` lee de la base:
  ítems, habilidades, enemigos, actores y tropas (la `Db` de
  `rm2k-snes-battle`, y sus reglas para los parámetros).
* **Escribe** `mapdata.inc`, los crudos de `crudos/`, y un JSON con lo
  que el resto necesita (el informe de lo compartido y comprimido).

**Dónde vive cada hoja**:

* `compress` y `materials` → `rm2k-snes-mapdata`. La compresión usa `lz2`
  como biblioteca, en hilos. `compress.py` se queda mientras lo use
  `fullscreen.py`, que es de las imágenes.
* `vram` → `rm2k-snes-mapdata`, que **publica** los repartos: `vram`
  contesta la tabla, las constantes y cuál le toca a cada mapa. Es el
  contrato con el runtime —lo que el `.inc` dice de la VRAM—, y así lo
  leen los mapas y las pantallas de un solo lado, como pidió Mara.
* las constantes de `map_layers` → `rm2k-snes-mapdata`; `layers_answer`
  se queda con el orquestador.
* `blocks` (`Substitutions`) → `rm2k-snes-maps`, la etapa del mapa: es la
  que arma los bloques, con las mismas reglas de pasabilidad. El pedido
  lleva los `TileSubstitution` que pueden correr en el mapa, y la
  respuesta trae los bloques ya agrandados, la tabla para el compilador y
  los que no se pudieron armar. Qué pares pidió una página —`SUB_MAX`— lo
  sigue contando el orquestador con lo que contestó el compilador.

**Lo que queda en Python**: el orquestador (`snes_convert.py`,
`map_convert.py` y `layers_answer`), que junta lo de cada dominio y arma
el pedido; `compress.py` para `fullscreen.py`; y lo que el pedido necesita
de otros dominios que siguen en Python (`animation.cells`, los bytes de la
escena).

## El plan

1. **Las hojas**: `compress`, `materials` (la compresión y los flujos),
   `vram`, las constantes de `map_layers`; y `blocks` a la etapa de mapas.
2. **`map_record`**: lo que se emite por mapa.
3. **`mapdata`**: el resto de las tablas y el armado del archivo.
4. **El borrado**, en su propio commit, sólo con borrados. La prosa que
   nombraba lo borrado, en otro.

Cada etapa: `mapdata.inc` de los tres cartuchos igual línea por línea, y
todo `rom/build/` byte por byte, con `NO_CACHE=1`.

## Hecho, etapa por etapa

### 1. Las hojas

* `74055585`: la compresión y los flujos (`compress.rs`, `materials.rs`), los
  repartos de VRAM (`vram.rs`, que la etapa publica con `vram`) y las
  constantes de la CGRAM baja (`cgram.rs`). `vram.py` queda como lector de
  lo publicado. Las pruebas de los repartos y de los flujos se mudaron al
  crate.
* `68038577`: `Substitutions` a `rm2k-snes-maps` (`substitutions.rs`): el
  pedido del mapa lleva los `TileSubstitution` y la respuesta trae los
  bloques agrandados, la tabla para el compilador y los que faltan. `SUB_MAX`
  pasó a `snes_convert.py`. `blocks.py` queda sin usar.

### 2. `map_record`

* `260c36ed`: `rm2k-snes-mapdata maps` escribe todo lo que va por mapa
  —registro, tablas, páginas, NPC, poses, bloques con su LZ2, crudos— en tres
  pedazos que `emit` pone en su lugar. `pages` escribe una tabla de páginas
  sola, para la prueba de ABL que la mira. Las pruebas del crate comparan
  contra los sha256 del Python de la base, sobre un pedido armado
  (`tests/maps.json`).

### 3. `mapdata`

* `ac8b075b`: `rm2k-snes-mapdata emit` escribe el `.inc` entero —el
  encabezado de constantes, la ventana y la fuente, la imagen, las
  animaciones, el título y las pantallas completas, las ranuras y el menú,
  las pantallas de texto, el equipo, la pelea, las habilidades, las tropas
  y sus páginas, la escena, las tablas del banco 0, y `timer_mask` y
  `CASE_SLOT`, que `snes_convert` agregaba después—. `mapdata.py` queda
  como el armado del pedido.
* `42332816`: las pruebas del `.inc` entero contra los hashes del Python,
  sobre dos cartuchos armados (`tests/emit-*.json`) con la base del juego de
  prueba de `rm2k-snes-battle`: uno pelado y uno con todo.
* `f4544820`: merge de `main` (Tangle Forest, de Tacuarita). Chocó en
  `mapdata.py`: sus dos constantes nuevas del encabezado, `TIMER_SLOT` y
  `COND_TIMER`, pasaron a la plantilla de `emit/header.rs` y a `engine.rs`.
  Los hashes de las pruebas son desde ahí los del Python de `main`
  (`601c6f9a`).

Cómo quedó, por dentro:

* **El pedido lleva las respuestas de los otros dominios tal cual**: la de
  `rm2k-snes-screens convert` entera —con su geometría—, la del modelo de la
  pelea, las páginas de tropas del compilador, las tablas de la pelea. Lo
  que es de otro dominio que sigue en Python llega hecho bytes y números:
  los cuadros de las animaciones con su ancla (`animations_request`) y la
  escena con sus fondos, battlers, posiciones y orden de dibujo
  (`scene_request`).
* **La base la lee la etapa**: ítems, habilidades, enemigos, actores y
  tropas, con la `Db` y las reglas de `rm2k-snes-battle`, que es de quien
  depende.
* **Las plantillas largas de constantes se copiaron del Python tal cual** y
  las llena `pyfmt.rs`, un `%` de Python: así el texto sale igual carácter
  por carácter sin transcribir a mano ciento sesenta y seis argumentos.
* **Un error latente del Python**, corregido: `tpage_var` y `tpage_value`
  leían los campos `ranura` y `valor` de un `Trigger` que desde la
  traducción se llaman `slot` y `value`. Ninguna página de un juego de RM2k
  usa esa condición, así que nunca se evaluaba; tiene su prueba.

### 4. El borrado

* `9470aba5`: antes de borrar, lo que el orquestador todavía tomaba de
  `map_record` —la tupla de sprite del `map_info`, que ya nadie leía, y
  `PARALLEL_MAX` y `ROUTE_EV_MAX`, que pasan a `snes_convert.py` al lado de
  `SUB_MAX`—.
* `36a6a8db`: **sólo borrados**. `map_record.py`, `materials.py`,
  `blocks.py`, `asm.py` y `color.py` enteros; de `battle_animations.py` y
  `battle_scenes.py` lo que escribían para el `.inc`; las constantes que
  sólo leía la emisión en `map_layers.py`, `sprites.py`, `obj_extras.py` y
  `constants.py`; `commands` de `compress.py`; de `rules.py`,
  `equipped_params` y los términos de la pelea. 1812 líneas.
* `40f7527a`: la prosa que nombraba lo borrado —docstrings, comentarios,
  `README.md`, `tools/README.md`, `AGENTS.md`, `docs/port/maps.md` y
  `vram.md`, tres pruebas de ABL, dos crates— y el README del crate.
* `0a160c4d`: las combinaciones de bloques, que el `map_info` seguía
  llevando sin que nadie las leyera.
* `bf45a944`: la prueba de la huella de `cartridge`, que no sabía de
  `rm2k-snes-mapdata`.

## Lo que quedó en Python

* **El orquestador**: `snes_convert.py`, `map_convert.py` y `layers_answer`
  —juntan lo de cada dominio y arman los pedidos—, `mapdata.py` —el pedido
  de la emisión— y `vram.py` —el lector de los repartos que publica la
  etapa—.
* `compress.py`, que usa `fullscreen.py` para el título y el Game Over.
* Lo que el pedido de la emisión necesita de dominios que siguen en
  Python: los cuadros de `animation.py` y lo de la escena de `scene.py`.

## Cómo se verificó

Con los scripts de `<scratchpad>/timbo-emision/` (`base.sh`, `huellas.py`):
`NO_CACHE=1 just cartuchos` con los sellos borrados, y el sha256 de todo
`rom/build/` —menos el caché, los `.o`, `sello.txt` y `conversor.log`; el
`.dbg` sin `mtime`—, con los tres `mapdata.inc` aparte.

* **Antes del merge**, después de cada commit de las etapas 1 a 3: los 1035
  archivos y los tres `mapdata.inc` iguales a la base de `052cb999`.
* **Después del merge**: la base se volvió a sacar sobre `main`
  (`601c6f9a`) —su Python y sus binarios de `events`, `maps` y `cartridge`,
  instalados en el `bin/` local—, y el árbol mergeado, con los binarios de
  esta rama, dio **los 1075 archivos iguales**, después del merge y después
  de cada commit del borrado. Los `mapdata.inc` de los tres cartuchos,
  iguales línea por línea: 305476, 65718 y 28581 líneas antes del merge.
* Las ROMs, iguales a las de `main`:
  * `release/abl.sfc` `19e771abd78b329153a2fc77717a87f521f1afc65a499c2abe1f67d5b7465b3c`
  * `tests/special/prueba.sfc` `4f091bfd8de4a5869d19b5bfe09dc9169f294bd48ec2a8feb9ac1ab64fcfefe9`
  * `tests/encounter-every-step/prueba.sfc` `555c3be1d826d01759473ec8e6d52c12639f079107095a453f3e4e5729d72ec2`
* **Contra el Python, fuera de los cartuchos**: las pruebas del crate
  comparan con los sha256 de lo que escribía el Python sobre entradas
  armadas para pasar por cada camino —incluidos los que ningún cartucho
  recorre: sin título, sin Game Over, sin imagen, sin animaciones, sin audio
  de pelea, sin páginas de tropas—. Los sacó un script descartable
  (`gen_record.py`, `gen_emit.py`) que corría el Python sobre lo mismo; las
  salidas eran iguales línea por línea antes de anotar los hashes.
* Las tandas, sobre el árbol final: `just pruebas`, 934 —eran 936 en `main`;
  dos de `test_lz2.py` se mudaron al crate—; `just -f tools/justfile test`,
  39 —eran 46; las siete de `test_vram_layouts.py` se mudaron al crate—;
  `cargo test -p` de `rm2k-snes-mapdata` (38), `rm2k-snes-maps`,
  `rm2k-snes-events`, `rm2k-snes-images` y `rm2k-snes-cartridge`, en verde.

Lo que el log del conversor cambia, y no está en la huella: el renglón "the
map fits in N 16x16 blocks" cuenta ahora los bloques que armaron las
sustituciones, porque la etapa los arma antes de contestar. Y `NO_CACHE=1
just cartuchos` tarda lo mismo que antes, unos 45 s.

## Al mergear

* Instalar en el global **`mapdata`** —el binario nuevo—, **`maps`** —su
  pedido lleva las sustituciones y el `map_convert` nuevo se las manda— y
  **`cartridge`** —la huella nombra `rm2k-snes-mapdata`—: `just -f
  tools/justfile install mapdata maps cartridge`. Van juntos con el Python:
  sin `rm2k-snes-mapdata` el conversor para y dice cómo instalarlo, y el
  `maps` viejo no entiende el pedido nuevo. `events` e `images` sólo
  cambiaron un comentario.
* Ningún script de Python cambió de nombre: no hace falta `install-scripts`.
* No mueve la ROM ni las goldens.

## Lo que falta

* **Las constantes del motor están dos veces**: en `engine.rs`, de donde las
  emite el `.inc`, y en `events.py`, con sus comentarios largos, porque las
  leen pruebas de ABL. Lo mismo `SUB_MAX`, `PARALLEL_MAX` y `ROUTE_EV_MAX`
  (`snes_convert.py` y `record.rs`) y `OBJ_PRIORITY*` con `block_tile`
  (`sprites.py` y `objects.rs`). Se van de Python cuando el orquestador
  pase a Rust, o antes si las pruebas de ABL las leen del `.inc`.
* **Lo que dibuja cada página** (`oam`, en `snes_convert`) se arma todavía
  en Python con `where` y `block_tile`: podría armarlo la emisión, que ya
  tiene los objetos del mapa.
* **Lo que se emite al `.inc` sigue citando el Python** ("Generated by
  tools/port/snes_convert.py", "see `anim_table` in
  tools/port/snes_convert.py"), y comentarios del runtime nombran archivos
  que ya no existen (`frame_without_gaps` en `battle_animation_frames.s`,
  `Substitutions` en `interpreter_map.s`). Las dos cosas cambian el `.inc` o
  el `.dbg`: van en su propio commit, cuando se decida tocar lo que se emite.
* `compress.py` se va cuando `fullscreen.py` pase a usar la etapa.

---
name: "Rust: el orquestador y el lector del juego en Python"
description: "Lo último de la migración: snes_convert.py y lo que queda en tools/port/ (unas 7.000 líneas) como un binario de Rust, y los lectores del juego en Python (tools/rpgmaker/lcf.py, rm2k.py, fork.py) reemplazados por Ditto y el volcado"
type: refactor
assignee: Chuña
---

De taro, el 2026-10-02: el último paso de la migración, después de las
reglas repetidas (Cachirla). Todos los dominios ya son Rust; en
`tools/port/` queda el orquestador —que arma los pedidos de cada etapa y
reparte lo que contestan— y algunos restos, y `tools/rpgmaker/lcf.py`,
`rm2k.py` y `fork.py` todavía leen el juego en Python. Los usan 10 módulos
de `tools/port/`, 2 de `tools/render/`, uno de `tools/tests/` y 15 pruebas
de ABL.

Sale de `main` en `8db96253`. Ahí, `NO_CACHE=1 just cartuchos` da 1418
archivos en `rom/build/` —sin el caché, los `.o`, `sello.txt` ni
`conversor.log`; el `.dbg` sin `mtime`—, iguales a los de la base del
encargo: `abl.sfc` `35c765009320d436…`. Los sha256 y los tres
`mapdata.inc`, en `<scratchpad>/chuna/`.

## Inventario: qué hace hoy cada archivo y quién lo usa

Medido el 2026-10-02 con un grep de los `import` de `tools/` y de
`rom/pruebas/`.

### `tools/port/`

| archivo | qué hace | quién lo usa | qué es |
|---|---|---|---|
| `snes_convert.py` | `main`: el orden, los chequeos de las páginas compiladas, la segunda ronda (código de cada mapa, `draws`), los pedidos a patches y audio, las imágenes de Adeleine | el script; 8 pruebas lo importan sólo por los ganchos de `lcf` que instala, una por `SUB_MAX` | orquestación |
| `options.py`, `cases.py`, `stage.py` | los flags, `--case`, correr una etapa | el conversor; `stage.run` también el arnés | orquestación; `stage.run` lo usa el arnés |
| `map_convert.py`, `map_layers.py`, `sprites.py`, `obj_extras.py`, `window.py`, `vram.py` | el pedido de `wally map` y el `map_info` de su respuesta; `separate_from_hero`, `maps_per_character`; el System del cronómetro; el lector de los repartos | sólo el conversor | orquestación |
| `game_scan.py` | líderes posibles, ítems, miembros, lluvia, alcance del cronómetro | el conversor; `test_lideres`, `test_timer_paleta`, `test_destello_paleta` | orquestación: lo que el conversor deduce para armar los pedidos |
| `compiler.py` | los dos pedidos de `rm2k-snes-events` y su respuesta; `loose_page`, `slots`, `troop_triggers` para las pruebas | conversor; arnés (`datos`, `etapa_mapas`) y 3 pruebas | orquestación, más un cliente de la etapa para las pruebas |
| `screen_stage.py` | el pedido de `rm2k-snes-screens convert` y su respuesta; `layout`, `render`, `equip`, `refit` para las pruebas | conversor; arnés (`pantallas`, `modelo`, `batalla`) y `test_textos_del_juego` | orquestación, más un cliente para las pruebas |
| `image_stage.py`, `battle_stage.py`, `mapdata.py` | los pedidos de `rm2k-snes-images`, `rm2k-snes-battle model` y `rm2k-snes-mapdata emit` | sólo el conversor | orquestación |
| `picture.py` | qué imágenes de `ShowPicture` lleva cada mapa, cortadas en objetos; las grandes, numeradas | sólo el conversor | dominio de las imágenes, en el lado del pedido |
| `animation.py`, `battle_animations.py` | qué animaciones lleva el cartucho (se recorre el bytecode), el ancla, los cuadros en tiles | conversor; `test_parches` (`fit_size`, `BOX`), `test_animacion_cuadros` | dominio de las imágenes y de la emisión |
| `scene.py`, `battle_scenes.py` | qué fondos y battlers lleva el cartucho, sus bytes, dónde se para cada uno; `compose` | conversor; `test_batalla_escena_dibujo`, `test_msu_datos` | dominio de la escena |
| `fullscreen.py`, `palette.py`, `compress.py`, `snes_format.py` | título y Game Over: la imagen de la etapa, en tiles, comprimida con `lz2` | conversor; `pack_tile` en `test_msu_datos` | dominio de las imágenes y de la emisión |
| `constants.py`, `engine.py`, `event_opcodes.py` | números del motor y opcodes | conversor y muchas pruebas | constantes |
| `events.py` | constantes de comandos, registros, `MapEvents`, `walk_code`, `PartyState`, `Encounters`, `key_value`, `named_backdrops`, `index_animations` | conversor y 25 pruebas y módulos del arnés | mezcla: lo del conversor es orquestación; lo demás son modelos de las pruebas |
| `experience.py` | la curva de RM2k | `lcf.py` (no), 4 pruebas, `test_rm2k_rules` | modelo de las pruebas |

### `tools/rpgmaker/`

| archivo | qué hace | quién lo usa |
|---|---|---|
| `lcf.py` | lee el volcado en Python: `Map`, `Database`, `TreeMap`; los ganchos `REFIT_TEXTS` y `DECORATE_TRANSLUCENT` | 10 módulos de `port/`, 2 de `render/`, `test_rm2k_rules` y 15 de las pruebas de ABL |
| `rm2k.py` | las reglas en Python: pasabilidad, `page_graphic`, `collect_npcs`, los nombres decorados (`~horneado`, `~aparte`, `@tile:`) | conversor, `render/`, `test_rm2k_rules`, 6 de ABL |
| `fork.py` | `rom/parches/manual/`: valida los forks y los mapas nuevos | `lcf`, `compiler`, `chipset_recipe`, `test_fork_mapas` |
| `resources.py`, `event_codes.py` | dónde está el juego; los nombres de los códigos | conversor y pruebas |

`test_dump_readers.py` mira sólo el Rust: que ningún `src/` fuera de Ditto
nombre los archivos del volcado. `lcf.py` sigue vivo porque el conversor es
Python, y en Python no hay Ditto: lo que lee el juego en Python es eso.

### `tools/render/` y `tools/emulator/`

* `render_map.py` es el `Renderer`: guarda la base, el árbol y dónde se
  buscan las imágenes, y al construirse **arma las imágenes de los ChipSets
  del fork** (`chipset_recipe.py`) en `rom/build/parches-manual/`, que
  `wally` lee. Es conversor.
* `chipset_recipe.py` es la receta de `rom/parches/manual/chipsets/`: copia
  bloques, poda, pega poses y una imagen. Es del dominio de los mapas: va a
  Rust con el orquestador (el PNG que escribe es intermedio y entra en la
  huella de `rom/build/`).
* `emulator/retro.py` es el arnés del emulador, por ctypes: **se queda en
  Python**. No es del conversor y lo usan sólo las pruebas.

## El plan

**Cambio el orden del encargo**, y el porqué: los lectores del juego en
Python (paso 1) existen porque el conversor es Python. Pasarlos a Ditto
antes de pasar el conversor quiere decir que el Python le pregunte a un
binario lo que hoy lee —las páginas de cada mapa, los nombres, la base—,
pedidos que se tiran cuando el conversor es Rust y lee con Ditto él
mismo. Así que:

1. **El orquestador a Rust**: un crate nuevo,
   `tools/rm2k-snes/convert/` (`rm2k-snes-convert`), con los mismos flags,
   que reemplaza a `snes_convert.py` sin que `rm2k-snes-cartridges` cambie
   más que en la huella. Lee el juego con Ditto (con `Game` de
   `rm2k-snes-events` donde alcanza), y llama a las etapas por el PATH con
   **los mismos pedidos**: se verifica capturando cada pedido del Python y
   del Rust y comparándolos, y después todo `rom/build/` byte por byte.
   Con eso el conversor deja de leer con `lcf`/`rm2k`/`fork`.
   Lo que es de un dominio y hoy hace el Python sobre la respuesta de una
   etapa —los bytes de la escena, qué imágenes lleva un mapa, la receta del
   ChipSet— va al crate de ese dominio cuando es una función pura que se
   puede llamar como biblioteca sin cambiar ningún pedido, y si no, a un
   módulo del orquestador con el nombre del dominio, anotado abajo.
2. **Las pruebas sin los lectores de Python**: lo que leen sólo las pruebas
   de ABL —las constantes de `events.py`, `Encounters`, `key_value`,
   `experience.py`, `scene.compose`, los clientes de las etapas— pasa a
   `rom/pruebas/arnes/`, leyendo el volcado en JSON (que es de ABL) o
   preguntándole a los binarios, como ya hacen `modelo.py` y `musica.py`.
3. **El borrado**, en su propio commit, y la prosa en otro.

Cada paso, con todo `rom/build/` igual con `NO_CACHE=1` y las dos tandas en
verde. Si no entra todo, se entrega el 1 terminado.

## Hecho, etapa por etapa

### Cómo se verifica

Dos redes, en `<scratchpad>/chuna/`:

* **Los pedidos**: `capture.sh` corre el conversor sobre los tres cartuchos
  con las etapas detrás de un shim que copia cada `--request`, y
  `compare.py` compara los pedidos de un conversor contra los del otro
  —como JSON, con el orden de las claves— y todo lo que cada uno escribió
  al lado de la salida. Las líneas de la llamada (`argv-*.txt`) se sacaron
  de `rm2k-snes-cartridges` con un envoltorio que las anotaba.
* **Todo `rom/build/`**: `base.sh`, con `NO_CACHE=1 just cartuchos`, los
  sha256 de todo menos el caché, los `.o`, `sello.txt` y `conversor.log`
  —el `.dbg` sin `mtime`—, y los tres `mapdata.inc` aparte.

**La base se sacó dos veces**, por la trampa de Mara: con el ensamblador
global los `.dbg` salen distintos que con el local, y la etapa 1 toca
`cartridge` (la huella), así que el local es el que arma. La que vale es
`sha-base2.txt`: el conversor de Python con el `cartridge` de la rama.

### 1. El orquestador a Rust

`tools/rm2k-snes/convert/`, `rm2k-snes-convert`, con los mismos flags
—menos `--charset` y `--charset-index`, que el Python asignaba y nadie
leía desde que el gráfico del héroe sale del grupo—. Lee el juego con
Ditto y llama a las etapas por el PATH con **los mismos pedidos**: los de
los tres cartuchos, iguales a los del Python como JSON, salvo:

* `rm2k-snes-mapdata vram` y `engine`, que ya no se llaman: los repartos,
  los chequeos y los números del motor se leen de `rm2k-snes-mapdata`
  como biblioteca, de donde salían;
* `test_graphics` del pedido de `compile` va por número de mapa y no en el
  orden en que Python recorría un `set`; la etapa lo lee a un mapa.

Lo que hacía el Python sobre las respuestas, que era de un dominio, quedó
en módulos del crate con el nombre del dominio: `pictures.rs` (qué imágenes
lleva cada mapa, los objetos), `animations.rs` (los cuadros en tiles, el
ancla), `scene.rs` (qué fondos y battlers, sus bytes, dónde se para cada
uno, quién pide cada cosa), `fullscreen.rs` (el flujo del título y del
Game Over), `chipsets.rs` (la receta de los ChipSets del fork, que era
`render/chipset_recipe.py`) y `fork.rs` (la validación de
`parches/manual/`). Pasarlos a sus etapas cambia pedidos y los hashes de
las pruebas de esos crates: queda anotado abajo.

Medido sobre la rama, con `convert` y `cartridge` en el `bin/` local:

* **Todo `rom/build/` igual** a `sha-base2.txt` —1418 archivos— **menos
  los tres PNG de `parches-manual/ChipSet/`**, que el Rust escribe con
  otro compresor que Pillow: decodificados son iguales —modo, tamaño,
  paleta, índices e info, `pngcmp.py`—, y `wally`, que los lee, contesta
  lo mismo. Los tres `mapdata.inc`, iguales línea por línea: 336442,
  63556 y 27325 líneas. Las ROMs, las de la base.
* El `conversor.log` de `release`, igual línea por línea al del Python.
* `just pruebas`, 1008; `just -f tools/justfile test`, 39;
  `cargo test` de `rm2k-snes-convert` (25), `rm2k-snes-cartridge` y
  `ditto`.

Cosas que cambiaron por el camino:

* La huella de los cartuchos nombra `rm2k-snes-convert` y ya no `lz2`, que
  nadie corre: el conversor comprime el título con `lz2` como biblioteca,
  por `rm2k-snes-mapdata`.
* Ditto ganó `dump::layers_path` y `dump::is_dump`: la validación del fork
  necesita saber dónde van las capas de un mapa, y `test_dump_readers.py`
  —con razón— no deja que otro crate lo escriba.
* El chequeo del destello del héroe cuenta los NPC que contestó `wally` y
  no un `collect_npcs` propio: el de Python contaba distinto un evento con
  una página condicionada por el cronómetro. No cambia ningún cartucho.

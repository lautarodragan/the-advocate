---
name: "Las reglas repetidas, en un solo lugar"
description: "Lo que varios agentes dejaron anotado dos o tres veces: las reglas del actor, las constantes del motor, equip y la cola de escapes; cada una a un solo lugar, con las ROMs byte por byte iguales"
type: refactor
assignee: taro
---

Del 2026-10-02, mientras taro no puede revisar nada: un refactor que se
verifica solo. Lo anotaron:

- Cardón (`testing/rust-el-dominio-de-la-pelea.md`): el parámetro del actor
  en su nivel y el equipo sumado están en `rm2k-snes-battle`, en
  `rm2k-snes-screens` y en `port/rules.py`; su lugar es `rm2k-rules`.
- Timbó (`testing/rust-la-emision.md`): las constantes del motor están en
  `engine.rs` de `rm2k-snes-mapdata` y en `events.py`, que leen las pruebas
  de ABL; lo mismo `SUB_MAX`, `PARALLEL_MAX`, `ROUTE_EV_MAX`, `OBJ_PRIORITY`
  y `block_tile`.
- Tataupá (`testing/rust-el-dominio-de-las-pantallas.md`): `equip` en la
  etapa y en el arnés de pruebas; la cola de escapes en el compilador de
  eventos y en `rm2k-snes-text`.

Sale de `main` en `5a93a5ca`. Ahí: `NO_CACHE=1 just cartuchos` da
`abl.sfc` `35c765009320d436…`, 1418 archivos en `rom/build/`;
`just pruebas` 1001, `just -f tools/justfile test` 39.

## Cómo se verifica cada paso

`NO_CACHE=1 just cartuchos` con los crates que se tocan en el `bin/`
local, y el sha256 de todo `rom/build/` —menos el caché, los `.o`,
`sello.txt` y `conversor.log`; el `.dbg` sin `mtime`— contra la base.

Una trampa que apareció a mitad de camino: **el ensamblador global arma
con el runtime del checkout principal**, así que si `main` cambia
`tools/runtime/` mientras uno trabaja, los `.dbg` cambian aunque la rama
no toque nada. Pasó con el merge de Ratona (`main.s`): la base se volvió
a sacar sobre el merge, con el commit en cuestión revertido.

## 1. Las reglas del actor → `rm2k-rules`

`157ecf82`. Quedan en `tools/rm2k/rules/src/actor.rs`: `level_of`,
`curve`, `curve_at`, `points`, `with_equipment`, `PARAM_MAX`,
`EQUIPPED`, `initial_equipment`, `learned_skills`, `level_learned`.
`rm2k-snes-battle` (`rules.rs`) y `rm2k-snes-screens` (`texts.rs`) ponen
arriba sólo qué es un error para cada una; la pelea reexporta lo que la
emisión le pide, para no sumarle a `rm2k-snes-mapdata` una dependencia.

`port/rules.py` se borró: el conversor ya no lo usaba y las pruebas de
ABL, lo único que lo leía, piden los máximos al modelo de la pelea
(`datos.maximos()`). Comparados los 60 actores contra el Python borrado:
iguales.

## 2. Las constantes del motor → `engine.rs`

`bb4fdeda`. **Se eligió preguntarle al ejecutable**: `rm2k-snes-mapdata
engine` contesta por nombre todas las de `engine.rs` y las dos topes de
`record.rs` que mira el conversor (`PARALLEL_MAX`, `ROUTE_EV_MAX`), y
`port/engine.py` las pide una vez por proceso. Por qué ésa:

* es la que ya usan `port/vram.py`, `screen_stage.layout()` y
  `modelo.disposicion()`: no hay mecanismo nuevo;
* el `.sym` sólo existe después de armar, y el conversor las necesita
  antes —`ITEMS_N`, `MESSAGES_STEP`, `ROUTE_FREQUENCY`, los
  disparadores—;
* generarlas de una declaración, como `tools/snes/protocol/`, era pasar
  ciento diez constantes a otro formato para lo mismo.

`events.py` las sigue contestando con sus nombres por un `__getattr__` de
módulo, así que ninguna prueba cambió; donde estaba cada asignación queda
una línea con el nombre, porque los porqués siguen ahí y el runtime y el
`.inc` los citan como "see X in events.py". Una prueba de `engine.rs`
compara la lista que contesta contra sus `pub const`.

`345001f6`: **lo que dibuja una página** (`oam`) lo arma la emisión
(`objects::page_oam`), con lo que `OBJ_PRIORITY`, `OBJ_PRIORITY_ABOVE` y
`block_tile` se fueron de `sprites.py`. El conversor manda el bloque y la
paleta. Cambiaron tres hashes de `rm2k-snes-mapdata`: el mapa inventado
traía unos bytes que ningún bloque da; está explicado en el commit y en
la prueba.

**`SUB_MAX` quedó en dos lados**, a propósito: es del runtime
(`low_ram.s`), no de `engine.rs`, y la copia del conversor la compara
`test_substitutions.py`. Pasarlo al motor es emitirlo en el `.inc` y
sacarlo de `low_ram.s`: cambia el `.inc` y el `.dbg`, y no entraba en un
refactor que tiene que salir igual.

`9826efd1`: al sacar el `block_tile` de Python apareció que la emisión
tenía su propia copia de cuatro números de `rm2k-snes-map-sprites`
—`block_tile`, `OBJ_COLORS`, `SPRITE_POSES`, `POSE_BYTES`— y de los dos
de los glifos del cronómetro. La emisión depende ahora de esa etapa y los
nombra desde ahí.

## 3. `equip` → `rm2k-rules`, y el arnés le pregunta a la etapa

`e9eb697a`. `Game_Actor::ChangeEquipment` es de RM2k: queda en
`rm2k-rules` (`actor::change_equipment`). La etapa la usa para dibujar la
lista y contesta `rm2k-snes-screens equip`; `pantallas.equipar` se lo
pide por `screen_stage.equip`. Se eligió en ese sentido porque la etapa
es la que corre la regla, en Rust, y el arnés ya le pide todo lo demás
de las pantallas.

## 4. La cola de escapes → `rm2k-snes-text`

`e7022dfe`. Queda la de `refit.rs`, y el compilador de eventos depende de
`rm2k-snes-text`; al revés se traería el compilador a la pelea y a las
pantallas, que dependen de `text`. `tests/escapes.json` se mudó con ella
y `events/tests/escapes.rs`, que comparaba las dos copias, se borró. El
porqué de qué escapes compilan sigue en el `escape_tail` del compilador,
que sólo traduce el error.

## 5. Las que aparecieron por el camino

Arregladas, porque eran una línea cada una:

* `8ccdbf82`: `EQUIPMENT_SLOTS` en `engine.rs`, `layout.rs` y
  `compile.rs` → `rm2k-rules`; `ENEMIES_MAX` en `engine.rs` → el de
  `db.rs` de la pelea.
* `1bca3fdc`: `RAIN_COLORS`, `rain_pixels` y `CHOICE_CURSOR` en
  `events.py`, copias sin uso de las de `map-sprites` y del compilador.
  Y antes, en `bb4fdeda`, `wait_after_step`, `wait_after_turn`,
  `fade_step`, `fade_ramp` y `SHAKE_SINE`, también sin uso.

Anotadas y sin tocar:

* **Dos reglas para el nivel inicial en `rm2k-rules`**: `level_of`
  (`initial_level`, un 0 es 1) y `initial_level` (lo mismo, topado contra
  el nivel final). Los parámetros y las habilidades se leen con la
  primera, la experiencia con la segunda; sólo difieren si el nivel
  inicial pasa al final. Unirlas puede cambiar la ROM de un juego así.
* **`port/constants.py`**: `CELL`, `COLUMNS`, `ENEMIES_MAX` y
  `MENU_CGRAM` están también en `engine.rs`; `rpgmaker/lcf.py` tiene
  `EQUIPMENT_SLOTS`; `picture.py` y `animation.py` tienen `GRID` y
  `OBJ_SIDE`, y `picture.py` su propio `block_tile` para el banco de las
  imágenes. Se importan con `from … import` a nivel de módulo: pasarlos a
  `port.engine` obliga a leerlos al importar, o a cambiar cada uso.
* **`ITEMS_N`** está en `compile.rs` del compilador y en `engine.rs`: la
  emisión no depende del compilador.
* **`events.py` y el compilador** siguen compartiendo los códigos de
  comando de RM2k (`codes.rs` contra `event_codes.py`, que sale de liblcf)
  y unas constantes del compilador que leen las pruebas de ABL
  —`WALK_SPEED`, `ENC_RATE`, `ENC_TABLE`, `CELL_DEST_A/B`, `BATTLE_LOSE`,
  `ROUTE_HERO`, `PLACE_BACKDROP` (que además está en `battle_scenes.py`
  y en `scene.rs`)—. Es el mismo arreglo que el de `engine.rs`: que el
  compilador las publique.
* **Contra el runtime**: `STEP_PER_SPEED` y `JUMP_PER_SPEED` de
  `events.py` son tablas que el runtime tiene escritas
  (`chipset_animation.s`, `jump_per_speed`); `SUB_MAX`, ver arriba.
* `rm2k.py` tiene `ANIMATED_*` y `WATER_*`, que también están en
  `engine.rs`; es la copia de Python de `rm2k-rules`, y la ata
  `test_rm2k_rules.py`.

`6501dadf` es la prosa que nombraba las copias que se fueron.

## Los números al final

Sobre el último merge de `main` (`4248d4f4`): `NO_CACHE=1 just
cartuchos`, los 1418 archivos de `rom/build/` iguales a la base sacada
sobre ese merge; `just pruebas` 1005 —las cuatro de más son las de
Ratona—; `just -f tools/justfile test` 39; `cargo test` de `rm2k-rules`,
`rm2k-snes-battle`, `rm2k-snes-screens`, `rm2k-snes-events`,
`rm2k-snes-text` y `rm2k-snes-mapdata` en verde. Cambiaron tres hashes de
pruebas, los de `rm2k-snes-mapdata` en `345001f6`, explicado ahí.

## Al mergear

* **Reinstalar en el global**: `just -f tools/justfile install battle
  screens mapdata events`. `rules` y `text` son bibliotecas: lo que
  cambió de ellas lo usan esos cuatro. Los demás que dependen de
  `rm2k-rules` (`cartridge`, `wally`, `rm2k-snes-audio`,
  `map-background`) sólo ganaron funciones que no llaman, y
  `map-sprites` no se tocó.
* **Python**: se agregó `tools/port/engine.py` y se borró
  `tools/port/rules.py`; son módulos y no scripts, así que
  `install-scripts` no hace falta.
* **El orden importa**: el Python nuevo le pide a `rm2k-snes-mapdata
  engine` y a `rm2k-snes-screens equip`, y manda `draws` en vez de `oam`
  a la emisión: con los binarios viejos en el global, el conversor y las
  pruebas fallan. Instalar antes de correr nada.

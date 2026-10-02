---
name: "Las reglas repetidas, en un solo lugar"
description: "Lo que varios agentes dejaron anotado dos o tres veces: las reglas del actor, las constantes del motor, equip y la cola de escapes; cada una a un solo lugar, con las ROMs byte por byte iguales"
type: refactor
assignee: Cachirla
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

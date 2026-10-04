---
name: "Los ítems de SP en la pelea y las píldoras"
description: "En la pelea no se pueden usar los ítems que recuperan SP, y la Agility Pill no se puede usar en ningún lado: medicinas con SP y los ítems de tipo 8 (los que suben atributos)"
type: bug
assignee: taro
agents: [Mulita]
---

De taro, el 2026-10-04: "no puedo usar items que recuperan SP en batalla, y
no puedo usar la Agility Pill en general".

En ABL (volcado, `data/db/items.json`):

* medicinas (tipo 6) con SP: 3 Magic Ether, 4 Miracle Drop, 8 Pocket
  Shelter, 103 Cheap Wine-SP, 107 Bottle of Health, 125 Bottled Water-SP,
  129 Motor Oil-HPSP, 258 Recharge Draught-SP;
* tipo 8, los que suben atributos: 10 Apple, 11 MP Apple, 12 Powr-Up, 13
  Defensive-Up, 14 Mind-Up, 15 Speed Up, 109 Agility Pill-AGL, 134 Vitality
  Pill-MHP, 259 Agility Potion-AGL, 260 Strength Potion-ATK (estos dos
  últimos además curan HP).

## Mulita, 2026-10-04

Herramientas desde `43b2c5a5`; ABL en el clon `/extras/scratch/mulita/abl`,
rama `mulita-items`, desde `88c00a4`.

### Por qué

* **Las medicinas de SP en la pelea**: `item_usable_in_battle`
  (`rm2k-snes-battle`, `rules.rs`) pedía `recover_hp` o `recover_hp_rate`.
  El blame da `e9441441` (la pelea a Rust), que lo copió del Python; `git
  log -S` lleva a `72109da8` (2026-09-12, "`Use Item` anda"), que lo dice
  en el mensaje: "Quedan afuera las medicinas de SP […]: los SP no son
  estado". Dejaron de ser ciertas con las habilidades (2026-09-13) y nadie
  volvió a la regla. La ROM además no sabía reponer SP en la pelea.
* **Los materiales (tipo 8)**: nunca se implementaron. `item_usable` de
  `rm2k-snes-screens` (`2b017b2e`, que viene de `0b060661` y `ced94647`)
  sólo deja usar medicinas y switches; `la-pantalla-de-items-como-el-original`
  lo anotó: "los materiales […] van en gris […] porque la ROM todavía no
  sabe usarlos".

### Qué hace RM2k (easyrpg)

* Medicina en la pelea: `Item::vExecute` repone HP y SP; el mensaje de
  resultado es uno por parámetro, cada uno en el lugar del anterior
  (`ProcessBattleActionParamEffects`), y el de SP sólo si repuso algo. Antes
  mira `IsItemUsable` (el `actor_set`).
* Material: `Game_Actor::UseItem` sobre uno en pie suma los seis
  `*_points` al `*_mod` del actor y devuelve que sirvió; sobre un caído, nada.
  **No lee `recover_*`**: la Agility y la Strength Potion traen
  `recover_hp_rate` 75 de cuando eran otro tipo —el editor guarda los campos
  que esconde—, y RM2k no las cura. Se hizo como RM2k: suben, no curan.
  `IsItemUsable` dice que no en la pelea: no van en su lista.

### Qué se hizo

* La SRAM pasa a 32 KB, una ranura por banco: la partida de ABL estaba en
  1983 de los 2038 bytes de una ranura de 2048, y lo de los materiales son
  12 bytes por actor que pelea (216). Ver `SRAM_STRIDE`.
* La pelea: `item_usable_in_battle` con SP; `ba_item_use` repone SP
  (`ba_item_sp`); el porcentaje se calcula en dos mitades (`ba_rate_of`), que
  no se pasa de 16 bits con un máximo de más de 655; el cursor de a quién
  mira el `actor_set` (el Motor Oil es de los droides). El mensaje: la línea
  de HP si el ítem cura HP, si no la de SP; con los dos, la de SP en un
  mensaje propio después (`BA_MSG_ITEM_SP`). El modelo de Rust repone SP y
  mira el `actor_set`.
* El menú: los materiales van en blanco y abren la elección de actor;
  `medicine_use` les suma a `FAR_GROWTH` —seis palabras por ranura de
  experiencia— desde la tabla `item_up` del conversor, y `level_param`
  suma eso, con los topes de RM2k: así lo ven el menú, el equipo y la pelea.
  Viaja en la partida y arranca en cero. La elección se redibuja entera
  después de un material, porque puede cambiar un máximo.

RAM: `FAR_GROWTH`, `$7E7D00`-`$7E7EEF` (usa `EXP_K * 12`, 216 en ABL);
`BA_MHPLINE`, `BA_MSP`, `BA_MSP_NEXT` en `$7E7851`-`$7E7854`, dentro de lo
que ya era del mensaje del ítem (`$7E7850`-`$7E785F`). Opcodes: ninguno.

### Verificado

* La tanda de ABL entera, con las herramientas de esta rama (`battle`,
  `screens`, `mapdata`, `convert`, `cartridge`) y la rama `mulita-items`
  del clon, las dos con `main` mergeado: **1094 en verde**. Diez pruebas
  nuevas (cuatro en `test_batalla.py`, seis en `test_materiales.py`), todas
  rojas con las herramientas de `main`. **Ninguna golden cambió**.
* `cargo test` de `rm2k-snes-battle`, `-screens`, `-mapdata`, `-convert` y
  `-cartridge`; `just -f tools/justfile test`: 27. En la misma corrida falla
  `the_layers_are_the_ones_the_python_made` de `wally`, que no depende de
  nada que esta rama toque: heredado, sin bisectar.
* Lo que la tanda no cubre: el SP de un ítem que levanta a un caído (en ABL
  el único es la Pocket Shelter, que no va en la pelea), un material que
  baje un máximo, y que la elección redibujada se vea bien —se mira jugando—.

### Al mergear

Reinstalar en el global `battle screens mapdata convert cartridge`
(`cartridge` por el runtime). Las partidas guardadas viejas no cargan.

## Para taro

En la pelea, usar el Magic Ether o el Bottled Water-SP y ver subir los SP;
la Miracle Drop muestra dos mensajes, HP y después SP. En el menú, la
Agility Pill (y los demás materiales) van en blanco; usarla sube la
agilidad para siempre —se ve en el equipo y en la pelea—. La Agility y la
Strength Potion no curan: RM2k tampoco, el `recover_hp_rate` que traen es
un resto del tipo que tenían antes.

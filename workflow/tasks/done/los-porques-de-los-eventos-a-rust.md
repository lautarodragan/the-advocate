---
name: "Los porqués de los eventos, junto al código en Rust"
description: "Los comentarios largos de cada comando que quedaron en tools/port/events.py pasan al lado de la línea que protegen, en tools/rm2k-snes/events/"
type: docs
assignee: taro
---

Lo dejó anotado Guazú al pasar el compilador de eventos a Rust
(`testing/rust-el-compilador-de-eventos.md`): los porqués de cada comando
—cuánto destrabó, cuándo entró, qué se midió, qué error protege— siguen en
`tools/port/events.py`, pero el código que protegen está ahora en
`tools/rm2k-snes/events/`. La regla de AGENTS.md es que un porqué que
protege una línea va como comentario en esa línea, así que se mudan. Es
sólo prosa: la ROM no puede cambiar.

## Retomada el 2026-09-29

Tordo arrancó y se cortó: un clasificador de seguridad interrumpió su
respuesta mientras escribía los comentarios de `branch_bytes` en
`compile.rs` (el bloque de las condiciones: ítems, preguntas sobre actores,
habilidades, equipo), sin commitear nada. Lo decidido con taro:

- se sigue con **todo lo demás**, incluidos los ~1.027 renglones de porqués
  que el borrado de Guazú (`1487129f`) se llevó junto con el compilador de
  Python: están en `git show 1487129f^:tools/port/events.py`;
- **el bloque de `branch_bytes` no se escribe**: queda con los comentarios
  cortos de Guazú y un puntero a ese commit;
- si el clasificador vuelve a cortar, el agente no busca la vuelta: avisa, y
  Hornero —con aviso a taro— aplica a mano el comentario en el worktree.

Lo que dejó Tordo, sin commitear, está en su worktree
(`agent-a3eccaf0086f4b17e`): comentarios ya mudados a constantes y
bloques de `compile.rs`. Su mapeo de qué se queda en Python, qué va a los
dos lados y qué va sólo a Rust está en su informe, copiado abajo por
Hornero.

### El mapeo de Tordo

- **Se queda en Python** (el código sigue ahí): el fundido, `PAUSE_FRAMES`,
  `STEP_PER_SPEED`, `JUMP_*`, el modelo de la lluvia, las notas de `KEY_*`,
  `CELL_*`, `TEST_SWITCH`, `CASE_VARIABLE`, `SWITCH_IMPOSSIBLE`, `ENC_*` y
  `Encounters`, `PartyState`, `database`, `Pictures`, `SHAKE_SINE`.
- **Va a los dos lados** (el código existe en los dos): `escape_tail`, el
  encabezado de los mensajes y `MESSAGES_STEP`, la frecuencia de las rutas,
  la numeración de `Songs`, `BATTLE_PACKAGE`, los disparadores y el
  encabezado de las tropas, `encounter_backdrop`, `picture_fits`,
  `MapEvents` (los 39 mapas).
- **Va sólo a Rust**: el resto.
- **No va a ningún lado**: las dos advertencias de "el número se elige
  mirando los que hay" (OP_ACTOR_SPRITE, OP_PLACE_VAR), que ya cubren
  AGENTS.md y `test_no_opcode_shares_a_number_with_another`.
- **Constantes de Python muertas**: `CHOICE_CURSOR` no la usa ningún código;
  `SHOW_PICTURE` sólo adentro de `events.py`.
- **Los comentarios de los opcodes** van al brazo de `compile.rs` que emite
  cada uno, no a `events.toml`: `protocol` descarta los comentarios del
  TOML, su README dice que qué hace un opcode se escribe a mano, y esos
  comentarios nombran el juego, que `protocol` no puede conocer.
- El docstring del módulo `events.py` (renglones 20-21) dice que los porqués
  siguen al lado de cada constante: se actualiza cuando se muden.
- Tordo borró sin reponer, en su worktree, una línea de Guazú que estaba
  mal pegada al doc de `ITEMS_N` (el tope de oro): hay que reponer ese dato
  en `CHANGE_GOLD`.

Su diff sin commitear está guardado en
`<scratchpad>/porques-tordo/tordo-parcial.diff`: sirve de punto de partida,
salvo que toque el bloque de `branch_bytes`.

## Hecho por Churrinche, el 2026-09-29

Partió del diff de Tordo (aplicado con `git apply`, revisado: la línea
del tope de oro volvió a `ChangeGold`, y un `[`refresh`]` que rustdoc
marcaba como enlace a un privado quedó en `` `refresh` ``). Cuatro
commits, de a archivo de Rust o grupo:

- `compile.rs`, más `game.rs` (los términos de la posada) y `lib.rs`
  (los eventos comunes de equipo): cada porqué al brazo de
  `compile_command` que emite su opcode, o a la constante, la función o
  el renglón del bucle de la página que protege;
- `route.rs`: las órdenes de ruta, `decode`, `min_frequency`, `own`;
- `registry.rs`, `messages.rs` y `pages.rs`;
- `troops.rs` e `indices.rs`, con el `cargo fmt` de `pages_of`, que
  venía de main sin formatear y dejaba `cargo fmt --check` en rojo.

**Al mergear hay que instalar sólo `events`**: `just -f tools/justfile
install events`. Es sólo prosa, pero el binario se rearma.

### Lo que cambió del plan: el runtime cita a events.py

El mapeo de Tordo decía "va sólo a Rust: el resto". Al borrar apareció
que **el runtime y `mapdata.inc` citan a events.py por nombre**: "see
OP_KEY in events.py", "see VAR_REFRESH in events.py", "See
`ChangeScreenTransitions` in tools/port/events.py", unos treinta. Borrar
esas notas deja las citas colgando, y arreglar las citas cambia los
`.s` —y con ellos el `.dbg`— y `mapdata.py` —y con él el `mapdata.inc`
de cada cartucho—: deja de ser sólo prosa y `rom/build/` deja de salir
igual. Así que **lo citado queda en los dos lados**: en events.py, como
estaba, y copiado entero en el crate. Son el giro (TURN), las
transiciones, `VAR_REFRESH` y las variables, `VAR_CHARACTER`,
`OP_ITEM`, `ACCESS_BIT` y `ChangeEscapeAccess`, `OP_WEATHER`,
`OP_ANIMATION`, `OP_BATTLE` y `BATTLE_LOSE`, la imagen, `OP_ACTOR_SPRITE`,
`OP_KEY`, `OP_PLACE_VAR`/`OP_LOCATION`, `OP_SAVE`, `SKILL_SLOT`,
`PARTY_COMMON_EVENTS`, `MESSAGES_STEP`. El docstring del módulo lo dice.
Cuando alguien toque esos `.s` por otra razón, puede apuntarlos al crate
y borrar la nota de acá.

De events.py salió sólo lo que nadie cita y ya es sólo del crate:
`CHANGE_EVENT_LOCATION`, `TILE_SUBSTITUTION`, `SHOW_MESSAGE`, la ruta
forzada, `FLASH_SPRITE`, `WEATHER_EFFECTS`, `PLAY_SOUND`,
`SHOW_BATTLE_ANIMATION`, `SHOW_PICTURE`, `OPEN_SHOP`, `TIMER_OPERATION`,
el bloque de los opcodes salvo `OP_SAVE`, el desplazamiento de
`OP_MESSAGE`, la vida y el HP, la tienda, el sonido, `HaltAllMovement`,
los parámetros de `EnemyEncounter`, las ramas de la pelea y la lista de
`TROOP_COMMANDS`. Y volvió uno: el encabezado de los encuentros
aleatorios, que el borrado se llevó y protege a `Encounters`, que sigue
en events.py.

### Cuánto

Medido con `git diff` sobre los cuatro commits: al crate entran 2257
renglones de comentario y salen 235 —los cortos de Guazú que se
reemplazaron por el porqué entero, reenvueltos a otro ancho—; de
events.py salen 369 y entran 44 —el docstring y el encabezado de los
encuentros—. El borrado de Guazú se había llevado 1027 renglones `#`;
`b0001b6b` repuso unos 170.

### Lo que no fue a ningún lado, y por qué

- **Los porqués largos de las condiciones** —la tabla de cuánto
  destraba cada tipo, las preguntas del actor, el docstring y los
  comentarios de `branch_bytes`, `OP_IF_VAR`, `OP_IF_ACTOR`—: por la
  restricción del clasificador. `branch_bytes` tiene un renglón que
  apunta a `git show 1487129f^:tools/port/events.py`, y los que estaban
  en el events.py de hoy (`COND_*`, `OP_IF_VAR`, `OP_IF_ACTOR`) siguen
  ahí, sin tocar. El `OP_IF` sí fue: al brazo de `COND_BRANCH` del bucle
  de la página, que está fuera de `branch_bytes`.
- **Las dos advertencias de "el número se elige mirando los que hay"**
  (`OP_ACTOR_SPRITE`, `OP_PLACE_VAR`): las cubren AGENTS.md y
  `test_no_opcode_shares_a_number_with_another`. Se borraron también de
  events.py.
- **Viejas, que describen un estado que ya no existe**: la deuda de
  `ChangeItems`/`ChangeGold` de antes del inventario ("nobody reads the
  inventory"), la frase de `ShowBattleAnimation` que decía que la ROM no
  dibuja animaciones, y la nota de `CONTROL_VARS` sobre "la lista de
  acá".
- **Lo que protegía código de Python que ya no existe**: el docstring de
  `Messages.tail`, el campo `visible` de `MapEvents`, "Returns copies" de
  `troop_commands` —en Rust la entrada es inmutable—, `_Commands`, los
  `index_*` (cuándo los llama el conversor), `ENC_DEFAULT_STEPS`, y que
  los `se_*` se lean al usarse y no al importar.
- **Lo que decide el conversor y no el crate**: la página imposible por
  ítem y `SWITCH_IMPOSSIBLE`, el gráfico y el `tile_pass` de cada página.

### Tres cosas que se mudaron tal cual y parecen mal

Se copiaron enteras porque la tarea era sólo mudar; quien las lea con
el código al lado puede decidir:

- `OP_LOCATION` dice "when **recalling** bits 7, 6 and 5 are the
  VAR_REFRESH of each of the three writes", pero los bits los pone
  `MemorizeLocation`, que es el que escribe las variables.
- `can_trigger` dice que la acción sobre la celda propia "we do not do
  those", y el comentario de abajo dice que se hace desde el 2026-09-07.
- El brazo de `ChangeEquipment` dice que las tropas "this port does not
  run", y desde el 2026-09-21 las corre; el de la pelea sin manejadores
  dice que `ChangeEscapeAccess` "is accepted and not done", y hoy se
  guarda.

### Verificación

- `cargo test -p rm2k-snes-events`, `cargo fmt --check` y `cargo doc`
  sin advertencias.
- `NO_CACHE=1 just cartuchos`: los 999 archivos de `rom/build/` —sin el
  caché, los `.o`, `sello.txt` ni `conversor.log`, y el `.dbg` sin
  `mtime`— iguales a los de antes de empezar.
- `just pruebas`: 872 en verde; `just -f tools/justfile test`: 88 en
  verde. Las dos sobre el árbol final, con `events` reinstalado.

Lo que taro tiene que mirar no es jugar: es leer el diff de los
comentarios, sobre todo las tres cosas de arriba.

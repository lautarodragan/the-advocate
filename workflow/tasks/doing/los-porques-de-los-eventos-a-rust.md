---
name: "Los porqués de los eventos, junto al código en Rust"
description: "Los comentarios largos de cada comando que quedaron en tools/port/events.py pasan al lado de la línea que protegen, en tools/rm2k-snes/events/"
type: docs
assignee: Churrinche
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

---
name: "La guarda de los bancos"
description: "Una prueba que recorra el .dbg y marque todo jsr/jmp absoluto que cae en otro banco y toda lectura absoluta de ROM fuera del banco 0: la regla de main.s que el ensamblador no revisa"
type: feature
assignee: Ratona
---

Lo propuso Pepitero (`testing/el-banco-1-se-lleno.md`), sin hacerlo: el
script descartable con el que verificó las mudanzas a `FAR2` dio 0 antes y
después de cada una, y la regla de dónde va el código (encabezado de
`tools/runtime/main.s`) "nada de esto lo revisa el ensamblador". Un `jsr` a
una rutina de otro banco salta al lugar equivocado sin ningún error.

## Lo hecho (2026-10-02, Ratona, sobre `5a93a5ca`)

`rom/pruebas/herramientas/test_saltos_entre_bancos.py`, sobre los tres
cartuchos. Python del arnés, sin desensamblador aparte: **el `.dbg` de
`ld65` ya trae lo que hace falta.** Cada `sym` dice en qué líneas se lo nombra
(`ref=`), y cada `line` qué bytes salieron de ella (`span=`, con `ooffs` en
el `seg` para ir al archivo). Así que no se lee el operando del fuente con
una expresión regular, como el script de Pepitero: se lee el opcode en la ROM,
que dice el modo, y se compara adónde va la instrucción con dónde está el
símbolo. Lo único que hubo que escribir del 65816 es la tabla de modos de los
256 opcodes. El fuente se lee sólo para el mensaje.

Lo que revisa, de cada instrucción que nombra una etiqueta (o un `=` que cae
en la ROM o en un registro):

* `jsr`/`jmp` absolutos: que el destino esté en el banco de la instrucción;
* `jsr`/`jmp (tabla, x)`: que la tabla esté en el banco de programa, **y que
  cada entrada caiga en una etiqueta de ese banco** —es lo que dice el
  comentario de `opcode_handlers`—. La tabla va de su etiqueta a la
  siguiente;
* `jmp (abs)` y `jml [abs]`: que el puntero esté en el banco 0;
* lo largo (`f:`, `jsl`, `jml`): que el banco escrito sea el del símbolo,
  con los espejos `$00`/`$80` y `$01`/`$81` resueltos;
* lo absoluto de datos —lecturas **y** escrituras—: que el banco de datos
  con que corre ese código, más la dirección, sea el lugar del símbolo. Los
  espejos están resueltos: la WRAM baja se ve igual desde `$7E` y desde el
  banco 0, y los registros no se ven desde `$7E`.

**El banco de datos no se sigue: se dice.** `BANCO_DE_DATOS` en la prueba:
`$7E` para los ocho `battle*.s` que corren en la pelea y para
`encounters.s` —los dos lo dicen en su encabezado—, y el 0 para todo lo
demás. **La única excepción** es una rutina: `scene_cgram_restore` vive en
`battle_scene.s` pero la llama `back_from_battle`, desde el banco 0, con el
banco de datos en 0 —lo dice su comentario—, y escribe `CGADD` y el DMA con
direcciones absolutas. Con la tabla por archivo, la prueba la marcaba (siete
líneas, todas registros). Otra prueba del mismo archivo se fija que todo lo
nombrado en `BANCO_DE_DATOS` exista, para que un renombre no la deje sin
efecto callada.

Lo que **no** ve, y lo dice su docstring: lo que cambia el banco de datos a
mitad de camino (los puentes `ba_t_*`, el intérprete con el del bytecode), lo
que se direcciona por un puntero, y que a lo que se entra con `jsl` se salga
con `rtl`.

**`FAR2` con `+ FAST` no hace falta revisarlo**: lo probé cambiando el `jsl
f:battle_run` de `op_battle` a `+ FAST`, y `ld65` se niega a linkear —"Range
error"—, porque `$C0 + $80` no entra en 24 bits. Queda dicho en `main.s`.

### El rojo que vi

Con cuatro roturas a la vez, cada una en los tres cartuchos (`release`,
`test-special`, `test-encounter-every-step`), y la prueba las marcó todas:

    battle_loop.s:417  jsl f:exp_add -> jsr exp_add
      "en `ba_exp_allocate` ($C01ECC): `jsr exp_add`. `exp_add` está en el
      banco $01, y un jsr no cambia de banco: salta a $C0:8805. Entre bancos
      va jsl, con un rtl o una entrada `_l`."
    battle.s:313       lda f:actor_txt, x -> lda actor_txt, x  (con $7E)
      "`actor_txt` está en $00F3CD, y con el banco de datos en $7E esto va a
      $7EF3CD: lo que no está en ese banco va con `f:`."
    shop.s:74          lda f:item_id, x -> lda item_id, x
      "`item_id` está en $C3FFE4, y con el banco de datos en $00 esto va a
      $00FFE4 …"
    interpreter.s:80   op_reserved_39 = op_done -> = exp_add
      "`jmp (opcode_handlers, x)`. Las entradas de `opcode_handlers` se
      saltan en el banco $00, y éstas no caen en una etiqueta de ahí: $8805
      (`exp_add` en $018805)."

Después, con la versión final, otra vez las dos primeras. Todo vuelto atrás.

**Un error propio que la prueba ahora cuida**: la primera versión no le
sacaba el `\n` al último campo de cada renglón del `.dbg`, que es `type=lab`,
así que no reconocía ninguna etiqueta y daba cero revisando casi nada. Por
eso la prueba exige haber mirado al menos una instrucción de cada clase
(salto, tabla, largo, datos).

## Los números

Sobre el `main` de hoy da **cero** en los tres cartuchos. `abl.sfc` de
`release`: `35c76500…`, el mismo de Pepitero. El comentario de `main.s` no
mueve la ROM: `NO_CACHE=1 just cartuchos` antes y después, los tres `.sfc` y
los tres `.msu` byte por byte iguales.

## Al mergear

No hay nada que instalar: la prueba es Python del arnés, y `main.s` cambia
sólo un comentario. (Para ver el rojo instalé `cartridge` en el `bin/` local
del worktree, porque el ensamblador global arma con el runtime del checkout
principal; eso no viaja.)

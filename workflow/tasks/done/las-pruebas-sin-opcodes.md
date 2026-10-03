---
name: "Las pruebas de ABL, sin opcodes"
description: "Que ninguna prueba de Python necesite los números del bytecode: las que arman bytecode a mano pasan a casos con comandos de RM2k, las que revisan lo que compiló pasan a Rust, y las que decodifican la música se lo piden al binario de audio"
type: refactor
assignee: taro
---

De taro, el 2026-10-02, antes de pasar los bytecodes a Rust: "¿no tendría
más sentido resolver los 3 puntos primero, y luego hacer los cambios a
protocol?". Hoy el arnés tiene `rom/pruebas/arnes/event_opcodes.py`
generado por `protocol`, y las pruebas usan los números para tres cosas:

1. **Armar bytecode a mano** e inyectarlo (`test_posada.py`, …): pasan a
   casos escritos con comandos de RM2k (`rom/pruebas/casos/`) que compila
   el compilador de verdad. Las que arman a propósito algo que el
   compilador nunca emitiría pasan a pruebas del crate o se tiran.
2. **Revisar el bytecode que compiló** (`test_paginas.py`, …): prueban el
   compilador, y van a las pruebas de `rm2k-snes-events`.
3. **Decodificar el stream de música** (`musica.py`): se lo pide a
   `rm2k-snes-audio decode`.

Cuando esto termine, la tarea siguiente es declarar los dos bytecodes en
Rust y dejar `protocol` y sus TOML: `todo/los-bytecodes-en-rust.md`.

## El conteo, antes de tocar nada (Cotorra, 2026-10-02)

Contado con `tokenize` sobre todos los `.py` de `rom/`: un nombre `OP_*`,
`OPCODE_SIZE`, `opcode_size` o `event_opcodes` **en código**, no en
comentarios ni docstrings. Son **6 archivos de prueba y 11 pruebas**, más
`arnes/events.py`, que los reexporta:

| archivo | pruebas | tipo |
|---|---|---|
| `herramientas/test_paginas.py` | 6: el Tram Officer, las dos del refresco después de un `Teleport`, las tres de `OP_CELL_TEST` | 2 |
| `rpgmaker/test_posada.py` | 1: la página del bum byte por byte | 2 (página de ABL) |
| `rpgmaker/test_game_over.py` | 1: la derrota del jefe va a `BATTLE_LOSE` | 2 (página de ABL) |
| `rpgmaker/test_eventos_de_tropa.py` | 1: el despegue pide su efecto, leyendo el bytecode de la tropa **en la ROM armada** | 2 |
| `herramientas/test_protocolo_contra_el_juego.py` | 3: el módulo al día, la tabla del despacho contra la ROM, los largos en todo el juego | — / ROM / 2 |
| `arnes/events.py` | `from event_opcodes import *`, `walk_code`, `CELL_DEST_A/B` | arnés |

Lo que **no** hay, y el encargo suponía:

* **Tipo 1, bytecode armado a mano e inyectado: ninguna.** `test_posada.py`
  no inyecta nada: compara la página del bum, compilada por el compilador
  de verdad, contra bytes escritos a mano. Es tipo 2.
* **Tipo 3, decodificar la música: ya está.** `arnes/musica.py` le pide
  todo a `rm2k-snes-audio decode` desde el 2026-10-01 (`--unfold` incluido),
  y `consola.py` lo usa por ahí. Los `OP_END` y `OP_REPEAT` que quedan son
  comentarios. Al binario de audio no le falta nada.

Comentarios que nombran un opcode: unos 25 archivos (`events.py`, `consola.py`,
`musica.py`, `tanda.py`, `animation.py`, `test_curar.py`…). Se quedan.

## Qué pasa con cada una

* **`test_paginas.py`**: las dos del refresco (`la_escritura_despues_de_saltar…`
  y su control) y las tres de la celda pasan a `compile.rs` de
  `rm2k-snes-events`: `a_write_after_jumping_to_another_map_asks_for_the_refresh`,
  `without_jumping_a_write_asks_for_the_refresh_if_the_map_looks`,
  `the_four_of_the_cell_go_in_one_opcode`,
  `the_else_of_the_inner_branch_comes_from_its_destination` y
  `without_the_exact_shape_it_is_not_fused`. Usaban los mapas 6, 49 y 133 de
  ABL sólo como contexto —quién mira la 123, qué ranura tiene cada
  variable—, y en Rust el contexto es un mapa de juguete que mira la 123 o
  no. La del Tram Officer **depende de ABL** (mapa 9): se queda, mirando que
  la página compila y que sus variables tienen ranura; lo que perdió es el
  `OP_VAR in codigo`, un byte suelto que podía estar como operando de
  cualquier otro, y que `ControlVars` compile a `OP_VAR` lo cubre el juego
  chico del crate (`tests/python.rs`).
* **`test_posada.py`**: no era tipo 1 sino 2. Se queda
  `test_la_pagina_del_bum_compila` (**depende de ABL**: mapa 20, evento 4),
  y el byte por byte pasa a
  `an_inn_with_a_price_is_its_greeting_a_choice_and_a_gold_branch`, con la
  misma forma: un mensaje y la posada a 5.
* **`test_game_over.py`**: `test_la_derrota_del_jefe_apunta_al_game_over` se
  tira. Lo que miraba ya lo mira `escaping_with_escape_mode_1_ends_the_page`
  —`escape_mode` y `defeat_mode` en 0, que es la forma de las del jefe, da
  `[9, 9, BATTLE_LOSE]`—, y que las tres del jefe compilen sigue en
  `test_las_tres_paginas_del_jefe_compilan`, que **depende de ABL**.
* **`test_eventos_de_tropa.py`**: `test_el_despegue_pide_su_efecto` leía el
  bytecode de la tropa en la ROM armada y buscaba `OP_SOUND` con el índice
  del `Thunder9`. Pasa a `test_el_despegue_toca_su_efecto`, que **lo oye**:
  pelea, turno 1, y entre las órdenes y el mensaje de la página arranca una
  voz de efectos con la muestra y los cuadros de la fila del `Thunder9` en
  `sound_table` —como `test_sonido_en_ruta.py`—. Prueba más que antes: que
  el índice llegue a sonar, no sólo que esté escrito.
* **`test_protocolo_contra_el_juego.py`**:
  * `test_el_modulo_de_los_opcodes_esta_al_dia` se va con el módulo;
  * la de la tabla del despacho saca los números de **los símbolos del
    cartucho**: cada `OP_X` cuyo `op_x` existe es un opcode de eventos
    —los de música no tienen manejador—. Sobrevive a la tarea siguiente,
    porque el `.inc` lo va a seguir definiendo, lo escriba quien lo escriba;
  * la de los largos en todo el juego pasa **adentro del compilador**:
    `whole_instructions`, en `compile_page`, recorre cada página que emite
    por los largos declarados y, si no cae justo en el final, para la
    conversión —es un error del compilador, no de la página—. Así lo mira
    cada `just cartuchos`, con las tres mil y pico de ABL. En Python queda
    que el juego entero pase por ahí (**depende de ABL**), y en Rust
    `a_page_that_does_not_walk_by_the_declared_sizes_stops_the_conversion`.
* **`arnes/events.py`**: sin el reexport, sin `walk_code` y sin
  `CELL_DEST_A/B`, que sólo usaban las de la celda.
* **`arnes/event_opcodes.py`** borrado. La receta que lo generaba ya no
  existía: desde el conversor en Rust lo regeneraba a mano quien cambiara
  `events.toml`, y lo cuidaba la prueba que se fue con él.
* **La guarda**: `test_ningun_py_de_abl_nombra_un_opcode_en_codigo`, en
  `test_lado_de_abl.py`, con `tokenize`: falla con un `OP_…`,
  `OPCODE_SIZE`, `opcode_size` o `event_opcodes` en código de `pruebas/`,
  `parches/` o `data/`; en comentarios y strings no.

## Visto fallar

Rompiendo el compilador o el runtime a propósito, uno por vez:

* `Teleport` sin `after_jump` → rojo
  `a_write_after_jumping_to_another_map_asks_for_the_refresh` (y
  `erasing_the_event_after_a_jump_is_nothing`, que ya estaba);
* `refresh` pidiéndolo siempre → rojo su control;
* los dos destinos de la celda cruzados → rojo
  `the_else_of_the_inner_branch_comes_from_its_destination` (la de sin
  `else` no lo ve: ahí los dos destinos son el mismo, igual que en Python);
* el "Yes" de la posada contado desde cero (`14` en vez de `length + 14`) →
  rojo la de la posada;
* el índice del `Thunder9` corrido en uno, sólo para ése → rojo
  `test_el_despegue_toca_su_efecto` (no arranca ninguna voz con su muestra);
* `.addr op_big_show` y `.addr op_big_move` cruzados en
  `event_opcodes.inc` → rojo la de la tabla del despacho en los tres
  cartuchos;
* `OP_SWITCH` sin el byte del valor cuando apaga → `just cartuchos` se
  para en la conversión: "the compiler emitted a page that does not walk by
  the declared sizes". **Ojo con lo que esto no ve**: un byte de más o de
  menos que sea un cero casi siempre pasa, porque `0x00` es `OP_DONE` y el
  recorrido lo absorbe —lo probé primero con la posada y pasó—. La prueba de
  Python que se fue tenía el mismo punto ciego.
* La guarda: un `.py` con `events.OP_DONE` en código da rojo con su línea;
  el mismo nombre en un comentario o en un string, no.

## Números

* `NO_CACHE=1 just cartuchos`, antes y después: los 1.418 archivos de
  `rom/build/` iguales, `abl.sfc` `35c765009320d436…`. La ROM no cambia: no
  sumé casos.
* `just pruebas`: **993** (eran 999: siete pruebas se mudaron a Rust o se
  tiraron, y se sumó la guarda).
* `just -f tools/justfile test`: **36**, igual.
* `cargo test -p rm2k-snes-events`: 63 de la biblioteca (eran 56: las siete
  nuevas), y las de integración iguales.

## Qué instalar al mergear

`just -f tools/justfile install events`: el compilador ahora recorre cada
página que emite. Lo de Python no hace falta: no se renombró ni agregó
ningún script, sólo se borró `arnes/event_opcodes.py`, que no es un script
instalado.

## Lo que queda para la tarea siguiente

* La receta `protocol` de `tools/justfile` todavía dice que un juego puede
  generarse su propio módulo con `--python`; nadie lo hace ya. Se va con
  `protocol`.
* `test_protocolo_contra_el_juego.py` saca los números de los símbolos del
  cartucho (`OP_X` con su `op_x`): cuando el `.inc` lo escriba
  `rm2k-snes-assemble`, sigue andando sin tocarla.

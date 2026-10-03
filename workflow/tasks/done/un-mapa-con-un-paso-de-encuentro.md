---
name: "Un mapa con un paso de encuentro rompe el ensamblado"
description: "encounter_steps = 1 da enc_base 65536, que no entra en un .word: --test-encounters 1 no arma"
type: bug
assignee: taro
---

Lo encontró Surubí el 2026-09-29 al pasar las tablas de pelea a Rust
(`testing/rust-el-piloto-de-la-pelea.md`): un mapa con `encounter_steps` 1
da `enc_base` 65536, que no entra en un `.word`. El Python lo emitía igual y
el Rust lo reproduce a propósito, porque su prueba fija la salida del
Python. Ningún mapa de ABL tiene 1, pero `--test-encounters 1` rompería el
ensamblado. Arreglarlo cambia la salida en ese caso, así que va aparte:
decidir qué hace RM2k con un paso (¿un encuentro por paso?) y emitir algo
que entre.

## Tomada el 2026-09-29

Hornero miró easyrpg (`Game_Player::UpdateEncounterSteps`): la chance por
paso es `1/encounter_steps` por un factor que crece con lo caminado, así que
con 1 da 100% o más: pelea en cada paso. No hay nada que decidir: la chance
tiene que saturar en el máximo en vez de desbordar. Ningún mapa de ABL usa
1, así que la ROM de ABL no cambia; el caso de prueba es
`--test-encounters 1`.

## Cómo lo usa la ROM, y dónde se arregla (Calandria, 2026-09-29)

`enc_base` es `65536 // pasos`, una palabra por registro de encuentros.
`encounter_map` la copia a `ENC_BASE` al entrar al mapa, y
`encounter_steps` —el cuerpo de `OP_ENCOUNTER_STEPS`— la pisa con la del
operando. En cada paso, `encounter_step` sube de fila con `ENC_N` contra los
umbrales, y corre la base según el `pmod` de la fila: a la derecha 4 a 1 veces
en las filas 0 a 3, a la izquierda 1 a 4 en las 4 a 7. **Si el corrimiento a
la izquierda acarrea, es "siempre"**, sin tirar el dado —el `PercentChance`
con chance >= 1—; si no, pelea si el xorshift da menos que eso.

La cuenta con 1 paso: los umbrales son `ceil(fila / 100)` = 1, 1, 1, 1, 2, 2,
2, así que en el primer paso —`ENC_N` = 1— ya está en la fila 4, `pmod` 2. En
easyrpg: `ratio` = 100 / 1 = 100, la misma fila, `p = 1 * 2 * 1` = 2, siempre.
En la ROM: `$FFFF << 1` acarrea, siempre. Y como `ENC_N` vuelve a 0 con cada
encuentro y el paso siguiente lo pone en 1, **las filas 0 a 3 nunca se tiran
con un paso**; si se tiraran, `$FFFF >> k` es `$10000 >> k` menos una parte en
65536. Así que **alcanza con saturar en `$FFFF` en lo que se emite**, y el
runtime no se toca. Con 2 pasos la base es `$8000`, que ya entra.

Son tres copias, y las tres saturan igual: `base` en `rm2k-snes-battle` (las
tablas del mapa), `enc_base` en `rm2k-snes-events` (el operando de
`ChangeEncounterSteps`, que con 1 **no compilaba**: `word` se negaba) y
`enc_base` en `tools/port/events.py` (el modelo). La prueba de `battle` que
fija el texto del Python, `the_encounters_of_the_game_are_the_pythons`,
cambió a propósito: su juego tiene el mapa 5 con 1 paso. El hash nuevo es el
del texto del Python con ese `.word` de 65536 a 65535 y nada más —verificado
contra el texto guardado del piloto—.

La prueba de la ROM es un cartucho nuevo, `test-encounter-every-step`: el
mapa 21 y el grupo del encuentro de `test-special`, con `--test-encounters
1`. Su caso, `encuentro-cada-paso`, es una copia de `grupo-11-12-13` y no
el mismo: un caso en dos cartuchos tiene que estar en el que lleva todos
(`test_un_caso_que_esta_en_dos_corre_en_el_que_lleva_todos`), y ése no
está en `release`. Así que va en `excluded_cases`. Antes del arreglo no ensamblaba (`Range error (65536
not in [0..65535])`); después, `test_encuentro_cada_paso.py` camina para
arriba y la pelea sale al primer paso. Con el cartucho cambiado a
`test-special` la misma prueba da rojo con "8 pasos", que es el control.

## Al mergear

Reinstalar en el global `battle` y `events`: `just -f tools/justfile install
battle events`. El cartucho nuevo lo arma `just cartuchos` solo. En `abl.sfc`
no hay nada que jugar, porque sale igual. Lo único que queda para taro, si
quiere, es mirar `rom/build/tests/encounter-every-step/prueba.sfc`, donde
cada paso en el mapa 21 es una pelea.

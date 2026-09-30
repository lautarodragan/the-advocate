---
name: "Un mapa con un paso de encuentro rompe el ensamblado"
description: "encounter_steps = 1 da enc_base 65536, que no entra en un .word: --test-encounters 1 no arma"
type: bug
assignee: Calandria
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

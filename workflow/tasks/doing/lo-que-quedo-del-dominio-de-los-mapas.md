---
name: "Lo que quedó del dominio de los mapas"
description: "Los cabos sueltos que dejó Mara al pasar los mapas a Rust"
type: refactor
assignee: Ceibo
---

De `testing/rust-el-dominio-de-los-mapas.md` (Mara, 2026-09-30):

- que `rm2k-snes-events scan` conteste los blancos de ruta de cada página,
  así `movable_events` sale de Python;
- los repartos de VRAM (`tools/port/vram.py`) en un solo lado: hoy los leen
  las pantallas y la emisión;
- la regla de los colores del cronómetro está dos veces: `timer_colors_of`
  en Python y `timer_colors` en `extras.rs`;
- sacar `voodoo` de la huella de `cartridge`: el conversor ya no corre el
  binario, la etapa de mapas lo usa como biblioteca (entra por el binario
  de `rm2k-snes-maps`);
- decidir si `rm2k-snes-maps layers` se queda: hoy sólo lo usan sus
  pruebas;
- el camino de los translúcidos tramados (`TRANSLUCENT_MODE=dither`) está
  portado pero ningún cartucho lo ejercita;
- los avisos de clippy de los tres crates.

Fuera del encargo: los repartos de VRAM (`vram.py`) quedan como están —son
de la emisión, y Cardón, que pasa la pelea a Rust, puede necesitarlos—.

## Hecho (Ceibo, 2026-09-30)

Base: `968af650`. Cada punto en su commit; la ROM y todo `rom/build/`
—1032 archivos, con el script de huellas de Mara— iguales después de cada
uno, con `NO_CACHE=1 just cartuchos`.

### 1. Quién camina sale de Python

`rm2k-snes-events scan` —y `compile`, que arma los mismos registros—
contesta en cada página `route_targets`: los eventos a los que su código
manda una ruta, recorriendo el bytecode (`instructions`, al lado de
`size_of` en `compile.rs`). La regla de quién se mueve —las rutas, la ruta
propia, los quietos que animan con su tope de cuatro, los que giran— pasó
a `rm2k-snes-maps`, en `moves.rs`: el pedido lleva los registros del scan
tal como salieron (`pages`) y los que manda a caminar una página de prueba
(`also_walk`), y la respuesta trae `movable`, `animates_still` y
`turning`, que `map_convert` lee para la tabla de NPC. Se fueron
`movable_events` y `ANIMATES_STILL_MAX` de `sprites.py` y
`events.route_targets`.

Cómo se verificó: antes de borrar el Python, `map_convert` comparó lo que
contestaba la etapa contra `movable_events` en cada mapa de los tres
cartuchos (102 llamadas) con un `assert`: iguales todas. Las pruebas de
`events` comparan contra hashes del Python viejo que no se regeneran, así
que `route_targets` se saca antes de hashear y tiene su prueba, con los
valores contrastados contra la regla de Python; `moves.rs` tiene las suyas
(sin juego).

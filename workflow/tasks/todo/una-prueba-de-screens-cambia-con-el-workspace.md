---
name: "Una prueba de screens da distinto con el workspace entero"
description: "the_boxes_of_the_maps_and_the_common_events da 4 cajas con cargo test -p rm2k-snes-screens y 5 con cargo test --workspace, desde el merge de las caras y los escapes (3f34ca23)"
type: bug
agents: [Hornero]
---

Visto el 2026-10-06 al mergear lo de Mulita y Carpintero. Bisectado: en
`ea1c5beb` (el padre) pasa con el workspace entero, en `3f34ca23` falla
(`left: 5, right: 4`, `screens/tests/python.rs:327`). Con `-p
rm2k-snes-screens` solo, pasa. ABL no cambia (la tanda en verde, la misma
huella), y los binarios se instalan crate por crate, así que la ROM la arma
el comportamiento de `-p`.

La diferencia entre las dos corridas es la unificación de dependencias y
features del workspace: `serde_json` con `preserve_order` (lo piden
`rm2k-snes-audio` y `convert`) es el sospechoso, junto con el
`without_waits` de `text/src/refit.rs`. No se siguió, por el límite de uso.

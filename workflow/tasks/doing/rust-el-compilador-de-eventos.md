---
name: "Rust: el compilador de eventos"
description: "tools/port/events.py (páginas de evento a bytecode) como crate propio en Rust, sobre la biblioteca de Ditto y rm2k-rules, con las ROMs byte por byte iguales"
type: refactor
assignee: Guazú
---

La pieza más cara del conversor, charlada con taro el 2026-09-29: el
compilador de eventos va a un crate propio, porque la frontera es real —de
páginas de RM2k a bytecode, con el protocolo declarado en
`tools/snes/protocol/events.toml`— y porque es lo que más gana con Rust.

Se apoya en lo que ya existe: la biblioteca de Ditto para leer el volcado,
`rm2k-rules` para las reglas de RM2k, y la forma que fijó el piloto de la
pelea (`tools/rm2k-snes/battle/README.md`, "One stage of a converter").
Zorzal dejó anotado lo que falta de ese lado: la adivinanza de Shift-JIS
de `lcf.text`, aplicar los forks de `rom/parches/manual/`, `REFIT_TEXTS`, y
reglas chicas de `lcf.py`.

---
name: "rm2k-snes-cartridges lee el volcado con Ditto"
description: "El tercer lector del volcado a mano: cartridges.rs lee maps.json por su cuenta para el tipo de cada nodo; que use la biblioteca de Ditto, y una prueba que impida un cuarto"
type: refactor
assignee: Cardenal
---

Lo dejó anotado Zorzal el 2026-09-29 (`testing/rust-ditto-como-biblioteca.md`):
desde que la biblioteca de Ditto es el único lugar en Rust que sabe leer el
volcado, queda un lector a mano en `tools/rm2k-snes/cartridge/src/cartridges.rs`,
que lee `maps.json` para saber el tipo de cada nodo del árbol. Que pase a
`ditto::dump::Dump`, y una prueba (en `tools/tests/`, como la de capas) que
falle si un crate que no es Ditto lee un `.json` del volcado por su cuenta.

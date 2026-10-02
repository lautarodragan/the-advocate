---
name: "Los bytecodes, declarados en Rust"
description: "Los dos bytecodes en un crate de tools/rm2k-snes/ con una macro, el .inc escrito por rm2k-snes-assemble al armar, y fuera protocol, sus TOML y los cuatro archivos generados"
type: refactor
assignee: Benteveíto
---

De taro, el 2026-10-02. Va **después** de `doing/las-pruebas-sin-opcodes.md`,
para que ninguna prueba de Python necesite los números.

- Un crate en `tools/rm2k-snes/` (por ejemplo `rm2k-snes-bytecode`) declara
  los dos bytecodes con una `macro_rules!` que da las constantes y una tabla
  recorrible; las validaciones de `protocol` (números contiguos, nombres que
  no se repiten entre los dos, tamaños) pasan a ser pruebas o `const`
  asserts del crate.
- `rm2k-snes-assemble` escribe `event_opcodes.inc` y `music_opcodes.inc`
  —con la tabla del despacho— en el directorio del cartucho, al armar.
- Se van `tools/snes/protocol/`, sus TOML, los cuatro archivos generados y
  commiteados, `test_protocol.py` y la receta `just protocol`.
- Verificación: las ROMs byte por byte iguales, y el `.inc` generado igual
  línea por línea al que hoy está commiteado.

El bytecode es el formato de este runtime, no de RM2k: agregar una feature es
sumar opcodes (`decisiones/rm2k-plus.md`).

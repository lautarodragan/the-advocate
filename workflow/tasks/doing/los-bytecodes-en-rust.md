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

## Cómo quedó (Benteveíto, 2026-10-02)

**El crate es `tools/rm2k-snes/bytecode/`**, paquete `rm2k-snes-bytecode`:
el nombre del directorio sigue a los vecinos (`events`, `battle`), y el del
paquete al prefijo de la capa. Es una biblioteca: no se instala, entra en
`rm2k-snes-events`, `rm2k-snes-audio`, `rm2k-snes-convert` y
`rm2k-snes-cartridge`.

* `src/events.rs` y `src/music.rs` son las dos declaraciones, cada una una
  invocación de `bytecode!`:

      /// `CallEvent` inside a shared common event body: ...
      OP_CALL = 0x3F (body: byte);
      OP_CHOICE = 0x14 (length: count byte, on_cancel: byte)
          repeated options (window: word, destination: word);
      OP_PAN = 0x11 (operation: byte, dx: signed word, ...);

  La macro da un `pub const OP_X: u8` por opcode, con el doc comment encima,
  y `BYTECODE`, la tabla recorrible (nombre, número, argumentos con tipo,
  `signed` y `count`, y el grupo repetido). Los tamaños salen de ahí
  (`fixed_size`, `size_at`): ya no hay `OPCODE_SIZE` ni `VARIABLE_SIZE`.
* Los TOML se transcribieron con un script, no a mano: la cabecera de cada
  uno pasó a `//!` del módulo —reescrita donde hablaba del TOML, de
  `README.md` o del generador—, y el comentario de cada opcode a `///`. En
  la música los comentarios eran de familia (uno cada ocho opcodes): se
  repiten en los ocho, para que cada constante diga qué es.
* Comprobado contra lo que había: los dos `.inc` iguales línea por línea
  salvo las líneas 3 a 5 de la cabecera, y los tamaños de cada opcode
  iguales a los de los `opcodes.rs` generados —con una prueba descartable
  que los incluía a los dos—.

**Las validaciones son `const` asserts**, con el mensaje armado en un
`const fn` porque `panic!` en una constante no formatea: un número repetido
("OP_RETURN and OP_CALL both take 0x3F"), un hueco en el despacho de eventos
("nothing takes 0x40, 0x41"), un nombre en los dos bytecodes ("OP_END is in
the event bytecode and in the music one"), un grupo repetido sin `count` o
un `count` sin grupo, y un bytecode vacío **no compilan**. Un tipo que no
existe (`dword`) tampoco: es un token que la macro no espera. Dos opcodes
con el mismo nombre son dos `const` con el mismo nombre. Las cuatro primeras
las vi fallar rompiendo `events.rs` a propósito. Las pruebas del crate son
esos mensajes —llamando a los mismos `const fn` en tiempo de ejecución—, la
forma del `.inc` y `tests/runtime.rs`, que reemplaza a la mitad de
`test_protocol.py` que miraba el runtime: cada `#OP_X` está declarado y
ningún `OP_X =` está escrito a mano (visto fallar con los dos).

**El ensamblador**: `rm2k-snes-assemble` escribe `event_opcodes.inc` y
`music_opcodes.inc` en el directorio del cartucho (`-I`) antes de buscar
los generados, así que son generados como los demás: el reparto en bancos
los recorre —no tienen segmentos, salen iguales— y una copia vieja al lado
de `main.s` se rechaza como la de `mapdata.inc`. `main.s` no cambió.

**La cabecera del `.inc` cambió** —dice que lo escribe `rm2k-snes-assemble`
en cada build—, con las mismas cinco líneas, así que las líneas de lo demás
no se mueven. El `.dbg` cambia: el archivo del `.inc` pasa de
`tools/runtime/` a `rom/build/<cartucho>/`, con otro tamaño. Y `just
entregar` ya no lleva los opcodes en el `tools/runtime/` que copia: Mesen2
los ve como a los demás `.inc` generados.

---
name: "Las pruebas de ABL, sin opcodes"
description: "Que ninguna prueba de Python necesite los números del bytecode: las que arman bytecode a mano pasan a casos con comandos de RM2k, las que revisan lo que compiló pasan a Rust, y las que decodifican la música se lo piden al binario de audio"
type: refactor
assignee: Cotorra
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

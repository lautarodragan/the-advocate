---
name: "Rust: el orquestador y el lector del juego en Python"
description: "Lo último de la migración: snes_convert.py y lo que queda en tools/port/ (unas 7.000 líneas) como un binario de Rust, y los lectores del juego en Python (tools/rpgmaker/lcf.py, rm2k.py, fork.py) reemplazados por Ditto y el volcado"
type: refactor
assignee: Chuña
---

De taro, el 2026-10-02: el último paso de la migración, después de las
reglas repetidas (Cachirla). Todos los dominios ya son Rust; en
`tools/port/` queda el orquestador —que arma los pedidos de cada etapa y
reparte lo que contestan— y algunos restos, y `tools/rpgmaker/lcf.py`,
`rm2k.py` y `fork.py` todavía leen el juego en Python. Los usan 10 módulos
de `tools/port/`, 2 de `tools/render/`, uno de `tools/tests/` y 15 pruebas
de ABL.

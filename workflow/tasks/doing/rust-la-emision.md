---
name: "Rust: la emisión"
description: "Lo que escribe mapdata.inc (mapdata, map_record, materials, blocks, vram, map_layers, compress) a Rust, con mapdata.inc igual línea por línea y las ROMs byte por byte"
type: refactor
assignee: Timbó
---

De taro, el 2026-10-01: "en paralelo, ¿podemos avanzar con alguna migración
de Python a Rust?". Todos los dominios que alimentan la emisión ya son Rust
(eventos, mapas, pantallas, pelea, imágenes, música, parches); lo que queda
en `tools/port/` es casi todo emisión y pegamento. Era lo último del plan,
junto con el orquestador (`snes_convert.py`), que va después.

Base: `main` en el commit que lanza la tarea, `abl.sfc` `8f8bf5b3c5facf51…`,
`just pruebas` 923, `just -f tools/justfile test` 46.

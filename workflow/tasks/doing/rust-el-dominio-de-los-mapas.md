---
name: "Rust: el dominio de los mapas"
description: "Las capas, los sprites, la VRAM, los bloques y el horneado del conversor (map_layers, sprites, vram, blocks, baking, map_convert) a un crate de dominio en Rust, con las ROMs byte por byte iguales"
type: refactor
assignee: Mara
---

De taro, el 2026-09-30: seguir con la migración del conversor a Rust, por
el dominio de los mapas, que ya usa `rm2k-render`, Adeleine y `voodoo`. Es
un crate de dominio en `tools/rm2k-snes/`, con la forma de
`tools/rm2k-snes/battle/README.md` ("One stage of a converter"), que el
orquestador en Python (`snes_convert.py`) llama por el PATH.

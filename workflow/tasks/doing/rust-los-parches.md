---
name: "Rust: los parches"
description: "tools/port/patches.py (rm2k-snes-patches: escribe y verifica los TOML de rom/parches/auto/) a Rust, con el mismo ejecutable y los mismos archivos byte por byte"
type: refactor
assignee: Yacutoro
---

De taro, el 2026-09-30, en la migración del conversor a Rust. `patches.py`
ya es un ejecutable propio (`rm2k-snes-patches`, que llaman `just parches`
y `just parches-check`) con entrada y salida claras.

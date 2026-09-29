---
name: "Traducir las herramientas, fase 2: port/"
description: "Los nombres de código de tools/port/ (el conversor en Python) al inglés, con todos sus usos"
type: refactor
assignee: Tatú
---

Fase 2 de la traducción de `tools/` al inglés, tercera área: `tools/port/`,
el conversor en Python —`snes_convert.py`, `eventos.py`, `batalla.py`,
`menus.py`, `pantallas.py`, `parches.py` y el resto—, con todos sus usos en
`tools/` y `rom/pruebas/`. Las constantes y los símbolos que el conversor
emite al ensamblador (lo que escribe en los `.inc`) **no** entran: son de la
última área, junto con el runtime.

## Cómo va

De a un módulo o un grupo chico por commit, de las hojas hacia
`snes_convert.py`. Cada commit: `SIN_CACHE=1 just cartuchos` con todo
`rom/build/` (menos `cache/`, `.o`, `sello.txt` y el mtime de los `.dbg`)
byte por byte igual al de `a6fd0d19`, `just pruebas` y
`just -f tools/justfile test` en verde, pyflakes sin avisos nuevos y los
ejecutables `rm2k-snes-*` andando desde `/tmp`.

1. `constantes` → `constants`, `formato_snes` → `snes_format`, `comprimir` →
   `compress`, `fuente` → `font`, `reglas` → `rules`, y los nombres de
   `color`.
2. `asignador` → `allocator`, `msu_datos` → `msu_data`, `paleta` →
   `palette`, `experiencia` → `experience`, y los nombres de `tiles_bin`.

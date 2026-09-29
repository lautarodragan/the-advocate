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

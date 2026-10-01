---
name: "La tabla de páginas de prueba se llenó"
description: "El número de página de prueba es un byte y release ya tiene 256: un caso más no ensambla"
type: bug
assignee: Mulita
---

Lo encontró Tacuarita el 2026-10-01 (`testing/mundo-5-tangle-forest.md`):
la tabla de páginas de prueba de `release` está llena, porque el número de
página es un byte y ya hay 256. Un caso más rompe el ensamblado con `Range
error`. Mientras tanto, ningún mapa nuevo puede sumar casos propios.

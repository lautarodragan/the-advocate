---
name: "Partir el sello del conversor"
description: "Un sello para el conversor y otro para rom/src/, para que editar ensamblador no reconvierta todo"
type: refactor
---

Propuesto el 2026-09-26 por la optimización de `just cartuchos` (ver
`done/cartuchos-en-caliente-en-diez-segundos.md`): hoy tocar cualquier
archivo de `rom/src/` reconvierte todo, pero el conversor lee de `rom/src/`
un solo archivo, `ram_lejana.s` (medido con un audit hook). Con un sello para
el conversor (flags, casos, `tools/`, binarios, `parches/manual`, techos y
`ram_lejana.s`) y otro para `rom/src/`, `ca65` y `ld65`, editar ensamblador
costaría unos 4 s en vez de ~15. Es un cambio de estructura en
`tools/ensamblado/cartuchos.py`.

taro lo dejó en wishlist: no es mucho lo que se gana.

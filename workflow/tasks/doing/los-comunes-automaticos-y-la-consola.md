---
name: "Los comunes automáticos, el CallEvent compartido y \\V[n]"
description: "Fases 4 y 5 del sistema de imágenes: lo que le falta al compilador y al intérprete para la portable console de ABL, todo genérico"
type: feature
assignee: Picaflor
---

Fases 4 y 5 de `docs/research/2026-10-01-el-sistema-de-imagenes.md`
(Jilguero), de taro el 2026-10-02. La portable console no hace falta para
jugar, pero sus piezas sirven a los sistemas custom de muchos juegos. Lo que
falta: los eventos comunes automáticos (los paralelos no), un `CallEvent`
que comparta el cuerpo en vez de pegarlo (pegado, el común 39 son 140.193
comandos; compartido, unos 2.400), y `\V[n]` en los mensajes. `Label` y
`JumpToLabel` ya están (`testing/label-y-jumptolabel.md`, Pitogüé).

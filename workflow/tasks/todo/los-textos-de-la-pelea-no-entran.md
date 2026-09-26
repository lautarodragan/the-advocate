---
name: "Los textos de la pelea"
description: "Mensajes de pelea cortados a 31 caracteres o pasados del borde"
type: bug
---

**Los textos de la pelea que no entran en el ancho de la pantalla.**

Dos casos, los dos de la pantalla de pelea:

- **Los mensajes de las páginas de tropa se cortan a los 31 caracteres.**
  Algunas líneas de `Absorb Aura` llegan a 40 ("RainDrop... GatheringWaves...") y
  pierden la segunda técnica.
- **El mensaje propio de la pelea se pasa del borde** en vez de cortarse:
  "Talan has absorbed the enemy aura!". Ya estaba así antes de las páginas de
  tropa.

Salen de `done/el-sistema-de-batalla-de-talan.md`.

**Otro caso, visto el 2026-09-26 al hacer el elixir en la pelea**: "Kersh
Pungent Elixir-LIFE  used." pasa de 32 columnas y el punto cae en la columna
0 del renglón de abajo, delante de "Core has revived!". Pasa con cualquier
ítem de nombre largo, y el nombre del LDB trae un espacio al final.

---
name: "Los textos de la pelea"
description: "Mensajes de pelea cortados a 31 caracteres o pasados del borde"
type: bug
assignee: Cardenal
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

**Dos más, desde que corren las páginas por turno y por HP (2026-09-28)**: el
despegue de la pelea de los agentes sale "The Captain has taken off in th", y
el segundo llamado del Rat King pierde la "s" de "sounds". Ver
`tasks/*/eventos-de-tropa-de-release.md`.

# Lo que se hizo (Cardenal, 2026-10-02)

**Qué dijo el blame del tope de 31.** `BA_PAGE_MSG_WIDTH` es 31 porque es lo
que entra desde la columna 1 en una pantalla de 32 celdas, y el comentario
de `screen.rs` ya lo daba por deuda declarada ("the map's window carries
thirty-nine. It is declared debt"). El bloque `messages_troop` se armaba
con la ventana del mapa —39 columnas— y la ROM cortaba al dibujar. No era
una decisión de cortar: era lo que faltaba hacer.

**Las páginas de tropa** (el primer commit): el compilador rehace las cajas
de las páginas para la ventana de la pelea —31 por 4— con el mismo `refit`
que las del mapa usan para la suya (`reflow` en `troops.rs`); el conversor
le pasa la ventana en el pedido, `troop_window`, con el ancho que contesta
`rm2k-snes-battle layout`. La ROM no cambia. "The Captain has taken off in
the ship!" sale en una caja de tres renglones con TALAN arriba.

Pruebas, en ABL: `test_el_despegue_se_lee_entero` lee la pantalla —no el
cartucho— y exige el texto entero del LDB; en rojo antes: "The Captain has
taken off in th". Las que comparaban el bloque contra el LDB
(`test_eventos_de_tropa.py`, `test_sistemas_de_tropa.py`) ahora comparan
contra las cajas rehechas (`screen_stage.refit`).

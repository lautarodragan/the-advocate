---
name: "La pantalla de Game Over"
description: "Perder una pelea o un GameOver vuelven directo al título; RM2k muestra la imagen de GameOver con su música y espera una tecla"
type: feature
assignee: Carpincho
---

Pedido de taro, el 2026-09-28.

Hoy `op_game_over` (`rom/src/interprete_game_over.s`) y la derrota sin
manejador (`op_battle_destination`) hacen `jml reset`: vuelven al arranque sin
mostrar nada. RM2k pasa por `Scene_Gameover`: la imagen del juego en
`GameOver/` (la que nombra el `System` del LDB), la música de Game Over del
sistema, un fundido, y espera una tecla antes de volver al título.

El juego trae su imagen en `GameOver/` (ver `ABL_GAME_DIR`).

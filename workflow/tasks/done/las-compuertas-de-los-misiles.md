---
name: "Las compuertas de los misiles se vuelven militares"
description: "En la cinemática del pasado, cuando se disparan los misiles, los eventos que hacen de compuertas toman el gráfico de una persona militar"
type: bug
agents: [Hurón, Tijereta]
assignee: taro
---

De taro, el 2026-10-05: "Otro bug, similar al del tanque: en la cinemática
del pasado, cuando se disparan los misiles, los eventos que hacen de
compuertas se convierten en gráficos de persona militar". Puede ser la
misma causa que `el-tanque-de-dalia-se-vuelve-dalia.md`: un gráfico que
pone un evento y otra cosa le cambia.

# Lo medido (Tijereta, 2026-10-05)

Base: ABL `c988101`, herramientas `d0e2e16c`.

**Se reproduce, y no es la animación de batalla**: las compuertas ya son
soldados hacia el tick 150, cuando los `MoveEvent` del evento 4 las giran
(`face_down`, `face_left`), bastante antes de los `ShowBattleAnimation`.
La caja de 64 tiles de la animación cae en el tile 128 y no pisa a nadie.

**La causa.** Los silos son `Missiles` índice 1, con la animación
`fixed_graphic` (4) y la columna 0. En esa hoja la columna 0 de cada fila
es la compuerta —cerrada, entreabierta, abierta— y las columnas 1 y 2 son
un soldado. RM2k no le cambia nunca la columna a un `fixed_graphic`
(`IsAnimated` en `Game_Character::UpdateAnimation`): girar muestra la
columna 0 de la fila nueva. La ROM, al darle lugar de ruta a un evento
(`route_for_event`), lo ponía siempre en la columna del medio, y
`animate_ev_route` lo dejaba ahí: la compuerta giraba al soldado.

No es una regresión: es así desde que los eventos que mueve una ruta
tienen sus doce poses.

# El arreglo

En las herramientas, rama `worktree-agent-ac0c3db5dd60db962` (commit "Eventos
que una ruta mueve: la columna del gráfico fijo y el gráfico de la página"):
la página lleva en su +15 si su gráfico es fijo y su columna, y el lugar de
ruta —forzada o propia— la conserva y no la anima, como RM2k. RAM nueva:
`FOUND_SPEED`, $7E30CB. Ningún opcode.

Comparado con el original con Wine (copia que arranca en el 92): las
compuertas se abren —cerrada, entreabierta, luces rojas— sin ningún
soldado, y la ROM ahora igual. Capturas en
`/shared/capturas/2026-10-05-compuertas-y-wick/`.

Movió dos goldens, a propósito: `tram-320` y `tram-620`, el Hover-Tram del
9, también de gráfico fijo en la columna 0, que pierde la llama de abajo.

La prueba es `rpgmaker/test_grafico_de_pagina.py`: la silueta de cada
compuerta en la VRAM contra la celda de la hoja. Roja con las herramientas
de main, verde con las de la rama.

**Al mergear**: instalar `cartridge`, `convert`, `mapdata` y `wally`.

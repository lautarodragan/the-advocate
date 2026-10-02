---
name: "Plan: un juego de RM2k para pruebas"
description: "Un juego sintético, sin assets con derechos, con el que las pruebas de lo que hace RM2k vivan con las herramientas y el runtime y no con ABL"
type: research
assignee: Leñatero
---

De taro, el 2026-10-02: "empezar el proyecto de tener un juego de rpg maker
2000 para pruebas". Hoy las pruebas de "lo que hace RM2k"
(`rom/pruebas/rpgmaker/`) viven del lado de ABL sólo porque necesitan un
juego. Los crates ya tienen juegos chicos en `tests/game/`. Es un plan, no
código: de él salen las tareas.

# La dirección de taro (2026-10-02)

"Cuando terminen estos, me gustaría proceder con el juego de pruebas, si
Leñatero lo encuentra factible":

1. **Primero, todo lo de ABL en un solo lugar, fuera de este repo**: un repo
   propio, con su historia.
2. **Después, pruebas en este repo 100% originales**, sin referencias a ABL
   ni assets con copyright.
3. **Los assets**: el reemplazo del RTP de EasyRPG
   (https://easyrpg.org/rtp-replacement/), otros assets libres —taro tiene
   sitios guardados—, o fabricados por ahora; efectos de sonido que taro
   puede hacer en FL Studio; y MIDIs de obras de dominio público (Bach,
   Beethoven, Mozart), con la licencia del archivo verificada.

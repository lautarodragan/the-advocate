---
name: "La otra rama de la cinemática de los Neon Vipers"
description: "Lo que el recorrido del mapa 12 dejó sin ejecutar: la rama del `no`, la reja y el mapa 14"
---

`pruebas/abl/test_recorrido_vipers.py` juega el tramo entero por la rama de
**"Yes, I'll do it!"**, que es la que sale de tocar A sin mover el cursor del
`ShowChoice`. Quedaron sin ejecutar tres cosas, y son las tres del mismo lado:

* la rama de **"No, it's a waste of time!"**, que en vez de teletransportar baja
  caminando y sale por la reja, con **los dos saltos de 5 celdas** del mapa 12
  —7,3 px por cuadro, de los movimientos más rápidos del juego—;
* el **evento 1 de (1,47)**, la reja, con su `ShowChoice` de "Climb the Fence" y
  su salto después del `Teleport`;
* el **mapa 14**, donde con estos switches no entra ninguna de las dos ramas.

Para tomarla hay que mover el cursor del `ShowChoice`, que el arnés hoy no hace;
ver `Recorrido.activar` y `mirar_a`. Lo demás ya está: el camino hasta la
cinemática es el mismo, y el detalle de cada evento está escrito en
`workflow/tasks/done/el-recorrido-de-los-neon-vipers.md`.

Por qué vale: los saltos largos son el caso extremo de `salto_avanzar_heroe`, y
el bug del salto colgado de esta semana vivía justo ahí.

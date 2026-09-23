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

## Y son las dos candidatas a reproducir el mapa corrido

El 2026-09-23 se midió que el tramo cubierto **no puede** reproducirlo, ni
siquiera caminando después de volver: el peor salto de la cámara por vuelta es
de 2 px y hacen falta más de 8. Las dos cosas de esta zona que podrían llegar
son justamente las que quedaron afuera:

* el `PanScreen` de la escena de los chicos y el dueño del negocio —eventos 51 y
  53 del mapa 8, en (59,23) y (59,24), que piden el switch 33— **sumado al héroe
  caminando**, que es la receta que `pruebas/rpgmaker/test_camara.py` arma a
  mano;
* el salto de cinco celdas de la reja, que son 7,3 px por cuadro.

Y de paso, midiendo la reja apareció otra cosa, que **no** es el mapa corrido y
además parece fiel: al salir por la reja el héroe cae en (40,56) del mapa 8 y la
cámara queda **48 px —tres celdas— más abajo de donde la dejaría un
teletransporte**, con `pan_y` en 768 dieciseisavos. Pasa igual con el arreglo de
`stream_map` y sin él.

De dónde sale, medido el 2026-09-23: la reja termina prendiendo el switch 36, y
con 36 prendido arranca sola la página 2 del **Bum**, el evento 10 de (38,55)
—"Woah! Where'd you come from, Mister? You a ghost?"—. Esa página hace un
`PanScreen` de scroll de tres celdas para abajo y **nunca lo devuelve**: no tiene
la operación de volver.

Y así es como quedarse: en el modelo de RM2k el pan es un corrimiento que la
cámara **se sigue llevando mientras el héroe camina** —`Game_Player::UpdateScroll`
le resta `GetPanX/Y` al objetivo, y sólo lo saltea si el pan está fijado— y lo
único que lo pone en cero es cambiar de mapa, que es lo que hace
`PerformTeleport` con `map_changed`. Las dos cosas son las que hace `main.s`. O
sea que el corrimiento es del juego original, no del port, y explica por qué se
arregla con cualquier teletransporte.

Lo que falta para cerrarlo es jugar ese camino en EasyRPG y ver la cámara igual
de baja. Si no lo está, entonces sí es nuestro y hay que mirar `pan_tick`.

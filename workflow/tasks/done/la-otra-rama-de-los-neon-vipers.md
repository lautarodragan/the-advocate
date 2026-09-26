---
name: "La otra rama de la cinemática de los Neon Vipers"
description: "Lo que el recorrido del mapa 12 dejó sin ejecutar: la rama del `no`, la reja y el mapa 14"
type: test
---

`pruebas/abl/test_recorrido_vipers_golden.py` juega el tramo entero por la
rama de **"Yes, I'll do it!"**, que es la que sale de tocar A sin mover el cursor del
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

Y lo que apareció midiendo la reja —la cámara que queda tres celdas corrida al
salir— **ya está contestado y no es nuestro**: lo hace el `PanScreen` del Bum,
que nadie devuelve, y el RPG_RT original queda igual de corrido. Ver
`workflow/decisiones/la-camara-corrida-de-la-reja-es-del-juego.md`.

---

## Al 2026-09-26: cubierta

`pruebas/abl/test_recorrido_vipers_otras_ramas_golden.py`, con
`Recorrido.elegir` —ver `done/elegir-una-opcion-en-el-recorrido.md`—. Tres
casos, que arrancan con `ir_al_mapa` en el techo del HQ y entran por la puerta:
el camino del caño ya lo juega el tramo del "Yes".

Lo que se aprendió leyendo los eventos, que la descripción de arriba tenía mal:

- **Los dos saltos de cinco celdas no son del mapa 12**: son las rutas del
  "No" y de la reja, que están escritas en el 12 pero corren **después** del
  `Teleport` al 8, en (40,51) → (40,56). Lo que sí corre en el 12 es un salto
  de dos celdas sobre la reja, y ése **no se da**, ni acá ni en RM2k: el
  `through` está adentro del par `begin_jump`/`end_jump`, donde RM2k lo
  ignora, y (1,49) no es pisable.
- **Al 14 no lleva ninguna de las dos ramas**: lleva la página 2 de la puerta
  del HQ, con el Idol —ítem 90— y el switch 53, que deja al héroe sobre el
  hotplate, cuya página 2 es automática y termina en `Teleport [14, 44, 13]`.
  La cinemática del 14 corre sola, con cinco `PanScreen`, y termina en el 16.
- **La reja se alcanza sin la cinemática**: el camino corto de la puerta a
  (1,47) baja por la columna 3 y el hotplate está en la 5.
- **Aterrizar en el 8 dispara al Bum**: las dos salidas prenden el switch 36, y
  la página automática del evento 10 lo apaga al terminar. La prueba espera eso
  —el 36 visto prendido y después apagado— antes de mirar la celda.

**Lo del mapa corrido, medido**: el salto de cinco celdas son once vueltas de 7
u 8 px, con la cámara detrás a lo mismo. No llega a los más de 8 que hacen
falta, así que esta candidata queda descartada; la que queda es el `PanScreen`
de los chicos del mapa 8.

**Un aviso para las fotos del tramo del "Yes"**: la partida que arranca por
"Begin the Story" tiene de líder a DummyHero, el actor 10, que no tiene gráfico.
En `test_recorrido_vipers_golden.py` las fotos del 8 y el 12 salen **sin
Talan**. Ésta le pone el grupo —Talan es el 14— antes de entrar.

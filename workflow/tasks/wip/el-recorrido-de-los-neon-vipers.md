---
name: "El recorrido de los Neon Vipers"
description: "Una jugada larga que cubra la escena donde aparecieron los dos bugs"
---

**Una prueba que juegue el tramo de los Neon Vipers de punta a punta**: arrancar
en la calle de Lashe City, subir por el caño, cruzar el techo, entrar al HQ,
caminar hasta disparar la cinemática, pasar todos los diálogos y volver a la
calle. Lo pidió taro el 2026-09-22.

El punto no es la cobertura en abstracto: **ahí aparecieron los dos bugs de esta
semana** —el salto que quedaba colgado y el mapa que quedaba corrido— y ninguna
prueba los ejecutaba. Del mapa 11 la tanda sólo tiene `en-11`, que entra y nada
más; del 12 y el 14, nada. De paso ejercita dos teletransportes y varios tipos
de evento: contacto, automáticos, paralelos y el salto.

Los mapas: la calle es el **8** (`Lashe City - 34,35`) y el HQ es el **12**
(`Trash Dump 004`), donde están `Conda`, `NVone`, `NVtwo`, `NVthree`,
`NV Lookout` y `NV hotplate`. El 12 tiene además dos saltos de 5 celdas, que son
de los más rápidos del juego: 7,3 px por cuadro.

El modelo es `pruebas/abl/test_recorrido.py`, que ya juega desde el título hasta
el auditorio con `Mundo`/`Recorrido` —el grafo de islas y el plan por puertas—,
y guarda una captura por hito.

Hecho es: la prueba corre en la tanda, y **se la vio fallar contra la ROM de
antes de los dos arreglos**, que es lo que dice si cubre de verdad lo que taro
encontró jugando.

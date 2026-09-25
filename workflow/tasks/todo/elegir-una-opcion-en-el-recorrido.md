---
name: "El recorrido elige la opción N"
description: "Que Recorrido pueda mover el cursor de un ShowChoice antes de confirmar"
type: test
---

# Qué

`Recorrido` —`pruebas/arnes/recorrido.py`— sólo confirma un `ShowChoice` con la
opción de arriba: toca A sin mover el cursor. Hace falta **elegir la opción N**:
bajar el cursor N veces, comprobar en la RAM que quedó donde se pidió, y recién
ahí confirmar.

Es el hito 0 de `lashe-city-hasta-la-carrera.md` y se puede hacer en paralelo
con el 1. Sin esto no se puede escribir ningún recorrido de Lashe City con
auto:

- la elección del 36 es `Sector 32 / 33 / 34 / 35`, y el tramo principal
  —el 37— es la **cuarta**;
- el favor de Boss Wick (40, evento 7, página 4) tiene dos elecciones seguidas,
  y la rama de "Refuse" es la segunda;
- la cola del auto (36, página 2) es "Stay / We've got to get out of here": la
  que lleva al límite es la segunda.

Y destraba `wishlist/la-otra-rama-de-los-neon-vipers.md`, que se quedó sin hacer
justamente por esto.

# Lo que ya se sabe

- **Un toque puede perderse**: la ROM lee el pad una vez por vuelta y una
  vuelta puede durar varios cuadros. `Recorrido.mirar_a` ya resolvió lo mismo
  para girar comprobando la RAM; conviene el mismo método (ver
  `done/el-recorrido-de-los-neon-vipers.md`, "Un agujero del arnés").
- **La ventana ignora el botón mientras se compone**: nada de toques en los
  primeros treinta cuadros desde que se abre (ver `ESTADO.md`, "Lo que la tanda
  no cubre").
- Qué variable de la RAM dice dónde está el cursor: está en el intérprete de
  `OP_CHOICE`; la tabla de símbolos del cartucho la exporta si tiene nombre.

# Hecho es

Una prueba que elige la opción 2 de una elección de dos y comprueba que corrió
esa rama —en `release` hay candidatos: el guardia del auditorio—, vista en rojo
con el toque de A sin mover el cursor.

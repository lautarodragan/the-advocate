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

---

## Al 2026-09-26: hecho

**La API**, en `Recorrido`: `elegir(opcion)` espera el próximo `ShowChoice`
cerrando con A los mensajes de antes, baja el cursor hasta `opcion` —desde
cero— y confirma. Son dos mitades sueltas, `marcar(opcion)` y `confirmar()`,
para poder sacarle una foto a la ventana con el cursor puesto.

Todo por RAM y ningún cuadro contado:

- **abierta** es `eleg_activo` y `msg_abierto` juntos, como `abierta` de
  `test_elegir.py`: `op_choice` prende el primero antes de que la ventana
  termine de componerse, y `eleccion_tick` no mira el pad hasta el segundo;
- **el A que cierra los mensajes** se toca sólo con un mensaje abierto y la
  elección no. Es la trampa de verdad: la paciencia de `esperar` toca A a
  ciegas, y un toque que cae con la elección recién compuesta se lleva la
  opción de arriba;
- **cada toque de abajo se comprueba** en `eleg_sel` y se repite si se perdió;
  uno que llegó no se repite nunca, porque la ventana mira flancos;
- **resuelta** es que la ventana deje de estar lista. Si la rama abre otra
  elección, esa no está compuesta todavía y no se la contesta de paso.

`activar` sigue tocando A a ciegas después del primer toque, así que antes de
un `elegir` hay que cortarlo apenas arranca la página:
`activar(celda, lambda p: p.corriendo_una_pagina())`.

**La prueba**: `pruebas/abl/test_recorrido_vipers_otras_ramas_golden.py`, que
juega la rama del "No" de la cinemática del hotplate, las dos opciones de la
reja y el mapa 14 —ver `done/la-otra-rama-de-los-neon-vipers.md`—. **Vista en
rojo** con la opción de arriba en lugar de la segunda: la del "No" termina en
(44,13) sin el switch 38, que es la rama del "Yes", y la reja con "Climb the
Fence" en vez de "Don't Bother".

Lo del guardia del auditorio no hizo falta: la cinemática de los Neon Vipers
es una elección de dos donde la segunda rama deja rastro en la RAM.

---
name: "Lashe 3: la planta de reciclaje y el droide"
description: "Stash, los pisos que se rompen y AG7-17 entrando al grupo: 57, 59 a 63 y 164"
type: feature
---

# Qué

El hito 3 de `lashe-city-hasta-la-carrera.md` —el contexto y lo medido están
ahí—. Va después del 1 y en paralelo con el 2.

El camino del droide desde el Sector 32 (48): la puerta de Stash, la escena del
"bald man" que te robó en el Hover-Tram (o del guardia sobornado), la planta de
reciclaje con los pisos que se rompen, el Motivator Chip, el túnel de vuelta, y
**AG7-17 entrando al grupo**, con su tutorial. Prende el 150, que es lo que la
rama sin compañero necesita para irse.

Mapas: **57** (Stash's Emporium), **59** (Outside Recycling Plant), **60**,
**61** y **62** (los tres pisos), **63** (el túnel) y **164** (el tutorial del
droide, fuera del subárbol de Lashe City). Las áreas de encuentros 180 a 183 ya
las lee el conversor desde el árbol.

La pelea del droide —sus habilidades y las de los enemigos de la planta— es el
hito 4. Acá AG7 entra al grupo y camina; pelear, pelea con lo que hay.

# Lo que falta

**`RecallToLocation`** (10830): 54 páginas lo piden solo —28 del 60, 26 del 62—
y el 164. Es un **teletransporte con el mapa y la celda en variables**
(`CommandRecallToLocation`, en `game_interpreter_map.cpp`: arma
`ReserveTeleport(map_id, x, y)` y el paralelo sigue corriendo). Los pisos lo
usan así: cargan el 61 en la variable 45, la celda del héroe en la 43 y la 44,
le suman 5 a la fila, y el héroe **cae al piso de abajo**. En todo el juego es
lo que más páginas frena (60, 55 él solo).

Lo que pide que no pide el `Teleport` de hoy: **traducir un id de mapa de RM2k
a un índice del cartucho en la ROM**, porque el número llega en una variable.
Una tabla de ids por índice —dos bytes por mapa— y una búsqueda; y qué hace si
el mapa no está en el cartucho (lo más honesto parece no saltar y seguir).

**`MemorizeLocation`** (10820): la página 5 del evento 2 del 57, la que mete al
droide. Guarda el id de RM2k del mapa actual y la celda del héroe en tres
variables, así que también pide la tabla al revés: el id de RM2k del mapa en
el que se está.

**`MemorizeBGM` / `PlayMemorizedBGM`** (11530/11540): el tutorial. Un byte de
estado —el tema recordado— en la RAM lejana.

**El 164 en el cartucho**, o un fork del 57 que se saltee el tutorial (pregunta
9 del plan). Recomendado conservarlo: `RecallToLocation` hace falta igual.

**`fm2bar_gs`**, el tema de Stash: sin muestras en el banco (suena con el 83% de
las notas). La pista de MSU-1 la tiene sola: ver `pista_msu`.

**El evento común 37, `UpdateAG7 Skills`**: es paralelo con el switch 150, y la
ROM no corre eventos comunes paralelos. Sin él AG7 entra sin habilidades. Qué
hacer con esto es del hito 4; acá alcanza con que conste.

# Números a repartir

Entre uno y cuatro opcodes (se pueden juntar: `MemorizeLocation` y
`RecallToLocation` comparten la tabla, y los dos del tema son el mismo estado),
una pista de MSU-1, una o dos direcciones de RAM lejana, y la tabla nueva en
`TABLAS` (banco 0: dos bytes por mapa).

# Pruebas

- **Casos de tanda** para cada opcode: caer de un mapa a otro con
  `RecallToLocation` (el mapa y la celda en variables), recordar y volver, un
  mapa que no está en el cartucho, y el tema recordado.
- **El recorrido**, sin compañero y con el 71 puesto (el ídolo robado en el
  tram): entrar al 57, la escena, la planta, caer por un piso del 60 al 61 al
  menos una vez, el chip, el túnel, el droide en el grupo —comprobar el 150 y el
  actor 18 en la RAM—, el tutorial y la vuelta a (3,39) del 48. Los encuentros
  al azar de la planta se pelean con el arnés de `pruebas/arnes/batalla.py`, o
  se apagan: decidirlo mirando cómo lo resuelven las pruebas que ya caminan por
  áreas con encuentros.
- La otra puerta: con Arden, la de Stash dice "Looks like they're closed".

# Qué tiene que mirar taro jugando

La escena de Stash según cómo haya ido el tram, los pisos que se rompen y la
caída, el chip, el tutorial, y AG7 en el grupo desde el menú de pausa.

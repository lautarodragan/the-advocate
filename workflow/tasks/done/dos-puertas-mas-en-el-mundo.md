---
name: "Dos puertas más en el mapa de debug, en el mundo"
description: "Una que deja en el Northern World / Lashe Area pasando el puente, con la historia de Eisen hecha y la charla con Vago terminada, y otra a la izquierda del EV0020 del 66, después del bosque en llamas, los agentes y el Hover Tram"
type: feature
assignee: taro
agents: [Hurón]
---

De taro, el 2026-10-10: "Podés agregar dos puertas más en el mapa debug
del ABL?

1. Una que te deje justo después del puente, en el Northern World / Lashe
   Area (Map0066, uno o dos tiles a la izquierda de EV0006, habiendo
   completado la historia de Eisen y terminado la charla con Vago. El
   puente es mapas 2059 y 0255)

2. Otra que te deje también en Northern World / Lashe Area, pero a la
   izquierda de EV0020, habiendo terminado la secuencia del bosque que se
   prende fuego, luchado con los agentes y el Hover Tram."

Sigue a `done/dos-puertas-mas-en-el-mapa-de-debug.md`: mismo método.

## Dónde quedaron

**Las dos nuevas caen entre la 7 y la de Paradise, no después.** El
camino del capítulo es Sorbe (la 7), el puente, el bosque de Tangle con el
tram y la nave, el túnel, Mountain Path y Paradise: las dos que pidió taro
son el segundo y el tercer paso. Así que el cuarto pasó de 29 a 35 celdas
de ancho y las puertas quedaron en el orden del juego: la 8, después del
puente, en (25,14) con su cartel en (24,11); la 9, después del Hover Tram,
en (28,14) con el suyo en (27,11); y la de Paradise se corrió a (31,14),
cartel en (30,11), y pasó a ser la 10. Su evento sigue siendo el 18 y su
página no cambió; sólo su lugar y su nombre (`Door10`). Las dos nuevas son
los eventos 20 a 23. Si taro prefiere la de Paradise donde estaba, es
volver a cambiarle la x y correr las otras dos.

Las dos piden compañero, como la 7: sin ninguno el juego no llega, y lo
dicen sin saltar. Y las dos suman al compañero, porque en el juego está:
el que se queda en Mountain Path es recién en Paradise.

## El momento de cada una

**El puente es el 259 y el 255**, como confirmó taro: el 2059 no existe.
El 259 es el Northern Highway Bridge y el 255, Under the Bridge.

**La 8: del otro lado del río, en (73,7) mirando a la izquierda**, a una
celda del EV0006 (74,7) —que con el 849 ya no deja volver—. Es donde dejan
las dos maneras de cruzar: el 255 al salir por abajo (evento 64) y el 259
al pagarle al guardia (eventos 15 y 16). "La charla con Vago" es la que
esperaba: la del 81 que cierra la historia de Eisen y que ya cerraba la
puerta 7. En el puente no hay otra; el 259 no nombra a Vago.

**La 9: (34,56) mirando a la izquierda, a una celda del EV0020** (35,56,
que lleva al 312). Ahí deja la automática del 312 (evento 81, página 2,
con el 846) después de la pelea con la nave, y termina. Antes: Tangle
(310), el claro (311) con los agentes, el tram que prende fuego el bosque,
la salida del 312 con el cronómetro y el Hover Tram (313).

## Cómo salió el estado

Jugado, no inventado, igual que la vez pasada: una prueba descartable
entró al cuarto, sumó a cada compañero, cruzó la puerta del mundo (la 6) y
jugó con el arnés el camino de los recorridos —Sorbe, el capítulo, el
puente (por debajo con Arden y Saldra, pagando con AG7-17), Tangle, el
tram y la nave—, sin los `ir_al_mapa` ni los `poner_exp` de los
recorridos. Ningún tramo se rompió. En cada punto volcó lo que guarda
`save_table`, y las páginas salen de la diferencia contra el cuarto, por
rama, con el generador de la vez pasada.

Lo que se dejó afuera es lo mismo que en la 7 y la de Paradise, y lo dice
el comentario de cada página: los switches 298 y 806, que no lee nadie, y
la variable 134. Lo nuevo:

* **Escapar queda prohibido después del puente con Arden y con Saldra.**
  La automática del evento 10 del 255 lo prohíbe y el juego no lo
  devuelve hasta el claro de Tangle (311, evento 1): la puerta 8 lo
  prohíbe igual en esas dos ramas. Con AG7-17 no se pasa por abajo.
* **El nivel de Talan depende de la rama** en las dos: la pelea de abajo
  del puente le da experiencia. Va adentro de cada rama, con el del
  compañero.

Los niveles jugados: después del puente, Talan en el 4 con Arden y Saldra
y en el 3 con AG7-17; Arden en el 4, Saldra en el 5 y AG7-17 en el 6.
Después del tram, Talan en el 7 con Arden y Saldra y en el 6 con AG7-17;
Arden y Saldra en el 7 y AG7-17 en el 8.

**Verificado** así: la misma prueba descartable cruzó cada puerta con cada
compañero y volcó lo mismo, y la diferencia contra lo jugado es sólo lo de
siempre: los dos switches, la variable 134, la experiencia (la justa del
nivel contra la jugada) y los HP y SP (lo jugado tiene los 999 del arnés;
la puerta, `FullHeal`). Mapa, celda, dirección, grupo, oro, ítems,
habilidades, equipo, velocidad, permisos, tinte y tema, iguales. La puerta
7 se volvió a medir así y sigue igual.

## Las pruebas

En `pruebas/abl/test_mapa_de_debug.py`, por compañero, en rojo antes del
mapa nuevo (no hay camino a (28,14) ni a (31,14), y la de (25,14) llevaba
a Paradise):

* `test_la_puerta_despues_del_puente_sigue_al_bosque`: mapa, celda,
  dirección, grupo, switches, rama, oro, velocidad, escapar, niveles; la
  golden de la llegada; y de ahí caminando hasta Tangle.
* `test_la_puerta_despues_del_tram_sigue_a_mountain_path`: lo mismo, y de
  ahí el túnel hasta Mountain Path.

Las seis goldens nuevas son `mapa-de-debug-puente-*` y
`mapa-de-debug-tram-*`. **La del cuarto, `mapa-de-debug-llegada`, no
cambió**: desde la llegada no se ve más allá de la terminal de la 7, y lo
que se agregó está a la derecha de eso. Las fotos de lo que sigue (el
bosque y Mountain Path) quedan en `pendientes.txt`, como las de las otras
puertas.

## Para mergear

Sólo ABL: no se tocaron herramientas, no hay nada que instalar. Verificado
con la tanda entera sobre la rama (`just pruebas`, con las herramientas
globales): todo en verde. Lado a lado en
`/shared/capturas/2026-10-10-puertas-de-debug-mundo/`.

Lo que la tanda no cubre: la experiencia por encima de la justa del
nivel, los HP y SP jugados, y que taro juegue desde las dos puertas más
allá de Tangle y de Mountain Path.

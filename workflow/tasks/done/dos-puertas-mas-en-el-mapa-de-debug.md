---
name: "Dos puertas más en el mapa de debug"
description: "Una puerta que deja en Distant Paradise apenas se toma el control de Talan después de las cinemáticas de llegada, y otra después del minijuego de Fortitude, al terminar la charla con el Dr. Vago"
type: feature
assignee: taro
agents: [Hurón]
---

De taro, el 2026-10-04: "Podés agregar una o dos puertas más al mapa debug?
… una que te deje en Paradise directamente — en el mismo lugar que te
dejaría llegar normalmente, luego de todas las cinemáticas, apenas tomás
control de Talan", y "una después del mini juego de Fortitude, después de
retomar el control de Talan (creo que sería inmediatamente al terminar la
charla con Dr Vago, no?)".

El mapa de debug es `parches/manual/nuevos/Map0900.json`; cada puerta deja
el estado de alguien que jugó hasta ahí.

## Dónde quedaron

El cuarto pasó de 26 a 29 celdas de ancho, para que entren dos puertas
más con el mismo paso que las otras: la 7 en (22,14), con su cartel en
(21,11), y la 8 en (25,14), con el suyo en (24,11). Las dos piden
compañero, como la de la carrera y la del mundo: sin ninguno el juego no
llega, y lo dicen sin saltar.

## El momento de cada una

**Después de Fortitude, la 7: taro tenía razón**, es apenas termina la
charla con Vago. Pero no es en la casa de Vago: la automática del 81
(evento 6, página 5, con el 309) cierra la historia, salta a Sorbe (69,
10,19), suma al compañero y prende el 310, y ahí termina. Desde la
escotilla del 95 no se mueve nadie hasta ese salto. Talan queda mirando
abajo, con el compañero en el grupo.

**Paradise, la 8: el primer control es adentro del Consejo, no en el
pueblo.** La llegada al 108 (la automática del 5) lleva derecho al Consejo
(110), el recuerdo de Pierson (175 a 177) vuelve ahí, y la página 2 del
evento 11 prende el 350 y el 349 y termina: Talan en (10,14), mirando
arriba, solo —el compañero se quedó en Mountain Path—. Ése es "apenas tomás
control"; el pueblo (108, 25,22) viene recién al salir. Si taro la quiere
en el pueblo, es cambiar el destino y prender el 361.

## Cómo salió el estado

Jugado, no inventado. Una prueba descartable entró al cuarto, sumó a cada
compañero, cruzó la puerta del mundo y jugó con el arnés el camino de los
recorridos —Sorbe, el capítulo, el puente (por debajo con Arden y Saldra,
pagándole 2000 al guardia con AG7-17), Tangle, Mountain Path, el túnel y
Paradise—, sin los `ir_al_mapa` ni los `poner_exp` de los recorridos. En
cada punto volcó de la RAM lo que guarda `save_table`: switches,
variables, ítems, oro, habilidades, equipo, HP, experiencia, grupo, mapa,
celda, dirección, velocidad, tinte y música. Las dos puertas las generó un
script desde la diferencia entre el cuarto y ese volcado, por rama.

Lo que se dejó afuera, y por qué, está en el comentario de cada página:
los switches 298 y 806, que no los lee ninguna página, rama ni común; la
variable 134, que el común 35 vuelve a poner antes de leerla; y **la
experiencia: el compilador de eventos no tiene `ChangeExp` ni
`ChangeLevel`**, y una página con un comando que no compila se cae entera.
Jugando, después de Fortitude Talan está en el nivel 3 (Arden 4, Saldra 5,
AG7-17 6) y en Paradise en el 7 (Arden y Saldra 7, AG7-17 8); con la
puerta, en los del cuarto. Las habilidades que Arden aprende subiendo se le
dan con `ChangeSkills`. Darles el nivel es trabajo de las herramientas.

**Verificado** así: la misma prueba descartable cruzó cada puerta con cada
compañero y volcó lo mismo, y la diferencia contra lo jugado es sólo eso:
los dos switches, la variable 134, la experiencia y los HP (lo jugado tiene
los 999 del arnés; la puerta, `FullHeal`). Mapa, celda, dirección, grupo,
oro, ítems, habilidades, equipo, velocidad, tinte y tema (el 26 en Sorbe,
el 44 en el Consejo), iguales.

## Las pruebas

En `pruebas/abl/test_mapa_de_debug.py`, por compañero:

* `test_la_puerta_despues_de_fortitude_sigue_el_capitulo`: mapa, celda,
  dirección, grupo, los switches del capítulo, la rama, el oro y la
  velocidad; la golden de la llegada; y de ahí el puente del mundo y el
  evento de la rama que lo cruza.
* `test_la_puerta_de_paradise_llega_a_la_granja`: lo mismo en el Consejo, y
  el primer día entero hasta la granja.

La golden del cuarto, `mapa-de-debug-llegada`, cambió en el borde derecho:
asoma la terminal de la puerta 7. Lado a lado, con las seis nuevas, en
`/shared/capturas/2026-10-04-puertas-de-debug/`.

## Lo que encontré y no es de esta tarea

**Con la velocidad 3 el mirador deja la dirección del héroe trabada.** La
ruta del héroe del 109 (evento 6: 26, 28, nueve pasos, 27, 29) se corta
antes de su 27 y `hero_lock` queda en 1, con la velocidad en 4. Con la 4
termina entera. La 3 es la del juego de verdad desde la carrera —el
volcado la tiene así en todo el camino—, y el recorrido del primer día
pasa porque corre con la 4 del arranque. Trabado, Talan no gira hacia
Emily en su casa. La prueba de Paradise lo destraba a mano, con un
comentario. No medí si RM2k lo hace igual: easyrpg no cancela la ruta del
héroe al teletransportar, y una ruta nueva la reemplaza.

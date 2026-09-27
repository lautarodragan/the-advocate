---
name: "Lashe 5: la cola del auto"
description: "El cierre del 36 por las tres ramas, hasta el Teleport al 49 exclusive"
type: feature
assignee: taro
---

# Qué

El último hito de `lashe-city-hasta-la-carrera.md`. Va cuando están el 1, el 2
y el 3 —y el 4 si se quiere jugar la rama del droide peleando con él—.

Que las tres ramas lleguen al final: la página 2 del evento 3 del 36, con el 161
y la condición de la rama cumplida, nota el auto de la Agency (prende el 238),
pregunta "Should we stay in Lashe City or get out?", y con "We've got to get out
of here" prende el 182 y llega al límite —lo que se haya decidido en el hito 1
para el `Teleport [49, 1, 26]`—.

    Arden   161 + 169   (el HQ de los Vipers, en el 38)
    Saldra  161 + 181   (el Sector 33, el 47)
    solo    161 + 150   (el droide)

"Stay in the city a little longer" no cierra nada: la próxima vez que se vuelve
al auto, la rama de arriba de la misma página lo vuelve a preguntar.

No debería pedir código nuevo: todo lo que la página usa ya compila en el hito 1.
Lo que pide es **jugarlo de punta a punta**, porque es el único lugar donde se
juntan los tres caminos y los switches que dejaron.

# Pruebas

- **Tres recorridos**, uno por rama, desde la charla en el auto (mapa 4,
  página 5) hasta el límite, sobre `release`. Son largos: conviene que cada uno
  arranque con los switches de los tramos que no son de su rama ya puestos
  —el tramo de Wick lo cubre el recorrido del hito 2— y juegue lo suyo más el
  cierre.
- "Stay" una vez y "get out" después.
- Comprobar que **ninguna** rama llega al cierre sin su condición: la rama sin
  compañero y sin droide tiene que quedarse en la ciudad, como en el original.

# Status

2026-09-27, en `testing/`: hecho sobre `a3140f1` (hitos 1, 2 y 3), en la
rama del agente, con `main` mergeado antes de entregar. **No pidió código
nuevo**: las tres ramas cierran con la ROM como estaba. Lo que queda es de
taro: jugarlo y mirar las fotos sin golden.

# Lo hecho

`pruebas/abl/test_recorrido_lashe_cierre_golden.py`, sobre `release`, un
recorrido por rama. Cada uno arranca en la charla del auto del mapa 4 (el 132),
pasa por la cinemática del 34, y llega al 36 con el tramo de Wick hecho (el
161 prendido a mano: lo juega `test_recorrido_lashe_wick_golden.py`). Después:

1. su sector y de vuelta al auto **sin hacer lo suyo**: el 36 no prende el 238
   y la primera elección que abre es la de sectores (cuatro opciones, no dos);
2. lo suyo, jugado desde el 36 y no con `ir_al_mapa`, y caminando de vuelta al
   auto;
3. "Stay": el 238 prendido, el 182 no; otra vuelta a un sector y al auto;
4. "We've got to get out of here": el 182, el cartel del fin y el título.

Para que "sin su condición" no sea sólo "sin nada", cada uno arranca con el
switch de **otra** rama que se puede tener sin ser la propia:

    Arden   con el 181 (los guardias andan en las tres ramas); juega el caño,
            el HQ y el susurro (169) en el 38
    Saldra  con el 150 y AG7 en el grupo (con ella el droide es opcional); juega
            la tienda del 56 y los guardias (181) en el 47. La rama de la
            página que mira el 150 pide que el 56 esté apagado: no alcanza
    solo    con el 181; juega Stash, la planta, el chip, el túnel, AG7 y su
            tutorial en el 48. Sin el 150 se queda en la ciudad, como en el
            original

Los tramos que ya jugaban los hitos 1 y 3 se reusan: en un commit aparte, el
cuerpo de sus pruebas pasó a funciones (`el_hq_por_el_cano`,
`la_tienda_y_los_guardias`, `irse_termina_la_demo`, `de_stash_a_ag7`), sin
cambiar lo que juegan.

Que el paso 1 caza lo que dice se comprobó a mano una vez: con el 169 prendido
de entrada, la rama de Arden se planta ahí ("tiene 2 opciones").

**Ninguna pelea obligatoria** en las tres ramas: la única zona con encuentros
es la planta (59 a 62), y ahí Talan va solo —AG7 entra después—; el recorrido
los apaga, como el del hito 3. Así que la rama del droide no depende del
hito 4.

Las fotos quedan en `pruebas/snapshots/playthrough/lashe-cierre-*/` **sin
golden** (`arden`, `saldra`, `solo`). Lo que **no** cubren: el auto azul (130
apagado), el tramo de Wick jugado en la misma corrida, y las peleas de la
planta.

# Qué tiene que mirar taro jugando

El juego desde la charla en el auto hasta el límite, por la rama que elija, con
el build que sale de `main` mergeado. Y que el límite haga lo que se decidió.

Por rama, con el build de `main` mergeado: con Arden, el caño y el susurro;
con Saldra, los guardias del 33; sin compañero, Stash, la planta y AG7. Antes
de cumplir la condición, volver al auto no tiene que preguntar nada; después,
"Stay" una vez (se vuelve a preguntar la próxima) y "get out": el cartel del
fin de la demo y el título.

---
name: "Lashe 5: la cola del auto"
description: "El cierre del 36 por las tres ramas, hasta el Teleport al 49 exclusive"
type: feature
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

# Qué tiene que mirar taro jugando

El juego desde la charla en el auto hasta el límite, por la rama que elija, con
el build que sale de `main` mergeado. Y que el límite haga lo que se decidió.

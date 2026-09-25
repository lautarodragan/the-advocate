---
name: "Lashe 1: los cuatro sectores con auto"
description: "37, 38, 47 y 48 (con el 39 y el 56) en release, y el 36 que no traba"
type: feature
---

# Qué

El hito 1 de `lashe-city-hasta-la-carrera.md`, que es donde está el contexto
entero y lo medido. Bloquea a los demás.

Meter en `_DE_RELEASE` los cuatro sectores con auto —**37, 38, 47 y 48**—, que
la elección del 36 pide juntos, y los dos interiores que no piden nada: el
**39** (Talan's Pad With Car, copia exacta del 7; prende el 151) y el **56**
(la tienda del Sector 33). Y dejar el 36 sin trabarse en la segunda visita.

Lo que queda afuera y muerto hasta su hito: la puerta del vecino en el 37 (va
al 41), la del 48 a Stash (57), y el caño del 38 si el HQ va a otro mapa y
ese mapa no entra en este hito.

# Lo que hay que resolver, en orden

**1. Las decisiones de taro** (preguntas 1, 2 y 3 del plan): qué hace el
límite del 49, cómo entra el 38, y qué pasa con `test-main`. Sin las tres no se
puede cerrar este hito.

**2. El conversor se planta en el 37.** "El evento 11 se hornea en el mapa y
además se dibujaba con una paleta ajena": es `PawnDoorTop`, un tile del ChipSet
en (67,29). `eventos_horneables` tiene que dejar afuera a un evento que se
dibuja con una paleta prestada, que es lo que su comentario ya prevé. El orden
importa: las prestadas salen de `npcs_dibujables`, que corre **después** de
hornear, así que o se pregunta antes o se deshace el horneado de ése. Medido
con un parche en memoria que no hornea ese evento: el 37 convierte y todo lo
demás sigue.

**3. El 38** (pregunta 2). Si se parte, la costura es natural: el HQ de los
Vipers es la franja de arriba, a la que sólo se entra por los `Teleport` de los
eventos 20 y 21 —a (2,10) del mismo 38— y se sale por el 26 —a (73,65)—. Las
filas 33 a 74 son las filas 0 a 41 del mapa 8 celda por celda. Estimado con
celdas distintas de 16x16 (no con tiles de 8x8, que es lo que cuenta la VRAM):
cortando en la fila 33, arriba 172 y abajo 275 de 388; con el 38 entero en 476
tiles de 8x8 y el tope en 448, los dos pedazos tendrían que entrar con margen.
Medirlo con el conversor antes de dibujar nada.

**4. El límite del 49** (pregunta 1). Con el 36 compilando la página 1, la
página 2 —la de cada vez que se vuelve al auto— sigue sin compilar por el
`Teleport [49, 1, 26]`, y el jugador queda trabado en negro la segunda vez.
Eso tiene que quedar resuelto acá, no en el hito 5.

**5. El presupuesto de `test-main`** (pregunta 3). Con los cinco mapas de este
hito que convierten (37 39 47 48 56) `test-main` llega al banco $7B de $7D;
con el 38 puede no entrar. Medir con `testmain.py` de
`/extras/scratch/lashe-plan/` antes de sumar a `MAPAS`.

# Pruebas

- **Un recorrido nuevo**, `pruebas/abl/test_recorrido_lashe_golden.py` o el
  nombre que convenga, sobre `release`: arranca con los switches 132 (el auto
  elegido), 130 (rojo) y 54 o 56 (el compañero), que hacen correr la página 5
  del evento 1 del mapa 4 —la charla en el auto—, pasa por el 34 y llega al
  36. De ahí, **una vez por sector**: elegir la opción (hito 0), llegar a la
  celda del `Teleport`, comprobar grupo (Talan + compañero) y caminar hasta el
  auto, subirse, volver al 36 y comprobar que corre la página 2. Una foto por
  sector, como `Recorrido.foto`.
- **El HQ del 38 por la rama de Arden**: el caño, el `PanScreen` y el 169
  prendido.
- **El 47 por la rama de Saldra**: el evento 15 y el 181.
- **Los cuadros perdidos** caminando en el 37 y en el 38, como se midió el 11:
  el 8, que tiene su tamaño, era de los más cargados.
- Las goldens nuevas se muestran todas, lado a lado, antes de mergear.

# Qué tiene que mirar taro jugando

Los cuatro sectores con el auto: que la elección lleve a cada uno, que al volver
al auto se pueda elegir otro, el HQ de los Vipers por el caño con Arden, los
guardias del Sector 33, la tienda del 56 y el pad de Talan. Y los NPCs con
paleta prestada del 37 —las dos puertas de tile y la gente que aparece con el
161—, que es lo que el reparto de CGRAM deja: se ven con colores de otro.

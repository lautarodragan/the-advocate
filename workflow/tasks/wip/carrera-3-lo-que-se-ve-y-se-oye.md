---
name: "Carrera 3: lo que se ve y se oye"
description: "El cartel de los controles de la carrera como mensaje, y los efectos de sonido adentro de las rutas forzadas"
type: feature
---

# Qué

El hito 3 de `todo/la-carrera-y-lo-que-sigue.md`: las faltas 4 y 5. Sale de
`main` en `69e66ed`.

* **El cartel de los controles** (`EscapeInst`): decidido, la opción (a). Un
  fork del 49 que cambia el `ShowPicture` por `ShowMessage` con el mismo
  texto que la imagen.
* **Los sonidos adentro de las rutas**: `todo/los-sonidos-adentro-de-las-rutas.md`.
  El caso que lo pide es el puente de la carrera, pero general.

Números reservados: opcode 0x32 y la RAM lejana $7E79A0-$7E79BF.

# Status

2026-09-27: en curso.

# El cartel

El texto, leído de la imagen del juego:

    Escape from Lashe City

    Use the UP and DOWN arrow keys to change lanes, and avoid the
    traffic!

    Fewer crashes means better rewards!

    Press any key to begin.

No entra en una ventana de 39 columnas por cuatro renglones, así que son dos
cuadros: el título y los controles; los choques y "Press any key to begin."

**El `KeyInputProc` que esperaba la tecla se sacó**, y el `ErasePicture` de
la imagen que ya no está. El mensaje se cierra con A y el `KeyInputProc`
pedía después otra tecla más, con la pantalla negra y nada que lo dijera:
dos toques donde el original pide uno. La variable 151, donde guardaba la
tecla, no la lee ningún mapa ni ningún evento común (medido sobre `data/`).
Lo que se pierde: en el original cualquier tecla arranca, y acá sólo la que
cierra el mensaje.

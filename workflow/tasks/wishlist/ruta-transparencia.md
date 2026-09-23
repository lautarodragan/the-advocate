---
name: "Ruta: transparencia"
description: "Las órdenes 40 y 41, que suben y bajan la transparencia"
---

# Qué

Las órdenes de ruta **40 y 41**, subir y bajar la transparencia de a un octavo.
Hoy se aceptan y se tiran al compilar.

# Status

Anotado, sin empezar.

# Por qué

Las **ocho rutas del juego** que las usan son las cuatro pantallas del mapa 2
atenuándose mientras Manta hackea. Tirarlas —y no rechazar la página— es lo que
deja compilar esa escena entera; lo que se pierde es el fundido, que **sobre
tiles de fondo la SNES no hace barato**: atenuar un sprite por partes pide color
math.

Ojo con el efecto de borde al hacerlo: una ruta que se quedara sin órdenes por
esto **no se emite**, porque RM2k la consume entera en el cuadro y no deja nada
que esperar.

La otra orden que corre la misma suerte es **`play_sound_effect`**, que también
se acepta y se tira; las dos juntas en `traducir`, en `tools/port/eventos.py`.
Tirarlas no cuesta cuadros —RM2k no le toca el contador de parada— y con eso el
bytecode sigue siendo un byte por orden.

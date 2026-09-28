---
name: "Bug en caño en mapa 0008"
description: "Edge case al subirse al caño en Lashe City 34,35"
type: bug
---

Si dejo apretado el auto-fire del emulador (que es más rápido que
el que tenemos implementado directamente en el rom), 
puedo subir y bajar del caño sin apretar ningún otro botón.

El EV0042 triggerea la subida con Action Button. Te deja sobre 
EV0043. EV0043 hace lo mismo, pero para bajar.

Por lo que vi, la subida es irrelevante.
Creo que lo que pasa es que el auto-fire del `A`
triggerea el evento EV0052, que está sobre el caño.
Ese evento se supone que le podés interactuar solo desde
la izquierda, nunca _sobre_ él.

No logré reproducirlo con el auto-fire propio del juego.
Tampoco pude reproducirlo en el juego original.

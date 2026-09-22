---
name: "El sistema de imágenes"
description: "ShowPicture entero, más allá del cartel"
---

# Qué

El sistema de imágenes más allá del cartel: que la ROM dibuje más de un
`ShowPicture` por cartucho.

# Status

Anotado, sin empezar. Estaba en "Lo que falta del port" de `ESTADO.md`. Los
comandos que no entran se siguen aceptando sin hacerse.

# Por qué

La ROM dibuja **un** `ShowPicture` por cartucho, que es el caso fácil: ver "El
cartel del 'One year previously'" en `ESTADO.md`, y el cómo en `README.md`.

Lo que costaría el resto está medido, y el detalle está en "Lo que costaría el
sistema de imágenes entero" del README: **34 `ShowPicture` en el juego, 20
carteles distintos**, y 7 de esos 34 comandos son de los que el modelo de hoy
sabe hacer.

Y el sub-dato que decide la forma de la solución: **cinco de esos carteles son
de 320x240 exactos, y con objetos no se pueden hacer** —serían 56 de los 128 de
OAM y 32 de los 34 tiles por línea—. Ésas piden prestarle una capa al cartel, y
con eso el mapa se recarga al borrarlo.

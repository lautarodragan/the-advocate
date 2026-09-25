---
name: "El salto del héroe ignora su velocidad"
description: "Los eventos saltan según su velocidad y el héroe siempre a la del paso normal"
type: bug
---

**El salto del héroe usa una velocidad fija** —`SALTO_VELOCIDAD`, la de la
velocidad 4— mientras que los eventos la sacan de `salto_por_vel`, que es el
`jump_speed[move_speed - 1]` de RM2k. Un `increase_movement_speed` sobre el
héroe le cambia el paso y no el salto.

Apareció el 2026-09-22, arreglando `el-salto-que-queda-colgado.md`, y quedó
anotado en el comentario de `salto_avanzar_heroe`. Ya estaba así de antes: ese
arreglo no lo tocó.

Hecho es: el héroe salta con su velocidad, como los eventos, con una prueba que
lo mire. Ojo con que cambiar la duración del salto **mueve la cámara más rápido**
y el mapa se dibuja de a una fila por vuelta: ver
`el-mapa-corrido-al-volver-de-una-cinematica.md`.

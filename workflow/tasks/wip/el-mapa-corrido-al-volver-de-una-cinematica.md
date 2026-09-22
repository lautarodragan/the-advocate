---
name: "El mapa corrido al volver de una cinemática"
description: "Los tiles dibujados quedan una o dos celdas por encima de la colisión"
---

Taro lo reportó el 2026-09-22, y dice que **en algún momento anduvo bien**.

Después de la secuencia de los Neon Vipers —el mapa 14, `NV Get Talan to Work`—
y de salir por su cinemática al mapa de Lashe City del que se entró, **lo
dibujado queda corrido una o dos celdas hacia arriba respecto de la colisión**:
se camina sobre paredes y se choca contra el aire, y los teleports están
movidos lo mismo. **La colisión y los eventos coinciden entre ellos**: el que
miente es el dibujo. **Se arregla con cualquier teletransporte.**

## La causa, con el código delante

`stream_map` redibuja **una sola fila y una sola columna por vuelta**, y anota
la posición nueva completa:

    lda camara_y / lsr a x3      ; la fila de 8 px
    cmp win_row / beq sin_fila
    sta win_row                  ; anota la fila nueva, salte lo que salte
    jsr build_row                ; pero dibuja UNA

Su propio comentario dice la premisa y quién la iba a romper: *"La cámara se
mueve como mucho dos pixeles por vuelta y sólo por un eje... Si algún día la
cámara pudiera saltar —un teleport, un cambio de mapa— eso no es un ajuste de
esta rutina sino un `fill_window` entero"*.

La premisa ya no vale, y por dos lados medidos:

* **`PanScreen` mueve la cámara además del héroe** (`pan_px`/`pan_py` entran en
  `follow_camera`). Los del mapa 14 son horizontales a 2 px por cuadro, pero el
  juego tiene pans de **8 px por cuadro** (velocidad 6, `2 << vel` en 1/16 de px);
* **el héroe ya no camina siempre a 2 px**: `paso_medio_por_vel` es
  `2, 4, 8, 16, 32, 64` en octavos de pixel, o sea **hasta 8 px por cuadro** a
  velocidad 6.

Las dos cosas suman en el mismo eje. Con más de 8 px en una vuelta se saltea
una fila, y como `win_row` queda anotada como si se hubiera dibujado, **la fila
vieja se queda ahí para siempre**: la ventana es un toro —la celda `(mx,my)`
vive en la ranura `(my mod 32)`— así que el efecto es exactamente "todo corrido
una o dos celdas". Y cualquier teletransporte lo arregla porque rellena la
ventana entera.

## Lo que falta

Reproducirlo en el arnés —una ruta rápida más un pan, o la secuencia del mapa
14—, arreglarlo y dejar la prueba. El arreglo probable es que `stream_map`
alcance a la cámara en un lazo en vez de asumir una fila, y que un salto grande
pida `fill_window`.

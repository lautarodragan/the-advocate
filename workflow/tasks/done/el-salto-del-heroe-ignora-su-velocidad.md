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

# Lo hecho, el 2026-09-26

**La causa era la de arriba, tal cual**: `armar_salto_heroe` arrancaba en
`SALTO_PASO - SALTO_VELOCIDAD` y `salto_avanzar_heroe` restaba
`SALTO_VELOCIDAD`, las dos con la constante de la velocidad 4. `git blame` da
el commit que partió `main.s`; `git log -S` lleva a `a95ac7f`, que introdujo el
salto cuando el héroe no cambiaba de velocidad, y el comentario que dejó el
arreglo del salto colgado ya lo daba por divergencia.

Ahora las dos le piden el descuento a `salto_del_heroe`, que es `salto_por_vel`
—la misma tabla de los eventos— indexada con `FAR_HERO_VEL`. Se lee cada
cuadro, como `Game_Character::Update`, que llama a `GetMoveSpeed()` cada vez.
`SALTO_VELOCIDAD` desapareció del `.inc` y de `eventos.py`; en su lugar
`eventos.SALTO_POR_VELOCIDAD` es la tabla de RM2k que miran las pruebas.

**La prueba** es `pruebas/rpgmaker/test_salto_velocidad.py`, con los casos
`salto-heroe-lento` (velocidad 1) y `salto-heroe-veloz` (velocidad 6) más el
`salto` de siempre (4): cuenta los ticks con `ruta_salto` distinto de cero
contra `ceil(256 / s) - 1`. Sin el arreglo da rojo en las dos velocidades
nuevas —"a velocidad 6 … en RM2k está 3 ticks en el aire; acá estuvo 10"— y
la de 4 pasa, que es lo que dice que el conteo mide lo mismo que RM2k.

**Ninguna golden se movió.** Ninguna prueba de la tanda ni del recorrido salta
al héroe a otra velocidad que la 4.

## La cámara

En el juego, contando la velocidad desde 4 al principio de cada ruta, los
saltos del héroe a otra velocidad son doce: once a la 3 —más lentos, así que la
cámara va más despacio que antes— y uno a la 5 en el mapa 3, de dos celdas en
x y una en y, que son unos cuatro pixeles por cuadro. Ninguno pasa de la fila
por vuelta. Lo que no se mira es una velocidad que venga de una ruta anterior:
un salto largo a la 6 —cinco celdas en cuatro cuadros— sí la pasaría, y no hay
ninguno en las rutas del juego que lo arme en la misma ruta.

## Lo que tiene que mirar taro

Los saltos del héroe a velocidad 3 duran dieciséis cuadros en vez de once: el
del mapa 19 (tres celdas hacia arriba), el 98, el 105 y el 132, entre otros.

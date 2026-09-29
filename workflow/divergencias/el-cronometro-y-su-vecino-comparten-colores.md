# Qué

Los dígitos del cronómetro comparten paleta con un personaje —ver
`decisiones/el-cronometro-no-tiene-paleta-propia.md`—, y si el personaje tiene
uno de sus dos colores, negro o rojo puro, **los dos usan la misma entrada de
CGRAM**. Mientras el cronómetro se ve, esa entrada va sin teñir, porque en RM2k
los dígitos no se tiñen; así que ese color del personaje tampoco se tiñe.

El resto del personaje sí, y sin cronómetro en pantalla, todo: lo hace
`upload_timer_pal`, que sube sin teñir sólo las entradas de los dígitos y sólo
mientras se ven.

# Medido

En `release`, el 2026-09-25, el personaje comparte el negro en los mapas 2 y 10,
y los dos colores en el 11, el 17, el 21 y los seis del save point (8, 20, 23,
26, 28, 32). Cambia con el reparto de paletas: la tabla y cómo se sacó están en
`tasks/testing/el-tinte-no-tine-al-que-comparte-paleta-con-el-cronometro.md`.

Qué tinte lo destapa:

* **el negro**, sólo uno que aclara un canal —por encima de 100—: oscurecer y
  desaturar dejan el negro en negro;
* **el rojo puro**, casi cualquiera: oscurecer, desaturar o correr el rojo.

En el juego, el cronómetro coincide con un tinte dos veces: el despertador de
Talan corre con la saturación en 40 por el mapa 7 y Lashe City hasta el 16 —el
save point del mapa 8 conserva su rojo—, y el del bosque en llamas corre sobre
(120, 50, 50) en el 312, que no está en `release`.

# Cómo se ve hoy

Ninguna prueba lo mira: la tanda arma sin cronómetro, y el caso `timer` corre en
el mapa 6, donde los dígitos no comparten color con nadie.

# Cuándo deja de alcanzar

Si se nota. El arreglo es que los dígitos tengan **entradas propias** aunque el
color ya esté en la paleta: dos entradas en vez de las que falten. No es una
paleta, pero el save point usa quince colores y en el mapa 8 las ocho paletas
están llenas, así que ahí habría que bajarle colores a alguien.

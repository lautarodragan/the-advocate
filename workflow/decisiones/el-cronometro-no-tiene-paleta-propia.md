# Qué

**El cronómetro no tiene paleta propia**: entra en la de cualquier personaje que
use trece colores o menos.

# Por qué

Tenerla aparte costaba un evento sin dibujar en el mapa 2 —la celda del medio de
la puerta que Core rompe—, y un evento que no se dibuja igual ocupa lugar en
`npcs_dibujables`.

Lo que esto cuesta hoy, y la idea de reservarla sólo mientras el cronómetro
corre, está en `wishlist/timer-paleta-dinamica.md`.

# Cuándo deja de alcanzar

En un mapa que llene las ocho paletas a quince colores. Ahí se le hace lugar
bajando a un personaje a catorce —el que menos pixeles mueva, y nunca uno de
líder—, y si ni eso alcanza el conversor corta y lo dice. Ver "the timer
**before the events drawn with a chipset tile**" en `drawable_npcs`, en
`tools/port/sprites.py`.

# Lo que obliga en la ROM

Como la paleta es de un personaje, **el tinte no la puede saltear entera**: los
dígitos no se tiñen y el personaje sí. `upload_timer_pal` sube sin teñir sólo
las entradas de los dígitos, y sólo mientras se ven. Hasta el 2026-09-25 subía
la paleta entera, que era lo correcto cuando los dígitos la tenían para ellos
solos, y el personaje quedaba sin teñir. Los colores que el personaje comparte
con los dígitos siguen sin teñirse mientras el cronómetro se ve: ver
`divergencias/el-cronometro-y-su-vecino-comparten-colores.md`.

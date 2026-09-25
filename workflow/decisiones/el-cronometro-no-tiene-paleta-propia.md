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
líder—, y si ni eso alcanza el conversor corta y lo dice. Ver "por último, el
cronómetro" en `tools/port/snes_convert.py`.

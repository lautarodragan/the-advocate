# Qué

La caja de la animación de batalla necesita **una paleta de sprite entera para
ella sola**: sus quince colores son de la animación y se pisan cuando empieza
otra, así que un personaje metido ahí cambiaría de color con ella. En los mapas
que muestran animaciones los personajes se reparten **siete** paletas y no
ocho, y eso les fusiona más colores que en RM2k, donde no hay paletas.

**Salvo que con siete no entre el cronómetro**: ahí manda él, se vuelve a ocho y
ese mapa no dibuja animaciones. La regla está en `tools/port/snes_convert.py`,
donde se reparten las paletas de personajes.

# Medido

El 2026-09-12 los mapas con animaciones eran el 2 y el 3, los de la intro. El
que se quedaba sin caja por el cronómetro era el 9.

# Cómo se ve hoy

Los personajes de esos mapas pueden tener algún color fusionado de más; las
fusiones de cada mapa las deja escritas el conversor al lado de la ROM.

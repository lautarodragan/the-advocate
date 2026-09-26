---
name: "La terraza pierde cuadros en los destellos"
description: "Recalcular las paletas de FlashSprite y FlashScreen se come casi todo el cuadro en la terraza del mapa 32"
type: bug
---

taro nota lag en la escena de la terraza (mapa 32) y en el destello azul de
Kersh (`done/dos-destellos-a-la-vez.md`: "mejoró, pero no es perfecto; lo que
queda es lag"). La investigación de los chips (`wishlist/chips-sa-1-y-s-dd1.md`,
"Dónde se va el cuadro hoy") midió que en las vueltas pesadas casi 200 de las
262 líneas se van en recalcular paletas: `destello_tick` ~103 y
`flashes_tick` ~94. Es CPU pura, y medida en snes9x: en el hardware puede ser
peor (ver lo que dé la medición en bsnes del minijuego del mapa 11).

Ideas que propuso esa investigación, sin chip: calcular la paleta destellada
una vez por paso de intensidad y no cada cuadro, o repartir el trabajo entre
cuadros. Medir primero en bsnes.

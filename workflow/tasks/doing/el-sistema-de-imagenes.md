---
name: "Plan: el sistema de imágenes y la portable console"
description: "Qué usa la portable console de ABL (ShowPicture, MovePicture, eventos comunes automáticos y paralelos, la entrada del control), cuántas imágenes y de qué tamaño, cómo dibujarlas en modo 3 y qué se congela mientras se muestran; para sacar de ahí las tareas"
type: research
assignee: Jilguero
---

De taro, el 2026-10-01: le interesa `ShowPicture` y "todo el sistema de la
portable console" —el menú propio de ABL, hecho con eventos comunes e
imágenes—, porque sirve para sistemas custom de muchos juegos. Dijo que es
aceptable usar el MSU-1; con 46 bancos libres de 64 KB y las imágenes del
juego estimadas en ~430 KB con LZ2, Hornero cree que entran en la ROM sin
romper `decisiones/el-juego-se-juega-sin-msu-1.md`.

La idea de taro para dibujarlas en modo 3, que tiene dos capas: "en la
práctica la mayoría de los ShowPicture impiden moverse mientras se muestran.
No sé si congelan otras cosas, como movimientos de eventos o tiles
animados, pero no descartaría la posibilidad de hornear en runtime la
imagen o capas del mapa, o no mostrar eventos mientras se muestra una
imagen. No es algo que sirva siempre, pero creo que en muchos casos sí".

El menú custom propio, con modo 5 y fuente, quedó en el wishlist:
`wishlist/un-menu-custom-propio.md`. Esto es antes: las imágenes como las
usa RM2k.

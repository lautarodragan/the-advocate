---
name: "Que el mapa 1 de Vampires Dawn se arme sin su caja de animaciones"
description: "Si la caja de las animaciones de pelea de un mapa no entra en el banco de sprites, el mapa queda sin ellas con un aviso, en vez de cortar el armado"
type: feature
agents: [Carpintero]
assignee: Carpintero
---

Vampires Dawn no arma: con el System de ABL por la perilla (b8224c3 del
repo del juego) se corta en "map 1: shows battle animations and the 64
tiles of its box don't fit in the sprite bank: it spends 320 of 0. See
`animacion_de_mapa`." Es la misma línea de "degradar en vez de fallar":
el mapa se queda sin esas animaciones, con un WARNING. Lo que aparezca
detrás, del mismo tipo, también.

taro, el 2026-10-06: "vamos con esos dos en paralelo", con Sonnet.

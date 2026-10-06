---
name: "Que el mapa 1 de Vampires Dawn se arme sin su caja de animaciones"
description: "Si la caja de las animaciones de pelea de un mapa no entra en el banco de sprites, el mapa queda sin ellas con un aviso, en vez de cortar el armado"
type: feature
agents: [Carpintero]
assignee: taro
---

Vampires Dawn no arma: con el System de ABL por la perilla (b8224c3 del
repo del juego) se corta en "map 1: shows battle animations and the 64
tiles of its box don't fit in the sprite bank: it spends 320 of 0. See
`animacion_de_mapa`." Es la misma línea de "degradar en vez de fallar":
el mapa se queda sin esas animaciones, con un WARNING. Lo que aparezca
detrás, del mismo tipo, también.

taro, el 2026-10-06: "vamos con esos dos en paralelo", con Sonnet.

## Lo hecho (Carpintero, 2026-10-06)

* Wally: si un mapa no entra en ningún reparto de VRAM con la caja de
  animaciones (64 tiles de sprites, que no se pueden achicar), se convierte
  de nuevo sin ella y dice WARNING; el ROM no dibuja animaciones ahí.
  Prueba en `wally/tests/whole_map.rs`, vista en rojo antes.
* **Pero no era eso lo que cortaba el mapa 1.** El mapa 1 de VD es de
  300x300 y su fondo tiene 597 tiles únicos de 8x8; el reparto más grande
  da 544. No entra con ni sin caja, con ni sin cuadros: es el fondo. Que lo
  diga bien: el mensaje del conversor ahora dice "fits no VRAM layout" con
  los tres números, en vez de "spends 320 of 0" del banco de sprites.
* Lo que falta para que VD arme es decidir qué se hace con un fondo que no
  entra (fusionar tiles parecidos, bajar el mapa de resolución, partirlo):
  eso cambia lo que se ve, y no se degrada solo.

Tanda de ABL con estas herramientas: 1147 verdes y `abl.sfc` identico
(`602b60e0...`). La caja se pierde solo como ultimo recurso, despues de las
ranuras compartidas y del cache: la primera version la soltaba antes y
cambiaba el ROM de ABL. Al mergear: reinstalar `wally` y `convert`.
No verificado en un juego real: VD no llega a ese camino, se corta antes.

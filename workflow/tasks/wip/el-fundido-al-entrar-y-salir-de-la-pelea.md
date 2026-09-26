---
name: "El fundido al entrar y salir de la pelea"
description: "La transición de RM2k al empezar y terminar una pelea, que además tapa la carga del paquete de audio"
type: feature
---

Hoy la pelea entra y sale sin transición. En RM2k hay una (la de la base de
datos del sistema, "Battle Start" y "Battle End"; ver
`wishlist/las-otras-transiciones-de-rm2k.md` para las que no son el fundido).

Además de parecerse al original, taro señaló el 2026-09-26 que **tapa el tiempo
de carga**: con las muestras repartidas por paquete de mapa (paso 6 de
`la-calidad-de-la-musica.md`), subir el paquete de la pelea pasa de ~0,7 s a
~1,3 s congelados al entrar, y otro tanto al salir. Con un fundido, esa carga
cae adentro de la pantalla negra, como ya pasa en el cambio de mapa.

Mirar qué transición pide la base de datos de ABL, si el fundido que ya
existe para los mapas alcanza, y medir que la carga quede entera adentro.

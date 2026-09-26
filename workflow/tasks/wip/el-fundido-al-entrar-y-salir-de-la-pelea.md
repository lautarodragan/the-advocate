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

# Qué pide la base de datos

`battle_start_fadeout = 16`, `battle_start_fadein = 17`, `battle_end_fadeout =
17`, `battle_end_fadein = 16`. En `Game_System::GetTransition` de easyrpg el 16
es `ZoomIn`/`ZoomOut` y el 17 `MosaicOut`/`MosaicIn`, de 41 cuadros cada una.
Además, al entrar, `Scene_Map::TransitionOut` antepone siempre dos destellos
blancos de diez cuadros (`PrependFlashes(31, 31, 31, 31, 10, 2)`).

# Qué se hizo

Todo en `rom/src/fundido_de_pelea.s`, y bloqueando como la pelea: no cuesta
ningún tick.

* los destellos, con color math: el color fijo sumado a toda la pantalla;
* el zoom **como fundido** —la decisión de taro para lo que la consola no
  hace—, con la rampa del teletransporte;
* el mosaico con el mosaico del PPU, **y fundiendo a la vez**: RM2k no
  oscurece en el mosaico, pero la carga tiene que caer en negro. Así, cada
  lado se apaga, carga, y el otro prende.

Las goldens de la pelea no se movieron: ninguna captura cae adentro de la
transición. Lo que se corrió fueron los números de `test_batalla_golden.py`
—68 cuadros, lo que la transición suma antes de que la pelea tome el
control—, el de `test_cores.py`, y `Pelea.cerrar`, que ahora espera a que el
mapa vuelva a correr.

`test_fundido_de_pelea.py` cobra que cada cuadro en que el paquete avanza se
ve negro, al entrar y al salir. Sin el cambio da 83 de 83 cuadros visibles de
los dos lados (droide del mapa 2, `release`).

# Medido, el droide del mapa 2 en `release`, sin MSU-1

| | antes | después |
|---|---|---|
| entrar: de la pelea pedida al control | 90 cuadros, 83 con el mapa congelado | 158: destellos 20, fundido 23, carga 83 en negro, escena 9 en negro, mosaico 23 |
| salir: de la A final al mapa corriendo | 104, 83 con la pelea congelada | 150: mosaico 23, carga 83 en negro, mapa 22 en negro, fundido 22 |

La carga tarda lo mismo; lo que se suma son las rampas.

# Para mirar jugando

* que los destellos se parezcan: son suma de color, no alfa, y los sprites de
  las paletas 0 a 3 —el héroe— destellan menos, que es del hardware;
* el mosaico de la pelea, que en RM2k llega a bloques de 41 pixeles y acá a
  16, el tope del PPU;
* ya estaba antes: al empezar la pelea del droide vuelve a verse el último
  mensaje ("Get ready everyone!") durante los destellos y el fundido. Está
  igual en `main` sin este cambio —antes se veía congelado—, no es de acá.

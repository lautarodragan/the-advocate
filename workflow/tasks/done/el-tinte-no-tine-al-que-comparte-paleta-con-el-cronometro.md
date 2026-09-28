---
name: "El tinte no tiñe al que comparte paleta con el cronómetro"
description: "tinte.s subía sin teñir la paleta entera de los dígitos, que desde el 09-07 comparte un personaje; ahora sube sólo las entradas de los dígitos"
type: bug
assignee: taro
---

Encontrado midiendo si se juntan `release` y `test-main` (ver
`juntar-release-y-test-main.md`), el 2026-09-25. **Pasaba en `release`.**
Arreglado en el commit que mueve esta tarea a `testing/`.

# Qué pasaba

`rom/src/tinte.s` volvía a subir **la paleta entera** de los dígitos sin
teñir, porque "los dígitos tienen una paleta para ellos solos" (`5be4ade`,
2026-09-04). Desde `034d721` (2026-09-07) esa paleta la comparten con un
personaje, y ese personaje quedaba sin teñir. Y no sólo con el cronómetro
corriendo: la subida miraba si el mapa **llevaba** los glifos, no si se veían,
y `release` los lleva en todos sus mapas.

Las cinco goldens de la puerta del mapa 7 que destapó la medición —`sacudir-60`,
`cerrar-400`, `cerrar-right-400`, `autocierre-63` y `autocierre-3-185`— lo
muestran si se arma `test-main` sin `--sin-timer`: **la puerta de la casa de
Talan** (un evento dibujado con los tiles 111 y 117 de `BLchp1`) queda gris en
la pantalla teñida de azul. 512 pixeles en cada una con el código de antes, 0
con el de ahora. **No hay goldens que re-congelar por esto.**

# Lo que se averiguó antes de tocar nada

**RM2k no tiñe el cronómetro.** En easyrpg el tono de `TintScreen` lo aplica
`Spriteset_Map` a su tilemap, a sus personajes y al panorama, y `Sprite_Timer`
no es de ahí (`Priority_Timer` 140 contra `Priority_Screen` 90). Así que saltear
los dígitos estaba bien; lo que estaba mal era saltear la paleta entera.

**Los dígitos usan dos colores**, negro y rojo puro (`colores_del_timer`), y
el personaje con el que comparten a veces tiene uno de los dos o los dos. Con
ésos no hay arreglo sin gastar entradas: son **la misma entrada de CGRAM**.

**Quién comparte**, en `release` —medido corriendo el conversor con
`digitos_del_timer` envuelto por un script descartable—:

| Mapas | Quién | Comparte con los dígitos |
|---|---|---|
| 1, 3, 6, 14, 16, 30 | eventos dibujados con un tile del ChipSet | nada |
| 7 | la puerta de la casa de Talan (`BLchp1` 111 y 117) | nada |
| 9 | `Future1:7` | nada |
| 13 | `Future3:5` | nada |
| 2 | tres tiles de `ChipSet3` | el negro |
| 10 | `People4:4` | el negro |
| 11 | `Object2:6` | los dos |
| 17 | `Men1:5` | los dos |
| 21 | dos tiles de `caveD` y `Object2:5` | los dos |
| 8, 20, 23, 26, 28, 32 | el save point | los dos |
| 4, 5, 12, 18, 19, 29, 33, 34, 36 | nadie: la paleta es de los dígitos | — |

**Dónde se usa el cronómetro en el juego** (`TimerOperation` en `data/`): no es
uno solo. Hay **tres cuentas atrás visibles** —el despertador de Talan (mapa 7,
600 s), la cantera (mapa 150, 300 s) y el bosque en llamas (311 a 312, 120 s)—,
y en los mapas 9 y 11 el oficial del tram la pone desde una variable y la para
en el mismo evento, así que ahí no se ve. **Dos de las tres coinciden con un
tinte**: el despertador arranca poco después de un `TintScreen` con la
saturación en 40 que ni el mapa 7 ni el 8 deshacen —la cuenta atrás corre sobre
la pantalla desaturada hasta que la para el mapa 16—, y la del bosque arranca
con la pantalla en (120, 50, 50). O sea que el caso no es sólo de la tanda: en
Lashe City el save point estaba entero sin teñir mientras todo lo demás estaba
desaturado.

# El arreglo

Sin paleta nueva y sin tocar el reparto:

* `subir_timer_pal` sube de la ROM **sólo las entradas de los dígitos**, que el
  conversor emite como `timer_mascara` —una palabra por mapa, aparte de
  `mapa_tabla` porque el registro está en sus 128 bytes—.
* Y sólo **mientras el cronómetro se ve**. Al prenderse o apagarse con un tinte
  puesto, `timer_repintar` pide volver a subir la sombra, porque esas entradas
  cambian de dueño.

Lo que queda está en `divergencias/el-cronometro-y-su-vecino-comparten-colores.md`.

# Qué mirar jugando

El save point de Lashe City (mapa 8) con el despertador corriendo: antes se veía
con todos sus colores sobre la pantalla desaturada; ahora se desatura con el
resto, **salvo su rojo puro**, que queda rojo mientras se ve el cronómetro. Y la
puerta de la casa de Talan en cualquier escena teñida del mapa 7.

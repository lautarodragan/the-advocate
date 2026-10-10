---
name: "Las puertas cerradas por los cuatro lados se atraviesan"
description: "Un evento de tile debajo del héroe cuyo tile cierra todo impone $00, y `pass_has` guardaba ese valor como bandera: quedaba apagada y `pass_with_event` no miraba las filas"
type: bug
assignee: taro
agents: [Hornero]
---

De taro, el 2026-10-10: en Tasgarde Military Base (mapa 74 de ABL) la
puerta —Door1Bottom y Door1Top, eventos 2 y 1— se atraviesa sin que
DoorGuard la abra. En RM2k un evento debajo del héroe, no atravesable y
con gráfico de tile impone la pasabilidad de su tile
(`Game_Map::IsPassableTile` de easyrpg), y los tiles 109 y 115 del
chipset 19 cierran los cuatro lados.

Medido con el arnés sobre el `release` de ABL: desde (19,40), arriba
sostenido, Talan termina en (19,32). Las filas de los dos eventos llegan
con +15 = $00, bien; pero `pass_has` está en 0.

`pass_look` (`far_npcs.s`) y el refresco de página (`event_pages.s`)
guardaban en `pass_has` el valor de la fila, no un uno: con $00 la
bandera dice "nadie impone". Nació en `da466bbe`, la carrera a 60
cuadros, que agregó la bandera.

## Hecho

Las dos escrituras guardan un uno (`7dcdcfce`). La prueba es de ABL,
`pruebas/rpgmaker/test_puerta_de_tile.py`: la puerta cerrada al cargar,
con la página del 279 —el otro camino, el refresco— y abierta con el 279
y el 280. Las dos primeras dieron rojo sin el arreglo, con Talan en
(19,32). Con el 280 solo la puerta sigue cerrada, y no es error: `Door1Top`
sigue en su página 1, con el 109; `DoorGuard` prende los dos.

**Verificado:** la tanda entera de ABL con el runtime del arreglo, sobre
`main` de ABL con las puertas del mundo de Hurón: ninguna golden cambió, y
todo verde menos la prueba nueva —que tenía mal el estado de "abierta"— y
el índice que no la nombraba, las dos arregladas y corridas de nuevo.
`just -f tools/justfile test` en verde.

**Lo que no cubre:** cualquier otra puerta del juego que estuviera abierta
por esto. Ningún recorrido cruzaba una puerta cerrada —si no, alguno
habría cambiado—, pero ahora todas las de un tile cerrado por los cuatro
lados frenan, como en RM2k: a jugar.

**Al mergear:** nada que instalar. `project` encuentra el runtime en el
checkout del que se instaló, así que el global ya lo ve, y la huella de
los cartuchos lo rearma.

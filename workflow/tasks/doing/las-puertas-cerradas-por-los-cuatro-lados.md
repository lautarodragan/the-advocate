---
name: "Las puertas cerradas por los cuatro lados se atraviesan"
description: "Un evento de tile debajo del héroe cuyo tile cierra todo impone $00, y `pass_has` guardaba ese valor como bandera: quedaba apagada y `pass_with_event` no miraba las filas"
type: bug
assignee: Hornero
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

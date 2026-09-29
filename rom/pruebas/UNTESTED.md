## `SetTimer` desde una variable negativa

Tenía la trampa de `plx`/`ply` —ver AGENTS.md, "La trampa que más veces
mordió"— y se arregló con el `cmp #0` de siempre, pero **no lo mide nadie**:
ninguna página de prueba lo emite, así que el arreglo es lectura del manual
del 65816 y no medición. El `IsActorInParty`, que estaba igual, siguió roto
hasta que una prueba lo midió: es lo que hace falta acá.

## Audio

`pruebas/rpgmaker/test_musica_paquete.py` le pregunta a la ROM si las muestras del
tema que dice estar tocando están de verdad en la ARAM (`FAR_ARAM_OF` contra
`song_samples`), y `pruebas/rpgmaker/test_bateria_suena.py` que las voces 6 y 7
—la batería, compartidas con los efectos— reciban lo que el stream les
escribe, leyendo su sombra.

Lo que **sigue** sin mirar nadie es que lo que sale del DSP
suene a lo que tiene que sonar: eso es oído, y es de taro.
  
## Dalia's Blast de las catacumbas

El `EV0001` paralelo que espera la
A con `KeyInputProc [176,1,0,1,0]`, tiene el mismo patrón que el motor de las
piedras: medido el 2026-09-19, sus 23 páginas (mapas 281 a 283 y 324 a 344)
**compilan**, pero ningún cartucho —ni los de las pruebas ni `release`—
lleva esos mapas, así que ninguna prueba mira que cerrar un mensaje
ahí no dispare la ráfaga. Si entran en un cartucho, ésa es la prueba que
falta.

## Que una `TileSubstitution` le cambie el terreno a la celda

`GetTerrainTag` pasa por `map_info.lower_tiles` antes de leer la tabla de
terrenos, así que sustituir un tile le cambia el terreno a todas sus celdas.
Acá sale gratis —el terreno viaja adentro del bloque, y `op_terrain` lee el
bloque **ya sustituido**— pero no hay con qué probarlo: `TileSubstitution` sólo
habla de los 144 tiles sueltos de cada capa, y **ningún ChipSet del juego tiene
dos de ésos con terrenos distintos** (medido sobre los 52). El mapa 5, que es
el único del cartucho de pruebas con más de un terreno, los tiene todos en sus
autotiles.

El día que el fork del mapa 11 traiga su ChipSet propio con un terreno por
cono, ése es el caso que falta.

# Qué

Al empezar una pelea, el mapa se va a negro **en mosaico**: después de los
dos destellos, los bloques crecen de 2 a 16 mientras el brillo baja, con la
misma rampa, cuadro por cuadro, con la que la pelea se va al terminar. Ver
`battle_fade_in` en `tools/runtime/battle_fade.s`.

RM2k hace lo que dice el `System` de la base de datos, y *A Blurred Line*
pide otra cosa para tapar el mapa: `battle_start_fadeout = 16`, que en la
tabla de `Game_System::GetTransition` de easyrpg-player es el zoom
(`TransitionZoomIn`). Las otras tres sí son el mosaico o el zoom que la ROM
ya hacía: `battle_start_fadein = 17` (la pelea sale del mosaico),
`battle_end_fadeout = 17` (se va en mosaico) y `battle_end_fadein = 16` (el
mapa vuelve con zoom).

El zoom la consola no lo hace —acercar el mapa es modo 7, y el mapa está en
modo 3—, y hasta el 2026-09-30 era un fundido, como decidió taro el
2026-09-26 para todas las que no se pueden. Ese día pidió el mosaico: "hagamos
que la transición de entrar a batalla sea la misma que de salida —la de los
cuadros—". Así que **no se lee el `System`**: la entrada es el mosaico para
cualquier juego, y es un cambio de diseño, no un arreglo.

Lo demás del mosaico es lo de siempre (ver
`las-transiciones-del-teletransporte.md`): **oscurece**, porque la carga del
paquete de audio tiene que caer en el negro, y **los sprites no se pixelan**:
el héroe y los eventos se ven enteros mientras el mapa se hace bloques. La
ventana del mensaje que abrió la pelea, si está, sí: es una capa del fondo.

**La vuelta al mapa sigue siendo un fundido**, que es lo que el zoom de
`battle_end_fadein` venía siendo. taro no la nombró.

# Medido

`test_la_entrada_tapa_el_mapa_con_el_mosaico_de_la_salida`, en
`pruebas/rpgmaker/test_fundido_de_pelea.py` de ABL, mide el lado de los bloques
en cada cuadro **mirando la pantalla** —en qué columnas cambia el color de
cada línea— y exige que la bajada del mapa al entrar sea la misma secuencia
que la de la pelea al salir. Con el fundido daba la entrada vacía.

# Cómo se ve hoy

Hablarle al droide del caso `linkage`: dos destellos, el mapa y el mensaje
se deshacen en bloques hacia el negro con el héroe nítido encima, y la pelea
sale de los bloques.

# Cuándo deja de alcanzar

Un juego cuyo `System` pida para tapar el mapa una transición que la ROM sí
hace y que no sea el mosaico —el corte, por ejemplo—: ahí habría que leerlo,
y el mosaico quedaría para las que la consola no hace.

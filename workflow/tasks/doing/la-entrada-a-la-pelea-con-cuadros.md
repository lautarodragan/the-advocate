---
name: "La entrada a la pelea, del lado del mapa, con la transición de cuadros"
description: "Al salir de la pelea y al entrar del lado de la pelea ya es la de los cuadros; al entrar, del lado del mapa, es un fundido"
type: feature
assignee: Biguá
---

De taro, el 2026-09-30: "hagamos que la transición de entrar a batalla sea
la misma que de salida —la de los cuadros—. Ya es así en la mitad del lado de
la batalla, al ingresar, pero del lado del mapa es un fade out".

## Qué pide el juego

El `System` de *A Blurred Line* (`rom/data/db/system.json`) dice
`battle_start_fadeout = 16`, `battle_start_fadein = 17`,
`battle_end_fadeout = 17` y `battle_end_fadein = 16`. En
`Game_System::GetTransition`, 16 es el zoom y 17 el mosaico. O sea que **el
juego no pide los cuadros para tapar el mapa: pide el zoom**, que la consola
no hace y que desde el 2026-09-26 era un fundido. La ROM no estaba
desobedeciendo el `System`; lo que taro pide es un cambio de diseño, y quedó
en `workflow/divergencias/la-entrada-a-la-pelea-en-mosaico.md`. No se lee el
`System`: el mosaico va siempre.

La vuelta al mapa (`battle_end_fadein = 16`, el zoom) **sigue siendo un
fundido**: taro no la nombró. Si la quiere en cuadros también, es el mismo
cambio en `battle_fade_to_map`, que está en el banco 0 y costaría unos 15 B
ahí —o un puente al lejano—.

## Lo hecho

`battle_fade_in` (`tools/runtime/battle_fade.s`, en el banco lejano) escribe
MOSAIC atado al brillo en la bajada del mapa, con la misma rampa que
`battle_fade_out`, y lo apaga ya en negro. Los sprites no se pixelan —el
héroe queda nítido—, igual que en el mosaico del teletransporte; la ventana
del mensaje que abrió la pelea sí, porque es una capa del fondo. El banco 0
no se movió: 182 B libres en `release` antes y después.

## La prueba

`test_la_entrada_tapa_el_mapa_con_el_mosaico_de_la_salida`, en
`rom/pruebas/rpgmaker/test_fundido_de_pelea.py`: mide el lado de los bloques
de cada cuadro **mirando la pantalla** —en cada línea, en qué columnas cambia
el color; con bloques de lado n sólo pueden ser múltiplos de n, y se cuenta por
línea para que el héroe, que no se pixela, no tape el mapa—, y exige que la
bajada del mapa al entrar sea la misma secuencia que la de la pelea al salir.

En rojo sin el arreglo: `al entrar [], al salir [2, 2, 3, 4, 4, 5, 6, 6, 7, 8,
8, 9, 9, 10, 11, 11, 12, 13, 13, 14, 15, 15]`. Con el arreglo, las dos
iguales. Una primera versión que contaba por pixel y no por línea perdía el
mosaico a partir de 9 cerca del negro, con el héroe dominando los cambios.

`just pruebas`: 901, en verde (900 + ésta). Ninguna golden se movió: ninguna
cae adentro de la transición, que no gasta ticks.

Las tiras, del caso `linkage` hablándole al droide —los 26 cuadros antes del
negro—: `/shared/capturas/2026-09-30-entrada-a-la-pelea/antes.png` y
`despues.png`.

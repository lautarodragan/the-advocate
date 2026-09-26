---
name: "La partida lleva su versión"
description: "Que una partida de otro build se rechace limpia en vez de cargar corrupta"
type: bug
---

Desde que `release` y `test-main` son un solo cartucho (2026-09-25), la
partida guardada cambia de tamaño cada vez que un caso nombra una variable
nueva o trae una tropa nueva: los casos viajan en la ROM que se juega. Medido
al juntar: una partida del `release` de antes, cargada en el unido, **no
carga** si detrás quedó lo que deja snes9x en la SRAM, y **carga corrupta**
(inventario, HP, SP, equipo, gráficos de actor y habilidades corridos) si
detrás hay ceros, porque la suma de control igual cuadra.

Que la cabecera de la partida lleve su tamaño o una versión derivada del
formato (`partida_tabla`), y que una que no coincide se trate como "no hay
partida". Ver `workflow/tasks/testing/juntar-release-y-test-main.md`.

No urge: taro prueba siempre desde cero y no comparte partidas entre builds.
Importa el día que un `.srm` viaje para reproducir un bug, o para quien juegue
builds seguidos.

# Lo que se hizo (2026-09-26)

La cabecera de cada ranura pasa de seis bytes a diez:

    $0100  "ABLS"          la magia, como antes
    $0104  suma            la suma de los bytes de la partida, como antes
    $0106  PARTIDA_BYTES   el largo, que el ensamblador saca de las mismas
                           constantes que `partida_tabla`
    $0108  PARTIDA_FIRMA   16 bits del CRC32 de qué variable de RM2k va en
                           cada ranura, de qué actor es cada par de habilidad y
                           cada ranura de experiencia, más ITEMS_N, SWITCH_BYTES
                           y ACTORES_N: `firma_de_la_partida`, en el conversor
    $010A  los datos

Ninguna de las dos palabras se sube a mano. La firma cubre lo que el largo no
ve: dos builds con la misma cantidad de variables y otra variable en la misma
ranura. Lo que **no** cubre: reordenar dos renglones de `partida_tabla` sin
cambiar el total, porque la tabla es fuente a mano y el conversor no la lee
(comentado arriba de la tabla).

`ranura_de_este_formato` (en `partida.s`) mira magia, largo y firma, y la usan
la pantalla de ranuras y `cargar_partida`: una partida de otro build **se ve
vacía** ("- Empty -") y elegirla empieza de cero, como una ranura vacía.

Vacía y no "corrupta": EasyRPG pone "Savegame corrupted" en `Window_SaveFile`,
pero es un texto suyo en inglés escrito en el código, no un término del LDB, y
la ROM saca del LDB todo lo que dice. Y es lo que la ROM ya hacía con una suma
que no cuadra.

La prueba: `test_una_partida_de_otro_build_se_ve_vacia_y_no_carga`, en
`pruebas/rpgmaker/test_titulo_dibujo.py`, con tres variantes: la partida de un
build de antes de este cambio (`sin-cabecera`), otro largo y otra firma. Guarda
de verdad por el menú, rearma la ranura corrida dos bytes con ceros detrás
—el caso que antes cargaba corrupto— y la escribe en la SRAM
(`retro.escribir_sram`, nuevo). Compara la pantalla de ranuras contra la de
cuatro vacías pixel por pixel y después elige la ranura.

Contra la ROM de `b581d4e`, `sin-cabecera` da rojo en 570 pixeles —la ranura 2
muestra a Talan con nivel "L 0"— y, salteando la comparación, en el mapa: la
partida corrida carga (mapa 5 y no el 4). Las otras dos no existen sin el
cambio (piden `PARTIDA_FIRMA`).

`release` y `test-special` hoy salen con firmas distintas, así que una partida
de uno no carga en el otro.

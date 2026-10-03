---
name: "Las letras de ancho variable, en baja"
description: "La fuente baja-ancho-variable de Espinillo en todo el juego: la ventana de mensajes, el menú, la pelea y las tiendas con texto compuesto y avance por letra, y el reparto de las cajas por ancho en pixeles"
type: feature
assignee: taro
---

De taro, el 2026-10-03, después de ver `2026-09-30-fuentes` en la SNES: le
gustan las dos de ancho variable y quiere probarlas en el juego. Esta es la
fase 1, la de baja (256, la resolución de siempre). La fase 2 es el modo 5
como perilla del proyecto, sobre lo que deje ésta: el compositor, la tabla
de avances, el reparto por pixeles y las pantallas en texto compuesto se
aprovechan las dos.

El estudio, la hoja y lo que costaría: `workflow/tasks/done/una-fuente-para-la-alta-resolucion.md`,
en ABL, y `experimentos/fuentes/` allá.

## Hecho (Calandria)

### La fuente

La hoja `baja-ancho-variable` es ahora `low-variable`, una fuente **del
motor**: `tools/rm2k-snes/text/fonts/low-variable.png`, con un README que
dice cómo editarla. El juego elige en `rm2k-snes.toml`, `[text] font`: `rm2k`
—la de RM2k, que sigue siendo una fuente más, de avance fijo—, una del motor,
o la ruta de una hoja suya. Una hoja propia entra en la huella de los
cartuchos. Para retocarla sin reinstalar: se copia al juego y se apunta la
clave a la copia.

Un glifo más en las tablas de la consola, el 95: un blanco tan ancho como el
`>` (DEL en el texto), para los `ShowChoice` y los `InputNumber`, que con un
espacio se movían con el cursor.

### El conversor

`refit` mide en pixeles (`Measure`), con los costos en letras de `n`: con la
fuente de RM2k da lo mismo que antes, al bit. La ventana de los mensajes mide
240 pixeles. Sobre los cuadros del ABL, con `rm2k-snes-screens boxes`:

    39 columnas:          1245 cajas rearmadas, 299 partidas en varias
    240 px, low-variable:    1 caja rearmada,     0 partidas

La única es "Isabella!!" del mapa 157, que trae una cola de espacios.

### La ventana de mensajes

x acumulada en `msg_x`, ocho fases, y el tope de pixeles con `font_reach`.

**Precompuesta, con el número.** Se escribieron las dos y dibujan igual pixel
por pixel. Sobre el mapa 6 con la cámara andando, contando cuadros de hardware
contra ticks mientras compone (el caso `anclada` y uno de cuatro renglones
llenos):

    letras por vuelta   precompuesta (8 fases)   de un bit
    5                   0 perdidos               0
    6                   0                        1 (una vez)
    7-10                0                        0
    11-12               0                        se pierden
    16-18               0
    20 en adelante      se pierden

La de un bit cuesta casi el doble por letra. Las tablas son 117 KB; la de un
bit, 1,1 KB y una tabla de 4,5 KB. Van las tablas, y `MSG_CHARS` queda en 5.

### Las pantallas de texto

Ítems, equipo, tienda y pelea **componen** su texto: `text_layer.s`, que
explica el diseño (registros por fila, sólo se compone lo que cambió, una
fila que dice lo que otra decía toma sus tiles, el tilemap cambia de una vez).
La letra va precompuesta como en la ventana (`scr_pre0..7`, 117 KB más): de a
un bit, una descripción tardaba nueve cuadros.

**Deuda declarada: el texto llega después del cursor.** Medido en ítems con
catorce: 4 cuadros un paso, 6 uno que corre la lista. Las pruebas de dibujo
esperan a que se asiente.

VRAM: el pozo de pares de tiles va debajo de las ventanas, en el banco de
`SLOT_VRAM`: 167 pares en ítems y equipo (las ventanas al final del banco),
191 en tienda y pelea. En reposo la lista de catorce ítems usa unos 104.
RAM: `$7E3D20-$7E5FFF` (`FAR_TEXT_LAYER`), fuera de `FAR_PAIR_LIST` y del
búfer de mensajes de la pelea.

El tope de un texto (`scr_cap`) es de celdas, en pixeles; la pelea corta sus
renglones (`ba_flow`, la página de tropa) en pixeles, y el conversor rearma
las cajas de las páginas para esa ventana.

### Menú, elección de actor y ranuras

Los nombres se componen en tiras (`tl_strip`) con la fuente precompuesta
para la paleta de texto del banco (`slot_pre0..7`). Los números siguen una
letra por celda: se reescriben en el vblank. El banco de `release` baja de
385 a 314 tiles de 448, y los nombres piden como mucho 78 de los 134 libres
(lo imprime el conversor: "menu bank").

### Para el modo 5

Se aprovecha: la hoja como fuente de verdad (con celdas de cualquier ancho
hasta 16), la tabla de avances, `refit` en pixeles, el compositor con x
acumulada, `text_layer.s` y `tl_strip`. Lo que es de baja: las ocho fases y
las tablas precompuestas por fase (en alta serían otras), y `TL_COLS`.

## Para taro

Jugar: los mensajes, el menú y sus pantallas, una tienda y una pelea. Mirar
el retraso del texto en ítems/equipo/tienda y si molesta. Las goldens están
lado a lado en `/shared/capturas/2026-10-03-ancho-variable/` (con LEEME):
cambian sólo letras, y no están bendecidas.

Ramas: herramientas, la de Calandria; ABL, `ancho-variable` de su clon.
Al mergear, reinstalar `text` no hace falta (es biblioteca): sí `screens`,
`events`, `convert`, `mapdata` y `cartridge`.

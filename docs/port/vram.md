# El reparto de la VRAM lo decide el conversor

Las 64 KB no se reparten como uno quiera: la base de los tiles de los sprites va
de a 16 KB, la de cada fondo de a 8 KB y la de cada tilemap de a 2 KB. Todo
mapa lleva la ventana de mensaje, que pide 8 KB de tiles y 2 KB de tilemap
propios, y el tilemap de la capa de encima está fijo al final. Con eso no hay
un reparto que sirva para todos los mapas: cuál toca lo decide el conversor
—junto con los valores ya armados de `OBSEL` y `BG12NBA`, y desde el 2026-09-25
la dirección del tilemap del fondo— y viaja en el `.inc`. La ROM no elige nada.

Son seis, y `vram_layout` devuelve **el primero que entre**, así que agregar
uno al final no le cambia el reparto a ningún mapa que ya lo tenía:

    ventana        sprites 448 | ventana_map | fondo 448 | mapa $5800 | encima 128 | ventana 256
    ventana+fondo  sprites 256 | fondo 480  | ventana_map | mapa $5800 | encima 128 | ventana 256
    ventana+sprite sprites 512 | fondo 384  | ventana_map | mapa $5800 | encima 128 | ventana 256
    ventana+ambos  sprites 384 | mapa $1800 | fondo 480  | ventana_map | encima 128 | ventana 256
    ventana+techo  sprites 256 | fondo 544  | ventana_map | mapa $5800 | encima 128 | ventana 256
    ventana+encima sprites 384 | mapa $1800 | fondo 384  | encima 256 | ventana 256 | ventana_map

Los detalles, con las direcciones, están en `LAYOUT_VENTANA*` de
`tools/port/snes_convert.py`, y `_controlar_repartos` comprueba que cada uno
respete las alineaciones del hardware y lo que la ROM supone.

El "+sprite" lo pide **Delcentric Factory**, el camino al auditorio: gasta 217
tiles de fondo y **475 de sprite** —26 NPCs con CharSet son 28 ranuras, o sea
448 tiles justos, y encima van los 8 glifos del cronómetro y las 19 gotas de
lluvia—. Los 512 no son una elección: son el tope del hardware, porque el campo
de nombre de OAM tiene nueve bits y con el name select de `OBSEL` en cero las
dos tablas quedan pegadas.

El "+ambos" lo pide **`Sector 34 With Car`**, el mapa 38: 476 tiles de fondo y
347 de sprite. En bytes entraba en los otros tres; lo que no dejaba era el
tilemap del fondo clavado en $5800, que corta el banco de BG1 en 448 tiles. Es
el único reparto que lo mueve: lo baja a los 2 KB que quedan entre los sprites y
el fondo, y la ROM lo lee de `FAR_VRAM_MAPA` al armar filas y columnas.

## Dónde está el techo

Enumerando todas las bases que el hardware permite —con la capa de encima y la
ventana pegadas, y el tilemap de encima en $7800—, el máximo de tiles de fondo
para cada tope de sprites es:

    sprites   256   320   384   448   512
    fondo     544   512   480   448   416

Y da lo mismo con el tilemap del fondo libre o clavado en $5800: moverlo no
corre el techo. Lo que sí cambia es qué repartos respetan la pantalla de
ranuras, que pisa $2000..$4000 y cuenta con que `load_map` lo reponga: con el
tilemap en $5800, 347 sprites dejan 448 de fondo; moviéndolo, 480. Para eso se
mudó.

Dos de los repartos están por debajo del techo —"+fondo" podría dar 544 y
"+sprite" 416—. Subirlos cambiaría el reparto de los mapas que ya los usan.

El de "+fondo" lo pidió **el mundo**, el mapa 66: 527 tiles de fondo y 222 de
sprite. En vez de subir "+fondo" se agregó "+techo" al final, que es "+fondo"
con los 544: los mapas que ya estaban siguen donde estaban. Y 544 tiles de 8bpp
son 34 KB, más que el buffer de carga de LZ2, así que ese fondo viaja en dos
flujos: ver `lz2_fondo` en `tools/runtime/descomprimir.s`.

El sexto, "+encima", lo pidió **Sorbe Village**, el mapa 69: 157 tiles en la
capa de encima, y los otros cinco le dan 128. No sube ningún techo de fondo ni
de sprite: **muda la base de BG2** de $6000 a $5000, y con eso la capa de
encima tiene 256 tiles y la ventana arranca en el índice 256 de BG2 y no en el
128. Como las celdas de la ventana llevan ese índice horneado, el cartucho
lleva dos planos de la ventana —640 bytes cada uno— y `estampar_ventana` elige
el suyo por la distancia entre la ventana y la base de BG2. `vram_layout` mira
desde entonces también la capa de encima; los mapas que ya convertían entraban
todos en 128, así que ninguno cambió de reparto.

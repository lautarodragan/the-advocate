# El reparto de la VRAM lo decide el conversor

Las 64 KB no se reparten como uno quiera: la base de los tiles de los sprites va
de a 16 KB, la de cada fondo de a 8 KB y la de cada tilemap de a 2 KB. Todo
mapa lleva la ventana de mensaje, que pide 8 KB de tiles y 2 KB de tilemap
propios —en el tilemap van dos planos de diez filas, la ventana y la ventana
sin marco, y cuál se ve y en qué líneas lo dice el HDMA: ver
`message_place.s`—, y el tilemap de la capa de encima está fijo al final. Con eso no hay
un reparto que sirva para todos los mapas: cuál toca lo decide el conversor
—junto con los valores ya armados de `OBSEL` y `BG12NBA`, y desde el 2026-09-25
la dirección del tilemap del fondo— y viaja en el `.inc`. La ROM no elige nada.

Son seis, y `vram_layout` devuelve **el primero que entre**, así que agregar
uno al final no le cambia el reparto a ningún mapa que ya lo tenía. Hay dos
más, los del panorama —ver abajo—, que `vram_layout` no da nunca:

    ventana        sprites 448 | ventana_map | fondo 448 | mapa $5800 | encima 128 | ventana 256
    ventana+fondo  sprites 256 | fondo 480  | ventana_map | mapa $5800 | encima 128 | ventana 256
    ventana+sprite sprites 512 | fondo 384  | ventana_map | mapa $5800 | encima 128 | ventana 256
    ventana+ambos  sprites 384 | mapa $1800 | fondo 480  | ventana_map | encima 128 | ventana 256
    ventana+techo  sprites 256 | fondo 544  | ventana_map | mapa $5800 | encima 128 | ventana 256
    ventana+encima sprites 384 | mapa $1800 | fondo 384  | encima 256 | ventana 256 | ventana_map

Los detalles, con las direcciones, están en `LAYOUT_WINDOW*` del `vram.rs` de
`tools/rm2k-snes/mapdata/`, y `check_splits` comprueba que cada uno respete
las alineaciones del hardware y lo que la ROM supone. Los razonamientos largos
de cada reparto quedaron en la historia de `tools/port/vram.py`, donde vivían
hasta el 2026-10-01.

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
el fondo, y la ROM lo lee de `FAR_VRAM_MAP` al armar filas y columnas.

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
flujos: ver `lz2_backdrop` en `tools/runtime/decompress.s`.

El sexto, "+encima", lo pidió **Sorbe Village**, el mapa 69: 157 tiles en la
capa de encima, y los otros cinco le dan 128. No sube ningún techo de fondo ni
de sprite: **muda la base de BG2** de $6000 a $5000, y con eso la capa de
encima tiene 256 tiles y la ventana arranca en el índice 256 de BG2 y no en el
128. Como las celdas de la ventana llevan ese índice horneado, el cartucho
lleva dos planos de la ventana —640 bytes cada uno— y `stamp_window` elige
el suyo por la distancia entre la ventana y la base de BG2. `vram_layout` mira
desde entonces también la capa de encima; los mapas que ya convertían entraban
todos en 128, así que ninguno cambió de reparto.

## Cuando ningún reparto alcanza: los quietos se turnan

El techo de arriba es del hardware, y **Distant Paradise**, el mapa 108, lo
pasa: 462 tiles de fondo —sólo "+fondo", "+ambos" y "+techo" le sirven— y
42 ranuras de sprite, 696 tiles, contra las 24 que deja el mejor. Casi todo
eso son poses quietas —quince vecinos mirando para tres o cuatro lados—, y
en pantalla nunca hay más de la mitad.

Así que en un mapa que no entra en ningún reparto, y **sólo ahí**, los quietos
que nunca están juntos en pantalla comparten una ranura aunque muestren poses
distintas, y la ROM sube la pose del que entra en pantalla. Quién se turna con
quién lo decide `wally` —`plan_sharing` en su `map.rs`, con el coloreo de
`share` en su módulo `sprites`—, la tabla la emite `share_table` en
`rm2k-snes-mapdata`, y lo que hace la ROM está en
`tools/runtime/shared_poses.s`. El 108 queda en 22 ranuras, 376 tiles, y entra
en "+ambos". Los demás mapas convierten como siempre: `wally` prueba primero
sin turnos y sólo si eso no entra vuelve a convertir con ellos.

## Cuando ni turnándose alcanza: una caché de ranuras

**ParadiseFarmland**, el 127 de ABL, no entra ni así: la celebración pone
veintinueve personas en una pantalla, dieciséis de las cuales la escena hace
saltar y girar, y el mapa pide 41 ranuras contra las 32 que da el mejor
reparto. Turnarse no le sirve, porque los quietos están todos juntos.

Así que en un mapa que no entra ni con turnos, y **sólo ahí**, nadie tiene
ranura: el que entra en pantalla pide una, la ROM le sube la pose, y la
ranura que lleva dos cuadros sin dibujarse la puede tomar otro. Los quietos
que muestran la misma pose comparten la suya, como siempre; el que camina
tiene una propia mientras se lo ve. Lo decide `wally` —`Mode::Cache` en su
`map.rs`, con la cuenta en `sprites::cache`—, que le da a la caché todos los
bloques que entran en el mejor reparto para su fondo; la tabla la emite
`cache_table` en `rm2k-snes-mapdata`, y lo que hace la ROM está en
`tools/runtime/cache_slots.s`. El 127 queda con el héroe, la ranura del giro
y 30 en la caché: 32 bloques, 512 tiles, en "+sprite".

Lo que se ve a la vez en el 127 no lo puede contar el conversor: la
celebración y el baile que sigue nunca están juntos, pero por dónde arrancan
los eventos suman 33 en una pantalla, y `wally` lo avisa. La consola sí lo
sabe, porque una fila que no se dibuja no pide nada: en la celebración son
26. La medición de todo el juego, y qué ayudas se probaron, en
`workflow/tasks/*/la-cache-de-ranuras.md`.

## Una imagen grande no usa el reparto

Una imagen de `ShowPicture` que tapa la pantalla va en BG1, en modo 1, con
el mapa oculto —`decisiones/las-imagenes-grandes-en-modo-1.md`—, y **ocupa
el mismo lugar en los seis repartos**: sus tiles de 4bpp desde la palabra 0
hasta $3FFF —los 1024 que nombra una entrada de tilemap—, encima de los
sprites y de los tiles del mapa, y su tilemap en $4000. El tilemap de la
ventana cae en ese rango en "ventana" ($1C00), así que mientras dura se muda
a $4800, que en ninguno es de algo que se use mientras tanto —en algunos son
tiles del mapa, que se recargan—; los tiles de BG2 y los de la ventana están
de $5000 para arriba en todos. Lo que pisa lo repone, al borrarla, la
misma carga que la vuelta de la pelea: ver `tools/runtime/big_picture.s`.

## Una imagen grande con zoom usa la otra mitad

El modo 7 es dueño de las palabras `$0000` a `$3FFF` —su mapa de 128x128 en
los bytes bajos y sus 256 tiles en los altos— y no se puede correr. Así que
una imagen grande que un `MovePicture` agranda o achica, y que por eso lleva
una textura de modo 7, se muestra quieta **en la mitad de arriba**: sus
tiles desde `$4000` —hasta 960— y su tilemap, una pantalla de 32x32, en
`$7C00`. Mientras está quieta la textura sube a la mitad de abajo de a un
pedazo por vblank, encima de los sprites y de los tiles del mapa, que no se
ven. Eso pisa la ventana y los tiles de BG2, que estaban arriba en los seis
repartos: con el modo 7 en pantalla la mitad de arriba queda libre y la
ventana vuelve ahí, también de a pedazos. Borrarla repone todo con la misma
carga que la vuelta de la pelea, que pisa las mismas palabras. Ver
`tools/runtime/big_picture_zoom.s`.

## Un mapa que muestra su panorama usa uno suyo

Desde el 2026-10-05, los mapas a los que Wally les da al panorama una capa
propia —ver `Way` en `background/panorama.rs`—. Hay cuatro, y un mapa
toma el primero de su modo donde entran su fondo, sus sprites y su
panorama: Wally convierte el panorama con los tiles que deja el primero
que le alcanza al fondo.

    panorama               sprites 384 | mapa $1800 | fondo 256 | panorama 256 | ventana 256 | ventana_map | panorama 320 | su tilemap $7800
    panorama_m1            sprites 256 | mapa $1000 | ventana_map | fondo 512 a 4 bits | panorama 768 a 2 bits | su tilemap $5800 | encima 128 | ventana 256
    panorama_fondo         sprites 384 | mapa $1800 | fondo 384 | panorama 256 | ventana 256 | ventana_map | panorama 64 | su tilemap $7800
    panorama_fondo_sprite  sprites 256 | mapa $1000 | ventana_map | fondo 384 | panorama 256 | ventana 256 | panorama 128 | su tilemap $7800
    panorama_fondo_techo   sprites 256 | mapa $1000 | ventana_map | fondo 448 | ventana 256 | panorama 256 | su tilemap $7800

**El último pasa la base de BG2**, que está en `$5000`, adentro de los
tiles del fondo: los primeros 128 de BG2 son del fondo, y nadie en BG2 los
nombra —la ventana está en el 128, como en "ventana", y el panorama
después—. Por eso `load_above` no sube nada a la base de BG2 en un mapa
con el panorama en modo 3.

**En modo 3 el panorama es BG2**, así que tiene que caber, con la ventana,
en lo que los diez bits de BG2 alcanzan desde su base: va antes y después
de ella, y la ventana se queda en el índice 256, de `$5000` para arriba,
donde una imagen grande no la pisa. Su tilemap es el de la capa de encima,
que el mapa no usa. **En modo 1 es BG3**, con base y tilemap propios, y
el fondo va a 4 bits: su `tiles` se cuenta en unidades de 64 bytes, como
el de 8, así que sus 256 son 512 tiles.

En los dos, los tiles del panorama que caen después de los de BG1 vuelven
con `load_above` —`pano_load`— igual que BG1 con `load_map`, así que las
pantallas pueden pisarlos. Los detalles, en `LAYOUT_PANORAMA_MODE*` del
`vram.rs`.

## La pelea no usa el reparto

La pelea pisa la VRAM entera y `back_from_battle` la repone:

    palabra 0 .. $1FFF    el texto, en BG2: 255 pares de tiles de 4bpp
    $2000 .. $37FF        las ventanas, tiles de 8bpp de BG1 (192 caben)
    $3800 .. $3BFF        el tilemap de BG1: la escena y las ventanas
    $3C00 ..              el tilemap del texto, `SLOT_MAP`
    $4000 .. $7FFF        la escena, 512 tiles de 8bpp

**La escena y las ventanas son la misma capa**, BG1 en modo 3: la escena
ocupa las primeras dieciséis filas del tilemap, y las ventanas de abajo
—y la de la descripción, que le tapa las cuatro de arriba mientras hay una
lista abierta— van en las filas que quedan, con tiles numerados desde la
base de la escena, que dan la vuelta hasta `$2000` (el 768 en adelante).
Sus colores son la última paleta de los battlers, la entrada 240 en
adelante, y por eso una tropa muestra siete battlers distintos a lo sumo.
Ver `battle.rs` en `rm2k-snes-screens` y `ba_win_tick` en
`tools/runtime/battle_scene.s`.

**Se descartó el modo 1 en la franja de abajo, sin escribirlo.** Pide una paleta
de BG1 entre la 0 y la 7, y en la pelea están todas tomadas: la 0 y la 1
son las del texto y la 2 a la 7 son los 96 colores del fondo, que siguen
en la pantalla mientras se dibuja la franja. En 8bpp un pixel es su
entrada de CGRAM, y la última paleta de los battlers sobra. Con el modo 3
no hace falta cambiar ni el modo ni las bases por HDMA: lo único que va
por HDMA, el canal 5, es el desplazamiento horizontal de BG1 por franja,
para que el temblor de la pantalla mueva la escena y no las ventanas.

**El texto tiene 255 pares**, de la palabra 0 a `$1FFF`. Desde la mañana
del 2026-10-04 hasta la tarde fueron 447, hasta el tilemap de la escena,
porque la lista de habilidades sobre la escena, con el grupo y las órdenes
abajo, agotaba los 191 que dejaba `SLOT_VRAM` y después los 255 con
`letter_spacing` 2. Con las ventanas en la franja la pelea escribe mucho
menos —la descripción y cinco renglones— y el conversor avisa contra los
255. La palabra 0 es el tile transparente de la escena y el par en blanco
del texto a la vez: ver `battle_bank_upload` en
`tools/runtime/screen_bank.s`.

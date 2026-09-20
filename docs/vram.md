# El reparto de la VRAM lo decide el conversor

Las 64 KB no se reparten como uno quiera: la base de los tiles de los sprites va
de a 16 KB, la de cada fondo de a 8 KB y la de cada tilemap de a 2 KB. Con los
dos tilemaps clavados al final quedan 56 KB para los tres bancos de tiles, y las
granularidades dejan exactamente dos cortes posibles:

    ancho    fondo 512 tiles (32 KB) | sprites 512 (16 KB) | encima 256 (8 KB)
    fondo    fondo 640 tiles (40 KB) | encima 256 (8 KB)   | sprites 256 (8 KB)

Ninguno sirve para todos los mapas: el que más tiles de fondo gasta necesita
620, y Lashe City necesita 320 de sprite. Cuál toca lo decide el conversor
—junto con los valores ya armados de `OBSEL` y `BG12NBA`— y viaja en el `.inc`.
La ROM no elige nada.

Con la ventana de mensaje puesta hay que sacarle 8 KB de tiles y 2 KB de tilemap
a alguien, y eso da otros tres cortes. Son seis en total, y `vram_layout`
devuelve **el primero que entre**, así que agregar uno al final no le cambia el
reparto a ningún mapa que ya lo tenía:

    ancho          fondo 512 | sprites 384 | encima 256
    fondo          fondo 640 | encima 256  | sprites 256
    ancho+sprite   sprites 512 | fondo 448 | encima 256
    ventana        sprites 448 | ventana_map | fondo 448 | encima 128 | ventana 256
    ventana+fondo  sprites 256 | fondo 480  | ventana_map | encima 128 | ventana 256
    ventana+sprite sprites 512 | fondo 384  | ventana_map | encima 128 | ventana 256

Los dos "+sprite" los pide **Delcentric Factory**, el camino al auditorio:
gasta 217 tiles de fondo y **475 de sprite**
—26 NPCs con CharSet son 28 ranuras, o sea 448 tiles justos, y encima van los 8
glifos del cronómetro y las 19 gotas de lluvia—. Los 512 no son una elección:
son el tope del hardware, porque el campo de nombre de OAM tiene nueve bits y
con el name select de `OBSEL` en cero las dos tablas quedan pegadas.

**Lo que no entra en ninguno de los seis** es un mapa que gaste mucho de las dos
cosas a la vez. El caso medido es `Sector 34 With Car`, el mapa 38: 476 tiles de
fondo y 347 de sprite, que son 41 KB de tiles más los 10 de la ventana, los 8 de
la capa de encima y los 8 de los dos tilemaps. Son 67 de 64.

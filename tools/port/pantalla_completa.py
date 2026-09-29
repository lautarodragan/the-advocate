"""Una imagen que ocupa la pantalla entera, comprimida en un flujo LZ2.

Es el camino de las pantallas de Game Over y de título: la imagen se convierte
con `paleta.convertir` —escalada a 256x224, a 8 bits por pixel en BG1, que en
modo 3 direcciona CGRAM entera— y lo que va al cartucho es **un solo flujo**
con las tres cosas que la ROM sube, una detrás de otra:

    los tiles, a 64 bytes cada uno
    el tilemap de 32x32, que son 2048 bytes
    los colores, a dos bytes cada uno

La ROM lo descomprime entero en la WRAM y lo sube con tres DMA: ver
`pantalla_subir` en tools/runtime/game_over.s, que lee de `pantallas_tabla` dónde
está cada flujo y cuánto mide cada parte.

**Por qué comprimido y no un liviano en la ROM con el de calidad en el
`.msu`**, como los fondos de batalla: medido el 2026-09-28 con la imagen de
Game Over del RTP, a calidad completa son 36.224 B de tiles crudos y 11.530
con LZ2; una liviana a 128x112 y 16 colores, agrandada al doble como el
respaldo de los fondos, son 2.901 comprimida. El ahorro de la liviana son
unos 9 KB del cartucho, y costaría un segundo camino en la ROM —agrandar al
doble, leer del `.msu`, la espera de la búsqueda— que ningún core de la tanda
ejercita entero. Comprimida, la imagen de calidad va en todas las consolas.
La del título se decidió igual, el 2026-09-28: los números están en
`workflow/tasks/*/la-pantalla-de-game-over.md` y en
`workflow/tasks/*/la-pantalla-de-titulo-comprimida.md`.
"""

from port import comprimir
from port.formato_snes import cgram_word, entry, pack_tile
from port.paleta import convertir

# El tilemap que sube la ROM: 32x32 entradas de dos bytes, aunque la pantalla
# muestre 28 filas. Es el tamaño que el PPU lee, y el mismo que el título.
TILEMAP_BYTES = 32 * 32 * 2


def comprimida(imagen, primer_color=0, tope=256, debajo=()):
    """La imagen como un dict: `flujo` es el LZ2 con las tres partes, y
    `tiles`, `colores` y `primer_color` son lo que la ROM necesita para
    partirlo.

    `primer_color` y `tope` son los de `paleta.convertir`: por omisión la
    imagen se queda con CGRAM entera, desde el 0. El índice 0 es además el
    color del fondo del PPU, y `paleta.reducir` le deja ahí el negro.

    `debajo` son colores que no son de la imagen y van en CGRAM justo antes
    de los suyos —en el título, los del menú—: viajan en el mismo flujo y se
    suben con el mismo DMA, así que el `primer_color` de la fila baja lo que
    ellos ocupen. Es para no gastar otro DMA en el banco 0.
    """
    if len(debajo) > primer_color:
        raise ValueError("%d colores debajo de la imagen y la imagen empieza "
                         "en el %d" % (len(debajo), primer_color))
    tiles, paleta, tilemap = convertir(imagen, primer_color, tope)
    datos = bytearray()
    for celda in tiles:
        datos += pack_tile(celda, planes=8)
    plano = bytearray()
    for indice in range(32 * 32):
        numero = tilemap[indice] if indice < len(tilemap) else 0
        plano += entry(numero, False, False).to_bytes(2, "little")
    colores = list(debajo) + list(paleta)
    crudo = (bytes(datos) + bytes(plano)
             + b"".join(cgram_word(c).to_bytes(2, "little") for c in colores))
    return {"flujo": comprimir.comprimir(crudo), "crudo": len(crudo),
            "tiles": len(tiles), "colores": len(colores),
            "primer_color": primer_color - len(debajo)}

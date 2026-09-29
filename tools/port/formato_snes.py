"""Los formatos del PPU de la SNES: un tile, un color de CGRAM y una celda
del tilemap, como bytes o palabras listas para la consola.
"""


def pack_tile(indices, planes=8):
    """Formato del PPU: planos de bits, no dos pixeles por byte.

    Cada plano guarda un bit de cada pixel, una fila por byte y el pixel de más
    a la izquierda en el bit más alto. Los planos van de a pares y de a 16
    bytes: 0 y 1 primero, después 2 y 3, y así. Por eso un tile de 4 bits es
    exactamente la primera mitad de uno de 8, y el mismo código sirve para los
    dos con sólo cambiar cuántos planos recorre.
    """
    data = bytearray(planes * 8)
    for y, row in enumerate(indices):
        for x, value in enumerate(row):
            bit = 1 << (7 - x)
            for plane in range(planes):
                if (value >> plane) & 1:
                    data[(plane // 2) * 16 + y * 2 + (plane % 2)] |= bit
    return bytes(data)


def cgram_word(color):
    """Palabra de CGRAM: 0BBB BBGG GGGR RRRR."""
    red, green, blue = color
    return (blue << 10) | (green << 5) | red


def entry(tile, horizontal, vertical, priority=0):
    """Una celda del tilemap: vhop ppcc cccc cccc.

    Los tres bits de paleta no se ponen acá: en 8 bits por pixel el índice ya
    alcanza CGRAM entero y el PPU los ignora. Las celdas de la pantalla de
    ranuras, que es BG2 a 4bpp, ya vienen de `menus.py` con la paleta puesta
    en `tile`, y esto la deja pasar.
    """
    return (tile | (priority << 13) | (horizontal << 14) | (vertical << 15))

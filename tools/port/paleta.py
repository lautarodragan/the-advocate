"""An image brought down to N 15-bit colors, or to a full screen at 8 bpp.

`reducir` and `convertir` were born for the title screen, and today the
pictures, the animations, the battle backdrops and the full screens use them
too.
"""

import collections

from port.constantes import ALTO, ANCHO, CELL, COLORES, COLS, FILAS, MENU_CGRAM

NEGRO = (0, 0, 0)


def _distancia(a, b):
    """How far apart two 15-bit colors are, squared.

    Euclidean and with no per-channel weights: the alternative —weighting by
    luma, which is what `merge_least_visible` does for the palettes of
    sixteen— would change nothing visible here and would need an explanation
    of why the weights are those. The colors that get merged are the ones
    that barely appear, and the neighbor they get is one step away.
    """
    return sum((x - y) ** 2 for x, y in zip(a, b))


def reducir(pixeles, tope=COLORES):
    """The image's colors brought down to `tope`, and the map of where each
    one went.

    It keeps the most used ones and sends each of the leftovers to its
    nearest neighbor among those that stayed. **It is not median cut**: it
    does not average colors, so it cannot invent one that was not in the
    image and there is no need to quantize to 15 bits again afterwards. And
    it does not depend on which version of PIL is installed, which is what
    makes the ROM come out the same byte for byte on any machine.

    Ties are broken by the color, not by the order they appeared in: two
    colors with the same count must always fall on the same side, or the ROM
    changes without anyone having touched anything.
    """
    cuenta = collections.Counter(pixeles)
    # Black keeps index 0 even if it was not among the most used: it is the
    # backdrop color, and this way what the PPU paints where there is
    # nothing matches what the image has there.
    orden = sorted(cuenta, key=lambda c: (-cuenta[c], c))
    if NEGRO in orden:
        orden.remove(NEGRO)
    paleta = [NEGRO] + orden[:tope - 1]
    quedan = set(paleta)
    mapa = {c: c for c in quedan}
    for color in orden[tope - 1:]:
        mapa[color] = min(paleta, key=lambda p: (_distancia(color, p), p))
    return paleta, mapa


def _quince(imagen):
    """The image scaled to the screen, with its colors at 15 bits.

    The scaling is LANCZOS, which is the one that smears the edges of the
    title's text the least; the original has a lot of gradient and little
    fine detail, so the difference against bicubic shows in the credits and
    nowhere else.
    """
    from PIL import Image
    chica = imagen.convert("RGB").resize((ANCHO, ALTO), Image.LANCZOS)
    return [(r >> 3, g >> 3, b >> 3) for r, g, b in chica.get_flattened_data()]


def convertir(imagen, primer_color=MENU_CGRAM, tope=COLORES):
    """A full-screen image as (tiles, paleta, tilemap).

    `tiles` are the unique tiles at 8 bits per pixel; `paleta` their colors,
    which go in CGRAM **starting at `primer_color`** —on the title,
    `MENU_CGRAM`, because the ones below belong to the menu—; `tilemap` the
    32x28 entries, in the 32x32 tilemap the PPU expects. `tope` is how many
    colors are left.

    The indices the tiles carry are already shifted, so whoever emits them
    does not have to remember to add anything: the shift is written once and
    here.
    """
    pixeles = _quince(imagen)
    paleta, mapa = reducir(pixeles, tope)
    indice = {color: i + primer_color for i, color in enumerate(paleta)}
    # The image as palette indices, row by row.
    filas = []
    for y in range(ALTO):
        filas.append([indice[mapa[pixeles[y * ANCHO + x]]] for x in range(ANCHO)])

    tiles, donde, tilemap = [], {}, []
    for ty in range(FILAS):
        for tx in range(COLS):
            celda = tuple(tuple(filas[ty * CELL + y][tx * CELL:(tx + 1) * CELL])
                          for y in range(CELL))
            if celda not in donde:
                donde[celda] = len(tiles)
                tiles.append(celda)
            tilemap.append(donde[celda])
    return tiles, paleta, tilemap

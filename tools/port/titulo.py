"""The title screen: from `Title/ABL20Title.png` to tiles, palette and tilemap.

It lives apart from `snes_convert.py` because it is not a map: it has no
chipset, no events, no upper layer. It is a lone image, and the only job is
to fit it into mode 3 without losing anything noticeable.

**It goes on BG1, which in mode 3 has eight bits per pixel**, so it
addresses all of CGRAM and does not need to split anything into palettes of
sixteen. It is the only place in the port where that is worth it: a map
spends its 256 colors across several palettes because the sprites need
theirs, and here there are no sprites.

**It is scaled and not cropped**, and that took looking at the image: the
original is 320x240 and the screen 256x224, so the centered crop eats the
"2.1" of the title on the right and the `Additional Graphics` credits at the
bottom. What is paid in exchange is that the image ends up 20% narrower —the
original's aspect ratio is not the console's— and that the colors go up from
133 to 369, because interpolating invents shades between the ones there
were.

From there comes the only step that is not mechanical: from 369 colors to
256.
"""

import collections

from port.constants import HEIGHT, WIDTH, CELL, COLS, MENU_CGRAM
from port.paleta import NEGRO, convertir


def informe(imagen):
    """The numbers that justify the layout, for the recipe to print."""
    tiles, paleta, tilemap = convertir(imagen)
    return {
        "tiles": len(tiles),
        "colores": len(paleta),
        "bytes_tiles": len(tiles) * 64,
        "bytes_tilemap": 32 * 32 * 2,
    }


def render(imagen, sys_img=None, textos=None, elegida=0, font_id=None):
    """The title screen as the console has to show it.

    It is `convertir` undone: the tiles put back in their place according to
    the tilemap, with the palette colors taken from 15 bits to 24. Coming
    from the same data the ROM uploads does not make it an empty
    comparison: what is checked is the other stretch of the path —the DMA to
    VRAM, the PPU's two bases, the one-line scroll that already cost a red
    on the maps— and there the ROM can get it wrong without the reference
    noticing.

    What this comparison **cannot** see is the image being converted wrong:
    if `convertir` picked the 256 colors badly, both sides would be wrong
    the same way and the result would still be zero. That is checked with
    the eyes, once, and it does not change again.
    """
    from PIL import Image
    tiles, paleta, tilemap = convertir(imagen)
    fuera = Image.new("RGB", (WIDTH, HEIGHT))
    px = fuera.load()
    for i, indice in enumerate(tilemap):
        tx, ty = (i % COLS) * CELL, (i // COLS) * CELL
        celda = tiles[indice]
        for y in range(CELL):
            for x in range(CELL):
                color = paleta[celda[y][x] - MENU_CGRAM]
                px[tx + x, ty + y] = tuple(v << 3 for v in color)
    if sys_img is None:
        return fuera
    # The menu goes on top, and **by the same path as the ROM**: the 4bpp
    # tiles that `menu` emits, not the text layer they came from. Drawing the
    # text here with the font and there with the tiles would leave out
    # exactly the step that can go wrong —quantizing the skin's gradient to
    # fifteen colors— and the comparison would not see it.
    tiles_menu, paleta_menu, mapas = menu(sys_img, textos, font_id)
    for i, indice in enumerate(mapas[elegida]):
        tx, ty = (i % COLS) * CELL, (i // COLS) * CELL
        if ty >= HEIGHT:
            break
        celda = tiles_menu[indice]
        for y in range(CELL):
            for x in range(CELL):
                valor = celda[y][x]
                if valor:       # index 0 is not drawn: the image shows through
                    px[tx + x, ty + y] = tuple(
                        v << 3 for v in paleta_menu[valor])
    return fuera


# --- the menu ----------------------------------------------------------------
#
# The two title options go on **BG2, which in mode 3 has four bits per
# pixel**, and not on BG1 with the image. Two reasons, and both are measured:
# on BG1 the text would have to be mixed with the image when converting, that
# is a new tile for every cell where the text covers the background, and the
# text could no longer move; and at 4bpp each tile costs half.
#
# The cursor **is not drawn separately**: one tilemap is emitted per selected
# option, and moving the cursor is uploading the other one. That is 2048 B per
# tilemap and a DMA that only runs when the player presses up or down. The
# alternative —writing by hand the two tilemap words that change— saves 2 KB
# of cartridge and requires knowing which cell each arrow falls on, which is
# exactly the kind of number that gets written wrong on one side and not the
# other.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
MENU_Y = 152                    # where the first option starts, in pixels
MENU_ALTO = 24                  # and how far apart the next one is
MENU_X = 72
CURSOR = "> "
SIN_CURSOR = "  "


def opciones(db):
    """The menu texts, as the game says them and not as we would.

    In ABL they are 'Begin the Story' and 'Resume the Story'; the stock
    engine would say 'New Game' and 'Load Game'. They come from the LDB
    terms.
    """
    return [db.term_new_game, db.term_load_game]


def _capa_de_texto(sys_img, textos, elegida, font_id=None):
    """A transparent screen with the options drawn, and the cursor in place.

    It is drawn with `ventana.dibujar_linea`, the same one that composes the
    messages: same font, same color gradient, same shadow shifted by one.
    That the title menu and a game message look the same is not an aesthetic
    detail: it is what means there is no second font to maintain.
    """
    from PIL import Image
    from port import ventana as ventana_mod
    capa = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for n, texto in enumerate(textos):
        marca = CURSOR if n == elegida else SIN_CURSOR
        ventana_mod.dibujar_linea(capa, sys_img, MENU_X, MENU_Y + n * MENU_ALTO,
                                  marca + texto, font_id=font_id)
    return capa


def menu(sys_img, textos, font_id=None):
    """The menu's 4bpp tiles, its palette, and one tilemap per option.

    The tiles are gathered from **all** the variants before deduplicating:
    there is a single bank and the tilemaps index it, so building each
    variant separately would give indices that do not match.

    Palette index 0 is transparent and goes to the empty cell, which is
    almost the whole screen: that is why the bank ends up small even though
    the tilemap has 1024 entries.
    """
    capas = [_capa_de_texto(sys_img, textos, n, font_id)
             for n in range(len(textos))]

    # The colors of all the layers together, at 15 bits. The transparent one
    # does not count: it is index 0 and is not drawn.
    vistos = collections.Counter()
    for capa in capas:
        for r, g, b, a in capa.get_flattened_data():
            if a:
                vistos[(r >> 3, g >> 3, b >> 3)] += 1
    if len(vistos) > 15:
        raise SystemExit(
            "the title menu uses %d colors and 4bpp fits 15. The skin's "
            "gradient is the suspect: look at `color_de_texto` in ventana.py"
            % len(vistos))
    paleta = [NEGRO] + sorted(vistos, key=lambda c: (-vistos[c], c))
    indice = {color: i for i, color in enumerate(paleta)}

    tiles, donde, tilemaps = [], {}, []
    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    donde[vacio] = 0
    tiles.append(vacio)
    for capa in capas:
        px = capa.load()
        mapa = []
        for ty in range(32):
            for tx in range(COLS):
                celda = []
                for y in range(CELL):
                    fila = []
                    for x in range(CELL):
                        sx, sy = tx * CELL + x, ty * CELL + y
                        if sy >= HEIGHT:
                            fila.append(0)
                            continue
                        r, g, b, a = px[sx, sy]
                        fila.append(indice[(r >> 3, g >> 3, b >> 3)] if a else 0)
                    celda.append(tuple(fila))
                celda = tuple(celda)
                if celda not in donde:
                    donde[celda] = len(tiles)
                    tiles.append(celda)
                mapa.append(donde[celda])
        tilemaps.append(mapa)
    return tiles, paleta, tilemaps

"""The End Game screen of the pause menu: RM2k's `Scene_End`.

It is two windows over black: on top the question —the LDB term
`exit_game_message`, "End game?" in ABL— and below "Yes" and "No" —`yes` and
`no`—, with the System's bar over the one being chosen. The rules come from
easyrpg-player's `Scene_End::CreateCommandWindow` and `CreateHelpWindow`,
and the measurements were compared against the 2015 RPG_RT running under
Wine: with these same computations at 320x240, the windows, the text and the
bar land on the same pixels as in the capture of the original. What differs
are things of `ventana.py` and of the font, which apply to every window of
the port: the light band of the stretched background lands a few rows off,
and a couple of glyphs —the "g"— are not identical.

**It is drawn whole, as an image**, and not with the one-letter-per-cell
font of the item screen: it is a fixed screen of three words, so the letters
can go at the font's 6 pixels, as in RM2k, and the windows can measure what
they measure there. It goes on BG1 at 8bpp, which in mode 3 addresses all of
CGRAM.

**The cursor does not move tiles: it changes colors.** The two images —with
the bar on "Yes" and with the bar on "No"— share the tiles and the tilemap,
and what tells them apart are the pixels of the two bars. Each pair (color
with the cursor on Yes, color with the cursor on No) that appears in the
image is a CGRAM entry of its own: the pixels that do not change have the
same color in both, and those of the bars, a different one. Moving the
cursor is writing those few entries with the other image's palette, during
vblank. That way there is no second tilemap and no extra tiles.
"""

from port import constantes
from port import ventana as ventana_mod

ANCHO, ALTO = constantes.ANCHO, constantes.ALTO
CELL = constantes.CELL
NEGRO = (0, 0, 0)

# `menu_item_height` of Window_Selectable and the borders of Window.
LINEA = 16
BORDE = 8
# The two windows in RM2k, which is 320x240: the question at y=72 and the
# commands 48 further down, centered in x. Here the screen is 256x224, so
# they are centered on 256 and moved up 8, half of the 16 missing rows.
Y_PREGUNTA = 72
Y_ORDENES = 72 + 48
SUBIR = (240 - ALTO) // 2

# Which command the cursor marks on entering. The 2015 RPG_RT enters on
# "Yes", measured under Wine; easyrpg-player enters on "No" (`SetIndex(1)`).
# The original wins.
SI, NO = 0, 1
ENTRA = SI


def textos(db):
    """The question and the two commands, from the LDB, with the same
    fallback texts as easyrpg if the term is empty."""
    t = db.terms
    def uno(nombre, repuesto):
        # Measured against A Blurred Line: an assumption of the engine, not a
        # fact of the game. See
        # `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
        valor = t.get(nombre, b"").decode("cp1252")
        return valor or repuesto
    return (uno("exit_game_message", "Do you really want to quit?"),
            uno("yes", "Yes"), uno("no", "No"))


def _ancho_de(texto):
    from port import fuente
    return len(texto) * fuente.ANCHO


def dibujar(sys_img, db, elegida, font_id=None, ancho=ANCHO, alto=ALTO,
            subir=SUBIR):
    """The screen in RGB, with the cursor on `elegida`. `ancho`, `alto` and
    `subir` at 320, 240 and 0 give RM2k's, which is the one compared against
    the capture of the original."""
    from PIL import Image
    pregunta, si, no = textos(db)
    if _ancho_de(pregunta) + 2 * BORDE > ancho:
        # RM2k would let it run off the screen; here it would be cut
        # without warning.
        raise SystemExit("the End Game question, %r, does not fit in %d "
                         "pixels" % (pregunta, ancho))
    fuera = Image.new("RGBA", (ancho, alto), NEGRO + (255,))

    def pegar(una, x, y):
        fuera.paste(una, (x, y), una)

    # The question: `Window_Help`, as wide as the text plus the borders, with
    # the text at (0, 2) of its contents.
    w = _ancho_de(pregunta) + 2 * BORDE
    x, y = ancho // 2 - w // 2, Y_PREGUNTA - subir
    pegar(ventana_mod.ventana(sys_img, w, 2 * LINEA), x, y)
    ventana_mod.dibujar_linea(fuera, sys_img, x + BORDE, y + BORDE + 2,
                              pregunta, font_id=font_id)

    # The commands: `Window_Command`, as wide as the longest plus the borders
    # and sixteen per command plus the borders tall. The bar is
    # `UpdateCursorRect`'s: four more on each side of the contents.
    ordenes = (si, no)
    w = max(_ancho_de(o) for o in ordenes) + 2 * BORDE
    x, y = ancho // 2 - w // 2, Y_ORDENES - subir
    pegar(ventana_mod.ventana(sys_img, w, len(ordenes) * LINEA + 2 * BORDE),
          x, y)
    pegar(ventana_mod.cursor(sys_img, w - 2 * BORDE + 8, LINEA),
          x + BORDE - 4, y + BORDE + elegida * LINEA)
    for n, orden in enumerate(ordenes):
        ventana_mod.dibujar_linea(fuera, sys_img, x + BORDE,
                                  y + BORDE + n * LINEA + LINEA // 8, orden,
                                  font_id=font_id)
    return fuera.convert("RGB")


# --- what goes into the cartridge ---------------------------------------------
#
# BG2, at 4bpp and with palette 0: the tiles from `RANURA_VRAM` and the tilemap
# at `RANURA_MAP`, which are the VRAM places the menu and the slot screen
# already write —see `volver_al_mapa`—, so the map comes back without anything
# else having to be restored. The palette is entries 0 to 15, which the menu
# also restores on the way back.
COLORES_MAX = 16
# How many frames the fade to black of "Yes" lasts, and how long the song's:
# the screen's measured on the 2015 RPG_RT —about 330 ms—, and the song's is
# `Scene_End`'s `BgmFade(400)`.
CUADROS_FUNDIDO = 20
MS_FUNDIDO_TEMA = 400


def rampa():
    """The INIDISP brightness on each frame of the fade to black: a straight
    line from 15 to 0 in `CUADROS_FUNDIDO` steps, the last one black."""
    ultimo = CUADROS_FUNDIDO - 1
    return [15 * (ultimo - n) // ultimo for n in range(CUADROS_FUNDIDO)]


def convertir(sys_img, db, font_id=None):
    """The screen as the ROM uploads it: `(tiles, filas, fila0, paletas)`.

    `tiles[i][y][x]` are indices from 0 to 15, and 0 is the empty tile;
    `filas` the tilemap words of the cell rows that have something, from
    `fila0`; the rest of the tilemap is zero. `paletas` are two lists of 16
    15-bit colors: the one with the bar on "Yes" and the one with the bar on
    "No". See the header: one index per pair of colors.
    """
    quince = [[tuple(v >> 3 for v in p) for p in
               dibujar(sys_img, db, n, font_id).get_flattened_data()]
              for n in (SI, NO)]
    pares = sorted(set(zip(*quince)))
    pares.remove((NEGRO, NEGRO))
    pares.insert(0, (NEGRO, NEGRO))     # 0: transparent, the black background
    if len(pares) > COLORES_MAX:
        raise SystemExit("the End Game screen uses %d pairs of colors and "
                         "a 4bpp palette has %d" % (len(pares),
                                                           COLORES_MAX))
    indice = {par: i for i, par in enumerate(pares)}
    pixeles = [indice[par] for par in zip(*quince)]
    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde, mapa = [vacio], {vacio: 0}, []
    for fila in range(ALTO // CELL):
        for col in range(ANCHO // CELL):
            celda = tuple(tuple(pixeles[(fila * CELL + y) * ANCHO
                                        + col * CELL:(fila * CELL + y) * ANCHO
                                        + col * CELL + CELL])
                          for y in range(CELL))
            # Mirrored too, with the tilemap's flip bits: the window frame is
            # symmetric.
            h = tuple(tuple(reversed(r)) for r in celda)
            for volteo, forma in ((0, celda), (0x4000, h),
                                  (0x8000, tuple(reversed(celda))),
                                  (0xC000, tuple(reversed(h)))):
                if forma in donde:
                    mapa.append(donde[forma] | volteo)
                    break
            else:
                donde[celda] = len(tiles)
                tiles.append(celda)
                mapa.append(donde[celda])
    cols = ANCHO // CELL
    usadas = [f for f in range(ALTO // CELL) if any(mapa[f * cols:(f + 1) * cols])]
    fila0, fila1 = usadas[0], usadas[-1] + 1
    paletas = [[par[n] for par in pares] + [NEGRO] * (COLORES_MAX - len(pares))
               for n in (SI, NO)]
    return tiles, mapa[fila0 * cols:fila1 * cols], fila0, paletas


def render(sys_img, db, elegida, font_id=None):
    """What the ROM has to show, rebuilt from `convertir` and not from
    `dibujar`: the tiles, the tilemap and the palette, at 15 bits. That way
    the drawing the ROM is compared against goes through the same color-pair
    math as the ROM does."""
    from PIL import Image
    tiles, filas, fila0, paletas = convertir(sys_img, db, font_id)
    paleta = paletas[elegida]
    fuera = Image.new("RGB", (ANCHO, ALTO), NEGRO)
    px = fuera.load()
    cols = ANCHO // CELL
    for n, palabra in enumerate(filas):
        celda = tiles[palabra & 0x3FF]
        if palabra & 0x4000:
            celda = tuple(tuple(reversed(r)) for r in celda)
        if palabra & 0x8000:
            celda = tuple(reversed(celda))
        fila, col = fila0 + n // cols, n % cols
        for y in range(CELL):
            for x in range(CELL):
                r, g, b = paleta[celda[y][x]]
                px[col * CELL + x, fila * CELL + y] = (r << 3, g << 3, b << 3)
    return fuera

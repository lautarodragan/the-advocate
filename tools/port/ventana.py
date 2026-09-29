"""RM2k's message window, built from the game's System.

The rules come from easyrpg-player's `Window::RefreshBackground` and
`Window::RefreshFrame`, and the text from `Font::Render`. Nothing is made up
here: if something does not match the original, it is fixed by looking at
those functions.

The System is a 160x80 image with everything inside:

    (0,0,32,32)     the background, which is **stretched** to the window size
    (32,0,8,8)      the top-left corner of the frame
    (40,0,16,8)     the top edge, repeated across the width
    (56,0,8,8)      the top-right corner
    (32,8,8,16)     the left edge, repeated down the height
    (56,8,8,16)     the right edge
    (56,0,8,8)      the top-right corner
    (...,24,...)    the same for the bottom
    (16,32,16,16)   the color of the text shadow
    (c%10*16, c//10*16+48, 16, 16)   text color number c

The text and shadow colors are **16x16 blocks**, not single colors: each
pixel of the glyph takes the color at the same position inside the block, so
a letter comes out with a vertical gradient. It is what `MaskedBlit` does.
"""
import os

from PIL import Image

from port.constants import COLUMNS, LINES
from render import render_map

# The size and place of the message window. In RM2k the screen is 320x240
# and the window takes 320x80 at the bottom; here the screen is 256x224, so
# the window is 256x80 and the text loses 64 px of width. What does not fit
# is truncated: it is the phase 1 decision.
ANCHO, ALTO = 256, 80
BORDE = 8                       # `border_x` and `border_y` of Window
ALTO_LINEA = 16                 # `contents_y += 16` of Window_Message
TEXTO_Y = 2                     # the `contents_y = 2` of the first line


def skin(game_dir, nombre):
    """The game's System, in RGBA and with the color key already resolved.

    It goes through `render_map.load_image` and not `Image.open` on purpose:
    in RM2k **palette index 0 is transparent**, and that rule is already
    written there. Writing it again here would mean two conventions that
    have to be kept the same.

    It is not a detail: in `ablskin` index 0 is a strong orange, and the
    window frame uses it for its whole inside. Drawing it opaque gave an
    8 px orange frame where the game has a 2 px one and the rest
    transparent. The EasyRPG capture found it, not the eye.
    """
    for base in (os.path.join(game_dir, "System"), game_dir):
        ruta = os.path.join(base, nombre + ".png")
        if os.path.exists(ruta):
            return render_map.load_image(ruta)
    raise FileNotFoundError("System %r is not in %s" % (nombre, game_dir))


def color_de_texto(sys_img, numero):
    """The 16x16 block of text color number `numero`."""
    x, y = numero % 10 * 16, numero // 10 * 16 + 48
    return sys_img.crop((x, y, x + 16, y + 16))


def color_de_sombra(sys_img):
    return sys_img.crop((16, 32, 32, 48))


def _repetido(origen, ancho, alto):
    """`TiledBlit`: repeat a crop until it fills ancho x alto."""
    salida = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    for y in range(0, alto, origen.height):
        for x in range(0, ancho, origen.width):
            salida.paste(origen, (x, y))
    return salida.crop((0, 0, ancho, alto))


def _pegar(destino, trozo, x, y):
    """Paste honoring the color key, like `chipset.blit`."""
    destino.paste(trozo, (x, y), trozo)


def ventana(sys_img, ancho=ANCHO, alto=ALTO):
    """The empty window: the stretched background and the frame on top."""
    # The background is stretched, not tiled: it is the `stretch` RM2k has on
    # by default.
    fondo = sys_img.crop((0, 0, 32, 32)).resize((ancho, alto), Image.NEAREST)
    marco = fondo.copy()
    # The top and bottom edges, repeated between the corners.
    _pegar(marco, _repetido(sys_img.crop((40, 0, 56, 8)), ancho - 16, 8), 8, 0)
    _pegar(marco, _repetido(sys_img.crop((40, 24, 56, 32)), ancho - 16, 8),
           8, alto - 8)
    # The side ones.
    _pegar(marco, _repetido(sys_img.crop((32, 8, 40, 24)), 8, alto - 16), 0, 8)
    _pegar(marco, _repetido(sys_img.crop((56, 8, 64, 24)), 8, alto - 16),
           ancho - 8, 8)
    # And the four corners, which go last because they overwrite the edges.
    _pegar(marco, sys_img.crop((32, 0, 40, 8)), 0, 0)
    _pegar(marco, sys_img.crop((56, 0, 64, 8)), ancho - 8, 0)
    _pegar(marco, sys_img.crop((32, 24, 40, 32)), 0, alto - 8)
    _pegar(marco, sys_img.crop((56, 24, 64, 32)), ancho - 8, alto - 8)
    return marco


def cursor(sys_img, ancho, alto=16):
    """The cursor of a list, the first of the System's two frames: Window's
    `RefreshCursor` in easyrpg, 8x8 corners and the rest repeated between
    them. What is transparent in the System stays transparent."""
    x0 = 64
    salida = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    if ancho > 16 and alto > 16:
        _pegar(salida, _repetido(sys_img.crop((x0 + 8, 8, x0 + 24, 24)),
                                 ancho - 16, alto - 16), 8, 8)
    _pegar(salida, _repetido(sys_img.crop((x0 + 8, 0, x0 + 24, 8)),
                             ancho - 16, 8), 8, 0)
    _pegar(salida, _repetido(sys_img.crop((x0 + 8, 24, x0 + 24, 32)),
                             ancho - 16, 8), 8, alto - 8)
    if alto > 16:
        _pegar(salida, _repetido(sys_img.crop((x0, 8, x0 + 8, 24)),
                                 8, alto - 16), 0, 8)
        _pegar(salida, _repetido(sys_img.crop((x0 + 24, 8, x0 + 32, 24)),
                                 8, alto - 16), ancho - 8, 8)
    _pegar(salida, sys_img.crop((x0, 0, x0 + 8, 8)), 0, 0)
    _pegar(salida, sys_img.crop((x0 + 24, 0, x0 + 32, 8)), ancho - 8, 0)
    _pegar(salida, sys_img.crop((x0, 24, x0 + 8, 32)), 0, alto - 8)
    _pegar(salida, sys_img.crop((x0 + 24, 24, x0 + 32, 32)), ancho - 8,
           alto - 8)
    return salida


# Where the color of each glyph pixel comes from, according to easyrpg-player's
# `Font::Render`. It is not a flat color: the glyph is used as a mask over the
# System's 16x16 block, so the letter comes out with a gradient.
#
#   text    (color%10*16 + 2, color//10*16 + 48 + 16 - 12)
#   shadow  (16, 32), drawn first, shifted one pixel in x and in y
#
# The `16 - 12` is what rests the 12-row glyph against the foot of the 16 block.
# None of these numbers is guessed: they come from font.cpp.
TEXTO_OFS = (2, 4)
SOMBRA_ORIGEN = (16, 32)


def dibujar_linea(destino, sys_img, x, y, texto, color=0,
                  font_id=None):
    """A line of text on `destino`, with its shadow, like RM2k.

    Returns the x it ended at. Whatever goes past the width of `destino` is
    clipped on its own: in phase 1 lines that do not fit are truncated.
    """
    from port import font
    if font_id is None:
        font_id = font.MINCHO
    bloque = color_de_texto(sys_img, color)
    sombra = color_de_sombra(sys_img)
    ox, oy = TEXTO_OFS
    for ch in texto:
        for px, py in font.pixels(ch, font_id):
            # The shadow goes first and shifted by one, so the text covers it
            # where they overlap. It is easyrpg's order and it shows on the
            # diagonals.
            for dx, dy, fuente_color, fx, fy in (
                    (1, 1, sombra, px, py), (0, 0, bloque, ox + px, oy + py)):
                dx, dy = x + px + dx, y + py + dy
                color = fuente_color.getpixel((fx, fy))
                if (0 <= dx < destino.width and 0 <= dy < destino.height
                        and color[3]):
                    destino.putpixel((dx, dy), color)
        x += font.WIDTH
    return x


def pagina(sys_img, lineas, ancho=ANCHO, alto=ALTO, font_id=None):
    """The window with up to four lines of text inside."""
    vista = ventana(sys_img, ancho, alto)
    for n, texto in enumerate(lineas[:LINES]):
        # The truncation goes here and not in the caller so both sides use
        # the same number: the ROM applies it when emitting the message.
        dibujar_linea(vista, sys_img, BORDE,
                      BORDE + TEXTO_Y + n * ALTO_LINEA, texto[:COLUMNS],
                      font_id=font_id)
    return vista

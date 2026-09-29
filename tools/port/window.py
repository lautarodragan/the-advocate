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
WIDTH, HEIGHT = 256, 80
BORDER = 8                       # `border_x` and `border_y` of Window
LINE_HEIGHT = 16                 # `contents_y += 16` of Window_Message
TEXT_Y = 2                     # the `contents_y = 2` of the first line


def skin(game_dir, name):
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
        path = os.path.join(base, name + ".png")
        if os.path.exists(path):
            return render_map.load_image(path)
    raise FileNotFoundError("System %r is not in %s" % (name, game_dir))


def text_color(sys_img, number):
    """The 16x16 block of text color number `number`."""
    x, y = number % 10 * 16, number // 10 * 16 + 48
    return sys_img.crop((x, y, x + 16, y + 16))


def shadow_color(sys_img):
    return sys_img.crop((16, 32, 32, 48))


def _tiled(source, width, height):
    """`TiledBlit`: repeat a crop until it fills ancho x alto."""
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for y in range(0, height, source.height):
        for x in range(0, width, source.width):
            out.paste(source, (x, y))
    return out.crop((0, 0, width, height))


def _paste(dest, piece, x, y):
    """Paste honoring the color key, like `chipset.blit`."""
    dest.paste(piece, (x, y), piece)


def window(sys_img, width=WIDTH, height=HEIGHT):
    """The empty window: the stretched background and the frame on top."""
    # The background is stretched, not tiled: it is the `stretch` RM2k has on
    # by default.
    background = sys_img.crop((0, 0, 32, 32)).resize((width, height), Image.NEAREST)
    frame_img = background.copy()
    # The top and bottom edges, repeated between the corners.
    _paste(frame_img, _tiled(sys_img.crop((40, 0, 56, 8)), width - 16, 8), 8, 0)
    _paste(frame_img, _tiled(sys_img.crop((40, 24, 56, 32)), width - 16, 8),
           8, height - 8)
    # The side ones.
    _paste(frame_img, _tiled(sys_img.crop((32, 8, 40, 24)), 8, height - 16), 0, 8)
    _paste(frame_img, _tiled(sys_img.crop((56, 8, 64, 24)), 8, height - 16),
           width - 8, 8)
    # And the four corners, which go last because they overwrite the edges.
    _paste(frame_img, sys_img.crop((32, 0, 40, 8)), 0, 0)
    _paste(frame_img, sys_img.crop((56, 0, 64, 8)), width - 8, 0)
    _paste(frame_img, sys_img.crop((32, 24, 40, 32)), 0, height - 8)
    _paste(frame_img, sys_img.crop((56, 24, 64, 32)), width - 8, height - 8)
    return frame_img


def cursor(sys_img, width, height=16):
    """The cursor of a list, the first of the System's two frames: Window's
    `RefreshCursor` in easyrpg, 8x8 corners and the rest repeated between
    them. What is transparent in the System stays transparent."""
    x0 = 64
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if width > 16 and height > 16:
        _paste(out, _tiled(sys_img.crop((x0 + 8, 8, x0 + 24, 24)),
                           width - 16, height - 16), 8, 8)
    _paste(out, _tiled(sys_img.crop((x0 + 8, 0, x0 + 24, 8)),
                       width - 16, 8), 8, 0)
    _paste(out, _tiled(sys_img.crop((x0 + 8, 24, x0 + 24, 32)),
                       width - 16, 8), 8, height - 8)
    if height > 16:
        _paste(out, _tiled(sys_img.crop((x0, 8, x0 + 8, 24)),
                           8, height - 16), 0, 8)
        _paste(out, _tiled(sys_img.crop((x0 + 24, 8, x0 + 32, 24)),
                           8, height - 16), width - 8, 8)
    _paste(out, sys_img.crop((x0, 0, x0 + 8, 8)), 0, 0)
    _paste(out, sys_img.crop((x0 + 24, 0, x0 + 32, 8)), width - 8, 0)
    _paste(out, sys_img.crop((x0, 24, x0 + 8, 32)), 0, height - 8)
    _paste(out, sys_img.crop((x0 + 24, 24, x0 + 32, 32)), width - 8,
           height - 8)
    return out


# Where the color of each glyph pixel comes from, according to easyrpg-player's
# `Font::Render`. It is not a flat color: the glyph is used as a mask over the
# System's 16x16 block, so the letter comes out with a gradient.
#
#   text    (color%10*16 + 2, color//10*16 + 48 + 16 - 12)
#   shadow  (16, 32), drawn first, shifted one pixel in x and in y
#
# The `16 - 12` is what rests the 12-row glyph against the foot of the 16 block.
# None of these numbers is guessed: they come from font.cpp.
TEXT_OFFSET = (2, 4)
SHADOW_ORIGIN = (16, 32)


def draw_line(dest, sys_img, x, y, text, color=0,
              font_id=None):
    """A line of text on `dest`, with its shadow, like RM2k.

    Returns the x it ended at. Whatever goes past the width of `dest` is
    clipped on its own: in phase 1 lines that do not fit are truncated.
    """
    from port import font
    if font_id is None:
        font_id = font.MINCHO
    block = text_color(sys_img, color)
    shadow = shadow_color(sys_img)
    ox, oy = TEXT_OFFSET
    for ch in text:
        for px, py in font.pixels(ch, font_id):
            # The shadow goes first and shifted by one, so the text covers it
            # where they overlap. It is easyrpg's order and it shows on the
            # diagonals.
            for dx, dy, font_color, fx, fy in (
                    (1, 1, shadow, px, py), (0, 0, block, ox + px, oy + py)):
                dx, dy = x + px + dx, y + py + dy
                color = font_color.getpixel((fx, fy))
                if (0 <= dx < dest.width and 0 <= dy < dest.height
                        and color[3]):
                    dest.putpixel((dx, dy), color)
        x += font.WIDTH
    return x


def page(sys_img, lines, width=WIDTH, height=HEIGHT, font_id=None):
    """The window with up to four lines of text inside."""
    view = window(sys_img, width, height)
    for n, text in enumerate(lines[:LINES]):
        # The truncation goes here and not in the caller so both sides use
        # the same number: the ROM applies it when emitting the message.
        draw_line(view, sys_img, BORDER,
                  BORDER + TEXT_Y + n * LINE_HEIGHT, text[:COLUMNS],
                  font_id=font_id)
    return view

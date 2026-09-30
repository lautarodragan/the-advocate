"""RM2k's message window, built from the game's System.

**What comes from the System is drawn by `rm2k-render system`**: the empty
window —its background stretched or tiled as the database's
`message_stretch` says, and the frame—, the cursor, the 16x16 blocks the
text and its shadow take their colors from, and the timer's glyphs. Which
piece of the System is which is `rm2k-rules`' (`system`), and how they are
put together is easyrpg-player's `Window::RefreshBackground`,
`RefreshFrame` and `RefreshCursor`: a viewer of the game on a PC would draw
them the same way.

What stays here is the port's: the window's size and the text's place on a
screen 256 wide, the lines cut to what fits, and the text drawn with the
port's 8-pixel font (`font.py`), which is `Font::Render`'s rule over the
System's blocks.

The text and shadow colors are **16x16 blocks**, not single colors: each
pixel of the glyph takes the color at the same position inside the block, so
a letter comes out with a vertical gradient. It is what `MaskedBlit` does.
"""
import os

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

# How many text colors the System has: `rm2k-render` draws them all at once.
TEXT_COLORS = 20


class Skin:
    """The game's System, and what `rm2k-render` drew from it, remembered:
    the same window and the same blocks are asked for many times."""

    def __init__(self, path, message_stretch):
        self.path = path
        self.message_stretch = message_stretch
        self._drawn = {}
        self._blocks = None

    def _draw(self, entries):
        return render_map.draw("system", [
            dict(entry, system_file=self.path) for entry in entries])

    def _block(self, name):
        """The small pieces, all in one call the first time one is asked
        for: the twenty text colors, the shadow and the timer."""
        if self._blocks is None:
            names = ([("text_color", n) for n in range(TEXT_COLORS)]
                     + [("shadow",), ("timer",)])
            drawn = self._draw([{"draw": "text_color", "color": n[1]}
                                if n[0] == "text_color" else {"draw": n[0]}
                                for n in names])
            self._blocks = dict(zip(names, drawn))
        return self._blocks[name]

    def window(self, width, height):
        key = ("window", width, height)
        if key not in self._drawn:
            self._drawn[key] = self._draw([{
                "draw": "window", "width": width, "height": height,
                "message_stretch": self.message_stretch}])[0]
        return self._drawn[key].copy()

    def cursor(self, width, height):
        key = ("cursor", width, height)
        if key not in self._drawn:
            self._drawn[key] = self._draw([{
                "draw": "cursor", "width": width, "height": height}])[0]
        return self._drawn[key].copy()

    def text_color(self, number):
        return self._block(("text_color", number))

    def shadow(self):
        return self._block(("shadow",))

    def timer(self):
        return self._block(("timer",))


_SKINS = {}


def skin(game_dir, database):
    """The game's System, the one `database` names, with the way its
    windows fill their background.

    The System is looked for in the game's `System/`, and then in the
    game's folder itself.
    """
    name = database.system_name
    for base in (os.path.join(game_dir, "System"), game_dir):
        path = os.path.abspath(os.path.join(base, name + ".png"))
        if os.path.exists(path):
            key = (path, database.message_stretch)
            if key not in _SKINS:
                _SKINS[key] = Skin(path, database.message_stretch)
            return _SKINS[key]
    raise FileNotFoundError("System %r is not in %s" % (name, game_dir))


def text_color(sys_img, number):
    """The 16x16 block of text color number `number`."""
    return sys_img.text_color(number)


def shadow_color(sys_img):
    return sys_img.shadow()


def window(sys_img, width=WIDTH, height=HEIGHT):
    """The empty window: the background and the frame on top."""
    return sys_img.window(width, height)


def cursor(sys_img, width, height=16):
    """The cursor of a list, the first of the System's two drawings."""
    return sys_img.cursor(width, height)


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

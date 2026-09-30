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

from render import render_map


class Skin:
    """The game's System, and what `rm2k-render` drew from it, remembered:
    the same window and the same blocks are asked for many times."""

    def __init__(self, path, message_stretch):
        self.path = path
        self.message_stretch = message_stretch
        self._timer = None

    def timer(self):
        if self._timer is None:
            self._timer = render_map.draw("system", [
                {"draw": "timer", "system_file": self.path}])[0]
        return self._timer


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


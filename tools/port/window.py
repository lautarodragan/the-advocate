"""The game's System, as the rest of the converter still reads it: where
its picture is, and the timer's glyphs, which `rm2k-render system` cuts.

The maps use it: `map_convert` hands the System to `rm2k-snes-maps` for
the timer's digits, and `snes_convert` masks the timer's colors with it.
Everything else that comes from the System —the windows, the cursors, the
text— is drawn by `rm2k-snes-screens`, which finds the System itself.
"""
import os

from render import render_map


class Skin:
    """The game's System, and its timer's glyphs once `rm2k-render` drew
    them."""

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


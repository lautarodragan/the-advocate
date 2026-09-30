"""The pictures, which are `rm2k-snes-images`: what goes into its requests
and the shape its answer takes for the converter.

**The pixels are the stage's**: scaling with Pillow's LANCZOS, the
console's tint, stacking an animation's cells, bringing the colours down
and handing back indices and palette —see its README,
`tools/rm2k-snes/images/`—. What stays here is which pictures, found in the
game's folder or the RTP, and the sizes the cartridge decided, which are
the constants of `scene.py`, `animation.py`, `picture.py` and
`constants.py` that the emission also writes for the ROM: they travel in
the request so they are written in one place.
"""

import json
import os

from port import stage

BINARY = "rm2k-snes-images"
PROJECT = "images"


def _answer(command, request, *flags):
    return json.loads(stage.run(BINARY, PROJECT, command, request,
                                *flags)[command + ".json"])


def _colors(palette):
    return [tuple(c) for c in palette]


def _cells(tiles):
    return [tuple(tuple(row) for row in cell) for cell in tiles]


def fullscreen(path, width, height, cell, first_color, cap):
    """A picture that fills the screen, as `(tiles, palette, tilemap)`: the
    distinct 8x8 cells of CGRAM indices —already shifted by
    `first_color`—, the colours at fifteen bits and a tile per cell."""
    a = _answer("fullscreen", {
        "file": os.path.abspath(path), "width": width, "height": height,
        "cell": cell, "first_color": first_color, "cap": cap})
    return _cells(a["tiles"]), _colors(a["palette"]), a["tilemap"]


def picture(path, use_transparent_color, top_trans, cx, cy, rm_screen,
            screen, colors):
    """The picture of a `ShowPicture` centred at `(cx, cy)` of RM2k's
    screen, as the stage answers it: where it lands, its palette and its
    indices plus one."""
    return _answer("picture", {
        "file": os.path.abspath(path),
        "use_transparent_color": bool(use_transparent_color),
        "top_trans": top_trans, "x": cx, "y": cy,
        "rm_screen": list(rm_screen), "screen": list(screen),
        "colors": colors})


def _scene():
    from port import scene as E
    return {"width": E.WIDTH, "height": E.HEIGHT, "colors": E.COLORS,
            "cgram_base": E.CGRAM_BASE, "light_scale": E.FALLBACK_SCALE,
            "light_colors": E.FALLBACK_COLORS,
            "scale": [E.SCALE_NUM, E.SCALE_DEN],
            "battler_colors": E.BATTLER_COLORS, "alpha_min": E.ALPHA_MIN}


def backdrops(wanted):
    """Each of `wanted` —`(path, quality, light)`— as `(quality, light)`,
    each None if it was not asked for: the stage's answers."""
    if not wanted:
        return []
    a = _answer("backdrops", {
        "scene": _scene(),
        "backdrops": [{"file": os.path.abspath(p), "quality": q, "light": li}
                      for p, q, li in wanted]})
    return [(one["quality"], one["light"]) for one in a]


def battlers(wanted):
    """Each of `wanted` —`(path, hue)`— as the stage answers it."""
    if not wanted:
        return []
    return _answer("battlers", {
        "scene": _scene(),
        "battlers": [{"file": os.path.abspath(p), "hue": hue}
                     for p, hue in wanted]})


def animations(wanted, game_dir):
    """Each of `wanted` —`(number, sheet)`— as the stage answers it, or
    None if nothing of it is drawn. The animation itself is read from the
    game's dump."""
    from port import animation as A
    from port.screen_stage import dump_of
    if not wanted:
        return []
    return _answer("animations", {
        "side": A.BOX, "colors": A.COLORS, "alpha_min": A.ALPHA_MIN,
        "animations": [{"number": n, "sheet": os.path.abspath(s)}
                       for n, s in wanted]},
        "--data", dump_of(game_dir))

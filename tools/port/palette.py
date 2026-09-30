"""An image brought to a full screen at 8 bpp: the title's and the Game
Over's.

`convert` was born for the title screen, with the colors kept by use that
the pictures, the animations and the quality battle backdrops are brought
down with too. Since 2026-09-30 `rm2k-snes-images` does all of it; this
says which screen and how many colors.
"""

from port.constants import HEIGHT, WIDTH, CELL, COLORS, MENU_CGRAM


def convert(path, first_color=MENU_CGRAM, cap=COLORS):
    """A full-screen image as (tiles, paleta, tilemap).

    `tiles` are the unique tiles at 8 bits per pixel; `palette` their colors,
    which go in CGRAM **starting at `first_color`** —on the title,
    `MENU_CGRAM`, because the ones below belong to the menu—; `tilemap` the
    32x28 entries, in the 32x32 tilemap the PPU expects. `cap` is how many
    colors are left.

    The indices the tiles carry are already shifted, so whoever emits them
    does not have to remember to add anything: the shift is written once and
    there. `rm2k-snes-images fullscreen` does it: the scaling —LANCZOS, the
    one that smears the edges of the title's text the least— and the
    colors, kept by use with black first —`adeleine::keep_most_used`—.
    """
    from port import image_stage
    return image_stage.fullscreen(path, WIDTH, HEIGHT, CELL, first_color, cap)

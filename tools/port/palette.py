"""An image brought down to N 15-bit colors, or to a full screen at 8 bpp.

`reduce` and `convert` were born for the title screen, and today the
pictures, the animations, the battle backdrops and the full screens use them
too.
"""

import collections

from port.constants import HEIGHT, WIDTH, CELL, COLORS, COLS, ROWS, MENU_CGRAM

BLACK = (0, 0, 0)


def _distance(a, b):
    """How far apart two 15-bit colors are, squared.

    Euclidean and with no per-channel weights: the alternative —weighting by
    luma, which is what `merge_least_visible` does for the palettes of
    sixteen— would change nothing visible here and would need an explanation
    of why the weights are those. The colors that get merged are the ones
    that barely appear, and the neighbor they get is one step away.
    """
    return sum((x - y) ** 2 for x, y in zip(a, b))


def reduce(pixels, cap=COLORS):
    """The image's colors brought down to `cap`, and the map of where each
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
    counts = collections.Counter(pixels)
    # Black keeps index 0 even if it was not among the most used: it is the
    # backdrop color, and this way what the PPU paints where there is
    # nothing matches what the image has there.
    order = sorted(counts, key=lambda c: (-counts[c], c))
    if BLACK in order:
        order.remove(BLACK)
    palette = [BLACK] + order[:cap - 1]
    kept = set(palette)
    mapping = {c: c for c in kept}
    for color in order[cap - 1:]:
        mapping[color] = min(palette, key=lambda p: (_distance(color, p), p))
    return palette, mapping


def _to_15_bits(image):
    """The image scaled to the screen, with its colors at 15 bits.

    The scaling is LANCZOS, which is the one that smears the edges of the
    title's text the least; the original has a lot of gradient and little
    fine detail, so the difference against bicubic shows in the credits and
    nowhere else.
    """
    from PIL import Image
    small = image.convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    return [(r >> 3, g >> 3, b >> 3) for r, g, b in small.get_flattened_data()]


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
    colors, as `reduce` here.
    """
    from port import image_stage
    return image_stage.fullscreen(path, WIDTH, HEIGHT, CELL, first_color, cap)

#!/usr/bin/env python3
"""The picture of a `ShowPicture` on the console screen.

It lives apart from `snes_convert.py` for the same reason as `title.py`: it
is not a map. It is a loose image that has to be put on the screen, and the
only thing to decide is **exactly where each pixel lands and what color it
is**.

Three decisions, and all three are paid for:

**It goes in OAM objects, not in a layer.** In mode 3 both layers belong to
the map, and the alternative —lending one to the picture while it lasts—
forces reloading the map when erasing it: 30 KB of DMA and two black frames,
which is what `back_to_map` costs. With objects the picture is put up and
taken down without touching anything underneath, which is also what RM2k
does: the image is composited on top. The price is **fifteen colors**, those
of a sprite palette, against the PNG's 226; and the per-line object budget,
which on the picture's 29 lines drops from 34 tiles to 10.

**RM2k's screen is 320x240 and the console's 256x224**, so the picture is
scaled like the title image: the two corners of its rectangle go through the
same math and the image is brought to the size that results. It is the same
20% narrower that the title screen already has, and for the same reason: the
original's aspect ratio is not the console's.

**RM2k's position is the center of the image**, not its corner:
`Sprite_Picture` does `SetOx(width / 2)`. The "One year previously" picture
is centered at (100, 175) of 320x240 and measures 233x31, so **it starts at
-16 and its left edge gets cut off**. That is not our bug: it is what the
game shows.

What is **not** done, and therefore not accepted either —see
`picture.fits`—: moving the image, scaling it, making it
translucent (`top_trans`), the transparent color, saturation, and the
rotation and wave effects. Of the three `Picture`s on the "1 year earlier"
page none asks for any of that: the only thing that changes between one and
the next is the **tone**, which is what draws the fade.
"""

import collections

from port.color import apply_tint
from port.palette import reduce

# RM2k's screen and the console's.
RM_WIDTH, RM_HEIGHT = 320, 240
WIDTH, HEIGHT = 256, 224

# This port's large object, which `OBSEL_VALUE` fixes at 32x32.
OBJ = 32
# The 8x8 tiles it measures on a side, and how many there are in a row of the
# OAM name grid.
OBJ_SIDE = OBJ // 8
GRID = 16
# The fifteen of a sprite palette: index 0 is not drawn.
COLORS = 15
# How many objects wide are accepted. Eight are 256 pixels, that is the whole
# screen, and 128 sprite tiles; more than that is not a picture.
OBJECTS_MAX = 8
BLACK = (0, 0, 0)


def scale_x(v):
    """A horizontal coordinate of RM2k's screen, on the console's.

    Integer division rounding down **with negatives too**, which is what
    `//` does in Python: the picture starts at -16 and both ends have to get
    the same -13.
    """
    return v * WIDTH // RM_WIDTH


def scale_y(v):
    return v * HEIGHT // RM_HEIGHT


def box(width, height, cx, cy):
    """Where on the console screen an image of `width` x `height` centered at
    (cx, cy) of RM2k's lands: (x, y, ancho, alto).

    Both corners go through the same math and the size comes from
    subtracting them. Scaling the size on its own would give a height of 28
    where the corners give 29, and one pixel of difference between the two
    ends is a comparison that fails.
    """
    x0, y0 = cx - width // 2, cy - height // 2
    ex0, ey0 = scale_x(x0), scale_y(y0)
    return ex0, ey0, scale_x(x0 + width) - ex0, scale_y(y0 + height) - ey0


def _to_15_bits(image, width, height):
    """The image scaled and with its colors at 15 bits, row by row.

    LANCZOS like `palette._to_15_bits`, and for the same reason: it is the one
    that smears the edges of text the least.
    """
    from PIL import Image
    small = image.convert("RGB").resize((width, height), Image.LANCZOS)
    data = [(r >> 3, g >> 3, b >> 3) for r, g, b in small.get_flattened_data()]
    return [data[y * width:(y + 1) * width] for y in range(height)]


def convert(image, cx, cy):
    """The picture ready for both ends.

    Returns a dictionary with where it lands —`x`, `y`, `width`, `height`—,
    how many 32x32 objects it takes, its palette of fifteen 15-bit colors and
    the image as indices into that palette **shifted by one**, which is how a
    sprite palette numbers them: 0 is the transparent one and is not drawn.

    The colors come from `palette.reduce`, the same as the title screen's,
    and for the same reason: it does not average, so it does not invent
    colors that would have to be quantized again, and it does not depend on
    the PIL version. From 226 colors to fifteen the glow's gradient becomes
    stepped; it shows and it is declared.
    """
    x, y, width, height = box(image.width, image.height, cx, cy)
    rows = _to_15_bits(image, width, height)
    pixels = [c for row in rows for c in row]
    palette, mapping = reduce(pixels, COLORS)
    where = {color: i + 1 for i, color in enumerate(palette)}
    indices = [[where[mapping[c]] for c in row] for row in rows]
    return {
        "x": x, "y": y, "ancho": width, "alto": height,
        "objetos": -(-width // OBJ),
        "paleta": palette,
        "indices": indices,
    }


def fits(info):
    """Whether the picture fits the model: one object tall and up to
    `OBJECTS_MAX` wide. `events.Pictures` asks this when choosing the
    picture."""
    return 0 < info["alto"] <= OBJ and 0 < info["objetos"] <= OBJECTS_MAX


def cells(info):
    """The picture cut into 8x8 tiles, in the order OAM numbers them.

    A 32x32 object reads four tiles from four consecutive rows of the name
    grid, which is sixteen wide: so a **row of blocks** —64 tiles— fits four
    objects and no more. Object `o` therefore starts at
    `(o // 4) * 64 + (o % 4) * 4`, and inside it tile (tx, ty) is `ty` grid
    rows further on.

    Returns {tile number relative to the base: 8x8 cell}. What falls outside
    the image —the padding pixels up to the object's 32— is index 0, that is
    transparent: whatever is underneath shows there, which is what should
    happen.
    """
    out = {}
    indices = info["indices"]
    for o in range(info["objetos"]):
        start = (o // 4) * (4 * GRID) + (o % 4) * OBJ_SIDE
        for ty in range(OBJ_SIDE):
            for tx in range(OBJ_SIDE):
                cell = []
                for py in range(8):
                    row = []
                    for px in range(8):
                        cy = ty * 8 + py
                        cx = o * OBJ + tx * 8 + px
                        row.append(indices[cy][cx]
                                   if cy < info["alto"] and cx < info["ancho"]
                                   else 0)
                    cell.append(tuple(row))
                out[start + ty * GRID + tx] = tuple(cell)
    return out


def reserved_tiles(info):
    """How many 8x8 tiles of the sprite bank the picture takes.

    Whole rows of blocks, not the 96 it uses: the arithmetic above needs them
    whole, and the timer's digits already round to the same thing for the
    same reason —`timer_digits`, in `rm2k-snes-map-sprites`—. With six objects that is two rows, 128 tiles, of which 96
    are used.
    """
    return -(-info["objetos"] // 4) * (4 * GRID)


def render(info, hue):
    """The picture as it looks on screen, with its tone applied: an RGBA
    image of `width` x `height` to paste at (x, y).

    The tone is RM2k's —(r, g, b, sat), 100 neutral— and goes through
    `color.apply_tint`, which is the same math as the screen tint: there and here
    it is `ToneBlit`. The console does not tint pixels but the picture's
    fifteen CGRAM entries, so tinting the palette and painting gives exactly
    the same thing.
    """
    from PIL import Image
    palette = [apply_tint(c[0] | (c[1] << 5) | (c[2] << 10), hue)
               for c in info["paleta"]]
    colors = [(0, 0, 0, 0)] + [(((p & 0x1F) << 3), (((p >> 5) & 0x1F) << 3),
                                (((p >> 10) & 0x1F) << 3), 255)
                               for p in palette]
    out = Image.new("RGBA", (info["ancho"], info["alto"]))
    out.putdata([colors[i] for row in info["indices"] for i in row])
    return out


def report(info):
    """The numbers that justify the layout, for the recipe to print."""
    return {
        "donde": (info["x"], info["y"]),
        "tamano": (info["ancho"], info["alto"]),
        "objetos": info["objetos"],
        "tiles": reserved_tiles(info),
        "colores": len(info["paleta"]),
    }

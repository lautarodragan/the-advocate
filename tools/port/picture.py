#!/usr/bin/env python3
"""The picture of a `ShowPicture` on the console screen.

It lives apart from `snes_convert.py` for the same reason as the title: it
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


def convert(path, p):
    """The picture of the file at `path`, shown by a `ShowPicture` with
    parameters `p`, ready for both ends.

    Returns a dictionary with where it lands —`x`, `y`, `width`, `height`—,
    how many 32x32 objects it takes, its palette of fifteen 15-bit colors and
    the image as indices into that palette **shifted by one**, which is how a
    sprite palette numbers them: 0 is the transparent one and is not drawn.

    `rm2k-snes-images picture` does it: RM2k's drawing of the picture —with
    its transparent color and its transparency, which the console drops—,
    `box` and the scaling, and the colors, which are kept by use like the
    title screen's and for the same reason: it does not average, so it does
    not invent colors that would have to be quantized again. From 226 colors
    to fifteen the glow's gradient becomes stepped; it shows and it is
    declared.
    """
    from port import image_stage
    a = image_stage.picture(path, p[7], p[6], p[2], p[3],
                            (RM_WIDTH, RM_HEIGHT), (WIDTH, HEIGHT), COLORS)
    return {
        "x": a["x"], "y": a["y"], "ancho": a["width"], "alto": a["height"],
        "objetos": -(-a["width"] // OBJ),
        "paleta": [tuple(c) for c in a["palette"]],
        "indices": a["indices"],
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


def report(info):
    """The numbers that justify the layout, for the recipe to print."""
    return {
        "donde": (info["x"], info["y"]),
        "tamano": (info["ancho"], info["alto"]),
        "objetos": info["objetos"],
        "tiles": reserved_tiles(info),
        "colores": len(info["paleta"]),
    }

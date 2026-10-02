#!/usr/bin/env python3
"""The pictures of `ShowPicture` on the console screen: which ones each map
carries, and how.

It lives apart from `snes_convert.py` for the same reason as the title: a
picture is not a map. It is a loose image that has to be put on the screen,
and what has to be decided is **exactly where each pixel lands and what
color it is**, and where in the console it lives.

**They go in OAM objects, not in a layer**, the plane of the sprites. In
mode 3 both layers belong to the map, and lending one to a picture while it
lasts forces reloading the map when erasing it: 30 KB of DMA and two black
frames, which is what `back_to_map` costs. That is for the big ones, with
the map hidden —`decisiones/las-imagenes-grandes-en-modo-1.md`—; the small
ones over the map go here. With objects the picture is put up and taken
down without touching anything underneath, which is also what RM2k does.
The price is **fifteen colors**, those of a sprite palette, and the
per-line object budget.

**Per map**: a picture's tiles go into the sprite bank of the map that
shows it, after its characters, and are uploaded with the bank. So the map
has to have room for them —its VRAM layout and its palettes— and `wally`
says whether it did; the one that did not is accepted without being done.
The scan of the event compiler says which pictures each map's pages and
test pages can show, in the order they are met.

**Two slots**: the console keeps up to `SLOTS` pictures at a time, one per
RM2k picture number —the first numbers a map shows, in order—, each with
a sprite palette of its own from the last one down, because the picture's
fade tints its fifteen colors and no other drawing can share them. It is
what the game's pictures over the map ask for: the most any of its scenes
shows at once is the counter's label and its two digits, and the digits are
the counter's.

**RM2k's screen is 320x240 and the console's 256x224**, so a picture that
goes with the screen is scaled like the title image: the two corners of its
rectangle go through the same math. **One that goes with the map is not**:
the map is not scaled, its tiles are sixteen pixels on both, and the
picture is part of it —the smoke out of a chimney, a shadow on the ground—.
Only its zoom shrinks it.

**RM2k's position is the center of the image**, not its corner:
`Sprite_Picture` does `SetOx(width / 2)`. The "One year previously" picture
is centered at (100, 175) of 320x240 and measures 233x31, so **it starts at
-16 and its left edge gets cut off**. That is not our bug: it is what the
game shows. The console computes the corner when it shows the picture, from
the center and half the picture's size in RM2k's pixels: a picture placed
by variables does not know its place until then.
"""

import os

from PIL import Image

# RM2k's screen and the console's.
RM_WIDTH, RM_HEIGHT = 320, 240
WIDTH, HEIGHT = 256, 224

# This port's large object, which `OBSEL_VALUE` fixes at 32x32.
OBJ = 32
# The 8x8 tiles it measures on a side, and how many there are in a row of the
# OAM name grid.
OBJ_SIDE = OBJ // 8
GRID = 16
# A row of blocks of the name grid, in tiles: four objects side by side.
BLOCK_ROW = 4 * GRID
# The fifteen of a sprite palette: index 0 is not drawn.
COLORS = 15
# How many pictures the console keeps at a time: `PIC_SLOTS` in the
# runtime's `picture.s`. Each takes a sprite palette.
SLOTS = 2
# The biggest picture the plane of objects takes: half the 512 tiles the
# PPU names —256x128— and no more, so a map's characters keep the other
# half. The bigger ones are the plane of the background's.
WIDTH_MAX, HEIGHT_MAX = 256, 128


def zoomed(side, zoom):
    """`zoom` percent of `side`, rounded and never under one: what
    `rm2k-snes-images` does."""
    return max(1, (side * zoom + 50) // 100)


def path_of(game_dir, name):
    """The file of the `ShowPicture` picture `name`, or None if the game
    does not have it."""
    path = os.path.abspath(os.path.join(game_dir, "Picture", name + ".png"))
    return path if os.path.exists(path) else None


def convert(path, key):
    """The picture of the file at `path`, as the `ShowPicture` that `key`
    describes shows it —see `PictureKey` in the event compiler—.

    Returns a dictionary with where it lands —`x`, `y`, `ancho`, `alto`; for
    one with the map, relative to its center—, half its size in RM2k's
    pixels, its palette of fifteen 15-bit colors and the image as indices
    into that palette **shifted by one**, which is how a sprite palette
    numbers them: 0 is the transparent one and is not drawn.

    `rm2k-snes-images picture` does it: RM2k's drawing of the picture with
    its transparent color, the zoom, the scaling to the console's screen if
    it goes with it, and the colors, which are kept by use like the title
    screen's and for the same reason: it does not average, so it does not
    invent colors that would have to be quantized again.
    """
    from port import image_stage
    with Image.open(path) as image:
        width, height = image.size
    zw, zh = zoomed(width, key["zoom"]), zoomed(height, key["zoom"])
    if key["at"] is not None:
        cx, cy = key["at"]
    else:
        # Placed by variables, or with the map: converted with its corner on
        # the grid, which is where the size comes out exact.
        cx, cy = zw // 2, zh // 2
    a = image_stage.picture(path, key["transparent_color"], 0, cx, cy,
                            (RM_WIDTH, RM_HEIGHT), (WIDTH, HEIGHT), COLORS,
                            zoom=key["zoom"], map_fixed=key["map_fixed"])
    return {
        "x": a["x"], "y": a["y"], "ancho": a["width"], "alto": a["height"],
        "mitad": (zw // 2, zh // 2),
        "paleta": [tuple(c) for c in a["palette"]],
        "indices": a["indices"],
    }


def fits(info):
    """Whether the picture fits the plane of objects."""
    return (0 < info["ancho"] <= WIDTH_MAX and 0 < info["alto"] <= HEIGHT_MAX
            and info["paleta"])


def objects(info):
    """The picture cut into 32x32 objects, row by row, leaving out the ones
    with nothing drawn: `[(dx, dy, cells)]`, with `cells` the sixteen 8x8
    cells of the object, row by row. What falls outside the image —the
    padding up to the object's 32— is index 0, transparent."""
    out = []
    indices = info["indices"]
    for oy in range(0, info["alto"], OBJ):
        for ox in range(0, info["ancho"], OBJ):
            cells = []
            for ty in range(OBJ_SIDE):
                for tx in range(OBJ_SIDE):
                    cell = []
                    for py in range(8):
                        y = oy + ty * 8 + py
                        row = []
                        for px in range(8):
                            x = ox + tx * 8 + px
                            row.append(indices[y][x]
                                       if y < info["alto"]
                                       and x < info["ancho"] else 0)
                        cell.append(row)
                    cells.append(cell)
            if any(v for cell in cells for row in cell for v in row):
                out.append((ox, oy, cells))
    return out


def block_tile(block):
    """The first tile of object `block` of the pictures, from their base.

    A 32x32 object reads four tiles from four consecutive rows of the name
    grid, which is sixteen wide: so a **row of blocks** —64 tiles— fits four
    objects and no more. Object `k` therefore starts at
    `(k // 4) * 64 + (k % 4) * 4`, and inside it tile (tx, ty) is `ty` grid
    rows further on. `picture_oam` does the same sum.
    """
    return (block // 4) * (4 * GRID) + (block % 4) * OBJ_SIDE


def for_map(game_dir, keys, map_id):
    """What a map carries of the pictures the scan says it can show —`keys`,
    in its order—: `(asked, table, images)`, or None if it carries none.

    * `asked` is what `wally` reserves in the sprite bank: every picture's
      objects one after the other, as cells from the base, and how many
      slots, each a palette;
    * `table` is what the event compiler numbers against: each picture
      that went in, with its slot;
    * `images` is what the emission writes for the console: each one's
      half size, its objects and its colors.

    A picture whose file is missing, that does not fit the plane, or whose
    number is past the console's slots, is left out, and its commands are
    accepted without being done.
    """
    slots = {}
    table, images, cells, names = [], [], [], []
    block = 0
    for key in keys:
        number = key["number"]
        if number not in slots:
            if len(slots) == SLOTS:
                print("  map %d: the picture %r (number %d) doesn't go in: the "
                      "console keeps %d at a time" % (map_id, key["name"], number,
                                                      SLOTS))
                continue
            slots[number] = len(slots)
        path = path_of(game_dir, key["name"])
        if path is None:
            continue
        info = convert(path, key)
        if not fits(info):
            print("  map %d: the picture %r is %dx%d on the console: bigger than the "
                  "plane of objects" % (map_id, key["name"], info["ancho"],
                                        info["alto"]))
            continue
        if key["at"] is not None:
            # The corner the console computes from the center and the half
            # size —`pic_show`— has to be the one the picture was converted
            # at: the same floor of four fifths and fourteen fifteenths.
            cx, cy = key["at"]
            hw, hh = info["mitad"]
            assert (info["x"], info["y"]) == (
                (cx - hw) * WIDTH // RM_WIDTH, (cy - hh) * HEIGHT // RM_HEIGHT
            ), (key, info["x"], info["y"])
        cut = objects(info)
        first = block
        for _dx, _dy, object_cells in cut:
            start = block_tile(block)
            for k, cell in enumerate(object_cells):
                tile = start + (k // OBJ_SIDE) * GRID + k % OBJ_SIDE
                cells.append([tile, [v for row in cell for v in row]])
            block += 1
        table.append(dict(key, slot=slots[number]))
        images.append({
            "half": list(info["mitad"]),
            "first": first,
            "objects": [[dx, dy] for dx, dy, _c in cut],
            "palette": [list(c) for c in info["paleta"]],
        })
        names.append(key["name"])
    if not table:
        return None
    asked = {
        "name": ", ".join(names),
        "objects": block,
        "tiles": -(-block // 4) * BLOCK_ROW,
        "cells": cells,
        "slots": max(t["slot"] for t in table) + 1,
    }
    return asked, table, images

#!/usr/bin/env python3
"""The **drawing** of a battle animation over the map.

It lives apart from `snes_convert.py` for the same reason as `picture.py`: it
is not a map. It is a loose drawing that has to be put on the screen, and
the only thing to decide is **exactly where each pixel lands and what color
it is**. The sounds and flashes of the same animation are not here: those
are `OP_ANIMATION` in `events.py`, and they exist since 2026-09-11.

**RM2k's part of the drawing is `rm2k-render battle-animation`'s**, since
2026-09-30: which cells each frame has, cut from the sheet, zoomed, faded,
and where they go in the animation's box. What is left here is the port's:
toning each cell —with the console's tint, see `_paint_frame`— and stacking
them, and everything after that.

The budget, which is where everything else comes from:

* The sprite VRAM a map has left free is **101 tiles on map 2 and 162 on
  map 3**, which are the two worst of those that show animations. A 96x96
  box is 144 tiles and does not fit on map 2.
* A 32x32 object reads four tiles from four consecutive rows of the name
  grid, so **a row of blocks is 64 tiles and four objects**, not one more.
  Four objects in two by two are 64x64 pixels.
* One of those frames is 2 KB of DMA, and one goes up every two console
  frames, which is how long an animation frame lasts in RM2k.

From there comes **the 64x64 box, the same for the whole ROM**. It is not
for convenience: the box not depending on the map is what lets the game's
388 `ShowBattleAnimation` across 81 maps share the frames already converted
in the cartridge instead of emitting one copy per map.

And from there also comes what taro accepted on 2026-09-12 —*"we should be
able to pull it off if we shrink some of the effects"*—: **the animation is
shrunk whole until it fits in the box**, keeping its proportions, and how
much it was shrunk is reported by the converter animation by animation. The
small ones are barely touched —a 96x96 one ends up at 64x64, 67%— and the
big ones from the intro are: number 82 measures 536x416 and ends up at
64x49, 11%. Nothing is drawn wrong silently: the criterion is a computation,
`fit_size`, and it is the one `test_parches.py` enforces.

What is lost, and it is declared in
`workflow/divergencias/la-animacion-de-batalla-achicada.md`:

* **A cell's transparency does not exist.** A console object is opaque or it
  is not there. What is done is to composite the cells with their alpha in
  the frame and then **round the alpha**: a pixel at 128 or more stays, the
  rest does not. A cell that fades out disappears when it passes the half,
  instead of going away gradually.
* **The animation is not tinted by the screen tint nor reached by the
  flash.** The first is faithful: `Spriteset_Map::Update` sets the tone on
  the tilemap, the characters, the panorama and the shadows, and not on the
  animations. The second is debt, the same the picture already has: its
  palette lands above `SPRITE_CGRAM`.
* **A target without an NPC row, or with the row hidden, gets no
  animation.** On the console there is nowhere to get its position from; in
  RM2k the animation is drawn anyway over an invisible event.
* **`global` —the one RM2k repeats three by three to cover the screen— is
  not drawn.** None of the eleven in the intro asks for it.
"""

# The box, and the 32x32 objects it is drawn with.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
BOX = 64
OBJ = 32
OBJ_SIDE = OBJ // 8
GRID = 16                 # tiles per row of the OAM name grid
OBJECTS = (BOX // OBJ) ** 2
TILES = 4 * GRID          # one row of blocks: the four objects
COLORS = 15

# `character_height` of `BattleAnimationMap::DrawSingle`, and the center of
# RM2k's screen, which is where those with "screen" scope land.
CHARACTER_HEIGHT = 24
RM_SCREEN = (320, 240)
SCREEN = (256, 224)

# The three values of `Animation::Position`, which is what shifts the
# animation up or down from the target.
POS_TOP, POS_CENTER, POS_BOTTOM = 0, 1, 2
SCOPE_SCREEN = 1        # `Animation::Scope_screen`

# The alpha from which a pixel is drawn. Half, rounding up: a pixel that is
# half and half stays.
ALPHA_MIN = 128

_CACHE = {}


def sheet_file(renderer, anim):
    """The path of this animation's `Battle` sheet, or None if it has none
    or it is not there."""
    from rpgmaker import resources
    name = anim.get("imagen") or ""
    if not name:
        return None
    folder = "Battle2" if anim.get("grande") else "Battle"
    return resources.find_resource(renderer.search_dirs, folder, name)


def _request(anim, sheet):
    """An entry of `rm2k-render battle-animation`: the sheet and the
    animation, named as in the dump. The cells go in the LDB's order, which
    is the order they are stacked in."""
    return {"sheet_file": sheet,
            "animation": {
                "large": bool(anim.get("grande")),
                "frames": [{"cells": [c for _k, c in sorted(
                    (frame or {}).items())]}
                           for frame in anim["cuadros"]]}}


def draw(wanted):
    """The cells of each animation of `wanted` —`(anim, sheet)` pairs—, with
    one call to `rm2k-render battle-animation`: for each one, `(box,
    frames)`, where `box` is `(x0, y0, width, height)` relative to the
    anchor, or None if it has no cell, and each frame is a list of
    `(image, (x, y), tone)`, the cells in the order they are stacked.

    Cutting the cells, zooming and fading them and where they go in the box
    is RM2k's drawing, and `rm2k-render` does it. **The tone is not**: see
    `_paint_frame`.
    """
    import json
    import os
    import subprocess
    import tempfile
    from PIL import Image
    from render import render_map
    if not wanted:
        return []
    with tempfile.TemporaryDirectory(prefix="rm2k-render-") as out:
        request_path = os.path.join(out, "animations.json")
        with open(request_path, "w", encoding="utf-8") as f:
            json.dump([_request(anim, sheet) for anim, sheet in wanted], f)
        cells_dir = os.path.join(out, "cells")
        done = subprocess.run(
            [render_map.binary(), "battle-animation", "--request",
             request_path, "--out", cells_dir],
            capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit("rm2k-render could not draw the battle "
                             "animations:\n%s" % done.stderr.strip())
        drawn = []
        for i in range(len(wanted)):
            with open(os.path.join(cells_dir, "%d.json" % i),
                      encoding="utf-8") as f:
                listed = json.load(f)
            frames = []
            for k, cells in enumerate(listed["frames"]):
                frame = []
                for c, cell in enumerate(cells):
                    path = os.path.join(cells_dir, "%d-%d-%d.png" % (i, k, c))
                    # `convert` reads it now, before the directory goes away.
                    with Image.open(path) as image:
                        frame.append((image.convert("RGBA"),
                                      (cell["x"], cell["y"]),
                                      tuple(cell["tone"])))
                frames.append(frame)
            box = listed["box"]
            drawn.append((tuple(box) if box else None, frames))
    return drawn


def fit_size(width, height):
    """The size an animation of `width` x `height` is shrunk to in order to
    fit in the box, keeping its proportions.

    The denominator is the side that overflows the most, and never less than
    the box: an animation that already fits is not enlarged. Done with
    integers.
    """
    den = max(width, height, BOX)
    return max(1, width * BOX // den), max(1, height * BOX // den)


def _paint_frame(cells, box):
    """A frame in RM2k pixels, the size of `box`, with alpha: the cells
    `rm2k-render` cut, zoomed and faded, each toned and stacked in order.

    **The tone is the port's**, and it is why the stacking is done here and
    not in `rm2k-render`: RM2k tones each cell before stacking it, and here
    the tone is the console's, on fifteen bits —see `_tint`—. A viewer on a
    PC would tone at eight.
    """
    from PIL import Image
    _x0, _y0, width, height = box
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for piece, where, hue in cells:
        if hue != (100, 100, 100, 100):
            piece = _tint(piece, hue)
        canvas.alpha_composite(piece, where)
    return canvas


def _tint(piece, hue):
    """The tone of a cell, with the same math as the screen tint.

    `color.apply_tint` works on the console's fifteen bits, which is where the
    comparison looks: tinting the PNG's eight and truncating afterwards would
    give a different number from the screen tint's on the same color.
    """
    from port.color import apply_tint
    from PIL import Image
    out = Image.new("RGBA", piece.size)
    memo = {}
    data = []
    for r, g, b, a in piece.convert("RGBA").get_flattened_data():
        key = (r >> 3, g >> 3, b >> 3)
        if key not in memo:
            p = apply_tint(key[0] | (key[1] << 5) | (key[2] << 10),
                              hue)
            memo[key] = ((p & 0x1F) << 3, ((p >> 5) & 0x1F) << 3,
                         ((p >> 10) & 0x1F) << 3)
        data.append(memo[key] + (a,))
    out.putdata(data)
    return out


def convert(anim, drawn):
    """The animation ready for both ends, or None if it cannot be drawn.

    `drawn` is what `draw` gave for it, or None if it has no sheet.
    Returns a dictionary with:

      `frames`  for each RM2k frame, the 64x64 box as palette indices
                 shifted by one: 0 is the console's transparent.
      `palette`   its fifteen 15-bit colors, chosen **over all the frames at
                 once**: the palette is uploaded only once at the start.
      `ancla`    where inside the box the point that RM2k puts over the
                 target lands. The ROM subtracts this from the target's
                 position and gets the corner of the box.
      `tam`      what it was shrunk to, and `caja_rm` what it came from.
    """
    if drawn is None or drawn[0] is None:
        return None
    from PIL import Image
    from port.palette import reduce
    box, cells = drawn
    x0, y0, width, height = box
    box_w, box_h = fit_size(width, height)
    ox, oy = (BOX - box_w) // 2, (BOX - box_h) // 2
    frames = []
    for frame_cells in cells:
        small = _paint_frame(frame_cells, box).resize(
            (box_w, box_h), Image.LANCZOS)
        whole = Image.new("RGBA", (BOX, BOX), (0, 0, 0, 0))
        whole.paste(small, (ox, oy))
        frames.append(whole)
    # The colors of all the frames together, down to fifteen.
    # `palette.reduce` does not average, so it does not invent a color that
    # would have to be quantized again.
    pixels = []
    for whole in frames:
        for r, g, b, a in whole.get_flattened_data():
            if a >= ALPHA_MIN:
                pixels.append((r >> 3, g >> 3, b >> 3))
    if not pixels:
        return None
    palette, mapping = reduce(pixels, COLORS)
    where = {color: i + 1 for i, color in enumerate(palette)}
    indices = []
    for whole in frames:
        data = whole.get_flattened_data()
        indices.append([
            [where[mapping[(data[y * BOX + x][0] >> 3,
                            data[y * BOX + x][1] >> 3,
                            data[y * BOX + x][2] >> 3)]]
             if data[y * BOX + x][3] >= ALPHA_MIN else 0
             for x in range(BOX)]
            for y in range(BOX)])
    return {
        "cuadros": indices,
        "paleta": palette,
        "ancla": (ox + (-x0) * box_w // width, oy + (-y0) * box_h // height),
        "tam": (box_w, box_h),
        "caja_rm": (width, height),
        "alcance": anim.get("alcance", 0),
        "posicion": anim.get("posicion", POS_CENTER),
    }


def by_numbers(renderer, numbers):
    """The animations `numbers` converted, `{number: info or None}`, cached
    per process.

    Converting one is a handful of large `resize`s, and the converter asks
    for it once per map that shows it. The ones not converted yet are drawn
    with a single call to `rm2k-render`.
    """
    from port import events
    new = sorted(set(numbers) - set(_CACHE))
    wanted = []
    for number in new:
        anim = events.ANIMATIONS.get(number)
        sheet = sheet_file(renderer, anim) if anim else None
        if sheet is None:
            _CACHE[number] = None
        else:
            wanted.append((number, anim, sheet))
    drawn = draw([(anim, sheet) for _n, anim, sheet in wanted])
    for (number, anim, _sheet), one in zip(wanted, drawn):
        _CACHE[number] = convert(anim, one)
    return {number: _CACHE[number] for number in numbers}


def by_number(renderer, number):
    """Animation `number` converted: see `by_numbers`."""
    return by_numbers(renderer, [number])[number]


def rom_anchor(info):
    """The anchor as the ROM's table carries it: (ax, ay).

    The vertical shift of `Animation::Position` is baked into it, since it
    is fixed per animation, so the console only has to subtract. With
    "screen" scope there is no shift: `DrawSingle` draws at the center
    without asking the target anything.
    """
    ax, ay = info["ancla"]
    if info["alcance"] == SCOPE_SCREEN:
        return ax, ay
    run = {POS_TOP: -(CHARACTER_HEIGHT // 2), POS_CENTER: 0,
           POS_BOTTOM: CHARACTER_HEIGHT // 2}[info["posicion"]]
    return ax, ay + CHARACTER_HEIGHT // 2 - run


def cells(frame):
    """A frame cut into 8x8 tiles, in the order OAM numbers them.

    The four objects fit in one row of blocks —64 tiles— and object `o`
    starts at `o * 4`; inside it, tile (tx, ty) is `ty` grid rows further
    on. It is the same arithmetic as `picture.cells`, which is where it came
    from.

    On screen the objects go two by two: `o` at `(o % 2 * 32, o // 2 * 32)`
    of the box.
    """
    out = {}
    for o in range(OBJECTS):
        start = (o % 4) * OBJ_SIDE
        base_x, base_y = (o % 2) * OBJ, (o // 2) * OBJ
        for ty in range(OBJ_SIDE):
            for tx in range(OBJ_SIDE):
                cell = tuple(
                    tuple(frame[base_y + ty * 8 + py][base_x + tx * 8 + px]
                          for px in range(8))
                    for py in range(8))
                out[start + ty * GRID + tx] = cell
    return out


def render(info, frame):
    """The frame as it looks on screen: a 64x64 RGBA image to paste wherever
    `ancla_en_pantalla` says."""
    from PIL import Image
    colors = [(0, 0, 0, 0)] + [(r << 3, g << 3, b << 3, 255)
                               for r, g, b in info["paleta"]]
    out = Image.new("RGBA", (BOX, BOX))
    out.putdata([colors[i] for row in info["cuadros"][frame]
                 for i in row])
    return out


def report(number, info):
    """The numbers that justify the layout, for the recipe to print."""
    width, height = info["caja_rm"]
    box_w, box_h = info["tam"]
    return {
        "animacion": number,
        "cuadros": len(info["cuadros"]),
        "original": (width, height),
        "caja": (box_w, box_h),
        "porciento": 100 * box_w // width,
        "colores": len(info["paleta"]),
        "bytes": len(info["cuadros"]) * TILES * 32,
    }

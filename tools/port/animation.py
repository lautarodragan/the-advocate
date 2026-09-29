#!/usr/bin/env python3
"""The **drawing** of a battle animation over the map.

It lives apart from `snes_convert.py` for the same reason as `imagen.py`: it
is not a map. It is a loose drawing that has to be put on the screen, and
the only thing to decide is **exactly where each pixel lands and what color
it is**. The sounds and flashes of the same animation are not here: those
are `OP_ANIMATION` in `events.py`, and they exist since 2026-09-11.

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

# The `Battle` sheet: five cells per row, of 96x96 —or 128x128 if the
# animation is `large`, which none is in ABL—. It is the `size` of
# `BattleAnimation::DrawAt`.
CELL = 96
BIG_CELL = 128
COLUMNS = 5

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


def sheet_of(renderer, anim):
    """The `Battle` sheet of this animation, or None if it has none or it is
    not there."""
    from render import render_map
    from rpgmaker import resources
    name = anim.get("imagen") or ""
    if not name:
        return None
    folder = "Battle2" if anim.get("grande") else "Battle"
    path = resources.find_resource(renderer.search_dirs, folder, name)
    return render_map.load_image(path) if path else None


def _live_cells(anim, i):
    """The valid cells of frame `i`, in the LDB's order.

    `valid` defaults to 1 —liblcf, `AnimationCellData`— so a cell without the
    field counts. The invalid ones are the holes the editor leaves when a
    cell in the middle is deleted.
    """
    return [c for _k, c in sorted((anim["cuadros"][i] or {}).items())
            if c.get("valid", 1)]


def _side(anim, cell):
    """How big a cell is on screen with its zoom, in RM2k pixels."""
    side = BIG_CELL if anim.get("grande") else CELL
    return max(1, side * cell.get("zoom", 100) // 100)


def rm_box(anim):
    """The rectangle the whole animation takes in RM2k pixels, relative to
    its anchor: (x0, y0, ancho, alto).

    It is the union of all the cells of all the frames, not that of the
    biggest frame: the console box is a single one for the whole animation,
    so a frame that shifts to one side has to fit all the same.
    """
    x0 = y0 = None
    x1 = y1 = None
    for i in range(len(anim["cuadros"])):
        for cell in _live_cells(anim, i):
            side = _side(anim, cell)
            cx, cy = cell.get("x", 0), cell.get("y", 0)
            a, b = cx - side // 2, cy - side // 2
            x0 = a if x0 is None else min(x0, a)
            y0 = b if y0 is None else min(y0, b)
            x1 = a + side if x1 is None else max(x1, a + side)
            y1 = b + side if y1 is None else max(y1, b + side)
    if x0 is None:
        return None
    return x0, y0, x1 - x0, y1 - y0


def fit_size(width, height):
    """The size an animation of `width` x `height` is shrunk to in order to
    fit in the box, keeping its proportions.

    The denominator is the side that overflows the most, and never less than
    the box: an animation that already fits is not enlarged. Done with
    integers.
    """
    den = max(width, height, BOX)
    return max(1, width * BOX // den), max(1, height * BOX // den)


def _paint_frame(anim, sheet, i, box):
    """A frame in RM2k pixels, the size of `box`, with alpha.

    It is `BattleAnimation::DrawAt` without the screen: each cell comes from
    the sheet, is scaled by its zoom, gets its tone and transparency applied,
    and is composited centered at its (x, y).
    """
    from PIL import Image
    from port import events
    x0, y0, width, height = box
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sheet_side = BIG_CELL if anim.get("grande") else CELL
    for cell in _live_cells(anim, i):
        cid = cell.get("cell_id", 0)
        sx, sy = (cid % COLUMNS) * sheet_side, (cid // COLUMNS) * sheet_side
        if sx + sheet_side > sheet.width or sy + sheet_side > sheet.height:
            continue            # a cell the sheet does not have: RM2k draws nothing
        piece = sheet.crop((sx, sy, sx + sheet_side, sy + sheet_side))
        side = _side(anim, cell)
        if side != sheet_side:
            piece = piece.resize((side, side), Image.BILINEAR)
        hue = (cell.get("tone_red", 100), cell.get("tone_green", 100),
               cell.get("tone_blue", 100), cell.get("tone_gray", 100))
        if hue != (100, 100, 100, 100):
            piece = _tint(piece, hue)
        opacity = 100 - max(0, min(100, cell.get("transparency", 0)))
        if opacity != 100:
            alpha = piece.getchannel("A").point(
                lambda v: v * opacity // 100)
            piece.putalpha(alpha)
        canvas.alpha_composite(
            piece, (cell.get("x", 0) - side // 2 - x0,
                    cell.get("y", 0) - side // 2 - y0))
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


def convert(anim, sheet):
    """The animation ready for both ends, or None if it cannot be drawn.

    Returns a dictionary with:

      `frames`  for each RM2k frame, the 64x64 box as palette indices
                 shifted by one: 0 is the console's transparent.
      `palette`   its fifteen 15-bit colors, chosen **over all the frames at
                 once**: the palette is uploaded only once at the start.
      `ancla`    where inside the box the point that RM2k puts over the
                 target lands. The ROM subtracts this from the target's
                 position and gets the corner of the box.
      `tam`      what it was shrunk to, and `rm_box` what it came from.
    """
    box = rm_box(anim)
    if box is None or sheet is None:
        return None
    from PIL import Image
    from port.palette import reduce
    x0, y0, width, height = box
    box_w, box_h = fit_size(width, height)
    ox, oy = (BOX - box_w) // 2, (BOX - box_h) // 2
    frames = []
    for i in range(len(anim["cuadros"])):
        small = _paint_frame(anim, sheet, i, box).resize(
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


def by_number(renderer, number):
    """Animation `number` converted, cached per process.

    Converting one is a handful of large `resize`s, and the converter asks
    for it once per map that shows it.
    """
    from port import events
    if number in _CACHE:
        return _CACHE[number]
    anim = events.ANIMATIONS.get(number)
    out = convert(anim, sheet_of(renderer, anim)) if anim else None
    _CACHE[number] = out
    return out


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

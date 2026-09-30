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


def fit_size(width, height):
    """The size an animation of `width` x `height` is shrunk to in order to
    fit in the box, keeping its proportions.

    The denominator is the side that overflows the most, and never less than
    the box: an animation that already fits is not enlarged. Done with
    integers.
    """
    den = max(width, height, BOX)
    return max(1, width * BOX // den), max(1, height * BOX // den)


def by_numbers(renderer, numbers):
    """The animations `numbers` converted, `{number: info or None}`, cached
    per process.

    Converting one is a handful of large `resize`s, and the converter asks
    for it once per map that shows it. The ones not converted yet are
    converted with a single call to `rm2k-snes-images animations`, which
    reads each animation from the game's dump and does all of `convert`:
    RM2k's cells, toned, stacked, shrunk into the box and reduced.
    """
    from port import events, image_stage
    new = sorted(set(numbers) - set(_CACHE))
    wanted = []
    for number in new:
        anim = events.ANIMATIONS.get(number)
        sheet = sheet_file(renderer, anim) if anim else None
        if sheet is None:
            _CACHE[number] = None
        else:
            wanted.append((number, anim, sheet))
    answers = image_stage.animations(
        [(number, sheet) for number, _anim, sheet in wanted],
        renderer.game_dir)
    for (number, anim, _sheet), a in zip(wanted, answers):
        _CACHE[number] = a and {
            "cuadros": a["frames"],
            "paleta": [tuple(c) for c in a["palette"]],
            "ancla": tuple(a["anchor"]),
            "tam": tuple(a["size"]),
            "caja_rm": tuple(a["rm_box"]),
            "alcance": anim.get("alcance", 0),
            "posicion": anim.get("posicion", POS_CENTER),
        }
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

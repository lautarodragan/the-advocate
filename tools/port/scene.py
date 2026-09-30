#!/usr/bin/env python3
"""The battle scene: the backdrop and the monsters, **composited on the console**.

It lives apart from `snes_convert.py` for the same reason as `picture.py` and
`animation.py`: it is not a map, it is a loose drawing. What the converter
and the ROM have to share is exactly where each pixel lands and what color
it is.

taro asked for both things on 2026-09-13 —*"The battle has neither a
background image nor a monster image"*— and until 2026-09-21 they were baked
together: a 32 KB image **per troop**, with the backdrop and the battlers
already on top. That multiplied images per combination —six in `abl`, over
four backdrops— and a dead enemy was still visible. Since that day, taro's
idea, the cartridge carries **each backdrop once and each battler once**,
and the console composites them when the battle starts. See `scene_upload`
in tools/runtime/battle_scene.s.

It is still a single 8bpp layer on BG1, and that is what buys the same as
before:

* **The screen does not have to be redone.** The 32x28 text grid is full
  —eight enemies, four actors and two message lines— and a monster drawn
  with objects would require taking something out. On the backdrop, the
  text is still visible on top.
* **There are no objects**: no OAM to build and no 34-tiles-per-line limit,
  which with four 64-pixel-wide battlers was at 32 with no margin.

The pictures as RM2k draws them —the backdrop opaque, the battler with its
color key and turned by its `battler_hue`— are `rm2k-render`'s, and
everything from there on is the console's: since 2026-09-30 both are done
by `rm2k-snes-images`, which draws with `rm2k-render` as a library. See
`backdrops` and `battlers`.

## How a battler is overlaid

The SNES 8bpp is **planar**: each row of a tile is eight bytes, one per
bitplane, and planes 0/1, 2/3, 4/5 and 6/7 are interleaved in pairs. So
putting a battler over the backdrop is, per byte of each plane,
`backdrop AND NOT mask OR battler`, without touching pixel by pixel.

Each battler has **15 colors plus transparent**. Its low 4 bits come from
its drawing —index 0 is the transparent one, which is the mask— and its high
4 bits are **the palette it gets in this battle**: the ROM picks it at the
start, the troop's first distinct battler on palette 8, the second on 9, and
so on. Planes 4 to 7 are not stored: they are the mask or zero, depending on
the palette's bits. That is why the same battler serves any troop without
preparing anything per combination.

That they are fifteen colors **is an artistic decision**: color is lost
compared with the baked scene, where the battlers shared the 96 entries with
the backdrop. What was merged with what is written per battler in
`rom/parches/auto/battlers/`, like the map layers. See
`rm2k-snes-patches`, in `tools/rm2k-snes/patches/`.

The edge changes too: before, the battler blended with the backdrop when
shrunk —`alpha_composite`— and now each pixel is either the battler's or the
backdrop's, with the cut at half the alpha. It is the cost of not preparing
anything per troop.

## The geometry

RM2k's battle backdrop is 320x160 and is drawn at the very top of a 320x240
screen. Here the screen is 256x224, so the backdrop goes in scaled to
**80%**: 256x128, which are the top seven text lines. The battlers go at the
same 80%, so the troop positions —which in the LDB are the center of each
battler, in 320x240 coordinates— map by multiplying by the same and no other
math.

The only thing that is not RM2k's is **the clipping**: a tall battler goes
past the scene's 128 pixels, so its corner is clamped inside. In RM2k it
does not go past because it has another eighty pixels of screen below.

## The budget

* **512 tiles at 8bpp, 32,768 B of VRAM**, which is exactly the 32x16 grid
  without deduplicating. A photo does not repeat, and compositing on top
  would make it repeat even less.
* **The colors**: the backdrop carries 96, CGRAM entries 32 to 127 —0 to 31
  are the two text palettes—, and the battlers **the top eight palettes**,
  128 to 255. Those are the map objects' ones, and the battle draws no
  objects; returning to the map did not restore them whole —the picture and
  the battle animation are uploaded only when they change—, so now
  `back_from_battle` uploads the 128 from `cgram_shadow` before anything
  else.
* **WRAM**: the clean backdrop at `$7F0000` and the composited scene at
  `$7F8000`, 32 KB each. The clean one is what allows recompositing the
  cells of a dead enemy without reading anything from the cartridge again:
  see `scene_tick`.
* In the battle's VRAM everything fits without fighting anything: the battle
  screen **does not share VRAM with the map**, because `back_from_battle`
  redoes it entirely on the way out. The text tiles live at $2000, their
  tilemap at $3C00, the scene's at $3800 and the scene's tiles at $4000.

## Which backdrops there are, and which ones the cartridge carries

**The game's backdrops** are all the ones a battle can ask for: those named
by the `EnemyEncounter`s and the `ChangeBattleBG`s, those of the map tree and
those of the terrains —see `game_backdrops`—. Each one has a **number**,
its place in that list sorted by name, and the number does not depend on
which maps the cartridge carries: it is what gives each backdrop a fixed
place in the `.msu`, which carries **all** of them, in quality
(`msu_data.rs` in `rm2k-snes-audio`).

**The ROM carries, in the light fallback, all the ones the cartridge's
battles can ask for**: those a troop names, those of the maps with random
encounters and, if the map names none, those of the terrains its cells
stand on. taro asked for it on 2026-09-27, with the quality as low as needed
for them to fit: see "The light fallback". Until that day it carried three,
and the other battles used the replacement.

**The replacement**, `replacement()`, is left for what the ROM cannot know at
conversion time: a troop that fights with the "local" backdrop on a map
without random encounters, where the backdrop comes from the terrain under
the hero and any terrain of the map is possible. In `release` only test
pages do that. Not black, because "black is confusing", taro's words. With
MSU-1, each battle reads its own from the `.msu`, whether or not it is in
the ROM.

The flat backdrop —zeros, which is black— is left for the battle that has no
backdrop: an `EnemyEncounter` with an empty name, or a terrain without a
backdrop. It is the same as RM2k does, and it is the same code with the
backdrop at zero.

## The light fallback

And since that same day **they are not the same**: the `.msu` carries the
quality backdrop —8bpp, 96 colors, 32 KB— and the ROM one of **16 colors at
half resolution, 128x64 at 4bpp: 4 KB**, which the ROM doubles in size. It
is what someone playing without MSU-1 sees, and it can be told apart by eye
from the quality one, which is what taro asked for to know which side it
came from.

Until 2026-09-27 it was 256x128, 16 KB, and the ROM carried three. That day
taro asked that all the ones `release`'s maps ask for fit "with the quality
as low as it takes", and every option was measured —the figures and the
images, in `workflow/tasks/*/todos-los-fondos-en-la-rom.md`—: at 256x128,
not even with LZ2 do they fit without eating the banks the main path of the
world needs; with four colors at 2bpp the shades are lost; and deduplicating
tiles saves almost nothing, because a photo does not repeat. At 128x64 each
backdrop weighs a quarter, and the sixteen colors stay.

The layer is still **a single one at 8bpp**: the only thing that changes is
how the fallback travels. Its sixteen colors go in the `CGRAM_BASE` palette
—entries 32 to 47—, so at 8bpp its indices are `CGRAM_BASE + i` and planes
4 to 7 of all its pixels are the same: those of `CGRAM_BASE`. The ROM first
fills the two WRAM buffers with those fixed planes, by DMA, and then
doubles the small one with the CPU: each pixel twice across and each row
twice down. From there on everything is the same —compositing, erasing a
dead one, uploading to VRAM—, because what is left in WRAM is an 8bpp
backdrop like the `.msu` one. See `scn_fill` and `scn_double` in
tools/runtime/battle_scene.s, and `fallback_bytes` in battle_scenes.py for
the order the bytes travel in, which is the one that saves the ROM math.

The other way out was for the `.msu` to carry 4bpp too, "more quality within
the same format"; but sixteen colors are the ceiling of 4bpp, so the quality
would have nowhere to grow.

The sixteen come from `adeleine::merge_least_visible`, the battlers' one,
and not from `adeleine::keep_most_used`, which is the one that builds the
96: that one keeps the most used, and in a backdrop the sixteen most used are all from
the floor and the walls —the green sign and the violet water turned gray—.
Merging by what shows the least keeps the accents. The 96 did not change
reducer because they are the bytes of the `.msu`, and with them its
signature.
"""

import os

from common import settings

# The scene, in screen pixels: the top seven text lines.
WIDTH, HEIGHT = 256, 128
# RM2k's battle backdrop and the screen it lives on, where the 80% comes from.
RM_BACKDROP = (320, 160)
RM_SCREEN = (320, 240)
SCALE_NUM, SCALE_DEN = WIDTH, RM_BACKDROP[0]     # 256/320

# The backdrop's colors, and from which CGRAM entry they go. See "The
# budget".
COLORS = 96
CGRAM_BASE = 32
# Those of the light fallback, which goes at 4bpp: see "The light fallback".
# They fit in a palette of sixteen, and `CGRAM_BASE` has to be the start of
# one so that planes 4 to 7 are the same on all its pixels.
FALLBACK_COLORS = 16
FALLBACK_PLANES = 4
assert CGRAM_BASE % FALLBACK_COLORS == 0
# And it goes at half resolution: the ROM doubles each pixel across and down.
# `scn_double` is written for double and nothing else.
FALLBACK_SCALE = 2
FALLBACK_WIDTH = WIDTH // FALLBACK_SCALE
FALLBACK_HEIGHT = HEIGHT // FALLBACK_SCALE
# The battlers' palettes: 8 to 15, that is entries 128 to 255. One per
# distinct battler of the troop, and a troop has at most eight enemies, so
# there are always enough.
BATTLER_PALETTE = 8
BATTLER_PALETTES = 8
BATTLER_COLORS = 15
# The alpha from which a pixel of a shrunk battler is its: half, rounding
# up. A pixel is either the battler's or the backdrop's.
ALPHA_MIN = 128

CELL = 8
TILES_X, TILES_Y = WIDTH // CELL, HEIGHT // CELL
TILES = TILES_X * TILES_Y                       # 512, the whole grid

# Where it lives in VRAM, in words. The tilemap goes before the text's
# —$3C00— and the tiles after, which is the only 32 KB gap left.
VRAM_MAP = 0x3800
VRAM_TILES = 0x4000

def replacement():
    """The backdrop of the battles whose backdrop is not in the ROM: see
    "Which backdrops there are". The game chooses it, in
    `[battle] fallback_backdrop` of the project file, with its reason."""
    return settings.value("battle", "fallback_backdrop", kind=str)

# How many planes the cartridge stores per row of a battler: the mask and the
# four of its drawing. The ROM sets the other four according to the palette.
BATTLER_PLANES = 5


def scale(value):
    """An RM2k length in scene pixels. The same math on both sides, with
    integers: `//` would round differently from the hardware divider only
    with negatives, and there are none here."""
    return max(1, (value * SCALE_NUM + SCALE_DEN // 2) // SCALE_DEN)


def _file(game_dir, folder, name, rtp=False):
    """The file of a backdrop or a battler, or None if the game does not
    have it.

    With `rtp`, if the game does not have it, it is looked up in the RTP,
    like RM2k. Only the backdrops ask for it: thirteen of the game's are
    from the RTP —`Cave1`, `Castle`, the terrain ones—, and until 2026-09-27
    it was not needed because the ROM's three are the game's. The battlers
    still do not look there, so as not to change which ones get in without
    looking at it."""
    from rpgmaker import resources
    places = [game_dir] + ([resources.RTP_DIR] if rtp else [])
    path = resources.find_resource(places, folder, name,
                                   (".png", ".bmp", ".xyz"))
    return None if path is None else os.path.abspath(path)


# --- the backdrop -------------------------------------------------------------

def game_backdrops(named, tree, terrains, game_dir):
    """The game's backdrops, in the order that gives them their number: see
    "Which backdrops there are".

    `named` are the ones the commands name (`events.named_backdrops`),
    `tree` the map tree and `terrains` each terrain's backdrop
    (`Database.terrain_backdrops`). They are sorted by name ignoring case,
    which is how RM2k looks them up, and a name that is neither in the game
    nor in the RTP is left out: in RM2k that battle has no backdrop. Returns
    the names as the game writes them the first time, in that order.
    """
    from rpgmaker import resources
    every = set(named)
    every |= {name for kind, name in tree.background.values()
              if kind == 2 and name}
    every |= {name for name in terrains.values() if name}
    by_key = {}
    for name in sorted(every):
        by_key.setdefault(name.lower(), name)
    out = []
    for key in sorted(by_key):
        name = by_key[key]
        if resources.find_resource([game_dir, resources.RTP_DIR],
                                   "Backdrop", name,
                                   (".png", ".bmp", ".xyz")) is None:
            print("  backdrop %r is neither in the game nor in the RTP" % name)
            continue
        out.append(name)
    return out


def backdrop(name, game_dir):
    """A battle backdrop ready for the ROM, or None if it is not there.

      `indices`  256x128 CGRAM indices, row by row, already shifted by
                 `CGRAM_BASE`: it is what the console reads.
      `palette`   its `COLORS` 15-bit colors, from `CGRAM_BASE`.

    `rm2k-snes-images backdrops` does it —RM2k's drawing, opaque, scaled
    with LANCZOS and kept by use—; `backdrops` asks for several at once.
    """
    return backdrops([name], game_dir, light=False)[0][0]


def light_backdrop(name, game_dir):
    """The backdrop's fallback: the one that goes in the ROM, with
    `FALLBACK_COLORS` and at half resolution.

    The same image as `backdrop`, shrunk to `FALLBACK_WIDTH` x `FALLBACK_HEIGHT`
    and with sixteen colors merged by `adeleine::merge_least_visible`: see
    "The light fallback". The palette goes from most used to least, and on
    equal counts by color, so it always comes out the same.

      `small`    the fallback's CGRAM indices, at 128x64: what travels.
      `indices`  the same, doubled to 256x128 as the ROM leaves them in
                 WRAM: it is what the tests compare.
    """
    return backdrops([name], game_dir, quality=False)[0][1]


def backdrops(names, game_dir, quality=True, light=True):
    """`backdrop` and `light_backdrop` of each of `names`, with a single call
    to the stage: `(quality, light)` per name, None where the game does not
    have it or it was not asked for."""
    from port import image_stage
    paths = [_file(game_dir, "Backdrop", name, rtp=True) for name in names]
    found = [(p, quality, light) for p in paths if p is not None]
    answers = iter(image_stage.backdrops(found))
    out = []
    for name, path in zip(names, paths):
        if path is None:
            out.append((None, None))
            continue
        q, li = next(answers)
        out.append((
            q and {"nombre": name, "indices": q["indices"],
                   "paleta": [tuple(c) for c in q["palette"]]},
            li and {"nombre": name, "chico": li["small"],
                    "indices": li["indices"],
                    "paleta": [tuple(c) for c in li["palette"]]}))
    return out


def tiles(indices):
    """The 8x8 tiles of a grid —the 512 of a 256x128 one—, in the order the
    tilemap reads them: row by row, without deduplicating. See "The
    budget"."""
    out = []
    for ty in range(len(indices) // CELL):
        for tx in range(len(indices[0]) // CELL):
            out.append([[indices[ty * CELL + y][tx * CELL + x]
                         for x in range(CELL)] for y in range(CELL)])
    return out


# --- the battlers --------------------------------------------------------------

def key(name, hue):
    """What a battler is called in the cartridge and in `rom/parches/`: the
    image and its hue, which is what makes it different from another with
    the same image."""
    return "%s-%d" % (name, hue) if hue else name


def battler(name, hue, game_dir):
    """A battler ready for the ROM, or None if the image is not there.

      `width`, `height`  in scene pixels, already at 80%.
      `pixels`        row by row, from 0 to 15: 0 is the transparent one and
                       the others the color in `palette`, plus one.
      `palette`         its up to fifteen 15-bit colors.
      `colores`        how many distinct ones the drawing had, already
                       shrunk.
      `merges`       what was merged with what to get to fifteen, as
                       `adeleine::merge_least_visible` returns them.

    The enemy's `battler_hue` is what makes the same `BLmouse` be the
    GiantRat, the MutantMouse and the HairyVermin. The baked scene ignored
    it; now, with one battler per enemy and not per image, ignoring it would
    draw all three the same. `rm2k-snes-images battlers` does it —RM2k's
    drawing, turned by its hue, shrunk with LANCZOS, cut at half the alpha
    and merged by what shows the least—; `battlers` asks for several at
    once.
    """
    return battlers([(name, hue)], game_dir)[0]


def battlers(wanted, game_dir):
    """`battler` of each `(name, hue)` of `wanted`, with a single call to the
    stage."""
    from port import image_stage
    paths = [_file(game_dir, "Monster", name) for name, _hue in wanted]
    answers = iter(image_stage.battlers(
        [(p, hue) for p, (_n, hue) in zip(paths, wanted) if p is not None]))
    out = []
    for (name, hue), path in zip(wanted, paths):
        if path is None:
            out.append(None)
            continue
        a = next(answers)
        out.append({
            "clave": key(name, hue), "imagen": name, "tono": hue,
            "ancho": a["width"], "alto": a["height"], "pixeles": a["pixels"],
            "alto_rm": a["rm_height"],
            "paleta": [tuple(c) for c in a["palette"]],
            "colores": a["colors"],
            "fusiones": [(tuple(v), tuple(t), n) for v, t, n in a["merges"]]})
    return out


def columns(info):
    """How many bytes a row of a plane is: eight pixels per byte."""
    return (info["ancho"] + 7) // 8


def battler_bytes(info):
    """A battler in the format `scene_set` reads.

    **Plane by plane**, and within each plane row by row: the mask first and
    then the four planes of the drawing. Each row of a plane is
    `columnas + 1` bytes and goes **backwards**, the rightmost column first,
    with a zero in front:

        [0] [col n-1] ... [col 1] [col 0]

    That way a sixteen-bit read at column `k` brings `k` in the low byte and
    `k - 1` in the high one, which is exactly the word that has to be shifted
    right to place a battler that does not fall on a tile boundary. Column
    `-1` is the leading zero of the next row —or of the next plane—, so the
    ROM does not have to check for the edge; the last plane carries an extra
    zero at the end for the same reason.
    """
    n = columns(info)
    planes = []
    for plane in range(BATTLER_PLANES):
        data = bytearray()
        for row in info["pixeles"]:
            row_bytes = bytearray(n)
            for x, value in enumerate(row):
                lit = (value != 0) if plane == 0 else \
                    bool((value >> (plane - 1)) & 1)
                if lit:
                    row_bytes[x // 8] |= 0x80 >> (x % 8)
            data += bytes([0]) + bytes(reversed(row_bytes))
        planes.append(bytes(data))
    return b"".join(planes) + b"\x00"


def position(center, info):
    """Where a battler's corner lands in the scene, already clamped inside.

    The LDB position is **the center** of the battler, on RM2k's 320x240
    screen. It is scaled like everything else and clamped inside the scene:
    see "The geometry".
    """
    x, y = center
    px = min(max(scale(x) - info["ancho"] // 2, 0),
             max(0, WIDTH - info["ancho"]))
    py = min(max(scale(y) - info["alto"] // 2, 0),
             max(0, HEIGHT - info["alto"]))
    return px, py


def drawing_order(centers, infos):
    """The order a troop's enemies are placed in: the one that goes later
    covers.

    It is easyrpg's `Sprite_Battler::ResetZ`: the depth is the battler's
    bottom edge in RM2k —the LDB center plus half the PNG's height— and, on
    an equal edge, the one with the lower place in the troop ends up on top.
    `infos` may carry None for an enemy without a battler: it is not drawn,
    and it does not matter where it lands.
    """
    def z(k):
        height = infos[k]["alto_rm"] if infos[k] else 0
        return (centers[k][1] + height // 2, -k)
    return sorted(range(len(centers)), key=z)


def compose(backdrop_indices, placed):
    """The scene as the console composites it, in CGRAM indices.

    `backdrop_indices` is a backdrop's grid, or None for the flat backdrop.
    `placed` are `(info, paleta, x, y)` in the order the ROM places them,
    which is `drawing_order`: the one that goes later covers the one
    before. The converter does not use it —the ROM composites on its own—
    but the tests do, to know what has to be in each pixel.
    """
    scene = [list(row) if backdrop_indices else [0] * WIDTH
             for row in (backdrop_indices or [None] * HEIGHT)]
    for info, palette, px, py in placed:
        for y, row in enumerate(info["pixeles"]):
            for x, value in enumerate(row):
                if value and 0 <= py + y < HEIGHT and 0 <= px + x < WIDTH:
                    scene[py + y][px + x] = palette * 16 + value
    return scene


def battler_report(info):
    """The battler's numbers, for the converter to print."""
    return {"clave": info["clave"], "ancho": info["ancho"],
            "alto": info["alto"], "bytes": len(battler_bytes(info)),
            "colores": info["colores"], "quedan": len(info["paleta"])}

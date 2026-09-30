"""The map's two background layers in mode 3: how CGRAM is split between
them, the 15-bit quantization, the conversion with Voodoo, and the disk cache
of what comes out.

The input is the two layers already drawn —by `rm2k-render`, through
`render_map`— and the output, per layer, its tiles, its CGRAM words and its
tilemap.

Splitting colors into palettes, and merging the least used ones when they
don't fit, lives in `adeleine.py`, and reusing mirrored tiles in Voodoo.
What is left here is what depends on the hardware:

  * **Color is 15 bits, five per channel.** Of the 72 colors in the render of
    Map0007, 60 survive.
  * **The background goes in mode 3, at 8 bits per pixel.** There each pixel is
    a direct index into CGRAM and there is no per-tile palette, so the problem
    of splitting the colors into groups simply does not exist. With 4 bits and
    8 palettes, Map0007 lost 32 of its 60 colors; with 8 bits it loses none.

    It costs twice the VRAM per tile, 64 bytes instead of 32. With 92 tiles
    that is 5.8 KB of the 64 available, so it is not a real constraint.
  * **The tile format is planar**, not packed in nibbles: each bit of a pixel
    lives in a different bitmap, in pairs and 16 bytes at a time. That is why
    a 4-bit tile is exactly the first half of an 8-bit one.

Indices are kept to the lower half of CGRAM. Sprites always use palettes 8 to
15, that is indices 128 to 255, and at 8 bits the background reaches up to
255: staying low avoids stepping on them.
"""

import collections
import json
import os
import shutil

import numpy

from port import tiles_bin
from rpgmaker import rm2k
from port import adeleine
from port.adeleine import CELL, tile_colors
from port.snes_format import BYTES_PER_TILE, COLORS_PER_PALETTE
from render import render_map


# The PPU addresses 1024 tiles per layer: ten bits in each tilemap cell.
MAX_TILES = 1024

# CGRAM has 256 entries. The upper half belongs to the sprites; the lower half
# is shared by the background, which goes at 8 bits per pixel and addresses
# CGRAM directly, and the layer that goes above the hero, which goes at 4 bits
# and therefore counts its index within a palette of 16.
#
# Where the split between the two falls is not fixed: the converter decides it
# map by map, in _convert_layers(). With one palette above, the background has
# 111 colors; with three, 79. It used to be two always, and 27 maps didn't fit
# —the first three of the game among them— while the background left colors
# unused.
#
# The cap below is not a quality decision but the shape of the hardware: the
# background has to keep at least one palette. How many the upper layer really
# takes comes from what the background doesn't need.
BG_PALETTES = 8                          # the lower half of CGRAM, in palettes
MAX_ABOVE_PALETTES = BG_PALETTES - 1


def above_split(palettes):
    """Which palette the upper layer starts at if it takes this many."""
    return BG_PALETTES - palettes


# The CGRAM entries the background **cannot** use, at the very bottom: entry 0,
# which is the screen's backdrop color, and the seven of the message window.
#
# The window goes in **palette 0** and not floating below the upper layer, and
# that is what gives the background back everything that used to be thrown
# away. BG1 goes at 8 bits per pixel and addresses CGRAM directly: it doesn't
# need palettes of 16, it is enough that nobody steps on its entries. With the
# window at the very bottom, the background is contiguous from 8 up to where
# the upper layer starts, with no gaps.
#
# The window used to go in the lowest palette of the whole ROM —`paleta_de_la
# ventana`— and the background got only the block below. In the opening ROM
# that left it at 47 colors while palettes 4, 5 and 6 were used by **nobody**:
# 57 entries thrown away in map 7. The nine maps of the PoC merged 97 colors
# among them and now they merge 8.
#
# And there is a property that comes for free from putting it at the bottom:
# `apply_tint` tints from where the background starts, so the window is
# outside the range without anyone having to remember. In RM2k the tone is
# applied to the map and not to the window.
# **Eight and not seven.** Counting them with `sum(1 for w in cram if w)` gives
# seven because one of the window colors is pure black and its CGRAM word is
# zero. With seven, the ROM drew the text with a color nobody had uploaded and
# the suite caught 79 pixels in the text lines. What rules is the highest
# index the window uses, and `convert_window` makes sure of that.
WINDOW_COLORS = 8
CGRAM_RESERVED = 1 + WINDOW_COLORS


def bg_budget(first):
    """The colors left for the background below the upper layer.

    The ones at the very bottom don't count: the screen's backdrop color and
    the ones of the message window. See `CGRAM_RESERVED`.
    """
    return first * COLORS_PER_PALETTE - CGRAM_RESERVED


# The priority order of mode 3, from front to back, is:
#
#     objects 3 / BG1 1 / objects 2 / BG2 1 / objects 1 / BG1 0 / objects 0
#
# which is exactly what is needed: the map in BG1 with priority 0, the hero and
# the regular NPCs in objects with priority 1, the upper layer in BG2 with
# priority 1, and the events marked "above" in objects with priority 2. The
# RM2k order comes out of the hardware with no tricks.
PRIORITY_ABOVE = 1                       # for the BG2 cells


# CGRAM color 0 is the backdrop: it shows where no layer draws, and also where
# a tile uses index 0. Black, which is what RM2k draws where the map has
# nothing and beyond its edges, and since 2026-09-05 that shows: the screen
# shake reveals what is at the sides. It used to be magenta, a sentinel for the
# eye —"if it shows inside the screen, something is wrong"—.
BACKDROP = (0, 0, 0)


def quantized_tiles(image):
    """The image split into 8x8 cells of 15-bit colors, which is what the PPU
    shows: a grid of rows of cells, each cell a tuple of eight rows of eight
    colors. A transparent pixel stays as None and ends up at index 0 of the
    palette, which the PPU doesn't draw.

    With numpy: the colors and the cells come from arrays, and each distinct
    cell is built as a tuple **only once** —the same object at every place of
    the map where it repeats—. Large maps are millions of pixels and a few
    thousand distinct cells, and building it pixel by pixel in Python was the
    most expensive part of converting their layers. `_colors_of` relies on
    repeated cells being the same object.
    """
    pixels = numpy.asarray(image.convert("RGBA"))
    height, width = len(pixels) // CELL, len(pixels[0]) // CELL
    pixels = pixels[:height * CELL, :width * CELL].astype(numpy.int32)
    codes = numpy.where(pixels[:, :, 3] == 0, -1,
                        ((pixels[:, :, 0] >> 3) << 10)
                        | ((pixels[:, :, 1] >> 3) << 5)
                        | (pixels[:, :, 2] >> 3)).astype(numpy.int32)
    cells = numpy.ascontiguousarray(
        codes.reshape(height, CELL, width, CELL).transpose(0, 2, 1, 3)
    ).reshape(height * width, CELL * CELL)
    unique, which = numpy.unique(
        cells.view(numpy.dtype((numpy.void, cells.itemsize * CELL * CELL))),
        return_inverse=True)
    unique = unique.view(numpy.int32).reshape(-1, CELL * CELL)
    colors = {-1: None}
    for c in numpy.unique(unique).tolist():
        if c >= 0:
            colors[c] = (c >> 10, (c >> 5) & 31, c & 31)
    built = [tuple(tuple(colors[c] for c in row[y * CELL:(y + 1) * CELL])
                   for y in range(CELL))
             for row in unique.tolist()]
    return [[built[k] for k in row]
            for row in which.reshape(height, width).tolist()]


def _colors_of(grids):
    """How many pixels of each color there are in these grids, without the
    transparent ones: a `Counter` with the colors **in the order in which
    they appear**, walking cell by cell and row by row, which is the order it
    had when counting them pixel by pixel.

    It counts each distinct cell once and multiplies it by how many times it
    occurs, and "distinct" is by identity: the repeated cells from
    `quantized_tiles` are the same object. With other grids it gives the
    same result, slower.
    """
    times = {}
    for grid in grids:
        for row in grid:
            for cell in row:
                seen = times.get(id(cell))
                if seen is None:
                    times[id(cell)] = [cell, 1]
                else:
                    seen[1] += 1
    counts = collections.Counter()
    for cell, n in times.values():
        for line in cell:
            for p in line:
                if p is not None:
                    counts[p] += n
    return counts


def split_above(grid, limit):
    """Which palettes the upper layer takes, with `limit` as the cap.

    It is the decision, separate from the emission: how many palettes this
    layer uses is what decides where it starts in CGRAM, and that in turn
    tells the background how far it can go. That is why `_convert_layers`
    makes it, being the only one that sees both layers, and `convert_above`
    gets the result.

    If they don't fit, it merges. Returns (grid, palettes, merged): the grid
    is a different one if merging was needed.
    """
    sets = {tile_colors(t) for row in grid for t in row}
    sets = {s for s in sets if s}
    groups = adeleine.try_pack(sets, limit) if sets else []
    merged = []
    if sets and groups is None:
        # Splitting doesn't fit. There are two reasons and they used to be
        # confused as one: that the colors are too many for the palettes
        # granted, or that a single tile has more than 15, which fits in no
        # palette however many it is given. No split fixes the second one.
        #
        # Both are fixed by the same thing: merging the least used color with
        # its nearest neighbor and retrying.
        grid, groups, merged = adeleine.reduce_colors(grid, limit)
    return grid, [sorted(g) for g in groups], merged


def above_image(grid, palettes, above_first):
    """The upper layer as Adeleine leaves it: an indexed PNG.

    Its indices are **CGRAM entries**: color `k` of palette `i` of this layer
    is entry `(above_first + i) * 16 + k + 1`, and transparent is 0. That way
    what was decided —which palette each cell takes and where each one
    starts— is written in the image, and can be looked at without building the
    ROM.
    """
    columns, rows = len(grid[0]), len(grid)
    width = columns * CELL
    pixels = [0] * (width * rows * CELL)
    position = [{color: k + 1 for k, color in enumerate(p)} for p in palettes]
    for cy, row in enumerate(grid):
        for cx, tile in enumerate(row):
            colors = tile_colors(tile)
            if not colors:
                continue
            # The first palette that has all its colors, which is the same
            # count `split_above` did when building them.
            i = next(i for i, pal in enumerate(palettes) if colors <= set(pal))
            base = (above_first + i) * COLORS_PER_PALETTE
            for y, line in enumerate(tile):
                offset = (cy * CELL + y) * width + cx * CELL
                for x, color in enumerate(line):
                    if color is not None:
                        pixels[offset + x] = base + position[i][color]
    colors_out = [None] * 256
    for i, palette in enumerate(palettes):
        base = (above_first + i) * COLORS_PER_PALETTE
        colors_out[base] = BACKDROP
        for k in range(COLORS_PER_PALETTE - 1):
            colors_out[base + k + 1] = palette[k] if k < len(palette) else (0, 0, 0)
    return tiles_bin.indexed_png(
        width, rows * CELL, pixels, colors_out,
        [e % COLORS_PER_PALETTE == 0 for e in range(256)])


def convert_above(grid, palettes, above_first, merged=0):
    """The layer that goes above the hero: 4-bit tiles and their tilemap.

    It is much smaller than the lower one —in Map0073 it is 419 cells of 900,
    with seven colors— so it almost always fits in one or two palettes. Empty
    cells point to tile 0, which is left transparent on purpose.

    **It decides nothing**: the palettes were chosen by `split_above`, and
    which CGRAM palette it starts at, `above_first`, was chosen by
    `_convert_layers`. With that it writes the indexed image and `tiles`
    converts it.

    Returns (tiles, CGRAM words, tilemap, first palette, merged, the
    Adeleine's image).
    """
    png = above_image(grid, palettes, above_first)
    tiles, cgram, tilemap, _ = tiles_bin.convert(
        png, 4, len(grid[0]), priority=PRIORITY_ABOVE)
    # The palettes of this layer, and nothing else: the rest of the image's
    # CGRAM belongs to other layers.
    cram = cgram[2 * above_first * COLORS_PER_PALETTE:
                 2 * (above_first + len(palettes)) * COLORS_PER_PALETTE]
    # Never zero: on the console a DMA of size zero transfers 65536 bytes, not
    # none. A map with no upper layer sent an empty palette and wiped the
    # whole CGRAM, sprite palettes included. An empty palette is emitted.
    if not cram:
        cram = bytes(2 * COLORS_PER_PALETTE)
    return tiles, cram, tilemap, above_first, merged, png


# --- conversion -------------------------------------------------------------

def build_palette(grid, bg_colors, others=()):
    """The map's colors, in a single table, merging only if there are too many.

    At 8 bits per pixel the only limit is how many CGRAM entries are left free
    below the upper layer. Map0007 uses 60, so nothing is merged; the merge
    path exists for more loaded maps and is `adeleine.reduce_colors`.

    `others` are the grids of the other drawings of the ChipSet animation. They
    count for the palette like the usual drawing —the water of map 5 brings
    three colors that aren't in its step 0, and without them step 1 couldn't
    be written with this palette— and come out merged with the same
    `mapping`, which is what keeps them comparable with each other.
    """
    counts = _colors_of((grid,) + tuple(others))
    if len(counts) <= bg_colors:
        return sorted(counts), grid, list(others), []

    mapping, merged = adeleine.merge_least_visible(counts, bg_colors)

    def merge(g):
        return [[tuple(tuple(mapping.get(p) for p in line) for line in tile)
                 for tile in row] for row in g]

    return (sorted({c for c in mapping.values()}), merge(grid),
            [merge(g) for g in others], merged)


_LAYERS_VERSION = None


def _layers_version():
    """Which version of the code produced whatever is stored under `layers`.

    It is the sources that take part in drawing or converting, plus the
    program that isn't a source of this tree:

    * **the `rm2k-snes-maps` binary** draws the layers —with `rm2k-render`
      as a library—, decides which colors are lost and how they are grouped
      —Adeleine, also a library— and cuts the tiles —Voodoo—: recompiling
      it without touching any `.py` has to invalidate what is stored. Until
      2026-09-30 those were three binaries of their own and Pillow, and
      this list carried each one's hash;
    * `render/render_map.py`, which is where the search directories the
      stage gets come from, with `rpgmaker/resources.py` and
      `common/project.py`; and this file, which asks the stage and reads its
      answer. `port/adeleine.py`, `port/snes_format.py` and
      `rpgmaker/rm2k.py` no longer take part, and `port/snes_convert.py`
      has not since 2026-09-29: they stay in the list because taking one
      out is a decision of its own, and costs only a cold cache when they
      change.

    What does **not** go in, on purpose: `rpgmaker/lcf.py`. What it reads from
    the dump —the two layers, the size, the ChipSet's passability— goes in by
    its value in `layer_inputs`, so a change in how it is read only
    matters if what is read changes, and then the key changes by itself.
    """
    global _LAYERS_VERSION
    if _LAYERS_VERSION is None:
        from common import disk_cache
        _LAYERS_VERSION = (disk_cache.version_of("port/snes_convert.py",
                                                 "port/map_layers.py",
                                                 "port/snes_format.py",
                                                 "port/adeleine.py",
                                                 "rpgmaker/rm2k.py",
                                                 "render/render_map.py",
                                                 "rpgmaker/resources.py",
                                                 "common/project.py")
                           + _stage_version())
    return _LAYERS_VERSION


def _stage_version():
    """The installed stage's hash: recompiling it without touching any
    `.py` has to invalidate what is stored."""
    import hashlib
    from port import stage
    path = shutil.which(STAGE)
    if path is None:
        raise SystemExit(stage.MISSING % (STAGE, "maps"))
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def converted_layers(renderer, game_map, baked=None):
    """The map's layers converted, remembered on disk. `None` if there is no
    ChipSet. `baked` are the events `baking` painted into its upper layer,
    `{event: (cell, tile)}`: `game_map` already carries them, and the stage
    that converts gets them as cells.

    It is the most expensive part of the converter end to end: **drawing** the
    two layers and the drawings of their animations, and then quantizing
    them, cutting them into tiles and splitting CGRAM. Since 2026-09-30 all
    of it is `rm2k-snes-maps layers`'s —see `_stage_layers`—.

    The key comes from **the inputs** —the map, its ChipSet and the version of
    the code that draws and converts— and not from the result. Until
    2026-09-20 it came from the already drawn pixels, which had the virtue that
    there was nothing to enumerate: whatever produced the images went in by
    itself. The cost was that to ask the cache you had to draw anyway, and
    drawing the 29 maps of `abl` with their animations is 24 of the 65 s of a
    warm build. With the key from the inputs, a warm build draws none.

    What is lost is exactly that virtue, and that is why `layer_inputs`
    lives next to `animated_layers`, which builds what `rm2k-render` reads,
    and says what that is: now the list is
    maintained by hand, and if it falls short the cache answers stale without
    anything failing.

    Verified with `NO_CACHE=1` and with the cache deleted: the `.sfc` is the
    same byte for byte.
    """
    from common import disk_cache
    inputs = renderer.layer_inputs(game_map)
    if inputs is None:
        return None
    on_disk = disk_cache.key(_layers_version(), *inputs)
    if on_disk in _layers_in_memory:
        return _layers_in_memory[on_disk]
    done = disk_cache.read("capas", on_disk)
    if done is not None:
        _layers_in_memory[on_disk] = done
        return done
    done = _stage_layers(renderer, game_map, baked)
    disk_cache.write("capas", on_disk, done)
    _layers_in_memory[on_disk] = done
    return done


STAGE = "rm2k-snes-maps"

# The families by the name the stage gives them.
_FAMILY_NAMES = {"water": "agua", "animated": "animado"}


def _stage_layers(renderer, game_map, baked):
    """`rm2k-snes-maps layers` on this map, and its answer in the shape the
    rest of the converter reads: what `_convert_layers` returned."""
    from port import compiler, stage
    dump = compiler.dump_of(renderer.game_dir)
    flags = ["--data", dump]
    for directory in renderer.search_dirs:
        flags += ["--search-dir", os.path.abspath(directory)]
    written = stage.run(STAGE, "maps", "layers", {
        "map": game_map.map_id,
        "map_files": compiler.map_files(dump),
        "chipset_files": compiler.chipset_files(dump),
        "baked": [list(cell) for cell in sorted((baked or {}).values())],
    }, *flags, raw=True)
    answer = json.loads(written["layers.json"])
    bg, above = answer["background"], answer["above"]

    def merges(listed):
        return [(tuple(v), tuple(t), n) for v, t, n in listed]

    animation = {}
    for run in bg["runs"]:
        animation[_FAMILY_NAMES[run["family"]]] = {
            "base": run["base"], "tiles": run["tiles"],
            "dibujos": [written[name] for name in run["drawings"]]}
    pictures, above_png = [], None
    for picture in answer["pictures"]:
        name, png = picture["name"], written[picture["file"]]
        if name == "above":
            above_png = png
            continue
        if name == "background":
            name = "fondo"
        else:
            family, drawing = name.rsplit("-", 1)
            name = "%s-%s" % (_FAMILY_NAMES[family], drawing)
        pictures.append((name, png))
    stats = {
        "colores": bg["colors"],
        "usados": bg["used"],
        "presupuesto": bg["budget"],
        "fusionados": len(bg["merges"]),
        "tiles": bg["tiles"],
        "celdas": bg["cells"],
        "animacion": animation,
        "imagenes": pictures,
        "fusiones": {"fondo": merges(bg["merges"]),
                     "encima": merges(above["merges"])},
    }
    return ((written["background.bin"], bg["cgram"], bg["tilemap"], stats),
            (written["above.bin"], written["above-cgram.bin"],
             above["tilemap"], above["first"], len(above["merges"]),
             above_png))


# The layers already converted in this run, keyed by the disk cache key.
# `precompute_layers` fills it and it also works with `NO_CACHE=1`: it is not
# a cache between runs but the same computation done earlier and in parallel.
_layers_in_memory = {}


def _convert_layers(base, above_img, variants=None):
    """Both layers together, which is the only way to split CGRAM well.

    The split between the background and the upper layer can't be decided by
    either of them on its own, so it is decided here and there is a single
    place where it is written. Each caller used to convert one and then the
    other, and the three copies of the order matching was a matter of luck.

    The rule is that the background has first choice: it keeps the palettes
    it needs for the colors it actually uses, because it goes at 8 bits and
    can't split them into groups. The upper layer takes what is left —up to
    what it asks for, never more— and if that isn't enough, it merges.

    It goes in that order and not the reverse because there are 300 maps
    whose upper layer asks for one or two palettes against a handful that
    would ask for seven: letting the upper one be served first would take
    colors from the background in all of them so that a few don't merge.

    Until 2026-09-07 the message window also took the palette right below the
    upper layer, and **the background paid for it**. The choice of whom to
    charge was measured and not a matter of taste. The background goes at 8
    bits, so its palettes are a shared pool: one less takes 16 CGRAM entries
    from it and forces it to merge only the excess. The upper layer goes at 4
    and packs per tile, so one palette less can cost it much more. In map 1
    —the one that uncovered this— the background uses 49 colors and the upper
    layer exactly 64 in 4 palettes: taking one from the background merges 2
    colors, and taking it from the upper layer would require merging 16.

    Today the window lives in palette 0, at the very bottom —see
    `window_palette`—, so it charges neither layer.

    Returns (what convert() returns, what convert_above() returns).
    """
    base_grid = quantized_tiles(base)
    above_grid = quantized_tiles(above_img)
    # The other drawings of the ChipSet animation, cut the same as the
    # background. See `convert`.
    grids = {family: [quantized_tiles(img) for img in pictures]
             for family, pictures in (variants or {}).items()}

    # What the background uses, and therefore the palettes of 16 it needs. The
    # +1 is the screen's backdrop color, which takes entry 0.
    #
    # **All the drawings** count: the water of map 5 brings three colors that
    # aren't in the drawing seen on entering, and if the split were decided
    # without them there would be nowhere to put them when the water moves.
    used = len(_colors_of([base_grid] + [g for gs in grids.values()
                                         for g in gs]))
    palettes_needed = -(-(used + CGRAM_RESERVED) // COLORS_PER_PALETTE)
    free = max(1, min(MAX_ABOVE_PALETTES, BG_PALETTES - palettes_needed))

    above_grid, above_palettes, merged_colors = split_above(above_grid, free)
    # Without an upper layer nothing is reserved, but the DMA still sends an
    # empty palette —see `convert_above`—, so the split is counted as if there
    # were one.
    first = above_split(max(1, len(above_palettes)))
    above = convert_above(above_grid, above_palettes, first, len(merged_colors))
    # The background reaches **up to where the upper layer starts**, without
    # leaving palettes in between: it goes at 8 bits and needs no alignment.
    # The window doesn't charge it a palette because it lives at the very
    # bottom, inside `CGRAM_RESERVED`.
    cap = first
    if cap < 1:
        # Unreachable with the game's data —it would take an upper layer that
        # asks for all eight palettes— but if it happens, the background would
        # be left with none and `bg_budget` would give a negative budget.
        raise SystemExit(
            "the upper layer took all eight palettes and none is left "
            "for the background")
    # And the background palette, with that budget and over **all** its
    # drawings. It is decided here and `convert` gets it, same as the upper
    # layer.
    budget = bg_budget(cap)
    others = [g for family, _ in FAMILIES for g in grids.get(family, ())]
    before = len(_colors_of([base_grid]))
    palette, base_grid, others, merged = build_palette(base_grid, budget,
                                                       others)
    background = convert(base_grid, palette, grids, others,
                         {"colores": before, "presupuesto": budget,
                          "fusionados": len(merged)})
    # Which color was merged with which, in the order it was decided, for
    # `port/patches.py` to write it. It goes **with the background's summary
    # and not inside the upper layer's tuple** even though half of it is the
    # upper layer's: `_same_cgram_split` compares that whole tuple, so
    # adding a field would change the criterion baking is decided by, and this
    # can't change a single byte of the ROM. The summary, instead, it compares
    # field by field, so one more key is inert —and `merged_colors`, which is one
    # of the ones it compares, is still the usual number—.
    background[3]["fusiones"] = {"fondo": list(merged), "encima": list(merged_colors)}
    return background, above


def window_palette(first_ones=None):
    """Which palette the message window goes in: **0**, always.

    The window cells are emitted only once with the three palette bits
    inside, so the palette has to be a single one for the whole ROM. It used
    to take the lowest of the upper layers of all maps —`min(primeras) - 1`—
    and the background of **all** of them was squeezed below it, even if the
    map had half of CGRAM free above.

    Putting it in 0 makes the problem go away: the window takes entries 1 to 7
    —0 is the screen's backdrop color, which in a BG2 palette is transparent
    and the window doesn't draw—, and the background is contiguous from 8 up
    to where each map's upper layer starts. `first_ones` is no longer used and
    stays so as not to break callers.
    """
    return 0


# The two tile families the ChipSet animates, with how many drawings each one
# has and in the order their runs go to VRAM. It lives in rm2k.py together with
# each one's cadence, which is what says which drawing is due.
FAMILIES = rm2k.ANIMATED_FAMILIES


def convert(grid, palette, variants, others, summary):
    """The map grid to tiles, palette and tilemap.

    **It doesn't decide the palette**: it comes from `build_palette`, which
    chooses it in `_convert_layers` with the budget the upper layer left.
    `grid` and `others` are the grids already merged with that same palette;
    `variants` the original ones, which are only used to know how many
    drawings each family brings. `summary` carries what was measured before
    merging.

    `variants` are the grids of the **other** drawings of the ChipSet
    animation, per family: `{"agua": [g1, g2], "animado": [g1, g2, g3]}`.
    Drawing 0 is `grid`.

    The cells that change from one drawing to another get their own tiles, in
    a **contiguous run at the end of the bank**, and share none with the still
    cells. Animating is overwriting the tile data in VRAM without touching the
    tilemap, so a tile shared with a still cell would make it change too; and
    with the contiguous run, one animation step is a single DMA.

    Returns (tile data, CGRAM words, tilemap, summary). Where the runs land
    and the bytes of each drawing go in `resumen["animacion"]`.
    """
    # Back to their family, already merged with the same mapping as `grid`, and
    # with drawing 0 first: `dibujos[familia][d]` is the grid of drawing `d`.
    drawings, rest = {None: [grid]}, list(others)
    for family, _ in FAMILIES:
        how_many = len(variants.get(family, ()))
        drawings[family] = [grid] + rest[:how_many]
        rest = rest[how_many:]

    # What Adeleine decided, as indexed images: color `k` of the palette
    # is entry `CGRAM_RESERVED + k`, and transparent is 0. One per drawing,
    # all with the same CGRAM: `tiles` stops if two give a different color to
    # an entry that any of them draws.
    position = {color: CGRAM_RESERVED + k for k, color in enumerate(palette)}
    colors = [None] * 256
    for color, cg_entry in position.items():
        colors[cg_entry] = color
    transparent = [e == 0 for e in range(256)]
    width, height = len(grid[0]) * CELL, len(grid) * CELL

    def picture(g):
        pixels = [0] * (width * height)
        for cy, row in enumerate(g):
            for cx, tile in enumerate(row):
                for y, line in enumerate(tile):
                    offset = (cy * CELL + y) * width + cx * CELL
                    for x, color in enumerate(line):
                        if color is not None:
                            pixels[offset + x] = position[color]
        return tiles_bin.indexed_png(width, height, pixels, colors,
                                     transparent)

    pictures = [("fondo", picture(grid))]
    families, animations = [], []
    for family, _ in FAMILIES:
        if len(drawings[family]) < 2:
            continue
        pngs = [picture(g) for g in drawings[family][1:]]
        pictures += [("%s-%d" % (family, d + 1), png)
                     for d, png in enumerate(pngs)]
        families.append(family)
        animations.append(pngs)

    # The cells that change from one drawing to another get their own tiles in
    # one contiguous run per family, after the still ones: Voodoo does that,
    # since it is the one that numbers them. See "Animations" in
    # tools/snes/voodoo/README.md.
    tile_data, cgram, tilemap, runs = tiles_bin.convert(
        pictures[0][1], 8, len(grid[0]), animations=animations,
        max_tiles=MAX_TILES)
    next_tile = len(tile_data) // BYTES_PER_TILE

    # And the other drawings of each run, one after the other and in VRAM
    # order: that way uploading them is writing the address and firing the
    # DMA.
    animation = {}
    for family, (start, length, drawing_bytes) in zip(families, runs):
        if not length:
            continue
        count = dict(FAMILIES)[family]
        if len(drawing_bytes) != count:
            raise SystemExit("family %r asks for %d drawings and %d arrived"
                             % (family, count, len(drawing_bytes)))
        animation[family] = {"base": start, "tiles": length,
                             "dibujos": list(drawing_bytes)}

    # CGRAM: the map's block carries **only its colors** and is uploaded
    # starting at `CGRAM_RESERVED`. What is below —the screen's backdrop
    # color and the window palette— belongs to the whole ROM and `cgram_base`
    # uploads it.
    cram = [int.from_bytes(cgram[2 * e:2 * e + 2], "little")
            for e in range(CGRAM_RESERVED, CGRAM_RESERVED + len(palette))]

    stats = {
        "colores": summary["colores"],
        "usados": len(palette),
        "presupuesto": summary["presupuesto"],
        "fusionados": summary["fusionados"],
        "tiles": next_tile,
        "celdas": sum(len(row) for row in tilemap),
        "animacion": animation,
        "imagenes": pictures,
    }
    return bytes(tile_data), cram, tilemap, stats

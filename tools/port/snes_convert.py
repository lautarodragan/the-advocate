#!/usr/bin/env python3
"""Converts an A Blurred Line map into data the SNES PPU consumes.

Splitting colors into palettes, and merging the least used ones when they
don't fit, lives in `allocator.py`, and reusing mirrored tiles in Voodoo.
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

Usage:
    rm2k-snes-convert --map-id 7 -o rom/build/inc/mapdata.inc

With a test page, which is the list of RM2k commands from a file in
`rom/pruebas/casos/`; several in one cartridge, each one after a `--case`, and
the cartridge flags before the first. The harness picks which one runs with
`Partida(case=k)`:
    rm2k-snes-convert -o … --map-id 6 \
        --test-commands rom/pruebas/casos/pan.json \
        --case --test-commands rom/pruebas/casos/pan-vuelve.json
"""

import argparse
import collections
import contextlib
import json
import multiprocessing
import os
import shutil
import sys
import zlib

import numpy

# Run as a script —which is how the recipes run it—, Python puts this file's
# folder in `sys.path`, not `tools/`, which is where the packages are imported
# from. It is replaced instead of adding `tools/` next to it: with both, a bare
# `import eventos` would work and load a second copy of the module, distinct
# from `port.events`.
# `realpath` and not `abspath`: `just install` installs it on the PATH as
# a symlink, and the folder that matters is the one of the real file.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from port import tiles_bin
from port import compress
from rpgmaker import event_codes
from port import events
from rpgmaker import lcf
from rpgmaker import rm2k

# Translucent events carry their own graphic: see `rm2k.decorate_translucent`
# —baked against the background, dithered, or opaque—.
lcf.DECORATE_TRANSLUCENT = rm2k.decorate_translucent
# And the text boxes, rebuilt for the SNES window: see
# `lcf.REFIT_TEXTS` and `port/texts.py`.
from port import texts
lcf.REFIT_TEXTS = texts.refit_commands
from port import animation as animation_mod
from port import picture
from port import allocator
from port import patches as patches_mod
from port import title as title_mod
from port import menus as menus_mod
from port import fullscreen
from port import end_game as end_game_mod
from port import screens as screens_mod
from port import battle as battle_mod
from port import experience as X
from port import scene as scene_mod
from port import color as color_mod
from port import constants
from port import rules
from port import msu_data
from audio import msu_effects
from common import settings
from common import project
from common.parallel import in_parallel
from audio import snes_music
from port.allocator import CELL, tile_colors
from port.snes_format import cgram_word, entry, pack_tile
from rpgmaker.rm2k import TILE, collect_npcs, hero_start, passability_map
from render import render_map
from render.render_map import Renderer, build_passability, load_image
from common import environment
from rpgmaker import resources
from rpgmaker.resources import find_resource

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
BYTES_PER_TILE = 64                      # 8 bit planes, 8 rows each


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

# The window tiles live in the bank that follows the upper layer's, and BG2
# reaches them with the same base because they ended up adjacent: indices 0 to
# 255 are the upper layer's and 256 to 511 the window's.

# The window size in cells. It is fixed: 256x80 stuck to the bottom of the
# screen, the same numbers as `tools/port/window.py`.
WINDOW_COLS_INC, WINDOW_ROWS_INC = 32, 10

# The glyph, which is what the ROM composes. The same numbers as
# `tools/port/font.py`, which is generated from easyrpg-player.
FONT_WIDTH, FONT_HEIGHT = 6, 12

# And the ones for objects, already shifted into place in the vhoopppN byte:
# the priority is bits 5 and 4, not 0 and 1: writing $20 thinking it is
# priority 1 gives priority 2, and in the order above that one extra place
# crosses exactly the upper layer. Nothing fails and the sprite is still
# visible: only on the wrong side of a layer, that is covering the roof it
# should be walking under.
#
# These two values are the only ones in the program: the ROM gets the hero's
# in HERO_PRIORITY and each NPC's comes built into its attribute byte. They are
# not written in `tools/runtime/` too: a second copy is one more place to get
# it wrong without anything noticing.
OBJ_PRIORITY = 0x10                      # priority 1: below BG2 1
OBJ_PRIORITY_ABOVE = 0x20                # priority 2: above it

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


def pack_tiles(tiles, planes=8):
    """`pack_tile` for several tiles at once: `tiles` is a numpy array of
    (n, 8, 8) indices, and out comes the list of the n packed tiles."""
    bits = (tiles[..., None] >> numpy.arange(planes, dtype=numpy.uint8)) & 1
    # (n, y, x, plane) -> one byte per row and plane, the leftmost pixel in
    # the high bit; and from there to the PPU order: pairs of planes, and
    # within each pair row by row.
    rows = numpy.packbits(bits, axis=2, bitorder="big")[:, :, 0, :]
    ppu = rows.reshape(-1, CELL, planes // 2, 2).transpose(0, 2, 1, 3)
    data = numpy.ascontiguousarray(ppu).reshape(len(tiles), planes * 8)
    return [bytes(row) for row in data]


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
    groups = allocator.try_pack(sets, limit) if sets else []
    merged = []
    if sets and groups is None:
        # Splitting doesn't fit. There are two reasons and they used to be
        # confused as one: that the colors are too many for the palettes
        # granted, or that a single tile has more than 15, which fits in no
        # palette however many it is given. No split fixes the second one.
        #
        # Both are fixed by the same thing: merging the least used color with
        # its nearest neighbor and retrying.
        grid, groups, merged, _ = allocator.reduce_colors(grid, limit)
    return grid, [sorted(g) for g in groups], merged


def above_image(grid, palettes, above_first):
    """The upper layer as the allocator leaves it: an indexed PNG.

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
    allocator's image).
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


# --- the character sprite ---------------------------------------------------
#
# An RM2k CharSet is 4 characters wide by 2 high; each one takes 72x128 and has
# 12 poses of 24x32: 3 walking frames for 4 directions.
#
# The SNES has no 24x32 sprites. The smallest one that covers that pose is
# 32x32, so it is padded with transparency at the sides and a quarter of the
# tiles is lost. The alternative was splitting each pose into several 16x32
# objects, which spends the same and multiplies the OAM entries.
#
# Sprites are always 4 bits per pixel, no exceptions: there is no mode 3 for
# them. That is, Talan has to fit in 15 colors, and has 36.

SPRITE_W, SPRITE_H = 24, 32
OBJ_W = OBJ_H = 32                 # the real size of the object on screen
OBJ_COLORS = 15                    # 4 bits per pixel, and 0 is transparent
COLORS_PER_PALETTE = 16            # what each sprite palette takes in CGRAM
SPRITE_POSES = 12
INITIAL_POSE = 2 * 3 + 1           # facing down, the middle frame
OBJ_PALETTES = 8                   # 8 to 15, with or without the timer

# The OAM name table is 16 tiles wide, so a 32x32 object doesn't take 16 tiles
# in a row but a 4x4 block inside that grid.
OBJ_ROW = 16


def pose_origin(index, pose):
    """Where a pose starts inside the CharSet."""
    return ((index % 4) * SPRITE_W * 3 + (pose % 3) * SPRITE_W,
            (index // 4) * SPRITE_H * 4 + (pose // 3) * SPRITE_H)


ALL_POSES = frozenset(range(SPRITE_POSES))


def sprite_colors(image, index, poses=None):
    """The character's colors, with how many pixels each one uses.

    `poses` are the ones the event can end up showing. **Counting all twelve
    when one is seen gives away CGRAM entries**: the save point in Lashe City
    animates facing up and nothing else, and its twelve poses together have
    41 colors against the 13 of those three frames. The 26 of difference were
    all merged, and the first to go were the blue and white of the glow —few
    pixels each— against the grays that cover the rest of the block.

    Who can show what is decided by `map_poses`, which is the same pass
    that already chose who gets all twelve poses in the cartridge: the
    optimization existed in tiles and in VRAM since 2026-09-05 and had never
    reached the color count. `None` is "all twelve", which is what fits
    whoever walks, animates standing still, turns toward the hero or changes
    graphic with command 34.
    """
    base_x = (index % 4) * SPRITE_W * 3
    base_y = (index // 4) * SPRITE_H * 4
    # With numpy and not pixel by pixel: the character's block to an array,
    # the poses by slicing, and each 15-bit color as a single integer to
    # count them with `unique`. Millions of pixels are read per ROM.
    block = numpy.asarray(image.crop((base_x, base_y,
                                      base_x + SPRITE_W * 3,
                                      base_y + SPRITE_H * 4)))
    seen = numpy.concatenate([
        block[(pose // 3) * SPRITE_H:(pose // 3 + 1) * SPRITE_H,
              (pose % 3) * SPRITE_W:(pose % 3 + 1) * SPRITE_W].reshape(-1, 4)
        for pose in (sorted(ALL_POSES) if poses is None
                     else sorted(poses))])
    return _count_colors(seen)


def _count_colors(pixels):
    """A Counter of the 15-bit colors of the opaque RGBA pixels.

    **The keys come in the order in which they appear**, which is the one the
    `Counter` built pixel by pixel had: whoever walks it
    —`merge_least_visible` breaks ties by that order— has to see the same.
    """
    opaque = pixels[pixels[:, 3] != 0, :3] >> 3
    codes = ((opaque[:, 0].astype(numpy.int32) << 10)
             | (opaque[:, 1].astype(numpy.int32) << 5) | opaque[:, 2])
    unique, first, count = numpy.unique(codes, return_index=True,
                                        return_counts=True)
    counts = collections.Counter()
    for k in numpy.argsort(first, kind="stable").tolist():
        c = int(unique[k])
        counts[(c >> 10, (c >> 5) & 31, c & 31)] = int(count[k])
    return counts


# --- the NPCs ---------------------------------------------------------------
#
# They are the map events that have a CharSet, standing still in the pose their
# page declares. Their scripts are not evaluated. Each one is one more OAM
# object.
#
# Two console limits rule here. One is how many sprite tiles fit in VRAM: 512
# addressable, and each pose is 16. The other, harder, is that a single screen
# line cannot have more than 34 8x8 sprite tiles; a 32x32 object contributes 4,
# so from nine characters together onward the console starts not drawing the
# last ones.

BLOCKS_PER_ROW = 4              # 4x4-tile blocks that fit in the grid


def block_tile(block):
    """The tile number where a 32x32 block starts."""
    return (block // BLOCKS_PER_ROW) * 64 + (block % BLOCKS_PER_ROW) * 4


def character_palette(image, index, cap=None, poses=None):
    """A character's palette, and how to map each color to its index.

    It is the same computation for the image that goes to VRAM and for the
    cartridge's pose bank, and it has to be: a pose uploaded on the fly is
    drawn with the palette already in CGRAM.

    `cap` lowers the number of colors below fifteen, and exists to make room
    for the timer: its digits are two colors and black is usually already
    there, so one entry is enough. **Who pays for it and how much is decided
    by `drawable_npcs`**, which is the only one that sees all the palettes
    of the map; here it is only obeyed. If the converter chose it here, two
    calls for the same character could give different palettes and the
    cartridge's poses wouldn't match the CGRAM.

    `poses` are the ones the event can show: **the fifteen colors are chosen
    looking only at those**, which is where almost all of the save point's
    color gain comes from. Same as `cap`, `drawable_npcs` decides it and
    here it is only obeyed.

    The returned `mapping` still covers **all** the colors of the twelve-pose
    block, not only those of `poses`: the ones left out of the count go to
    the nearest of the survivors. It is not defensive decoration —it is what
    keeps `pose_tiles` from dying with a KeyError if someone asks for one pose
    too many—, and it costs one computation per color.
    """
    cap = OBJ_COLORS if cap is None else cap
    counts = sprite_colors(image, index, poses)
    if len(counts) <= cap:
        mapping = {c: c for c in counts}
    else:
        mapping, _ = allocator.merge_least_visible(counts, cap)
    palette = sorted(set(mapping.values()))
    if poses is not None and palette:
        for color in sprite_colors(image, index):
            if color not in mapping:
                mapping[color] = min(
                    palette, key=lambda p, c=color: (allocator.luma_distance(p, c), p))
    lookup = {color: i + 1 for i, color in enumerate(palette)}
    return palette, lookup, mapping


def pose_tiles(image, index, pose, lookup, mapping):
    """The sixteen tiles of a pose, by rows: four rows of four.

    It is the order in which the PPU reads a 32x32 object —each row is four
    consecutive tiles of the name grid, and rows go sixteen apart— and that is
    why a pose is uploaded with four DMAs of 128 bytes.
    """
    ox, oy = pose_origin(index, pose)
    # With numpy, like `sprite_colors`: the pose to an array, each distinct
    # color translated only once, and the bit planes of the sixteen tiles
    # together.
    pixels = numpy.asarray(image.crop((ox, oy, ox + SPRITE_W,
                                       oy + SPRITE_H)))
    rgb = pixels[:, :, :3] >> 3
    codes = ((rgb[:, :, 0].astype(numpy.int32) << 10)
             | (rgb[:, :, 1].astype(numpy.int32) << 5) | rgb[:, :, 2])
    opaque = pixels[:, :, 3] != 0
    unique, which = numpy.unique(codes[opaque], return_inverse=True)
    indices = numpy.array(
        [lookup[mapping[(c >> 10, (c >> 5) & 31, c & 31)]]
         for c in unique.tolist()], dtype=numpy.uint8)
    whole_pose = numpy.zeros((OBJ_H, OBJ_W), dtype=numpy.uint8)
    margin = (OBJ_W - SPRITE_W) // 2
    center = numpy.zeros((SPRITE_H, SPRITE_W), dtype=numpy.uint8)
    center[opaque] = indices[which]
    whole_pose[:SPRITE_H, margin:margin + SPRITE_W] = center
    tiles = whole_pose.reshape(4, CELL, 4, CELL).swapaxes(1, 2).reshape(
        16, CELL, CELL)
    return pack_tiles(tiles, planes=4)


def changes_graphic(event):
    """Whether some page of the event draws something different from another.

    It is what separates an annoying discard from one that breaks the game. A
    decorative single-page event that isn't drawn is just lost —the
    `CoreBlood` of map 3, the four `Link`s—. One that **changes graphic** is a
    mechanism: a door that opens, a machine that turns on. If it isn't drawn,
    the change is never seen, and since the event still blocks the way, what is
    left is an invisible wall the player expected to open.
    """
    graphics = {((getattr(p, "character_name", "") or "").strip(),
                 p.character_index) for p in event.pages}
    return len(graphics) > 1


def discard_warning(text, dangerous):
    """An event that isn't drawn. If it is one of those that break, it stops
    the conversion.

    **And it stops on purpose.** This was a `print` among fifty others, and on
    2026-09-07 it cost an afternoon: `demo-apertura` was built with the timer,
    map 2 lost event 30 —the middle cell of the door Core breaks— and the
    warning went by unnoticed in the build output. taro reached the cutscene,
    the door didn't change tile and he couldn't get through.

    It is the same criterion as `enter_panic` in the ROM: something that
    shouldn't happen is not discarded silently. The difference is where the
    noise is made. A discard is decided **when converting**, and by the time
    the ROM runs the event is no longer in any table: there is nothing left
    for the console to look at. Making it blow up when loading the map would be
    the same as not building the ROM, but later and without being able to say
    which event.

    Stopping on **all** discards doesn't work either: today there are
    decorative ones that don't fit in several maps, so every recipe would have
    to ask to continue and the stop wouldn't protect against anything. That is
    why the cap is `changes_graphic`, which is exactly the class event 30
    belonged to.

    There is no way to ask it to continue: there was a `--descartar-eventos`,
    and it went away in step 9e, when no cartridge discarded anything that
    needed it anymore.
    """
    if not dangerous:
        print("  " + text)
        return
    sys.exit(
        "%s\n\n"
        "The ROM is not built: that event **changes graphic between its pages**,\n"
        "that is, it is a mechanism and not decoration. Without being drawn, the\n"
        "change is never seen, and since the event still blocks the way and\n"
        "triggers, what is left is an invisible wall where the game expected a door." % text)


# --- the weight of a graphic ------------------------------------------------
#
def graphic_weight(charset):
    """How much a CharSet weighs when splitting the sprite palettes: the one
    that weighs is served first, and the one that doesn't arrives in map order
    and may end up with someone else's palette. The game decides it, in
    `[graphics.palette_weight]` of the project file, with its reasons. The
    `~trama` suffix of translucent ones doesn't count: the weight belongs to
    the drawing."""
    weights = settings.value("graphics", "palette_weight", kind=dict)
    return weights.get((charset or "").split(rm2k.DITHER_SUFFIX)[0], 0)


def pose_row(pose):
    """The three frames of the walking cycle for the direction of `pose`.

    An event that animates standing still changes column and **never row**: the
    ROM builds its pose as `facing_of_row * 3 + columna` in `animate_still`,
    so of the twelve it can only show these three.
    """
    return frozenset(range(pose // 3 * 3, pose // 3 * 3 + 3))


def map_poses(renderer, game_map, leaders, movable=(), turning=(),
              route_graphics=(), animates_still=()):
    """Which poses each (CharSet, index) can end up showing in this map.

    Each character's palette comes from here: fifteen colors chosen over what
    is seen and not over the twelve poses of the block. The list of who needs
    all twelve is **the same** that already decided which poses go to the
    cartridge and to VRAM —see `movable_events` and how `slots` is built in
    `convert_map`—, and it has to be: a pose the ROM uploads and the palette
    didn't count is drawn with colors that aren't its own.

    These take all twelve:

    * the leader candidates, because the hero walks;
    * the events in `movable` that **walk**;
    * the graphics in `turning`, because one that turns toward the hero can end
      up in any of the four directions;
    * the graphics of command 34, which keep walking after the change.

    One that **animates standing still** keeps the three frames of its
    direction, which is all `animate_still` can put on screen: it changes
    column and not row. That is where the save point in Lashe City is, the one
    taro saw gray: its twelve poses have 41 colors and the three frames it
    shows, 13. `savept` is an **edited** CharSet —the original RPG Maker
    drawing in almost all of the block and a new drawing, with its own colors,
    in a corner—, and in those the twelve poses don't share a palette. In a
    normal one counting twelve or counting three gives almost the same.

    The rest keep the pose their page declares, plus each page's if the
    graphic follows them: exactly the VRAM slots the map reserves for it, not
    one more.

    The same (CharSet, index) can belong to a still one and to a walking one
    at once —and across maps of the same ROM, too—: the union accumulates,
    which is what makes the count independent of the order they are walked in.
    """
    poses = {}

    def add(key, which_ones):
        previous = poses.get(key)
        poses[key] = ALL_POSES if (previous is ALL_POSES
                                   or which_ones is ALL_POSES) \
            else frozenset(previous or ()) | frozenset(which_ones)

    for actor in leaders:
        a = renderer.database.actors[actor]
        add((a.charset, a.charset_index), ALL_POSES)
    for pairs in (turning.values() if hasattr(turning, "values") else turning):
        for pair in pairs:
            add(tuple(pair), ALL_POSES)
    for pair in route_graphics:
        add(tuple(pair), ALL_POSES)
    for npc in collect_npcs(game_map):
        key = (npc["charset"], npc["index"])
        # Animates standing still and doesn't walk: the three frames of its
        # row. If it is also in `turning` it already took all twelve above, so
        # the turn doesn't run out of colors.
        still_animated = (npc["event"] in animates_still
                          and npc["event"] in movable)
        if still_animated:
            own = pose_row(npc["pose"])
        elif npc["event"] in movable:
            own = ALL_POSES
        else:
            own = frozenset((npc["pose"],))
        add(key, own)
        if npc["changes"]:
            for graphic in npc["graphics"]:
                if graphic is not None:
                    # An event that walks and also changes graphic loses the
                    # change —walking wins, see `convert_map`—, but the page's
                    # graphic still asks for a palette here, so the pose it
                    # declares is counted.
                    add(graphic[:2],
                        pose_row(graphic[2]) if still_animated
                        else ALL_POSES if npc["event"] in movable
                        else (graphic[2],))
    return poses


# --- the events baked into the map ------------------------------------------
# An event drawn with **an opaque ChipSet tile**, always the same and always in
# the same cell, doesn't need to be drawn as an event: its tile goes into the
# map's upper layer and its NPC row starts hidden. The event stays whole for
# its logic —it triggers, blocks the way, is the target of a page—; what is
# saved is its OAM object and its pass through `place_npc`, which is what
# costs frames in the most loaded map of the game.
#
# **Passability doesn't change, and that is what allows hiding the row.** For
# an upper-layer tile without the "above the hero" bit,
# `rm2k.passability_map` resolves the cell with that tile's bits, which are
# exactly the ones `rm2k.event_tile_passability` made the event's row
# impose; and `pass_with_event`, in tools/runtime/hero.s, skips hidden
# rows. That is, the baking hands the same table answer over to the map. It
# is guarded by `rom/pruebas/herramientas/test_horneados.py`.
#
# What is **not** saved yet: its sprite palette and its VRAM slot. The event
# still enters the `drawable_npcs` split as if it were drawn, on purpose:
# taking it out of there frees a palette for the map and that changes what is
# seen —the tiles that today are drawn with someone else's palette would get
# their own, and map 11 has one—, and that is a separate decision from this
# one.

# The commands that move an event to another cell or touch its drawing: an
# event that some page can move, change drawing or flash is not fixed, so it
# isn't baked. The **raw** commands are looked at and not the compiled pages:
# it is more conservative —it also counts the pages this port doesn't
# compile— and nothing needs compiling to ask, which is what lets the decision
# be made before drawing the layers.
MOVING_COMMANDS = (events.MOVE_EVENT, events.CHANGE_EVENT_LOCATION,
                   events.TRADE_EVENT_LOCATIONS, events.FLASH_SPRITE)


def _tile_alphas(chipset, index):
    """The alpha of the 16x16 pixels of upper-layer tile `index`."""
    return render_map.upper_tile(chipset, index).getchannel("A").tobytes()


def bakeable_events(renderer, game_map):
    """The map's events that can be baked, as {event: map tile}.

    The rule is deliberately small, because what holds it up is that **it
    looks the same**; when in doubt the event keeps being drawn. All five
    things are required:

    * **it is drawn with a tile of the ChipSet's upper layer** —not with a
      CharSet—, with tile 0 left out because in RM2k it is "no graphic";
    * **the drawing is fixed**: the first page without a condition and **all**
      pages drawing the same tile on the same layer. A door that opens with a
      switch changes tile, so it doesn't qualify; one that only changes
      script does. Until 2026-09-20 **a single page** was required, and that
      left out four light tiles of map 11 whose two or three pages draw the
      same thing;
    * **the event doesn't move or change**: no `move_type`, no own route on any
      page, no continuous animation on any, and no page of the map moves it or
      makes it flash (see `MOVING_COMMANDS`);
    * **the tile covers the whole cell**: opaque in all 16x16, and without the
      "above the hero" bit —with it, placed in the upper layer it would be
      drawn above the hero and not below, which is where the sprite of a
      below-layer event is—;
    * **the cell has room and doesn't open**: the event is on the below layer,
      the map's upper layer is empty there, and the tile adds no passage bit
      the map's table didn't have. If a tile is already drawn, baking would
      cover it; if the event is on the hero's layer or the above one its
      sprite doesn't go in the map's upper layer without changing what covers
      what; and if the tile opened the cell, baking would leave a hole that
      until then only existed while the row was visible.

    The tile below being animated **doesn't rule it out**: the cell is baked
    into every drawing of the animation, because what is touched is the map
    layer and `animated_layers` renders all of them from there. What is lost is
    the animation the opaque tile already covered.
    """
    chipset = renderer.chipset_by_name(getattr(game_map, "chipset_filename",
                                               None))
    flags = getattr(game_map, "passability_table", None)
    if chipset is None or flags is None:
        return {}
    # That tile 0 of the upper layer —the one an empty cell carries— draws
    # nothing is checked, not assumed: it is what makes putting the event's
    # tile there cover nothing. The ChipSets of this game satisfy it; one that
    # doesn't leaves the map without baked events instead of changing what is
    # seen.
    if any(_tile_alphas(chipset, 0)):
        return {}
    # The events that some page moves, flashes or sends walking. It goes by
    # the RM2k id, which is what the commands carry, and it is translated by
    # the same `events.MapEvents` the compilation uses.
    map_events = events.MapEvents(game_map)
    touched = set()
    for event in game_map.events:
        for page in event.pages:
            for cmd in page.commands:
                if cmd.code in MOVING_COMMANDS and cmd.parameters:
                    target = map_events.route_target(cmd.parameters[0])
                    if target:
                        touched.add(target - 1)
    # And the ones that walk on their own: `move_type` set to anything other
    # than still, or an own route on some page.
    walking = {number for number, event in enumerate(game_map.events)
               if any(p.move_type or p.move_route.commands
                      for p in event.pages)}
    opaque = {}
    bakeable = {}
    for npc in collect_npcs(game_map):
        number = npc["event"]
        base = rm2k.unbaked(npc["charset"])
        if not base.startswith(rm2k.TILE_PREFIX) or not npc["visible"]:
            continue
        if npc["changes"] or number in walking or number in touched:
            continue
        pages = game_map.events[number].pages
        if pages[0].condition.active:
            continue
        # All its pages have to draw the same thing, on the same layer and
        # without continuous animation, and not only the active one: the row
        # is hidden for the whole playthrough, so what decides is what the
        # event **can end up** drawing. Half of
        # `test_hornear_no_cambia_la_pasabilidad_de_la_celda` comes for free
        # from this: with the same graphic and the same layer on all of them,
        # `rm2k.event_tile_passability` gives the same on all of them.
        if set(npc["graphics"]) != {npc["graphics"][0]} \
                or npc["graphics"][0] is None:
            continue
        if set(npc["layers"]) != {rm2k.LAYER_BELOW}:
            continue
        if any(p.animation_type in rm2k.CONTINUOUS_ANIMATION for p in pages):
            continue
        index = int(base.rsplit(":", 1)[1])
        if not index:
            continue                    # tile 0 is "no graphic"
        tile = rm2k.UPPER_BASE + index
        if flags[tile] & rm2k.PASS_ABOVE:
            continue                    # it would go above the hero
        cell = npc["y"] * game_map.width + npc["x"]
        if game_map.upper_layer[cell] != rm2k.UPPER_BASE:
            continue                    # the cell's upper layer is taken
        # **And baking cannot open the cell.** Baking puts the tile in the
        # upper layer, so the map's table starts declaring the tile's bits
        # where it used to declare its own. Closing too much doesn't happen
        # —a solid event on free floor is the normal case, and the row already
        # closed that cell for everyone—, but **opening** does: a walkable
        # tile over a cell the map has closed is a hole that until now only
        # existed while the row was visible.
        #
        # The case that brought it up is the `MovinDoor` of map 2, which the
        # relaxed rule reaches: it is in a corner of the map, out of any
        # camera, and baking it moved the golden `puerta-izq-950` —113 pixels,
        # on a door sixty cells from there, with the same switches set—. The
        # whole mechanism was never fully taken apart; what is measured is
        # that this baking is the only thing that changes between the two
        # ROMs.
        if npc["tile_pass"] & ~rm2k.cell_passability(
                flags, game_map.lower_layer[cell],
                game_map.upper_layer[cell]):
            continue
        if index not in opaque:
            opaque[index] = all(a == 255
                                for a in _tile_alphas(chipset, index))
        if not opaque[index]:
            continue
        bakeable[number] = (cell, tile)
    return bakeable


def _same_cgram_split(without_it, with_it):
    """Whether baking didn't move anyone else's colors they are drawn with.

    What baking adds to the map are the tile's colors, and the background's
    colors are a shared pool with a budget: a few extra make it merge —and
    then pixels change in cells that have nothing to do with it— or take a
    palette away from the upper layer, which packs per tile and merges much
    worse. Both things show here: the upper layer has to come out identical,
    and the background with the same budget and without merging more than
    before. The background palette having new colors, and therefore another
    order, is not a change: the tilemap comes out with the indices of that
    same palette.
    """
    if with_it is None:
        return False
    (_, _, _, before), above_before = without_it
    (_, _, _, now), above_now = with_it
    return (above_before == above_now
            and before["presupuesto"] == now["presupuesto"]
            and before["fusionados"] == now["fusionados"])


def _bake_unless_cgram_moves(renderer, game_map, map_id, without_baked,
                             baked):
    """Bakes `baked` and returns (layers, baked): the baked ones if the
    CGRAM split didn't move, and otherwise those of `without_baked`, with none.
    See `_same_cgram_split`."""
    bake_into_map(game_map, baked)
    with_baked = converted_layers(renderer, game_map)
    if _same_cgram_split(without_baked, with_baked):
        return with_baked, baked
    print("  map %d: baking %d event(s) moved its CGRAM split, "
          "so they are drawn" % (map_id, len(baked)))
    for cell, _tile in baked.values():
        game_map.upper_layer[cell] = rm2k.UPPER_BASE
    return without_baked, {}


def bake_into_map(game_map, bakeable):
    """Puts the tile of each baked event into the map's upper layer.

    It is done on the `game_map` and not on the drawn image, and that solves
    three things at once: the layers are drawn from here —so the drawings of
    the ChipSet animation come out baked too—, the layer cache key carries the
    upper layer, so it changes by itself, and the cell's passability is
    resolved by `passability_map` with the tile's bits, which are the same the
    event's row imposed.
    """
    for cell, tile in bakeable.values():
        game_map.upper_layer[cell] = tile


def drawable_npcs(renderer, game_map, leaders, cap, route_graphics=(),
                  timer_colors=(), only_here=None, poses=None):
    """The map's NPCs that are drawn: all the ones with a CharSet, and the ones
    drawn with a chipset tile **that fit** in the sprite palettes.

    An event with a tile graphic is one more character for the console, with
    its palette, and there are eight sprite palettes. The game's CharSets use
    fifteen colors each and share none, so in a map with seven CharSet
    characters there is a single palette left for all the tiles, and two tiles
    that don't share colors don't fit. It happened in map 8: nine characters in
    nine palettes. Before this, tile events weren't drawn at all in any map
    —the door of map 2 was a black portal—, so drawing the ones that fit and
    warning about the ones that don't is strictly better.

    There is a single rule: first the possible leaders are placed, the NPCs
    with a CharSet and the graphics that routes change to with command 34
    —which are one more character, with its palette—, in map order and with the
    same first-place-that-fits as `build_characters`; then the tiles, in map
    order, each one while it fits. Returns the list of NPCs that are drawn and
    that of the (event, tile) left out.
    A tile left out isn't drawn, but its event is still there: it blocks the
    way and triggers all the same.
    """
    palettes = []
    palette_of = {}
    # Who had to be lent someone else's palette. They show up in the
    # converter's report: they don't break anything, but they are seen with
    # colors that aren't their own.
    lent = set()
    # The palettes of the possible leaders. **Nobody else goes in there**, and
    # not for tidiness: an event's flash —`FlashSprite`— on the console is a
    # CGRAM tint, so it tints the whole palette and with it everything sharing
    # it. RM2k, instead, applies it on the sprite image; that is, sharing the
    # hero's palette is a real difference from RM2k and not a packing detail.
    #
    # taro saw it on 2026-09-07 in the Emitter Room: when Talan absorbs Core's
    # anger and flashes red, two black tiles above some chests —invisible,
    # because they are all black— turned red with him. They shared palette 0
    # with `Future1:0`.
    #
    # The leader is protected and not "the one that flashes" because the target
    # of a flash can be any event and is decided at run time; the hero is the
    # one that flashes in this game and is the only one that can be known here.
    # If a flash on another event shows up, it will leak all the same.
    leader_owned = set()
    # Which poses each graphic can show, which is what its fifteen colors are
    # chosen over. Without it they are the usual twelve.
    poses = dict(poses or {})

    def fits(charset, index, force, leader=False):
        palette, _, _ = character_palette(renderer.charsets.get(charset),
                                          index,
                                          poses=poses.get((charset, index)))
        for number, existing in enumerate(palettes):
            if number in leader_owned and not leader:
                continue
            union = existing + [c for c in palette if c not in existing]
            if len(union) <= OBJ_COLORS:
                palettes[number] = union
                palette_of[(charset, index)] = number
                return True
        if force or len(palettes) < cap:
            if leader:
                leader_owned.add(len(palettes))
            palette_of[(charset, index)] = len(palettes)
            palettes.append(list(palette))
            return True
        # There is no palette for it, so **one is lent to it**: each color goes
        # to the nearest of the ones there are. It looks bad, but it shows.
        #
        # It used to be discarded, and taro cut that discussion short with the
        # argument that settles it: if we can't include all the events, the
        # whole project falls apart. And a sprite with odd colors is a
        # **visible** error; an invisible one is a trap, and it already cost us
        # an afternoon with the door Core breaks.
        #
        # How much it shows depends on the color jump, not on how many pixels
        # change: the pad's door changes 42% of its own with a jump of 1 out
        # of 31 and stays almost the same, while `Future3:1` changes 49% with
        # jumps of 17 and it does show.
        counts = sprite_colors(renderer.charsets.get(charset), index)
        best = None
        for number, existing in enumerate(palettes):
            if number in leader_owned:
                continue        # the ROM overwrites those with the leader's colors
            cost = sum(v for c, v in counts.items() if c not in existing)
            if best is None or cost < best[0]:
                best = (cost, number)
        if best is None:
            return False        # there isn't a single non-leader palette
        palette_of[(charset, index)] = best[1]
        lent.add((charset, index))
        return True

    npcs = collect_npcs(game_map)

    def keys(npc):
        """The (CharSet, index) pairs the NPC can end up drawing: its row's
        and, if the graphic follows the page, those of all its pages."""
        out = [(npc["charset"], npc["index"])]
        if npc["changes"]:
            out += [g[:2] for g in npc["graphics"] if g is not None]
        return out

    # The possible leaders, which are the ones the hero can end up drawing.
    #
    # **They share a single CGRAM slot**, because one leads at a time: the ROM
    # uploads the fifteen colors of whoever is leading when the party changes
    # and when loading the map. A palette used to be reserved for each, and
    # that is a palette taken by someone who isn't on screen: map 8 —the street
    # Talan's pad opens onto— asked for nine out of eight because of that, with
    # Talan and Kersh reserved on a street where neither appears.
    #
    # **Except the one that is also an NPC in this map.** That one gets its own
    # palette, because its row uses it at the same time as the hero: sharing
    # the slot, with Talan leading, the Kersh standing on the map would be
    # drawn with Talan's colors. It happens in maps 1 and 6 with Kersh and in 3
    # with Talan; in the other six of the PoC it doesn't, and that is where the
    # gain is.
    npc_keys = {c for npc in npcs for c in keys(npc)}
    seen, slot_leader, own = set(), None, set()
    for actor in leaders:
        a = renderer.database.actors[actor]
        key = (a.charset, a.charset_index)
        if key in seen or not sprite_colors(
                renderer.charsets.get(a.charset), a.charset_index):
            continue
        seen.add(key)
        if key in npc_keys or slot_leader is None:
            fits(a.charset, a.charset_index, True, leader=True)
            if key not in npc_keys:
                slot_leader = palette_of[key]
        else:
            # To the shared slot, and with **its own** colors: its poses are
            # packed with its sorted palette, which is the one the ROM uploads
            # when its turn to lead comes.
            palette_of[key] = slot_leader
            own.add(key)

    # The CharSets of the pages **are no longer forced**. They were forced so
    # that a character never ran out of palette, and the price was that a map
    # with more characters than palettes didn't convert: map 8 asked for nine
    # out of eight and the Hover-Tram asks for eleven. With the lending in
    # `fits` that is no longer needed —whoever doesn't fit is drawn with
    # someone else's— and no map fails because of this.
    #
    # The only one still forced is the leader: the hero is on screen all the
    # time and is the one where it would show the most.
    #
    # The order is the map's, **except the ones with weight**: see `graphic_weight`.
    for npc in sorted(npcs, key=lambda n: -graphic_weight(n["charset"])):
        for key in keys(npc):
            if key not in seen and not key[0].startswith(rm2k.TILE_PREFIX):
                seen.add(key)
                fits(key[0], key[1], False)
    # And the ones from command 34, after the NPCs and before the tiles.
    # **While they fit**, like the tiles and not like a page's CharSets: forcing
    # them broke three maps of the game —108, 114 and 207 asked for nine
    # palettes out of eight— and breaking a map that converts today is worse
    # than not drawing a graphic change. The one that doesn't fit isn't drawn,
    # which is the same that already happens with a page whose graphic didn't
    # fit. Transparent ones don't even ask for a palette.
    for key in route_graphics:
        if key not in seen and sprite_colors(
                renderer.charsets.get(key[0]), key[1]):
            seen.add(key)
            fits(key[0], key[1], False)
    # The timer **before the events drawn with a chipset tile**. Its two colors
    # go to the first palette with room and are reserved there;
    # `timer_digits` later finds them in place and adds nothing.
    #
    # The order matters and until now it was reversed by accident. A tile event
    # goes in "while it fits" —that is how it is written a few lines below, and
    # the one that doesn't fit isn't drawn—, while the timer is HUD and is on
    # screen always. In map 8 chipset tile 118, which is two colors, went into
    # the save point's palette and left it at fourteen: the timer no longer fit
    # anywhere and a whole character had to lose a color to make room for it.
    # Serving it first, nothing is merged and the tile settles in another
    # palette.
    if timer_colors:
        for number, existing in enumerate(palettes):
            if number in leader_owned:
                continue        # the ROM overwrites those with the leader's colors
            union = existing + [c for c in timer_colors if c not in existing]
            if len(union) <= OBJ_COLORS:
                palettes[number] = union
                break

    fit, outside, out, discarded = set(), set(), [], []
    for npc in npcs:
        for key in keys(npc):
            if key in seen or key in fit or key in outside:
                continue
            if fits(key[0], key[1], False):
                fit.add(key)
            else:
                outside.add(key)
        # The ones left out aren't drawn, from anywhere: the row is hidden if
        # it is its own, and the page that asks for it comes out with no
        # graphic.
        npc["afuera"] = {c for c in keys(npc) if c in outside}
        discarded += [(npc["event"], c[0]) for c in sorted(npc["afuera"])]
        if (npc["charset"], npc["index"]) in outside:
            npc["visible"] = False
            npc["tile_pass"] = None
            if not npc["changes"]:
                continue
            # The row stays for the other pages, hidden, and its fields move to
            # the first of them that fits: it is the slot it starts with. If
            # none fits, the event is never drawn.
            other = next((g for g in npc["graphics"]
                          if g is not None and g[:2] not in outside), None)
            if other is None:
                continue
            npc["charset"], npc["index"], npc["pose"] = other
        out.append(npc)
    # And last, the timer. Its digits are two colors and black is usually
    # already in almost all of them, so **one free entry** is enough; the
    # problem shows up in a map that fills the eight palettes to fifteen, which
    # is 8 —Lashe City, the street Talan's pad opens onto—.
    #
    # There room is made by lowering a fifteen-color character to fourteen,
    # and **the one that moves the fewest pixels** is chosen. Only palettes of
    # a single character are looked at: lowering one shared by two would force
    # requantizing both against the new palette, and that is a lot more code
    # for a case that doesn't come up. Leader ones aren't looked at either: the
    # ROM overwrites them.
    #
    # Measured in map 8: `BLVehicles:5` moves 105 pixels of 4648, 2.26%, with a
    # jump of 4 out of 31. The next candidate costs 11.84%.
    caps = {}
    # Only if it really has nowhere to go: not a palette with room **nor a free
    # slot**. Without looking at the free slots, this took two colors off
    # `People4:5` in map 5 —16.85% of its pixels— when the map uses four
    # palettes of the eight and the timer had a whole one to spare.
    if timer_colors and len(palettes) >= OBJ_PALETTES and not any(
            n not in leader_owned
            and len(set(p) | set(timer_colors)) <= OBJ_COLORS
            for n, p in enumerate(palettes)):
        singles = collections.Counter()
        for key, n in palette_of.items():
            singles[n] += 1
        best = None
        for key, n in palette_of.items():
            if n in leader_owned or singles[n] != 1 or key[0].startswith(
                    rm2k.TILE_PREFIX):
                continue
            # The ones in another map of the ROM go **last**, not out: the pose
            # bank is global, so quantizing it differently here than there
            # costs the cartridge one more bank, 6 KB. Until 2026-09-12 they
            # were excluded and that was enough, because in map 8 there was
            # always a single-map candidate; when the weighted graphics —the
            # save point— started being served first the split rearranged
            # itself, none was left, and the ROM with the timer stopped
            # building. Six kilobytes is worse than nothing and better than not
            # having a timer.
            foreign = only_here is not None and key not in only_here
            counts = sprite_colors(renderer.charsets.get(key[0]), key[1],
                                   poses.get(key))
            if not counts:
                continue
            missing = len([c for c in timer_colors if c not in palettes[n]])
            new_cap = OBJ_COLORS - missing
            m, _ = allocator.merge_least_visible(counts, new_cap)
            moved = sum(v for c, v in counts.items() if m[c] != c)
            cost = (foreign, moved / float(sum(counts.values())), key)
            if best is None or cost < best[0]:
                best = (cost, key, n, new_cap, sorted(set(m.values())))
        if best is not None:
            _cost, key, n, new_cap, new_palette = best
            print("  to make room for the timer, %s:%d drops to %d colors "
                  "(%.2f%% of its pixels)%s"
                  % (key[0], key[1], new_cap, 100 * _cost[1],
                     ", and with a pose bank of its own" if _cost[0] else ""))
            palettes[n] = new_palette
            caps[key] = new_cap

    # The split is returned so `build_characters` uses it as is: a second
    # first-place-that-fits in another order can give a different count, and
    # it did: map 8 fit here in eight palettes and there asked for nine.
    return out, discarded, (palettes, palette_of, own, leader_owned,
                            caps, lent, poses)


def build_characters(images, characters, slots, split):
    """The sprite bank that goes to VRAM: one pose per slot.

    `characters` is the list of (charset, index) that need a palette, in the
    order they are handed out; `slots` that of (key, charset, index, pose), a
    block of 16 tiles for each one and in that order. Since 2026-09-05 what
    goes here is **one pose per slot** and nothing else: the twelve of the
    walkers live in the cartridge —see `pose_bank`— and are uploaded on
    the fly. They all used to go here, and the opening scene asked for 768
    tiles of the 512 the PPU addresses.

    **Palettes are not decided here**: they arrive in `split`, which is what
    `drawable_npcs` decided for the whole map. Here only the index of each
    color inside its own is built. Until 2026-09-17 there was also a split of
    its own, first-that-fits, for when none arrived; nobody used it, and a
    second split in another order had already given a different count —map 8
    fit there in eight palettes and here asked for nine—.

    Returns (tiles, palettes, location, paleta_de): location maps the slot's
    key to (block, palette), and paleta_de each (charset, index) to its
    palette.
    """
    tiles = bytearray()
    colors = {}
    palettes = [list(p) for p in split[0]]
    palette_of = dict(split[1])
    # The ones that share the leader's slot: their `lookup` comes from **their**
    # palette and not from the slot's, because the ROM will upload their colors
    # there when their turn to lead comes. See `drawable_npcs`.
    own = set(split[2])
    # And who had their number of colors lowered so the timer would fit. It has
    # to be the same number `drawable_npcs` used: if here it were quantized
    # with fifteen, the cartridge's poses wouldn't match the palette the ROM
    # uploads to CGRAM.
    caps = dict(split[4])
    # And which poses each one can show, which is what their fifteen colors
    # were chosen over there. It has to be the same set: with another one, the
    # palette the ROM uploads to CGRAM and the tiles packed here would come
    # from two different computations.
    poses_of = dict(split[6])
    for charset, index in characters:
        if (charset, index) in colors:
            continue
        palette, lookup, mapping = character_palette(
            images[charset], index, caps.get((charset, index)),
            poses=poses_of.get((charset, index)))
        if (charset, index) not in palette_of:
            sys.exit("%s:%d is not in the palette split" % (charset, index))
        if (charset, index) in own:
            colors[(charset, index)] = (lookup, mapping)
            continue
        union = palettes[palette_of[(charset, index)]]
        # The colors that aren't in the palette it got go to the nearest of the
        # ones there are. It happens when the map ran out of palettes and
        # `drawable_npcs` lent it someone else's: it looks bad, but it shows.
        lookup = {}
        for color in palette:
            if color in union:
                lookup[color] = union.index(color) + 1
            else:
                near = min(union,
                           key=lambda p, c=color: allocator.luma_distance(p, c))
                lookup[color] = union.index(near) + 1
        colors[(charset, index)] = (lookup, mapping)

    where = {}
    for block, (key, charset, index, pose) in enumerate(slots):
        lookup, mapping = colors[(charset, index)]
        where[key] = (block, palette_of[(charset, index)])
        first = block_tile(block)
        # The block doesn't take 16 consecutive tiles: it is a 4x4 square inside
        # a grid 16 wide, so the gap has to be left.
        needed = (first + 3 * OBJ_ROW + 4) * 32
        if len(tiles) < needed:
            tiles += bytes(needed - len(tiles))
        for i, tile in enumerate(pose_tiles(images[charset], index, pose,
                                            lookup, mapping)):
            number = first + (i // 4) * OBJ_ROW + (i % 4)
            tiles[number * 32:(number + 1) * 32] = tile
    return bytes(tiles), palettes, where, palette_of, colors


# A pose in the cartridge: the 16 tiles in a row, by rows.
POSE_BYTES = 16 * 32


def pose_bank(images, characters, colors):
    """The twelve poses of each character that changes pose, for the cartridge.

    One block per character —twelve poses of 512 bytes, 6 KB— and not one for
    all: each goes with `.block`, so no DMA of a pose crosses a bank. And
    **from the whole ROM, not from the map**: maps 1 and 2 share Core, Manta
    and Kersh, and with one copy per map the boot-with-window ROM went over the
    cartridge by 19 KB. `emit` splits them into poses and emits each distinct
    pose only once; the map carries its animated characters in order and
    `emit` translates.
    """
    banks = {}
    for charset, index in characters:
        # With the lookup from `build_characters`, which is that of the palette
        # it ended up packed in: a pose uploaded on the fly is drawn with the
        # palette already in CGRAM.
        lookup, mapping = colors[(charset, index)]
        data = bytearray()
        for pose in range(SPRITE_POSES):
            for tile in pose_tiles(images[charset], index, pose, lookup,
                                   mapping):
                data += tile
        banks[(charset, index)] = bytes(data)
    return banks


# The timer: eleven 8x16 glyphs in the System, starting at (32, 32). Ten digits
# and the colon, which is all `Sprite_Timer::Draw` draws.
TIMER_GLYPHS = 11
TIMER_GLYPH_W, TIMER_GLYPH_H = 8, 16
TIMER_ORIGIN = (32, 32)
# Where it is drawn on screen. `Sprite_Timer` puts it at `menu_offset_x + 4`
# and `menu_offset_y + 4`, and with a screen narrower than the menu both
# offsets come out zero.
TIMER_X, TIMER_Y = 4, 4


def timer_colors_of(sys_img):
    """The colors the timer's eleven glyphs use.

    It is needed **before** splitting the palettes and not only when packing
    the digits: if a map fills all eight, someone has to be chosen to lose a
    color to make room for it, and that decision changes how that character is
    quantized.
    """
    colors = collections.Counter()
    for i in range(TIMER_GLYPHS):
        for y in range(TIMER_GLYPH_H):
            for x in range(TIMER_GLYPH_W):
                r, g, b, a = sys_img.getpixel((TIMER_ORIGIN[0] + i * 8 + x,
                                               TIMER_ORIGIN[1] + y))
                if a:
                    colors[(r >> 3, g >> 3, b >> 3)] += 1
    return colors


def timer_digits(sys_img, tiles, palettes, leader_owned=(),
                     cap=OBJ_PALETTES):
    """The timer's eleven glyphs, at the end of the sprite bank.

    Each goes as two stacked 8x8 tiles, and all eleven fit in a row of
    sixteen: glyph i takes tile `base + i` and `base + 16 + i`. The base is
    rounded up to a row so that computation holds.

    Returns (tiles, base, palette number). **It doesn't take a palette of its
    own unless needed**: they are two colors —black and pure red— and fit
    easily in that of any character with thirteen or fewer, exactly like the
    events drawn with a chipset tile fit. One is added only if none has room.

    Reserving it up front cost one palette of the eight, and that is not
    bookkeeping: `drawable_npcs` decides with that number **which events are
    drawn**. On 2026-09-07, when building `demo-apertura` with the timer, map 2
    lost two events, and one was the middle one of the door Core breaks: taro
    reached the cutscene, the door didn't change tile and he couldn't get
    through. An event that isn't drawn **still takes space**, so the loss is
    not only visual.
    """
    colors = timer_colors_of(sys_img)
    if len(colors) > OBJ_COLORS:
        raise SystemExit("the timer digits use %d colors and %d fit"
                         % (len(colors), OBJ_COLORS))
    wanted = sorted(colors)
    # The first palette its colors fit in without merging anything. It is the
    # same first-fit as `build_characters` and for the same reason.
    #
    # **Except the leader slots.** The ROM overwrites those with the fifteen
    # colors of whoever is leading every time the party changes or a map
    # loads, so a digit put there would lose its red as soon as Talan hands
    # the lead to Kersh. In the seven maps of `demo-apertura` it doesn't land
    # in any today, which is exactly what made the error invisible.
    for number, existing in enumerate(palettes):
        if number in leader_owned:
            continue
        union = list(existing) + [c for c in wanted if c not in existing]
        if len(union) <= OBJ_COLORS:
            palettes[number] = union
            palette, which = union, number
            break
    else:
        if len(palettes) >= cap:
            raise SystemExit(
                "the timer doesn't fit: the map already uses the %d sprite "
                "palettes it gets and none has room for its %d colors"
                % (cap, len(wanted)))
        palette, which = list(wanted), len(palettes)
        palettes.append(palette)
    index = {color: palette.index(color) + 1 for color in wanted}

    tiles = bytearray(tiles)
    # The base is rounded up to a **row of blocks**, 64 tiles, and not to a
    # grid row: the 4x4 blocks of the last row of blocks take four grid rows,
    # and with the small VRAM image there is since poses go on the fly,
    # rounding to 16 left the glyphs on top of the last row of the hero's
    # block. Nothing showed there until the hero's pose was uploaded and
    # overwrote the 0 and the colon.
    base = -(-(len(tiles) // 32) // 64) * 64
    if (base + 16 + TIMER_GLYPHS) * 32 > len(tiles):
        tiles += bytes((base + 16 + TIMER_GLYPHS) * 32 - len(tiles))
    for i in range(TIMER_GLYPHS):
        for half in (0, 1):
            cell = []
            for y in range(CELL):
                row = []
                for x in range(CELL):
                    r, g, b, a = sys_img.getpixel(
                        (TIMER_ORIGIN[0] + i * 8 + x,
                         TIMER_ORIGIN[1] + half * CELL + y))
                    row.append(index[(r >> 3, g >> 3, b >> 3)] if a else 0)
                cell.append(tuple(row))
            number = base + half * 16 + i
            tiles[number * 32:(number + 1) * 32] = pack_tile(tuple(cell),
                                                             planes=4)
    return bytes(tiles), base, which


def rain_drops(tiles, palettes, leader_owned=(), timer_base=None,
                   cap=OBJ_PALETTES, timer_pal=None):
    """The six raindrop tiles —above and below the streak, in the three
    grays— and the palette their colors go in. See OP_WEATHER in events.py.

    It is the same as `timer_digits`: the colors go in the first
    character palette with room, except the leader ones, and the tiles at the
    end of the bank. If the timer is there, in its same row of sixteen, which
    has five places to spare; if not, in a row of blocks of its own. Tone `t`
    above is tile `base + t` and below `base + 16 + t`. Returns (tiles, base,
    palette number).

    **And not in the timer's either.** The reason was that `upload_timer_pal`
    uploaded that whole palette again **untinted** —the digits go above the
    tint, `Priority_Timer` is 140 and `Priority_Screen` 90—, and a drop put
    there stayed gray on a tinted screen; rain is tinted in RM2k,
    `Priority_Weather` is 80. Since 2026-09-25 it uploads only the digits'
    entries, so a drop wouldn't stay gray anymore, except in a color it shared
    with them. It is still avoided because removing it can move where the
    drops land, and that wasn't measured.
    """
    wanted = [c for c in events.RAIN_COLORS]
    avoid = set(leader_owned)
    if timer_pal is not None:
        avoid.add(timer_pal)
    which = _first_place(palettes, avoid, wanted, cap)
    if which is None:
        # No room: this map doesn't draw rain. Nobody loses a color to make
        # room for it, unlike the timer: that would change the split, and the
        # split is what decides which colors each map has.
        return bytes(tiles), 0, 0
    palette = palettes[which]
    tiles = bytearray(tiles)
    if timer_base:
        base = timer_base + TIMER_GLYPHS
    else:
        base = -(-(len(tiles) // 32) // 64) * 64
    if (base + 16 + 3) * 32 > len(tiles):
        tiles += bytes((base + 16 + 3) * 32 - len(tiles))
    streak = set(events.rain_pixels(0, 0))
    for hue, color in enumerate(wanted):
        index = palette.index(color) + 1
        for half in (0, 1):
            cell = tuple(tuple(index if (x, half * CELL + y) in streak else 0
                               for x in range(CELL)) for y in range(CELL))
            number = base + half * 16 + hue
            tiles[number * 32:(number + 1) * 32] = pack_tile(cell, planes=4)
    return bytes(tiles), base, which


def picture_of_image(info, tiles, palettes, previous_base=None):
    """The `ShowPicture` picture at the end of the sprite bank: its tiles and **a
    whole palette just for it**.

    It shares a palette with nobody, unlike the timer and the drops, and not
    for lack of room: the picture's fade is a tint of its fifteen CGRAM entries
    frame by frame, so a character put in that palette would fade out and back
    in with it.

    And it goes **above `SPRITE_CGRAM`**, that is outside the range
    `apply_tint` and `upload_palettes` walk. That is not shuffling numbers: in
    RM2k pictures have `affected_by_tint` off by default
    —`Priority_PictureOld` is 120 and `Priority_Screen` 90—, so the screen tint
    doesn't touch them. Being outside the range, nobody has to remember to
    skip them.

    Returns (tiles, base, palette number), or (tiles, 0, 0) if the map already
    uses the eight sprite palettes: then this map doesn't draw the picture.
    """
    if len(palettes) >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    which = len(palettes)        # the first free one, without adding it to the list
    tiles = bytearray(tiles)
    if previous_base:
        base = -(-(previous_base + 2 * 16) // 64) * 64
    else:
        base = -(-(len(tiles) // 32) // 64) * 64
    count = picture.reserved_tiles(info)
    if (base + count) * 32 > len(tiles):
        tiles += bytes((base + count) * 32 - len(tiles))
    for number, cell in picture.cells(info).items():
        tiles[(base + number) * 32:(base + number + 1) * 32] = pack_tile(
            cell, planes=4)
    return bytes(tiles), base, which


def map_shows_animation(game_map, renderer, commands=()):
    """Whether some page of this map can draw a battle animation.

    It is looked at on the raw commands and not on the already compiled
    bytecode, and on purpose: VRAM has to be reserved when converting the map
    and the pages are compiled afterwards. It is a superset —a page that in the
    end doesn't compile leaves 64 tiles reserved and unused— and it has to be:
    if the bytecode showed an animation the map didn't reserve, the ROM would
    write the tiles on top of a character's.

    `commands` are those of the test pages, which don't come from the map.
    """
    numbers = set()
    for cmd in list(commands) + [cmd for event in game_map.events
                                 for page in event.pages
                                 for cmd in page.commands]:
        if (cmd.code == events.SHOW_BATTLE_ANIMATION
                and len(cmd.parameters) >= 3):
            numbers.add(cmd.parameters[0])
    return any(animation_mod.by_number(renderer, n) is not None
               for n in numbers)


def map_animation(tiles, palettes, used=0):
    """The battle animation box at the end of the sprite bank: its 64 tiles
    and **a whole palette just for it**.

    It shares a palette with nobody for the same reason as the picture: the
    fifteen colors belong to the animation, are uploaded when it starts and
    overwritten when another starts, and a character put there would change
    color with it. And it goes **above `SPRITE_CGRAM`**, that is outside the
    range `apply_tint` and `upload_palettes` walk, which is also the faithful
    thing: in `Spriteset_Map::Update` the map's tone goes to the tilemap, the
    characters, the panorama and the shadows, and not to the animations.

    The tiles are reserved **blank**: what goes inside is uploaded by the ROM
    via DMA frame by frame, from the cartridge. See `animation.py`.

    Returns (tiles, base, palette number), or (tiles, 0, 0) if the map already
    uses the eight sprite palettes. `used` are the ones the picture already
    took.
    """
    which = len(palettes) + used
    if which >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    tiles = bytearray(tiles)
    # After everything else: the timer, the drops and the picture already grew
    # `tiles` to cover theirs, so the end of the bank is the length. Rounded up
    # to a **row of blocks**, which is what the arithmetic of 32x32 objects
    # needs whole.
    base = -(-(len(tiles) // 32) // 64) * 64
    if (base + animation_mod.TILES) * 32 > len(tiles):
        tiles += bytes((base + animation_mod.TILES) * 32 - len(tiles))
    return bytes(tiles), base, which


def map_palette_cap(renderer, game_map, leaders, graphics,
                    timer_colors, singles, poses, sample_animation):
    """How many sprite palettes this map can split among its characters: all
    eight, or **seven** if it shows battle animations.

    The animation box needs a whole palette just for it, and the two maps of
    the intro —2 and 3, which are the ones the scene uses— filled all eight.
    Taking one away from the characters is what gives the Emitter Room scene
    its drawing; what it costs is merged colors, and each map's report says so.

    **Unless the timer doesn't fit with seven**, which is not negotiable:
    without its two colors there is no timer in the whole ROM. Then it goes
    back to eight and this map doesn't draw animations, which is what happens
    to map 9.

    It lives on its own and not inside `convert_map` because it is a split
    decision and not a detail of `convert_map`.
    """
    if not sample_animation:
        return OBJ_PALETTES
    minus = OBJ_PALETTES - 1
    if timer_colors:
        split = drawable_npcs(renderer, game_map, leaders, minus, graphics,
                              timer_colors, singles, poses)[2]
        clone = [list(p) for p in split[0]]
        if _first_place(clone, split[3], list(timer_colors),
                        minus) is None:
            return OBJ_PALETTES
    return minus


def _first_place(palettes, leader_owned, colors, cap=OBJ_PALETTES):
    """The first palette —except the leader ones— where `colors` fit without
    merging anything, or a new one if a slot is left; it adds or grows it and
    returns its number, or None if there is no room.

    `cap` is how many sprite palettes this map can use, which **isn't always
    all eight**: a map that shows battle animations reserves one for the
    animation box, and neither the timer nor the drops can take it. See
    `palette_cap` in `convert_map`.
    """
    for number, existing in enumerate(palettes):
        if number in leader_owned:
            continue
        union = list(existing) + [c for c in colors if c not in existing]
        if len(union) <= OBJ_COLORS:
            palettes[number] = union
            return number
    if len(palettes) < cap:
        palettes.append(list(colors))
        return len(palettes) - 1
    return None


def maps_per_character(renderer, map_ids, game_dir):
    """How many maps of the ROM each (CharSet, index) appears in."""
    counts = collections.Counter()
    for other in map_ids:
        gm = renderer.load_map(os.path.join(game_dir, "Map%04d.lmu" % other))
        theirs = set()
        for event in gm.events:
            for page in event.pages:
                name = (getattr(page, "character_name", "") or "").strip()
                if name:
                    theirs.add((name, page.character_index))
        counts.update(theirs)
    return counts


def has_rain(map_ids, extra=()):
    """Whether some page of these maps sets rain: then every map of the ROM
    carries the drops, because the weather persists across map changes.
    `extra` are the commands of the test pages."""
    def rains(cmd):
        return (cmd.code == events.WEATHER_EFFECTS
                and cmd.parameters[:1] == [events.WEATHER_RAIN])
    if any(rains(cmd) for cmd in extra):
        return True
    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_game(),
                                        "Map%04d.lmu" % map_id))
        for event in game_map.events:
            for page in event.pages:
                for cmd in page.commands:
                    if rains(cmd):
                        return True
    return False


def npc_table(npcs, where, movable=(), animated_index=None, animates_still=()):
    """The NPCs ready for the ROM, already sorted the way RM2k draws them.

    The drawing order is first by layer and only then by Y: a "below" one stays
    below the hero even if it is further forward on screen. On the console,
    the object with the lowest OAM index is the one shown on top, so the table
    goes from front to back.

    **This initial order also rules afterwards.** The walking ones change Y
    and the ROM re-sorts them one at a time, with an insertion that respects
    the order of ties: between two tied ones the order of this list still
    holds.

    The ones in `movable` also carry which cartridge pose bank their twelve
    are in, so the ROM uploads them on the fly while they walk.
    """
    rows = []
    for npc in sorted(npcs, key=drawing_order, reverse=True):
        walks = npc["event"] in movable
        key = (("ev", npc["event"]) if walks
               else (npc["charset"], npc["index"], npc["pose"]))
        block, slot = where[key]
        rows.append({
            "x": npc["x"] * 16, "y": npc["y"] * 16,
            "tile": block_tile(block), "palette": slot,
            "layer": npc["layer"], "blocks": npc["blocks"],
            "event": npc["event"], "dir": npc["pose"] // 3,
            "pose": npc["pose"],
            "poses": (animated_index[(npc["charset"], npc["index"])]
                      if walks else None),
            "speed": npc.get("speed", 3),
            # The still ones with continuous animation: their column comes from
            # the game clock. The walking ones carry it in their route slot, so
            # the flag doesn't apply to them even if their page asks for it too.
            "animates": npc["event"] in animates_still,
            "visible": npc.get("visible", True),
            "tile_pass": npc.get("tile_pass"),
        })
    return rows


# --- conversion -------------------------------------------------------------

def build_palette(grid, bg_colors, others=()):
    """The map's colors, in a single table, merging only if there are too many.

    At 8 bits per pixel the only limit is how many CGRAM entries are left free
    below the upper layer. Map0007 uses 60, so nothing is merged; the merge
    path exists for more loaded maps and is `allocator.reduce_colors`.

    `others` are the grids of the other drawings of the ChipSet animation. They
    count for the palette like the usual drawing —the water of map 5 brings
    three colors that aren't in its step 0, and without them step 1 couldn't
    be written with this palette— and come out merged with the same
    `mapping`, which is what keeps them comparable with each other.
    """
    counts = _colors_of((grid,) + tuple(others))
    if len(counts) <= bg_colors:
        return sorted(counts), grid, list(others), []

    mapping, merged = allocator.merge_least_visible(counts, bg_colors)

    def merge(g):
        return [[tuple(tuple(mapping.get(p) for p in line) for line in tile)
                 for tile in row] for row in g]

    return (sorted({c for c in mapping.values()}), merge(grid),
            [merge(g) for g in others], merged)


_LAYERS_VERSION = None


def _layers_version():
    """Which version of the code produced whatever is stored under `layers`.

    It is the six pieces that take part in drawing or converting, plus the
    three programs that aren't sources of this tree:

    * **the `rm2k-render` binary** draws the layers and expands the
      ChipSet, and `render/render_map.py` is what hands it the map and reads
      back what it drew. Until 2026-09-20 they weren't needed, because the
      key was the already drawn pixels: changing the drawing changed the key
      by itself. Since the key comes from the inputs, the only way for a change
      in the drawing to invalidate what is stored is this one: recompiling
      the binary without touching any `.py` has to invalidate it.
      `rpgmaker/resources.py` goes with them because it is where `render_map`
      gets how it finds the ChipSet, and `common/project.py` because it is
      where the directories it searches in come from;
    * `port/allocator.py` decides which colors are lost, `rpgmaker/rm2k.py`
      has the constants of the split and of the animated families, and this
      file does the rest;
    * **the Voodoo binary**, which is the one that emits the tiles:
      recompiling it without touching any `.py` has to invalidate what is
      stored;
    * **the Pillow version**, which reads back the layers `rm2k-render`
      wrote and is what the conversion works on. Until 2026-09-29 it also
      decoded the ChipSet and composed the tiles; reading a PNG is not
      supposed to change between versions, but nothing proves it, and it
      costs nothing to keep.

    What does **not** go in, on purpose: `rpgmaker/lcf.py`. What it reads from
    the dump —the two layers, the size, the ChipSet's passability— goes in by
    its value in `layer_inputs`, so a change in how it is read only
    matters if what is read changes, and then the key changes by itself.
    """
    global _LAYERS_VERSION
    if _LAYERS_VERSION is None:
        import PIL
        from common import disk_cache
        _LAYERS_VERSION = (disk_cache.version_of("port/snes_convert.py",
                                                 "port/allocator.py",
                                                 "rpgmaker/rm2k.py",
                                                 "render/render_map.py",
                                                 "rpgmaker/resources.py",
                                                 "common/project.py")
                           + render_map.version()
                           + tiles_bin.version()
                           + " Pillow " + PIL.__version__)
    return _LAYERS_VERSION


def converted_layers(renderer, game_map):
    """The map's layers converted, remembered on disk. `None` if there is no
    ChipSet.

    It is the most expensive part of the converter end to end: **drawing** the
    two layers and the drawings of their animations with Pillow, and then
    quantizing them, cutting them into tiles and splitting CGRAM.

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
    on_disk = None
    if inputs is not None:
        on_disk = disk_cache.key(_layers_version(), *inputs)
        if on_disk in _layers_in_memory:
            return _layers_in_memory[on_disk]
        done = disk_cache.read("capas", on_disk)
        if done is not None:
            _layers_in_memory[on_disk] = done
            return done
    base, above_img, variants = renderer.animated_layers(game_map)
    if base is None:
        return None
    done = _convert_layers(base, above_img, variants)
    if on_disk is not None:
        disk_cache.write("capas", on_disk, done)
        _layers_in_memory[on_disk] = done
    return done


# The layers already converted in this run, keyed by the disk cache key.
# `precompute_layers` fills it and it also works with `NO_CACHE=1`: it is not
# a cache between runs but the same computation done earlier and in parallel.
_layers_in_memory = {}


def precompute_layers(renderer, map_ids, args):
    """The layers of all maps, converted in parallel before `convert_map` asks
    for them.

    It is the most expensive part of a cold build —or of a warm one after
    touching this file, which invalidates the stored layers— and each map is
    independent, so there is one process per map. The processes fork with all
    the state already built, prepare the map like `convert_map` does and return
    what they computed with its key; `convert_map` then asks for the same key.
    **A map prepared differently here than there doesn't give a different
    ROM**: it gives another key, and `convert_map` computes it as always.
    """
    if len(map_ids) < 2:
        return
    global _to_precompute
    _to_precompute = (renderer, args)
    processes = min(len(map_ids), os.cpu_count() or 1)
    with multiprocessing.get_context("fork").Pool(processes) as pool:
        for done_ones in pool.map(_map_layers, map_ids, chunksize=1):
            _layers_in_memory.update(done_ones)
    _to_precompute = None


_to_precompute = None


def _map_layers(map_id):
    """What `precompute_layers` does in each process: the same steps as
    `convert_map` up to its two calls to `converted_layers`."""
    renderer, args = _to_precompute
    try:
        # Quiet: whatever it has to say, `convert_map` says it, in order.
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            game_map = renderer.load_map(
                os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
            separate_from_hero(renderer, game_map, args,
                               case_commands(args, map_id))
            converted_layers(renderer, game_map)
            baked = bakeable_events(renderer, game_map)
            if baked:
                bake_into_map(game_map, baked)
                converted_layers(renderer, game_map)
    except BaseException:
        # If it fails, let it fail in `convert_map`, which can say why.
        pass
    return _layers_in_memory


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

    # What the allocator decided, as indexed images: color `k` of the palette
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
    # tools/voodoo/README.md.
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


# --- the map as 16x16 blocks ------------------------------------------------
# The PPU tilemap doesn't go beyond 64x64 cells, and on top of that VRAM has to
# be shared with the tiles, so the window left for it is 64x32: 512x256 pixels
# against the 256x224 of the screen. The game's maps reach 1000x80 cells, so
# the whole map is never in VRAM: the ROM keeps redrawing the column and the
# row that come in while the camera moves.
#
# What is stored in the ROM isn't the expanded tilemap either. An RM2k 16x16
# cell is four SNES 8x8 cells, and it is the unit the game was drawn with: it
# repeats a lot. Storing an index into a table of blocks, the heaviest map
# goes from 175 KB —more than the whole ROM— to 40.
#
# The block carries both layers together and the passability. Passability
# going into the block isn't free: two cells that are drawn the same could
# have different permissions if they came from different ChipSet tiles, so it
# goes in the key and they separate by themselves.
WINDOW_W, WINDOW_H = 64, 32     # the tilemap window that lives in VRAM
MAP_LAYOUT = 1                  # two 32x32 screens side by side, which is 64x32
BLOCK_BYTES = 16                # four BG1 cells and four BG2 cells

# --- the VRAM layout --------------------------------------------------------
# The 64 KB can't be split any way one likes: the base of the sprite tiles
# goes in steps of 16 KB, that of each background in steps of 8 KB and that of
# each tilemap in steps of 2 KB. Which layout applies is decided by the
# converter and travels in the .inc: the ROM chooses nothing.
#
# Every map carries the message window —since 2026-09-17 it isn't optional; a
# map without a text window doesn't exist in practice— and there are three
# layouts that make room for it. Until that day there were three others
# without it. The window needs 8 KB of its own tiles —the text is 240 tiles
# and there is no way to lower that, because a 6 px glyph doesn't align to
# 8-pixel cells and it has to be composed pixel by pixel— plus **2 KB of its
# own tilemap**, and the 64 KB were already 100% allocated.
#
# What makes the tiles part possible is that `above` and `window` end up
# **adjacent**: BG2 has a single base and its tile indices are 10 bits, so 0
# to 255 fall in the first 8 KB bank and 256 to 511 in the next. That forces
# putting the sprites first, because the OBJ base goes in steps of 16 KB and
# a background's in steps of 8.
#
# And the tilemap of its own comes from trimming tiles from the sprites, which
# is where they are left over. Measured over the 318 maps that convert, the
# one that spends the most uses **380 sprite tiles**: 253 use 192 or fewer, 58
# between 193 and 256, and 7 between 257 and 380. With 448 none falls short,
# and the 2 KB freed land at word $1C00, which is a multiple of 1024 and
# therefore a valid tilemap base.
#
#   sprites   $0000  14 KB  448 4bpp tiles      OBJ base at 0
#   ventana_map $1C00 2 KB  the window's 32x32 tilemap
#   tiles     $2000  24 KB  384 8bpp tiles
#   encima    $5000   8 KB  256 tiles           <- the BG2 base
#   ventana   $6000   8 KB  256 tiles           <- indices 256..511
#   tilemaps  $7000   8 KB
#
# The second trades sprite tiles for background tiles, for the maps that
# spend more background, and there the 2 KB can't come from the sprites —those
# maps use up to 320— but from the background: 480 tiles instead of 512.
#
#   sprites     $0000   8 KB  256 tiles
#   tiles       $1000  30 KB  480 8bpp tiles
#   ventana_map $4C00   2 KB
#   encima      $5000   8 KB
#   ventana     $6000   8 KB
#   tilemaps    $7000   8 KB
#
# Measured over the 318 maps that convert: 309 fit in the first, 6 in the
# second and 3 didn't fit in either —8, 66 and 250—. **8 no longer**: on
# 2026-09-07, with the window moved to palette 0, its background tiles went
# down to 400 and it fits in the second layout. The number above is from
# before that and wasn't measured again over the 318.
#
# The old number written here was 2, and it was wrong for a reason worth
# stating: `vram_layout` didn't check that the background tiles fit in the
# bank of the chosen layout. `MAX_TILES` is 1024, which is the cap of the
# tilemap index and not of the bank, so maps 66 and 250 —518 and 620
# background tiles— took the 512 layout and spilled over the upper layer. It
# was never seen because no recipe asks for a window for them.
# The layout above gave 384 background tiles, and the one after it traded
# sprites for background. Both gave **256 tiles to the upper layer**, and
# measured that is a waste: over the 328 maps that convert, the median use is
# **1 tile** and 326 fit in 128. Lowering it to 128 frees 4 KB, which at 8bpp
# is 64 more background tiles.
#
# It was needed on 2026-09-07, when drawing all the events —see `fits`— took
# map 8 to 400 background tiles and 347 sprite ones, and there was no layout
# that gave it both.
#
# The puzzle is one of alignment and not of space: `BG12NBA` fixes the BG1 and
# BG2 bases at multiples of 8 KB, `OBSEL` that of the objects at multiples of
# 16 KB, and the tilemaps at multiples of 1 KB. The tilemaps moved to $5800
# and $7800, which are the only two gaps left aligned in the four layouts.
LAYOUT_WINDOW = {"sprites": (0x0000, 448), "ventana_map": (0x1C00, 1),
                 "tiles": (0x2000, 448), "mapa": (0x5800, 1),
                 "encima": (0x6000, 128), "ventana": (0x6800, 256)}
LAYOUT_WINDOW_BG = {"sprites": (0x0000, 256), "tiles": (0x1000, 480),
                    "ventana_map": (0x4C00, 1), "mapa": (0x5800, 1),
                    "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# And the third, which does the opposite of the second: it trades background
# tiles for sprite tiles. Delcentric Factory asked for it —map 17, the road to
# the auditorium—, which spends **217 background tiles and 475 sprite ones**
# and didn't fit in either of the two: 28 character slots are exactly 448
# tiles, and on top of that go the 8 timer glyphs and the 19 raindrops. That
# is 27 tiles too many over the 448 of the first layout, and the rain can't be
# removed because the weather persists across map changes and it rains in the
# opening.
#
#   sprites     $0000  16 KB  512 4bpp tiles      OBJ base at 0
#   tiles       $2000  24 KB  384 8bpp tiles      <- the BG1 base
#   ventana_map $5000   2 KB  the window's 32x32 tilemap
#   (free)      $5400   2 KB
#   tilemap     $5800   4 KB
#   encima      $6000   8 KB  128 tiles           <- the BG2 base
#   ventana     $6800   8 KB  256 tiles           <- indices 128..383
#   tilemap     $7800   4 KB
#
# 512 is the hardware cap and not a choice: the OAM name field is nine bits,
# and with `OBSEL`'s name select at zero both tables end up adjacent, which is
# exactly what `OBSEL_VALUE` emits. That is, this layout gives the sprites all
# the console can address.
#
# The 2 KB free at $5400 are the price of alignment: the BG1 base goes in
# steps of 8 KB, so lowering the background from 448 to 384 tiles frees 8 KB
# and the window needs 2. They can't be used for anything because there is
# nothing else to place.
#
# **It goes last on purpose.** `vram_layout` returns the first one that fits,
# so no map that already had a layout changes layout because of this: only
# the ones that didn't fit in the other two take it.
LAYOUT_WINDOW_SPRITE = {"sprites": (0x0000, 512), "tiles": (0x2000, 384),
                        "ventana_map": (0x5000, 1), "mapa": (0x5800, 1),
                        "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# And the fourth, the only one that **moves the map's tilemap**: `Sector 34
# With Car` asked for it, map 38, which spends **476 background tiles and 347
# sprite ones** and didn't fit in any of the three —it lacked 28 background
# tiles in the first and 91 sprite ones in the second—. In bytes it did fit;
# what didn't allow it was the tilemap fixed at $5800, which cut the BG1 bank
# at 448 tiles. Moving it down to the 2 KB left free between the sprites and
# the background:
#
#   sprites     $0000  12 KB  384 4bpp tiles      OBJ base at 0
#   mapa        $1800   4 KB  the BG1 tilemap     <- down here, not at $5800
#   tiles       $2000  30 KB  480 8bpp tiles      <- the BG1 base
#   ventana_map $5C00   2 KB  the window's 32x32 tilemap
#   encima      $6000   8 KB  128 tiles           <- the BG2 base
#   ventana     $6800   8 KB  256 tiles           <- indices 128..383
#   tilemap     $7800   4 KB  the upper layer's, which doesn't move
#
# 480 is the ceiling with 347 sprites even if the tilemap could go anywhere
# —measured by enumerating every base the hardware allows—: the BG1 bank
# starts at $2000 because the sprites go past $1000, and the window's tilemap
# needs a base that is a multiple of 1024 words after the background.
#
# The tilemap moving is paid for by `build_column` and `build_row`, which add
# `FAR_VRAM_MAP` instead of a constant, and by the step to the upper layer in
# `push_strips`, which masks instead of adding a fixed distance. That is why
# **both bases have to be multiples of 2048 words**, and the map's can't be
# zero: `col_addr` at zero means "no column". `_check_splits` checks it.
#
# **It goes last on purpose**, for the same reason as the previous one: no
# map that already fit changes layout.
LAYOUT_WINDOW_BOTH = {"sprites": (0x0000, 384), "mapa": (0x1800, 1),
                      "tiles": (0x2000, 480), "ventana_map": (0x5C00, 1),
                      "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# And the fifth, the ceiling of "+fondo": the world asked for it, map 66,
# which spends **527 background tiles and 222 sprite ones** and didn't fit in
# any of the four —the one that gives the most background with 222 sprites is
# the 480 of "+fondo" and "+ambos"—. With 256 sprites the hardware gives 544
# (see docs/port/vram.md, "Dónde está el techo"), and "+fondo" stays 64 below
# only because raising it would change the layout of the maps that already
# use it. It is "+fondo" with the ventana_map and the tilemap shifted behind
# the background:
#
#   sprites     $0000   8 KB  256 4bpp tiles      OBJ base at 0
#   tiles       $1000  34 KB  544 8bpp tiles      <- the BG1 base
#   ventana_map $5400   2 KB  the window's 32x32 tilemap
#   tilemap     $5800   4 KB
#   encima      $6000   8 KB  128 tiles           <- the BG2 base
#   ventana     $6800   8 KB  256 tiles           <- indices 128..383
#   tilemap     $7800   4 KB
#
# 544 8bpp tiles are 34 KB, more than the LZ2 buffer: that is why the
# background goes in two streams —see `compressed_parts`—.
#
# **It goes last on purpose**, for the same reason as the two previous ones.
LAYOUT_WINDOW_BG_CEILING = {"sprites": (0x0000, 256), "tiles": (0x1000, 544),
                            "ventana_map": (0x5400, 1), "mapa": (0x5800, 1),
                            "encima": (0x6000, 128), "ventana": (0x6800, 256)}

# And the sixth, the only one that **moves the BG2 base**: Sorbe Village asked
# for it, map 69, which spends **329 background tiles, 157 upper ones and 283
# sprite ones**. The other five give the upper layer 128 tiles, because the
# window starts at BG2 index 128 and the upper tilemap is fixed at $7800. With
# the BG2 base at $5000 the upper layer has 256, and the window goes after it:
#
#   sprites     $0000  12 KB  384 4bpp tiles      OBJ base at 0
#   mapa        $1800   4 KB  the BG1 tilemap, as in "+ambos"
#   tiles       $2000  24 KB  384 8bpp tiles      <- the BG1 base
#   encima      $5000   8 KB  256 tiles           <- the BG2 base
#   ventana     $6000   8 KB  256 tiles           <- indices 256..511
#   ventana_map $7000   2 KB  the window's 32x32 tilemap
#   (free)      $7400   2 KB
#   tilemap     $7800   4 KB  the upper layer's, which doesn't move
#
# What it costs is that the window starts at index 256 and not 128, and its
# cells carry that index baked in: that is why there are **two layouts** of
# the window, one for each base the VRAM layouts use —see `ventana_bases`—,
# and `stamp_window` picks its own by looking at where the window ended up
# relative to the BG2 base.
#
# **It goes last on purpose**, for the same reason as the previous ones:
# `vram_layout` now also looks at the upper layer, and since all the maps that
# already converted fit in 128, none changes layout.
LAYOUT_WINDOW_ABOVE = {"sprites": (0x0000, 384), "mapa": (0x1800, 1),
                       "tiles": (0x2000, 384), "encima": (0x5000, 256),
                       "ventana": (0x6000, 256), "ventana_map": (0x7000, 1)}

# In the order `vram_layout` tries them. **New ones are added at the end**,
# never in the middle: that way a new layout doesn't change any map's.
LAYOUTS = (("VENTANA", LAYOUT_WINDOW),
           ("VENTANA_FONDO", LAYOUT_WINDOW_BG),
           ("VENTANA_SPRITE", LAYOUT_WINDOW_SPRITE),
           ("VENTANA_AMBOS", LAYOUT_WINDOW_BOTH),
           ("VENTANA_FONDO_TECHO", LAYOUT_WINDOW_BG_CEILING),
           ("VENTANA_ENCIMA", LAYOUT_WINDOW_ABOVE))
# How many save slots the cartridge has. The same number is in
# `tools/runtime/save_game.s` as `SRAM_SLOTS`, and the ROM checks it: if they
# didn't match, the screen would show one number of slots and the SRAM would
# have another.
SLOTS = 4

# Where the tilemap and the tiles of the slots screen live, in words. The same
# numbers are in the `.inc` as SLOT_MAP and SLOT_VRAM.
#
# **They don't share with the title menu**, although until 2026-09-10 they
# did: the save point opens this screen with a map loaded and when closing it
# whatever it overwrote has to be restored, and that is cheap only if what it
# overwrote is the BG1 tile bank, which `load_map` uploads whole again. The
# menu's addresses —$4400 and $5000— fell on the sprites of a layout without
# a window that no longer exists: the NPCs came back from the menu with broken
# poses and the hero too if it wasn't the one in block 0. The ones here are in
# the intersection of the BG1 bank of the five layouts, which is $2000..$4000:
#
#   LAYOUT_WINDOW        $2000..$5800
#   LAYOUT_WINDOW_BG  $1000..$4C00
#   LAYOUT_WINDOW_SPRITE $2000..$5000
#   LAYOUT_WINDOW_BOTH  $2000..$5C00
#   LAYOUT_WINDOW_BG_CEILING $1000..$5400
#
# A BG's tile base goes in steps of 4096 words and the tilemap in steps of
# 1024: the tiles at $2000, which with the party's faces are about 300 and can
# reach 448 —up to $3C00—, and the tilemap at $3C00. The title screen
# overwrites them —its image reaches $3E00— and it doesn't matter: coming back
# from the slots the title is uploaded whole. `_check_slots` checks it
# against the real layouts, so that moving one doesn't leave this written
# wrong.
SLOT_VRAM = 0x2000
# The row of `slot_actor_text`: an actor's name, the two digits of the
# level and max HP, one after the other. Its size is a power of two even if
# bytes are left over, so that the actor's index comes out of five `asl` and
# not of a multiplication written in assembly.
SLOT_TEXT_WIDTH = 32
SLOT_TEXT_LEVEL = 16         # the name fits in thirteen, and three are left over
SLOT_TEXT_MAX = SLOT_TEXT_LEVEL + menus_mod.LEVEL_DIGITS
SLOT_MAP = 0x3C00

# The upper layer's tilemap is fixed: the background's is chosen by the layout
# —see LAYOUT_WINDOW_BOTH—.
VRAM_ABOVE_MAP = 0x7800

# Where the window's bank starts **counted from the BG2 base**, which is where
# the upper layer begins. It comes from the layout and not from a written
# number: with the upper layer at 128 tiles, the window starts at index 128
# and not 256, and writing it by hand was the first thing that broke when the
# layout moved.
def window_base(layout):
    """The BG2 index of the window's first tile in that layout."""
    return (layout["ventana"][0] - layout["encima"][0]) // 16


# The bases the layouts use, in the order of their layouts in the `.inc`: the
# first one's is `window_cells` —the usual one— and the second's,
# `window_cells_256`. The ROM picks between the two by the distance between
# the window and the BG2 base, so **there can't be a third** without touching
# `stamp_window`; `_check_splits` enforces it.
WINDOW_TILE_BASE = window_base(LAYOUT_WINDOW)
WINDOW_BASES = (WINDOW_TILE_BASE, 256)

# The block table is read with `lda tabla, x`, that is it lives in bank 0
# together with the code.
MAX_BLOCKS = 1024


def vram_layout(tiles, sprites=0, above=0):
    """Which VRAM layout a map gets, according to what it spends.

    The three numbers are checked in every layout, and the first one that
    fits is returned. The upper layer is checked since the sixth layout, the
    one that gives it 256: with the five before it always fit, because a map
    that went over 128 didn't convert.
    """
    # The two numbers are checked in both layouts. The background used to be
    # checked in one and the sprites in the other, and that let a map with 620
    # background tiles into a bank of 512: see the comment on
    # LAYOUT_WINDOW_BG.
    for _name, layout in LAYOUTS:
        if (tiles <= layout["tiles"][1] and sprites <= layout["sprites"][1]
                and above <= layout["encima"][1]):
            return layout
    raise SystemExit(
        "this map can't carry a message window: it spends %d background tiles, "
        "%d sprite tiles and %d upper tiles, and there is no layout that leaves "
        "8 KB of tiles plus 2 KB of tilemap for the window" % (tiles, sprites, above))


def _check_slots(slot_tiles):
    """That the slots screen lands in the BG1 bank of every layout.

    It is what lets `back_to_map` restore the map with `load_map` and
    nothing else; see the comment on SLOT_MAP.
    """
    end_tiles = SLOT_VRAM + slot_tiles * 16
    end_map = SLOT_MAP + 32 * 32
    if not (end_tiles <= SLOT_MAP or end_map <= SLOT_VRAM):
        raise SystemExit(
            "the %d tiles of the slots screen reach $%04X and overwrite its "
            "tilemap at $%04X" % (slot_tiles, end_tiles, SLOT_MAP))
    for name, layout in LAYOUTS:
        base, count = layout["tiles"]
        cap = base + count * (BYTES_PER_TILE // 2)
        for what, first, last in (("the tiles", SLOT_VRAM, end_tiles),
                                  ("the tilemap", SLOT_MAP, end_map)):
            if first < base or last > cap:
                raise SystemExit(
                    "the slots screen puts %s at $%04X..$%04X and the "
                    "BG1 bank of LAYOUT_%s is $%04X..$%04X: when coming back "
                    "from the menu `load_map` wouldn't restore it"
                    % (what, first, last, name, base, cap))


def items_border_first(source):
    """The first 8bpp tile of the item and equipment windows, counted from
    `SLOT_VRAM`, which is the BG1 base and the BG2 one: the first free one
    after the `source` tiles of the font, which are 4bpp and half the size."""
    return (source + 1) // 2


def _check_items_border(source, border):
    """That the font and the windows of the item and equipment screens, one
    after the other, don't reach the BG1 tilemap, and that everything stays
    in the BG1 bank of the layouts, like the rest of the screen —see
    `_check_slots`—."""
    end = SLOT_VRAM + (items_border_first(source) + border) * 32
    if end > menus_mod.ITEM_BORDER_MAP:
        raise SystemExit(
            "the item screen's font (%d 4bpp tiles) and the item and "
            "equipment windows (%d 8bpp ones) reach $%04X and the windows' "
            "tilemap is at $%04X" % (source, border, end, menus_mod.ITEM_BORDER_MAP))
    end_map = menus_mod.ITEM_BORDER_MAP + 32 * 32
    for name, layout in LAYOUTS:
        base, count = layout["tiles"]
        cap = base + count * (BYTES_PER_TILE // 2)
        if SLOT_VRAM < base or end_map > cap:
            raise SystemExit(
                "the item and equipment windows reach $%04X and the BG1 "
                "bank of LAYOUT_%s is $%04X..$%04X" % (end_map, name, base,
                                                       cap))


def _check_target(tiles):
    """That the tiles and the tilemap of the actor-choice windows fit between
    their BG1 base and their tilemap, and that everything lands in the BG1
    bank of every layout, which is what `load_map` restores when closing the
    menu —like `_check_slots`—, and outside what the menu already uses:
    its tiles and its tilemap end at `SLOT_MAP` + 1024."""
    T = menus_mod
    end_tiles = T.TARGET_VRAM + tiles * 32
    end_map = T.TARGET_MAP + 32 * 32
    if end_tiles > T.TARGET_MAP:
        raise SystemExit(
            "the actor-choice windows are %d 8bpp tiles and "
            "reach $%04X, and their tilemap is at $%04X"
            % (tiles, end_tiles, T.TARGET_MAP))
    if T.TARGET_VRAM < SLOT_MAP + 32 * 32:
        raise SystemExit("the actor-choice windows overwrite the "
                         "menu's tilemap")
    for name, layout in LAYOUTS:
        base, count = layout["tiles"]
        cap = base + count * (BYTES_PER_TILE // 2)
        if T.TARGET_VRAM < base or end_map > cap:
            raise SystemExit(
                "the actor-choice windows go at $%04X..$%04X and "
                "the BG1 bank of LAYOUT_%s is $%04X..$%04X: when closing the "
                "menu `load_map` wouldn't restore them"
                % (T.TARGET_VRAM, end_map, name, base, cap))


def _check_shop(tiles):
    """That the tiles of the shop windows, from their BG1 base, don't reach
    beyond what `load_map` restores when closing in any layout —like
    `_check_target`—, nor what the screen uses: the font and the BG2
    tilemap end at `SLOT_MAP` + 1024. The tilemap is the item and equipment
    one, which `_check_items_border` already checks."""
    P = screens_mod
    end_tiles = P.TI_VRAM + tiles * 32
    if P.TI_VRAM < SLOT_MAP + 32 * 32:
        raise SystemExit("the shop windows overwrite the text "
                         "tilemap")
    for name, layout in LAYOUTS:
        base, count = layout["tiles"]
        cap = base + count * (BYTES_PER_TILE // 2)
        if P.TI_VRAM < base or end_tiles > cap:
            raise SystemExit(
                "the shop windows are %d 8bpp tiles, at "
                "$%04X..$%04X, and the BG1 bank of LAYOUT_%s is "
                "$%04X..$%04X: when closing the shop `load_map` wouldn't "
                "restore them" % (tiles, P.TI_VRAM, end_tiles, name, base,
                                  cap))


def _check_splits():
    """That each layout respects the hardware and what the ROM assumes of it.

    None of this depends on the map, so it is checked once per conversion.
    """
    for name, layout in LAYOUTS:
        # In words: what each thing takes, and the step its base goes in. The
        # sprite and upper-layer tiles are 4bpp, 16 words.
        pieces = {
            "sprites": (layout["sprites"][1] * 16, 0x2000),
            "tiles": (layout["tiles"][1] * (BYTES_PER_TILE // 2), 0x1000),
            "encima": (layout["encima"][1] * 16, 0x1000),
            "ventana": (layout["ventana"][1] * 16, 1),
            "ventana_map": (32 * 32, 0x400),
            # 2048 and not 1024, which is what `BG1SC` asks for: `push_strips`
            # steps to the upper layer by masking eleven bits. See
            # `push_one_column`.
            "mapa": (WINDOW_W * WINDOW_H, 0x800),
        }
        stretches = [("upper map", VRAM_ABOVE_MAP, VRAM_ABOVE_MAP
                      + WINDOW_W * WINDOW_H)]
        for piece, (length, step) in pieces.items():
            base = layout[piece][0]
            if base % step:
                raise SystemExit("LAYOUT_%s: %s at $%04X, and its base goes in "
                                 "steps of $%X words" % (name, piece, base, step))
            stretches.append((piece, base, base + length))
        if layout["mapa"][0] == 0:
            raise SystemExit("LAYOUT_%s: the tilemap at $0000, and `col_addr` "
                             "at zero means there is no column" % name)
        if window_base(layout) not in WINDOW_BASES:
            raise SystemExit("LAYOUT_%s: the window starts at BG2 tile %d, "
                             "and there are layouts for %s: see WINDOW_BASES"
                             % (name, window_base(layout), WINDOW_BASES))
        # And the window has to land inside what BG2 reaches from its base: the
        # tilemap index is ten bits.
        if window_base(layout) + layout["ventana"][1] > 1024:
            raise SystemExit("LAYOUT_%s: the window goes past BG2 index "
                             "1023" % name)
        stretches.sort(key=lambda t: t[1])
        for (a, _, end), (b, first, _) in zip(stretches, stretches[1:]):
            if end > first:
                raise SystemExit("LAYOUT_%s: %s ends at $%04X and %s starts "
                                 "at $%04X" % (name, a, end, b, first))
        if stretches[-1][2] > 0x8000:
            raise SystemExit("LAYOUT_%s: %s goes past VRAM"
                             % (name, stretches[-1][0]))


# The message window, split in two: what the ROM carries ready-made and what
# it composes on the fly.
#
# **Why it is composed on the fly.** A composed message page is about 240 4bpp
# tiles, that is 7.5 KB. The game has 18,808 lines of text: emitting one
# window per message doesn't come close to fitting in a 256 KB cartridge. The
# way out is FF6's —the font in the ROM and the text built from the 65816— and
# it is what `componer_mensaje` does in tools/runtime/.
#
# How the window's bank of 256 tiles is split:
#
#   0 .. 14       the empty window, deduplicated: frame and stretched background
#   15 .. 254     the text area, 30 columns by 8 rows of cells
#
# The 240 of the text area **are not deduplicated**: each cell has its fixed
# tile, because the ROM is going to rewrite them and can't go around looking
# for repeats. That is where the cap of 39 characters per line comes from: with
# 40 the shadow of the last one spills into column 31 and 8 more tiles than
# there are would be needed. Truncating to 39 loses 1.58% of the game's
# characters against 1.09% for truncating to 40.
WINDOW_TEXT_ROW = 1           # the first row of cells that carries text
WINDOW_TEXT_ROWS = 8
WINDOW_TEXT_COL = 1
WINDOW_TEXT_COLS = 30


def _columns():
    """How many characters fit on a line. It lives in `window.py` with the
    rest of the geometry, and the reason for the number is there."""
    from port import window as window_mod
    return constants.COLUMNS


def _to_15_bits(picture):
    """The pixels of an RGBA image as 15-bit colors, over black."""
    from PIL import Image
    plain = Image.alpha_composite(
        Image.new("RGBA", picture.size, (0, 0, 0, 255)), picture).convert("RGB")
    return [tuple(v >> 3 for v in p) for p in plain.get_flattened_data()]


def convert_window(sys_img, font_id=None):
    """The message window: tiles, palette, cells and what the font needs.

    The image is built by `window.py`, which follows easyrpg-player's rules
    and is verified against a capture of the original game running in
    EasyRPG.
    Here it is cut into 8x8 cells and the fixed part is separated from what
    the ROM composes.

    The palette carries the colors of the empty window **plus** those of the
    text and the shadow, even though the empty window doesn't use them: they
    are the ones the ROM is going to write. Index 0 is left free on purpose,
    which is BG2's transparent and no window tile uses it.

    Returns a dict with:
        tiles     those of the empty window, deduplicated
        cram      the 16 words of the palette
        celdas    the 32x10 tilemap, with the text tiles already numbered
        fondo     the 240 tiles of the text area, without text, in order
        color     the palette index of each of the glyph's 12 rows
        sombra    the index of the shadow
    """
    from port import font as font_mod
    from port import window as window_mod

    if font_id is None:
        font_id = font_mod.MINCHO
    empty = window_mod.window(sys_img)
    pixels = _to_15_bits(empty)
    width, height = empty.width, empty.height

    # The text colors come from the System's 16x16 block, and they are the
    # ones `Font::Render` uses as a mask. Each row of the glyph takes a single
    # one —it is measured: the gradient is horizontally uniform— so they are
    # twelve colors, not a block, and the shadow is a single one.
    block = window_mod.text_color(sys_img, 0)
    shadow_img = window_mod.shadow_color(sys_img)
    ox, oy = window_mod.TEXT_OFFSET
    color_row = []
    for py in range(font_mod.HEIGHT):
        row = {tuple(v >> 3 for v in block.getpixel((ox + px, oy + py))[:3])
               for px in range(font_mod.WIDTH)}
        if len(row) != 1:
            raise SystemExit(
                "row %d of the text color has %d distinct colors; the "
                "ROM composes it with a single one" % (py, len(row)))
        color_row.append(row.pop())
    shadow = tuple(v >> 3 for v in shadow_img.getpixel((0, 0))[:3])

    colors = sorted(set(pixels) | set(color_row) | {shadow})
    if len(colors) > COLORS_PER_PALETTE - 1:
        raise SystemExit("the window uses %d colors and %d fit"
                         % (len(colors), COLORS_PER_PALETTE - 1))
    index = {c: i + 1 for i, c in enumerate(colors)}

    def cell_at(tx, ty):
        return tuple(tuple(index[pixels[(ty * 8 + y) * width + tx * 8 + x]]
                           for x in range(8)) for y in range(8))

    # The cells without text are deduplicated as always; the ones in the text
    # area are numbered consecutively from there.
    tiles, cells = {}, []
    for ty in range(height // 8):
        row = []
        for tx in range(width // 8):
            if (WINDOW_TEXT_ROW <= ty < WINDOW_TEXT_ROW + WINDOW_TEXT_ROWS
                    and WINDOW_TEXT_COL <= tx < WINDOW_TEXT_COL + WINDOW_TEXT_COLS):
                row.append(None)       # numbered below, once it is known how many
                continue
            cell = cell_at(tx, ty)
            if cell not in tiles:
                tiles[cell] = len(tiles)
            row.append(tiles[cell])
        cells.append(row)

    base = len(tiles)
    background = []
    for n, ty in enumerate(range(WINDOW_TEXT_ROW,
                                WINDOW_TEXT_ROW + WINDOW_TEXT_ROWS)):
        for m, tx in enumerate(range(WINDOW_TEXT_COL,
                                     WINDOW_TEXT_COL + WINDOW_TEXT_COLS)):
            cells[ty][tx] = base + n * WINDOW_TEXT_COLS + m
            background.append(cell_at(tx, ty))
    if base + len(background) > 256:
        raise SystemExit("the window needs %d tiles and the bank has 256"
                         % (base + len(background)))

    data = b"".join(pack_tile(cell, planes=4)
                    for cell, _ in sorted(tiles.items(), key=lambda kv: kv[1]))
    cram = [0] + [cgram_word(c) for c in colors]
    cram += [0] * (COLORS_PER_PALETTE - len(cram))
    # The background starts where this ends, so if the window grew it would
    # step on it and the ROM would draw the text with a map color. The highest
    # index really used is checked —the shadow's or that of some row of the
    # glyph— and not how many words are nonzero: a black color has word zero
    # and wouldn't be counted.
    height = max([index[c] for c in color_row] + [index[shadow]])
    if height >= CGRAM_RESERVED:
        raise SystemExit(
            "the message window uses CGRAM entry %d and the background "
            "starts at %d: raise CGRAM_RESERVED" % (height, CGRAM_RESERVED))
    return {"tiles": data, "cram": cram, "celdas": cells,
            "base": base,
            "fondo": b"".join(pack_tile(c, planes=4) for c in background),
            "color": [index[c] for c in color_row],
            "sombra": index[shadow]}


def font_bytes(font_id):
    """The 95 ASCII glyphs, twelve rows of six bits each.

    It is the same table as `tools/port/font.py`, which is generated from
    easyrpg-player, but **with the bits reversed**: there bit 0 is the
    leftmost pixel and in the console's tile format the leftmost is bit 7.
    Reversing them here and not in the ROM comes for free: it is a 1140-byte
    table generated once.
    """
    from port import font as font_mod
    out = bytearray()
    for code in range(32, 127):
        for row in font_mod.rows(chr(code), font_id):
            inverted = 0
            for px in range(FONT_WIDTH):
                if row >> px & 1:
                    inverted |= 1 << (7 - px)
            out.append(inverted)
    return bytes(out)


# The window glyphs already composed, for each of the four phases a character
# can land on: x is `WINDOW_BORDER + 6 * column`, so modulo 8 it gives 0, 6, 4
# or 2 and never anything else. Per glyph and phase go the cell rows of
# `FONT_PRE_ROWS` it touches —the glyph's twelve from `TEXT_OFS_Y`, and
# one more of shadow— and per row the two cells it can step on, each with
# three words: what is kept from the buffer, and what is set in planes 0-1
# and in 2-3. The ROM does `buf = buf & conservar | prender`, which is what it
# used to compute on each row with `pintar`, twice —shadow and glyph— and with
# a one-bit-at-a-time shift. See `compose_char`.
#
# The shadow and the glyph come already combined, with the ordering rule of
# `Font::Render`: on a row lands the glyph from two rows up and the shadow
# from three, shifted one pixel, and where they overlap the glyph wins.
FONT_PRE_ROWS = FONT_HEIGHT + 1
FONT_PRE_CHAR = FONT_PRE_ROWS * 2 * 6


def font_prerender(source, colors, shadow):
    """The four tables, one per phase (0, 2, 4 and 6), in that order."""
    n = len(source) // FONT_HEIGHT
    tables = []
    for phase in (0, 2, 4, 6):
        out = bytearray()
        for c in range(n):
            rows = source[c * FONT_HEIGHT:(c + 1) * FONT_HEIGHT]
            run = [(f << 8) >> phase for f in rows]
            for k in range(FONT_PRE_ROWS):
                glyph = run[k] if k < FONT_HEIGHT else 0
                color = colors[k] if k < FONT_HEIGHT else 0
                shadow_m = (run[k - 1] >> 1) if k >= 1 else 0
                shadow_m &= ~glyph & 0xFFFF
                for cell in (0, 1):
                    g = (glyph >> (8 if cell == 0 else 0)) & 0xFF
                    s = (shadow_m >> (8 if cell == 0 else 0)) & 0xFF
                    keep = ~((g | s) * 0x0101) & 0xFFFF
                    turn_on = []
                    for bits in (0, 2):
                        word = 0
                        for m, col in ((g, color), (s, shadow)):
                            if col >> bits & 1:
                                word |= m
                            if col >> (bits + 1) & 1:
                                word |= m << 8
                        turn_on.append(word)
                    for word in [keep] + turn_on:
                        out += bytes([word & 0xFF, word >> 8])
        tables.append(bytes(out))
    return tables


def build_blocks(game_map, tilemap, above_tilemap, passable, width, height,
                 chipset=None):
    """The map as indices into 16x16 blocks, with its table.

    Returns (cells, block table, passability per block, combinations). The
    cells go row by row, which is how the ROM walks them.

    The **combinations** are `(lower tile, upper tile) -> block`, with the
    RM2k ids and nothing from the console. They don't take part in the block's
    key, so they don't change a single byte of the output: they are what
    `TileSubstitution` needs to know which block a tile substituted by another
    ends up in, because the bytecode talks about tiles and the ROM about
    blocks. A block is exactly one RM2k 16x16 cell, so the correspondence
    exists.
    """
    blocks, cells, combos = {}, [], {}
    for by in range(height):
        for bx in range(width):
            bottom = game_map.lower_layer[by * width + bx]
            key = (tuple(tilemap[by * 2 + dy][bx * 2 + dx]
                         for dy in (0, 1) for dx in (0, 1)),
                   tuple(above_tilemap[by * 2 + dy][bx * 2 + dx]
                         for dy in (0, 1) for dx in (0, 1)),
                   passable[by * width + bx],
                   # The terrain goes into the key for the same reason as the
                   # passability: two cells drawn the same can come from tiles
                   # with different terrain, and the ROM reads it per block.
                   # It doesn't split any extra block in this game, where the
                   # terrain of every ChipSet is 1.
                   rm2k.terrain_of(chipset, bottom) if chipset else 1)
            if key not in blocks:
                blocks[key] = len(blocks)
            cells.append(blocks[key])
            combos.setdefault((bottom,
                               game_map.upper_layer[by * width + bx]),
                              blocks[key])

    if len(blocks) > MAX_BLOCKS:
        raise SystemExit("the map uses %d distinct blocks and the table can't "
                         "go over %d" % (len(blocks), MAX_BLOCKS))

    table = bytearray(BLOCK_BYTES * len(blocks))
    pass_bytes = bytearray(len(blocks))
    terrain_bytes = bytearray(len(blocks))
    for (base, above, permissions, terrain), number in blocks.items():
        entries = list(base) + list(above)
        for i, cell in enumerate(entries):
            table[number * BLOCK_BYTES + i * 2:
                  number * BLOCK_BYTES + i * 2 + 2] = cell.to_bytes(2, "little")
        pass_bytes[number] = permissions
        if not 0 <= terrain <= 0xFF:
            raise SystemExit("a tile with terrain %d and the ROM's table "
                             "carries one byte per block" % terrain)
        terrain_bytes[number] = terrain
    return cells, table, pass_bytes, terrain_bytes, combos


# How many block pairs the ROM's substitution table can hold at once. It is
# `SUB_MAX` in tools/runtime/low_ram.s and it is written on both sides on
# purpose —the converter has to be able to refuse **before** emitting a map
# that doesn't fit—; the test `test_sustitucion.py` compares the two.
SUB_MAX = 8


class Substitutions:
    """`TileSubstitution` translated from RM2k tiles to ROM blocks.

    RM2k substitutes by **tile number**: every cell of the map that draws the
    old tile starts drawing the new one. In the ROM there are no RM2k tiles,
    there are 16x16 blocks that carry both layers and the passability
    together, so an RM2k substitution is as many block pairs as (lower, upper)
    combinations of the map carry that tile. Which ones they are is known when
    converting, which is why this lives here and not in `events.py`.

    The destination block may not exist —nobody drew that combination
    anywhere in the map— and then it is built: the four 8x8 cells of the layer
    that changes come from another block that already draws the new tile,
    those of the other layer come from the source block, and the passability
    is recomputed with the same RM2k rules. That is where the only real limit
    of this comes from: **the new tile has to be drawn in some cell of the
    map**, on its layer. If it isn't, its 8x8s didn't go into VRAM and there
    is nothing to draw it with; the page doesn't compile and it says why.

    All the blocks are built **before** compiling any page, and not as the
    commands show up: substitutions chain —turning on is 80→80A and turning
    off is 80A→80— so the block one needs is created by another, and the
    order the pages are compiled in can't decide what compiles.
    """

    def __init__(self, map_info, flags, chipset):
        self.map_info = map_info
        self.flags = flags
        self.chipset = chipset
        self.combos = map_info["combos"]
        # The four 8x8 cells each RM2k tile is drawn with, per layer. They come
        # from the blocks that already exist: a tile the map doesn't draw
        # anywhere isn't here and can't be substituted into.
        self.cells = ({}, {})
        for (low, height), block in self.combos.items():
            # **The lower half is only usable if the upper tile of that block
            # isn't baked into it.** An upper-layer tile **without** the
            # "Above" bit isn't drawn on BG2 but over the background —that is
            # what `rm2k-render` decides, and that is why there are upper tiles
            # whose BG2 half comes out empty—, so the lower half of that block
            # is the composition of the two and not the lower tile alone.
            # Copying it to build another combination would draw the
            # neighbor's upper tile.
            if not self._bakes(height):
                self.cells[0].setdefault(low, self._half(block, 0))
            self.cells[1].setdefault(height, self._half(block, 1))
        # The blocks some substitution of the map uses as a key, which is what
        # is going to take room in the RAM table.
        self.known_keys = set()
        # And the blocks by content, to deduplicate the ones built the same way
        # `build_blocks` deduplicates the map's. It isn't to save room: two
        # combinations that already share a block —the two water autotiles of
        # map 6 draw the same thing— have to keep sharing it after
        # substituting, or the substitution would send a single block to two
        # places and couldn't be expressed.
        self.by_bytes = {}
        for block in range(len(map_info["pass"])):
            self.by_bytes.setdefault(self._fingerprint(block), block)

    def _bakes(self, height):
        """Whether that upper-layer tile is baked into the background instead
        of going to BG2.

        It is the computation `rm2k-render` draws with: an upper tile goes above the hero
        —that is, to BG2— only with the `Above` bit set, and without it it is
        drawn stuck to the background. The empty tile draws nothing and bakes
        nothing.
        """
        return (height != rm2k.UPPER_BASE
                and not self.flags[height] & rm2k.PASS_ABOVE)

    def _half(self, block, layer):
        first = block * BLOCK_BYTES + layer * 8
        return bytes(self.map_info["bloques"][first:first + 8])

    def _fingerprint(self, block):
        first = block * BLOCK_BYTES
        return (bytes(self.map_info["bloques"][first:first + BLOCK_BYTES]),
                self.map_info["pass"][block], self.map_info["terreno"][block])

    def _combo(self, high_layer, old, new):
        """The RM2k ids of the tile that goes out and the one that comes in."""
        base = rm2k.UPPER_BASE if high_layer else rm2k.LOWER_BASE
        return base + old, base + new

    def pairs(self, high_layer, old, new):
        """The `(old block, new block)` pairs of a substitution, or None.

        None is "this page doesn't compile", which is what `events.py`
        expects from a command that can't be done.
        """
        if not (0 <= old < rm2k.TILES_PER_LAYER
                and 0 <= new < rm2k.TILES_PER_LAYER):
            return None
        layer = 1 if high_layer else 0
        old_id, new_id = self._combo(high_layer, old, new)
        out, seen = [], {}
        for combination, block in sorted(self.combos.items()):
            if combination[layer] != old_id:
                continue
            dest = list(combination)
            dest[layer] = new_id
            new_block = self.combos.get(tuple(dest))
            if new_block is None:
                return None     # `close` should have created it
            if seen.setdefault(block, new_block) != new_block:
                # Two distinct combinations that draw the same and have the
                # same permissions share a block, and there the substitution
                # can't be expressed: the block would have to go two ways. It
                # doesn't happen with any ChipSet of the game —drawing the
                # same means being the same tile— but if it did, substituting
                # would change cells RM2k doesn't touch.
                return None
            out.append((block, new_block))
        if len(out) > 0xFF:
            return None         # the count operand is one byte
        self.known_keys.update(pair[0] for pair in out)
        return out

    def close(self, triples):
        """Builds the blocks that are going to be needed, and returns what
        couldn't be done.

        `triples` are the `(upper layer, old, new)` of all the map's
        `TileSubstitution`s. It repeats until none creates a new block,
        because the block one creates is the source of the next.
        """
        missing = []
        while True:
            before = len(self.combos)
            for high_layer, old, new in triples:
                if not (0 <= old < rm2k.TILES_PER_LAYER
                        and 0 <= new < rm2k.TILES_PER_LAYER):
                    continue
                layer = 1 if high_layer else 0
                old_id, new_id = self._combo(high_layer, old, new)
                if new_id not in self.cells[layer]:
                    if (high_layer, old, new) not in missing:
                        missing.append((high_layer, old, new))
                    continue
                for combination in sorted(self.combos):
                    if combination[layer] != old_id:
                        continue
                    dest = list(combination)
                    dest[layer] = new_id
                    if self._create(tuple(dest)) is None \
                            and (high_layer, old, new) not in missing:
                        missing.append((high_layer, old, new))
            if len(self.combos) == before:
                return missing

    def _create(self, combination):
        """The block of a combination the map doesn't draw anywhere.

        None is "this combination can't be built without drawing the map
        again". It happens when the upper tile is baked into the background:
        then the two halves of the block aren't independent and there is
        nowhere to take the lower one from. See `_bakes`.
        """
        if combination in self.combos:
            return self.combos[combination]
        low, height = combination
        if self._bakes(height) or low not in self.cells[0] \
                or height not in self.cells[1]:
            return None
        fingerprint = (self.cells[0][low] + self.cells[1][height],
                       rm2k.cell_passability(self.flags, low, height),
                       rm2k.terrain_of(self.chipset, low))
        number = self.by_bytes.get(fingerprint)
        if number is None:
            number = len(self.map_info["pass"])
            if number >= MAX_BLOCKS:
                raise SystemExit(
                    "map %d goes over %d blocks building the ones "
                    "`TileSubstitution` needs"
                    % (self.map_info["id"], MAX_BLOCKS))
            self.map_info["bloques"] += fingerprint[0]
            self.map_info["pass"].append(fingerprint[1])
            self.map_info["terreno"].append(fingerprint[2])
            self.by_bytes[fingerprint] = number
        self.combos[combination] = number
        return number


def substitution_triples(game_map, cases, map_id):
    """The `(upper layer, old, new)` of all the `TileSubstitution`s that can
    end up running in this map: those of its events and those of the test
    cases that start here —which live in the boot map but are compiled with
    this one's context, see `case_map`—."""
    triples = []
    lists = [page.commands
             for event in game_map.events for page in event.pages]
    lists += [case.commands for case in cases if case.run_map == map_id]
    for commands in lists:
        for cmd in commands:
            if cmd.code != events.TILE_SUBSTITUTION or len(cmd.parameters) < 3:
                continue
            triple = (bool(cmd.parameters[0]),
                      cmd.parameters[1], cmd.parameters[2])
            if triple not in triples:
                triples.append(triple)
    return triples


# A map's record in the table. The stride is a power of two so that going from
# index to offset is shifts and not a multiplication, and there is room to
# spare on purpose: adding a field must not move anything already there.
#
# The pointers go four bytes at a time even though they are three. The spare
# byte is unused; what is gained is that the low part of each pointer always
# lands on an even address, which is how it is read with the accumulator in 16
# bits.
MAP_STRIDE = 128
MAP_SCALARS = [
    ("MAP_BW", "width in 16x16 cells"),
    ("MAP_BH", "height in 16x16 cells"),
    ("CAM_MAX_X", "how far the camera reaches without going out"),
    ("CAM_MAX_Y", ""),
    ("HERO_MAX_X", "how far the hero reaches"),
    ("HERO_MAX_Y", ""),
    ("HERO_START_X", "where it starts, in pixels"),
    ("HERO_START_Y", ""),
    ("VRAM_TILES", "the VRAM layout, in words"),
    # Where the background tilemap goes. The upper layer's base has no field:
    # it is the high nibble of BG12NBA_VALUE, and the record is full.
    ("VRAM_MAP", ""),
    ("VRAM_SPRITE", ""),
    ("VRAM_WINDOW", "0 if this ROM carries no message window"),
    ("VRAM_WINDOW_MAP", "and its own 32x32 tilemap"),
    ("MAP_TILES", "how many background tiles, for the DMA"),
    ("MAP_CGRAM", "how many CGRAM words"),
    ("ABOVE_TILES", ""),
    ("ABOVE_CGRAM", ""),
    ("SPRITE_TILES", ""),
    ("SPRITE_CGRAM", ""),
    ("NPC_COUNT", "how many NPCs with a CharSet"),
    ("EV_COUNT", "how many events the map has, with or without a graphic"),
    ("TIMER_BASE", "the first tile of the timer digits, 0 if there are none"),
    ("RAIN_BASE", "the first tile of the raindrops, 0 if there are none"),
    ("ACTOR_COUNT", "how many party leader candidates"),
    ("PAGE_COUNT", "how many event pages have to be resolved"),
    ("ROUTE_GRAPHIC_COUNT", "how many distinct graphics command 34 asks for"),
]
MAP_BYTES = [
    ("OBSEL_VALUE", "8x8 and 32x32 objects, and the page of their tiles"),
    ("BG12NBA_VALUE", "the tile pages of BG1 and BG2"),
    ("ABOVE_FIRST", "which CGRAM entry the upper layer starts at"),
    ("TIMER_PAL", "the sprite palette of the timer digits"),
    ("RAIN_PAL", "the sprite palette of the raindrops"),
    # A byte and not a scalar because the record is at exactly its 128. A
    # block's tile is always a multiple of four and less than 512.
    ("TURN_TILE4", "the tile of the turn slot divided by four, or $FF"),
    # The terrain, which is what `StoreTerrainID` answers. Both are bytes
    # because RM2k's terrain is an index into `Data.terrains` and doesn't go
    # over 255, and because the map record is at exactly its 128.
    ("TERRAIN_OUTSIDE", "the terrain of a cell outside the map"),
    ("TERRAIN_PLANE", "the terrain of the whole map, or 0 if there is a table"),
]
MAP_POINTERS = ["map_tiles", "map_cgram", "above_tiles", "above_cgram",
                "sprite_tiles", "sprite_cgram", "map_cells", "map_blocks",
                "block_pass", "block_terrain", "npc_table", "actor_table",
                "pages", "ev_pos", "npc_poses", "route_graphic",
                # The ChipSet animation: the two tile runs and their
                # drawings. See `anim_bytes`.
                "anim_tiles"]
MAP_PTR_STEP = 4
# Where the pointers start: right after the scalars and the bytes, rounded up
# to the stride. **It is computed and not written by hand**, because written by
# hand it already failed: adding one more scalar left `ABOVE_FIRST` and the
# first pointer at the same offset, the ROM read the palette byte as a pointer
# to the map tiles and the screen came out a flat color.
#
# It is one of those neither end can see: the assembler sees two different
# names with the same value, which is legal, and the pixel-by-pixel comparison
# says "all wrong" without saying where. The only defense is for the number to
# come from the data.
MAP_PTR_BASE = (-(-(len(MAP_SCALARS) * 2 + len(MAP_BYTES))
                  // MAP_PTR_STEP) * MAP_PTR_STEP)
assert MAP_PTR_BASE + len(MAP_POINTERS) * MAP_PTR_STEP <= MAP_STRIDE, \
    "the map record doesn't fit in %d bytes" % MAP_STRIDE

# An event page: which event it belongs to, what activates it, and where its
# code is. The pages of one event go together and in order, which is what lets
# the ROM choose the last one that meets its conditions in a single pass,
# without carrying a table per event.
PAGE_BYTES = 32
# No turn slot: the map has no still event that turns around.
TURN_NONE = 0xFFFF
# A leader candidate: id, palette, **its fifteen colors** and twelve 24-bit
# pointers to its poses. The colors go inside the table and not in a separate
# block because there are few actors per map and that way the ROM uploads them
# with one DMA from where it already is; see `pick_hero_graphic`.
#
# They are there because leaders **share a CGRAM slot**: one leads at a time,
# so reserving a palette for each is having it taken by someone who isn't on
# screen. The ROM uploads the leader's when the party changes and when the map
# loads. See `drawable_npcs`.
ACTOR_COLORS = 2 * OBJ_COLORS
ACTOR_BYTES = 2 + ACTOR_COLORS + 3 * 12

# One bit per switch. The game checks up to 1003 in page conditions, so 1024
# is more than enough: it is 128 bytes of RAM.
SWITCH_BYTES = 128

# How many distinct graphics command 34 can ask for in a map. The table is
# copied to RAM when the map loads, like the NPC one, so the cap costs bytes
# from bank 0's eight kilobytes —two per graphic— and can't be generous just
# because. **The map that asks for the most in the whole game asks for six**,
# measured over the 328; eight leaves two of slack and is sixteen bytes. The
# converter stops if any map goes over, so it can't fall short silently.
ROUTE_GFX_MAX = 8


def map_fields(map_info):
    """The values of a map's record, in the order they are emitted."""
    tilemap, above, sprite = map_info["tilemap"], map_info["above"], map_info["sprite"]
    collision, layout = map_info["collision"], map_info["layout"]
    height, width = len(tilemap), len(tilemap[0])
    return {
        "MAP_BW": collision[3], "MAP_BH": collision[4],
        "CAM_MAX_X": max(0, width * CELL - 256),
        "CAM_MAX_Y": max(0, height * CELL - 224),
        "HERO_MAX_X": width * CELL - 16, "HERO_MAX_Y": height * CELL - 16,
        "HERO_START_X": collision[1] * 16, "HERO_START_Y": collision[2] * 16,
        "VRAM_TILES": layout["tiles"][0], "VRAM_MAP": layout["mapa"][0],
        "VRAM_SPRITE": layout["sprites"][0],
        "VRAM_WINDOW": layout.get("ventana", (0, 0))[0],
        "VRAM_WINDOW_MAP": layout.get("ventana_map", (0, 0))[0],
        "MAP_TILES": len(map_info["tiles"]) // BYTES_PER_TILE,
        "MAP_CGRAM": len(map_info["cram"]) // 2,
        "ABOVE_TILES": len(above[0]) // 32,
        "ABOVE_CGRAM": len(above[1]) // 2,
        "SPRITE_TILES": len(sprite[0]) // 32 if sprite else 0,
        # One more than the colors: sprite index 0 is transparent and also
        # takes its place in CGRAM.
        "SPRITE_CGRAM": COLORS_PER_PALETTE * len(sprite[1]) if sprite else 0,
        "NPC_COUNT": len(sprite[3]) if sprite else 0,
        "EV_COUNT": len(map_info["ev_pos"]) // EV_STRIDE,
        "TIMER_BASE": sprite[5] if sprite else 0,
        "RAIN_BASE": sprite[10] if sprite else 0,
        "ACTOR_COUNT": len(sprite[4]) if sprite else 0,
        "PAGE_COUNT": len(map_info["pages"]),
        "ROUTE_GRAPHIC_COUNT": len(sprite[9]) if sprite else 0,
        "OBSEL_VALUE": 0x20 | (layout["sprites"][0] // 0x2000),
        "BG12NBA_VALUE": ((layout["encima"][0] // 0x1000) << 4)
                         | (layout["tiles"][0] // 0x1000),
        "ABOVE_FIRST": above[3] * COLORS_PER_PALETTE,
        "TIMER_PAL": (sprite[6] if sprite and sprite[6] is not None else 0),
        "RAIN_PAL": sprite[11] if sprite else 0,
        "TURN_TILE4": (sprite[12] // 4 if sprite and sprite[12] != TURN_NONE
                       else 0xFF),
        "TERRAIN_OUTSIDE": map_info["terreno_fuera"],
        "TERRAIN_PLANE": terrain_plane(map_info),
    }


def offsets():
    """The names of the record's fields, so that tools/runtime/ doesn't repeat
    them.

    The converter emitting the offsets and the ROM only naming them is what
    makes it impossible for them to get out of sync: if a field is added here,
    there is no number to update there.
    """
    out = ["; Where each field falls inside a map's record."]
    used = 0
    for name, _ in MAP_SCALARS:
        out.append("M_%-14s = %d" % (name, used))
        used += 2
    for name, _ in MAP_BYTES:
        out.append("M_%-14s = %d" % (name, used))
        used += 1
    for number, name in enumerate(MAP_POINTERS):
        out.append("M_PTR_%-10s = %d"
                   % (name.upper(), MAP_PTR_BASE + number * MAP_PTR_STEP))
    return "\n".join(out)


def map_table(maps, labels):
    """The table the ROM walks to know what to load.

    `labels` says, per map, which block each pointer points to. This didn't
    exist before and the name was rebuilt here with `"%s_%d" % (nombre,
    numero)`, that is with the same computation that had emitted it: two
    places computing the same name and no way for a block to belong to more
    than one map.
    """
    out = ['.segment "RODATA"',
           "; The map table: one record of %d bytes per map, with everything"
           % MAP_STRIDE,
           "; the ROM needs to load it. The pointers are 24 bits because the",
           "; data lives spread over all the banks.",
           ";",
           "; **It lives in RODATA and is read with `lda f:map_table + campo, x`.**",
           "; It is 144 bytes per map, and in bank 0 —where the table has to be",
           "; if it is walked with the data bank register— that was enough for",
           "; fourteen maps and no more: with the whole of Lashe City it is 33",
           "; and the bank went over by 3739 bytes. It is the third table that",
           "; moves for the same reason; the price is one byte per instruction",
           "; and that the two uses with Y had to switch to X, because long",
           "; absolute indexed addressing only exists with X.",
           ";",
           "; **Whole within one bank**, which is what `.block` asks for. In",
           "; LoROM what follows $03FFFF isn't bank 4's ROM but RAM, and the",
           "; first version of this landed at $03FFB1: the 144 bytes of the only",
           "; record were split in half and map 5 started black. The other maps",
           "; of the suite didn't see it because their table landed somewhere",
           "; else, which is exactly the kind of error that shows up when adding",
           "; a byte anywhere else.",
           ".block %d" % (MAP_STRIDE * len(maps)),
           "map_table:"]
    for number, map_info in enumerate(maps):
        fields = map_fields(map_info)
        # `mapas_de` in rom/pruebas/arnes/consola.py reads the table order
        # from this line with a regex that expects "map".
        out.append("    ; --- %d: map %d %r ---" % (number, map_info["id"],
                                                     map_info["nombre"]))
        used = 0
        for name, comment in MAP_SCALARS:
            out.append("    .word %-6d ; +%-3d %s%s"
                       % (fields[name], used, name,
                          "  " + comment if comment else ""))
            used += 2
        for name, comment in MAP_BYTES:
            out.append("    .byte $%02X    ; +%-3d %s  %s"
                       % (fields[name], used, name, comment))
            used += 1
        padding = MAP_PTR_BASE - used
        # Without padding the line doesn't go: a `.byte` without operands is an
        # error for `ca65`.
        if padding:
            out.append("    .byte %s ; +%d  padding up to the pointers"
                       % (",".join(["$00"] * padding), used))
        used += padding
        for name in MAP_POINTERS:
            label = labels[number][name]
            out.append("    .byte <(%s), >(%s), ^(%s), $00 ; +%d  %s"
                       % (label, label, label, used, name))
            used += MAP_PTR_STEP
        assert used <= MAP_STRIDE, used
        if used < MAP_STRIDE:
            out.append("    .byte " + ",".join(["$00"] * (MAP_STRIDE - used)))
    # And each map's RM2k id, by index: `MemorizeLocation` writes it into a
    # variable and `RecallToLocation` looks it up, because in variables the map
    # is RM2k's —any other page reads them—. It goes separately and not as a
    # record scalar because the record is at exactly its 128. See
    # `op_location`.
    out += ["",
            "; Each map's RM2k id, in the order of `map_table`.",
            ".block %d" % (2 * len(maps)),
            "map_rm2k:",
            "    .word " + ", ".join(str(m["id"]) for m in maps)]
    return "\n".join(out)


# The ChipSet animation block: the drawings, one after the other and in VRAM
# order —water 0, 1, 2; animated 0 to 3—, with no header.
#
# Where each one lands and which VRAM address it goes to isn't inside the
# block but in `anim_table`, one entry per map. It is so the ROM doesn't have
# to read anything from the cartridge to animate: the direct page is full, so
# an `lda [puntero], y` had nowhere to live, and the alternative —bringing the
# header into WRAM by DMA— asked for forty bytes of BSS that weren't there
# either. With the table built here, the ROM indexes and fires the DMA.
ANIM_STRIDE = 16
ANIM_FAM_STRIDE = ANIM_STRIDE // 2


def anim_bytes(animation):
    """The map's drawings, one after the other. Empty if nothing animates."""
    data = bytearray()
    for family, _ in FAMILIES:
        run = animation.get(family)
        if run:
            for drawing in run["dibujos"]:
                data += drawing
    return bytes(data)


def anim_table(maps):
    """One entry per map, with both runs already resolved.

    Per family, and in the order the ROM looks at them:

        +0 word  VRAM address, in words
        +2 word  offset of drawing 0 inside the block
        +4 word  how many bytes a drawing is
        +6 byte  how many tiles it is; 0 if this family doesn't animate in this map
        +7 byte  padding, so each family's entry is eight

    The VRAM address comes from here and not from a computation on the console
    because both halves are here: the map's VRAM layout and which tile of its
    bank the run starts at.

    The padding of the second family —byte +15 of the entry— carries **whether
    the map has some still event with continuous animation**. It goes here
    because it is the same as the rest: something per map that the ROM looks
    at once per frame and that no longer fit in the map record. Without it,
    `animate_still` would have to walk the forty NPC rows in every map.
    """
    out = ['.segment "RODATA"',
           "; The ChipSet animation, one entry of %d bytes per map."
           % ANIM_STRIDE,
           # `rom/src/` and not `tools/runtime/`, on purpose: it goes into the
           # `.inc`, and what is emitted isn't touched yet. See
           # las-herramientas-se-separan-de-abl.md.
           "; See `anim_table` in tools/port/snes_convert.py and `anim_flush` in rom/src/chipset_animation.s.",
           ";",
           "; **It lives in RODATA and is read with `lda f:anim_table + campo, x`**,",
           "; for the same reason as `map_table`: it is 16 bytes per map, and",
           "; with the maps the tests ask for bank 0 went over by 361. Whole",
           "; within one bank, because what follows $xxFFFF isn't the next one's ROM.",
           ".block %d" % (ANIM_STRIDE * len(maps)),
           "anim_table:"]
    for map_info in maps:
        animation = map_info["resumen"]["animacion"]
        out.append("    ; --- map %d %r ---" % (map_info["id"], map_info["nombre"]))
        offset = 0
        for family, count in FAMILIES:
            run = animation.get(family)
            tiles = run["tiles"] if run else 0
            vram = (map_info["layout"]["tiles"][0]
                    + (run["base"] if run else 0) * BYTES_PER_TILE // 2)
            out.append("    .word %-6d ; VRAM of %s" % (vram, family))
            out.append("    .word %-6d ; drawing 0, inside the block"
                       % offset)
            out.append("    .word %-6d ; bytes per drawing"
                       % (tiles * BYTES_PER_TILE))
            padding = 0
            if family == FAMILIES[-1][0]:
                padding = 1 if any(n.get("animates")
                                   for n in (map_info["sprite"][3]
                                             if map_info["sprite"] else ())) else 0
            out.append("    .byte %d, %d   ; %d tile(s)%s"
                       % (tiles, padding, tiles,
                          ", and the map has still events that animate"
                          if padding else ""))
            offset += tiles * BYTES_PER_TILE * count
    return "\n".join(out)


def rom_animations(maps, renderer):
    """The battle animations the already emitted bytecode shows, by RM2k
    number, each one converted by `animation.py`.

    The bytecode is walked and not the commands, which is what makes it the
    truth and not a guess: what counts is what ended up emitted, after the
    page filter decided which ones go in. It is the same rule as
    `events.route_targets`.
    """
    numbers = set()
    for map_info in maps:
        for page in map_info.get("pages", ()):
            code = page.get("codigo") or b""
            for i, c in events.walk_code(code):
                if (c[i] == events.OP_ANIMATION
                        and c[i + 1] != events.ANIM_NO_DRAWING):
                    numbers.add(c[i + 1])
    out = {}
    for number in sorted(numbers):
        info = animation_mod.by_number(renderer, number)
        if info is not None:
            out[number] = info
    return out


def animation_frame(frame):
    """The 2 KB of a battle animation frame as they end up in VRAM: the box's
    64 4bpp tiles, in order."""
    data = bytearray(animation_mod.TILES * 32)
    for tile, cell in animation_mod.cells(frame).items():
        data[tile * 32:(tile + 1) * 32] = pack_tile(cell, planes=4)
    return bytes(data)


# The end of a frame without its empty tiles: no tile of the box reaches 64.
FRAME_END = 0xFF


def frame_without_gaps(data):
    """A frame from `animation_frame` as the cartridge stores it: only its
    tiles that aren't all zero, each with its number in front, and
    `FRAME_END`.

    The frames are **almost all transparency**, so storing them whole was
    paying for zeros: what was measured is in the task
    `la-compresion-de-mapas-y-graficos.md`. What ends up in VRAM doesn't
    change: `anim_frame_build` rebuilds the 2 KB in far RAM and the vblank
    uploads them whole, as before.
    """
    out = bytearray()
    for tile in range(animation_mod.TILES):
        one = data[tile * 32:(tile + 1) * 32]
        if any(one):
            out.append(tile)
            out += one
    out.append(FRAME_END)
    return bytes(out)


def animations_asm(animations, maps):
    """The cartridge's battle animations, ready for the `.inc`.

    Four things:

      `anim_battle`          by RM2k number, which entry it gets, or $FF.
                             It goes by number and not by an index of ours so
                             that neither end has to carry a counter the other
                             must guess.
      `anim_battle_table`    per entry: how many frames, where its anchor
                             falls inside the box and which frame it starts at.
      `anim_battle_frames` per frame, the 24-bit pointer to its tiles
                             without the empty ones: see `frame_without_gaps`.
                             One per frame and not a contiguous block per
                             animation, which dates from when each frame was
                             2 KB and 28 didn't fit in a bank.
      `anim_battle_cgram`    its sixteen colors, which the ROM uploads when the
                             animation starts.
      `anim_battle_split` per map, where and with which palette it is drawn
                             here, or 0 if this map doesn't draw animations.
    """
    order = sorted(animations)
    slot_of = {number: k for k, number in enumerate(order)}
    cap = (max(order) + 1) if order else 1
    out = [
        "\n; --- the drawing of the battle animations ---",
        ";",
        "; The box is a single one for the whole ROM and the reason is in",
        "; tools/port/animation.py: four 32x32 objects in one row of blocks",
        "; of the name grid, which is the most that fits in the sprite VRAM",
        "; map 2 has left free. What changes per map is where that row lands",
        "; and with which palette, and that goes in `anim_battle_split`,",
        "; one byte per map.",
        "ANIM_B_BOX    = %d" % animation_mod.BOX,
        "ANIM_B_OBJ    = %d" % animation_mod.OBJ,
        "ANIM_B_OBJECTS = %d" % animation_mod.OBJECTS,
        "ANIM_B_TILES  = %d" % animation_mod.TILES,
        "ANIM_B_BYTES  = %d" % (animation_mod.TILES * 32),
        "ANIM_B_STRIDE = 8",
        "; How high an animation number `anim_battle` reaches: the bytecode",
        "; carries the RM2k number as is and a larger one isn't in the table,",
        "; so the ROM compares it before reading it.",
        "ANIM_B_MAX    = %d" % cap,
        "; The center of the screen, which is where the ones with scope",
        "; `Scope_screen` land: `DrawAt(screen_width / 2, screen_height / 2)`.",
        "ANIM_B_CENTER_X = %d" % (animation_mod.SCREEN[0] // 2),
        "ANIM_B_CENTER_Y = %d" % (animation_mod.SCREEN[1] // 2),
        "ANIM_B_NO       = $%02X" % events.ANIM_NO_DRAWING,
        "ANIM_B_SCREEN = $%02X" % events.ANIM_TARGET_SCREEN,
    ]
    out.append(block("anim_battle",
                     bytes(slot_of.get(n, 0xFF) for n in range(cap))))
    table = bytearray()
    first = 0
    for number in order:
        info = animations[number]
        # The anchor **as the ROM wants it**: with the shift of
        # `Animation::Position` already baked in, so the console only
        # subtracts.
        ax, ay = animation_mod.rom_anchor(info)
        table += bytes([len(info["cuadros"]), ax & 0xFF, ay & 0xFF, 0,
                        first & 0xFF, first >> 8, 0, 0])
        first += len(info["cuadros"])
    out.append(block("anim_battle_table", bytes(table)))
    cgram = bytearray()
    for number in order:
        colors = [(0, 0, 0)] + list(animations[number]["paleta"])
        colors += [(0, 0, 0)] * (COLORS_PER_PALETTE - len(colors))
        for color in colors:
            cgram += cgram_word(color).to_bytes(2, "little")
    out.append(block("anim_battle_cgram", bytes(cgram)))
    # The pointer table, with labels: it can't come from `block()`, but it
    # **is declared** with `.block` for the same reason as the page one —the
    # ROM reads it with a 24-bit pointer and it can't straddle two banks—.
    pointers = [".block %d" % (4 * first), "anim_battle_frames:"]
    for number in order:
        for k in range(len(animations[number]["cuadros"])):
            pointers.append("    .dword anim_battle_%d_%d" % (number, k))
    out.append("\n".join(pointers))
    for number in order:
        info = animations[number]
        for k, frame in enumerate(info["cuadros"]):
            out.append(block("anim_battle_%d_%d" % (number, k),
                             frame_without_gaps(animation_frame(frame))))
    split = bytearray()
    for map_info in maps:
        sprite = map_info["sprite"]
        base, pal = (sprite[15], sprite[16]) if sprite else (0, 0)
        # Bit 7 is "drawn here", and below go the 64-tile block and the
        # palette, three bits each. In one byte because the map record is at
        # exactly its 128: see MAP_STRIDE.
        split.append((0x80 | ((base // 64) << 3) | pal) if base else 0)
    out.append(block("anim_battle_split", bytes(split)))
    return "\n".join(out) + "\n"


def experience_slots(db, actors):
    """The actors that carry experience and level, in the order of their slot.

    They are the ones that can join the party —`ranuras["actores"]`—, because
    only they fight and experience is only gained by fighting: the game
    doesn't use `ChangeExp` or `ChangeLevel` in any map. Having a slot of their
    own and not one per actor number is what makes the save grow by four bytes
    per actor that fights and not for each of the sixty in the LDB. **Always at
    least one**, even if it belongs to nobody: with zero the reset DMA would
    copy 64 KB.
    """
    return sorted(a for a in actors if a in db.actors) or [None]


def experience_asm(db, actors, n_actors):
    """The experience and level tables: see `port.experience`.

    It leaves the segment in RODATA, which is where its caller finds it.

    Per slot of `experience_slots`:

        exp_initial    four bytes: the starting experience, 24 bits, and the
                       level. It is what the reset copies to `FAR_EXP`.
        exp_level_max  `GetMaxLevel()`, one byte.
        exp_curve      where its row starts in `exp_table`, a word.
        level_row      six words: where each parameter curve starts in
                       `level_params`, in the order of `lcf.CURVES`.

    `exp_table` is `MakeExpList` of each distinct curve —four bytes per level,
    `LEVEL_MAX` levels— and `level_params` the six curves of each slot,
    `LEVEL_MAX` words each. Everything goes outside bank 0: it is read when
    winning a battle, when setting it up and on the equipment screen, never
    per frame.
    """
    slots_exp = experience_slots(db, actors)
    k_of = {a: k for k, a in enumerate(slots_exp) if a is not None}
    curves, curve_of, initial, max_levels, rows, params = [], [], [], [], [], []
    for a in slots_exp:
        actor = db.actors[a] if a is not None else None
        exp_curve = (X.exp_list(actor) if actor else [0])
        exp_curve = exp_curve + [0] * (X.LEVEL_MAX - len(exp_curve))
        if exp_curve not in curves:
            curves.append(exp_curve)
        curve_of.append(4 * X.LEVEL_MAX * curves.index(exp_curve))
        exp = X.initial_exp(actor) if actor else 0
        initial += [exp & 0xFF, (exp >> 8) & 0xFF, exp >> 16,
                    X.initial_level(actor) if actor else 1]
        max_levels.append(X.max_level(actor) if actor else 1)
        for curve in lcf.CURVES:
            rows.append(2 * len(params))
            values = list(actor.params.get(curve) or []) if actor else []
            values = (values + [0] * X.LEVEL_MAX)[:X.LEVEL_MAX]
            params += [v & 0xFFFF for v in values]
    if 4 * len(slots_exp) > 0x200:
        raise SystemExit("%d actors with experience don't fit in the 512 "
                         "bytes of FAR_EXP" % len(slots_exp))
    out = ['.segment "RODATA"',
           "EXP_K = %d" % len(slots_exp),
           "EXP_LEVEL_MAX = %d" % X.LEVEL_MAX]

    def table(label, directive, values, width):
        out.append(".block %d" % max(width, width * len(values)))
        out.append("%s:" % label)
        for i in range(0, len(values), 16):
            out.append("    %s %s" % (directive, ", ".join(
                str(v) for v in values[i:i + 16])))

    table("actor_exp_k", ".byte",
          [k_of.get(a, 0xFF) for a in range(n_actors)], 1)
    table("exp_initial", ".byte", initial, 1)
    table("exp_level_max", ".byte", max_levels, 1)
    table("exp_curve", ".word", curve_of, 2)
    table("exp_table", ".dword", [v for c in curves for v in c], 4)
    table("level_row", ".word", rows, 2)
    table("level_params", ".word", params, 2)
    return "\n".join(out) + "\n"


# What goes in the backdrop tables instead of a backdrop number: the plain one
# —no backdrop, which is zeros— and "the one of the place", which the ROM
# resolves when the battle starts with the map and the terrain. See
# `rom_scene`.
FLAT_BACKDROP = 0xFF
PLACE_BACKDROP = 0xFE


def rom_scene(db, troops, maps, tree, encounters, game_dir):
    """Which backdrops and which battlers the cartridge carries, and who uses
    each one.

    It is the other half of tools/port/scene.py: there is how a backdrop or
    a battler is converted, here **which ones**. Backdrops are named by their
    number in the game —see "Which backdrops there are" there—, and a battle asks for its
    own in three ways:

    * **an `EnemyEncounter` that names it**, and then it belongs to the troop
      —that is how the baked scene worked—. If two asked for it differently
      for the same troop the first one wins, as in `Troops.request`;
    * **a random encounter in a map that inherits it**, which is
      `TreeMap.map_background`: the Back Alleys areas bring no backdrop and
      take it from their map;
    * **the one of the terrain the hero is standing on**, if the map names
      none: the world, 66. The ROM resolves that one when the battle starts,
      with `backdrop_terrain`. And an `EnemyEncounter` with the backdrop "of the
      place" does the same as a random encounter: `PLACE_BACKDROP`.

    A backdrop goes **into the ROM**, light, if some battle of the cartridge
    asks for it; if some can land on one that isn't there —a troop of the
    place in a map without encounters—, `scene.replacement()` goes in too, and
    `respaldo_de` says which one of the ROM each backdrop of the game uses.
    **All of them go in the `.msu`**: `calidad` is their bytes, by number.

    A battler goes in if some troop of the cartridge uses it, **once** even if
    four use it, and it is the image with its hue: the GiantRat and the
    HairyVermin are the same `BLmouse` and two battlers.
    """
    E = scene_mod
    names_in_game = E.game_backdrops(events.named_backdrops(game_dir), tree,
                                     db.terrain_backdrops, game_dir)
    number_of = {name.lower(): k for k, name in enumerate(names_in_game)}
    if len(names_in_game) >= PLACE_BACKDROP:
        raise SystemExit("the game has %d battle backdrops and the number of "
                         "one is a byte, with $%02X and $FF reserved"
                         % (len(names_in_game), PLACE_BACKDROP))
    data = {"juego": names_in_game, "fondos": [], "battlers": [], "battler_de": {},
            "tropa_fondo": {}, "mapa_fondo": [], "respaldo_de": [],
            "terreno_fondo": [], "calidad": []}

    def number(name):
        if name is None or name is events.PLACE_BACKDROP:
            return PLACE_BACKDROP
        return number_of.get(name.lower(), FLAT_BACKDROP) if name \
            else FLAT_BACKDROP

    for n in troops.ids:
        background = troops.backdrops.get(n)
        data["tropa_fondo"][n] = number(background) if background else FLAT_BACKDROP
    # The map's, for random encounters and for the troops that fight with the
    # one of the place. Only in the maps where some battle can look at it:
    # without that, any cartridge would ask for the replacement.
    per_map = (encounters or {}).get("por_mapa") or [0xFF] * len(maps)
    place_ones = PLACE_BACKDROP in data["tropa_fondo"].values()
    for map_info, record in zip(maps, per_map):
        if record != 0xFF or place_ones:
            data["mapa_fondo"].append(
                number(tree.map_background(map_info["id"])))
        else:
            data["mapa_fondo"].append(FLAT_BACKDROP)
    terrains = db.terrain_backdrops
    data["terreno_fondo"] = [number(terrains.get(t, "")) if terrains.get(t)
                             else FLAT_BACKDROP
                             for t in range(max(terrains, default=0) + 1)]

    # The ROM's: all the ones asked for, in the order they are asked for —see
    # "Which backdrops there are" in scene.py—. A map with encounters that asks for the
    # one of the place asks for those of all the terrains of its blocks, which
    # are the ones the hero can stand on, substitutions included. A map
    # without encounters that asks for it anyway —because some troop fights
    # with the one of the place, and it isn't known where— doesn't: if its
    # terrain isn't there, the replacement goes.
    def of_terrains(map_info):
        return [data["terreno_fondo"][t]
                if t < len(data["terreno_fondo"]) else FLAT_BACKDROP
                for t in sorted(set(map_info["terreno"]))]
    requested = list(data["tropa_fondo"].values()) + data["mapa_fondo"]
    possible = []
    for map_info, record, k in zip(maps, per_map, data["mapa_fondo"]):
        if k != PLACE_BACKDROP:
            continue
        if record != 0xFF:
            requested += of_terrains(map_info)
        else:
            possible += of_terrains(map_info)
    theirs = []
    for k in requested:
        if k < PLACE_BACKDROP and k not in theirs:
            theirs.append(k)
    if any(k < PLACE_BACKDROP and k not in theirs for k in possible):
        replacement = number_of[E.replacement().lower()]
        if replacement not in theirs:
            theirs.append(replacement)
    for k in theirs:
        info = E.light_backdrop(names_in_game[k], game_dir)
        data["fondos"].append({"nombre": names_in_game[k], "numero": k,
                               "respaldo": info})
    place = {k: i for i, k in enumerate(theirs)}
    replacement = place.get(number_of[E.replacement().lower()], 0)
    data["respaldo_de"] = [place.get(k, replacement) for k in range(len(names_in_game))]
    # The quality ones, for the `.msu`: all of them, whether in the ROM or not.
    data["calidad"] = in_parallel(
        lambda name: backdrop_bytes(E.backdrop(name, game_dir)), names_in_game)
    battler_k = {}
    for number in troops.ids:
        if number not in db.troops:
            continue
        for enemy in db.troops[number].members[:constants.ENEMIES_MAX]:
            if enemy in data["battler_de"] or enemy not in db.enemies:
                continue
            e = db.enemies[enemy]
            name = e.battler_name or ""
            hue = getattr(e, "battler_hue", 0) or 0
            k = E.key(name, hue)
            if k not in battler_k:
                info = E.battler(name, hue, game_dir) if name else None
                battler_k[k] = 0xFF if info is None else len(data["battlers"])
                if info is not None:
                    data["battlers"].append(info)
            data["battler_de"][enemy] = battler_k[k]
    return data


def patch_uses(maps, db, tree):
    """Who asks for each animation and each battler of the cartridge: per
    patch class, `{key: [origin, ...]}`, where the origin is the id of the map
    whose page or random encounter asks for it, or `"caso"` if a test page
    asks for it.

    It is what lets `patches.check` know what isn't the game's in the ROM
    that is played, which also carries the suite's maps and pages: an
    animation only a case asks for, or a battler that only shows up in a test
    map, isn't versioned. The bytecode is walked, as in
    `rom_animations`, so it counts what ended up emitted. A troop
    someone asked for and no emitted page names —a page that fell out after
    asking for it— has no origin, and `patches.check` treats it as the game's: the
    doubt leans toward asking for the patch.
    """
    E = scene_mod
    animations = collections.defaultdict(set)
    troops = collections.defaultdict(set)
    for map_info in maps:
        for page in map_info.get("pages", ()):
            origin = "caso" if page.get("prueba") else map_info["id"]
            code = page.get("codigo") or b""
            for i, c in events.walk_code(code):
                if (c[i] == events.OP_ANIMATION
                        and c[i + 1] != events.ANIM_NO_DRAWING):
                    animations[c[i + 1]].add(origin)
                elif c[i] == events.OP_BATTLE:
                    troops[c[i + 1] | (c[i + 2] << 8)].add(origin)
        game_map = map_info["game_map"]
        for *_rect, which_ones in events.encounter_zones(
                tree, map_info["id"], game_map.width, game_map.height):
            for number in which_ones:
                troops[number].add(map_info["id"])
    battlers = collections.defaultdict(set)
    for number, origins in troops.items():
        if number not in db.troops:
            continue
        for enemy in db.troops[number].members[:constants.ENEMIES_MAX]:
            if enemy not in db.enemies:
                continue
            e = db.enemies[enemy]
            if e.battler_name:
                battlers[E.key(e.battler_name,
                               getattr(e, "battler_hue", 0) or 0)] |= origins
    return {"animacion": animations, "battler": battlers}


def backdrop_bytes(info):
    """A battle backdrop as the console reads it: `(tiles, colors)`, its 512
    8bpp tiles in tilemap order and its `COLORS` 15-bit colors, padded with
    black."""
    E = scene_mod
    tiles_ = bytearray()
    for cell in E.tiles(info["indices"]):
        tiles_ += pack_tile(cell, planes=8)
    colors = list(info["paleta"])
    colors += [(0, 0, 0)] * (E.COLORS - len(colors))
    cgram = bytearray()
    for color in colors:
        cgram += cgram_word(color).to_bytes(2, "little")
    return bytes(tiles_), bytes(cgram)


def fallback_bytes(info):
    """The light fallback of a backdrop, as the ROM carries it: `(bytes,
    colors)`, its 4 KB of 128x64 at 4bpp and its `FALLBACK_COLORS` colors.
    They store the index **within their palette**: the ROM adds the planes of
    `CGRAM_BASE` separately, see `fallback_height`.

    **The bytes don't go in tile order**, but in the one `scn_double` enlarges
    them in without doing any arithmetic. Each small tile becomes four large
    ones, and the ROM fills them two neighbors of the same row at a time —the
    pair that comes from the same row of eight small pixels—, pair by pair in
    the scene's order. Of each pair, large row by large row two at a time (both
    come from the same small row) and planes 0/1 before 2/3.

    And within that, **each byte carries half a byte of two planes**: of the
    small row that gives planes `p` and `p+1`, the first carries the high
    nibble of both —the four leftmost pixels, which go to the left large
    tile— and the second the two low nibbles. That way each byte, duplicated
    bit by bit with `fallback_double`, is already the two-plane word of a row
    of a large tile, and the ROM writes it whole without separating the planes.
    """
    E = scene_mod
    light = info["respaldo"]
    smalls = [pack_tile([[v - E.CGRAM_BASE for v in row] for row in cell],
                        planes=E.FALLBACK_PLANES)
              for cell in E.tiles(light["chico"])]
    columns = E.FALLBACK_WIDTH // E.CELL
    tiles_ = bytearray()
    for big_row in range(E.TILES_Y):
        half = big_row % E.FALLBACK_SCALE     # above or below the small one
        for column in range(columns):
            small = smalls[(big_row // E.FALLBACK_SCALE) * columns
                           + column]
            for pair in (0, 16):                     # planes 0/1 and 2/3
                for k in range(4):                  # the large rows 2k, 2k+1
                    row = half * 4 + k            # the small row
                    p0, p1 = small[pair + 2 * row], small[pair + 2 * row + 1]
                    tiles_.append((p0 & 0xF0) | (p1 >> 4))
                    tiles_.append(((p0 & 0x0F) << 4) | (p1 & 0x0F))
    colors = list(light["paleta"])
    colors += [(0, 0, 0)] * (E.FALLBACK_COLORS - len(colors))
    cgram = bytearray()
    for color in colors:
        cgram += cgram_word(color).to_bytes(2, "little")
    return bytes(tiles_), bytes(cgram)


def fallback_height():
    """The upper half of an 8bpp tile of the fallback: planes 4 to 7, which
    are those of `CGRAM_BASE` in every pixel. It is what the ROM appends
    after each 4bpp tile."""
    E = scene_mod
    full = [[E.CGRAM_BASE] * E.CELL for _ in range(E.CELL)]
    return pack_tile(full, planes=8)[E.FALLBACK_PLANES * 8:]


def fallback_double():
    """The table `scn_double` enlarges the fallback with: for each byte of
    `fallback_bytes`, a word with its two nibbles duplicated bit by bit, the
    high one in the low byte. Each nibble is four pixels of one plane, and
    duplicated they are the eight of a row of that plane in a large tile."""
    def double(nibble):
        return sum(0b11 << (2 * b) for b in range(4) if nibble >> b & 1)
    return b"".join((double(s >> 4) | double(s & 0xF) << 8).to_bytes(2, "little")
                    for s in range(256))


def scenes_asm(data, troops, db):
    """The cartridge's battle scene, ready for the `.inc`.

    The backdrops and the battlers **separately**, which the ROM composes when
    the battle starts: the reason and the format are in tools/port/scene.py.
    What is emitted:

      `scene_troop_backdrop` per troop index —the order of `troop_id`—, the
                            number of the backdrop its `EnemyEncounter` names,
                            `PLACE_BACKDROP` or `FLAT_BACKDROP`.
      `scene_map_backdrop`  per map index, that of its random encounters: a
                            number, `PLACE_BACKDROP` —the terrain's— or
                            `FLAT_BACKDROP`.
      `backdrop_terrain`    per terrain, the number of its backdrop or
                            `FLAT_BACKDROP`.
      `backdrop_fallback`   per backdrop number, which one of the ROM replaces
                            it without MSU-1: its own, or that of
                            `scene.replacement()`.
      `backdrop_dir`        per ROM backdrop, the 24-bit pointer to the 4 KB
                            of its light fallback, in the order of
                            `fallback_bytes`.
      `backdrop_cgram`      its 16 colors, which go to CGRAM from 32 on.

    Where each backdrop is in the `.msu` is emitted by `write_msu`, by
    number.
      `fallback_height`       planes 4 to 7, which the ROM appends to each tile.
      `battler_*`           per battler: how many bytes a row of one plane is,
                            how many rows, how big a plane is, where its bytes
                            are and its fifteen colors.
      `miembro_*`           per troop member —the order of `troop_member`—,
                            which battler it is, where its corner falls and
                            which one of the troop goes in that place of the
                            drawing order.

    The tilemap isn't emitted: it is the 512 tiles in order and the ROM builds
    it with a loop. Emitting it would be 2 KB of cartridge to write 0, 1, 2...
    """
    E = scene_mod
    backdrops, battlers = data["fondos"], data["battlers"]
    out = [
        "\n; --- the battle scene: the backdrops and the battlers ---",
        ";",
        "; They go separately and the ROM composes them in an 8bpp layer of",
        "; 256x128, which is the seven text lines at the top. The reason is",
        "; in tools/port/scene.py; only the bytes travel here.",
        "; The game's backdrops, which the .msu carries all of, and the ROM's.",
        "BACKDROPS_GAME  = %d" % len(data.get("juego", ())),
        "SCENE_BACKDROPS = %d" % len(backdrops),
        "BACKDROP_PLAIN  = $%02X" % FLAT_BACKDROP,
        "PLACE_BACKDROP = $%02X" % PLACE_BACKDROP,
        "BACKDROP_TERRAINS = %d" % len(data.get("terreno_fondo") or [0]),
        "SCENE_BATTLERS = %d" % len(battlers),
        "SCENE_WIDTH     = %d" % E.WIDTH,
        "SCENE_HEIGHT    = %d" % E.HEIGHT,
        "SCENE_TILES     = %d" % E.TILES,
        "SCENE_ROWS      = %d" % E.TILES_Y,
        "SCENE_COLUMNS = %d" % E.TILES_X,
        "SCENE_COLORS    = %d" % E.COLORS,
        "SCENE_CGRAM     = %d" % E.CGRAM_BASE,
        "SCENE_VRAM      = $%04X" % E.VRAM_TILES,
        "SCENE_MAP       = $%04X" % E.VRAM_MAP,
        "; The ROM's light fallback: 4bpp and a single palette. See",
        "; tools/port/scene.py.",
        "FALLBACK_COLORS = %d" % E.FALLBACK_COLORS,
        "FALLBACK_TILE   = %d" % (E.FALLBACK_PLANES * 8),
        "FALLBACK_BYTES  = %d" % (E.FALLBACK_WIDTH * E.FALLBACK_HEIGHT
                                  * E.FALLBACK_PLANES // 8),
        "FALLBACK_SCALE = %d" % E.FALLBACK_SCALE,
        "SCENE_BAT_PALETTE = %d" % E.BATTLER_PALETTE,
        "; The tile that covers what is left below the scene. It falls",
        "; **outside** the tile block: 512 8bpp tiles are the 16,384 words",
        "; that go from SCENE_VRAM to the end of VRAM, so 512 wraps around",
        "; and lands on word 0, which during the battle is map VRAM that",
        "; nobody uses.",
        "SCENE_TARGET    = %d" % E.TILES,
    ]
    used = [n for n in troops if n in db.troops]
    out.append(block("scene_troop_backdrop", bytes(
        data["tropa_fondo"].get(n, 0xFF) for n in used) or b"\xFF"))
    out.append(block("scene_map_backdrop",
                     bytes(data["mapa_fondo"]) or b"\xFF"))
    out.append(block("backdrop_terrain",
                     bytes(data.get("terreno_fondo") or [FLAT_BACKDROP])))
    out.append(block("backdrop_fallback",
                     bytes(data.get("respaldo_de") or [0])))
    pointers = [".block %d" % (4 * max(1, len(backdrops))), "backdrop_dir:"]
    for k in range(len(backdrops)):
        pointers.append("    .dword backdrop_%d" % k)
    if not backdrops:
        pointers.append("    .dword 0")
    out.append("\n".join(pointers))
    drawing_bytes = [fallback_bytes(info) for info in backdrops]
    cgram = b"".join(colors for _tiles, colors in drawing_bytes)
    out.append(block("backdrop_cgram", cgram or b"\x00\x00"))
    out.append(block("fallback_height", fallback_height()))
    out.append(block("fallback_double", fallback_double()))
    # Where each quality backdrop is in the `.msu` and the signature the ROM
    # expects to find at the start don't go here: the `.msu` also carries the
    # sound effects, which come from the audio, and that is built later. See
    # `msu_asm`.
    # Sixty-four zeros: the transparent tile that covers what is left below
    # the scene, and incidentally the fixed source of the DMA that fills the
    # plain backdrop with zero.
    out.append(block("scene_zero", bytes(64)))
    # Each fallback in a block, which doesn't cross a bank because the ROM
    # reads it with `[puntero]` and adds to the pointer only the low sixteen
    # bits.
    for k, (tiles_, _colors) in enumerate(drawing_bytes):
        out.append(block("backdrop_%d" % k, tiles_))
    # The battlers: their tables and then their bytes, each in a block that
    # doesn't cross a bank because the ROM reads it with `[puntero], y`.
    out.append(block("battler_n", bytes(
        E.columns(b) for b in battlers) or b"\x00"))
    out.append(block("battler_height", bytes(
        b["alto"] for b in battlers) or b"\x00"))
    planes = bytearray()
    for b in battlers:
        planes += ((E.columns(b) + 1) * b["alto"]).to_bytes(2, "little")
    out.append(block("battler_plane", bytes(planes) or b"\x00\x00"))
    pointers = [".block %d" % (4 * max(1, len(battlers))), "battler_dir:"]
    pointers += ["    .dword battler_%d" % k for k in range(len(battlers))]
    if not battlers:
        pointers.append("    .dword 0")
    out.append("\n".join(pointers))
    cgram = bytearray()
    for b in battlers:
        colors = [(0, 0, 0)] + list(b["paleta"])
        colors += [(0, 0, 0)] * (16 - len(colors))
        for color in colors:
            cgram += cgram_word(color).to_bytes(2, "little")
    out.append(block("battler_cgram", bytes(cgram) or b"\x00\x00"))
    member_b, member_x, member_y, member_command = [], [], [], []
    for number in used:
        troop = db.troops[number]
        theirs = list(zip(troop.members,
                          troop.positions))[:constants.ENEMIES_MAX]
        infos = []
        for enemy, center in theirs:
            k = data["battler_de"].get(enemy, 0xFF)
            member_b.append(k)
            infos.append(battlers[k] if k != 0xFF else None)
            x, y = (E.position(center, battlers[k]) if k != 0xFF else (0, 0))
            member_x.append(x)
            member_y.append(y)
        # And the order they are drawn in, which isn't the troop's: see
        # `scene.drawing_order`. It goes per member, with the place in the
        # troop.
        member_command += E.drawing_order([c for _e, c in theirs], infos)
    out.append(block("member_battler", bytes(member_b) or b"\xFF"))
    out.append(block("member_x", bytes(member_x) or b"\x00"))
    out.append(block("member_y", bytes(member_y) or b"\x00"))
    out.append(block("member_command", bytes(member_command) or b"\x00"))
    for k, b in enumerate(battlers):
        out.append(block("battler_%d" % k, E.battler_bytes(b)))
    return "\n".join(out) + "\n"


def block(label, data, per_line=16, align=None, fit=True):
    """A data block with its placement declaration.

    Each block is declared before emitting it: almost all are uploaded by DMA,
    and a DMA that crosses a bank reads garbage from the middle onward. The
    cell grid isn't uploaded by DMA but walked with a pointer, so it doesn't
    need the whole bank: only that its words don't end up split between the
    end of one bank and the start of the next.

    The same holds for a table walked with `[ptr], y` or with
    `lda f:tabla, x`: it has to stay whole on one side, and its pointers being
    symbolic isn't enough. Split, the ROM reads the second half from `$0000`
    of the next bank, which in LoROM is the WRAM mirror. That is how the event
    page table ended up straddling `$02FFFF` the day a map's sprites grew, and
    what was seen was a background shifted six pixels: it is an error that
    appears or disappears when adding a byte anywhere else in the cartridge.

    `acomodar=False` is for what goes to TABLES: that area lives entirely
    inside bank 0 —it ends at $7FC0—, so nothing that falls there can cross,
    and declaring it emitted a computation that always came out zero.
    """
    out = ([".align %d" % align if align else ".block %d" % len(data)]
           if fit else [])
    out.append("%s:" % label)
    for i in range(0, len(data), per_line):
        out.append("    .byte " + ",".join("$%02X" % b
                                           for b in data[i:i + per_line]))
    return "\n".join(out)


def page_table(map_info, number, evcode):
    """The map's event pages, with the pointer to their code.

    `evcode` is the **label** of the code block, which can no longer be
    rebuilt here: two maps whose events compile to the same bytes share the
    block and the label doesn't carry this map's number. Rebuilding it is what
    it did —`"evcode_%d" % numero`— and when deduplication was turned on the
    suite caught it right away: `varios` didn't assemble because it named an
    `evcode_2` that no longer existed.

    It doesn't go through `block()` because its pointers are symbolic: they
    point inside the code block, which the linker places. But it **is
    declared** with `.block`: the ROM walks it with `[page_ptr], y`, and a
    table that crosses a bank continues at `$03:0000`, which in LoROM isn't
    ROM but the WRAM mirror. Without the declaration it really happened: when
    map 2's sprites grew with the events drawn with a tile, the table ended up
    straddling `$02FFFF`, the ROM read garbage instead of the last pages
    —among them the test one— and the shake at the edge of the map never
    started. The suite caught it in pixels without saying why; the
    emulator's RAM said it.
    """
    out = [".block %d" % (PAGE_BYTES * len(map_info["pages"])),
           "pages_%d:" % number]
    # Which events have some page with its own route: the ROM's refresh only
    # looks at the pages of those, and doesn't spend a single read on the rest.
    with_route = {p["event"] for p in map_info["pages"] if p.get("ruta_propia")}
    # And which ones change graphic with the page: the refresh also looks at
    # those, bit 5, and copies to the row what the active page draws.
    changing = map_info.get("cambian", set())
    # And which ones only appear and disappear with it: the ones that walk.
    # They go by the **same** bit 5, because none is left free in +13 —with an
    # own route the five low ones are the route's flags, and 4 is "the
    # animation continues while still"—. The one telling them apart is the
    # ROM, which already knows whether the row walks: `npc_buf + 9` holds
    # NPC_STILL or the bank of its twelve poses. See `page_graphic` in
    # tools/runtime/event_pages.s.
    appear = map_info.get("aparecen", set())
    # And which ones have some automatic page that compiled: bit 7. The ROM's
    # refresh has to know whether an event's active page is automatic —that
    # is where what starts on its own comes from— and with this it saves
    # reading the pages of the events that can never be. It is the same trick
    # as bit 6.
    #
    # The **parallel** ones go by this same bit, and not by one of their own:
    # none is left free in +13. The bit means "look at this event's pages in
    # the refresh", which is what both need; which is automatic and which is
    # parallel is said by the trigger of the one that wins. Without this,
    # `pick_pages` doesn't even note which one is active —it filters by
    # $E0— and `parallel_tick` would have nowhere to get its code from.
    with_autostart = {p["event"] for p in map_info["pages"]
                      if p["trigger"] in (events.TRIGGER_AUTOSTART,
                                          events.TRIGGER_PARALLEL) and p["codigo"]}
    for page in map_info["pages"]:
        if page["codigo"]:
            dest = "%s + %d" % (evcode, page["offset"])
            pointer = "<(%s), >(%s), ^(%s)" % (dest, dest, dest)
        else:
            pointer = "$00, $00, $00"   # no code: nothing to run
        out.append("    .word %-4d ; +0  the event it belongs to"
                   % page["event"])
        out.append("    .byte %-4d ; +2  its page number" % page["pagina"])
        out.append("    .byte %-4d ; +3  what triggers it" % page["trigger"])
        out.append("    .word %-4d ; +4  switch it asks for, or 0" % page["switch_a"])
        out.append("    .word %-4d ; +6  the second, or 0" % page["switch_b"])
        out.append("    .byte %s ; +8  its code" % pointer)
        out.append("    .byte %-4d ; +11 the actor it asks for in the party, or 0"
                   % page["actor"])
        out.append("    .byte %-4d ; +12 its layer: 1 is the hero's, the one "
                   "that blocks its way" % page["capa"])
        own = page.get("ruta_propia")
        if own:
            # The page's own route, the one it walks by itself: see
            # `events.own_route`. The flags: bit 0 it has one, 1 it
            # repeats, 2 it skips what is blocked, 3 it always faces the same
            # way, 4 the animation continues while still.
            flags = (1 | (2 if own["repite"] else 0)
                     | (4 if own["saltable"] else 0)
                     | (8 if own["dir_fija"] else 0)
                     | (16 if own["anim_continues"] else 0) | 64
                     | (32 if page["event"] in changing
                                 or page["event"] in appear else 0)
                     | (128 if page["event"] in with_autostart else 0))
            dest = "%s + %d" % (evcode, page["ruta_offset"])
            out.append("    .byte %-4d ; +13 the flags of its own route"
                       % flags)
            out.append("    .byte %-4d ; +14 its frequency" % own["frecuencia"])
            out.append("    .byte %-4d ; +15 and its speed" % own["speed"])
            out.append("    .byte <(%s), >(%s), ^(%s) ; +16 its commands"
                       % (dest, dest, dest))
            out.append("    .byte %-4d ; +19 how many" % len(own["ordenes"]))
        else:
            out.append("    .byte %-4d ; +13 no own route; bit 6 says whether "
                       "another page of the event has one, 5 whether the "
                       "graphic follows the page, 7 whether the event has some "
                       "automatic one"
                       % ((64 if page["event"] in with_route else 0)
                          | (32 if page["event"] in changing
                                   or page["event"] in appear else 0)
                          | (128 if page["event"] in with_autostart else 0)))
            out.append("    .byte %-4d ; +14 its frequency" % page["frecuencia"])
            out.append("    .byte %-4d ; +15 and its speed, that of a route "
                       "forced on the event" % page["speed"])
            out.append("    .byte 0,0,0,0")
        # +20..+23: what the page draws, for the events that change graphic:
        # the tile, the attributes with the palette and the priority of its
        # layer, the pose with bit 7 set if there is a graphic, and the
        # passage bits of its tile or $FF. It is what the refresh copies to
        # the row.
        oam = page.get("oam")
        if oam is None:
            out.append("    .byte $00, $00, $00, $FF ; +20 no graphic")
        else:
            out.append("    .byte $%02X, $%02X, $%02X, $%02X ; +20 its graphic: "
                       "tile, attributes, pose, passage" % oam)
        # +24..+27: the variable condition: the slot or $FF, how it is
        # compared —==, >=, <=, >, <, !=— and against what, signed. It is what
        # `conditions_ok` passes to `compare_var`.
        variable = page.get("variable")
        if variable is None:
            out.append("    .byte $FF, 0 ; +24 no variable condition")
            out.append("    .word 0")
        else:
            slot, comparison, against = variable
            out.append("    .byte %d, %d ; +24 the variable it asks for and the "
                       "comparison" % (slot, comparison))
            out.append("    .word %d ; +26 against what" % (against & 0xFFFF))
        # +28: the item it asks to have, or 0: `conditions_ok` looks at its
        # count in `FAR_ITEMS`.
        out.append("    .word %-4d ; +28 the item it asks for, or 0" % page["item"])
        # +30 and +31: the turn toward the hero. Which entry of `npc_poses`
        # the poses of its graphic are in, or $FF if the page doesn't turn,
        # and its pose. When triggered, the ROM uploads the one facing the
        # hero; on a refresh, a change to a page that doesn't turn or has
        # another graphic undoes the turn. See TURN in events.py.
        graphic = page.get("grafico")
        k = (map_info.get("giro_k", {}).get(tuple(graphic[:2]))
             if page.get("gira") and graphic and page["event"] in
             map_info.get("giran", ()) else None)
        out.append("    .byte $%02X, %d ; +30 the turn: its poses and its pose"
                   % (0xFF if k is None else k, graphic[2] if k is not None else 0))
        assert PAGE_BYTES == 32
    if not map_info["pages"]:
        out.append("    .byte $00")     # a label can't be left empty
    return "\n".join(out)


class Materials:
    """The ROM's data blocks, with an identity of their own and not the map's.

    Each map used to emit its blocks with its number attached —`map_tiles_0`,
    `map_tiles_1`— and the map record built the pointer's name with that same
    computation. That is, a block's identity **was** the map that asked for
    it, and two maps with the same tiles paid for them twice without anywhere
    to notice.

    Here the block has a name of its own and the map stores which one it
    points to, which is what is needed before anything can be shared. The
    numbering is still per class and in map order, so without deduplicating
    the names are the usual ones and the ROM comes out byte for byte the
    same: it is on purpose, so that this step can be verified without
    depending on the suite.

    The poses already worked this way from before —`global_index` in `emit`—
    and that is where the shape comes from.
    """

    def __init__(self, dedupe=False, compressed=None):
        self.dedupe = dedupe
        self.where = {}
        self.counts = collections.Counter()
        self.saved = collections.Counter()
        self.repeated = collections.Counter()
        # {raw bytes: their LZ2 stream}, already compressed in one go: see
        # `compress_blocks`. And how much each class weighed and weighs,
        # of the blocks that were emitted.
        self.compressed = compressed or {}
        self.raw = collections.Counter()
        self.lz2 = collections.Counter()

    def store_compressed(self, kind, data):
        """Like `store`, but what goes to the cartridge is its LZ2 stream, or
        its streams stuck together if the block goes in pieces: see
        `compressed_parts`. It is deduplicated by the raw content, which is
        the same as by the stream."""
        data = bytes(data)
        stream = b"".join(self.compressed[part]
                          for part in compressed_parts(kind, data))
        label, text = self.store(kind, stream)
        if text:
            self.raw[kind] += len(data)
            self.lz2[kind] += len(stream)
        return label, text

    def store(self, kind, data, align=None):
        """(label, the asm to emit). The asm is empty if the block was already
        there.

        The key includes the class and the placement, not only the content:
        two blocks with the same bytes but a different `.block` or `.align`
        aren't the same block for the linker.
        """
        data = bytes(data)
        key = (kind, align, data)
        if key in self.where:
            if self.dedupe:
                self.saved[kind] += len(data)
                self.repeated[kind] += 1
                return self.where[key], ""
        label = "%s_%d" % (kind, self.counts[kind])
        self.counts[kind] += 1
        self.where.setdefault(key, label)
        return label, block(label, data, align=align)

    def report(self):
        """What was shared and how much was compressed, so that the saving is a
        number and not an idea."""
        lines = ["  %-14s %6.1f KB in LZ2, was %6.1f"
                 % (kind, self.lz2[kind] / 1024.0,
                    self.raw[kind] / 1024.0)
                 for kind in COMPRESSED_KINDS if self.raw[kind]]
        if self.raw:
            lines.append("  %-14s %6.1f KB in LZ2, was %6.1f: %.1f KB less"
                         % ("", sum(self.lz2.values()) / 1024.0,
                            sum(self.raw.values()) / 1024.0,
                            (sum(self.raw.values())
                             - sum(self.lz2.values())) / 1024.0))
        if not self.dedupe or not self.saved:
            return lines
        return lines + ["  %-14s %2d shared block(s), %6.1f KB"
                % (kind, self.repeated[kind], self.saved[kind] / 1024.0)
                for kind, _ in self.saved.most_common()] + [
            "  %-14s %2d              %6.1f KB in total"
            % ("", sum(self.repeated.values()),
               sum(self.saved.values()) / 1024.0)]


def terrain_plane(map_info):
    """The terrain the whole map has, or 0 if it has more than one.

    0 isn't a terrain: RM2k's are indices into `Data.terrains` and start at 1,
    so it serves as "there is a table here" without spending another field. A
    map with terrain 0 —which doesn't exist— falls into the table branch,
    which answers the same.
    """
    unique = set(map_info["terreno"])
    return unique.pop() if len(unique) == 1 else 0


def map_terrain(map_info):
    return (bytes([terrain_plane(map_info)]) if terrain_plane(map_info)
            else bytes(map_info["terreno"]))


# What the ROM decompresses when loading a map, per block class. See
# `lz2_decompress` in tools/runtime/decompress.s.
COMPRESSED_KINDS = ("map_tiles", "above_tiles", "sprite_tiles", "anim_tiles",
                    "map_cells")

# The largest each decompressed stream can be, by where it lands in WRAM: see
# the LZ2 reservation in tools/runtime/far_ram.s, which is where they come
# from, and the `.assert` in decompress.s, which checks them against the
# ones here. The background tiles are decompressed before the animation
# drawings and can step on their place; the upper layer and the sprites go
# after and can't.
#
# The background's is **per stream**, not per block: a background of more
# than 32 KB —that of map 66, with the 544-tile layout— goes in two, and the
# ROM decompresses and uploads the first before decompressing the second on
# top of it: see `lz2_backdrop`.
LZ2_CAP_BACKDROP = 0x8000
LZ2_CAP_ABOVE_AND_SPRITES = 0x6000
LZ2_CAP_ANIM = 0x2000
LZ2_CAP_GRID = 0x10000       # two halves of HALF_GRID


# What decompressing costs in the ROM, in master cycles, **on the high side**:
# measured on 2026-09-26 over the forty maps of `release`, against loading
# uncompressed, what was measured doesn't exceed this model by more than half
# a frame. An NTSC frame is 357,954 master cycles. The boot computation uses
# it.
LZ2_CYCLES_PER_COMMAND = 700
LZ2_CYCLES_PER_BYTE = 60
CYCLES_PER_FRAME = 357954


def decompress_frames(map_info, compressed):
    """How many frames decompressing a map's blocks takes."""
    cycles = 0
    for kind, data in map_raw(map_info).items():
        if kind not in COMPRESSED_KINDS:
            continue
        for part in compressed_parts(kind, data):
            cycles += (compress.commands(compressed[part])
                       * LZ2_CYCLES_PER_COMMAND
                       + len(part) * LZ2_CYCLES_PER_BYTE)
    return cycles / float(CYCLES_PER_FRAME)


def compress_blocks(maps):
    """{raw bytes: LZ2 stream} of everything the cartridge carries
    compressed, with a single `lz2` process. Along the way it enforces the
    WRAM caps."""
    parts = []
    for map_info in maps:
        for kind, data in map_raw(map_info).items():
            if kind not in COMPRESSED_KINDS:
                continue
            check_streams(map_info["id"], kind, data)
            parts += compressed_parts(kind, data)
    parts = list(dict.fromkeys(parts))
    return dict(zip(parts, compress.compress_many(parts)))


# The grid goes to the upper half of the two WRAM banks —see `lz2_grid`—, so
# it is compressed in two streams of up to 32 KB: each one lands whole in one
# bank, and the decompressor doesn't have to know how to cross.
HALF_GRID = 0x8000


# And the background tiles, in streams of whatever fits in the load buffer:
# the ROM decompresses one, uploads it by DMA and only then decompresses the
# next in the same place —see `lz2_backdrop`—. A background that fits in one
# goes in one, and that leaves the usual maps with the usual stream.
BACKDROP_STREAMS_MAX = 2            # the ones `lz2_backdrop` reads


def compressed_parts(kind, data):
    """The pieces of a block that are each compressed in their own stream."""
    if kind == "map_cells":
        return [data[:HALF_GRID], data[HALF_GRID:]]
    if kind == "map_tiles" and len(data) > LZ2_CAP_BACKDROP:
        return [data[k:k + LZ2_CAP_BACKDROP]
                for k in range(0, len(data), LZ2_CAP_BACKDROP)]
    return [data]


# How much of each stream fits in WRAM, and how many streams the ROM reads per
# block. The grid always goes in two, one per half; the rest in one, except
# the background.
CAPS_PER_STREAM = {"map_tiles": (LZ2_CAP_BACKDROP, BACKDROP_STREAMS_MAX),
                   "above_tiles": (LZ2_CAP_ABOVE_AND_SPRITES, 1),
                   "sprite_tiles": (LZ2_CAP_ABOVE_AND_SPRITES, 1),
                   "anim_tiles": (LZ2_CAP_ANIM, 1),
                   "map_cells": (HALF_GRID, 2)}


def check_streams(map_id, kind, data):
    """That each stream of the block fits in its WRAM place, and that there
    aren't more streams than the ROM reads. A stream that goes over breaks
    nothing when building: the ROM decompresses it anyway and steps on
    whatever is behind —with map 66's background, the upper half of the
    grid—, and it shows or not depending on the map."""
    cap, count = CAPS_PER_STREAM[kind]
    parts = compressed_parts(kind, data)
    for part in parts:
        if len(part) > cap:
            raise SystemExit(
                "map %d: a stream of %s is %d bytes and %d fit in WRAM: "
                "see the LZ2 reservation in tools/runtime/far_ram.s"
                % (map_id, kind, len(part), cap))
    if len(parts) > count:
        raise SystemExit(
            "map %d: %s is %d bytes, which is %d streams, and the ROM reads %d"
            % (map_id, kind, len(data), len(parts), count))


def map_raw(map_info):
    """{class: the uncompressed bytes} of a map, for `COMPRESSED_KINDS`."""
    above, sprite = map_info["above"], map_info["sprite"]
    return {"map_tiles": bytes(map_info["tiles"]),
            "above_tiles": bytes(above[0]),
            "sprite_tiles": bytes(sprite[0]) if sprite else b"",
            "anim_tiles": bytes(map_info["anim"]),
            "map_cells": bytes(map_info["celdas"])}


def write_raw(directory, maps):
    """Leaves in `directorio/crudos/` what the ROM has to have in VRAM and in
    WRAM after loading each map, uncompressed: `<index>.<class>.bin`, with the
    map's index in the ROM.

    It is the other end of the compression tests: `test_lz2.py` does the round
    trip of each block, and `test_carga_descomprimida.py` compares what the
    ROM decompressed against this. It comes from the converter and not from
    the ROM precisely so that it isn't the ROM answering itself.

    It is deleted entirely before writing: a map that left the cartridge would
    leave its file, and a test that walks the directory would look at it.
    """
    offset = os.path.join(directory, "crudos")
    if os.path.isdir(offset):
        shutil.rmtree(offset)
    os.makedirs(offset)
    for number, map_info in enumerate(maps):
        for kind, data in map_raw(map_info).items():
            with open(os.path.join(offset, "%d.%s.bin" % (number, kind)),
                      "wb") as f:
                f.write(data)


def map_data(map_info, number, global_index, materials):
    """A map's data blocks, with the number attached to each label.

    `global_index` are the labels of the twelve poses of each (CharSet,
    index) **as this map quantized it**: see `pose_bank`, and the pose
    split in `emit`.
    """
    above, sprite = map_info["above"], map_info["sprite"]
    pairs = [
        ("map_tiles", map_info["tiles"]),
        ("map_cgram", map_info["cram"]),
        ("above_tiles", above[0]),
        ("above_cgram", above[1]),
        ("sprite_tiles", sprite[0] if sprite else b""),
        ("sprite_cgram", sprite_colors_bytes(sprite)),
        ("map_blocks", map_info["bloques"]),
        ("block_pass", map_info["pass"]),
        # The terrain per block. A map whose terrain is the same everywhere
        # —the 328 of this game, which have it at 1— emits **one byte** and
        # `TERRENO_PLANO` says which: the whole table would be about eight
        # kilobytes of nothing spread over the forty maps. The byte is
        # deduplicated by `materials`, so all flat maps with the same terrain
        # share the same one.
        ("block_terrain", map_terrain(map_info)),
        ("npc_table", npc_bytes(sprite[3]) if sprite else b""),
        # Two bytes per graphic of command 34: its entry in `npc_poses` —or
        # $FF, which is hiding— and its palette. See `Graphics` in events.py.
        ("route_graphic",
         bytes(b for pair in (sprite[9] if sprite else []) for b in pair)),
        ("ev_pos", map_info["ev_pos"]),
        ("evcode", map_info["evcode"]),
        ("anim_tiles", map_info["anim"]),
    ]
    labels, out = {}, []
    for name, data in pairs:
        if name in COMPRESSED_KINDS:
            labels[name], text = materials.store_compressed(name, data)
        else:
            labels[name], text = materials.store(name, data)
        if text:
            out.append(text)
    # The two tables of pointers to the ROM's poses: that of the NPCs that
    # walk and that of the leader candidates.
    animated = sprite[7] if sprite else []
    out.append(npc_poses_asm(number, animated, global_index))
    out.append(actor_table_asm(number, sprite[4] if sprite else [],
                               animated, global_index))
    # The grid, in its two streams: see `lz2_grid`. Whole within one bank,
    # like everything compressed, because the decompressor doesn't cross.
    labels["map_cells"], text = materials.store_compressed(
        "map_cells", map_info["celdas"])
    if text:
        out.append(text)
    out.append(page_table(map_info, number, labels["evcode"]))
    # The three that aren't shared are the ones that carry **symbolic
    # pointers** inside —to the ROM's poses, to the events' code—: their bytes
    # are set by the linker, so here there is no content to compare them by.
    for name in ("npc_poses", "actor_table", "pages"):
        labels[name] = "%s_%d" % (name, number)
    return "\n".join(out), labels


def rom_encounters(maps, tree, test_steps, troops):
    """The random encounters of each map of the cartridge, ready to emit.

    The data lives in the tree and not in the `.lmu`: each node brings its
    list of troops, every how many steps, and —if it is an area— the
    rectangle it covers. See `events.encounter_zones`.

    Along the way it **asks for the troops**, which is what makes the
    cartridge carry their enemies and the battle's audio package: without
    that an encounter would start a battle against a troop that isn't in any
    table.

    `test_steps` replaces the `encounter_steps` of every map. It is for
    the test ROMs: with the game's —from 25 to 85— an encounter takes more than
    a hundred steps, which is what is wanted when playing and not what is
    wanted in a case of the suite.
    """
    records, zones, zone_troops, per_map = [], [], [], []
    for map_info in maps:
        game_map = map_info["game_map"]
        theirs = events.encounter_zones(tree, map_info["id"],
                                        game_map.width, game_map.height)
        steps = (test_steps if test_steps is not None
                 else tree.encounter_steps.get(map_info["id"],
                                               events.ENC_DEFAULT_STEPS))
        if not theirs or not events.enc_base(steps):
            per_map.append(0xFF)
            continue
        per_map.append(len(records))
        record = {"base": events.enc_base(steps),
                  "umbrales": events.enc_step_thresholds(steps),
                  "zona_ini": len(zones), "zona_n": len(theirs)}
        for left, top, right, bottom, which_ones in theirs:
            zones.append({"rect": (left, top, right, bottom),
                          "troop_init": len(zone_troops),
                          "troop_n": len(which_ones)})
            for number in which_ones:
                troops.request(number)
            zone_troops += which_ones
        records.append(record)
    if len(records) > 0xFF or len(zones) > 0xFF or len(zone_troops) > 0xFF:
        # The three tables are indexed with one byte. With the 53 maps of the
        # whole game it is 53 records, 56 zones and 322 troops, so the one
        # that can go over is the last —and today only in a cartridge that
        # carries all of them—.
        sys.exit("the encounters don't fit in one-byte tables: %d "
                 "record(s), %d zone(s), %d troop(s)"
                 % (len(records), len(zones), len(zone_troops)))
    return {"por_mapa": per_map, "registros": records, "zonas": zones,
            "tropas": zone_troops}


# The header title of a SNES ROM: 21 bytes, at `$FFC0`.
TITLE_HEADER = 21


def rom_identity():
    """What the ROM says about itself, from the `[rom]` of the project file:
    the header title, already padded with blanks, and the save signature in
    SRAM. They are `.define`s because they are text: `header.s` and
    `save_game.s` use them, and until 2026-09-29 they had them written in."""
    title = settings.ascii("rom", "title", max_length=TITLE_HEADER)
    signature = settings.ascii("rom", "sram_signature", length=4)
    return ("; Who the ROM is, from the project file: the header title and\n"
            "; the signature with which the SRAM says a slot holds a save of\n"
            "; this game.\n"
            '.define ROM_TITLE "%s"\n'
            '.define SRAM_MAGIC_TEXT "%s"\n\n'
            % (title.ljust(TITLE_HEADER), signature))


def emit(path, maps, initial=0, hero_above=False, initial_party=(),
         window=None, title=None, slots=None, picture_info=None,
         animations=None, troops=(), battle_audio=None, scenes=None,
         encounters=None, troop_pages=None, compressed=None,
         enemy_hp=False, game_over=None):
    """The .inc that is assembled together with main.s.

    `enemy_hp` is `--enemy-hp`: whether the battle draws the
    enemies' HP, which RM2k doesn't show.

    `compressed` is what `compress_blocks` returns; if missing it is
    compressed here.

    `title` is the title screen —the image and its menu— and may be missing;
    `game_over`, the Game Over one, too: it is what
    `fullscreen.compressed` returns.
    `slots` is the slots screen and **always goes**: the save point opens it
    from inside the game, whether the ROM has a title or not. See
    `slots_screen` in menus.py.
    """
    for number, map_info in enumerate(maps):
        layout = map_info["layout"]
        for count, name in (
                (len(map_info["tiles"]) // BYTES_PER_TILE, "tiles"),
                (len(map_info["above"][0]) // 32, "encima"),
                (len(map_info["sprite"][0]) // 32 if map_info["sprite"] else 0,
                 "sprites")):
            if count > layout[name][1]:
                raise SystemExit(
                    "map %d: with this VRAM layout, %s needs %d tiles and "
                    "%d fit" % (map_info["id"], name, count,
                                layout[name][1]))

    # Where the picture ended up: the map of the table that took its tiles, and
    # at which tile and with which palette. It comes from the already
    # converted maps and not from a variable that has to be passed around: the
    # one that has it is the only one with a nonzero `image_base`.
    picture_base, picture_pal = 0, 0
    for map_info in maps:
        if map_info["sprite"] and map_info["sprite"][13]:
            picture_base, picture_pal = map_info["sprite"][13], map_info["sprite"][14]
            break

    header = (
        "; Generated by tools/port/snes_convert.py. Do not edit.\n"
        "; Maps: %s\n\n"
        "MAP_COUNT    = %d\n"
        "MAP_STRIDE   = %d\n"
        "MAP_INITIAL = %d\n"
        "; What doesn't depend on the map: the upper layer's tilemap always\n"
        "; lives in the same place in VRAM —the background's is chosen by the\n"
        "; layout, M_VRAM_MAP—, and the NPC table's stride doesn't change.\n"
        "VRAM_ABOVE_MAP = $%04X\n"
        "MAP_LAYOUT  = %d\n"
        "NPC_STRIDE  = %d\n"
        "NPC_MAX     = %d\n"
        "NPC_STILL   = $%02X\n"
        "; The event position table, and how many forced routes can be\n"
        "; running on them at once.\n"
        "EV_STRIDE   = %d\n"
        "EV_MAX      = %d\n"
        "ROUTE_EV_MAX = %d\n"
        "PAGE_BYTES = %d\n"
        "TURN_NONE = $%04X\n"
        "; And how many distinct graphics command 34 can ask for in a map:\n"
        "; its table is copied to RAM like the NPC one.\n"
        "ROUTE_GFX_MAX = %d\n"
        "; The header of a text box, which is the first byte of the one\n"
        "; `OP_MESSAGE` names: the lines in the low three bits, the\n"
        "; auto-close of `\\^` in bit 3 and how many `\\|` pauses it carries in\n"
        "; the high nibble. And how long each pause lasts, which is 61 frames\n"
        "; and not 60: see PAUSE_FRAMES in events.py.\n"
        "HEADER_LINES        = $%02X\n"
        "HEADER_AUTOCLOSE = $%02X\n"
        "PAUSE_FRAMES        = %d\n"
        "; The top bit of the flags byte of the opcodes that write a\n"
        "; variable: whether the write asks for the page refresh. The\n"
        "; converter resolves it by looking at which variables this map's\n"
        "; page conditions look at; `var_apuntar` masks the slot with\n"
        "; VAR_SLOT. See VAR_REFRESH in events.py: without this half of\n"
        "; Lashe City ran at 30 frames.\n"
        "VAR_REFRESH = $%02X\n"
        "VAR_SLOT     = $%02X\n"
        "ANIM_ENTRY = %d\n"
        "ANIM_SOUND   = %d\n"
        "ANIM_FLASH = %d\n"
        "; The ShowPicture picture: where its corner falls on the console's\n"
        "; screen and how many 32x32 objects it measures.\n"
        "; The coordinates already come scaled from 320x240 to 256x224 and X\n"
        "; can be negative: the \"1 year earlier\" picture goes off the left\n"
        "; edge, which is what RM2k shows. See tools/port/picture.py.\n"
        "; The flags of `KeyInputProc`, which go in the second byte of\n"
        # `rom/src/` on purpose: it goes into the `.inc`, which isn't touched
        # yet.
        "; OP_KEY. See `op_key` in rom/src/interpreter_keys_and_waits.s.\n"
        "KEY_WAIT       = $%02X\n"
        "KEY_DIRS       = $%02X\n"
        "KEY_DECISION = $%02X\n"
        "KEY_CANCEL = $%02X\n"
        "KEY_STARTS     = $%02X\n"
        "KEY_VALUE_DECISION = %d\n"
        "KEY_VALUE_CANCEL = %d\n"
        "; And the four directions, with the same number `CheckInput` gives\n"
        "; them. The order they are checked in comes from here: from highest\n"
        "; to lowest, which is what \"RPG processes keys from highest\n"
        "; variable value to lowest\" says.\n"
        "KEY_VALUE_UP         = %d\n"
        "KEY_VALUE_RIGHT      = %d\n"
        "KEY_VALUE_LEFT = %d\n"
        "KEY_VALUE_DOWN       = %d\n"
        "; Which tile of its sprite bank it starts at and with which palette.\n"
        "; They are globals and not in the map record because the picture is\n"
        "; **a single one per ROM** and lives in a single map: the two fields\n"
        "; took the last free bytes of MAP_STRIDE, and growing the record\n"
        "; for that would have been expensive for nothing. That no other map\n"
        "; shows it is enforced by the converter, which stops.\n"
        "PICTURE_BASE = %d\n"
        "PICTURE_PAL = %d\n"
        "PICTURE_X   = %d\n"
        "PICTURE_Y   = %d\n"
        "PICTURE_OBJECTS = %d\n"
        "; How many tiles of the name grid have to be skipped to go from one\n"
        "; object to the next, and from a row of four to the following one.\n"
        "PICTURE_OBJ_STRIDE = %d\n"
        "PICTURE_ROW_STRIDE = %d\n"
        "; The rain: see OP_WEATHER in events.py.\n"
        "RAIN_DROPS_MAX = %d\n"
        "RAIN_DROPS_0 = %d\n"
        "RAIN_DROPS_1 = %d\n"
        "RAIN_DROPS_2 = %d\n"
        "RAIN_LIFE     = %d\n"
        "RAIN_BORN     = %d\n"
        "RAIN_SEED = $%04X\n"
        "WEATHER_RAIN  = %d\n"
        "; The inventory: one byte per item of the LDB and RM2k's cap. See\n"
        "; OP_ITEM in events.py.\n"
        "ITEMS_N       = %d\n"
        "ITEM_MAX      = %d\n"
        "; The variables: how many slots this ROM carries —at least one,\n"
        "; because a zero length would close the save table—, the ControlVars\n"
        "; operand classes the ROM distinguishes, the sum, and the random\n"
        "; seed. See 'RM2k's variables' in events.py.\n"
        "VARIABLES_N   = %d\n"
        "VAR_ADD       = %d\n"
        "VAR_VARIABLE  = %d\n"
        "VAR_RANDOM    = %d\n"
        "VAR_OTHER     = %d\n"
        "; Class 6, a character's coordinates: the target goes like that of\n"
        "; OP_ROUTE —0 the hero, the event's index plus one— and the other\n"
        "; operand says which coordinate. See VAR_CHARACTER in events.py.\n"
        "VAR_CHARACTER = %d\n"
        "CHARACTER_X   = %d\n"
        "CHARACTER_Y   = %d\n"
        "; The high bits of each OP_CELL_TEST write. See CELL_Y in\n"
        "; events.py.\n"
        "CELL_Y        = $%04X\n"
        "CELL_REFRESH = $%04X\n"
        "RANDOM_SEED   = $%04X\n"
        "; And the one for the encounters' randomness, which is a different\n"
        "; one on purpose: walking doesn't advance the map's randomness. See\n"
        "; ENC_SEED in events.py.\n"
        "ENC_SEED      = $%04X\n"
        "TIMER_SET_VAR = %d\n"
        "; The ConditionalBranch condition classes we know, with the RM2k\n"
        "; number as is.\n"
        "COND_GOLD   = %d\n"
        "COND_ITEM   = %d\n"
        "COND_ACTOR  = %d\n"
        "; And the two actor questions that carry two operands, with their\n"
        "; own opcode: see OP_IF_ACTOR in events.py.\n"
        "COND_ACTOR_SKILL = %d\n"
        "COND_ACTOR_EQUIPMENT = %d\n"
        "GOLD_MAX    = %d\n"
        "; The two PanScreen operations that compile.\n"
        "PAN_RUN     = %d\n"
        "PAN_RETURN  = %d\n"
        "; The three timer operations.\n"
        "TIMER_SET      = %d\n"
        "TIMER_START = %d\n"
        "; And its five glyphs on screen: where the first goes and how wide\n"
        "; each one is. The colon's is number 10.\n"
        "TIMER_X        = %d\n"
        "TIMER_Y        = %d\n"
        "TIMER_GLYPH_W  = %d\n"
        "TIMER_TWO_POINTS = %d\n"
        "; How many frames fit in a second, and the extra ones `SetTimer`\n"
        "; adds so that the first second shows whole.\n"
        "TIMER_FRAMES   = %d\n"
        "MORE_TIMER     = %d\n"
        "; How many flashes can be running at once.\n"
        "FLASH_MAX   = %d\n"
        "; How many events with a parallel page there can be in a map.\n"
        "PARALLEL_MAX = %d\n"
        "TRIGGER_AUTO = %d\n"
        "TRIGGER_ACTION     = %d\n"
        "TRIGGER_TOUCHES_HERO = %d\n"
        "TRIGGER_PARALLEL   = %d\n"
        "; How many frames a one-cell step lasts. It comes from events.py and\n"
        "; not from a computation in the ROM.\n"
        "FRAMES_PER_CELL = %d\n"
        "; A route's highest frequency, which is where commands 30 and 31\n"
        "; cap. The lowest is capped by the ROM at 1, like RM2k; what\n"
        "; guarantees it isn't reached is the converter, which rejects the\n"
        "; route.\n"
        "ROUTE_FREQUENCY = %d\n"
        "; And how much a `wait` inside a forced route costs. **It isn't one\n"
        "; frame**: in RM2k it is `SetMaxStopCountForWait`, that is\n"
        "; `20 + (1 << (8 - frecuencia))`, and with frequency 8 —the only\n"
        "; one the converter lets through— it is twenty.\n"
        "ROUTE_WAIT = %d\n"
        "; And the jump: how much is left when it starts. How much it drops\n"
        "; per frame depends on the speed —`jump_per_speed`— and not on the\n"
        "; distance.\n"
        "JUMP_STEP = %d\n"
        "TINT_NEUTRAL = %d\n"
        "; The teleport fade: 35 frames out and 35 back, like RM2k, and of\n"
        "; each 35 the ramp is 24. The map is loaded on the first black\n"
        "; frame, which is number %d. These numbers and the table below come\n"
        "; from the fade constants of tools/port/events.py.\n"
        "FADE_FRAMES = %d\n"
        "FADE_TOTAL      = %d\n"
        "FADE_RAMP       = %d\n"
        "FADE_BLACK      = %d\n"
        "FADE_LOAD       = %d\n"
        "BRIGHTNESS_MAX  = %d\n"
        "; The teleport transitions the ROM does with the mosaic and with\n"
        "; the cut; any other is the fade. See `ChangeScreenTransitions` in\n"
        "; tools/port/events.py.\n"
        "TRANSITION_MOSAIC = %d\n"
        "TRANSITION_CUTOFF  = %d\n"
        "; The Y'CbCr luminance weights, which are the ones RM2k saturates\n"
        "; with. They add up to exactly 65536, so over five-bit channels they\n"
        "; give a five-bit luminance without rescaling anything.\n"
        "LIGHT_R = %d\n"
        "LIGHT_G = %d\n"
        "LIGHT_B = %d\n"
        "; One bit per switch. The highest the game checks is 1003.\n"
        "SWITCH_BYTES = %d\n"
        "; The party the game starts with, and its cap. In RM2k the hero's\n"
        "; graphic is the first one's, so this decides which sprite is\n"
        "; drawn; `ChangePartyMembers` moves it on the fly.\n"
        "PARTY_MAX      = %d\n"
        "PARTY_INITIAL_N = %d\n"
        "ACTOR_BYTES    = %d\n"
        "; How many bytes of that entry are the actor's fifteen colors: the\n"
        "; ROM uploads them to the slot the leaders share. See\n"
        "; `pick_hero_graphic`.\n"
        "ACTOR_COLORS   = %d\n"
        "OBJ_COLORS     = %d\n"
        "; The hero's layer, to sort it against the NPCs.\n"
        "HERO_LAYER  = %d\n"
        "; Its object priority. $10 —below the upper layer— in every ROM\n"
        "; other than `encima`'s, which raises it to $20 to exercise priority\n"
        "; 2. No event of the game gets to exercise it: see `test_encima` in\n"
        "; test_caminar_golden.py.\n"
        "HERO_PRIORITY = $%02X\n"
        "; The message window: its tiles live in the second half of the BG2\n"
        "; bank, that is from index 256, and its cells already come built\n"
        "; with that shift and with the upper layer's priority.\n"
"; And where the background starts in CGRAM: below it live the\n"
        "; screen's backdrop color and the message window's palette, which\n"
        "; belong to the whole ROM. The background goes at 8 bits and\n"
        "; addresses CGRAM directly, so it is enough for it to start shifted.\n"
        "CGRAM_BASE     = %d\n"
"WINDOW_CGADD   = %d\n"
        "WINDOW_TILES   = %d\n"
        "WINDOW_ROWS_ = %d\n"
        "TEXT_WINDOW_COLS = %d\n"
        "; The text area: where it starts in the window's tile bank and\n"
        "; which cells it takes. Its tiles aren't deduplicated —the ROM\n"
        "; rewrites them— and that is where the cap of characters per line\n"
        "; comes from.\n"
        "WINDOW_TEXT_BASE = %d\n"
        "WINDOW_TEXT_ROW = %d\n"
        "WINDOW_TEXT_ROWS = %d\n"
        "WINDOW_TEXT_COL    = %d\n"
        "WINDOW_TEXT_COLS = %d\n"
        "MESSAGE_COLS   = %d\n"
        "; The font: 95 ASCII glyphs of six bits by twelve rows, and the\n"
        "; shadow's palette index. That of each row of the glyph is in\n"
        "; font_color.\n"
        "FONT_HEIGHT    = %d\n"
        "FONT_WIDTH     = %d\n"
        "FONT_SHADOW    = %d\n"
        "FONT_PRE_ROWS = %d\n"
        "FONT_PRE_CHAR    = %d\n"
        "; The ChipSet animation. Each map has an entry in `anim_table` with\n"
        "; its two runs and a block with the drawings; see `anim_table` in\n"
        "; snes_convert.py. The cadences and the water cycle come from\n"
        "; `rm2k.py`.\n"
        "ANIM_FAMILIES  = %d\n"
        "ANIM_STRIDE    = %d\n"
        "ANIM_FAM_STRIDE = %d\n"
        "WATER_FRAMES   = %d\n"
        "WATER_DRAWINGS = %d\n"
        "WATER_CYCLE_N  = %d\n"
        "ANIMATED_FRAMES = %d\n"
        "ANIMATED_STEPS = %d\n"
        "BYTES_PER_TILE = %d\n"
        "; The title screen. TITLE_TILES at 0 means this ROM doesn't carry\n"
        "; it and the blocks below are one byte of padding; the code in\n"
        # `rom/src/` on purpose: it goes into the `.inc`, which isn't touched
        # yet.
        "; rom/src/ turns itself off with that. It lives alone in VRAM —it\n"
        "; shares with no map, because while it is shown there is no map\n"
        "; loaded— so its addresses are fixed and don't come from the\n"
        "; `vram_layout` layout. The image is uploaded by `screen_upload`,\n"
        "; from its row in `screens_table`: the tiles from $0000 and the\n"
        "; tilemap at SCREEN_MAP.\n"
        "TITLE_TILES    = %d\n"
        "; The menu, on BG2 at four bits per pixel: its tile bank, how many\n"
        "; options it has and which is selected on entering. The cursor isn't\n"
        "; drawn separately: there is one tilemap per option and moving it is\n"
        "; uploading the other.\n"
        ";\n"
        "; The VRAM layout on this screen, in words, and why each one is\n"
        "; where it is: the image tiles start at 0 and take 15872, so\n"
        "; everything else goes **above** that. A BG's tile base goes in\n"
        "; steps of 4096 words, which is what fixes $5000 for the menu; the\n"
        "; tilemaps go in steps of 1024 and fit in the gap next to it.\n"
        ";\n"
        ";   $0000 .. $3E00   the image's 496 tiles, at 8bpp\n"
        ";   $4400 .. $4800   the menu's tilemap\n"
        ";   $5000 ..         the menu's tiles, at 4bpp\n"
        ";   $7C00 .. $8000   the image's, SCREEN_MAP of game_over.s\n"
        "TITLE_MENU_CGRAM = %d\n"
        "TITLE_MENU_TILES = %d\n"
        "TITLE_MENU_VRAM   = $5000\n"
        "TITLE_MENU_MAP    = $4400\n"
        "TITLE_MENU_N      = %d\n"
        "; The slots screen, which both ends use: 'Resume the Story' and the\n"
        "; save point. It is a screen of its own —not a layer over the\n"
        "; title— so it is uploaded whole on entering. **It goes in every\n"
        "; ROM**, with a title or without: the save point opens it from\n"
        "; inside the game, and that is why its VRAM addresses are its own\n"
        "; and not the menu's: they fall in the BG1 tile bank of every\n"
        "; layout, which is what `back_to_map` restores with `load_map`.\n"
        "; See SLOT_MAP in the converter.\n"
        "SLOT_VRAM         = $%04X\n"
        "SLOT_MAP          = $%04X\n"
        ";\n"
        "; The cell blocks: the header has two variants —load and save— and\n"
        "; each slot four —empty or full, with cursor or without—. Moving the\n"
        "; cursor is rewriting two rows and not a whole tilemap.\n"
        "SRAM_SLOTS_N      = %d\n"
        "SLOT_TILES        = %d\n"
        "SLOT_HDR_ROW      = %d\n"
        "SLOT_HDR_ROWS     = %d\n"
        "SLOT_HDR_CELLS = %d\n"
        "SLOT_ROW0         = %d\n"
        "SLOT_JUMP         = %d\n"
        "SLOT_ROWS         = %d\n"
        "SLOT_CELLS        = %d\n"
        "; And where each row goes in the tilemap, in words. It also comes\n"
        "; from a table: the computation is SLOT_ROW0 + n * SLOT_JUMP,\n"
        "; times 32, and writing it in the 65816 would be the fourth place to\n"
        "; get it wrong.\n"
        "SLOT_HDR_VRAM     = %d\n"
        "; How many blocks there are before the first of the rows: they are\n"
        "; the two headers, load and save.\n"
        "SLOT_BLOCK_ROWS = 2\n"
        "; The saved game's party, above the row: the faces of up to\n"
        "; SLOT_FACES_MAX, of SLOT_FACE_COLS by SLOT_FACE_ROWS cells,\n"
        "; and the first one's name and level. Which face block each actor\n"
        "; gets is said by `slot_face_block`, by actor id up to\n"
        "; SLOT_ACTORS_N, with $FF for 'has none'; and where they go,\n"
        "; `slot_face_vram` —four per slot— and `slot_name_vram`.\n"
        ";\n"
        "; The name and the level aren't blocks: they are composed one letter\n"
        "; per cell with `slot_glyph_cells`, and each actor's text comes\n"
        "; from its row of `slot_actor_text` —the name, the two digits of\n"
        "; the level and max HP, one after the other—. See 'lo que depende\n"
        "; del actor' in menus.py: it is what keeps the tile bank from\n"
        "; growing with the number of actors.\n"
        "SLOT_FACES_MAX    = %d\n"
        "SLOT_FACE_COLS    = %d\n"
        "SLOT_FACE_ROWS = %d\n"
        "SLOT_NAME_COLS      = %d\n"
        "; How long an actor's row is in `slot_actor_text` and where each\n"
        "; strip starts inside it. The width is a power of two even if bytes\n"
        "; are left over: that way the index comes from shifts and not from a\n"
        "; multiplication.\n"
        "SLOT_TEXT_WIDTH     = %d\n"
        "SLOT_TEXT_NAME = 0\n"
        "SLOT_TEXT_LEVEL     = %d\n"
        "SLOT_TEXT_MAX       = %d\n"
        "SLOT_LEVEL_DIGITS = %d\n"
        "; How many cells from the name the first digit of the level falls.\n"
        "SLOT_LEVEL_OFS      = %d\n"
        "; And where digit 0 starts inside `slot_glyph_cells`, which is\n"
        "; indexed by character: it is where the gold and the HP get their\n"
        "; digits from.\n"
        "GLYPH_DIGIT_0     = %d\n"
        "SLOT_ACTORS_N     = %d\n"
        "; How many CGRAM entries the slots screen uploads: palette 0 for\n"
        "; the text and one per face, of sixteen each.\n"
        "SLOT_CGRAM_N      = %d\n"
        "; How many CGRAM entries the title menu uses: one palette of\n"
        "; sixteen, number 0. It is already defined above, with the title\n"
        "; screen; this confirms both computations give the same.\n"
        ".assert TITLE_MENU_CGRAM = %d, error, \"two computations of the menu's CGRAM\"\n\n"
        % (", ".join("%d %s" % (m["id"], m["nombre"]) for m in maps),
           len(maps), MAP_STRIDE, initial,
           VRAM_ABOVE_MAP, MAP_LAYOUT, NPC_STRIDE, NPC_MAX,
           NPC_STILL,
           EV_STRIDE, EV_MAX, ROUTE_EV_MAX,
           PAGE_BYTES, TURN_NONE, ROUTE_GFX_MAX,
           events.HEADER_LINES, events.HEADER_AUTO_CLOSE,
           events.PAUSE_FRAMES, events.VAR_REFRESH, events.VAR_SLOT_MAX,
           events.ANIM_ENTRY_BYTES, events.ANIM_SOUND, events.ANIM_SCREEN_FLASH, events.KEY_WAIT,
           events.KEY_DIRS, events.KEY_DECISION,
           events.KEY_CANCEL, events.KEY_START,
           events.KEY_VALUE_DECISION, events.KEY_VALUE_CANCEL,
           events.KEY_VALUE_DIR[0], events.KEY_VALUE_DIR[1],
           events.KEY_VALUE_DIR[3], events.KEY_VALUE_DIR[2],
           picture_base, picture_pal,
           picture_info["x"] if picture_info else 0, picture_info["y"] if picture_info else 0,
           picture_info["objetos"] if picture_info else 0,
           picture.OBJ_SIDE, 4 * picture.GRID,
           max(events.RAIN_DROPS),
           events.RAIN_DROPS[0], events.RAIN_DROPS[1],
           events.RAIN_DROPS[2], events.RAIN_LIFE,
           events.RAIN_SPAWN, events.RAIN_SEED,
           events.WEATHER_RAIN,
           events.ITEMS_N,
           events.ITEM_MAX,
           variables_n(),
           events.VAR_ADD, events.VAR_VARIABLE, events.VAR_RANDOM,
           events.VAR_OTHER,
           events.VAR_CHARACTER, events.CHARACTER_X, events.CHARACTER_Y,
           events.CELL_Y, events.CELL_REFRESH,
           events.RANDOM_SEED, events.ENC_SEED,
           events.TIMER_SET_VAR,
           events.COND_GOLD, events.COND_ITEM,
           events.COND_ACTOR, events.COND_ACTOR_SKILL,
           events.COND_ACTOR_EQUIPMENT,
           events.GOLD_MAX,
           events.PAN_SHIFT, events.PAN_RETURN,
           events.TIMER_SET, events.TIMER_START,
           TIMER_X, TIMER_Y, TIMER_GLYPH_W, TIMER_GLYPHS - 1,
           events.FRAMES_PER_SECOND, events.TIMER_EXTRA_FRAMES,
           FLASH_MAX, PARALLEL_MAX,
           events.TRIGGER_AUTOSTART, events.TRIGGER_ACTION,
           events.TRIGGER_TOUCH_HERO, events.TRIGGER_PARALLEL,
           events.FRAMES_PER_CELL, events.ROUTE_FREQUENCY,
           events.ROUTE_WAIT_FRAMES,
           events.JUMP_STEP,
           color_mod.NEUTRAL_TINT,
           events.FADE_RAMP,
           events.FADE_FRAMES, events.FADE_TOTAL,
           events.FADE_RAMP, events.FADE_BLACK,
           events.FADE_RAMP, events.BRIGHTNESS_MAX,
           events.TRANSITION_MOSAIC, events.TRANSITION_CUT,
           color_mod.LUMA_R, color_mod.LUMA_G, color_mod.LUMA_B, SWITCH_BYTES,
           events.PARTY_MAX, len(initial_party), ACTOR_BYTES,
           ACTOR_COLORS, OBJ_COLORS,
           rm2k.LAYER_SAME,
           OBJ_PRIORITY_ABOVE if hero_above else OBJ_PRIORITY,
           CGRAM_RESERVED,
           window_palette() * COLORS_PER_PALETTE,
           len(window["tiles"]) // 32,
           WINDOW_ROWS_INC, WINDOW_COLS_INC,
           window["base"],
           WINDOW_TEXT_ROW, WINDOW_TEXT_ROWS,
           WINDOW_TEXT_COL, WINDOW_TEXT_COLS, _columns(),
           FONT_HEIGHT, FONT_WIDTH,
           window["sombra"],
           FONT_PRE_ROWS, FONT_PRE_CHAR,
           len(FAMILIES), ANIM_STRIDE, ANIM_FAM_STRIDE,
           rm2k.WATER_FRAMES_SLOW,
           FAMILIES[0][1],
           len(rm2k.WATER_CYCLE), rm2k.ANIMATED_FRAMES, rm2k.ANIMATED_STEPS,
           BYTES_PER_TILE,
           0 if title is None else title["pantalla"]["tiles"],
           constants.MENU_CGRAM,
           0 if title is None else len(title["menu_tiles"]),
           0 if title is None else len(title["menu_tilemaps"]),
           SLOT_VRAM, SLOT_MAP,
           len(slots["filas"]),
           len(slots["tiles"]),
           menus_mod.HEADER_Y // constants.CELL,
           menus_mod.HEADER_ROWS,
           menus_mod.HEADER_ROWS * constants.COLS,
           menus_mod.SLOT_Y // constants.CELL,
           menus_mod.SLOT_STEP // constants.CELL,
           menus_mod.SLOT_ROWS,
           menus_mod.SLOT_ROWS * constants.COLS,
           menus_mod.HEADER_Y // constants.CELL * 32,
           menus_mod.FACES_MAX, menus_mod.FACE_CELLS,
           menus_mod.FACE_CELLS, menus_mod.NAME_COLS,
           SLOT_TEXT_WIDTH, SLOT_TEXT_LEVEL, SLOT_TEXT_MAX,
           menus_mod.LEVEL_DIGITS,
           ((menus_mod.LEVEL_ROW - menus_mod.NAME_ROW) * 32
            + menus_mod.LEVEL_COL - menus_mod.NAME_COL),
           (ord("0") - menus_mod.ITEM_FIRST_CHAR) * 4,
           (max(list(slots["caras"]) + list(slots["actores"]) + [-1])
            + 1),
           len(slots["paletas"]) * constants.MENU_CGRAM,
           constants.MENU_CGRAM))

    with open(path, "w") as handle:
        handle.write(header)
        handle.write(rom_identity())
        handle.write(offsets())
        handle.write("\n\n")
        # The fade ramp, in bank 0 because `fade_tick` reads it with
        # `lda fade_ramp, x`. It comes from `events.fade_ramp()`:
        # writing it in tools/runtime/ too would be having two copies that can
        # get out of sync without anything noticing.
        handle.write('.segment "TABLES"\n'
                     '; The master brightness on each frame of the ramp, from\n'
                     '; black to full. Going down it is read backwards.\n'
                     'fade_ramp:\n        .byte %s\n\n'
                     % ",".join(str(v) for v in events.fade_ramp()))
        # The data goes in RODATA, which the linker spreads over the upper
        # banks. What stays in TABLES —that is, in bank 0— is what the ROM
        # walks with a bare `lda tabla, x`, which addresses the data bank.
        # `map_table` is no longer among those: see `map_table`.
        handle.write('.segment "RODATA"\n')
        # The twelve poses of each character that changes pose, **once per
        # quantization** and not once per ROM: two maps that draw the same
        # character with the same palette share the bank, and if one quantized
        # it differently —because it lent it someone else's palette, as map 8
        # does to Chara2:0, or took a color off— it carries its own. Until
        # 2026-09-10 this was a `sys.exit`, and the palette split had a rule to
        # dodge it that the lending didn't look at: adding Lashe City 33,36 to
        # the demo stopped there. One extra bank is 6 KB of cartridge; a stop
        # is a map that doesn't fit.
        global_index, banks, index_per_map = {}, [], []
        for map_info in maps:
            own = {}
            for pair, data in (map_info["sprite"][8].items()
                               if map_info["sprite"] else ()):
                key = (pair, data)
                if key not in global_index:
                    if any(k[0] == pair for k in global_index):
                        print("  map %d: %s:%d goes with a pose bank of its "
                              "own, quantized differently than in another map"
                              % (map_info["id"], pair[0], pair[1]))
                    global_index[key] = len(banks)
                    banks.append(data)
                own[pair] = global_index[key]
            index_per_map.append(own)
        handle.write("; --- the poses of the characters that change pose, "
                     "for the whole ROM ---\n")
        # **Each pose once**, even if several characters or the same one
        # repeat it: the pose tables carry one pointer per pose —`npc_poses`,
        # `actor_table`—, so two equal ones point to the same block and the
        # ROM uploads the same bytes from another place. It happens a lot: the
        # equal walking frames of the same CharSet, and the characters that
        # repeat across maps with another quantization that didn't change a
        # pose. Each one with its `.block`, because it is uploaded by DMA.
        pose_label, bank_poses = {}, []
        for data in banks:
            theirs = []
            for pose in range(SPRITE_POSES):
                bytes_ = data[pose * POSE_BYTES:(pose + 1) * POSE_BYTES]
                if bytes_ not in pose_label:
                    pose_label[bytes_] = "pose_%d" % len(pose_label)
                    handle.write(block(pose_label[bytes_], bytes_) + "\n")
                theirs.append(pose_label[bytes_])
            bank_poses.append(theirs)
        handle.write("\n")
        print("  poses: %d distinct out of %d, %.1f KB less"
              % (len(pose_label), SPRITE_POSES * len(banks),
                 (SPRITE_POSES * len(banks) - len(pose_label))
                 * POSE_BYTES / 1024.0))
        index_per_map = [{pair: bank_poses[g] for pair, g in own.items()}
                         for own in index_per_map]
        write_raw(os.path.dirname(os.path.abspath(path)), maps)
        materials = Materials(dedupe=True,
                              compressed=compressed
                              or compress_blocks(maps))
        handle.write("; The LZ2 caps, which decompress.s enforces\n"
                     "LZ2_CAP_BACKDROP = $%04X\n"
                     "LZ2_CAP_ABOVE_Y_SPRITES = $%04X\n"
                     "LZ2_CAP_ANIM = $%04X\n"
                     "LZ2_CAP_GRID = $%05X\n\n"
                     % (LZ2_CAP_BACKDROP, LZ2_CAP_ABOVE_AND_SPRITES,
                        LZ2_CAP_ANIM, LZ2_CAP_GRID))
        labels = []
        for number, map_info in enumerate(maps):
            # `mapas_de` in rom/pruebas/arnes/consola.py reads the table
            # order from this line with a regex that expects "map".
            handle.write("; --- %d: map %d %r ---\n"
                         % (number, map_info["id"], map_info["nombre"]))
            text, theirs = map_data(map_info, number,
                                    index_per_map[number], materials)
            labels.append(theirs)
            handle.write(text)
            handle.write("\n")
        if True:
            # The message window is a single one for the whole ROM —the same
            # skin, the same size— so it goes as a global block and not in the
            # map table. The only thing that depends on the map is which
            # palette it goes in, and that is resolved above, when choosing the
            # CGRAM split.
            #
            # BG2 goes at 4 bits, so its cell **does** use the three palette
            # bits —unlike the background, which goes at 8 and ignores them—.
            # The window goes in 0 and is the same for every map: its cells
            # are emitted only once. That the background doesn't step on it
            # comes from the split —it starts at `CGRAM_RESERVED`— but it is
            # checked anyway: if it stepped on it, the window would come out
            # with the map's colors and no single-map comparison would see it.
            palette = window_palette()
            for m in maps:
                if len(m["cram_words"]) + CGRAM_RESERVED > \
                        m["above"][3] * COLORS_PER_PALETTE:
                    raise SystemExit(
                        "the background of map %d uses %d CGRAM entries from "
                        "%d and steps on the upper layer, which starts at %d"
                        % (m["id"], len(m["cram_words"]), CGRAM_RESERVED,
                           m["above"][3] * COLORS_PER_PALETTE))
            handle.write("\n; --- the message window ---\n")
            handle.write(block("window_tiles", window["tiles"]) + "\n")
            # Only the `CGRAM_RESERVED` at the bottom: from 8 up it belongs
            # to the background, and uploading all sixteen would erase it.
            handle.write(block("window_cgram",
                               b"".join(w.to_bytes(2, "little")
                                        for w in window["cram"]
                                        [:CGRAM_RESERVED])) + "\n")
            # One layout for each window base the VRAM layouts use: the tile
            # index goes shifted behind the upper layer, and the upper layer
            # measures 128 or 256 depending on the layout. See
            # `WINDOW_BASES` and `stamp_window`.
            for base, label in zip(WINDOW_BASES, ("window_cells",
                                                  "window_cells_256")):
                plane = bytearray()
                for row in window["celdas"]:
                    for cell in row:
                        # With the upper layer's priority so that it covers
                        # the hero and the NPCs.
                        plane += (entry(base + cell, False, False,
                                        PRIORITY_ABOVE)
                                  | (palette << 10)).to_bytes(2, "little")
                handle.write(block(label, bytes(plane)) + "\n")
            # The text area without text: the 240 tiles the ROM copies to the
            # buffer before drawing on top. They go in the order the ROM needs
            # them, that is the cells' order.
            handle.write(block("window_backdrop", window["fondo"]) + "\n")
            # The font and the colors. `font_color` is the palette index of
            # each of the glyph's twelve rows: RM2k's gradient comes from a
            # 16x16 mask, but each row is a single color, so twelve bytes are
            # enough and the ROM doesn't have to sample anything.
            handle.write(block("font_table", window["fuente"]) + "\n")
            pre = font_prerender(window["fuente"], window["color"],
                                 window["sombra"])
            for phase, data in enumerate(pre):
                handle.write(block("font_pre%d" % phase, data) + "\n")
            handle.write(block("messages", window["mensajes"]) + "\n")
            # How big it is and how big it can be: the ROM doesn't use them,
            # `just espacio` reads them from the symbol table. The cap is what
            # the operand of `OP_MESSAGE` reaches, 16 bits and in steps of
            # `MENSAJES_PASO` bytes.
            handle.write("MESSAGES_BYTES = %d\nMESSAGES_CAP = %d\n"
                         % (len(window["mensajes"]),
                            0x10000 * events.MESSAGES_STEP))
        # --- the ShowPicture picture ---
        #
        # Its fifteen colors as they came out of `picture.convert`, in the
        # order the tiles index them. They go in a global block and not in the
        # map table because the picture is a single one per ROM; what does belong
        # to the map is which tile and which palette it ended up in, which
        # goes in the record.
        #
        # Entry 0 goes too, in black, and not because it is drawn —a sprite's
        # index 0 is transparent— but so that the ROM uploads all sixteen at
        # once: the DMA starts at the palette's entry, not one further on, and
        # subtracting one here is exactly the kind of computation that is
        # written right on one side and wrong on the other.
        handle.write("\n; --- the ShowPicture picture ---\n")
        colors = ([(0, 0, 0)] + list(picture_info["paleta"])) if picture_info else [(0, 0, 0)]
        handle.write(block("picture_cgram",
                           b"".join(cgram_word(c).to_bytes(2, "little")
                                    for c in colors)) + "\n")
        # The screen flash products: `d * nivel // 31` for d and level from 0
        # to 31, in the level's row. It is `destellar_canal`'s computation, and
        # the ROM read it from the multiplier and the divider for each of the
        # 96 entries of its tables on every odd frame: see
        # `one_flash_table`.
        handle.write(block("prod31_table", bytes(
            d * n // 31 for n in range(32) for d in range(32))) + "\n")
        handle.write(animations_asm(animations or {}, maps))
        # --- the title screen ---
        #
        # It goes entirely on BG1, which in mode 3 has eight bits per pixel:
        # the image addresses CGRAM directly and doesn't have to be split into
        # palettes of sixteen, which is what a map does have to do because the
        # sprites need theirs. There are no sprites here.
        #
        # The tiles are deduplicated like the map's. The image has a lot of
        # black —the bottom half, which is where the menu goes— so of the 1024
        # cells fewer than 500 are left.
        #
        # The image goes compressed, together with the menu's colors, in its
        # row of `screens_table`: see "the full screens", below. What stays
        # here is the menu, which isn't part of the image.
        handle.write("\n; --- the title screen ---\n")
        if title is None:
            handle.write(block("title_menu_tiles", b"\x00") + "\n")
            handle.write(block("title_menu_cells", b"\x00") + "\n")
        else:
            # The menu: a 4-bit tile bank and one tilemap per selected option.
            # Moving the cursor is uploading the other tilemap, and that is why
            # they go one after the other and the same size: the ROM indexes
            # them by multiplying.
            menu = bytearray()
            for cell in title["menu_tiles"]:
                menu += pack_tile(cell, planes=4)
            handle.write(block("title_menu_tiles", bytes(menu)) + "\n")
            plane = bytearray()
            for menu_map in title["menu_tilemaps"]:
                for index in menu_map:
                    plane += entry(index, False, False,
                                   PRIORITY_ABOVE).to_bytes(2, "little")
            handle.write(block("title_menu_cells", bytes(plane)) + "\n")

        # --- the full screens: Game Over and the title ---
        #
        # Each one is an LZ2 stream with the tiles, the tilemap and the
        # colors, and its row in `screens_table`, which is what
        # `screen_upload` reads: see tools/port/fullscreen.py. Without
        # a Game Over image, GAME_OVER_TILES at 0 and the ROM goes back to the
        # title without a screen, as until 2026-09-28; without a title screen,
        # TITLE_TILES at 0 and no row. Without either of them SCREEN_ROW
        # isn't defined, and `screen_upload` isn't assembled.
        handle.write("\n; --- the full screens ---\n")
        handle.write("GAME_OVER_TILES = %d\n"
                     % (0 if game_over is None else game_over["tiles"]))
        rows = []
        if game_over is not None:
            rows.append(("GAME_OVER", "game_over_lz2", game_over))
        if title is not None:
            rows.append(("TITLE", "title_lz2", title["pantalla"]))
        if not rows:
            handle.write(block("screens_table", b"\x00") + "\n")
        else:
            handle.write(
                "; Each screen's row in `screens_table`: where its stream is,\n"
                "; how many bytes of tiles and colors it brings, and from which\n"
                "; CGRAM color they go. See `screen_upload`.\n"
                "SCREEN_ROW = 8\n")
            for number, (name, _, _) in enumerate(rows):
                handle.write("SCREEN_%s = %d\n" % (name, number))
            handle.write(".block %d\nscreens_table:\n" % (8 * len(rows)))
            for _, label, data in rows:
                handle.write("    .word .loword(%s)\n"
                             "    .byte ^%s\n"
                             "    .word %d, %d\n"
                             "    .byte %d\n"
                             % (label, label, data["tiles"] * 64,
                                data["colores"] * 2, data["primer_color"]))
            handle.write("\n")
            for _, label, data in rows:
                handle.write(block(label, data["flujo"]) + "\n")

        # The slots screen, which **goes in every ROM** and not only in the
        # ones that carry a title: the save point opens it from inside the
        # game. Until 2026-09-10 it came out only with the title screen and
        # without it a byte of padding was left with `SLOT_TILES` at zero;
        # and a DMA of "zero bytes" is 65536, so opening it from a ROM without
        # a title filled VRAM with garbage. It is the "black screen with
        # garbage on top" that for a while was noted down as a mystery of the
        # interpreter's context.
        #
        # Its tile bank is its own: it shares the VRAM address with the title
        # menu's, but not the tiles, because both screens are uploaded whole
        # every time one is entered.
        handle.write("\n; --- the slots screen ---\n")
        data = bytearray()
        for cell in slots["tiles"]:
            data += pack_tile(cell, planes=4)
        handle.write(block("slot_tiles", bytes(data)) + "\n")

        # The bank of the slots and the menu goes **with the priority bit
        # set**, like the item glyphs: the actor choice turns on BG1 with its
        # windows, and in mode 3 BG1 at priority 0 stays above BG2 at priority
        # 0 —the red bar would cover the row—. In the other screens of this
        # bank BG1 is off and the bit doesn't change a pixel; the experience
        # sprites discard it.
        def cells_asm(blocks):
            plane = bytearray()
            for cells in blocks:
                for index in cells:
                    plane += entry(index, False, False,
                                   priority=1).to_bytes(2, "little")
            return bytes(plane)

        # Each cell block goes with its own label and is named by a pointer
        # table, just like the music songs. It is more ROM than computing the
        # offset with shifts —three one-byte tables per block— and in exchange
        # the ROM doesn't have to multiply by 96 or by 192 anywhere. That
        # multiplication would be written here and there, which is exactly
        # the shape of error this repo has already paid for three times.
        #
        # The order: first the two headers —load and save— and then, per slot,
        # the four variants as full * 2 + cursor.
        slot_blocks = []
        for mode, cells in enumerate(slots["cabeceras"]):
            name = "slot_hdr_%d" % mode
            handle.write(block(name, cells_asm([cells])) + "\n")
            slot_blocks.append(name)
        for number, row in enumerate(slots["filas"]):
            for full in (0, 1):
                for cursor in (0, 1):
                    name = "slot_%d_%d%d" % (number, full, cursor)
                    handle.write(
                        block(name, cells_asm([row[full][cursor]]))
                        + "\n")
                    slot_blocks.append(name)
        # And behind, per actor that can join the party, its face: the ROM
        # writes it over the row according to what the save stored. The face
        # cells carry the palette in their three bits, which are used here: it
        # is BG2 at 4bpp.
        #
        # Its name and its level are **not** blocks: the ROM composes them with
        # glyphs, see "what depends on the actor" in menus.py. That is what
        # keeps the bank from growing with the number of actors.
        face_block = {}
        for actor in sorted(slots["caras"]):
            name = "slot_face_%d" % actor
            handle.write(block(name, cells_asm([slots["caras"][actor]]))
                         + "\n")
            face_block[actor] = len(slot_blocks)
            slot_blocks.append(name)
        # And the pause menu's, which live in the same tile bank: each command
        # in its two variants —1 is disabled, in the gray palette—, the coin,
        # and the text of a party row, which is a single one for the four and
        # for every actor. The cursor and the glyphs don't go as blocks: they
        # are two cells each and the ROM writes them word by word, see
        # `slot_glyph_cells`.
        menu = slots["menu"]
        menu_option_block = len(slot_blocks)
        for order, variants in enumerate(menu["opciones"]):
            for disabled, cells in enumerate(variants):
                name = "menu_option_%d_%d" % (order, disabled)
                handle.write(block(name, cells_asm([cells])) + "\n")
                slot_blocks.append(name)
        menu_currency_block = len(slot_blocks)
        handle.write(block("menu_currency", cells_asm([menu["moneda"]]))
                     + "\n")
        slot_blocks.append("menu_currency")
        menu_row_block = len(slot_blocks)
        handle.write(block("menu_row", cells_asm([menu["fila"]])) + "\n")
        slot_blocks.append("menu_row")
        # And the item screen, which has a bank of its own: the font one
        # letter per cell, its two palettes, and the text of each item the ROM
        # knows —name and two lines of description—, in ASCII.
        data = bytearray()
        for cell in slots["items_tiles"]:
            data += pack_tile(cell, planes=4)
        handle.write(block("items_tiles", bytes(data)) + "\n")
        def palettes_cgram(palettes):
            return b"".join(
                cgram_word(c).to_bytes(2, "little") for palette in palettes
                for c in list(palette) + [(0, 0, 0)] * (constants.MENU_CGRAM
                                                        - len(palette)))

        # The first two, which are uploaded with the bank on every screen that
        # uses it; the "goes up" one and the red one go separately and only
        # the equipment screen uploads them, because in battle the entries
        # from the third palette on are the backdrop's —`scene.CGRAM_BASE`—
        # and uploading them there wouldn't help anyone.
        handle.write(block("items_cgram", palettes_cgram(
            slots["items_paletas"][:menus_mod.ITEM_UP])) + "\n")
        handle.write(block("item_cgram_uploads", palettes_cgram(
            slots["items_paletas"][menus_mod.ITEM_UP:])) + "\n")
        # The windows of the item and equipment screens, on BG1: see
        # `ITEM_WINDOWS` and `screens.EQ_WINDOWS`. The tiles and the
        # colors are the same for both. Each tilemap goes without the bottom
        # rows the screen doesn't show, and each cursor as the two rows of
        # cells it takes, which the ROM copies on top: 128 bytes.
        border_tiles, border_colors, ((border_map, border_bars),
                                      (eq_map, eq_bars)) = \
            slots["items_marco"]
        handle.write(block("items_border_tiles", b"".join(
            pack_tile(cell, planes=8) for cell in border_tiles)) + "\n")
        handle.write(block("items_border_map", b"".join(
            word.to_bytes(2, "little") for word in border_map)) + "\n")
        handle.write(block("items_border_bars", b"".join(
            word.to_bytes(2, "little") for bar in border_bars
            for word in bar)) + "\n")
        handle.write(block("eq_border_map", b"".join(
            word.to_bytes(2, "little") for word in eq_map)) + "\n")
        handle.write(block("eq_border_bars", b"".join(
            word.to_bytes(2, "little") for bar in eq_bars
            for word in bar)) + "\n")
        handle.write(block("items_border_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little")
            for c in border_colors)) + "\n")
        # The shop windows, on BG1 with their own base: see
        # `screens.TI_WINDOWS` and `compact_shop`, which says what is
        # stored. The stretches of each layer are `(VRAM word, source byte in
        # `ti_border_rows`, bytes)`, terminated by three zeros; the bars,
        # `(VRAM word, source byte in `ti_border_patches`, bytes per row,
        # rows)`.
        PM = screens_mod
        ti_tiles, ti_colors, ti_maps = slots["tienda_marco"]
        ti_rows, ti_top, ti_layers, ti_patches, ti_bars = \
            PM.compact_shop(ti_maps)

        def le_words(values):
            return b"".join(v.to_bytes(2, "little") for v in values)

        handle.write(block("ti_border_tiles", b"".join(
            pack_tile(cell, planes=8) for cell in ti_tiles)) + "\n")
        handle.write(block("ti_border_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little") for c in ti_colors)) + "\n")
        handle.write(block("ti_border_rows", le_words(
            p for f in ti_rows for p in f)) + "\n")
        handle.write(block("ti_border_patches", le_words(ti_patches))
                     + "\n")
        cols = constants.COLS
        stretches, layer_stretches = [], []
        for layer in ti_layers:
            layer_stretches.append(2 * len(stretches))
            for row, origin, how_many in layer:
                stretches += [PM.TI_MAP + row * cols, origin * 2 * cols,
                              how_many * 2 * cols]
            stretches += [0, 0, 0]
        handle.write(block("ti_stretches", le_words(stretches)) + "\n")
        handle.write(block("ti_layer_stretches", le_words(layer_stretches))
                     + "\n")
        handle.write(block("ti_bars", le_words(
            v for layer in ti_bars for row, col, rows, width, origin in layer
            for v in (PM.TI_MAP + row * cols + col, 2 * origin, 2 * width,
                      rows))) + "\n")
        base_bars = [0]
        for layer in ti_bars:
            base_bars.append(base_bars[-1] + len(layer))
        handle.write(block("ti_bar_base", bytes(base_bars[:-1])) + "\n")
        handle.write(block("ti_layer_mode", bytes(PM.TI_LAYER_OF_MODE))
                     + "\n")
        handle.write(
            "TI_BORDER_VRAM    = $%04X\n"
            "TI_BORDER_MAP     = $%04X\n"
            "TI_BORDER_TILES   = %d\n"
            "TI_BORDER_COLORS  = %d\n"
            "TI_BORDER_UP      = %d\n"
            % (PM.TI_VRAM, PM.TI_MAP, len(ti_tiles), len(ti_colors),
               ti_top))
        # The End Game screen, whole: see tools/port/end_game.py. The two
        # palettes go one after the other, the "Yes" one first: the ROM picks
        # one by multiplying.
        end_tiles, end_rows, end_row0, end_palettes = slots["fin"]
        handle.write(block("end_tiles", b"".join(
            pack_tile(cell, planes=4) for cell in end_tiles)) + "\n")
        handle.write(block("end_map", b"".join(
            word.to_bytes(2, "little") for word in end_rows)) + "\n")
        handle.write(block("end_cgram", palettes_cgram(end_palettes)) + "\n")
        handle.write(block("end_ramp", bytes(end_game_mod.ramp())) + "\n")
        handle.write(
            "END_TILES   = %d\n"
            "END_ROW0    = %d\n"
            "END_ROWS    = %d\n"
            "END_ENTERS  = %d\n"
            "END_NO      = %d\n"
            "END_FRAMES = %d\n"
            "END_STEP_SONG = %d\n"
            % (len(end_tiles), end_row0, len(end_rows) // constants.COLS,
               end_game_mod.DEFAULT_CHOICE, end_game_mod.NO, end_game_mod.FADE_FRAMES,
               events.fade_step(end_game_mod.SONG_FADE_MS)))
        item_texts, item_texts_ofs = bytearray(), []

        def new_text(text):
            text = menus_mod.item_text(text, 255)
            item_texts_ofs.append((len(item_texts), len(text)))
            item_texts.extend(text.encode("ascii"))
            return len(item_texts_ofs) - 1

        for number in slots["items"]:
            item = slots["items_db"][number]
            for text in ([menus_mod.item_text(
                    item.name, menus_mod.ITEM_NAME_WIDTH)]
                    + menus_mod.split_description(item.description)):
                new_text(text)
        # Dead texts **after the item ones and before all the others**, so
        # that the battle's indices go past 255 in a one-map cartridge:
        # reproducing it for real takes the fifty-seven items of `abl`, that
        # is its twenty-nine maps and two and a half minutes of converter per
        # case. It had a sibling, `--relleno-de-mensajes`, that did the same
        # with the text block; that one went away on 2026-09-20 because the
        # push can be given by a case —see the `test-special` cartridge in the
        # project file— and this one can't, because what shifts isn't a text
        # but an index.
        #
        # **They go here and not at the start, which is where they were until
        # 2026-09-20.** An item's name isn't named through a table but by the
        # computation `3k` —`3k + 1` and `3k + 2` are its two description
        # lines, see `text_write`—, so a dead text before the first one
        # shifts every item and the ROM ends up drawing the dead ones, which
        # measure zero: the battle's "Use Item" list came out with the cursor
        # and the quantities and without a single name. With the padding here
        # the flag goes back to doing what it promises, which is not changing
        # a pixel.
        for _ in range(slots.get("relleno_textos") or 0):
            item_texts_ofs.append((0, 0))
        # And the fixed ones, behind: the parameters and the equipment slots,
        # and the name of each actor that can join the party. See screens.py.
        P = screens_mod
        B = battle_mod
        db = slots["db"]
        param_text = [new_text(t[:P.EQ_PARAM_VALUE - 1])
                      for t in db.term_params]
        slot_text = [new_text(t[:P.EQ_SLOT_TERM_WIDTH])
                     for t in db.term_equipment]
        actor_text = {a: new_text(db.actors[a].name)
                      for a in slots["actores"]}
        # The shop's: the eleven messages of each of the three sets, two lines
        # each —`split_description`, as in screens.py—, and "Owned Items",
        # "Equipped Items" and the currency.
        shop_text = None
        for names_in_game in range(3):
            term = P.shop_terms(db, names_in_game)
            for name, _term in P.TI_TERMS:
                lines = menus_mod.split_description(term[name])
                # Outside the main one, the message goes in a one-line window:
                # `ti_message` writes only the first.
                if lines[1] and name not in ("saludo", "resaludo"):
                    raise SystemExit(
                        "the shop message %r, of set %d, takes two "
                        "lines and its window has one"
                        % (term[name], names_in_game))
                for line in lines:
                    t = new_text(line)
                    if shop_text is None:
                        shop_text = t
        owned_text = new_text(P.lcf_term(db, P.TI_TERM_OWNED))
        carried_text = new_text(P.lcf_term(db, P.TI_TERM_CARRIED))
        currency_text = new_text(db.term_gold)
        # And the battle's: the fifteen LDB terms the screen uses —in the order
        # of `rules.BATTLE_TERMS`, which is the one the ROM indexes— and the
        # name of each enemy some troop of the cartridge brings. The three
        # commands go **already trimmed**, by `screens.command_text`: the
        # LDB brings them with leading spaces and that would shift the text of
        # their column.
        battle_term = rules.battle_terms(db)
        battle_text = None
        victory = P.victory_lines(battle_term["victory"])
        if len(victory) > P.BA_VICTORY_TERM_MAX:
            raise SystemExit("the victory term takes %d lines and "
                             "the window leaves it %d: %r"
                             % (len(victory), P.BA_VICTORY_TERM_MAX, victory))
        for name, _term in rules.BATTLE_TERMS:
            text = battle_term[name]
            if name in ("attack", "defend", "escape"):
                text = P.command_text(text)
            if name == "victory":
                text = victory[0]
            t = new_text(text)
            if battle_text is None:
                battle_text = t
        # And the line for a fallen one an item revived: the dead state's
        # `message_recovery`, which goes stuck to the name —"Core has
        # revived!"—. It isn't a term but a piece of the state's data, so it
        # goes separately and with its own index. See `ba_message`.
        revived_text = new_text(P.revived_text(db))
        # The second line of the victory, empty if it fits in one: it goes
        # separately so as not to shift the indices of `BATTLE_TERMS`.
        victory2_text = new_text((victory + [""])[1])
        rom_enemies = sorted({e for number in troops
                              if number in db.troops
                              for e in db.troops[number].members})
        enemy_text = {e: new_text(menus_mod.item_text(
            db.enemies[e].name, P.BA_NAME_WIDTH)) for e in rom_enemies}
        # And the skills': the ones some actor that can join the party knows,
        # **at their LDB level** —see `battle.skills_of`—, sorted by
        # number, which is the order the menu puts them in. With the intro's
        # party they are seven: 129, 130, 131, 143, 144, 146 and 150.
        #
        # **All the ones they can end up knowing**, and not only the LDB's: a
        # `ChangeSkills` teaches the actor what the learning table doesn't
        # have, and since 2026-09-21 that shows in battle. They are those of
        # their pairs in `events.SKILL_SLOT` that the battle knows how
        # to offer.
        #
        # And the ones some enemy of the cartridge's troops uses, since
        # 2026-09-27: `ShortCircuit`, from the ones at the recycling plant. See
        # `battle.actions_of_enemy`.
        rom_actions = {e: B.actions_of_enemy(db, e) for e in rom_enemies}
        rom_skills = sorted(
            {h for (a, h) in events.SKILL_SLOT
             if a in slots["actores"] and B.skill_usable(db.skills[h])}
            | {skill.id for values in rom_actions.values()
               for _r, skill, _ef in values if skill is not None})
        skill_text = {h: new_text(menus_mod.item_text(
            db.skills[h].name, P.BA_SKILL_NAME_WIDTH))
            for h in rom_skills}
        skill_desc_text = {h: new_text(menus_mod.item_text(
            db.skills[h].description, P.BA_SKILL_DESC_WIDTH))
            for h in rom_skills}
        # And the **whole** name of the ones learned on leveling up, which is
        # what "<skill> acquired!" says at the victory: the list's is cut to
        # its column, and some of these the battle doesn't know how to offer
        # —Lurk In Shadows, Arden's— and aren't in the list. See
        # `skill_pair_learns_txt`.
        taught = {h for (a, h) in events.SKILL_SLOT
                  if a in slots["actores"] and a in db.actors
                  and B.level_learned(db, a, h)
                  > X.initial_level(db.actors[a])}
        whole_skill_text = {
            h: new_text(menus_mod.item_text(db.skills[h].name, 255))
            for h in sorted(taught)}
        # The two lines RM2k says when using it: `using_message1` goes after
        # the name of the one using it and `using_message2` alone, on the line
        # below. `GetSkillFirstStartMessage2k` and its sibling.
        skill_msg1_text = {h: new_text(db.skills[h].using_message1)
                           for h in rom_skills}
        skill_msg2_text = {h: new_text(db.skills[h].using_message2)
                           for h in rom_skills}
        # And what each actor's command is called: `Game_Actor::GetSkillName`,
        # that is its `skill_name` —"AgentTrain", "Telepathy", "Slicing"— and
        # not the LDB's `command_skill`. It goes trimmed like the other four
        # commands.
        skill_command_text = {a: new_text(P.command_text(
            B.skill_command_name(db, a))) for a in slots["actores"]}
        handle.write(block("item_texts", bytes(item_texts) or b"\x00")
                     + "\n")
        if len(slot_blocks) > 255:
            raise SystemExit("the slots screen has %d blocks and the "
                             "tables that name them are one byte"
                             % len(slot_blocks))
        # The tables that name them **don't go here**: the ROM reads them with
        # `lda slot_block_lo, x`, which addresses the data bank, so they
        # have to live in bank 0 together with the code. They are emitted
        # further down, in the TABLES segment.
        #
        # The palette goes padded up to the TITLE_MENU_CGRAM entries, which
        # is what the ROM uploads at once: if the text uses fewer colors, the
        # DMA would read whatever follows in the cartridge.
        colors = []
        for palette in slots["paletas"]:
            palette = list(palette)
            colors += palette + [(0, 0, 0)] * (constants.MENU_CGRAM
                                               - len(palette))
        handle.write(block("slot_cgram",
                           b"".join(cgram_word(c).to_bytes(2, "little")
                                    for c in colors)) + "\n")

        handle.write('\n.segment "TABLES"\n')
        # The cell blocks of the slots screen are named by pointers, and the
        # three tables go in bank 0 because the ROM reads them with
        # `lda slot_block_lo, x`. The same for `slot_vram`, which says
        # which tilemap address each row goes to: the computation comes from
        # the same geometry that drew the text and that is why it lives in a
        # single place.
        for field, prefix in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write("slot_block_%s:\n       .byte %s\n"
                         % (field, ", ".join(prefix + e
                                             for e in slot_blocks)))
        row_of = [SLOT_MAP + (menus_mod.SLOT_Y
                              + n * menus_mod.SLOT_STEP)
                  // constants.CELL * 32 for n in range(SLOTS)]
        handle.write("slot_vram:\n      .word %s\n" % ", ".join(
            str(v) for v in row_of))
        # Where the faces go —four entries per slot, so that the index is the
        # slot times four plus the place, without multiplying by three— and
        # the leader's name.
        handle.write("slot_face_vram:\n      .word %s\n" % ", ".join(
            str(row_of[n] + menus_mod.FACE_COL
                + place * menus_mod.FACE_STEP if place < menus_mod.FACES_MAX
                else 0)
            for n in range(SLOTS) for place in range(4)))
        handle.write("slot_name_vram:\n        .word %s\n" % ", ".join(
            str(row_of[n] + menus_mod.NAME_ROW * 32
                + menus_mod.NAME_COL) for n in range(SLOTS)))
        n_actors = max(list(face_block) + list(slots["actores"])
                       + [-1]) + 1
        handle.write("slot_face_block:\n       .byte %s\n" % (", ".join(
            str(face_block.get(actor, 0xFF))
            for actor in range(n_actors)) or "$FF"))
        # The pause menu: its blocks, and where each thing goes in the
        # tilemap, in words. The geometry is `menus.py`'s and comes from
        # there.
        T = menus_mod
        from port import font as font_mod

        def vram_cell(row, col):
            return SLOT_MAP + row * 32 + col

        option_rows = [(T.MENU_OPT_Y + n * T.MENU_OPT_STEP)
                       // constants.CELL for n in range(T.MENU_OPTIONS)]
        handle.write(
            "MENU_OPTIONS      = %d\n"
            "MENU_SAVE         = %d\n"
            "MENU_END          = %d\n"
            "MENU_BLK_OPTION   = %d\n"
            "MENU_BLK_CURRENCY = %d\n"
            "MENU_BLK_ROW      = %d\n"
            "MENU_OPT_COLS     = %d\n"
            "MENU_CURRENCY_COLS = %d\n"
            "MENU_CURRENCY_VRAM = %d\n"
            "MENU_ACTOR_COLS   = %d\n"
            "MENU_ACTOR_ROWS   = %d\n"
            "MENU_ROWS_PARTY   = %d\n"
            "MENU_ACTORS_N     = %d\n"
            "MENU_HP_DIGITS    = %d\n"
            "MENU_HP_OFS       = %d\n"
            "MENU_FACE_CELLS   = %d\n"
            "MENU_NAME_COLS    = %d\n"
            "MENU_NAME_OFS = %d\n"
            "MENU_LEVEL_OFS    = %d\n"
            "MENU_MAX_DIGITS   = %d\n"
            "MENU_MAX_OFS      = %d\n"
            % (T.MENU_OPTIONS, T.MENU_SAVE, T.MENU_END, menu_option_block,
               menu_currency_block, menu_row_block,
               T.MENU_OPT_COLS, T.MENU_CURRENCY_COLS,
               vram_cell(T.MENU_GOLD_Y // constants.CELL, T.MENU_CURRENCY_COL),
               T.MENU_ACTOR_COLS, T.MENU_ACTOR_ROWS, T.MENU_PARTY_ROWS,
               n_actors,
               # And how many cells from the first of the actor's block the
               # hundreds of its HP fall, which is what `menu_hp_write`
               # adds to `menu_row_vram`.
               T.MENU_HP_DIGITS,
               T.MENU_HP_ROW * 32 + T.MENU_HP_COL - T.MENU_ACTOR_COL,
               # The face goes in the top-left corner of the row —that is why
               # it carries no offset— and the three strips the ROM composes,
               # each in its own.
               T.FACE_CELLS, T.MENU_NAME_COLS,
               T.MENU_NAME_ROW * 32 + T.MENU_NAME_COL - T.MENU_ACTOR_COL,
               T.MENU_LEVEL_ROW * 32 + T.MENU_LEVEL_COL - T.MENU_ACTOR_COL,
               T.MENU_MAX_DIGITS,
               T.MENU_HP_ROW * 32 + T.MENU_MAX_COL - T.MENU_ACTOR_COL))
        # Which commands do something: 1 yes, 0 no. The save one also checks
        # the permission, in the ROM.
        handle.write("menu_done:\n     .byte %s\n" % ", ".join(
            "1" if n in T.MENU_DONE else "0"
            for n in range(T.MENU_OPTIONS)))
        handle.write("menu_option_vram:\n    .word %s\n" % ", ".join(
            str(vram_cell(f, T.MENU_OPT_COL)) for f in option_rows))
        handle.write("menu_cursor_vram:\n    .word %s\n" % ", ".join(
            str(vram_cell(f, T.MENU_CURSOR_COL)) for f in option_rows))
        handle.write("menu_row_vram:\n     .word %s\n" % ", ".join(
            str(vram_cell(r * T.MENU_ACTOR_ROWS, T.MENU_ACTOR_COL))
            for r in range(T.MENU_PARTY_ROWS)))
        # The cursor's two cells, top and bottom: the ROM writes them one word
        # at a time.
        handle.write("menu_cursor_cells:\n     .word %s\n" % ", ".join(
            "$%04X" % entry(c, False, False, priority=1)
            for c in menu["cursor"]))
        # And what the screen composes on the fly, which goes **outside bank
        # 0**: it is read with `lda f:`, and it is almost a thousand bytes the
        # code's bank would miss. The glyphs are indexed by character —from
        # ITEM_FIRST_CHAR, like those of the item screen— and the letters
        # this cartridge doesn't use stay in the empty cell: nobody asks for
        # them, and a complete table is indexed without subtracting anything
        # else.
        handle.write('.segment "RODATA"\n')
        empty = "$%04X, $%04X" % (entry(0, False, False),
                                  entry(0, False, False))
        handle.write(".block %d\nslot_glyph_cells:\n        .word %s\n"
                     % (menus_mod.ITEM_CHARS * 4, ", ".join(
                         ", ".join("$%04X" % entry(c, False, False,
                                                   priority=1)
                                   for c in menu["glifos"][letter])
                         if letter in menu["glifos"] else empty
                         for letter in map(
                             chr, range(menus_mod.ITEM_FIRST_CHAR,
                                        menus_mod.ITEM_FIRST_CHAR
                                        + menus_mod.ITEM_CHARS)))))
        # The experience line, which the ROM draws with sprites: see
        # `MENU_EXP_X` in menus.py. The term is four tiles —two wide, top and
        # bottom— and the digits come from `slot_glyph_cells`.
        handle.write(".block %d\nmenu_exp_finished:\n    .word %s\n" % (
            2 * len(menu["exp_termino"]), ", ".join(
                "$%04X" % entry(c, False, False)
                for c in menu["exp_termino"])))
        # The actor choice: its windows on BG1 —see `TARGET_WINDOWS` in
        # menus.py—. A single tilemap, the one with an item, and the bar only
        # in the rectangle that changes: see `menus.compact_target`. And
        # the name of each medicine on two lines, in ASCII, with a table of
        # one byte per `k` that says which one it is —$FF if it isn't a
        # medicine—: only medicines open this screen.
        obj_tiles, obj_colors, obj_maps = slots["objetivo"]
        (obj_map, obj_bars, obj_row0, obj_rows, obj_col0, obj_cols,
         obj_erase_rows, obj_erase_cols) = T.compact_target(obj_maps)
        handle.write(block("target_tiles", b"".join(
            pack_tile(cell, planes=8) for cell in obj_tiles)) + "\n")
        handle.write(block("target_map", b"".join(
            word.to_bytes(2, "little") for word in obj_map)) + "\n")
        handle.write(block("target_bars", b"".join(
            word.to_bytes(2, "little") for bar in obj_bars
            for word in bar)) + "\n")
        handle.write(block("target_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little") for c in obj_colors)) + "\n")
        medicines = [n for n in slots["items"]
                     if slots["items_db"][n].type == lcf.ITEM_TYPE_MEDICINE]
        if len(medicines) > 255:
            raise SystemExit("%d medicines don't fit in `target_name`"
                             % len(medicines))
        handle.write(block("target_name", bytes(
            medicines.index(n) if n in medicines else 0xFF
            for n in slots["items"])) + "\n")
        handle.write(block("target_names", b"".join(
            "".join(T.name_in_lines(slots["items_db"][n].name))
            .encode("ascii", "replace") for n in medicines)) + "\n")
        handle.write(
            "TARGET_VRAM       = $%04X\n"
            "TARGET_MAP        = $%04X\n"
            "TARGET_TILES      = %d\n"
            "TARGET_CGRAM      = %d\n"
            "TARGET_COLORS     = %d\n"
            "TARGET_NAME_WIDTH = %d\n"
            "TARGET_NAME_VRAM = %d\n"
            "TARGET_COUNT_VRAM = %d\n"
            "TARGET_BAR_ROW0 = %d\n"
            "TARGET_BAR_ROWS = %d\n"
            "TARGET_BAR_COL0 = %d\n"
            "TARGET_BAR_COLS = %d\n"
            "TARGET_ERASE_ROWS = %d\n"
            "TARGET_ERASE_COLS = %d\n"
            % (T.TARGET_VRAM, T.TARGET_MAP, len(obj_tiles),
               T.TARGET_CGRAM, len(obj_colors), T.TARGET_NAME_WIDTH,
               vram_cell(T.TARGET_NAME_ROW, T.TARGET_NAME_COL),
               vram_cell(T.TARGET_COUNT_ROW, T.TARGET_COUNT_COL),
               obj_row0, obj_rows, obj_col0, obj_cols, obj_erase_rows,
               obj_erase_cols))
        handle.write(
            "MENU_EXP_X        = %d\n"
            "MENU_EXP_NUM_X    = %d\n"
            "MENU_EXP_Y        = %d\n"
            "MENU_EXP_STEP     = %d\n"
            "MENU_EXP_DIGITS   = %d\n"
            "MENU_EXP_LETTERS  = %d\n"
            "MENU_ACTOR_HEIGHT = %d\n"
            % (T.MENU_EXP_X,
               T.MENU_EXP_X + T.MENU_EXP_NUM_DX - T.GLYPH_DX,
               T.MENU_EXP_Y - T.GLYPH_DY, font_mod.WIDTH, T.MENU_EXP_DIGITS,
               T.MENU_EXP_LETTERS, T.MENU_ACTOR_ROWS * constants.CELL))
        # Each actor's text, in ASCII: the name —with trailing spaces, which
        # are what erase whatever was there—, the two digits of the level and
        # max HP after its bar. **The three together, in one row per actor**,
        # so the ROM has a single address to compute and three offsets that
        # are constants.
        db_slots = slots["db"]
        if (SLOT_TEXT_LEVEL < menus_mod.MENU_NAME_COLS
                or SLOT_TEXT_MAX + menus_mod.MENU_MAX_DIGITS
                > SLOT_TEXT_WIDTH):
            raise SystemExit("the actor's three strips don't fit in the %d "
                             "bytes of its row" % SLOT_TEXT_WIDTH)
        strip = bytearray()
        for a in range(n_actors):
            row = (menus_mod.name_text(db_slots, a)
                   .ljust(SLOT_TEXT_LEVEL)
                   + menus_mod.level_text(db_slots, a)
                   + menus_mod.max_text(db_slots, a))
            strip += row.ljust(SLOT_TEXT_WIDTH).encode("ascii")
        handle.write(".block %d\nslot_actor_text:\n        .byte %s\n"
                     % (max(1, len(strip)),
                        ", ".join(str(b) for b in strip) or "0"))
        handle.write('.segment "TABLES"\n')
        # The item screen. `item_k` goes from the RM2k number to its place in
        # the ROM's tables, $FF if this ROM doesn't know it; the rest is per
        # place. `item_use`: bit 0 if it goes in white and A does something,
        # bit 1 if using it spends one —the switch ones with uses—, bit 2 if it
        # opens the actor choice —the medicines—, bit 3 if it is a two-handed
        # weapon. The texts go three per item —the name and the two lines of
        # the description—: text `t` is `3k + field`.
        items = slots["items"]
        db_items = slots["items_db"]
        if len(items) > 255:
            raise SystemExit("%d items don't fit in one-byte tables"
                             % len(items))
        k_of = {number: k for k, number in enumerate(items)}
        handle.write(
            "ITEMS_ROM         = %d\n"
            "ITEMS_TILES       = %d\n"
            "ITEMS_CGRAM_N     = %d\n"
            "ITEM_ROWS         = %d\n"
            "ITEM_CURSOR_COL   = %d\n"
            "ITEM_NAME_COL     = %d\n"
            "ITEM_TWO_POINTS_COL = %d\n"
            "ITEM_DIGITS_COL   = %d\n"
            "ITEM_DESC_VRAM    = %d\n"
            "ITEM_DESC_COL     = %d\n"
            "ITEM_FIRST_CHAR = %d\n"
            "ITEM_GLYPHS_GRAY  = %d\n"
            "ITEM_BORDER_VRAM  = $%04X\n"
            "ITEM_BORDER_TILES = %d\n"
            "ITEM_BORDER_MAP   = $%04X\n"
            "ITEM_BORDER_CGRAM = %d\n"
            "ITEM_BORDER_COLORS = %d\n"
            "ITEM_BORDER_ROWS  = %d\n"
            "ITEM_BORDER_LIST  = %d\n"
            % (len(items), len(slots["items_tiles"]),
               menus_mod.ITEM_UP * constants.MENU_CGRAM,
               T.ITEM_ROWS, T.ITEM_CURSOR_COL, T.ITEM_NAME_COL,
               T.ITEM_COLON_COL, T.ITEM_DIGITS_COL,
               vram_cell(T.ITEM_DESC_Y // constants.CELL, T.ITEM_DESC_COL),
               T.ITEM_DESC_COL,
               T.ITEM_FIRST_CHAR, T.ITEM_CHARS * 4,
               SLOT_VRAM
               + items_border_first(len(slots["items_tiles"])) * 32,
               len(border_tiles), T.ITEM_BORDER_MAP, T.ITEM_BORDER_CGRAM,
               len(border_colors), constants.ROWS,
               T.ITEM_LIST_Y // constants.CELL))

        def bytes_asm(label, values, fmt="%d", declare=False):
            if declare:
                handle.write(".block %d\n" % max(1, len(values)))
            handle.write("%s:\n    .byte %s\n" % (label, ", ".join(
                fmt % v for v in values) or "$FF"))

        def words_asm(label, values, fmt="%d", declare=False):
            if declare:
                handle.write(".block %d\n" % max(2, 2 * len(values)))
            handle.write("%s:\n    .word %s\n" % (label, ", ".join(
                fmt % v for v in values) or "0"))

        # `item_k` goes outside bank 0 —it is read with `lda f:item_k, x`—:
        # the code's bank filled up with the audio package.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_k", [k_of.get(n, 0xFF)
                             for n in range(events.ITEMS_N)],
                  declare=True)
        handle.write('.segment "TABLES"\n')
        words_asm("item_id", items)
        bytes_asm("item_use", [
            (1 if T.item_usable(db_items[n]) else 0)
            | (2 if T.item_usable(db_items[n])
               and not T.item_needs_actor(db_items[n])
               and db_items[n].uses else 0)
            | (4 if T.item_needs_actor(db_items[n]) else 0)
            | (8 if db_items[n].two_handed else 0)
            for n in items])
        # `item_switch` goes outside bank 0 —it is read with
        # `lda f:item_switch, x`, only once per item used— because the random
        # encounters pushed it over by 34 bytes on 2026-09-13. It is 124: the
        # largest of the tables that are read with X and aren't in any
        # per-frame loop.
        handle.write('.segment "RODATA"\n')
        words_asm("item_switch", [db_items[n].switch_id for n in items],
                  declare=True)
        handle.write('.segment "TABLES"\n')
        # What each item does in a battle: whether it goes in the list that is
        # offered and how much it heals. The rule for which ones go in is
        # `battle.item_usable_in_battle`, that is `Game_Party::IsItemUsable`
        # with the battle open plus what this port knows how to do; the
        # computation of how much it heals is
        # `Game_BattleAlgorithm::Item::vExecute`.
        # **Outside bank 0**, like `item_k` and for the same reason: with the
        # maps of `abl` the code area ended up at 32775 of 32704 when putting
        # them here. The battle reads them with `lda f:item_battle, x`.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_battle", [
            1 if B.item_usable_in_battle(db_items[n]) else 0 for n in items],
            declare=True)
        bytes_asm("item_heal_rate", [db_items[n].recover_hp_rate
                                     for n in items], declare=True)
        words_asm("item_heal_hp", [min(db_items[n].recover_hp, 0xFFFF)
                                   for n in items], declare=True)
        # And what a medicine does outside battle, which is the whole of
        # `Game_Battler::UseItem`: the SP, like the HP, and `item_medicine`
        # with three bits —1 if it is `ko_only`, 2 if it removes the dead
        # state, which is the first of `state_set` and what revives a fallen
        # one, 4 if using it spends one, which is `uses` nonzero—. The other
        # states of `state_set` don't go: outside battle this port has no
        # states, so removing them is never useful. See `medicine_use`.
        bytes_asm("item_heal_sp_rate", [db_items[n].recover_sp_rate
                                        for n in items], declare=True)
        words_asm("item_heal_sp", [min(db_items[n].recover_sp, 0xFFFF)
                                   for n in items], declare=True)
        bytes_asm("item_medicine", [
            (1 if db_items[n].ko_only else 0)
            | (2 if db_items[n].state_set[:1] == [True] else 0)
            | (4 if db_items[n].uses else 0)
            for n in items], declare=True)
        handle.write('.segment "TABLES"\n')
        # The four text ones go **outside bank 0**, like `item_k` and for the
        # same reason: they don't fit there. With the ten maps of `abl` the
        # code area was at 32622 of 32704 —eighty-two free bytes— and the
        # `ShowPicture` picture didn't fit. They are read with
        # `lda f:item_txt_lo, x`, which costs one byte and one cycle per read
        # in thirteen places, none inside a per-frame loop.
        handle.write('.segment "RODATA"\n')
        for field, prefix in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write(".block %d\n" % max(1, len(item_texts_ofs)))
            handle.write("item_txt_%s:\n    .byte %s\n" % (field, ", ".join(
                "%s(item_texts + %d)" % (prefix, ofs)
                for ofs, _ in item_texts_ofs) or "0"))
        bytes_asm("item_txt_n", [n for _, n in item_texts_ofs],
                  declare=True)
        handle.write('.segment "TABLES"\n')
        words_asm("item_row_vram", [
            vram_cell(T.ITEM_LIST_Y // constants.CELL + 2 * f, 0)
            for f in range(T.ITEM_ROWS)])
        # The two cells of each character, top and bottom: first the 95 in
        # white, then in gray and then in the "goes up" color. Character `c`
        # in variant `g` is at
        # `g * ITEM_GLYPHS_GRAY + (c - ITEM_FIRST_CHAR) * 4`.
        # --- the equipment ---
        # Per known item: its type, what it adds —attack, defense, spirit,
        # agility, signed— and who can equip it, one bit per actor. Per actor,
        # from 0 to the LDB's last: its level parameters and its initial
        # equipment, which the ROM copies to `FAR_EQUIPMENT` on reset. And where
        # each thing goes in the screen's buffer, in bytes: row * 64 + col * 2.
        n_actors = max(db.actors) + 1

        def pos(row, col):
            return row * 64 + col * 2

        bytes_asm("item_type", [db_items[n].type for n in items])
        handle.write('.segment "RODATA"\n')     # same: see `item_txt_lo`
        words_asm("item_points", [p & 0xFFFF for n in items
                                  for p in db_items[n].points],
                  declare=True)
        # And what attacking with each one costs: the weapons' `sp_cost`, zero
        # for the rest —`battle.weapon_sp_of`—. The battle reads it once per
        # actor when it is set up.
        bytes_asm("item_sp", [db_items[n].sp_cost
                              if db_items[n].type == lcf.ITEM_TYPE_WEAPON
                              else 0 for n in items], declare=True)
        # `item_actors` also goes outside bank 0 —it is read with
        # `lda f:item_actors, x`—: it is 496 bytes, the fattest ones `TABLES`
        # had left, and bank 0 overflowed. It isn't a precaution: on
        # 2026-09-13 `just demo` stopped with "el área no
        # entra: 32719 bytes en 32704" and no case of the suite saw it.
        # It is read once per item when building the equipment screen's list,
        # so the extra cycle of long addressing doesn't show.
        bytes_asm("item_actors", [
            sum(1 << b for b in range(8)
                if 8 * byte + b + 1 < n_actors
                and db_items[n].equippable_by(8 * byte + b + 1))
            for n in items for byte in range(8)], declare=True)
        # `actor_params` goes outside bank 0 —it is read with
        # `lda f:actor_params, x`, only once per equipment screen— for the same
        # reason as `item_k`: it is 488 bytes and the code's bank filled up,
        # and this time with the drawing of the battle animations.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_params", [
            (rules.param_of(db.actors[a], k)
             if a in db.actors else 0) & 0xFFFF
            for a in range(n_actors)
            for k in ("attack", "defense", "spirit", "agility")],
            declare=True)
        handle.write('.segment "TABLES"\n')
        handle.write('\n.segment "RODATA"\n')
        handle.write(".block %d\n"
                     % (2 * n_actors * constants.EQUIPMENT_SLOTS))
        handle.write("equipment_initial:\n .word %s\n" % ", ".join(
            str(db.actors[a].initial_equipment[r] if a in db.actors else 0)
            for a in range(n_actors)
            for r in range(constants.EQUIPMENT_SLOTS)))
        handle.write('\n.segment "TABLES"\n')
        words_asm("actor_txt", [actor_text.get(a, 0xFFFF)
                                for a in range(n_actors)], "$%04X")
        words_asm("eq_param_pos", [pos(f, c) for f, c in P.EQ_PARAMS])
        words_asm("item_price", [db_items[n].price for n in items])
        handle.write(
            "TI_TEXT           = %d\n"
            "TI_TEXT_HAVE      = %d\n"
            "TI_TEXT_CARRIED   = %d\n"
            "TI_TEXT_CURRENCY  = %d\n"
            "TI_SECOND         = %d\n"
            "TI_MAIN_MSG_POS = %d\n"
            "TI_MSG_POS        = %d\n"
            "TI_COMMAND_POS0   = %d\n"
            "TI_GOLD_POS       = %d\n"
            "TI_HAVE_POS       = %d\n"
            "TI_HAVE_NUM       = %d\n"
            "TI_CARRIED_POS    = %d\n"
            "TI_CARRIED_NUM    = %d\n"
            "TI_LIST_POS0      = %d\n"
            "TI_LIST_ROWS_BUY = %d\n"
            "TI_LIST_ROWS_SALE = %d\n"
            "TI_NAME           = %d\n"
            "TI_PRICE          = %d\n"
            "TI_COUNT_POS      = %d\n"
            "TI_COUNT_X_POS    = %d\n"
            "TI_COUNT_NUM_POS = %d\n"
            "TI_TOTAL_POS      = %d\n"
            "TI_RED            = %d\n"
            % (shop_text, owned_text, carried_text, currency_text,
               P.TI_SECOND,
               pos(P.TI_MAIN_MSG_ROW, T.ITEM_DESC_COL),
               pos(P.TI_MSG_ROW, T.ITEM_DESC_COL),
               pos(P.TI_MAIN_MSG_ROW + 2, P.TI_COMMAND_COL),
               pos(P.TI_GOLD_ROW, P.TI_GOLD_COL),
               pos(P.TI_OWNED_ROW, P.TI_STATUS_COL),
               pos(P.TI_OWNED_ROW, P.TI_STATUS_NUM),
               pos(P.TI_CARRIED_ROW, P.TI_STATUS_COL),
               pos(P.TI_CARRIED_ROW, P.TI_STATUS_NUM),
               pos(P.TI_LIST_ROW0, 0), P.TI_LIST_ROWS_BUY,
               P.TI_LIST_ROWS_SALE, P.TI_LIST_COL * 2,
               P.TI_PRICE_COL * 2,
               pos(P.TI_COUNT_ROW, P.TI_LIST_COL),
               pos(P.TI_COUNT_ROW, P.TI_COUNT_X_COL),
               pos(P.TI_COUNT_ROW, P.TI_COUNT_COL),
               pos(P.TI_TOTAL_ROW, P.TI_GOLD_COL), T.ITEM_RED))
        # `eq_bar` counts the rows of the slots and those of the list from
        # the same one: they are the same window.
        if P.EQ_LIST_ROW0 != P.EQ_SLOT_ROW0:
            raise SystemExit("the equipment list starts at row %d and the "
                             "slots at %d" % (P.EQ_LIST_ROW0,
                                              P.EQ_SLOT_ROW0))
        handle.write(
            "ACTORS_N          = %d\n"
            "SLOTS_EQUIPMENT   = %d\n"
            "EQ_TEXT_PARAM     = %d\n"
            "EQ_TEXT_SLOT      = %d\n"
            "EQ_ACTOR_POS      = %d\n"
            "EQ_BAR_ROW0       = %d\n"
            "EQ_BORDER_TEXT    = %d\n"
            "EQ_BORDER_TEXT_N  = %d\n"
            "EQ_PARAM_VALUE    = %d\n"
            "EQ_PARAM_ARROW    = %d\n"
            "EQ_SLOT_POS0      = %d\n"
            "EQ_SLOT_TERM      = %d\n"
            "EQ_SLOT_NAME      = %d\n"
            "EQ_SLOT_WIDTH     = %d\n"
            "EQ_LIST_POS0      = %d\n"
            "EQ_LIST_ROWS      = %d\n"
            "EQ_LIST_NAME      = %d\n"
            "SCR_TWO_POINTS    = %d\n"
            "SCR_DESC_POS      = %d\n"
            % (n_actors, constants.EQUIPMENT_SLOTS, param_text[0],
               slot_text[0],
               pos(P.EQ_ACTOR_ROW, P.EQ_ACTOR_COL), P.EQ_SLOT_ROW0,
               P.EQ_SLOT_ROW0,
               max(constants.EQUIPMENT_SLOTS, P.EQ_LIST_ROWS) * 2,
               P.EQ_PARAM_VALUE * 2,
               P.EQ_PARAM_ARROW * 2, pos(P.EQ_SLOT_ROW0, 0),
               P.EQ_SLOT_TERM_COL * 2, P.EQ_SLOT_NAME_COL * 2,
               P.EQ_SLOT_NAME_WIDTH, pos(P.EQ_LIST_ROW0, 0),
               P.EQ_LIST_ROWS,
               P.EQ_LIST_NAME_COL * 2,
               T.ITEM_COLON_COL * 2,
               pos(T.ITEM_DESC_Y // constants.CELL, T.ITEM_DESC_COL)))
        # --- the battle ---
        # Each actor's max HP at its level, by actor number. They go separately
        # from `actor_params`, which carries the four the equipment screen
        # shows; the equipment doesn't touch the HP, as in RM2k.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_hpmax", [
            (rules.param_of(db.actors[a], "maxhp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(n_actors)], declare=True)
        # And the SP, which are state since 2026-09-13 for the same reason as
        # the HP: the skills spend them. See `hp_initial_set` in
        # tools/runtime/bank1.s.
        words_asm("actor_spmax", [
            (rules.param_of(db.actors[a], "maxsp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(n_actors)], declare=True)
        handle.write(experience_asm(db, slots["actores"], n_actors))
        # --- the skills ---
        #
        # One row per skill the cartridge carries, in the order of
        # `rom_skills`, which is by RM2k number. The fields are those of
        # `lcf.Skill` and the computations that use them are in `battle.py`:
        # `skill_effect` is `Algo::CalcSkillEffect` and `cost_of` is
        # `CalcSkillCost`.
        #
        # They go **outside bank 0** and declared with `.block`, like
        # everything the battle reads with `lda f:`: the code's bank is full,
        # and a table split between two banks would be read wrong from the
        # middle on.
        skill_place = {h: k for k, h in enumerate(rom_skills)}
        # That all the ones that reach here are of the kind the battle knows
        # how to offer is guaranteed by `battle.skill_usable`, which is
        # the filter `skills_of` applies on both sides. It is checked
        # again in case they were ever emitted from somewhere else: a
        # multi-target scope or a three-digit cost would be drawn wrong
        # silently.
        for h in rom_skills:
            if not B.skill_usable(db.skills[h]):
                raise SystemExit(
                    "skill %d —type %d, scope %d, %d SP— isn't one of the "
                    "ones this battle knows how to offer" % (h, db.skills[h].type,
                                                             db.skills[h].scope,
                                                             db.skills[h].sp_cost))
        words_asm("skill_id", rom_skills, declare=True)
        words_asm("skill_txt", [skill_text[h] for h in rom_skills],
                  declare=True)
        words_asm("skill_desc", [skill_desc_text[h] for h in rom_skills],
                  declare=True)
        words_asm("skill_msg1", [skill_msg1_text[h] for h in rom_skills],
                  declare=True)
        words_asm("skill_msg2", [skill_msg2_text[h] for h in rom_skills],
                  declare=True)
        words_asm("skill_power", [db.skills[h].power for h in rom_skills],
                  declare=True)
        words_asm("skill_switch", [db.skills[h].switch_id
                                 for h in rom_skills], declare=True)
        bytes_asm("skill_sp", [db.skills[h].sp_cost for h in rom_skills],
                  declare=True)
        # The type: 0 is `normal` and 3 is `switch`, which is the one that
        # turns on a switch and does nothing else. See `Skill::vExecute`.
        bytes_asm("skill_type", [db.skills[h].type for h in rom_skills],
                  declare=True)
        bytes_asm("skill_phys", [db.skills[h].physical_rate
                              for h in rom_skills], declare=True)
        bytes_asm("skill_mag", [db.skills[h].magical_rate
                              for h in rom_skills], declare=True)
        bytes_asm("skill_var", [db.skills[h].variance
                              for h in rom_skills], declare=True)
        bytes_asm("skill_hit", [db.skills[h].hit for h in rom_skills],
                  declare=True)
        # What it touches, one bit per thing, in the order `Skill::vExecute`
        # looks at them —which is the order it consumes randomness in and
        # that is why it matters—: HP, SP, attack, defense, spirit and
        # agility. Bit 6 says whether it targets enemies
        # —`Algo::SkillTargetsEnemies`— and 7 whether it ignores defense.
        bytes_asm("skill_affects", [
            (1 if db.skills[h].affect_hp else 0)
            | (2 if db.skills[h].affect_sp else 0)
            | (4 if db.skills[h].affect_attack else 0)
            | (8 if db.skills[h].affect_defense else 0)
            | (16 if db.skills[h].affect_spirit else 0)
            | (32 if db.skills[h].affect_agility else 0)
            | (64 if db.skills[h].targets_enemies else 0)
            | (128 if db.skills[h].ignore_defense else 0)
            for h in rom_skills], "$%02X", declare=True)
        # And the scope as is, `rpg::Skill::Scope`: 0 one enemy, 1 all, 2
        # oneself, 3 one ally, 4 the whole party. Since 2026-09-27 the battle
        # knows all five: see `battle.skill_targets`.
        bytes_asm("skill_scope", [db.skills[h].scope for h in rom_skills],
                  declare=True)
        # The parallel common events that only look at the equipment,
        # compiled: the ROM runs them when closing the menu if their switch is
        # on. For each one, where its switch is in the bitmap —byte and mask—
        # and its code. See `events.PARTY_COMMON_EVENTS`.
        party_ones = sorted(events.PARTY_COMMON_EVENTS.items())
        handle.write("COMEQ_N = %d\n" % len(party_ones))
        words_asm("comeq_byte", [sw >> 3 for sw, _n in party_ones],
                  declare=True)
        bytes_asm("comeq_mask", ["$%02X" % (1 << (sw & 7))
                                    for sw, _n in party_ones], "%s",
                  declare=True)
        words_asm("comeq_code", [".loword(common_equipment_%d)" % n
                                for _sw, n in party_ones], "%s",
                  declare=True)
        # The bank goes as a word —its high byte isn't read— so that the ROM
        # indexes it with the same X as `comeq_code`.
        words_asm("comeq_bank", ["^common_equipment_%d" % n
                                  for _sw, n in party_ones], "%s",
                  declare=True)
        for _sw, n in party_ones:
            handle.write(block("common_equipment_%d" % n,
                               events.compile_party_common_event(n)) + "\n")
        # And what each actor knows, which since 2026-09-21 is state: one bit
        # per (actor, skill) pair in `FAR_SKILL`, with the slots of
        # `events.SKILL_SLOT`. It is answered by branch 4 of
        # `ConditionalBranch` —which already brings the slot in the bytecode—
        # and by the battle's list, which walks the actor's pairs: where they
        # start —`skill_pair_start`, as words because there are more than 255—,
        # how many there are, and the `k` of each one in the `hab_*` tables
        # above, or $FF if this one doesn't know how to offer it. Since an
        # actor's pairs go together and by number, the list comes out sorted
        # like `LearnSkill`'s.
        #
        # The bits start with `rules.learned_skills`, which is what the LDB
        # says at its initial level: `initial_skills_set` copies them on reset.
        pairs = sorted(events.SKILL_SLOT.items(), key=lambda x: x[1])
        skill_pair_start, skill_pair_n = [], []
        for a in range(n_actors):
            own_ones = [r for (actor, _s), r in pairs if actor == a]
            skill_pair_start.append(own_ones[0] if own_ones else 0)
            skill_pair_n.append(len(own_ones))
            if own_ones and own_ones != list(range(own_ones[0], own_ones[0] + len(own_ones))):
                raise SystemExit("the skill pairs of actor %d aren't "
                                 "contiguous" % a)
        if max(skill_pair_n, default=0) > 255:
            raise SystemExit("an actor has more than 255 skill pairs and "
                             "`skill_pair_n` is one byte")
        skill_bytes = max(1, (len(pairs) + 7) // 8)
        knows = {a: set(rules.learned_skills(db, a)) for a in db.actors}
        bits = [0] * skill_bytes
        for (a, h), r in pairs:
            if h in knows.get(a, ()):
                bits[r >> 3] |= 1 << (r & 7)
        handle.write("; How many bytes the skill bits take in `FAR_SKILL`.\n"
                     "SKILL_BYTES = %d\n" % skill_bytes)
        handle.write("; The signature of the save format: see `SRAM_SIGNATURE`.\n"
                     "GAME_SIGNATURE = $%04X\n" % save_signature(
                         pairs, experience_slots(db, slots["actores"]),
                         n_actors))
        words_asm("skill_pair_init", skill_pair_start, declare=True)
        bytes_asm("skill_pair_n", skill_pair_n, declare=True)
        bytes_asm("skill_pair_k", [skill_place.get(h, 0xFF)
                                if a in slots["actores"] else 0xFF
                                for (a, h), _r in pairs], declare=True)
        bytes_asm("skill_initial", bits, "$%02X", declare=True)
        # And at which level the LDB's learning table teaches each pair, or 0
        # if it doesn't —the ones only a `ChangeSkills` gives—: on leveling
        # up, `exp_add` sets the bits of the pairs whose level it just
        # passed, which is `LearnLevelSkills(old_level + 1, new_level)`.
        bytes_asm("skill_pair_level", [B.level_learned(db, a, h)
                                    if a in db.actors else 0
                                    for (a, h), _r in pairs], declare=True)
        # And the name the victory tells it by —"<skill> acquired!"—, or $FFFF
        # if it isn't learned by leveling up from the starting one.
        words_asm("skill_pair_learns_txt", [
            whole_skill_text[h] if a in slots["actores"]
            and B.level_learned(db, a, h) > 0 and h in whole_skill_text
            else 0xFFFF for (a, h), _r in pairs], "$%04X", declare=True)
        # 254 and not 256: `eacc_skill` uses $FF for the attack and
        # `ba_enemy_action` answers $FE when it has none left.
        if len(rom_skills) > 254:
            raise SystemExit("the cartridge's skills are %d and `skill_pair_k` "
                             "is one byte" % len(rom_skills))
        # And what each actor's skills command is called in the menu.
        words_asm("actor_skill_txt", [skill_command_text.get(a, 0xFFFF)
                                    for a in range(n_actors)], "$%04X",
                  declare=True)
        # The troops some battle of the cartridge asks for, and the enemies
        # that form them. The bytecode carries the troop's **RM2k number**, so
        # `troop_id` is what the ROM looks up; the list being only that of the
        # used troops doesn't change a byte of any page. See
        # `events.Troops`.
        used = [n for n in troops if n in db.troops]
        place_of = {e: k for k, e in enumerate(rom_enemies)}
        members, starts = [], []
        for number in used:
            values = db.troops[number].members[:constants.ENEMIES_MAX]
            starts.append(len(members))
            members += [place_of[e] for e in values]
        if len(members) > 255 or len(used) > 255:
            raise SystemExit("the cartridge's troops don't fit in one-byte "
                             "tables: %d troops, %d members"
                             % (len(used), len(members)))
        words_asm("troop_id", used, declare=True)
        # The experience beating each one gives, already added up: see
        # `experience.troop_exp`. It goes outside bank 0, like
        # everything here, because it is read once per battle.
        troop_exp = [X.troop_exp(db, n) for n in used]
        for n, exp in zip(used, troop_exp):
            if exp > 0xFFFF:
                raise SystemExit("troop %d gives %d experience and the ROM "
                                 "adds it in sixteen bits" % (n, exp))
        words_asm("troop_exp", troop_exp, declare=True)
        # And the gold, the same: `battle.troop_gold`. The victory tells
        # it with `ba_vic_number`, which reaches five digits.
        troop_gold = [B.troop_gold(db, n) for n in used]
        for n, gold in zip(used, troop_gold):
            if gold > 0xFFFF:
                raise SystemExit("troop %d gives %d gold and the ROM adds it "
                                 "in sixteen bits" % (n, gold))
        words_asm("troop_gold", troop_gold, declare=True)
        # What the victory writes has to fit on its line: the ROM builds it
        # with a number or a name in the middle and doesn't split it.
        P.collect_victory(
            battle_term, max(troop_exp, default=0),
            [db.actors[a].name for a in slots["actores"] if a in db.actors],
            [db.skills[h].name for h in sorted(taught)],
            max(troop_gold, default=0),
            [db_items[i].name for i in sorted({db.enemies[e].drop_id
                                               for e in rom_enemies}
                                              - {0})])
        bytes_asm("troop_init", starts, declare=True)
        # Which members of each troop start **hidden** —the troop's
        # `invisible`—, one bit per place: a page with `ShowHiddenMonster`
        # makes them appear. It is the Rat King, who calls his rats. See
        # `BAF_HIDDEN`.
        bytes_asm("troop_hidden", [
            sum(1 << k for k, hidden in enumerate(
                db.troops[n].hidden[:constants.ENEMIES_MAX]) if hidden)
            for n in used], "$%02X", declare=True)
        bytes_asm("troop_n",
                  [len(db.troops[n].members[:constants.ENEMIES_MAX])
                   for n in used], declare=True)
        bytes_asm("troop_member", members, declare=True)
        # And the event pages of each troop, in LDB order —which is the order
        # `ScheduleNextPage` tries them in—, without the ones that didn't
        # compile: skipping them doesn't change the order of the others. Per
        # troop, where they start and how many there are; per page, its
        # trigger and where its code is inside `troop_code`, which
        # deduplicates them. See `events.TroopPages` and `ba_page_test`
        # in tools/runtime/battle_troop.s.
        #
        # **The small tables go to bank 1, `FAR`; the two big blocks —the code
        # and the messages—, to RODATA.** Until 2026-09-27 all four went to
        # bank 1, because with them in RODATA the `names_in_game` cartridge went over
        # 4 MB (measured on 2026-09-21); that cartridge no longer exists,
        # `release` is around 71%, and in bank 1 the two blocks were almost
        # eleven KB of which the battle's hand-written code didn't have even
        # four hundred bytes. Both are read with a long pointer whose bank
        # comes from `^troop_code` and `^messages_troop`, so it is enough
        # for each to fit whole in one bank, which is what `block` asks for.
        pt = troop_pages or events.TroopPages()
        entries, page_start, page_n = [], [], []
        for number in used:
            theirs = pt.per_troop.get(number, [])
            page_start.append(len(entries))
            page_n.append(len(theirs))
            entries += theirs
        if max(page_n, default=0) > events.TROOP_PAGES_MAX:
            raise SystemExit("a troop brings %d pages and the battle tracks %d"
                             % (max(page_n), events.TROOP_PAGES_MAX))
        handle.write('.segment "FAR"\n')
        words_asm("troop_page_init", page_start)
        bytes_asm("troop_page_n", page_n)
        bytes_asm("tpage_flags", [d.flags for d, _ofs in entries], "$%02X")
        words_asm("tpage_sw_a", [d.switch_a for d, _ofs in entries])
        words_asm("tpage_code", [".loword(troop_code + %d)" % ofs
                               for _d, ofs in entries], "%s")
        # The three for `switch_b` and the variable only if some page uses
        # them: the characters' 32 systems only look at `switch_a`, and with
        # none the ROM never reads them —the bit in `tpage_flags` is zero—, so
        # the label is enough. The turn and the HP have no table: they go in
        # front of the code, see `events.troop_header`.
        for name, field, bit in (
                ("tpage_sw_b", "switch_b", events.TROOP_TRIGGER_SWITCH_B),
                ("tpage_var", "ranura", events.TROOP_TRIGGER_VARIABLE),
                ("tpage_value", "valor", events.TROOP_TRIGGER_VARIABLE)):
            uses_it = any(d.flags & bit for d, _ofs in entries)
            words_asm(name, [getattr(d, field) & 0xFFFF
                             for d, _ofs in entries] if uses_it else [])
        handle.write('.segment "RODATA"\n')
        handle.write(block("troop_code", bytes(pt.bodies) or b"\x00")
                     + "\n")
        handle.write(block("messages_troop", pt.messages.bytes())
                     + "\n")
        # And the random encounters, which also talk about troops by their
        # RM2k number. They go here outside bank 0 —they are read with
        # `lda f:tabla, x`— because eighty-five bytes were left there and this
        # is about two hundred. See `rom_encounters` and
        # `tools/runtime/encounters.s`.
        enc = encounters or {"por_mapa": [0xFF] * len(maps), "registros": [],
                             "zonas": [], "tropas": []}
        bytes_asm("enc_map", enc["por_mapa"], declare=True)
        words_asm("enc_base", [r["base"] for r in enc["registros"]],
                  declare=True)
        thresholds = []
        for r in enc["registros"]:
            # Seven thresholds and one of padding: with eight the record's
            # index is a shift and not a multiplication. See ENC_STRIDE.
            thresholds += list(r["umbrales"]) + [0xFF]
        bytes_asm("enc_threshold_n", thresholds, declare=True)
        bytes_asm("enc_zone_init", [r["zona_ini"] for r in enc["registros"]],
                  declare=True)
        bytes_asm("enc_zone_n", [r["zona_n"] for r in enc["registros"]],
                  declare=True)
        for k, label in enumerate(("enc_left", "enc_arr", "enc_right",
                                   "enc_down")):
            words_asm(label, [z["rect"][k] for z in enc["zonas"]],
                      declare=True)
        bytes_asm("enc_troop_init", [z["troop_init"] for z in enc["zonas"]],
                  declare=True)
        bytes_asm("enc_troop_n", [z["troop_n"] for z in enc["zonas"]],
                  declare=True)
        words_asm("enc_troop", enc["tropas"], declare=True)
        words_asm("enemy_hp", [db.enemies[e].max_hp for e in rom_enemies],
                  declare=True)
        words_asm("enemy_atk", [db.enemies[e].attack for e in rom_enemies],
                  declare=True)
        words_asm("enemy_def", [db.enemies[e].defense for e in rom_enemies],
                  declare=True)
        words_asm("enemy_agi", [db.enemies[e].agility for e in rom_enemies],
                  declare=True)
        # The spirit and the SP: `CalcSkillEffect` asks for them, subtracting
        # `magical_rate * spi_del_blanco / 80` from the effect. Until
        # 2026-09-13 nobody read them because no computation of the battle
        # used them.
        words_asm("enemy_spi", [db.enemies[e].spirit for e in rom_enemies],
                  declare=True)
        words_asm("enemy_sp", [db.enemies[e].max_sp for e in rom_enemies],
                  declare=True)
        bytes_asm("enemy_hit", [db.enemies[e].hit for e in rom_enemies],
                  declare=True)
        # The critical hit, already as a whole percentage:
        # `CalcCriticalHitChance` computes it as `1 / critical_hit_chance`
        # times a hundred and truncates it.
        bytes_asm("enemy_crit", [
            (100 // (db.enemies[e].critical_hit_chance or 30))
            if db.enemies[e].critical_hit else 0 for e in rom_enemies],
            declare=True)
        words_asm("enemy_txt", [enemy_text[e] for e in rom_enemies],
                  declare=True)
        # Each one's experience and gold, which the victory subtracts from the
        # troop's for each enemy that stayed hidden: see `ba_no_hidden`.
        words_asm("enemy_exp", [db.enemies[e].exp for e in rom_enemies],
                  declare=True)
        words_asm("enemy_gold", [db.enemies[e].gold for e in rom_enemies],
                  declare=True)
        # What it drops on dying: the LDB item, or 0 if it drops nothing, and
        # the chance as a percentage. See `ba_vic_drop` and
        # `battle.roll_drops`. Every item that can be dropped is in
        # `items`: see `drop_items`, which adds it.
        for e in rom_enemies:
            if db.enemies[e].drop_id and db.enemies[e].drop_id not in k_of:
                raise SystemExit("enemy %d drops item %d and the "
                                 "cartridge doesn't carry it"
                                 % (e, db.enemies[e].drop_id))
        words_asm("enemy_drop", [db.enemies[e].drop_id
                                    for e in rom_enemies], declare=True)
        bytes_asm("enemy_drop_pct", [db.enemies[e].drop_prob
                                        for e in rom_enemies], declare=True)
        # What each enemy can do on its turn: its list from
        # `battle.actions_of_enemy`, contiguous in `eacc_*` —where it
        # starts and how many there are—. Per action, the skill as a `k` of the
        # `hab_*` tables or $FF for the attack, and its `rating` with bit 7 set
        # if it isn't `effective`: it counts for the maximum and then weighs
        # zero. See `ba_enemy_action` in tools/runtime/battle.s.
        eacc_start, eacc_skill, eacc_weight = [], [], []
        for e in rom_enemies:
            if len(rom_actions[e]) > B.ACTIONS_MAX:
                raise SystemExit("enemy %d brings %d actions and the ROM "
                                 "weighs %d: see `battle.ACTIONS_MAX`"
                                 % (e, len(rom_actions[e]), B.ACTIONS_MAX))
            eacc_start.append(len(eacc_skill))
            for rating, skill, effective in rom_actions[e]:
                if not 0 < rating < 0x80:
                    raise SystemExit("enemy %d brings an action with rating "
                                     "%d and the ROM carries it in seven bits"
                                     % (e, rating))
                eacc_skill.append(0xFF if skill is None
                                  else skill_place[skill.id])
                eacc_weight.append(rating | (0 if effective else 0x80))
        if len(eacc_skill) > 255:
            raise SystemExit("the actions of the cartridge's enemies are %d "
                             "and `enemy_acc_init` is one byte"
                             % len(eacc_skill))
        handle.write("ACTIONS_MAX = %d\n" % B.ACTIONS_MAX)
        bytes_asm("enemy_acc_init", eacc_start, declare=True)
        bytes_asm("enemy_acc_n", [len(rom_actions[e]) for e in rom_enemies],
                  declare=True)
        bytes_asm("eacc_skill", eacc_skill, declare=True)
        bytes_asm("eacc_weight", eacc_weight, declare=True)
        # And the battle scene: the backdrops and the battlers separately.
        # `used` is the same order as `troop_id`, which is what
        # `scene_troop_backdrop` indexes, and that of `troop_member`.
        handle.write(scenes_asm(scenes or {"fondos": [], "battlers": [],
                                           "battler_de": {},
                                           "tropa_fondo": {},
                                           "mapa_fondo": [0xFF] * len(maps)},
                                used, db))
        handle.write('.segment "TABLES"\n')
        # The product of the hit computation has to fit in sixteen bits:
        # (100 - hit rate) times the sum of both agilities. With the minimum
        # hit rate of 70 that is 30 times 1998, and the agility cap is guarded
        # by `BA_AGI_CAP`; an enemy with a lower hit rate would overflow it
        # without warning, so it stops here.
        # `recover_hp_rate * hp_max` has to fit in sixteen bits: the ROM does
        # it with the hardware multiplier, which gives a word. With the
        # percentage capped at 100 that is hp_max of up to 655, and this
        # game's actors are around 40. A fatter actor would overflow without
        # warning, so it stops here.
        for a in range(n_actors):
            max_levels = (rules.param_of(db.actors[a], "maxhp")
                          if a in db.actors else 0)
            if max_levels * 100 > 0xFFFF:
                raise SystemExit(
                    "actor %d has %d HP and the ROM's healing computation "
                    "is sized for 655" % (a, max_levels))
        for e in rom_enemies:
            if db.enemies[e].hit < 70:
                raise SystemExit("enemy %d has a hit rate of %d, and the ROM's "
                                 "hit computation is sized for 70"
                                 % (e, db.enemies[e].hit))
        handle.write(
            "TROOPS_N          = %d\n"
            "BATTLE_SEED       = $%04X\n"
            "BA_TXT_BASE       = %d\n"
            "BA_ENEMY_POS0     = %d\n"
            "BA_PARTY_POS0     = %d\n"
            "BA_MSG_POS1       = %d\n"
            "BA_MSG_POS2       = %d\n"
            "BA_ROW_BYTES      = %d\n"
            "BA_CURSOR_DX      = %d\n"
            "BA_NAME_DX        = %d\n"
            "BA_NAME_WIDTH     = %d\n"
            "BA_HP_DX          = %d\n"
            "BA_HP_NUM_DX      = %d\n"
            "BA_HP_ENEMIES     = %d\n"
            "BA_BAR_DX         = %d\n"
            "BA_HPMAX_DX       = %d\n"
            "BA_MSG_DX         = %d\n"
            "BA_PAGE_MSG_POS0  = %d\n"
            "BA_PAGE_MSG_DX    = %d\n"
            "BA_PAGE_MSG_WIDTH = %d\n"
            "TROOP_PAGE_MAX    = %d\n"
            "TPAGE_SWITCH_A    = $%02X\n"
            "TPAGE_SWITCH_B    = $%02X\n"
            "TPAGE_VARIABLE    = $%02X\n"
            "TPAGE_TURN        = $%02X\n"
            "TPAGE_ENEMY       = $%02X\n"
            "TPAGE_ACTOR       = $%02X\n"
            "TPAGE_WITH_HEADER = $%02X\n"
            "TPAGE_HEADER      = %d\n"
            % (len(used), B.BATTLE_SEED, battle_text,
               pos(P.BA_ENEMY_ROW0, 0), pos(P.BA_PARTY_ROW0, 0),
               pos(P.BA_MSG_ROW1, 0), pos(P.BA_MSG_ROW2, 0), 2 * 64,
               P.BA_CURSOR_COL * 2, P.BA_NAME_COL * 2, P.BA_NAME_WIDTH,
               P.BA_HP_COL * 2, P.BA_HP_NUM * 2, int(enemy_hp),
               P.BA_BAR_COL * 2,
               P.BA_HP_MAX_NUM * 2, 1 * 2,
               pos(P.BA_PAGE_MSG_ROW0, 0), P.BA_PAGE_MSG_COL * 2,
               P.BA_PAGE_MSG_WIDTH, events.TROOP_PAGES_MAX,
               events.TROOP_TRIGGER_SWITCH_A, events.TROOP_TRIGGER_SWITCH_B,
               events.TROOP_TRIGGER_VARIABLE, events.TROOP_TRIGGER_TURN,
               events.TROOP_TRIGGER_ENEMY, events.TROOP_TRIGGER_ACTOR,
               events.TROOP_WITH_HEADER, events.TROOP_HEADER_BYTES))
        # The audio: the battle song, the victory one and the five sound
        # effects, with the index they got from `Songs`. $FF and $FFFF mean
        # "the LDB has it turned off", which is the case of `battle_se` in
        # this game. Who sounds at which moment is in `events.BATTLE_AUDIO`,
        # taken from easyrpg-player; only the numbers travel here.
        audio = battle_audio or {}
        # The battle's audio package goes after the maps' ones, so its index
        # is how many maps the ROM carries. It is emitted here and checked by
        # the music section, which is the one that builds the list.
        #
        # Sixteen bits, and "there is none" is $FFFF: with the 328 maps of the
        # whole game the index doesn't fit in a byte, same as `map_current`.
        # See `battle_audio_load`.
        handle.write(
            "BA_SONG           = $%02X\n"
            "BA_SONG_END       = $%02X\n"
            "BA_PACKAGE        = $%04X\n"
            % (audio.get("battle_music", 0xFF),
               audio.get("battle_end_music", 0xFF),
               len(maps) if audio else 0xFFFF))
        for name, constant in (("dodge_se", "BA_SE_MISS"),
                               ("enemy_attack_se", "BA_SE_ATTACK"),
                               ("enemy_damaged_se", "BA_SE_DAMAGE_ENEMY"),
                               ("actor_damaged_se", "BA_SE_DAMAGE_ACTOR"),
                               ("enemy_death_se", "BA_SE_DEATH"),
                               ("escape_se", "BA_SE_FLEE"),
                               ("item_se", "BA_SE_ITEM")):
            handle.write("%-18s= $%04X\n"
                         % (constant, audio.get(name, 0xFFFF)))
        handle.write("BA_TXT_VICTORY2   = %d\n"
                     "BA_VIC_FINISHED_N = %d\n"
                     % (victory2_text, len(victory)))
        # The terms, by their place in `rules.BATTLE_TERMS`.
        for k, (name, _term) in enumerate(rules.BATTLE_TERMS):
            handle.write("BA_TXT_%-11s= BA_TXT_BASE + %d\n"
                         % (name.upper(), k))
        handle.write("BA_TXT_REVIVED    = %d\n" % revived_text)
        # The menu's five commands, with what the ROM needs of each one: which
        # line and which column it goes in, which term names it and whether it
        # always goes in gray. They go in tables and not in a computation
        # because since 2026-09-13 **they aren't three in a row on one line**:
        # they are the five of ABL's menu spread over two. See
        # `screens.BA_COMMANDS`.
        handle.write("BA_COMMANDS_N     = %d\n" % len(P.BA_COMMANDS))
        handle.write("BA_ITEM_COUNT_DX = %d\n" % (P.BA_ITEM_COUNT_COL * 2))
        handle.write("BA_COMMAND_USE    = %d\n" % P.BA_COMMAND_USE)
        handle.write("BA_COMMAND_ESCAPE = %d\n" % P.BA_COMMAND_ESCAPE)
        handle.write("BA_COMMAND_ATTACK = %d\n" % P.BA_COMMAND_ATTACK)
        handle.write("BA_COMMAND_DEFEND = %d\n" % P.BA_COMMAND_DEFEND)
        handle.write("BA_COMMAND_SKILL= %d\n" % P.BA_COMMAND_SKILL)
        # The skills screen: two columns with the name and the cost, and the
        # description of the one under the cursor at the very top. The
        # geometry comes from `screens.py`, like the item list's.
        handle.write(
            "SKILLS_N          = %d\n"
            "BA_SKILL_DESC_POS = %d\n"
            "BA_SKILL_POS0     = %d\n"
            "BA_SKILL_ROWS     = %d\n"
            "BA_SKILL_COLUMNS  = %d\n"
            "BA_SKILL_COLUMN_DX = %d\n"
            "BA_SKILL_NAME_DX  = %d\n"
            "BA_SKILL_NAME_WIDTH = %d\n"
            "BA_SKILL_DASH_DX  = %d\n"
            "BA_SKILL_COST_DX  = %d\n"
            "BA_SKILL_COST_DIGITS = %d\n"
            % (len(rom_skills),
               pos(P.BA_SKILL_DESC_ROW, P.BA_SKILL_DESC_COL),
               pos(P.BA_SKILL_ROW0, 0), P.BA_SKILL_ROWS, P.BA_SKILL_COLUMNS,
               P.BA_SKILL_COLUMN_DX * 2, P.BA_SKILL_NAME_COL * 2,
               P.BA_SKILL_NAME_WIDTH, P.BA_SKILL_DASH_COL * 2,
               P.BA_SKILL_COST_COL * 2, P.BA_SKILL_COST_DIGITS))
        handle.write('.segment "RODATA"\n')
        words_asm("ba_command_row", [
            pos((P.BA_MSG_ROW1, P.BA_MSG_ROW2)[f], 0)
            for _n, f, _c in P.BA_COMMANDS], declare=True)
        words_asm("ba_command_dx", [c * 2 for _n, _f, c in P.BA_COMMANDS],
                  declare=True)
        # **Two bytes.** A text index doesn't fit in one: with the 29 maps of
        # `abl` the battle's start at 273, and the one-byte table that was here
        # until 2026-09-14 emitted them anyway —`.byte 273`— for the assembler
        # to truncate them without saying anything.
        words_asm("ba_command_txt", [
            battle_text + [n for n, _c in rules.BATTLE_TERMS].index(name)
            for name, _f, _c in P.BA_COMMANDS], declare=True)
        bytes_asm("ba_command_gray", [
            1 if k in P.BA_COMMAND_UNDONE else 0
            for k in range(len(P.BA_COMMANDS))], declare=True)
        handle.write('.segment "TABLES"\n')

        glyphs = slots["items_glifos"]
        # Outside bank 0, like `item_k`: it is read with `lda f:`.
        handle.write('.segment "RODATA"\n')
        # **With the priority bit set**, since the battle draws the scene on
        # BG1: in mode 3 the PPU order leaves BG1 at priority 0 **above** BG2
        # at priority 0, so without this the backdrop would cover the letters.
        # On the other screens that use these glyphs —items, equipment, shop—
        # BG1 is off and the bit doesn't change a pixel, and in the empty
        # cells neither, because their pixels are transparent. The "goes up"
        # variant brings only the digits; the other letters fall on the white
        # ones, which nobody asks for in that color but that way the table is
        # indexed the same as the others.
        words_asm("item_glyph_cells", [
            entry(cell, False, False, priority=1)
            for gray in (T.ITEM_WHITE, T.ITEM_GRAY, T.ITEM_UP,
                         T.ITEM_RED)
            for n in range(T.ITEM_CHARS)
            for cell in glyphs[gray].get(
                chr(T.ITEM_FIRST_CHAR + n),
                glyphs[T.ITEM_WHITE][chr(T.ITEM_FIRST_CHAR + n)])],
            "$%04X", declare=True)
        handle.write('.segment "TABLES"\n')
        handle.write("\n")
        # `font_color` goes in bank 0 and not with the rest of the window:
        # the ROM reads it with `lda font_color, y`, and that mode addresses
        # the data bank. With it in RODATA it read garbage, and the text came
        # out black.
        handle.write(block("font_color", bytes(window["color"]),
                           fit=False) + "\n")
        handle.write("party_initial:\n    .byte %s\n\n"
                     % ",".join("%d" % a for a in initial_party) or "0")
        handle.write(sine_table() + "\n")
        # How many frames a character stays still after a step and after a
        # turn, per route frequency: RM2k's stop counter, in two tables of
        # nine to index with the frequency as is. They come from
        # `events.wait_after_step` and `wait_after_turn`. 0 and 1 aren't
        # compiled; they carry zero so that the table has no holes.
        handle.write("route_after_step:\n  .byte %s\n" % ",".join(
            "%d" % (events.wait_after_step(f)
                    if f >= events.ROUTE_FREQUENCY_MIN else 0)
            for f in range(events.ROUTE_FREQUENCY + 1)))
        handle.write("route_after_turn:\n  .byte %s\n\n" % ",".join(
            "%d" % (events.wait_after_turn(f)
                    if f >= events.ROUTE_FREQUENCY_MIN else 0)
            for f in range(events.ROUTE_FREQUENCY + 1)))
        handle.write(map_table(maps, labels))
        handle.write("\n\n")
        # After the map one, which already left the segment in RODATA.
        handle.write(anim_table(maps))
        handle.write("\n")
    return materials.report()


def sprite_colors_bytes(sprite):
    """The sprite palettes as CGRAM bytes.

    Each one is 16 entries: index 0 is transparent and isn't drawn, but it
    still takes its place, and the leftover ones are padded so that the next
    starts where the hardware expects it.
    """
    if not sprite:
        return b""
    out = bytearray()
    for palette in sprite[1]:
        out += cgram_word(BACKDROP).to_bytes(2, "little")
        for color in palette:
            out += cgram_word(color).to_bytes(2, "little")
        out += bytes(2 * (COLORS_PER_PALETTE - 1 - len(palette)))
    return bytes(out)


# An event in the position table: x and y in cells, both 16 bits because
# there are maps 500 cells wide.
EV_STRIDE = 4
# How many events the RAM holds. The most populated map of this game has 114
# —measured over the 328—; the converter stops if any goes over, so the number
# can't fall short silently. Each one costs six bytes of RAM between
# `ev_pos_buf` and `pick_by_ev`.
EV_MAX = 120
# How many forced routes can be running at once on events. The page that sends
# the most walking in this game moves four distinct events, and a route
# survives the end of its page, so there can be another running on top. Eight
# gives margin and costs 88 bytes of RAM.
ROUTE_EV_MAX = 12
# How many flashes can be running at once. This game's pages chain them one at
# a time —almost all wait for it to finish— so four is plenty; the converter
# can't check it because it depends on what runs when, and a missing slot
# makes the flash not show.
FLASH_MAX = 4
# How many events with a parallel page there can be at once in a map. It was
# 12 because the most loaded one was 8 —Lashe City— with eight: the four cars
# and the four that relocate them.
#
# **With `ChangeSpriteAssociation` done it is 40**, and a single map sets it:
# each obstacle of the car chase is an event with a parallel page that
# compares the car's cell with its own, and maps 49, 52 and 54 have forty each.
# They didn't count before because none of those pages compiled. Measured over
# the 328 maps with everything that is done today; the converter stops if any
# goes over.
#
# What it costs: eight bytes of `FAR_PAIR_LIST` per slot —far RAM, not the
# BSS; see `PAIR_LIST_BYTES` in `tools/runtime/far_ram.s`, which besides the
# event stores the page the refresh chose for it— and **one interpreter pass
# per frame for each one**. It is the second that has to be watched if the
# race gets slow: the first is gone, because the page stopped being resolved
# every frame.
#
# 48 times eight is 384 bytes, and from `FAR_PAIR_LIST` to `FAR_RANDOM` there
# are 508.
PARALLEL_MAX = 48
# An NPC in the ROM's RAM. It was eight bytes; the four extra are for the ones
# that walk: which event they correspond to and where their pose table is.
#
#   +0 x, +2 y   in pixels
#   +4 key       layer and Y, which is what `build_oam` compares
#   +6 tile, +7 attributes
#   +8 event     its index in the event table, or $FF if it doesn't walk
#   +9 poses     its entry in `npc_poses`, or $FF
#   +10 dir      where its page faces, for the first pose of a route
#   +11 padding, so that the slot is indexed with two shifts
NPC_STRIDE = 16
NPC_STILL = 0xFF        # in +9: this NPC doesn't walk

# The table of NPCs of the loaded map is copied to RAM, because build_oam walks
# it with an index and that addresses the data bank. The ceiling above is set
# by OAM: 128 objects fit and one is the hero, so no map can **show** more
# than 127.
#
# The number isn't that since 2026-09-06, and not by choice: the row is
# sixteen bytes, so the cap takes two kilobytes of the eight bank 0 of RAM
# has, and the RAM ran out —see `STACK` in tools/assembly/banks.py—. **The
# map with the most rows in the whole game has 99**, measured over the 328, so
# 104 leaves five of headroom and gives back 368 bytes. It can't fall short
# silently: the converter stops if any map goes over.
NPC_MAX = 104


def drawing_order(npc):
    """What an event is sorted by to draw it, from front to back.

    RM2k sorts by **highest Y, then highest X, and then highest id**. It comes
    from `Game_Character::GetScreenZ` in easyrpg-player, which builds a 64-bit
    Z with the layer on top, the Y, the X and the id at the bottom, with the
    comment right there:

        The rendering order of characters is: Highest Y, Highest X, Highest ID

    The two tie-breakers were missing. With still NPCs it barely shows —you
    need two on the same row and one covering the other— but as soon as one
    walks it changes row all the time and ties with anybody.

    The table index stands for the id: the events come sorted by id, so the
    order is the same.
    """
    return (npc["layer"], npc["y"], npc["x"], npc["event"])


def sort_key(layer, y):
    """How RM2k sorts: first the layer and only then the Y.

    A "below" event stays below the hero even if it is further forward on the
    screen, and an "above" one always covers it. Putting the layer in the high
    bits makes a single 16-bit comparison decide both things.
    """
    return (layer << 12) | (y & 0x0FFF)


# How much each opcode takes, to walk the bytecode without running it. The
# variable-length ones go with None and are measured separately.
# The bytecode walk lives in events.py, with the length table: there was a
# copy here and the one there went stale without anyone seeing it.
walk_code = events.walk_code


def map_order(args):
    """The ROM's maps, in table order and without repeats.

    It is in a function and not written three times because **the order is
    the contract**: a compiled teleport stores the index in this table, not
    the RM2k id. Two lists built differently would take the same bytecode to
    different maps.
    """
    return [args.map_id] + [m for m in (args.maps or []) if m != args.map_id]


# How many still events with continuous animation a map animates. See the
# reason —and the measured number— inside `movable_events`.
# Measured against A Blurred Line: an assumption of the engine, not a piece of
# the game's data. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
ANIMATES_STILL_MAX = 4


def movable_events(game_map, map_index, associations=()):
    """The events with a graphic that some compilable page sends walking, and
    the graphics some route changes to with command 34.

    It is needed before building the sprite bank: the ones that move have to
    get **the twelve poses** of the walking cycle, and the others the single
    one they declare. Giving them to anyone that shows up in a MoveEvent would
    be simpler and doesn't fit: there are maps with seven, and that is 1232
    sprite tiles.

    The graphics of command 34 come from the same pass and for the same
    reason: an event that changes graphic needs the twelve poses of the new
    graphic put in the cartridge, and that is decided before building the
    bank. **The order has to be the same as the real compilation's**, because
    the bytecode carries the index: what guarantees it is that both passes
    compile the same pages, with the same text block. Without `Graphics` here
    a route with command 34 wouldn't compile in this pass and would in the
    other, and the two lists would drift apart.

    The pages are compiled to find out and what was compiled is thrown away.
    It is repeated work —main() compiles them again with the real text
    block— but it isn't a repeated **rule**: the decision of what compiles is
    made by the same function both times.
    """
    graphics = events.Graphics(associations)
    pages = events.map_pages(
        game_map, map_index,
        events.Messages(), graphics=graphics)
    npcs = rm2k.collect_npcs(game_map)
    visible = {npc["event"] for npc in npcs}
    # And the ones that walk on their own with some page's own route, which
    # need the twelve poses just like the ones a MoveEvent sends walking.
    own = {p["event"] for p in pages if p.get("ruta_propia")}
    # And the still ones with continuous animation —the save point in Lashe
    # City—, which don't walk but **change column all the same**. Without the
    # twelve poses their VRAM slot would carry a single one and there would be
    # nothing to animate them with: the still ones share a slot by (CharSet,
    # index, pose) and don't have one of their own.
    with_route = (events.route_targets(pages) | own) & visible
    animated = {npc["event"] for npc in npcs
                if npc.get("animates")} & visible - with_route
    # And the cap: a still event that animates **costs a whole VRAM slot**
    # —twelve tiles— because it stops sharing that of its (CharSet, index,
    # pose) and gets the twelve poses of its own, like the walking ones. A map
    # with thirty —52 has thirty— asks for 572 sprite tiles and 384 fit.
    #
    # So a map with more than `ANIMATES_STILL_MAX` animates **none**, and not
    # some yes and some no: two equal fountains, one moving and the other
    # frozen, looks worse than both still. Measured over the 328 maps of the
    # game: 312 have four or fewer, and of the maps the ROMs carry today the
    # only one that goes over is 52.
    if len(animated) > ANIMATES_STILL_MAX:
        animated = set()
    # And the ones that turn toward the hero when it talks to them: the events
    # with some action or touch page that compiled and turns —see TURN in
    # events.py—, with the graphics of **all** their pages that turn. The
    # twelve poses of each go to the cartridge, which is where the ROM takes
    # the one facing the hero from; the refresh compares the pages' graphics
    # to know whether the turn survives a page change.
    turning = {}
    for p in pages:
        if (p["codigo"] and p.get("gira")
                and p["trigger"] in (events.TRIGGER_ACTION,
                                     events.TRIGGER_TOUCH_HERO)):
            turning[p["event"]] = set()
    for p in pages:
        if p["event"] in turning and p.get("gira") and p["grafico"]:
            turning[p["event"]].add(tuple(p["grafico"][:2]))
    return with_route | animated, list(graphics.pairs), animated, turning


def test_graphics(argument):
    """The (CharSet, index) pairs of `--test-graphic`, or () if none."""
    return tuple((charset, int(index)) for charset, index in argument or ())


def save_signature(pairs, slots_exp, n_actors):
    """Sixteen bits that change when **what each byte of the saved game
    means** changes, so that the ROM rejects one from another build.

    The size is guarded by the ROM on its own —`SAVE_BYTES`, which comes
    from the same constants—; this covers what the size doesn't see: which
    RM2k variable goes in each slot, which actor each skill pair and each
    experience slot belongs to. Two builds can carry the same number of
    variables and slot 5 be a different variable in each; then the save would
    load with the same length and everything shifted.

    It is the assignments and not the whole ROM on purpose: two builds whose
    save reads the same have to be able to share it, even if everything else
    changes.
    """
    shape = {
        "variables": sorted(events.VARIABLE_SLOT.items(), key=lambda x: x[1]),
        "items": events.ITEMS_N,
        "switches": SWITCH_BYTES,
        "actores": n_actors,
        "habilidades": [[a, h, r] for (a, h), r in pairs],
        "experiencia": slots_exp,
    }
    return zlib.crc32(json.dumps(shape).encode()) & 0xFFFF


def variables_n():
    """How many variable slots the ROM carries: at least one —a zero length
    would close the save table— and up to 256, which is what fits between
    `FAR_VARIABLES` and `FAR_ITEMS`."""
    n = max(1, len(events.VARIABLE_SLOT))
    if n > 256:
        sys.exit("%d variables don't fit in far RAM: FAR_ITEMS is "
                 "512 bytes from FAR_VARIABLES" % n)
    return n


def sine_table():
    """The sine the screen shake reads by index, for the bank."""
    out = ["; The sine at scale 127, for the screen shake: it is the same",
           "; list `SENO_SACUDIDA` builds in events.py.",
           ";",
           "; It goes outside bank 0 —`lda f:sine_shake, x`, one read per",
           "; shake frame— for the same reason as `item_k`: it is 256 bytes",
           "; and the code's bank filled up.",
           '.segment "RODATA"',
           ".block 256",
           "sine_shake:"]
    values = events.SHAKE_SINE
    for i in range(0, 256, 16):
        out.append("    .byte " + ",".join("$%02X" % (v & 0xFF)
                                            for v in values[i:i + 16]))
    # And back to bank 0: what follows —`route_after_step` and company— is read
    # with absolute indexed addressing and has to stay here.
    out.append('.segment "TABLES"')
    return "\n".join(out) + "\n"


def ev_pos_bytes(game_map):
    """Where each event of the map starts, in cells and in index order.

    The **whole** map goes and not only the events with a graphic: a forced
    route can land on an invisible one, and in fact half of this game's do.
    The ROM copies it to RAM when loading the map because a route changes it,
    and the next route on the same event starts from where it was left: there
    is a page that sends the same one walking nine times.

    The order is the table index, which is what the bytecode carries. **It
    isn't the RM2k id**: 39 maps have gaps in the numbering, and translating
    is exactly what `events.MapEvents` does.
    """
    if len(game_map.events) > EV_MAX:
        raise SystemExit("the map has %d events and the ROM's RAM holds %d"
                         % (len(game_map.events), EV_MAX))
    out = bytearray()
    for event in game_map.events:
        out += event.x.to_bytes(2, "little")
        out += event.y.to_bytes(2, "little")
    return bytes(out)


def npc_bytes(table):
    """The NPC table: NPC_STRIDE bytes for each one.

    Position on the map, the key it is sorted against the hero by, which
    sprite tile it gets, and the attribute byte already built with its
    palette. The ROM only subtracts the camera and copies it to OAM.

    The ones that walk also carry which event they correspond to and where
    their table of twelve poses is, which is what lets the ROM change their
    tile while they take a step.
    """
    out = bytearray()
    for npc in table:
        out += npc["x"].to_bytes(2, "little")
        out += npc["y"].to_bytes(2, "little")
        # The key goes with the Y in pixels, which is how the ROM computes it
        # from the hero's position. With the Y in cells, the hero's would
        # always be greater and it would always stay in front of everyone.
        #
        # And `npc["y"]` **is already in pixels**: `npc_table` converts it.
        # Multiplying it by 16 again —which is what it did here— gave a key
        # sixteen times larger than the hero's, and since `sort_key` clips to
        # twelve bits, on top of that it wrapped around. The comparison didn't
        # see it because the order **between** NPCs is fixed by the
        # converter's `sorted` and this key only decides where the hero goes
        # in: the hero had to step on an NPC for it to show, and no test did.
        out += sort_key(npc["layer"], npc["y"]).to_bytes(2, "little")
        out.append(npc["tile"] & 0xFF)
        # vhoopppN: the priority is bits 5 and 4, so the value goes shifted
        # four places. The events marked "above" go at priority 2, which is
        # the only thing left above BG2 1; the rest share priority 1 with the
        # hero, and since that layer covers them, they walk underneath.
        priority = (OBJ_PRIORITY_ABOVE
                    if npc["layer"] == rm2k.LAYER_ABOVE
                    else OBJ_PRIORITY)
        out.append(priority | ((npc["palette"] & 0x07) << 1)
                   | ((npc["tile"] >> 8) & 0x01))
        # The event's index goes **always**, even if the NPC doesn't walk: it
        # is the last tie-breaker of the drawing order, and it applies to all.
        # What sets the walking ones apart is the pose table.
        out.append(npc["event"])
        out.append(NPC_STILL if npc["poses"] is None else npc["poses"])
        # Where its page faces. A forced route that hasn't given any turning
        # command yet leaves it facing here, which is where the first pose
        # drawn comes from.
        out.append(npc["dir"])
        out.append(0)               # padding
        # +12: the pose that is in VRAM, which on loading is its page's. The
        # ROM compares it with the one it wants to draw and uploads the new
        # one if it differs.
        out.append(npc["pose"])
        # +13: its page's speed, for a forced route on it, and in bit 7
        # whether it is a still one with continuous animation. They go
        # together because the row has no free byte —+11 is used by the
        # jump— and because both are read by the same computation: how many
        # frames between column changes comes from the speed. See
        # `animate_still` in tools/runtime/animated_stills.s.
        out.append(npc["speed"] | (0x80 if npc.get("animates") else 0))
        # +14: whether it is drawn. An event whose active page has no graphic
        # is in the table hidden, to appear when another page wins.
        out.append(1 if npc["visible"] else 0)
        # +15: the passage bits its tile imposes on the cell, or $FF: see
        # `rm2k.event_tile_passability`. The refresh redoes both.
        out.append(0xFF if npc["tile_pass"] is None else npc["tile_pass"])
    assert len(out) == NPC_STRIDE * len(table)
    return bytes(out)


def pointer(dest):
    """The three bytes of a symbolic pointer, for `.byte`."""
    return "<(%s), >(%s), ^(%s)" % (dest, dest, dest)


def npc_poses_asm(number, animated, global_index):
    """The pointers to the twelve poses of each character that changes pose.

    One entry per animated character —`k`, the same index the NPC's row
    carries in +9 and the actor in its table— and in each one twelve 24-bit
    pointers to its poses, `pose_N`. They are symbolic because they point to
    blocks the linker places, like the pages' ones; two equal poses are the
    same block.
    """
    out = [".block %d" % (3 * SPRITE_POSES * max(1, len(animated))),
           "npc_poses_%d:" % number]
    for pair in animated:
        for pose in range(SPRITE_POSES):
            out.append("    .byte " + pointer(global_index[pair][pose]))
    if not animated:
        out.append("    .byte $00")     # a label can't be left empty
    return "\n".join(out)


def actor_table_asm(number, actors, animated, global_index):
    """The leader candidates: id, palette, and the pointer to each of their
    poses.

    ACTOR_BYTES per actor. The ROM walks the table looking for the id of the
    party's first; there are two or three entries, so searching linearly is
    cheaper than indexing by id, which would take 256 gaps. An actor without
    a graphic carries twelve pointers at $FFFFFF, which is the sentinel
    `place_hero` looks at.
    """
    out = [".block %d" % (ACTOR_BYTES * max(1, len(actors))),
           "actor_table_%d:" % number]
    for actor, palette, k, colors in actors:
        out.append("    .byte $%02X, $%02X" % (actor & 0xFF, palette & 0x07))
        # Its fifteen colors, in the order its poses index them. An actor
        # without a graphic carries them at zero and the ROM doesn't upload
        # them: it isn't drawn.
        words = list(colors) + [0] * (OBJ_COLORS - len(colors))
        out.append("    .byte " + ",".join(
            "$%02X,$%02X" % (w & 0xFF, w >> 8) for w in words))
        for pose in range(SPRITE_POSES):
            if k is None:
                out.append("    .byte $FF, $FF, $FF")
            else:
                out.append("    .byte " + pointer(
                    global_index[animated[k]][pose]))
    if not actors:
        out.append("    .byte $00")
    return "\n".join(out)


def flags_parser():
    """The converter's flags. Separate from `main` for whoever needs to read a
    command line without converting anything."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Mandatory, but without `required`: `test_cases` reads the flags of
    # each `--case` again with this same parser, and there it doesn't go.
    # `main` enforces it.
    parser.add_argument("--map-id", type=int, default=None,
                        help="the boot map, which goes first in the "
                             "table. Mandatory and with no default: it "
                             "belongs to the game, and its project file "
                             "declares it")
    project.add_argument(parser)
    # No default, and no `required` for the same reason as `--map-id`:
    # `environment` enforces them when they are read.
    environment.add_arguments(parser, "game_dir", "rtp_dir", "soundfont",
                              "cache")
    parser.add_argument("-o", "--output",
                        default=os.path.join(project.build(), "inc", "mapdata.inc"))
    parser.add_argument("--msu",
                        help="where to write the .msu with the data the\n"
                             "MSU-1 serves to the ROM: next to the .sfc and\n"
                             "with its name, so the emulator finds it.\n"
                             "Without this, datos.msu next to --output")
    parser.add_argument("--text-padding", type=int, default=0,
                        help="dead texts after the item ones, so that\n"
                             "the battle's indices go past 255 without\n"
                             "building a twenty-nine-map cartridge. It\n"
                             "doesn't change a pixel, and that is why they\n"
                             "don't go first: item k's name is text 3k")
    parser.add_argument("--no-title", action="store_true",
                        help="without the game's title screen and its "
                             "start and load menu: the ROM boots straight "
                             "into the map. It is what the regression "
                             "suite's cartridges ask for: the title screen "
                             "would add frames to the boot, and the cases "
                             "compare frames counted from reset.")
    parser.add_argument("--measure-headroom", type=float, metavar="HEADROOM",
                        help="the same headroom for every song, instead of "
                             "the volume ceiling table: it is what "
                             "`tools/audio/ceilings.py` builds the ROM where it "
                             "measures each song's peak with. See "
                             "`read_ceilings` in tools/audio/snes_music.py")
    parser.add_argument("--enemy-hp", action="store_true",
                        help="the battle shows the enemies' HP, which RM2k "
                             "never shows: for debugging. It is asked for by "
                             "`[debug] enemy_hp` of the project file")
    parser.add_argument("--no-timer", action="store_true",
                        help="the timer digits —eleven glyphs of the System "
                             "image at the end of the sprite bank, which "
                             "share a palette with a character— only in the "
                             "maps where a case that uses them runs, and not "
                             "in all. It is what the suite's cartridges ask "
                             "for: see `args.timer_en`")
    parser.add_argument("--test-graphic", nargs=2, action="append",
                        default=None, metavar=("CHARSET", "INDEX"),
                        help="puts this graphic in the sprite bank of the\n"
                             "maps where some case runs, so that the test\n"
                             "page can change someone's graphic with\n"
                             "command 34 or with ChangeSpriteAssociation.\n"
                             "It can be repeated. No page that compiles\n"
                             "today changes graphic, so without this\n"
                             "nothing runs that path")
    parser.add_argument("--test-encounters", type=int, default=None,
                        metavar="STEPS",
                        help="every how many steps there is a random "
                             "encounter, for every map of the cartridge. "
                             "Without this the game tree's value applies, "
                             "which goes from 25 to 85 steps; 0 turns them off")
    parser.add_argument("--hero-above", action="store_true",
                        help="the hero at object priority 2, above the "
                             "layer that should cover it. It is the only "
                             "way to exercise it: the game's only above "
                             "event never gets to step on the upper layer")
    parser.add_argument("--party", nargs="+", type=int, default=None,
                        metavar="ACTOR",
                        help="the party it starts with, by actor ids. The "
                             "hero's graphic is the first one's, which is how "
                             "RM2k decides it. By default, the database's: "
                             "this game starts with actor 10, DummyHero, whose "
                             "sprite is an empty cell on purpose")
    parser.add_argument("--test-commands", default=None,
                        metavar="FILE",
                        help="this case's test page, as the command list of "
                             "an RM2k page in Ditto's JSON —see "
                             "rom/pruebas/casos/—. It is compiled by the same "
                             "path as a page of the game, with the context of "
                             "the map where it runs: that of its Teleport if "
                             "it starts with one, and otherwise the boot "
                             "map's")
    parser.add_argument("--charset", default=None,
                        help="force the hero's CharSet; by default it comes "
                             "from the party's first, which is how RM2k "
                             "decides it")
    parser.add_argument("--charset-index", type=int, default=None,
                        help="which of the CharSet's 8 characters")
    parser.add_argument("--maps", nargs="+", type=int, metavar="ID",
                        help="other maps to put in the same ROM. The one "
                             "from --map-id goes first in the table")
    parser.add_argument("--start-index", type=int, default=0, metavar="N",
                        help="which table index the ROM boots at. It serves "
                             "to test a map other than the first, which is "
                             "the only case where the record's offset isn't "
                             "zero")
    return parser


def main():
    project.from_command_line()
    parser = flags_parser()
    argv, stretches = split_cases(sys.argv[1:])
    args = parser.parse_args(argv)
    if args.map_id is None:
        parser.error("--map-id is missing, the boot map")
    environment.from_arguments(args, "game_dir", "rtp_dir", "soundfont",
                               "cache")
    args.game_dir = environment.game()
    args.cases = test_cases(parser, args, stretches)
    order = map_order(args)
    if not 0 <= args.start_index < len(order):
        sys.exit("--start-index %d but there are %d maps" % (args.start_index, len(order)))
    for case in args.cases:
        case.run_map = case_map(case, order, args.start_index)
    file_commands = case_commands(args)
    # Which maps carry the timer digits, which cost a sprite palette.
    # Normally, all: it is what the game asks for, where the countdown starts
    # in one map and is seen in the following ones. With `--no-timer`, the
    # maps where a case that touches it runs: until step 9e one was enough for
    # every map of the cartridge to carry them, and in the single cartridge of
    # 9f that took the palette away from every map —measured, fifteen goldens
    # moved—. A map without digits doesn't draw them: `TIMER_BASE` at zero,
    # see `timer_oam`.
    args.timer_maps = set(order) if not args.no_timer else {
        case.run_map for case in args.cases
        if any(cmd.code == events.TIMER_OPERATION for cmd in case.commands)}

    renderer = Renderer(args.game_dir)

    # The hero's graphic comes from the party, not from here. In RM2k the
    # first of the list gives it, and this game starts with actor 10
    # —'DummyHero', which is Chubby2[2]—. Until now there was a hand-set
    # default that gave Future1[0], that is another character's sprite.
    # --charset stays to force it by hand when needed.
    party = args.party if args.party else renderer.database.party
    if args.charset is None:
        args.charset, table_index = renderer.database.leader(party)
        if args.charset_index is None:
            args.charset_index = table_index
    if args.charset_index is None:
        args.charset_index = 0

    # The leader candidates are computed with all the ROM's maps together,
    # because the party is global state: a page of map A can add someone who
    # then walks around map B.
    args_game_dir[0] = args.game_dir
    every = map_order(args)
    # **The indices go before anything that compiles a page**, and
    # `possible_leaders` compiles pages. They were after, and the price was
    # concrete: without `index_variables`, no `ControlVars` compiles, so
    # `RaceController1` of map 49 —which starts with a `PlayBGM` and goes on
    # with two `ControlVars`— didn't compile **in that pass** and did in the
    # real one. The actors it adds to the party were lost: `CarRED` didn't go
    # into the map's actor table and the chase's hero was drawn **with no
    # graphic**, that is the car wasn't visible. It is the same hole that was
    # already noted for the page counts, in another place.
    #
    # The variables of the whole game, with their slot.
    extra = events.command_variables(file_commands)
    if len(args.cases) > 1:
        # The one that picks the case: see `events.CASE_VARIABLE`. With a
        # single one it isn't needed, and that way that cartridge comes out
        # the same as before `--case`.
        extra.add(events.CASE_VARIABLE)
    events.index_variables(args.game_dir, extra)
    # And the battle animations, which `ShowBattleAnimation` compiles with its
    # timeline inside: see OP_ANIMATION.
    events.index_animations(args.game_dir)
    # And the common events, which `CallEvent` compiles in place.
    events.index_common_events(args.game_dir)
    events.index_battle_audio(args.game_dir)
    # And the inn terms, which `ShowInn` builds its greeting with.
    events.index_terms(args.game_dir)
    # And the equipment and skills of each actor of the LDB: it is what the
    # two actor branches with two operands answer. **Before
    # `possible_leaders`**, which compiles pages: see its comment.
    events.index_actors(args.game_dir)
    # And the (actor, skill) pairs of the whole game, with those of the test
    # pages: it is the operand of `ChangeSkills` and of the branch that asks
    # whether it knows one, so it goes before compiling anything, same as the
    # variables.
    events.index_skills(
        args.game_dir, events.command_skill_pairs(file_commands))
    args.leaders = possible_leaders(renderer, every, party)
    # And those of the party each test page continues with, behind: the test
    # can start with it in any map of the cartridge.
    for case in args.cases:
        test_party = page_party(case, party)
        if test_party:
            for actor in possible_leaders(renderer, every, test_party):
                if actor not in args.leaders:
                    args.leaders.append(actor)
    # If some map sets rain, all of them carry the drops: see `has_rain`.
    args.with_rain = has_rain(every, file_commands)
    # How many maps of this ROM each character appears in. The palette split
    # uses it to choose who can lose a color without breaking anything: the
    # pose bank is **the whole ROM's**, so a character that is in two maps has
    # to be quantized the same in both. Quantizing it differently doesn't give
    # an ugly image but a `sys.exit` when emitting, which is what happened the
    # first time this was written: `Future1:4` dropped in one map and not in
    # the other.
    args.maps_per_character = maps_per_character(renderer, every,
                                                 args.game_dir)
    # The `ShowPicture` picture, one per ROM: see `events.Pictures`. The first
    # map of the table that shows it keeps it, which is the order `convert_map`
    # walks them in.
    args.pictures = events.Pictures(args.game_dir)
    args.pictures.map_id = None
    # And the slots `ChangeSpriteAssociation` reserves in the graphics table
    # of **all** maps, for the same reason as the picture: the graphic it gives
    # an actor crosses the teleport, so its index has to mean the same in both
    # maps. See `events.sprite_associations`.
    #
    # The test pages' ones come in through the same door: if they went by
    # `--test-graphic` they would have an index only in the maps where a
    # case runs, and what the command does —crossing the teleport— couldn't
    # be tested.
    args.associations = events.sprite_associations(
        [lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % m))
         for m in every], file_commands)

    precompute_layers(renderer, every, args)
    maps = [convert_map(renderer, map_id, args) for map_id in every]
    # The maps whose upper layer started higher than the window's palette used
    # to be reconverted here, to squeeze their background below it. With the
    # window in palette 0 there is nothing to squeeze: each map's background
    # starts at `CGRAM_RESERVED` and reaches up to its own upper layer,
    # without depending on what the other maps of the ROM need.
    # Teleports are resolved when all the maps are there: one can lead to any
    # other, so the destination index isn't known until the end.
    indices = {map_info["id"]: number for number, map_info in enumerate(maps)}

    # The blocks the map's `TileSubstitution`s are going to need, built
    # **before** compiling any page: see `Substitutions`. A map without that
    # command builds nothing and doesn't grow a byte, which is the case of the
    # game's 328 maps as of today.
    for map_info in maps:
        chipset = renderer.database.chipsets[map_info["game_map"].chipset_id]
        map_info["sustituciones"] = Substitutions(
            map_info, build_passability(chipset), chipset)
        # It hangs from the map so it reaches `events.MapEvents`, which is what
        # the compiler already passes around.
        map_info["game_map"].substitutions = map_info["sustituciones"]
        triples = substitution_triples(map_info["game_map"], args.cases,
                                       map_info["id"])
        for absent in map_info["sustituciones"].close(triples):
            # It doesn't stop the conversion: the page that asks for it
            # doesn't compile, which is what any command that can't be run
            # does. But it is said, because from outside it looks like an
            # event that does nothing.
            #
            # The two reasons a substitution can't be built, and both are
            # fixed on the data side: either the new tile isn't drawn in any
            # cell of the map —and then its 8x8s didn't go into VRAM—, or the
            # combination that would be needed carries an upper tile **without
            # the "Above" bit**, which isn't drawn on BG2 but baked into the
            # background, and then the block's two layers stop being
            # independent. See `Substitutions._bakes`.
            print("  map %d: TileSubstitution %d -> %d on the %s layer: the "
                  "block that would be needed can't be built. Either the new "
                  "tile isn't drawn in any cell of the map, or one of the two "
                  "is an upper tile without 'Above' and is baked into the "
                  "background. The page doesn't compile."
                  % (map_info["id"], absent[1], absent[2],
                     "upper" if absent[0] else "lower"))

    # The text block belongs to the whole ROM and is built while the pages
    # are compiled: each `ShowMessage` leaves its text here and takes an
    # offset, which is what goes in the bytecode.
    messages = events.Messages(step=events.MESSAGES_STEP)
    # The songs the pages' PlayBGMs ask for, numbered in the order they
    # appear. The ROM carries a single one —see `Songs`— and picks it further
    # down, when all are compiled and it is known which ones are asked for.
    songs = events.Songs()
    # And the troops the EnemyEncounters ask for. It doesn't number anything
    # —the bytecode carries the RM2k id— so it only says which enemy tables
    # have to be emitted. See `events.Troops`.
    troops = events.Troops()
    # The test pages' texts go **first**, before all the maps, and that isn't
    # aesthetic: that way their offset doesn't depend on how many texts the
    # map the ROM boots in brings nor on the order they are compiled in —the
    # first is 0—. They are stored here and the page's compilation, further
    # down, finds them stored, because the block deduplicates by content.
    for cmd, extra_lines in events.group_boxes(file_commands):
        if cmd.code == events.SHOW_MESSAGE:
            messages.add([cmd.string] + extra_lines)
    # The test pages already compiled, per case: see the second round.
    test_party = {}

    for map_info in maps:
        # The automatic events: their pages with the conditions, and the code
        # of the ones that can be run, all together in a single block.
        # One graphics registry per map: command 34 carries the index and the
        # map's `ruta_grafico` table resolves it. See `events.Graphics`.
        graphics = events.Graphics(args.associations)
        songs.current_map = maps.index(map_info)      # for its audio package
        pages = events.map_pages(map_info["game_map"], indices.get,
                                 messages, songs, graphics,
                                 args.pictures, troops)
        songs.current_map = None
        # One interpreter per event with some parallel page that compiles. The
        # ROM carries them in a fixed-cap list and **doesn't warn** if it goes
        # over —the extra ones wouldn't run and nothing would say so—, so the
        # stop goes here.
        with_parallel = {p["event"] for p in pages
                         if p["trigger"] == events.TRIGGER_PARALLEL
                         and p["codigo"]}
        if len(with_parallel) > PARALLEL_MAX:
            sys.exit("map %d has %d events with a parallel page and %d "
                     "fit: see PARALLEL_MAX"
                     % (map_info["id"], len(with_parallel), PARALLEL_MAX))
        if with_parallel:
            print("  map %d: %d event(s) with a parallel page"
                  % (map_info["id"], len(with_parallel)))
        if args.test_graphic and map_info["id"] in test_maps(args):
            for charset, index in test_graphics(args.test_graphic):
                graphics.index(charset, index)
        # **Only the map that took its tiles can show the picture.** The sprite
        # bank belongs to each map, so from another one the six objects would
        # read whatever was in those tiles. It doesn't happen today —the "1
        # year earlier" picture is shown by a single page— and that is why this
        # stops instead of choosing: the day two maps show the same one, it
        # has to be decided whether its tiles go in both, and the converter
        # can't make that decision alone.
        if (args.pictures.name is not None
                and map_info["id"] != args.pictures.map_id):
            for test_page in pages:
                code = test_page["codigo"]
                if code and any(code[i] == events.OP_PICTURE
                                for i, _c in events.walk_code(code)):
                    sys.exit(
                        "map %d: shows the picture %r and its tiles ended up in "
                        "map %d; the ROM carries it in a single one. See "
                        "`cartel_de_imagen`."
                        % (map_info["id"], args.pictures.name,
                           args.pictures.map_id))
        if graphics.pairs != map_info["graficos_de_ruta"]:
            # The two passes compiled different things. It can't happen —both
            # use `map_pages` with the same text block— and if it did,
            # the bytecode would end up pointing at the wrong table without
            # anything saying so.
            sys.exit("map %d: the two passes numbered the route graphics "
                     "differently: %s against %s"
                     % (map_info["id"], graphics.pairs, map_info["graficos_de_ruta"]))
        # The pages of the cases that run in this map, compiled with its
        # context even though they will live in the boot map: see
        # `case_map`. They are put there in the second round, when all
        # are done.
        for k, case in enumerate(args.cases):
            if case.run_map == map_info["id"]:
                test_party[k] = case_page(case, map_info, songs, graphics,
                                          messages, indices,
                                          args.pictures)
        map_info["pages"] = pages
        # And which maps outside the ROM the ones that don't compile point to.
        #
        # A `Teleport` to a map that didn't make it cuts the whole page, and a
        # page that doesn't compile does **nothing**: neither the teleport nor
        # what came before. `event` has always said so in its comment, but
        # the count above doesn't tell this reason apart from the others a
        # page falls out for, and it is the only one that is fixed from
        # outside —adding the map— and not by touching the compiler. That is
        # how the elevator page of map 2 was overlooked, which was seen
        # opening and led nowhere because it ends up jumping to map 3.
        outside_of, how_many = set(), 0
        for test_page in pages:
            if test_page["codigo"] or test_page["trigger"] not in events.TRIGGERS \
                    or test_page.get("prueba"):
                continue        # the test page doesn't come from the game
            event = map_info["game_map"].events[test_page["event"]]
            missing = {cmd.parameters[0]
                       for cmd in event.pages[test_page["pagina"]].commands
                       if cmd.code == events.TELEPORT and cmd.parameters
                       and indices.get(cmd.parameters[0]) is None}
            if missing:
                outside_of |= missing
                how_many += 1
        if outside_of:
            print("  map %d: %d of those %s because of a teleport to a map "
                  "that didn't make it into the ROM: %s"
                  % (map_info["id"], how_many,
                     "doesn't compile" if how_many == 1 else "don't compile",
                     ", ".join(str(m) for m in sorted(outside_of))))
        # Debts are warned about. A page that is accepted without doing
        # everything it asks for is a difference from the original game, and
        # keeping quiet about it is how it becomes invisible: here the command
        # and what is lost are named.
        debts = set()
        for event in map_info["game_map"].events:
            for page in event.pages:
                if page.trigger != events.TRIGGER_AUTOSTART:
                    continue
                # With the same text block as above: if it were None here, a
                # page with a text box wouldn't compile and its debt —a
                # PlayBGM, say— would go unwarned even though the ROM does run
                # it. Adding a text that is already there again doesn't grow
                # the block: the key is the content.
                if events.compile_page(page, indices.get,
                                       messages) is None:
                    continue
                debts |= set(events.page_debts(page,
                                               args.pictures))
        for cmd_code in sorted(debts):
            print("  map %d: WARNING, a page uses %s and the ROM doesn't do it; "
                  "see ACCEPTED_UNDONE in tools/port/events.py"
                  % (map_info["id"], event_codes.EVENT_CODES.get(cmd_code,
                                                                 cmd_code)))


    # The second round: with the pages of all the cases compiled, they are
    # put in the boot map and each map's block is built.
    for map_info in maps:
        pages = map_info["pages"]
        if args.cases and map_info is maps[args.start_index]:
            # The test pages, only in the map the ROM boots in. They don't come
            # from the game but from `rom/pruebas/casos/`: they exist because
            # there are interpreter paths no page of the game that compiles
            # exercises —the first was a wait—.
            #
            # It goes at **index 0**, that of the empty event `convert_map` put
            # at the start of the map: the ROM walks the events from lowest to
            # highest, and this page has to run before the game's. Until
            # 2026-09-17 it went at the first free index, at the end.
            #
            # **One page per case**, and page k asks for `CASE_VARIABLE` to
            # be at least k: see its comment. Page 0 asks for nothing, so a
            # single-case cartridge is the usual one.
            pages = pages + [{
                "event": 0, "pagina": k, "prueba": True,
                "trigger": events.TRIGGER_AUTOSTART,
                "switch_a": 0, "switch_b": 0, "actor": 0,
                "variable": ((events.variable_slot(
                    events.CASE_VARIABLE),
                    events.COMPARE_AT_LEAST, k) if k else None),
                "item": 0, "capa": 0,
                "frecuencia": events.ROUTE_FREQUENCY, "speed": 4,
                "codigo": test_party[k]} for k in range(len(args.cases))] + [{
                # And the one that turns it off: it asks for
                # `TEST_SWITCH` and has no code, so as soon as it wins,
                # the invented event no longer has an automatic page to run and
                # the first one doesn't repeat.
                "event": 0, "pagina": len(args.cases), "prueba": True,
                "trigger": events.TRIGGER_AUTOSTART,
                "switch_a": events.TEST_SWITCH, "switch_b": 0,
                "actor": 0, "variable": None, "item": 0, "capa": 0,
                "frecuencia": events.ROUTE_FREQUENCY, "speed": 4,
                "codigo": b""}]
        code = bytearray()
        for test_page in pages:
            test_page["offset"] = len(code)
            if test_page["codigo"]:
                code += test_page["codigo"]
            # And the commands of the own route, behind, one byte per command.
            own = test_page.get("ruta_propia")
            if own:
                test_page["ruta_offset"] = len(code)
                code += bytes(own["ordenes"])
        map_info["pages"] = pages
        # What each page of the events that change graphic draws, already as
        # OAM wants it: it is what the ROM copies to the NPC's row when the
        # active page changes. See `page_table`, +20.
        for test_page in pages:
            continues = test_page["event"] in map_info["cambian"]
            if not continues and test_page["event"] not in map_info["aparecen"]:
                continue
            graphic = test_page.get("grafico")
            if graphic is None \
                    or graphic[:2] in map_info["afuera"].get(test_page["event"], ()):
                continue
            if not continues:
                # The one that only appears carries no tile or attributes: its
                # own point to its slot of twelve poses and the ROM doesn't
                # touch them. The pose goes —with bit 7, which is "this page
                # draws something"— and what its tile imposes on the cell.
                test_page["oam"] = (0, 0, graphic[2] | 0x80,
                                 0xFF if test_page.get("tile_pass") is None
                                 else test_page["tile_pass"])
                continue
            block, slot = map_info["where"][graphic]
            tile = block_tile(block)
            priority = (OBJ_PRIORITY_ABOVE
                        if test_page["capa"] == rm2k.LAYER_ABOVE
                        else OBJ_PRIORITY)
            test_page["oam"] = (tile & 0xFF,
                             priority | ((slot & 0x07) << 1) | ((tile >> 8) & 1),
                             graphic[2] | 0x80,
                             0xFF if test_page.get("tile_pass") is None
                             else test_page["tile_pass"])
        map_info["evcode"] = bytes(code)
        # The ROM's substitution table has a fixed cap and **doesn't warn** if
        # it goes over: the pairs that don't fit wouldn't be applied and the
        # map would draw too much. How many entries it can end up having is
        # known here, and it is the number of distinct blocks some substitution
        # of the map uses as a key, because a key is never overwritten: the
        # second round changes its value. See `op_tile_sub` in
        # tools/runtime/interpreter_map.s.
        keys = len(map_info["sustituciones"].known_keys)
        if keys > SUB_MAX:
            sys.exit("map %d substitutes %d distinct blocks and the RAM "
                     "table carries %d: see SUB_MAX"
                     % (map_info["id"], keys, SUB_MAX))
        # How many distinct events this map can end up sending walking. The
        # ROM has ROUTE_EV_MAX slots and a route that finds no room is
        # discarded **without saying anything**: the NPC stays still and, if
        # the golden is taken like that, the test defends the error. With this
        # game's data the worst map uses two, so the check bothers nobody; it
        # is there so that a future change doesn't throw them away silently.
        #
        # The pages that **run** here: the map's and those of the cases that
        # jump to it, which live in the boot one. See `case_map`.
        run_here = [p["codigo"] for p in pages
                    if p["codigo"] and not p.get("prueba")]
        run_here += [test_party[k] for k, case in enumerate(args.cases)
                     if case.run_map == map_info["id"]]
        targets = {c[i + 1] for code in run_here
                   for i, c in walk_code(code)
                   if c[i] == events.OP_ROUTE and c[i + 1]}
        # And that nobody flashes someone who shares a graphic with another.
        # On the console the flash is done on the character's palette, so two
        # that share a graphic would flash together. `events.py` already
        # rejects the case of two events; here the one it can't see there is
        # covered, which is the hero's: which graphic it has depends on the
        # party, and the converter knows that and the compiler doesn't.
        #
        # `separate_from_hero` already avoids this in the maps whose pages flash
        # the hero. This stays for what that one doesn't see: a `FlashSprite`
        # that arrives inside a common event, which is compiled in place from
        # any `CallEvent` and isn't in the map's pages.
        graphics = collections.Counter(
            (npc["charset"], npc["index"])
            for npc in rm2k.collect_npcs(map_info["game_map"]))
        for actor in args.leaders:
            a = renderer.database.actors[actor]
            graphics[(a.charset, a.charset_index)] += 1
        for code in run_here:
            for i, c in walk_code(code):
                if c[i] != events.OP_FLASH or c[i + 1] != 0:
                    continue
                for actor in args.leaders:
                    a = renderer.database.actors[actor]
                    if graphics[(a.charset, a.charset_index)] > 1:
                        raise SystemExit(
                            "map %d: a page makes the hero flash, and "
                            "actor %d is drawn with %s[%d], which an NPC of "
                            "the map also uses. On the console they share a "
                            "palette and both would flash"
                            % (map_info["id"], actor, a.charset, a.charset_index))

        if len(targets) > ROUTE_EV_MAX:
            raise SystemExit(
                "map %d: its pages send %d distinct events walking and "
                "the ROM has %d route slots"
                % (map_info["id"], len(targets), ROUTE_EV_MAX))
        runnable = sum(1 for p in pages if p["codigo"])
        if pages:
            print("  map %d: %d automatic event page(s), %d runnable"
                  % (map_info["id"], len(pages), runnable))

    if not 0 <= args.start_index < len(maps):
        sys.exit("--start-index %d but there are %d maps" % (args.start_index, len(maps)))
    from port import window as window_mod
    skin = window_mod.skin(args.game_dir, renderer.database.system_name)
    font_id = renderer.database.font_id
    window_data = convert_window(skin, font_id)
    window_data["fuente"] = font_bytes(font_id)
    window_data["mensajes"] = messages.bytes()
    print("  message window: %d fixed tiles + %d of text, %d colors; "
          "font %d B, %d text box(es) in %d B"
          % (len(window_data["tiles"]) // 32,
             len(window_data["fondo"]) // 32,
             sum(1 for w in window_data["cram"] if w),
             len(window_data["fuente"]), len(messages.texts),
             len(window_data["mensajes"])))
    # The slots screen goes in every ROM: the save point opens it from inside
    # the game, and "Resume the Story" from the title when there is one. It is
    # drawn with the same font and the same skin as the message window, and
    # lives in the title's VRAM, where there is no map.
    # The actors that can be in the party when saving, to have their face and
    # their name in the cartridge: the starting ones and all the ones some
    # `ChangePartyMembers` of these maps adds, whether their pages compile or
    # not. It is a superset on purpose: one face too many costs 36 tiles and
    # one too few leaves a hole in the menu.
    members = possible_members(every, party, file_commands)
    # And the items that can be in the inventory, to carry their name and
    # their description: see "la pantalla de ítems" in menus.py.
    items_rom = possible_items(every, members, renderer.database,
                               file_commands)
    # With the letters of the medicines, which the actor choice writes with
    # the bank's glyphs: see `TARGET_WINDOWS`.
    medicine_letters = "".join(
        renderer.database.items[n].name for n in items_rom
        if renderer.database.items[n].type == lcf.ITEM_TYPE_MEDICINE)
    (slot_tiles, slot_palettes, slot_headers, slot_rows, slot_faces,
     slot_menu) = menus_mod.slots_screen(
        skin, renderer.database, SLOTS, renderer.database.font_id,
        members, args.game_dir, medicine_letters)
    target = menus_mod.borders(
        skin, 0, menus_mod.target_layers(skin, renderer.database,
                                           renderer.database.font_id),
        menus_mod.TARGET_CGRAM,
        menus_mod.TARGET_CGRAM + menus_mod.TARGET_COLORS_MAX)
    _check_target(len(target[0]))
    items_tiles, items_palettes, items_glyphs = menus_mod.items_screen(
        skin, renderer.database.font_id)
    # The item and equipment windows share tiles and colors: see
    # `menus.borders`.
    items_border = menus_mod.borders(
        skin, items_border_first(len(items_tiles)),
        [menus_mod.item_layers(skin), screens_mod.equipment_layers(skin)])
    _check_items_border(len(items_tiles), len(items_border[0]))
    # The shop's, with their own tiles and colors: see
    # `screens.TI_WINDOWS`.
    shop_border = menus_mod.borders(
        skin, 0, screens_mod.shop_layers(skin),
        menus_mod.ITEM_BORDER_CGRAM, menus_mod.TARGET_CGRAM)
    _check_shop(len(shop_border[0]))
    # The End Game screen's tiles go where the slots' do, so what is checked
    # is the same.
    end = end_game_mod.convert(skin, renderer.database, renderer.database.font_id)
    _check_slots(len(end[0]))
    slots_data = {"tiles": slot_tiles, "paletas": slot_palettes,
                  "cabeceras": slot_headers, "filas": slot_rows,
                  "caras": slot_faces,
                  "menu": slot_menu, "items": items_rom,
                  "db": renderer.database, "actores": members,
                  "relleno_textos": args.text_padding,
                  "items_db": renderer.database.items,
                  "items_tiles": items_tiles,
                  "items_paletas": items_palettes,
                  "items_glifos": items_glyphs,
                  "items_marco": items_border, "fin": end,
                  "tienda_marco": shop_border,
                  "objetivo": target}
    _check_slots(len(slot_tiles))
    _check_splits()
    print("  slots screen: %d, %d 4bpp tiles (%d B) + %d palettes, "
          "%d B of cells; %d actors with a face: %s"
          % (SLOTS, len(slot_tiles), len(slot_tiles) * 32,
             len(slot_palettes),
             (len(slot_headers) * len(slot_headers[0])
              + SLOTS * 4 * len(slot_rows[0][0][0])) * 2,
             len(slot_faces),
             ", ".join("%d %s" % (a, renderer.database.actors[a].name)
                       for a in sorted(slot_faces)) or "none"))
    title_data = None
    if not args.no_title:
        from PIL import Image
        name = renderer.database.title_name
        picture = Image.open(os.path.join(args.game_dir, "Title",
                                          name + ".png"))
        texts = title_mod.options(renderer.database)
        menu_tiles, menu_palette, menu_maps = title_mod.menu(
            skin, texts, renderer.database.font_id)
        # The image, compressed like the Game Over one, and with the menu's
        # colors below its own in the same stream: the whole CGRAM at once,
        # the menu's palette at the bottom because a 4-bit BG only reaches
        # those. The tiles' indices already come shifted from
        # `palette.convert`.
        below = list(menu_palette)
        below += [(0, 0, 0)] * (constants.MENU_CGRAM - len(below))
        screen = fullscreen.compressed(
            picture, constants.MENU_CGRAM, constants.COLORS, below)
        title_data = {"pantalla": screen,
                      "menu_tiles": menu_tiles, "menu_paleta": menu_palette,
                      "menu_tilemaps": menu_maps}
        print("  title screen %r: %d 8bpp tiles + %d colors, "
              "%d B in an LZ2 stream of %d B"
              % (name, screen["tiles"],
                 screen["colores"] - len(below), screen["crudo"],
                 len(screen["flujo"])))
        print("    menu (%s): %d 4bpp tiles (%d B) + %d colors, %d tilemap(s)"
              % (", ".join(repr(t) for t in texts), len(menu_tiles),
                 len(menu_tiles) * 32, len(menu_palette), len(menu_maps)))
    # The Game Over screen: the image the LDB's `System` names, in the game's
    # or the RTP's `GameOver/` —as RM2k looks for it—, compressed. It goes in
    # every ROM that finds it: any cartridge can lose a battle or run a
    # `GameOver`. See tools/port/fullscreen.py.
    game_over_data = None
    path = find_resource([args.game_dir, resources.RTP_DIR], "GameOver",
                         renderer.database.gameover_name)
    if renderer.database.gameover_name and path:
        from PIL import Image
        game_over_data = fullscreen.compressed(Image.open(path))
        print("  Game Over screen %r: %d 8bpp tiles + %d colors, "
              "%d B in an LZ2 stream of %d B"
              % (os.path.basename(path), game_over_data["tiles"],
                 game_over_data["colores"], game_over_data["crudo"],
                 len(game_over_data["flujo"])))
    # The battle animations the already emitted bytecode shows: their
    # prerendered frames go to the cartridge and the ROM uploads them by DMA.
    animations = rom_animations(maps, renderer)
    for number in sorted(animations):
        data = animation_mod.report(number, animations[number])
        print("  animation %d: %d frames of %dx%d, shrunk from %dx%d to %d%%,"
              " %d colors, %d B"
              % (data["animacion"], data["cuadros"], data["caja"][0],
                 data["caja"][1], data["original"][0], data["original"][1],
                 data["porciento"], data["colores"], data["bytes"]))
    # The random encounters of each map, which ask for their troops. They go
    # **before** those of the test pages, which go at the end: that way the
    # cartridge's troops are numbered by the maps and the invented one goes
    # last, which is the same `rom_songs` does with the map's song.
    # Asking for it first always gave it index 0, and with that no case of the
    # suite exercised that `scene_troop_backdrop` and `troop_id` are really
    # indexed. That is why `case_page` compiles without `Troops`.
    encounters = rom_encounters(maps, renderer.tree,
                                args.test_encounters, troops)
    how_many = sum(z["troop_n"] for z in encounters["zonas"])
    if encounters["registros"]:
        print("  random encounters: %d map(s), %d zone(s), %d troop(s)"
              % (len(encounters["registros"]), len(encounters["zonas"]),
                 how_many))
    for cmd in file_commands:
        if cmd.code == events.ENEMY_ENCOUNTER:
            troops.request(events.encounter_troop(cmd),
                           events.encounter_backdrop(cmd))
    # The battle's audio, with the indices it already got from `songs` while
    # the pages compiled. It is asked for again only to read them: `Songs`
    # numbers once and returns the same, and what was noted goes to the
    # battle's package and not to any map's.
    battle_audio = events.battle_audio(songs) if troops.ids else None
    # The backdrops and the battlers the cartridge's battles ask for, each one
    # once: the ROM composes them when each battle starts. See
    # tools/port/scene.py, which is where the reason and the budget are.
    scenes = rom_scene(renderer.database, troops, maps, renderer.tree,
                       encounters, args.game_dir)
    # The `.msu` is written after the audio, because it also carries the
    # quality sound effects: see `msu_asm`.
    for info in scenes["fondos"]:
        rom_tiles, rom_colors = fallback_bytes(info)
        msu_tiles, msu_colors = scenes["calidad"][info["numero"]]
        print("  battle backdrop %d %r: %dx%d, %d tiles from CGRAM entry %d; "
              "in the ROM %dx%d at 4bpp and %d colors (%d B), in "
              "the .msu 8bpp and %d colors (%d B)"
              % (info["numero"], info["nombre"], scene_mod.WIDTH,
                 scene_mod.HEIGHT, scene_mod.TILES, scene_mod.CGRAM_BASE,
                 scene_mod.FALLBACK_WIDTH, scene_mod.FALLBACK_HEIGHT,
                 len(info["respaldo"]["paleta"]),
                 len(rom_tiles) + len(rom_colors), scene_mod.COLORS,
                 len(msu_tiles) + len(msu_colors)))
    # And the ones that aren't in the ROM, with which one replaces them
    # without MSU-1.
    in_rom = {info["numero"] for info in scenes["fondos"]}
    outside = [k for k in range(len(scenes["juego"])) if k not in in_rom]
    if outside and scenes["fondos"]:
        print("  battle backdrops only in the .msu, which without MSU-1 fall "
              "back to %r: %s" % (scenes["fondos"][scenes["respaldo_de"][outside[0]]]
                                  ["nombre"], ", ".join(
                                      "%d %s" % (k, scenes["juego"][k])
                                      for k in outside)))
    for info in scenes["battlers"]:
        d = scene_mod.battler_report(info)
        print("  battler %r: %dx%d, %d B, %d colors of %d"
              % (d["clave"], d["ancho"], d["alto"], d["bytes"], d["quedan"],
                 d["colores"]))
    # The event pages of the troops some battle of the cartridge asks for,
    # with **all** the troops already asked for: the maps', the random
    # encounters' and the test pages'. See `events.TroopPages`, which is
    # also why their messages go to a separate block. With `songs`, because a
    # page's `PlaySound` sounds in the battle's package, which isn't built
    # yet: it is built further down.
    troop_pages = events.TroopPages()
    for number in troops.ids:
        if number in renderer.database.troops:
            troop_pages.compile(number, renderer.database.troops[number],
                                songs)
    print("  troop pages: %d of %d in %d distinct body(ies), %d B of "
          "code and %d B in %d message(s)"
          % (troop_pages.pages - troop_pages.left_out,
             troop_pages.pages, len(troop_pages.where),
             len(troop_pages.bodies), len(troop_pages.messages.data),
             len(troop_pages.messages.texts)))
    # The items the enemies of those troops drop can also reach the
    # inventory: see `drop_items`.
    slots_data["items"] = sorted(
        set(items_rom) | drop_items(renderer.database, troops.ids))
    compressed = compress_blocks(maps)
    report = emit(args.output, maps, args.start_index, args.hero_above, party,
                  window_data, title_data, slots_data,
                  args.pictures.info, animations, troops.ids, battle_audio,
                  scenes, encounters, troop_pages, compressed,
                  enemy_hp=args.enemy_hp,
                  game_over=game_over_data)
    # Which entries of their palette the timer digits use, one bit per entry
    # and one word per map, in the order of `map_table`. `upload_timer_pal`
    # uploads **those** again untinted and not the whole palette, because the
    # palette belongs to a character that is tinted. It goes separately and
    # not as a record field because the record is at exactly its 128. The
    # index is the same `index + 1` `timer_digits` painted the glyphs
    # with: the first one that has that color.
    timer_color_list = sorted(timer_colors_of(skin))
    masks = []
    for map_info in maps:
        sprite, mask = map_info["sprite"], 0
        if sprite and sprite[5]:
            palette = sprite[1][sprite[6]]
            for color in timer_color_list:
                mask |= 1 << (palette.index(color) + 1)
        masks.append(mask)
    with open(args.output, "a") as handle:
        handle.write('\n.segment "RODATA"\n.block %d\ntimer_mask:\n'
                     '    .word %s\n'
                     % (2 * len(masks),
                        ", ".join("$%04X" % m for m in masks)))
    if len(args.cases) > 1:
        # Where the harness writes the case number: see `--case`.
        with open(args.output, "a") as handle:
            handle.write("\nCASE_SLOT = %d\n" % events.variable_slot(
                events.CASE_VARIABLE))
    print("%d map(s) -> %s, boots at %d (map %d)"
          % (len(maps), args.output, args.start_index, maps[args.start_index]["id"]))
    # What the allocator decided, as images: to look at which colors were lost
    # and which palette each cell ended up in without building or running the
    # ROM. They are indexed and their indices are CGRAM entries, so an editor
    # in indexed mode opens them just as `tiles` is going to see them.
    allocator = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                             "asignador")
    os.makedirs(allocator, exist_ok=True)
    for map_info in maps:
        pictures = list(map_info["imagenes_fondo"]) + [("encima", map_info["above"][5])]
        for name, png in pictures:
            with open(os.path.join(allocator, "%04d-%s.png"
                                   % (map_info["id"], name)), "wb") as handle:
                handle.write(png)
    # And **what it decided to lose**, written down: which color was merged
    # with which in each layer. It goes next to the images because it comes
    # from the same decision, but it is something else: the images are for
    # looking at and this is for reading back and for the diff to warn. What
    # is versioned is in `rom/parches/`, and `just parches --check` compares.
    # See tools/port/patches.py.
    patches_dest = os.path.dirname(os.path.abspath(args.output))
    count, weigh = patches_mod.write_maps(patches_dest, maps)
    print("patches of %d map(s) -> %s (%d B)"
          % (count, patches_mod.MAPS_IN_BUILD, weigh))
    # And the other decision that is already written down: **at what size
    # each battle animation is drawn**. It comes from the same round above;
    # here it is joined with the name and the sheet the animation has in the
    # LDB, which nobody looks at to draw and are there so that the diff says
    # which one it is about.
    count, weigh = patches_mod.write_animations(
        patches_dest,
        [dict(animation_mod.report(number, animations[number]),
              nombre=events.ANIMATIONS[number].get("nombre", ""),
              hoja=events.ANIMATIONS[number].get("imagen", ""),
              lado=animation_mod.BOX)
         for number in sorted(animations)])
    print("patches of %d animation(s) -> %s (%d B)"
          % (count, patches_mod.ANIMS_IN_BUILD, weigh))
    # And **which fifteen colors each battler is reduced to**, which is the
    # decision the scene composed on the console brought: see
    # tools/port/scene.py.
    count, weigh = patches_mod.write_battlers(patches_dest,
                                              scenes["battlers"])
    print("patches of %d battler(s) -> %s (%d B)"
          % (count, patches_mod.BATTLERS_IN_BUILD, weigh))
    # And who asked for each one, which isn't versioned: it is what separates,
    # in the ROM that is played, what belongs to the game from what only
    # exists because of the suite.
    patches_mod.write_uses(patches_dest, patch_uses(
        maps, renderer.database, renderer.tree))
    if report:
        print("material compressed and shared between maps:")
        for line in report:
            print(line)

    # The music comes from here and not from a separate recipe.
    # `musicdata.inc` was global state as `mapdata.inc` was, with the
    # aggravating factor that nobody regenerated it: a ROM built for maps 4, 7,
    # 19 and 1 —which have no music— played the song of map 348, which was the
    # last one somebody had generated by hand. Emitting them together is the
    # only thing that guarantees both describe the same ROM.
    #
    # **All the songs** go, sharing a single sample bank, and the one of the
    # map the ROM boots in plays; the others are started by a `PlayBGM`, or
    # by the map that is entered if it brings its own —see `map_song_mute`
    # in tools/runtime/enter_map.s—. What rate each sample ends up at is
    # decided by the ARAM, package by package: see `Bank` in snes_music.py.
    music = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                         "musicdata.inc")
    requested, boot, title_song, map_song, game_over_song = (
        rom_songs(
            maps[args.start_index]["id"], songs, args.game_dir,
            renderer.database.title_music if not args.no_title else None,
            [m["id"] for m in maps],
            renderer.database.gameover_music if game_over_data else None))
    # The sound effects, in the order the compiled pages ask for them: the
    # maps are compiled in ROM order, so those of the map where it boots go
    # first —in the demo, the rain and the thunder of the opening—. Only the
    # ones that are in some package: one that isn't in any doesn't sound
    # anywhere —its row of `sound_table` stays at $FF— and building it would
    # cost the music, because `snes_music.copies` counts the cartridge's
    # sound effects. It happens with the route ones of
    # `se_route_left_out`.
    packed = {n for palettes_needed in songs.per_map.values()
              for n in palettes_needed["sonidos"]}
    requested_se = []
    for name, _v, _t, _b in songs.sounds:
        if name not in requested_se and name in packed:
            requested_se.append(name)
    # Each map's audio package, in the order of the map table: the songs its
    # pages can start —plus, in the boot one, the one that plays from the
    # start, and in all the map's own— and its sound effects, in the order
    # they appear, which is the priority the ROM uploads them with if they
    # don't all fit. See `package_load` in tools/runtime/audio_package.s.
    # They are built **before** the bank, by name, because each sample's
    # budget comes from them: see `snes_music.Bank`.
    packages, separate_ones = [], []
    for i, _map in enumerate(maps):
        palettes_needed = songs.per_map.get(i, {"temas": [], "sonidos": []})
        owned = list(palettes_needed["temas"])
        if i == args.start_index and boot != 0xFF and boot not in owned:
            owned.insert(0, boot)
        # And the map's own song, **in front**: it is the only one on the list
        # that surely plays on entering, so if the ARAM isn't enough for
        # everything it is the last one that has to fall. Without it in the
        # package, its samples would have to be uploaded by `song_ensure`
        # when starting it, rebuilding the whole package a second time.
        if map_song[i] != 0xFF:
            if map_song[i] in owned:
                owned.remove(map_song[i])
            owned.insert(0, map_song[i])
        # And the exit ones, separate and after the sound effects: the ones
        # the map starts only to leave have no reason to go in with its sound
        # effects. See `Songs.exit_songs`. Not the map's own nor the boot one:
        # those play on entering.
        out = [t for t in songs.exit_songs(i)
               if t in owned and t != map_song[i]
               and not (i == args.start_index and t == boot)]
        owned = [t for t in owned if t not in out]
        # And the separate ones, which don't go with the other songs either:
        # their `PlayBGM` uploads them with the package's sound effects. See
        # `separate_songs`.
        separate = [t for t in owned if requested[t] in snes_music.separate_songs().get(
                      _map["id"], ()) and t != map_song[i]
                    and not (i == args.start_index and t == boot)]
        owned = [t for t in owned if t not in separate]
        separate_ones.append(separate)
        packages.append((owned, list(palettes_needed["sonidos"]), out))
    # And the battle's package, after the maps: the battle song and its sound
    # effects, which the ROM uploads when opening the battle and unloads when
    # closing it. It goes separately and not inside the map's package because
    # the battle song alone fills the ARAM; see `events.BATTLE_PACKAGE`.
    palettes_needed = songs.per_map.get(events.BATTLE_PACKAGE)
    if palettes_needed:
        packages.append((list(palettes_needed["temas"]), list(palettes_needed["sonidos"]), []))
        separate_ones.append([])
    package_names = ([str(m["id"]) for m in maps]
                     + (["pelea"] if palettes_needed else []))
    # And the Game Over screen's, last: its song alone and no sound effects.
    # The ROM uploads it with the screen black, before the fade in —see
    # `game_over_black` in tools/runtime/game_over.s—, and with a package of
    # its own it uploads only that: arriving with `song_ensure` would
    # rebuild the whole map package behind it, which is one more second of
    # black. For the allocation it is a one-song package, which doesn't lower
    # anyone's rate: its samples fit alone in the ARAM.
    game_over_package = 0xFFFF
    if game_over_song != 0xFF:
        game_over_package = len(packages)
        packages.append(([game_over_song], [], []))
        separate_ones.append([])
        package_names.append("gameover")
    per_name = [(name, owned, theirs, out, separate)
                for name, (owned, theirs, out), separate
                in zip(package_names, packages, separate_ones)]
    # And the title screen's, which isn't in the table: `song_ensure`
    # uploads its song with the boot map's package behind.
    if title_song != 0xFF:
        owned, theirs, _out = packages[args.start_index]
        per_name.append(("titulo", [title_song] + owned, theirs))
    inheritance = inherited_songs(songs, map_song, args.start_index,
                                  title_song, package_names,
                                  [owned for owned, _e, _s in packages],
                                  separate_ones, not_given=settings.value(
                                   "music", "jumps_that_never_happen",
                                   kind=list))
    driver, samples, done_ones, bank = snes_music.build_all(
        requested, args.game_dir, requested_se, per_name, inheritance,
        measuring_headroom=args.measure_headroom)
    # And what `tools/audio/ceilings.py` needs from each song —how long it lasts
    # and the fingerprint of its mix—, written next to it: the bank can no
    # longer be rebuilt without compiling the pages, which is where the
    # packages come from.
    with open(os.path.join(os.path.dirname(music), "musica.json"),
              "w") as handle:
        json.dump({"temas": [
            {"nombre": t["nombre"],
             "largo": t["escrituras"][-1][0] + 1 if t["escrituras"] else 0,
             "huella": t.get("huella", ""),
             # `tools/audio/msu.py` reads it from here, which builds only the
             # tracks of the cartridge's songs.
             "pista": t["pista"]} for t in done_ones]},
            handle, indent=1)
    # Each package's sound effects go by number and not by SRCN: several share
    # the directory's place. See `snes_music.effect_places`.
    effects = getattr(bank, "effects", {})
    effect_id = getattr(bank, "effect_id", {})
    packages = [(owned, [effect_id[n] for n in theirs if n in effects], out)
                for owned, theirs, out in packages]
    directory = (len(bank.voices), getattr(bank, "places", 0))
    effect_place = [srcn - directory[0] for srcn, _e in sorted(
        effects.values(), key=lambda v: effect_id[v[1].name])]
    if palettes_needed:
        assert package_names[len(maps)] == "pelea", (
            "the battle's package has to end up at the index `emit` emitted "
            "as PAQUETE_BATALLA")
        print("  battle audio package: %d song(s), %d sound effect(s)"
              % (len(palettes_needed["temas"]), len(packages[-1][1])))
    # **And that the boot fits in `BOOT_FRAMES`**: the ROM waits until that
    # frame so that the loop always starts on the same one, and if uploading
    # the boot map's package took longer, it would come out later and the
    # tests —which count from there— would count wrong. See the comment on
    # `BOOT_FRAMES` in tools/runtime/far_ram.s.
    frames, in_package = snes_music.boot_frames_estimate(
        driver, samples, done_ones, packages[args.start_index],
        decompress_frames(maps[args.start_index], compressed),
        directory)
    cap = snes_music.boot_frames()
    if frames > cap:
        raise SystemExit(
            "the boot doesn't fit in BOOT_FRAMES: the boot map's package is "
            "%d B and with the map, the driver and the directory the "
            "computation gives %.0f frames, against %d. Raise BOOT_FRAMES in "
            "tools/runtime/far_ram.s, or shrink that package"
            % (in_package, frames, cap))
    print("  boot: the boot map's package is %d B, %.0f of "
          "the %d frames of BOOT_FRAMES" % (in_package, frames, cap))
    snes_music.emit(music, done_ones, driver, samples, boot, title_song,
                    snes_music.sound_table(songs.sounds, bank),
                    [p + (separate,) for p, separate in zip(packages, separate_ones)],
                    map_song, directory, effect_place,
                    game_over=(game_over_song, game_over_package))
    # The `.msu`: the quality backdrops and the quality sound effects, to read
    # them through the MSU-1 when it is there. It is always written, even if
    # the cartridge carries neither backdrops nor sound effects, because it is
    # also the file that turns on the MSU-1 for the tracks.
    write_msu(args.msu or os.path.join(os.path.dirname(os.path.abspath(
        args.output)), "datos.msu"), music, scenes["calidad"],
        per_name[:len(packages)], packages, done_ones, samples, bank,
        songs.sounds, args.game_dir)
    for i, (owned, theirs, out) in enumerate(packages[:len(maps)]):
        if owned or theirs or out or separate_ones[i]:
            print("  audio package of map %d: %d song(s), %d sound effect(s)%s%s"
                  % (maps[i]["id"], len(owned), len(theirs),
                     ", and for exit %s" % ", ".join(done_ones[t]["nombre"]
                                                     for t in out)
                     if out else "",
                     ", and separate %s" % ", ".join(done_ones[t]["nombre"]
                                                     for t in separate_ones[i])
                     if separate_ones[i] else ""))
    if requested_se:
        print("  sound effects: %d, %d B in the cartridge"
              % (len(effects), sum(len(e.data) for _s, e in effects.values())))
    print("music -> %s: %s"
          % (music, ", ".join(t["nombre"] for t in done_ones)
             or "none, it comes out silent"))

    # The bank packing is not decided here: both files send everything to
    # RODATA, with a `.block` or a `.crossbank` in front of each piece, and
    # `rm2k-snes-assemble` spreads it into banks and writes the memory map
    # before running `ca65`.
    for i, song in enumerate(done_ones):
        # The percentage of notes that reach the stream goes here and not
        # hidden: it is what is heard as "it's missing voices", and until
        # 2026-09-14 nobody said it. See
        # workflow/decisiones/un-solo-banco-de-muestras.md.
        sound = song["resumen"].get("notas")
        # And how much of what does have a sample is lost for lack of voices,
        # against what would be lost with no remedy with eight: it is what
        # the allocation of `snes_music.assign` measures.
        lost, floor = song["resumen"].get("perdido", (0.0, 0.0))
        print("  %d. %-16s %4.0f s, %6d B of stream and %4d of sounds, "
              "%s of the notes, %.0f%% of note-time without a voice (floor %.0f%%)%s"
              % (i, song["nombre"], song["segundos"], len(song["stream"]),
                 6 * len(song["sonidos"]),
                 "all" if sound is None or sound > 0.999
                 else "%.0f%%" % (100 * sound), 100 * lost, 100 * floor,
                 ", plays from boot" if i == boot else ""))
    if done_ones:
        print("  shared bank: %d samples, %d B in the cartridge; each "
              "package has %d B of ARAM for its samples"
              % (len(bank.voices), sum(len(v.data) for v in bank.voices),
                 bank.free))
        # What rate each sample ended up at and which package limited it: it
        # is what is heard, and what says where to look for room if needed. A
        # key with copies comes out once per copy, with the songs that use it:
        # see `snes_music.copies`.
        use = collections.defaultdict(list)
        for song, its in zip(done_ones, bank.assignment):
            for sample in its.values():
                use[sample].append(song["nombre"])
        for key, voice in zip(bank.keys, bank.voices):
            print("    %s %3d %-10s %5.1f kHz, %5d B%s%s%s"
                  % ("program " if key[0] == "p" else "hit     ", key[1],
                     voice.name.strip()[:10], voice.rate / 1000.0, len(voice.data),
                     ", root %d" % voice.root if key[0] == "p" else "",
                     ", limited by " + bank.limited_by[key]
                     if key in bank.limited_by else "",
                     ", for " + " ".join(use[key])
                     if len(key) > (3 if key[0] == "p" else 2)
                     or any(len(k) > len(key) and k[:len(key)] == key
                            for k in bank.keys) else ""))
        # And how much each package has left over, with its sound effects: the
        # whole ones with what they really take, not with what the music
        # budgeted for them. The bank's constraints already bring them that way
        # —they are those of `reales`, see `snes_music.copies`—: subtracting
        # the extra again gave packages that didn't fit and did fit.
        for r in bank.constraints:
            print("    package %-28s %5d B of samples, %5d left over"
                  % (r.name[:28], bank.takes(r.keys),
                     r.free - bank.takes(r.keys)))


def write_msu(path, music, backdrops, per_name, packages, done_ones, samples,
              bank, sounds, game_dir):
    """Writes the `.msu` to `path` and appends to `music` —the
    `musicdata.inc`— what the ROM needs to read it: the signature, where each
    backdrop is and, per package, where each sound effect is and at which
    pitch each sound plays.

    The backdrops go first —`backdrops` are the `(tiles, colors)` of **all the
    game's**, by number, each in its fixed place: see `msu_data.backdrop_offset`—
    and behind them the quality sound effects of each package, in the order
    of the package table and each package with its own in order of place in
    the directory —their SRCN—: it is the order `upload_placed` uploads them
    in, so the ROM reads them in one go, with a single seek per package. A
    sound effect that is in two packages goes twice even if at the same rate:
    a seek costs Mednafen one or two frames, and the file has no cap.

    `per_name` are the ROM's packages as `build_all` sees them —with the
    names of their sound effects— and `packages` the same as `emit` emits them
    —with their sound effect numbers—, in the same order. See
    tools/audio/msu_effects.py.
    """
    effects = getattr(bank, "effects", {})
    by_number = {i: n for n, i in getattr(bank, "effect_id", {}).items()}
    # What the music takes with MSU-1 in each package: only the songs without
    # a track, which `song_per_msu` doesn't skip.
    weighs = {}

    def music_of(songs):
        theirs = set()
        for t in songs:
            if done_ones[t]["pista"] is None:
                if t not in weighs:
                    weighs[t] = snes_music.song_samples(done_ones[t])
                theirs |= set(weighs[t])
        return sum(len(samples[i].data) for i in theirs)
    requested = [(str(p[0]), list(p[2]), music_of(p[1]))
                 for p in per_name]
    rates = msu_effects.rates_per_package(requested, effects, bank.free, game_dir)
    unique = sorted({(e, t) for theirs in rates.values()
                     for e, t in theirs.items()})
    done_tracks = dict(zip(unique, in_parallel(
        lambda pair: msu_effects.build(pair[0], pair[1], game_dir), unique)))

    entries = [part for pair in backdrops for part in pair]
    # Which entry each sound effect of each package is, in SRCN order: two of
    # the same package never share a place.
    in_package = []
    for (name, _t, _e, *_s), (_songs, numbers, _out) in zip(per_name,
                                                            packages):
        theirs = rates.get(str(name), {})
        values = []
        for e in sorted({by_number[i] for i in numbers},
                        key=lambda e: effects[e][0]):
            values.append((e, len(entries), done_tracks[e, theirs[e]]))
            entries.append(done_tracks[e, theirs[e]].data)
        in_package.append(values)
    blob, offset = msu_data.build(entries, backdrops=len(backdrops))
    signature = blob[:msu_data.SIGNATURE_SIZE]
    with open(path + ".nuevo", "wb") as handle:
        handle.write(blob)
    os.replace(path + ".nuevo", path)
    print("  .msu: %d backdrop(s) and %d sound effect(s) in %d B, signature %s -> %s"
          % (len(backdrops), sum(len(l) for l in in_package), len(blob),
             signature.hex(), path))

    # Per package, one row per sound effect of its list —that of `packages`,
    # in the order the ROM walks it—: where it is in the `.msu`, how long it
    # is and where it loops back, which is always to the start because they
    # go whole.
    rows, from_rows = bytearray(), bytearray()
    heights, from_heights, already_done = bytearray(), bytearray(), {}
    for (name, *_r), (_songs, numbers, _out), values in zip(
            per_name, packages, in_package):
        from_rows += (len(rows)).to_bytes(2, "little")
        by_effect = {e: (offset[k], v) for e, k, v in values}
        for i in numbers:
            pos, version = by_effect[by_number[i]]
            rows += (pos.to_bytes(4, "little")
                     + len(version.data).to_bytes(2, "little")
                     + bytes(2))
        # And the pitch of each sound of `sound_table` with this package's
        # version: with that the ROM does no arithmetic, not even in the
        # interrupt. **Only the sounds whose sound effect is from here**, as
        # (index, pitch) pairs sorted by index and closed with $FFFF, which
        # `msu_pitch` walks: until 2026-09-27 it was one row per package with
        # all the sounds, almost all zeros, and with the whole world chapter
        # it went over a bank. Two packages with the same list share it.
        theirs = rates.get(str(name), {})
        values = bytearray()
        for k, (effect, _volume, tempo, _balance) in enumerate(sounds):
            height = 0
            if effect in theirs:
                height = snes_music.effect_pitch(
                    done_tracks[effect, theirs[effect]], tempo)
            # Zero is "not from here" for the ROM, so it isn't stored.
            if height:
                values += k.to_bytes(2, "little") + height.to_bytes(2, "little")
        values += b"\xFF\xFF"
        values = bytes(values)
        if values not in already_done:
            already_done[values] = len(heights)
            heights += values
        from_heights += already_done[values].to_bytes(2, "little")
    for table in (rows, heights):
        if len(table) > 0x8000:
            raise SystemExit("the .msu sound effect tables go over a "
                             "bank: %d B" % len(table))
    positions = [(offset[2 * k], offset[2 * k + 1]) for k in range(len(backdrops))]
    backdrop_pos = b"".join(a.to_bytes(4, "little") + b.to_bytes(4, "little")
                            for a, b in positions) or bytes(8)
    with open(music, "a") as handle:
        handle.write(
            "\n; The `.msu`: see `escribir_msu` in tools/port/snes_convert.py.\n"
            "; How many entries of the .msu are backdrops —two per backdrop,\n"
            "; the first ones— and how many are sound effects, behind: for\n"
            "; the tests.\n"
            "MSU_BACKDROPS_N = %d\n"
            "MSU_EFFECTS_N = %d\n"
            '.segment "RODATA"\n%s\n'
            % (len(backdrops),
               sum(len(values) for values in in_package),
               "\n".join(block(label, data or bytes(2)) for label, data
                         in (("msu_data_signature", signature),
                             ("msu_backdrop_pos", backdrop_pos),
                             ("se_msu_pkg", from_rows),
                             ("se_msu_rows", rows),
                             ("se_msu_pitch_pkg", from_heights),
                             ("se_msu_pitch", heights)))))
    # And the same, readable, next to it: which sound each row of
    # `sound_table` is and at which rate each sound effect of each package
    # goes in the `.msu`. The ROM doesn't read it; it is for the tools that
    # touch a sound effect from outside and to look at what the allocation
    # decided.
    with open(os.path.join(os.path.dirname(music), "efectos.json"),
              "w") as handle:
        json.dump({"sonidos": [list(s) for s in sounds],
                   "srcn": {e: srcn for e, (srcn, _v) in effects.items()},
                   "tasas": rates}, handle, indent=1)
    for (name, *_r) in per_name:
        theirs = rates.get(str(name), {})
        if theirs:
            print("  quality sound effects of package %s: %s"
                  % (name, ", ".join(
                      "%d Hz: %d" % (t, sum(1 for v in theirs.values()
                                            if v == t))
                      for t in sorted(set(theirs.values()), reverse=True))))


def inherited_songs(songs, map_song, initial, title, package_names,
                    in_package=None, separate_ones=None, not_given=()):
    """[(package name, index of a song that can be already playing when it
    loads)], for `snes_music.build_all`.

    Almost no map of the game brings its own song: a page starts it, and
    until then the previous map's keeps going, and `package_load_done`
    doesn't move its samples. So the package of a map without its own song
    has to fit next to whatever can be already playing.

    The teleports of the compiled pages are followed —`destinos` of
    `Songs.per_map`— without looking at conditions, with a rule that is what
    makes the count realistic and not "any song to any map" (4 is the game's
    router): **a map with `PlayBGM` leaves with one of its own**, because the
    page that jumps is almost always the one that started the song before. A
    map with its own song silences what plays before loading its own
    —`map_song_mute`—, so it inherits nothing; and the boot map is reached
    with the title's playing. It is what step 6 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md` measured with a separate
    script.

    `in_package` are the songs each map's package uploads on entering
    —without the exit ones, see `Songs.exit_songs`—: a song that arrives
    playing and isn't there has to fit next to it. Without it, the ones its
    pages start. What leaves a map is still any of the ones they start, exit
    ones included: they are precisely the ones that leave with it.

    **Except in a map whose `PlayBGM`s are all exit ones**: there the rule
    above doesn't hold, because each one goes stuck to its jump and the map's
    other jumps carry none. Each jump carries what `Songs.jump` says: the
    exit song that precedes it, or whatever came into the map. It is the
    game's 41 and 40: `Kfmus5` comes into 41 from the page of 37 and goes on
    through 40, 42, 43, 44 and 45, while `golden_axe-turtlevillage2` and
    `tsmedit` play only to leave. From 2026-09-27; until then those maps
    inherited only their exit songs. The boot one keeps the rule above: see
    `carries`.

    `separate_ones` are the separate songs of each package —see
    `snes_music.separate_songs()`—: they don't leave the map, so they don't
    count in what goes out.

    `not_given` are the jumps of compiled pages that can't happen, as
    [map, destination] pairs: a jump that never happens makes it reserve room
    for a song that never arrives, at the expense of the ones that do. The
    game declares them, in `[music] jumps_that_never_happen` of the project
    file.
    """
    n = len(map_song)
    palettes_needed = [songs.per_map.get(i, {}) for i in range(n)]
    separate_ones = separate_ones or [()] * n
    index = {name: i for i, name in enumerate(package_names[:n])}
    not_given = {(index[str(a)], index[str(b)])
                 for a, b in not_given
                 if str(a) in index and str(b) in index}
    jumps = getattr(songs, "jumps", {})
    fits = [set() for _ in range(n)]
    if title != 0xFF:
        fits[initial].add(title)

    def carries(i, dest):
        if map_song[i] != 0xFF:
            return {map_song[i]}
        theirs = set(palettes_needed[i].get("temas", ())) - set(separate_ones[i])
        # Not the boot one: it is the router, which jumps to mid-game
        # according to variables, and without looking at conditions whatever
        # comes in there would go out anywhere.
        if theirs and theirs <= set(songs.exit_songs(i)) and i != initial:
            # A destination no noted jump names —that of a page that didn't
            # compile whole— carries what came in.
            with_it = jumps.get(i, {}).get(dest, {None})
            return ({t for t in with_it if t is not None}
                    | (fits[i] if None in with_it else set()))
        return theirs or fits[i]

    change = True
    while change:
        change = False
        for i in range(n):
            for dest in palettes_needed[i].get("destinos", ()):
                if (i, dest) in not_given:
                    continue
                leaves = carries(i, dest)
                if (dest != i and map_song[dest] == 0xFF
                        and not leaves <= fits[dest]):
                    fits[dest] |= leaves
                    change = True
    if in_package is None:
        in_package = [palettes_needed[i].get("temas", ()) for i in range(n)]
    return [(package_names[i], t) for i in range(n)
            for t in sorted(fits[i])
            if t not in in_package[i] and t != map_song[i]]


def rom_songs(map_id, songs, game_dir, title=None, map_ids=(),
              game_over=None):
    """Which songs the cartridge asks for, which one plays at boot and which
    one each map starts on entering.

    **All** are asked for: the ones the compiled `PlayBGM`s name, plus that of
    the map where the ROM boots, which is the one that plays without anything
    happening. **And all of them fit**: the index is given by the list and
    costs no ARAM. What the ARAM limits is the samples, and that is allocated
    by `snes_music.build_all` per package: at the rate the worst package of
    each one gives, but all of them.

    The indices are those of `Songs` and aren't touched: the bytecode already
    carries them emitted. That is why the map's is added **at the end**,
    which is the only thing that doesn't renumber the others. Going last
    costs nothing: since the per-package budget no song loses samples for its
    place in the list.

    And the own song of each map in `map_ids` —in the order of the map
    table—, which is easyrpg's `Game_Map::PlayBgm`: what plays when entering
    through a teleport. They go behind all, for the same reason, and as each
    one's index or $FF, which is "entering doesn't change the music".
    """
    own = snes_music.song_of_map(map_id, game_dir)
    if own:
        songs.index(own)            # adds it at the end if it wasn't there
    # The title screen's goes after, for the same reason: adding at the end is
    # the only thing that doesn't renumber the ones the bytecode already
    # names. It comes from the LDB —`title_music`, which in ABL is
    # Fantasia_Of_The_Wind— and not from the command line: it is a piece of
    # the game's data, not a choice of ours.
    if title:
        songs.index(title)
    # And the Game Over screen's, for the same reason: `gameover_music`,
    # which in ABL is `GameOver3` and comes from the RTP. See
    # `PACKAGE_GAME_OVER`.
    if game_over:
        songs.index(game_over)
    each_map = []
    for name in snes_music.songs_of_maps(map_ids, game_dir):
        index = songs.index(name) if name else 0xFF
        # $FF is "doesn't change": a song with that number couldn't be
        # started. A `PlayBGM`, which carries the index in one byte, wouldn't
        # start it either.
        assert index <= 0xFF, "song %r doesn't fit in a byte" % name
        each_map.append(index)
    names = list(songs.names)
    return (names, (names.index(own) if own else 0xFF),
            (names.index(title) if title else 0xFF), each_map,
            (names.index(game_over) if game_over else 0xFF))


def map_start(renderer, map_id, passable, width, height, used=()):
    """Where the hero stands on entering this map, in 16x16 cells.

    In the map where the game really starts, the LCF says it and there is
    nothing to choose: A Blurred Line starts in Map0004, which is an empty
    room whose only job is to trigger an event and teleport. That room doesn't
    have a single cell open on all four sides, so the heuristic below would
    have nowhere to put anyone.

    In any other map there is no real answer yet —it is reached by teleport,
    and where one comes from depends on where it came in— so the open tile
    nearest the center is used, which is what the tests need: a place from
    which one can walk.

    **And there are maps where no cell is open on all four sides**: the
    cutscene rooms, which are a black screen that is always reached by
    teleport with the coordinates set. `LasheCityVehicle` —map 36, the one
    that asks where to go with the car— is one, and without it the teleport
    of 34 doesn't compile and the whole car chain falls. There the emitted
    number is used by nobody, but the table carries it anyway, so the
    geometric center is used instead of stopping. The error from `hero_start`
    still holds for whoever asks it about a map where walking will happen.
    """
    if map_id == renderer.tree.start_map_id:
        return renderer.tree.start_x, renderer.tree.start_y
    try:
        return hero_start(passable, width, height, used)
    except ValueError:
        return width // 2, height // 2


def images_of(renderer, args, charset):
    """An actor's CharSet, loaded and cached."""
    if charset not in _charsets:
        _charsets[charset] = renderer.charsets.get(charset)
        if _charsets[charset] is None:
            sys.exit("can't find CharSet %r" % charset)
    return _charsets[charset]


_charsets = {}


def possible_leaders(renderer, map_ids, party):
    """The actors that can end up drawn as the hero in this ROM.

    The party it starts with, plus all the ones some `ChangePartyMembers` of
    some page that compiles adds. Removing someone also changes the leader,
    but to the next on the list, who is already counted.

    It is compiled with a text block, same as the real compilation: a page
    that adds someone to the party after a text box compiles only with it.
    Filtering differently here than there would leave that actor without its
    tiles in VRAM and the ROM would draw it with the previous one's. The text
    block built is throwaway: here only the yes or no matters.

    It is needed because the hero's tiles live in VRAM and aren't loaded on
    the fly: if the leader can change mid-map, the sprites of all the
    candidates have to be in place from the start.

    **And they are the ones that can go first, not all the ones that join the
    party.** The hero's graphic is the first one's; someone who always joins
    behind another is never drawn, and their twelve poses are 192 tiles that
    don't fit. It shows in the opening cutscene, which removes 10 and adds 11,
    12 and 13: with all four it is 628 sprite tiles and the layout gives 512.

    Who goes first is known by simulating: the `ChangePartyMembers` of the
    pages that compile are applied, in the order they appear, with the same
    rules as `PartyState.change_party`. It is an approximation —which page runs
    and when depends on switches that aren't known here— and that is why the
    order matters: if a ROM ever draws the hero with no graphic, start by
    looking here.

    **The party is reset in each map**, and that is the part that was hard.
    It used to be carried from one map to the next in file order, which isn't
    the order they are played in: the "1 year earlier" page of map 4 sets
    Talan, and since 4 goes before 1, when the simulation reached the opening
    the party already had Talan. The opening's `pone Kersh` put him
    **behind**, so Kersh was never leader, didn't go into the actor table and
    the hero was drawn with no graphic. taro saw it while playing: Core and
    Manta showed up at the end of the stairs and Kersh didn't.

    Resetting per map isn't more correct in general —it still isn't known
    with which party each one is reached— but it is the approximation that
    fits: the actor table is **per map**, so the question is who can lead
    while that map is loaded, and not what happened in the directory's
    previous maps.
    """
    actors = list(party[:1])
    for changes in _party_changes(map_ids):
        state = events.PartyState(party)
        for batch in changes:
            for who, operation in batch:
                state.change_party(who, operation)
            leader = state.leader()
            if leader is not None and leader not in actors:
                actors.append(leader)
    return actors


def _party_changes(map_ids):
    """The `ChangePartyMembers` of the pages that compile, map by map and in
    order: the only thing of each map `possible_leaders` looks at.

    **It is computed once per conversion**, because it doesn't depend on the
    party: `possible_leaders` runs again for each test case that touches the
    party, and each run loaded and compiled all the maps again. The
    compilation only reads the global indices of `events`, which are filled
    before the first call and don't change afterwards.
    """
    key = (_game(), tuple(map_ids))
    if key not in _changes_by_map:
        _changes_by_map[key] = [_map_changes(map_id, map_ids)
                                for map_id in map_ids]
    return _changes_by_map[key]


_changes_by_map = {}


def _map_changes(map_id, map_ids):
    indices = {m: i for i, m in enumerate(map_ids)}
    changes = []
    game_map = lcf.Map(os.path.join(_game(),
                                    "Map%04d.lmu" % map_id))
    map_events = events.MapEvents(game_map)
    for event in game_map.events:
        for page in event.pages:
            # With the map's context, which is the same the real filter uses.
            # Without it, a page that sends another event walking doesn't
            # compile here even though it does compile there, and the actors
            # it adds are lost: the opening cutscene adds Kersh to the party
            # right after sending event 8 walking, so the hero was left
            # without a pose table and wasn't drawn.
            # **With the same context as the real compilation**, and not only
            # with the text block. `Songs`, `Graphics` and `Pictures` were
            # missing, and without them a page that starts with a `PlayBGM`
            # doesn't compile **here** and does compile there: the actors it
            # adds to the party are lost. It is exactly what happened to the
            # chase car —`RaceController1` of map 49 starts with `PlayBGM`
            # and then adds `CarRED`—, and the symptom was that the hero
            # wasn't drawn: `hero_poses` at zero because the actor wasn't in
            # the map's table.
            if events.compile_page(
                    page, indices.get,
                    events.Messages(),
                    map_events.for_event(event.id), events.Songs(),
                    events.Graphics(), events.Pictures(
                        _game())) is None:
                continue
            # **In batches of consecutive commands**, and the leader is looked
            # at the end of each one: `ChangePartyMembers` stuck together run
            # in the same frame —none waits— so the hero isn't drawn with the
            # mid-batch leader. Looking at it after each command, 41 —which
            # removes everyone before adding Talan back, and does it in two
            # consecutive pages— left Arden, Saldra and AG7 as possible
            # leaders, with their poses and their colors in every map of the
            # cartridge, and moved the palettes of maps that have nothing to
            # do with it.
            batch = None
            for cmd in page.commands:
                if cmd.code != events.CHANGE_PARTY_MEMBERS:
                    batch = None
                    continue
                p = cmd.parameters
                if len(p) < 3 or p[1] != events.PARTY_FIXED_ID:
                    batch = None
                    continue
                if batch is None:
                    batch = []
                    changes.append(batch)
                batch.append((p[0], p[2]))
    return changes


# The game directory, for `possible_leaders`. It is ugly but it is a single
# place: the alternative was passing it through three functions that don't
# use it. `main` sets it, from `--game-dir`.
args_game_dir = [None]


def _game():
    """`main`'s or, if it didn't go through there —a test that calls these
    functions on their own—, the environment's, which is the same
    `--game-dir`."""
    return args_game_dir[0] or resources.GAME_DIR


def possible_items(map_ids, actors=(), db=None, extra=()):
    """The items that can be in the inventory with these maps in the ROM: the
    ones some `ChangeItems` of any page gives, whether it compiles or not,
    the ones some `OpenShop` sells, the equipment the `actors` start with
    and the ones the test page gives. It is a superset, like
    `possible_members`, and for the same reason: one item too many costs its
    text in the cartridge, one too few isn't seen in the list. `extra` are
    the commands of the test pages, which are swept the same as the maps'."""
    items = set()
    for actor in actors:
        if db is not None and actor in db.actors:
            items.update(i for i in db.actors[actor].initial_equipment if i)

    def sweep(commands):
        for cmd in commands:
            p = cmd.parameters
            if (cmd.code == events.CHANGE_ITEMS and len(p) >= 5
                    and p[0] == 0 and p[1] == 0):
                items.add(p[2])
            elif cmd.code == events.OPEN_SHOP:
                items.update(p[4:])

    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_game(),
                                        "Map%04d.lmu" % map_id))
        for event in game_map.events:
            for page in event.pages:
                sweep(page.commands)
    sweep(extra)
    return sorted(i for i in items if 0 < i < events.ITEMS_N)


def drop_items(db, troops):
    """The items some enemy of these troops can drop on losing a battle —its
    `drop_id`—, so that the cartridge carries their name: the victory tells
    it and the menu's list shows it. The ones `possible_items` doesn't find
    in any page. All the members, like `rom_enemies`."""
    return {db.enemies[e].drop_id for n in troops if n in db.troops
            for e in db.troops[n].members
            if 0 < db.enemies[e].drop_id < events.ITEMS_N}


def possible_members(map_ids, party, extra=()):
    """The actors that can be in the party with these maps in the ROM.

    The starting ones plus the ones any `ChangePartyMembers` of any page of
    these maps adds. Whether the page compiles isn't looked at: it is for the
    slots screen, which needs the face and the name of whoever can show up in
    a saved game, and one face too many costs nothing that matters. `extra`
    are the commands of the test pages.

    `party` can bring repeats —the cartridge's plus that of each test case,
    which is usually the same— and they are counted once: repeated, an actor
    took one face for each case that asked for it.
    """
    actors = list(dict.fromkeys(party))

    def sweep(commands):
        for cmd in commands:
            if cmd.code != events.CHANGE_PARTY_MEMBERS:
                continue
            p = cmd.parameters
            if len(p) < 3 or p[1] != events.PARTY_FIXED_ID:
                continue
            if p[0] == 0 and p[2] not in actors:
                actors.append(p[2])

    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_game(),
                                        "Map%04d.lmu" % map_id))
        for event in game_map.events:
            for page in event.pages:
                sweep(page.commands)
    sweep(extra)
    return sorted(actors)


def page_party(case, party):
    """Which party the test continues with after its page, if the page
    touches it: the case's `ChangePartyMembers` applied to the cartridge's
    party, with the same rules as the interpreter. None if it doesn't touch
    it."""
    state = events.PartyState(party)
    touches = False
    for cmd in case.commands:
        p = cmd.parameters
        if (cmd.code == events.CHANGE_PARTY_MEMBERS and len(p) >= 3
                and p[1] == events.PARTY_FIXED_ID):
            state.change_party(p[0], p[2])
            touches = True
    return state.party if touches else None


def separate_from_hero(renderer, game_map, args, commands=()):
    """If something flashes the hero, the NPCs with its graphic go with
    another palette.

    On the console the flash is done on the character's palette, and a leader
    that is also an NPC in the map shares a palette with that NPC —so that the
    NPC isn't drawn with another leader's colors—, so both flashed. It is
    solved by counting those NPCs' graphic as another one, with the suffix
    `rm2k.COPY_SUFFIX`: the same drawing, with its own palette. It costs one
    palette per graphic, and only in the maps where something flashes the
    hero. `commands` are those of the test pages.
    """
    flashes = any(
        cmd.code == events.FLASH_SPRITE and cmd.parameters
        and cmd.parameters[0] == events.ROUTE_HERO
        for cmd in list(commands) + [cmd for ev in game_map.events
                                     for page in ev.pages
                                     for cmd in page.commands])
    if not flashes:
        return
    leader_owned = set()
    for actor in args.leaders:
        a = renderer.database.actors[actor]
        leader_owned.add((a.charset, a.charset_index))
    for ev in game_map.events:
        for page in ev.pages:
            if (page.character_name, page.character_index) in leader_owned:
                page.character_name += rm2k.COPY_SUFFIX


# The flags that describe **a test case** —what its page does— and not the
# cartridge. They are the ones that can go after a `--case`; the rest belong
# to the whole cartridge and go before the first one. Since cut 3 of step 9d
# there is a single one, the file with the page: what the page does is RM2k
# data, not flags. `--test-graphic` belongs to the cartridge on purpose:
# it says which graphics are in the sprite bank of the maps where the cases
# run, not what the page does. And where a case runs isn't a flag either: the
# `Teleport` it starts with says so, see `case_map`.
CASE_FLAGS = ("test_commands",)


def split_cases(argv):
    """The command line split at `--case`: the cartridge's part, and the
    flags of each case that goes after."""
    stretches = [[]]
    for token in argv:
        if token == "--case":
            stretches.append([])
        else:
            stretches[-1].append(token)
    return stretches[0], stretches[1:]


def test_cases(parser, args, stretches):
    """The cartridge's test pages, one per case, in the order of their pages.
    Each one is a copy of `args` with its case's flags.

    Case 0 is the flags before the first `--case`, so a single-case cartridge
    is built as before this existed. If there are none, the first `--case`
    becomes 0. Each case takes the commands of its file in `commands`.
    """
    import copy
    cases = [args] if asks_test_page(args) else []
    default_args = parser.parse_args([])
    for stretch in stretches:
        loose = parser.parse_args(stretch)
        for dest, value in vars(loose).items():
            if dest not in CASE_FLAGS and value != getattr(default_args, dest):
                sys.exit("--%s belongs to the cartridge and not to a case: it "
                         "goes before the first --case" % dest.replace("_", "-"))
        case = copy.copy(args)
        for dest in CASE_FLAGS:
            setattr(case, dest, getattr(loose, dest))
        if not asks_test_page(case):
            sys.exit("a --case with nothing for the test page to do")
        cases.append(case)
    for case in cases:
        with open(case.test_commands, encoding="utf-8") as fh:
            case.commands = lcf.handwritten_commands(json.load(fh))
    return cases


def case_commands(args, map_id=None):
    """The commands of all the test pages, one after the other.

    It is what the functions that look at the map's pages to decide what the
    cartridge carries —variables, items, members, rain— sweep: a test page is
    one more page.

    With `map_id`, only those of the cases that **run** in that map —see
    `case_map`—: they are the ones that decide what belongs to each map,
    like who walks or which graphics go in its sprite bank.
    """
    return [cmd for case in args.cases
            if map_id is None or case.run_map == map_id
            for cmd in case.commands]


def case_map(case, order, initial):
    """The map where a case runs: that of its `Teleport`, if it starts with
    one, and otherwise the map where the ROM boots.

    It is how a case chooses where to start since step 9e, instead of a
    `--map-id` and a starting cell per cartridge: with RM2k's `Teleport`,
    which is data and not a flag. The page still lives in event 0 of the boot
    map —that is where the ROM finds it and where it runs first—, but what
    comes after the jump runs in the other map, so it is compiled with that
    one's context: its events, the variables its pages look at, its graphics.
    Compiled with the boot map's, a write to a variable only the destination
    looks at didn't ask for a refresh, and the chest of map 133 didn't appear
    even though the variable already held what its page asks for.
    """
    first = case.commands[0] if case.commands else None
    if first is None or first.code != events.TELEPORT:
        return order[initial]
    dest = first.parameters[0]
    if dest not in order:
        sys.exit("%s: the case jumps to map %d, which isn't in the cartridge "
                 "(it carries %s)" % (case.test_commands, dest,
                                      " ".join(str(m) for m in order)))
    return dest


def test_maps(args):
    """The maps where some case runs, which are the ones that carry the
    graphics of `--test-graphic` in their bank."""
    if args.cases:
        return {case.run_map for case in args.cases}
    return {map_order(args)[args.start_index]}


def case_page(case, map_info, songs, graphics, messages, indices, pictures):
    """The bytecode of a case's test page.

    It is compiled like any page of the game, with the context of the map
    where it runs —see `case_map`—; the only thing the converter puts in
    front of it is the `ControlSwitches` that turns it off, which is a
    convention of the harness and not of the case —see
    `events.TEST_SWITCH`—. The troops aren't noted here but at the end,
    in `main`: the test's goes last.
    """
    turn_off = lcf.EventCommand(
        events.CONTROL_SWITCHES, 0, "",
        [events.SWITCH_SINGLE, events.TEST_SWITCH,
         events.TEST_SWITCH, events.SWITCH_ON])
    code = events.compile_page(
        events._Commands([turn_off] + list(case.commands)), indices.get,
        messages, events.MapEvents(map_info["game_map"]).for_event(0), songs,
        graphics, pictures)
    if code is None:
        sys.exit("%s: the test page doesn't compile"
                 % case.test_commands)
    return code

def asks_test_page(args):
    """Whether there is a test page before the first `--case`."""
    return bool(args.test_commands)

def convert_map(renderer, map_id, args):
    """A whole map: tiles, colors, sprites, collision and blocks."""
    game_map = renderer.load_map(
        os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    if args.cases and map_id == map_order(args)[args.start_index]:
        # The test page's event goes **first**: the ROM walks the events from
        # lowest to highest, and the test page has to run before the game's.
        # It builds the party the test starts with, and a map whose page
        # touches the party on entering —21 adds Talan— found it already
        # changed. It is an event without pages: nothing is drawn or compiled,
        # it only takes index 0 so that everything that numbers events after
        # reading the map numbers the same.
        empty = lcf.Event.__new__(lcf.Event)
        empty.id, empty.name, empty.x, empty.y, empty.pages = (
            0, "prueba", 0, 0, [])
        game_map.events.insert(0, empty)
    separate_from_hero(renderer, game_map, args,
                       case_commands(args, map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    layers = converted_layers(renderer, game_map)
    if layers is None:
        sys.exit("can't find the chipset of map %d" % map_id)

    # And the layers again, with the opaque events baked into the map. **Both**
    # are converted and compared because baking adds colors to the
    # background: if that made it merge colors, or shifted the upper layer's
    # CGRAM split, what is seen in cells that have nothing to do with the
    # baking would change. In that case the map goes unbaked, which is the
    # usual. The second conversion isn't paid twice in a warm build: both stay
    # in the disk cache, with their key.
    without_baked = layers
    baked = bakeable_events(renderer, game_map)
    if baked:
        layers, baked = _bake_unless_cgram_moves(
            renderer, game_map, map_id, without_baked, baked)

    # The characters: the hero with its 12 poses because it walks, and each
    # NPC with the one its page declares. If an NPC uses the same character as
    # the hero, they share palette and tiles without anything having to be
    # done.
    #
    # The timer digits take one of the eight sprite palettes, so the ceiling
    # drops to seven. The events drawn with a chipset tile go in while they
    # fit under that ceiling.
    # Who is going to walk and which graphics the routes change to. It goes
    # **before** the palette split because a graphic of command 34 is one
    # more character and asks for a palette like anyone: splitting without
    # counting it, it would come in later and there might be no room.
    order = map_order(args)
    movable, route_graphics, animates_still, turning = movable_events(
        game_map, {m: i for i, m in enumerate(order)}.get,
        associations=args.associations)
    # And the ones from `--test-graphic`, which go only in the maps where
    # some case runs, and for the same reason their pages are compiled with
    # that map's context. They are added **after** the game's, which is the
    # order the real compilation numbers them in.
    if args.test_graphic and map_id in test_maps(args):
        for charset, index in test_graphics(args.test_graphic):
            if (charset, index) not in route_graphics:
                route_graphics.append((charset, index))
    if case_commands(args, map_id):
        # And the ones the test pages send walking, which don't come from
        # `map_pages`: they have to be added by hand or the NPC would
        # walk with a single pose. It goes **before** the palette split: since
        # the palette is chosen over the poses that are seen, knowing who walks
        # is part of choosing the colors and not only of splitting the VRAM.
        # The event goes by its RM2k id and the same `MapEvents` the compilation
        # uses translates it.
        map_events = events.MapEvents(game_map)
        for cmd in case_commands(args, map_id):
            if cmd.code == events.MOVE_EVENT and cmd.parameters \
                    and cmd.parameters[0] != events.ROUTE_HERO:
                target = map_events.route_target(cmd.parameters[0])
                if target:
                    movable = movable | {target - 1}
    # And with that, which poses each graphic can show: it is what decides
    # over which pixels its fifteen colors are chosen. See `map_poses`.
    poses_by_graphic = map_poses(renderer, game_map, args.leaders,
                                 movable, turning, route_graphics,
                                 animates_still)

    # All eight, with or without the timer: its two colors fit in some
    # character's palette. Reserving one for it here took events away from
    # the map, because this number is the one that decides which ones are
    # drawn.
    #
    # **One less in the maps that show battle animations**, since 2026-09-12:
    # the box needs a whole palette just for it —its fifteen colors belong to
    # the animation and are overwritten when another starts— and maps 2 and
    # 3, which are the intro's, filled all eight. Without this the Emitter
    # Room scene was left without its drawing, which is exactly what was
    # being done. What it costs —which characters merge more colors— is said
    # by each map's report.
    sample_animation = map_shows_animation(
        game_map, renderer,
        case_commands(args, map_id))
    # The timer's colors are passed to the split and not only to the packing:
    # in a map that fills the eight palettes someone has to be chosen to lose
    # a color to make room for it, and that changes how that character is
    # quantized.
    timer_colors = ()
    if map_id in args.timer_maps:
        from port import window as window_mod
        timer_colors = sorted(timer_colors_of(window_mod.skin(
            args.game_dir, renderer.database.system_name)))
    singles = {c for c, n in getattr(args, "maps_per_character", {}).items()
               if n == 1}
    palette_cap = map_palette_cap(
        renderer, game_map, args.leaders, route_graphics, timer_colors,
        singles, poses_by_graphic, sample_animation)

    npcs, discarded, split = drawable_npcs(renderer, game_map,
                                           args.leaders, palette_cap,
                                           route_graphics,
                                           timer_colors,
                                           singles,
                                           poses_by_graphic)
    lent = split[5]
    if lent:
        print("  map %d: %d graphic(s) without a palette of their own, drawn "
              "with someone else's: %s" % (map_id, len(lent),
                                          ", ".join(sorted("%s:%d" % k for k in lent))))
    # A baked event that was drawn with someone else's palette can't be
    # hidden: the sprite and the background tile would show different colors
    # —the lent ones and the real ones— and covering it with the second
    # changes what is seen. So that one is unbaked and goes back to being a
    # sprite, with the lent colors: it looks as it would without the baking.
    # It is asked here and not in `bakeable_events` because the lent ones
    # come from the split, which runs after drawing the layers. The first was
    # `PawnDoorTop`, event 11 of map 37: until 2026-09-26 this was a
    # `sys.exit`.
    lent_baked = sorted(
        event for event in baked
        for npc in npcs
        if npc["event"] == event and (npc["charset"], npc["index"]) in lent)
    if lent_baked:
        print("  map %d: event %s is drawn with someone else's palette, so "
              "it isn't baked" % (map_id, ", ".join(str(e + 1)
                                                    for e in lent_baked)))
        for event in lent_baked:
            cell_idx, _tile = baked.pop(event)
            game_map.upper_layer[cell_idx] = rm2k.UPPER_BASE
        layers = without_baked
        if baked:
            layers, baked = _bake_unless_cgram_moves(
                renderer, game_map, map_id, without_baked, baked)
    (tile_data, cram, tilemap, summary), above_data = layers
    if baked:
        print("  map %d: %d opaque event(s) baked into the map: %s"
              % (map_id, len(baked),
                 ", ".join(str(e + 1) for e in sorted(baked))))
    for event, tile in discarded:
        discard_warning(
            "map %d: event %d, drawn with tile %s, doesn't fit in "
            "the %d sprite palettes and isn't drawn"
            % (map_id, event + 1, tile[len(rm2k.TILE_PREFIX):],
               palette_cap),
            changes_graphic(game_map.events[event]))
    # Who changes pose and therefore carries their twelve to the cartridge:
    # the leader candidates with a graphic and the NPCs that walk. In that
    # order, with the initial leader first, which is the order the rest
    # expects.
    actors_with_graphic = []
    for actor in args.leaders:
        a = renderer.database.actors[actor]
        if not sprite_colors(images_of(renderer, args, a.charset),
                             a.charset_index):
            continue            # not a single opaque pixel: it isn't drawn
        actors_with_graphic.append(actor)
    first = renderer.database.leader(args.leaders)   # (CharSet, index)
    animated = []
    for actor in actors_with_graphic:
        a = renderer.database.actors[actor]
        if (a.charset, a.charset_index) not in animated:
            animated.append((a.charset, a.charset_index))
    animated.sort(key=lambda pair: pair != first)   # the initial leader first
    for npc in npcs:
        if npc["event"] in movable \
                and (npc["charset"], npc["index"]) not in animated:
            animated.append((npc["charset"], npc["index"]))
    # And the graphics a command 34 changes to. They go to the bank for the
    # same reason as the ones that walk: after changing, the event keeps
    # walking, so it needs the twelve poses of the new graphic and not the one
    # its page declared.
    #
    # The ones without **a single opaque pixel** don't go in, and it isn't a
    # rare case: `nobodyhere` is 185 of the game's 437 commands 34. A
    # transparent CharSet has no colors, so it has no palette to ask of the
    # bank; and it isn't needed, because what the command does there is hide
    # the row. It is the same `sprite_colors` an actor without a graphic is
    # discarded with.
    graphic_visible = []
    for charset, index in route_graphics:
        # It is drawn if it has an opaque pixel **and** it made it into the
        # palette split. The second is almost always yes; when not, the
        # command hides it just like a transparent one, which is what the ROM
        # does with any graphic that didn't make it.
        graphic_visible.append(
            bool(sprite_colors(images_of(renderer, args, charset), index))
            and (charset, index) in split[1])
        if graphic_visible[-1] and (charset, index) not in animated:
            animated.append((charset, index))
    # And the ones that turn toward the hero: their twelve poses, to upload
    # the one facing it. They go at the end so as not to move anyone else's
    # index.
    for pairs in turning.values():
        for pair in sorted(pairs):
            if pair in split[1] and pair not in animated:
                animated.append(pair)
    off_route = [pair for pair, visible in zip(route_graphics, graphic_visible)
                 if not visible and sprite_colors(
                          images_of(renderer, args, pair[0]), pair[1])]
    for charset, index in off_route:
        discard_warning(
            "map %d: graphic %s:%d, which a route changes to, doesn't fit "
            "in the %d sprite palettes: that command hides the event instead "
            "of changing it" % (map_id, charset, index, palette_cap),
            # A command 34 **is** a graphic change, so it always counts.
            True)

    # The slots of the VRAM bank, one pose each: the hero in block 0 —if some
    # leader candidate has a graphic—, then each NPC that walks with its own,
    # and the still ones shared by (CharSet, index, pose), which never change.
    # An NPC that walks doesn't share even with an identical one: each changes
    # pose on its own.
    slots = []
    if actors_with_graphic:
        charset, index = animated[0]
        slots.append(("heroe", charset, index, INITIAL_POSE))
    for npc in npcs:
        if npc["event"] in movable:
            if npc["changes"]:
                # Two mechanisms on the same row: the cartridge's twelve poses
                # and the page's graphic. The ROM doesn't know both at once, so
                # **walking wins** and its graphic stops following the page. It
                # is the same it did before `collect_npcs` counted "nothing" as
                # a state —see `changes` there—, that is nothing that used to
                # work is lost.
                #
                # This was a `sys.exit`, and it was fine while no event asked
                # for it. Counting the "nothing" state, event 10 of map 8 asks
                # for it, and stopping because of that would be not building
                # the ROM over a detail of an NPC that walks.
                # What **does** follow the page is whether the row is visible:
                # that is bit 4 and it doesn't overwrite the tile. Without
                # separating them, an event that walks and appears with the
                # page never appeared, because the row starts hidden when on
                # loading the map no page qualifies. See `page_graphic` in
                # tools/runtime/event_pages.s.
                npc["aparece"] = True
                npc["changes"] = False
            slots.append((("ev", npc["event"]), npc["charset"],
                          npc["index"], npc["pose"]))
        else:
            # The pose of its row and, if the graphic follows the page, that of
            # each page: the ROM's refresh chooses between slots that are
            # already in VRAM.
            poses = [(npc["charset"], npc["index"], npc["pose"])]
            if npc["changes"]:
                poses += [g for g in npc["graphics"]
                          if g is not None and g[:2] not in npc["afuera"]]
            for key in poses:
                if key not in {r[0] for r in slots}:
                    slots.append((key,) + key)
    # The turn slot: one more pose, for the still one that turns toward the
    # hero. The still ones share a slot by (CharSet, index, pose), so turning
    # its own would also turn the others that use it; the one that turns
    # moves to this one while its page lasts. It is a single one because only
    # the event the hero triggered turns, and there is one at a time. The
    # ones that walk or animate don't need it: they have their own. See TURN
    # in events.py.
    still_turning = [npc for npc in npcs
                     if npc["event"] in turning
                     and npc["event"] not in movable
                     and any(pair in split[1]
                             for pair in turning[npc["event"]])]
    if still_turning:
        npc = still_turning[0]
        slots.append(("giro", npc["charset"], npc["index"], npc["pose"]))
    characters = list(animated)
    for _key, charset, index, _pose in slots:
        if (charset, index) not in characters:
            characters.append((charset, index))

    images = {}
    for charset, _index in characters:
        if charset not in images:
            # Through the renderer's loader, which also builds the CharSet of
            # an event drawn with a chipset tile.
            images[charset] = renderer.charsets.get(charset)
            if images[charset] is None:
                sys.exit("can't find CharSet %r" % charset)

    tiles, palettes, where, palette_of, char_colors = build_characters(
        images, characters, slots, split)
    # It is counted here and not inside because the message has to name the
    # culprit, which is the map. With `drawable_npcs` above this shouldn't
    # fail because of a tile anymore; if it fails it is because of the
    # CharSets.
    if len(palettes) > palette_cap:
        sys.exit("the map uses %d characters in %d palettes and there are %d "
                 "sprite ones" % (len(characters), len(palettes), palette_cap))
    banks = pose_bank(images, animated, char_colors)
    animated_index = {p: k for k, p in enumerate(animated)}
    # The table of command 34: for each graphic a route asks for, which entry
    # of `npc_poses` it is in and with which palette. $FF in the entry is
    # "hide the row", which is what a transparent CharSet does.
    route_gfx = [
        (animated_index[pair], palette_of[pair]) if visible else (0xFF, 0)
        for pair, visible in zip(route_graphics, graphic_visible)]
    # The timer, if this ROM carries it: its glyphs go at the end of the bank
    # and share a palette with whoever has room, which there almost always is.
    timer_base, timer_pal = 0, None
    if map_id in args.timer_maps:
        from port import window as window_mod
        sys_img = window_mod.skin(args.game_dir, renderer.database.system_name)
        tiles, timer_base, timer_pal = timer_digits(
            sys_img, tiles, palettes, split[3],
            palette_cap)
    rain_base, rain_pal = 0, 0
    if args.with_rain:
        tiles, rain_base, rain_pal = rain_drops(
            tiles, palettes, split[3],
            timer_base, palette_cap, timer_pal)
        if not rain_base:
            print("  map %d: WARNING, the raindrops don't fit in the "
                  "sprite palettes and it doesn't rain here" % map_id)
    # The `ShowPicture` picture, if its own belongs to this map. The slot is
    # chosen by `Pictures.choose` **in the order of the map table**, which is
    # this same loop.
    image_base, image_pal = 0, 0
    record = getattr(args, "pictures", None)
    if record is not None:
        info = record.choose([game_map])
        if info is not None and record.map_id is None:
            record.map_id = map_id
        if info is not None and record.map_id == map_id:
            tiles, image_base, image_pal = picture_of_image(
                info, tiles, palettes, rain_base or timer_base)
            if not image_base:
                sys.exit("map %d: the picture %r doesn't fit: the map already uses "
                         "the %d sprite palettes and the fade needs a whole "
                         "one. See `cartel_de_imagen`."
                         % (map_id, record.name, OBJ_PALETTES))
            print("  map %d: the picture %r, %d objects in %d tiles from "
                  "%d, palette %d" % (map_id, record.name,
                                      info["objetos"],
                                      picture.reserved_tiles(info),
                                      image_base, image_pal))
    # And the battle animation box, if some page of this map can show one that
    # is drawn. It goes last because it takes the end of the bank and the
    # palette left free after the picture. The criterion for it to fit is a
    # computation and the converter emits it: if there is no palette or no
    # VRAM, **this map doesn't draw animations** and says so.
    anim_base, anim_pal = 0, 0
    if sample_animation:
        trial, trial_base, trial_pal = map_animation(
            tiles, palettes, 1 if image_base else 0)
        if not trial_base:
            # Without a palette this map doesn't draw animations. It is the
            # same that is done with the raindrops: it is declared and it goes
            # on.
            print("  map %d: WARNING, battle animations aren't drawn "
                  "here: the map already uses the %d sprite palettes and the "
                  "box needs a whole one" % (map_id, OBJ_PALETTES))
        else:
            # The VRAM, instead, **stops**: whether it fits depends on the
            # tile layout and not on the palettes. It stopped because the
            # Python reference couldn't recompute it without redoing the whole
            # bank; without it, it could warn and go on, as with the palettes.
            count = len(trial) // 32
            try:
                layout = vram_layout(len(tile_data) // BYTES_PER_TILE, count,
                                     len(above_data[0]) // 32)
            except SystemExit:
                layout = None
            if layout is None or count > layout["sprites"][1]:
                sys.exit(
                    "map %d: shows battle animations and the %d tiles of its "
                    "box don't fit in the sprite bank: it spends %d of %d. "
                    "See `animacion_de_mapa`."
                    % (map_id, animation_mod.TILES, count,
                       layout["sprites"][1] if layout else 0))
            tiles, anim_base, anim_pal = trial, trial_base, trial_pal
            print("  map %d: battle animations are drawn in %d "
                  "tiles from %d, palette %d"
                  % (map_id, animation_mod.TILES, anim_base, anim_pal))
    # And the rows of the baked events start hidden: their tile is already
    # drawn in the map. The row is still whole —the event triggers, blocks the
    # way and is the target of a route like any other—, and `build_oam` skips
    # it without building an object, which is what is being saved.
    # `tile_pass` is left set on purpose: the cell is already resolved by the
    # map's table with the same bits, and if a page ever showed this row
    # again, the data it needs is there.
    for npc in npcs:
        if npc["event"] in baked:
            npc["visible"] = False
    table = npc_table(npcs, where, movable, animated_index, animates_still)
    # For each leader candidate, its palette and which pose bank its twelve
    # are in. The ROM computes nothing from the pose: it looks up the pointer
    # here and queues it.
    actors = []
    for actor in args.leaders:
        a = renderer.database.actors[actor]
        if actor not in actors_with_graphic:
            # An actor with an empty graphic. `DummyHero`, 10, is like that:
            # its eight poses don't have an opaque pixel, and RM2k draws
            # nothing. It goes with the sentinel pointer and the ROM skips the
            # object.
            actors.append((actor, 0, None, []))
            continue
        # Its colors, in the same order as the `lookup` its poses were packed
        # with: `character_palette` returns the sorted palette and
        # `build_characters` indexes 1..15 over it. If the two orders drifted
        # apart, the hero would come out with its colors swapped around.
        own, _, _ = character_palette(
            images[a.charset], a.charset_index)
        actors.append((actor, palette_of[(a.charset, a.charset_index)],
                       animated_index[(a.charset, a.charset_index)],
                       [cgram_word(c) for c in own]))
    turn_tile = (block_tile(where["giro"][0]) if "giro" in where
                 else TURN_NONE)
    sprite = (tiles, palettes, where, table, actors, timer_base, timer_pal,
              animated, banks, route_gfx, rain_base, rain_pal,
              turn_tile, image_base, image_pal, anim_base, anim_pal)

    # The collision: one byte per 16x16 cell with the four direction bits
    # already resolved. All of RM2k's logic —that the upper layer rules unless
    # it is decoration, that wall faces are always crossed— is decided here,
    # not on the console.
    chipset = renderer.database.chipsets[game_map.chipset_id]
    flags = build_passability(chipset)
    passable = passability_map(game_map, flags)
    # The cells with an NPC are left out: if the hero started on one, both
    # would have the same sort key and which one stays on top would depend on
    # a tie-breaker that has no reason to match between the console and the
    # render. With **all** the ones drawn on some page: a tile left out of the
    # palettes still takes space.
    used = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
    start_x, start_y = map_start(
        renderer, map_id, passable, game_map.width, game_map.height, used)
    collision = (passable, start_x, start_y, game_map.width, game_map.height)

    if len(table) > NPC_MAX:
        sys.exit("map %d has %d NPCs and %d fit in OAM"
                 % (map_id, len(table), NPC_MAX))
    if len(route_gfx) > ROUTE_GFX_MAX:
        sys.exit("map %d has %d graphics of command 34 and %d fit: see "
                 "ROUTE_GFX_MAX" % (map_id, len(route_gfx), ROUTE_GFX_MAX))

    print("Map %d %r: %dx%d cells of %dx%d px"
          % (map_id, name, len(tilemap[0]), len(tilemap),
             CELL, CELL))
    print("  %d distinct colors, %d in CGRAM of %d available, %d merged"
          % (summary["colores"], summary["usados"], summary["presupuesto"],
             summary["fusionados"]))
    print("  %d unique tiles of %d cells (%.0f%% reuse)"
          % (summary["tiles"], summary["celdas"],
             100.0 * (1 - summary["tiles"] / summary["celdas"])))

    print("  sprites: %d characters, %d slots, %d tiles in VRAM, %d palettes; "
          "%d with their twelve poses in the cartridge"
          % (len(characters), len(where), len(tiles) // 32, len(palettes),
             len(animated)))
    print("  %d NPCs with a CharSet out of %d events" % (len(table), len(game_map.events)))

    open_ones = sum(1 for b in passable if b == 0x0F)
    print("  collision: %d cells, %d open on all four sides (%.0f%%), "
          "the hero starts at (%d,%d)"
          % (len(passable), open_ones, 100.0 * open_ones / len(passable),
             start_x, start_y))

    print("  layer above the hero: %d tiles, %d colors in %d palette(s) "
          "from %d, %d merged"
          % (len(above_data[0]) // 32, len(above_data[1]) // 2,
             BG_PALETTES - above_data[3], above_data[3], above_data[4]))

    cells, blocks, block_pass, block_terrain, combos = build_blocks(
        game_map, tilemap, above_data[2], passable,
        game_map.width, game_map.height, chipset)
    print("  the map fits in %d 16x16 blocks for %d cells: %d B of "
          "grid plus %d B of table, against the %d B of the expanded tilemap"
          % (len(blocks) // BLOCK_BYTES, len(cells), 2 * len(cells),
             len(blocks), 2 * summary["celdas"]))
    windows_x = (len(tilemap[0]) + WINDOW_W - 1) // WINDOW_W
    windows_y = (len(tilemap) + WINDOW_H - 1) // WINDOW_H
    if windows_x > 1 or windows_y > 1:
        print("  it doesn't fit in the %dx%d window: the ROM is going to redraw"
              % (WINDOW_W, WINDOW_H))

    words = bytearray()
    for cell in cells:
        words += cell.to_bytes(2, "little")
    colors = bytearray()
    for word in cram:
        colors += word.to_bytes(2, "little")

    return {
        "id": map_id, "nombre": name,
        "tiles": tile_data, "cram": bytes(colors), "cram_words": cram,
        "tilemap": tilemap, "above": above_data, "sprite": sprite,
        # The graphics of command 34 as the pass that builds the bank numbered
        # them. `main()` compares against the ones it gathers compiling for
        # real: if the two passes drifted apart, the bytecode would carry
        # indices of a table that says something else.
        "graficos_de_ruta": route_graphics,
        "collision": collision, "celdas": bytes(words),
        "ev_pos": ev_pos_bytes(game_map),
        # Both grow while the pages are compiled, if some substitutes tiles:
        # see `Substitutions`. That is why they are mutable and are frozen
        # only when emitted.
        "bloques": blocks, "pass": block_pass, "terreno": block_terrain,
        "combos": combos,
        # The terrain of a cell **outside the map**: `GetTerrainTag` uses the
        # ChipSet's index 0, that is the first autotile, and not that of any
        # cell. See `op_terrain`.
        "terreno_fuera": rm2k.terrain_of(chipset, 0),
        "layout": vram_layout(
            len(tile_data) // BYTES_PER_TILE,
            len(sprite[0]) // 32 if sprite else 0,
            len(above_data[0]) // 32),
        "resumen": summary,
        "anim": anim_bytes(summary["animacion"]),
        "imagenes_fondo": summary["imagenes"],
        # The whole map is stored because the events' pages can't be compiled
        # until all the maps are there: a `Teleport` translates map ids to
        # table indices.
        "game_map": game_map,
        # For the page table: where each (CharSet, index, pose) ended up in
        # the sprite bank, which events change graphic with the page and which
        # of their graphics were left out of the palettes.
        "where": where,
        # For the turn toward the hero: which entry of `npc_poses` the twelve
        # poses of each graphic are in, which is the page's +30.
        "giro_k": {pair: animated_index[pair] for pair in animated},
        "giran": set(turning),
        "cambian": {npc["event"] for npc in npcs if npc["changes"]},
        # And the ones that only appear and disappear with it: the ones that
        # walk, whose graphic was pinned further up.
        "aparecen": {npc["event"] for npc in npcs if npc.get("aparece")},
        "afuera": {npc["event"]: npc["afuera"] for npc in npcs},
    }


if __name__ == "__main__":
    main()

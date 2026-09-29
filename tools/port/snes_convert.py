#!/usr/bin/env python3
"""Converts an A Blurred Line map into data the SNES PPU consumes.

Splitting colors into palettes, and merging the least used ones when they
don't fit, lives in `asignador.py`, and reusing mirrored tiles in Voodoo.
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
`rom/pruebas/casos/`; several in one cartridge, each one after a `--caso`, and
the cartridge flags before the first. The harness picks which one runs with
`Partida(caso=k)`:
    rm2k-snes-convert -o … --map-id 6 \
        --comandos-de-prueba rom/pruebas/casos/pan.json \
        --caso --comandos-de-prueba rom/pruebas/casos/pan-vuelve.json
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
# from `port.eventos`.
# `realpath` and not `abspath`: `just herramientas` installs it on the PATH as
# a symlink, and the folder that matters is the one of the real file.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from ensamblado import bancos
from port import tiles_bin
from port import comprimir
from rpgmaker import event_codes
from port import eventos
from rpgmaker import lcf
from rpgmaker import rm2k

# Translucent events carry their own graphic: see `rm2k.decorar_translucido`
# —baked against the background, dithered, or opaque—.
lcf.DECORATE_TRANSLUCENT = rm2k.decorar_translucido
# And the text boxes, rebuilt for the SNES window: see
# `lcf.REFIT_TEXTS` and `port/textos.py`.
from port import textos
lcf.REFIT_TEXTS = textos.reajustar_comandos
from port import animacion as animacion_mod
from port import imagen
from port import asignador
from port import parches as parches_mod
from port import titulo as titulo_mod
from port import menus as menus_mod
from port import pantalla_completa
from port import fin_del_juego as fin_mod
from port import pantallas as pantallas_mod
from port import batalla as batalla_mod
from port import experiencia as X
from port import escena as escena_mod
from port import color as color_mod
from port import constantes
from port import reglas
from port import msu_datos
from audio import efectos_msu
from common import settings
from common import project
from common.parallel import in_parallel
from audio import snes_music
from port.asignador import CELL, tile_colors
from port.formato_snes import cgram_word, entry, pack_tile
from rpgmaker.rm2k import TILE, collect_npcs, hero_start, passability_map
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
# `aplicar_tinte` tints from where the background starts, so the window is
# outside the range without anyone having to remember. In RM2k the tone is
# applied to the map and not to the window.
# **Eight and not seven.** Counting them with `sum(1 for w in cram if w)` gives
# seven because one of the window colors is pure black and its CGRAM word is
# zero. With seven, the ROM drew the text with a color nobody had uploaded and
# the suite caught 79 pixels in the text lines. What rules is the highest
# index the window uses, and `convert_ventana` makes sure of that.
VENTANA_COLORES = 8
CGRAM_RESERVADAS = 1 + VENTANA_COLORES


def bg_budget(first):
    """The colors left for the background below the upper layer.

    The ones at the very bottom don't count: the screen's backdrop color and
    the ones of the message window. See `CGRAM_RESERVADAS`.
    """
    return first * COLORS_PER_PALETTE - CGRAM_RESERVADAS


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
# screen, the same numbers as `tools/port/ventana.py`.
VENTANA_COLS_INC, VENTANA_FILAS_INC = 32, 10

# The glyph, which is what the ROM composes. The same numbers as
# `tools/port/fuente.py`, which is generated from easyrpg-player.
FUENTE_ANCHO, FUENTE_ALTO = 6, 12

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


def tiles_cuantizados(image):
    """The image split into 8x8 cells of 15-bit colors, which is what the PPU
    shows: a grid of rows of cells, each cell a tuple of eight rows of eight
    colors. A transparent pixel stays as None and ends up at index 0 of the
    palette, which the PPU doesn't draw.

    With numpy: the colors and the cells come from arrays, and each distinct
    cell is built as a tuple **only once** —the same object at every place of
    the map where it repeats—. Large maps are millions of pixels and a few
    thousand distinct cells, and building it pixel by pixel in Python was the
    most expensive part of converting their layers. `_colores_de` relies on
    repeated cells being the same object.
    """
    pixeles = numpy.asarray(image.convert("RGBA"))
    alto, ancho = len(pixeles) // CELL, len(pixeles[0]) // CELL
    pixeles = pixeles[:alto * CELL, :ancho * CELL].astype(numpy.int32)
    codigos = numpy.where(pixeles[:, :, 3] == 0, -1,
                          ((pixeles[:, :, 0] >> 3) << 10)
                          | ((pixeles[:, :, 1] >> 3) << 5)
                          | (pixeles[:, :, 2] >> 3)).astype(numpy.int32)
    celdas = numpy.ascontiguousarray(
        codigos.reshape(alto, CELL, ancho, CELL).transpose(0, 2, 1, 3)
    ).reshape(alto * ancho, CELL * CELL)
    unicas, cual = numpy.unique(
        celdas.view(numpy.dtype((numpy.void, celdas.itemsize * CELL * CELL))),
        return_inverse=True)
    unicas = unicas.view(numpy.int32).reshape(-1, CELL * CELL)
    colores = {-1: None}
    for c in numpy.unique(unicas).tolist():
        if c >= 0:
            colores[c] = (c >> 10, (c >> 5) & 31, c & 31)
    armadas = [tuple(tuple(colores[c] for c in fila[y * CELL:(y + 1) * CELL])
                     for y in range(CELL))
               for fila in unicas.tolist()]
    return [[armadas[k] for k in fila]
            for fila in cual.reshape(alto, ancho).tolist()]


def _colores_de(grillas):
    """How many pixels of each color there are in these grids, without the
    transparent ones: a `Counter` with the colors **in the order in which
    they appear**, walking cell by cell and row by row, which is the order it
    had when counting them pixel by pixel.

    It counts each distinct cell once and multiplies it by how many times it
    occurs, and "distinct" is by identity: the repeated cells from
    `tiles_cuantizados` are the same object. With other grids it gives the
    same result, slower.
    """
    veces = {}
    for grilla in grillas:
        for fila in grilla:
            for celda in fila:
                visto = veces.get(id(celda))
                if visto is None:
                    veces[id(celda)] = [celda, 1]
                else:
                    visto[1] += 1
    counts = collections.Counter()
    for celda, n in veces.values():
        for linea in celda:
            for p in linea:
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
    filas = numpy.packbits(bits, axis=2, bitorder="big")[:, :, 0, :]
    ppu = filas.reshape(-1, CELL, planes // 2, 2).transpose(0, 2, 1, 3)
    datos = numpy.ascontiguousarray(ppu).reshape(len(tiles), planes * 8)
    return [bytes(fila) for fila in datos]


def repartir_encima(grid, limite):
    """Which palettes the upper layer takes, with `limite` as the cap.

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
    groups = asignador.try_pack(sets, limite) if sets else []
    merged = []
    if sets and groups is None:
        # Splitting doesn't fit. There are two reasons and they used to be
        # confused as one: that the colors are too many for the palettes
        # granted, or that a single tile has more than 15, which fits in no
        # palette however many it is given. No split fixes the second one.
        #
        # Both are fixed by the same thing: merging the least used color with
        # its nearest neighbor and retrying.
        grid, groups, merged, _ = asignador.reduce_colors(grid, limite)
    return grid, [sorted(g) for g in groups], merged


def imagen_encima(grid, palettes, above_first):
    """The upper layer as the allocator leaves it: an indexed PNG.

    Its indices are **CGRAM entries**: color `k` of palette `i` of this layer
    is entry `(above_first + i) * 16 + k + 1`, and transparent is 0. That way
    what was decided —which palette each cell takes and where each one
    starts— is written in the image, and can be looked at without building the
    ROM.
    """
    columnas, filas = len(grid[0]), len(grid)
    ancho = columnas * CELL
    pixeles = [0] * (ancho * filas * CELL)
    posicion = [{color: k + 1 for k, color in enumerate(p)} for p in palettes]
    for cy, row in enumerate(grid):
        for cx, tile in enumerate(row):
            colors = tile_colors(tile)
            if not colors:
                continue
            # The first palette that has all its colors, which is the same
            # count `repartir_encima` did when building them.
            i = next(i for i, pal in enumerate(palettes) if colors <= set(pal))
            base = (above_first + i) * COLORS_PER_PALETTE
            for y, line in enumerate(tile):
                fila = (cy * CELL + y) * ancho + cx * CELL
                for x, color in enumerate(line):
                    if color is not None:
                        pixeles[fila + x] = base + posicion[i][color]
    colores = [None] * 256
    for i, palette in enumerate(palettes):
        base = (above_first + i) * COLORS_PER_PALETTE
        colores[base] = BACKDROP
        for k in range(COLORS_PER_PALETTE - 1):
            colores[base + k + 1] = palette[k] if k < len(palette) else (0, 0, 0)
    return tiles_bin.png_indexado(
        ancho, filas * CELL, pixeles, colores,
        [e % COLORS_PER_PALETTE == 0 for e in range(256)])


def convert_above(grid, palettes, above_first, merged=0):
    """The layer that goes above the hero: 4-bit tiles and their tilemap.

    It is much smaller than the lower one —in Map0073 it is 419 cells of 900,
    with seven colors— so it almost always fits in one or two palettes. Empty
    cells point to tile 0, which is left transparent on purpose.

    **It decides nothing**: the palettes were chosen by `repartir_encima`, and
    which CGRAM palette it starts at, `above_first`, was chosen by
    `_convert_layers`. With that it writes the indexed image and `tiles`
    converts it.

    Returns (tiles, CGRAM words, tilemap, first palette, merged, the
    allocator's image).
    """
    png = imagen_encima(grid, palettes, above_first)
    tiles, cgram, tilemap, _ = tiles_bin.convertir(
        png, 4, len(grid[0]), prioridad=PRIORITY_ABOVE)
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
POSE_INICIAL = 2 * 3 + 1           # facing down, the middle frame
OBJ_PALETTES = 8                   # 8 to 15, with or without the timer

# The OAM name table is 16 tiles wide, so a 32x32 object doesn't take 16 tiles
# in a row but a 4x4 block inside that grid.
OBJ_ROW = 16


def pose_origin(index, pose):
    """Where a pose starts inside the CharSet."""
    return ((index % 4) * SPRITE_W * 3 + (pose % 3) * SPRITE_W,
            (index // 4) * SPRITE_H * 4 + (pose // 3) * SPRITE_H)


TODAS_LAS_POSES = frozenset(range(SPRITE_POSES))


def sprite_colors(image, index, poses=None):
    """The character's colors, with how many pixels each one uses.

    `poses` are the ones the event can end up showing. **Counting all twelve
    when one is seen gives away CGRAM entries**: the save point in Lashe City
    animates facing up and nothing else, and its twelve poses together have
    41 colors against the 13 of those three frames. The 26 of difference were
    all merged, and the first to go were the blue and white of the glow —few
    pixels each— against the grays that cover the rest of the block.

    Who can show what is decided by `poses_del_mapa`, which is the same pass
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
    bloque = numpy.asarray(image.crop((base_x, base_y,
                                       base_x + SPRITE_W * 3,
                                       base_y + SPRITE_H * 4)))
    vistos = numpy.concatenate([
        bloque[(pose // 3) * SPRITE_H:(pose // 3 + 1) * SPRITE_H,
               (pose % 3) * SPRITE_W:(pose % 3 + 1) * SPRITE_W].reshape(-1, 4)
        for pose in (sorted(TODAS_LAS_POSES) if poses is None
                     else sorted(poses))])
    return _contar_colores(vistos)


def _contar_colores(pixeles):
    """A Counter of the 15-bit colors of the opaque RGBA pixels.

    **The keys come in the order in which they appear**, which is the one the
    `Counter` built pixel by pixel had: whoever walks it
    —`merge_least_visible` breaks ties by that order— has to see the same.
    """
    opacos = pixeles[pixeles[:, 3] != 0, :3] >> 3
    codigos = ((opacos[:, 0].astype(numpy.int32) << 10)
               | (opacos[:, 1].astype(numpy.int32) << 5) | opacos[:, 2])
    unicos, primero, cuantos = numpy.unique(codigos, return_index=True,
                                            return_counts=True)
    counts = collections.Counter()
    for k in numpy.argsort(primero, kind="stable").tolist():
        c = int(unicos[k])
        counts[(c >> 10, (c >> 5) & 31, c & 31)] = int(cuantos[k])
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


def paleta_del_personaje(image, index, tope=None, poses=None):
    """A character's palette, and how to map each color to its index.

    It is the same computation for the image that goes to VRAM and for the
    cartridge's pose bank, and it has to be: a pose uploaded on the fly is
    drawn with the palette already in CGRAM.

    `tope` lowers the number of colors below fifteen, and exists to make room
    for the timer: its digits are two colors and black is usually already
    there, so one entry is enough. **Who pays for it and how much is decided
    by `npcs_dibujables`**, which is the only one that sees all the palettes
    of the map; here it is only obeyed. If the converter chose it here, two
    calls for the same character could give different palettes and the
    cartridge's poses wouldn't match the CGRAM.

    `poses` are the ones the event can show: **the fifteen colors are chosen
    looking only at those**, which is where almost all of the save point's
    color gain comes from. Same as `tope`, `npcs_dibujables` decides it and
    here it is only obeyed.

    The returned `mapping` still covers **all** the colors of the twelve-pose
    block, not only those of `poses`: the ones left out of the count go to
    the nearest of the survivors. It is not defensive decoration —it is what
    keeps `pose_tiles` from dying with a KeyError if someone asks for one pose
    too many—, and it costs one computation per color.
    """
    tope = OBJ_COLORS if tope is None else tope
    counts = sprite_colors(image, index, poses)
    if len(counts) <= tope:
        mapping = {c: c for c in counts}
    else:
        mapping, _ = asignador.merge_least_visible(counts, tope)
    palette = sorted(set(mapping.values()))
    if poses is not None and palette:
        for color in sprite_colors(image, index):
            if color not in mapping:
                mapping[color] = min(
                    palette, key=lambda p, c=color: (asignador.luma_distance(p, c), p))
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
    pixeles = numpy.asarray(image.crop((ox, oy, ox + SPRITE_W,
                                        oy + SPRITE_H)))
    rgb = pixeles[:, :, :3] >> 3
    codigos = ((rgb[:, :, 0].astype(numpy.int32) << 10)
               | (rgb[:, :, 1].astype(numpy.int32) << 5) | rgb[:, :, 2])
    opaco = pixeles[:, :, 3] != 0
    unicos, cual = numpy.unique(codigos[opaco], return_inverse=True)
    indices = numpy.array(
        [lookup[mapping[(c >> 10, (c >> 5) & 31, c & 31)]]
         for c in unicos.tolist()], dtype=numpy.uint8)
    pose_entera = numpy.zeros((OBJ_H, OBJ_W), dtype=numpy.uint8)
    margen = (OBJ_W - SPRITE_W) // 2
    centro = numpy.zeros((SPRITE_H, SPRITE_W), dtype=numpy.uint8)
    centro[opaco] = indices[cual]
    pose_entera[:SPRITE_H, margen:margen + SPRITE_W] = centro
    tiles = pose_entera.reshape(4, CELL, 4, CELL).swapaxes(1, 2).reshape(
        16, CELL, CELL)
    return pack_tiles(tiles, planes=4)


def cambia_de_grafico(evento):
    """Whether some page of the event draws something different from another.

    It is what separates an annoying discard from one that breaks the game. A
    decorative single-page event that isn't drawn is just lost —the
    `CoreBlood` of map 3, the four `Link`s—. One that **changes graphic** is a
    mechanism: a door that opens, a machine that turns on. If it isn't drawn,
    the change is never seen, and since the event still blocks the way, what is
    left is an invisible wall the player expected to open.
    """
    graficos = {((getattr(p, "character_name", "") or "").strip(),
                 p.character_index) for p in evento.pages}
    return len(graficos) > 1


def aviso_de_descarte(texto, peligroso):
    """An event that isn't drawn. If it is one of those that break, it stops
    the conversion.

    **And it stops on purpose.** This was a `print` among fifty others, and on
    2026-09-07 it cost an afternoon: `demo-apertura` was built with the timer,
    map 2 lost event 30 —the middle cell of the door Core breaks— and the
    warning went by unnoticed in the build output. taro reached the cutscene,
    the door didn't change tile and he couldn't get through.

    It is the same criterion as `entrar_en_panico` in the ROM: something that
    shouldn't happen is not discarded silently. The difference is where the
    noise is made. A discard is decided **when converting**, and by the time
    the ROM runs the event is no longer in any table: there is nothing left
    for the console to look at. Making it blow up when loading the map would be
    the same as not building the ROM, but later and without being able to say
    which event.

    Stopping on **all** discards doesn't work either: today there are
    decorative ones that don't fit in several maps, so every recipe would have
    to ask to continue and the stop wouldn't protect against anything. That is
    why the cap is `cambia_de_grafico`, which is exactly the class event 30
    belonged to.

    There is no way to ask it to continue: there was a `--descartar-eventos`,
    and it went away in step 9e, when no cartridge discarded anything that
    needed it anymore.
    """
    if not peligroso:
        print("  " + texto)
        return
    sys.exit(
        "%s\n\n"
        "The ROM is not built: that event **changes graphic between its pages**,\n"
        "that is, it is a mechanism and not decoration. Without being drawn, the\n"
        "change is never seen, and since the event still blocks the way and\n"
        "triggers, what is left is an invisible wall where the game expected a door." % texto)


# --- the weight of a graphic ------------------------------------------------
#
def peso_de_grafico(charset):
    """How much a CharSet weighs when splitting the sprite palettes: the one
    that weighs is served first, and the one that doesn't arrives in map order
    and may end up with someone else's palette. The game decides it, in
    `[graphics.palette_weight]` of the project file, with its reasons. The
    `~trama` suffix of translucent ones doesn't count: the weight belongs to
    the drawing."""
    pesos = settings.value("graphics", "palette_weight", kind=dict)
    return pesos.get((charset or "").split(rm2k.TRAMA_SUFIJO)[0], 0)


def fila_de_pose(pose):
    """The three frames of the walking cycle for the direction of `pose`.

    An event that animates standing still changes column and **never row**: the
    ROM builds its pose as `mirada_de_fila * 3 + columna` in `animar_quietos`,
    so of the twelve it can only show these three.
    """
    return frozenset(range(pose // 3 * 3, pose // 3 * 3 + 3))


def poses_del_mapa(renderer, game_map, lideres, movibles=(), giran=(),
                   graficos_de_ruta=(), anima_quieto=()):
    """Which poses each (CharSet, index) can end up showing in this map.

    Each character's palette comes from here: fifteen colors chosen over what
    is seen and not over the twelve poses of the block. The list of who needs
    all twelve is **the same** that already decided which poses go to the
    cartridge and to VRAM —see `eventos_movibles` and how `ranuras` is built in
    `convertir`—, and it has to be: a pose the ROM uploads and the palette
    didn't count is drawn with colors that aren't its own.

    These take all twelve:

    * the leader candidates, because the hero walks;
    * the events in `movibles` that **walk**;
    * the graphics in `giran`, because one that turns toward the hero can end
      up in any of the four directions;
    * the graphics of command 34, which keep walking after the change.

    One that **animates standing still** keeps the three frames of its
    direction, which is all `animar_quietos` can put on screen: it changes
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

    def sumar(clave, cuales):
        anterior = poses.get(clave)
        poses[clave] = TODAS_LAS_POSES if (anterior is TODAS_LAS_POSES
                                           or cuales is TODAS_LAS_POSES) \
            else frozenset(anterior or ()) | frozenset(cuales)

    for actor in lideres:
        a = renderer.database.actors[actor]
        sumar((a.charset, a.charset_index), TODAS_LAS_POSES)
    for pares in (giran.values() if hasattr(giran, "values") else giran):
        for par in pares:
            sumar(tuple(par), TODAS_LAS_POSES)
    for par in graficos_de_ruta:
        sumar(tuple(par), TODAS_LAS_POSES)
    for npc in collect_npcs(game_map):
        clave = (npc["charset"], npc["index"])
        # Animates standing still and doesn't walk: the three frames of its
        # row. If it is also in `giran` it already took all twelve above, so
        # the turn doesn't run out of colors.
        quieto_animado = (npc["evento"] in anima_quieto
                          and npc["evento"] in movibles)
        if quieto_animado:
            propias = fila_de_pose(npc["pose"])
        elif npc["evento"] in movibles:
            propias = TODAS_LAS_POSES
        else:
            propias = frozenset((npc["pose"],))
        sumar(clave, propias)
        if npc["cambia"]:
            for grafico in npc["graficos"]:
                if grafico is not None:
                    # An event that walks and also changes graphic loses the
                    # change —walking wins, see `convertir`—, but the page's
                    # graphic still asks for a palette here, so the pose it
                    # declares is counted.
                    sumar(grafico[:2],
                          fila_de_pose(grafico[2]) if quieto_animado
                          else TODAS_LAS_POSES if npc["evento"] in movibles
                          else (grafico[2],))
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
# exactly the ones `rm2k.pasabilidad_del_tile` made the event's row impose; and
# `pasa_con_evento`, in tools/runtime/heroe.s, skips hidden rows. That is, the
# baking hands the same table answer over to the map. It is guarded by
# `rom/pruebas/herramientas/test_horneados.py`.
#
# What is **not** saved yet: its sprite palette and its VRAM slot. The event
# still enters the `npcs_dibujables` split as if it were drawn, on purpose:
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
COMANDOS_QUE_MUEVEN = (eventos.MOVE_EVENT, eventos.CHANGE_EVENT_LOCATION,
                       eventos.TRADE_EVENT_LOCATIONS, eventos.FLASH_SPRITE)


def _alfas_del_tile(atlas, indice):
    """The alpha of the 16x16 pixels of upper-layer tile `indice`."""
    from PIL import Image
    tile = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    atlas.render_tile(tile, 0, 0, rm2k.UPPER_BASE + indice)
    return tile.getchannel("A").tobytes()


def eventos_horneables(renderer, game_map):
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
      makes it flash (see `COMANDOS_QUE_MUEVEN`);
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
    layer and `capas_animadas` renders all of them from there. What is lost is
    the animation the opaque tile already covered.
    """
    atlas = renderer.atlas_por_nombre(getattr(game_map, "chipset_nombre", None))
    flags = getattr(game_map, "pasabilidad_tiles", None)
    if atlas is None or flags is None:
        return {}
    # That tile 0 of the upper layer —the one an empty cell carries— draws
    # nothing is checked, not assumed: it is what makes putting the event's
    # tile there cover nothing. The ChipSets of this game satisfy it; one that
    # doesn't leaves the map without baked events instead of changing what is
    # seen.
    if any(_alfas_del_tile(atlas, 0)):
        return {}
    # The events that some page moves, flashes or sends walking. It goes by
    # the RM2k id, which is what the commands carry, and it is translated by
    # the same `eventos.Eventos` the compilation uses.
    del_mapa = eventos.Eventos(game_map)
    tocados = set()
    for evento in game_map.events:
        for page in evento.pages:
            for cmd in page.commands:
                if cmd.code in COMANDOS_QUE_MUEVEN and cmd.parameters:
                    blanco = del_mapa.blanco(cmd.parameters[0])
                    if blanco:
                        tocados.add(blanco - 1)
    # And the ones that walk on their own: `move_type` set to anything other
    # than still, or an own route on some page.
    caminan = {numero for numero, evento in enumerate(game_map.events)
               if any(p.move_type or p.move_route.commands
                      for p in evento.pages)}
    opacos = {}
    horneables = {}
    for npc in collect_npcs(game_map):
        numero = npc["evento"]
        base = rm2k.sin_horneado(npc["charset"])
        if not base.startswith(rm2k.TILE_PREFIX) or not npc["visible"]:
            continue
        if npc["cambia"] or numero in caminan or numero in tocados:
            continue
        paginas = game_map.events[numero].pages
        if paginas[0].condition.active:
            continue
        # All its pages have to draw the same thing, on the same layer and
        # without continuous animation, and not only the active one: the row
        # is hidden for the whole playthrough, so what decides is what the
        # event **can end up** drawing. Half of
        # `test_hornear_no_cambia_la_pasabilidad_de_la_celda` comes for free
        # from this: with the same graphic and the same layer on all of them,
        # `pasabilidad_del_tile` gives the same on all of them.
        if set(npc["graficos"]) != {npc["graficos"][0]} \
                or npc["graficos"][0] is None:
            continue
        if set(npc["capas"]) != {rm2k.LAYER_BELOW}:
            continue
        if any(p.animation_type in rm2k.ANIMA_CONTINUO for p in paginas):
            continue
        indice = int(base.rsplit(":", 1)[1])
        if not indice:
            continue                    # tile 0 is "no graphic"
        tile = rm2k.UPPER_BASE + indice
        if flags[tile] & rm2k.PASS_ABOVE:
            continue                    # it would go above the hero
        celda = npc["y"] * game_map.width + npc["x"]
        if game_map.upper_layer[celda] != rm2k.UPPER_BASE:
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
        if npc["tile_pasa"] & ~rm2k.pasa_de_celda(
                flags, game_map.lower_layer[celda],
                game_map.upper_layer[celda]):
            continue
        if indice not in opacos:
            opacos[indice] = all(a == 255 for a in _alfas_del_tile(atlas, indice))
        if not opacos[indice]:
            continue
        horneables[numero] = (celda, tile)
    return horneables


def _mismo_reparto_de_cgram(sin, con):
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
    if con is None:
        return False
    (_, _, _, antes), encima_antes = sin
    (_, _, _, ahora), encima_ahora = con
    return (encima_antes == encima_ahora
            and antes["presupuesto"] == ahora["presupuesto"]
            and antes["fusionados"] == ahora["fusionados"])


def _hornear_si_no_mueve_la_cgram(renderer, game_map, map_id, sin_horneado,
                                  horneados):
    """Bakes `horneados` and returns (layers, baked): the baked ones if the
    CGRAM split didn't move, and otherwise those of `sin_horneado`, with none.
    See `_mismo_reparto_de_cgram`."""
    hornear_en_el_mapa(game_map, horneados)
    con_horneado = capas_convertidas(renderer, game_map)
    if _mismo_reparto_de_cgram(sin_horneado, con_horneado):
        return con_horneado, horneados
    print("  map %d: baking %d event(s) moved its CGRAM split, "
          "so they are drawn" % (map_id, len(horneados)))
    for celda, _tile in horneados.values():
        game_map.upper_layer[celda] = rm2k.UPPER_BASE
    return sin_horneado, {}


def hornear_en_el_mapa(game_map, horneables):
    """Puts the tile of each baked event into the map's upper layer.

    It is done on the `game_map` and not on the drawn image, and that solves
    three things at once: the layers are drawn from here —so the drawings of
    the ChipSet animation come out baked too—, the layer cache key carries the
    upper layer, so it changes by itself, and the cell's passability is
    resolved by `passability_map` with the tile's bits, which are the same the
    event's row imposed.
    """
    for celda, tile in horneables.values():
        game_map.upper_layer[celda] = tile


def npcs_dibujables(renderer, game_map, lideres, tope, graficos_de_ruta=(),
                    timer_colores=(), solo_aqui=None, poses=None):
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
    paletas = []
    paleta_de = {}
    # Who had to be lent someone else's palette. They show up in the
    # converter's report: they don't break anything, but they are seen with
    # colors that aren't their own.
    prestadas = set()
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
    de_lider = set()
    # Which poses each graphic can show, which is what its fifteen colors are
    # chosen over. Without it they are the usual twelve.
    poses = dict(poses or {})

    def cabe(charset, index, forzar, lider=False):
        palette, _, _ = paleta_del_personaje(renderer.charsets.get(charset),
                                             index,
                                             poses=poses.get((charset, index)))
        for numero, existente in enumerate(paletas):
            if numero in de_lider and not lider:
                continue
            union = existente + [c for c in palette if c not in existente]
            if len(union) <= OBJ_COLORS:
                paletas[numero] = union
                paleta_de[(charset, index)] = numero
                return True
        if forzar or len(paletas) < tope:
            if lider:
                de_lider.add(len(paletas))
            paleta_de[(charset, index)] = len(paletas)
            paletas.append(list(palette))
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
        cuenta = sprite_colors(renderer.charsets.get(charset), index)
        mejor = None
        for numero, existente in enumerate(paletas):
            if numero in de_lider:
                continue        # the ROM overwrites those with the leader's colors
            costo = sum(v for c, v in cuenta.items() if c not in existente)
            if mejor is None or costo < mejor[0]:
                mejor = (costo, numero)
        if mejor is None:
            return False        # there isn't a single non-leader palette
        paleta_de[(charset, index)] = mejor[1]
        prestadas.add((charset, index))
        return True

    npcs = collect_npcs(game_map)

    def claves(npc):
        """The (CharSet, index) pairs the NPC can end up drawing: its row's
        and, if the graphic follows the page, those of all its pages."""
        salida = [(npc["charset"], npc["index"])]
        if npc["cambia"]:
            salida += [g[:2] for g in npc["graficos"] if g is not None]
        return salida

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
    de_npc = {c for npc in npcs for c in claves(npc)}
    vistos, ranura_lider, propios = set(), None, set()
    for actor in lideres:
        a = renderer.database.actors[actor]
        clave = (a.charset, a.charset_index)
        if clave in vistos or not sprite_colors(
                renderer.charsets.get(a.charset), a.charset_index):
            continue
        vistos.add(clave)
        if clave in de_npc or ranura_lider is None:
            cabe(a.charset, a.charset_index, True, lider=True)
            if clave not in de_npc:
                ranura_lider = paleta_de[clave]
        else:
            # To the shared slot, and with **its own** colors: its poses are
            # packed with its sorted palette, which is the one the ROM uploads
            # when its turn to lead comes.
            paleta_de[clave] = ranura_lider
            propios.add(clave)

    # The CharSets of the pages **are no longer forced**. They were forced so
    # that a character never ran out of palette, and the price was that a map
    # with more characters than palettes didn't convert: map 8 asked for nine
    # out of eight and the Hover-Tram asks for eleven. With the lending in
    # `cabe` that is no longer needed —whoever doesn't fit is drawn with
    # someone else's— and no map fails because of this.
    #
    # The only one still forced is the leader: the hero is on screen all the
    # time and is the one where it would show the most.
    #
    # The order is the map's, **except the ones with weight**: see `peso_de_grafico`.
    for npc in sorted(npcs, key=lambda n: -peso_de_grafico(n["charset"])):
        for clave in claves(npc):
            if clave not in vistos and not clave[0].startswith(rm2k.TILE_PREFIX):
                vistos.add(clave)
                cabe(clave[0], clave[1], False)
    # And the ones from command 34, after the NPCs and before the tiles.
    # **While they fit**, like the tiles and not like a page's CharSets: forcing
    # them broke three maps of the game —108, 114 and 207 asked for nine
    # palettes out of eight— and breaking a map that converts today is worse
    # than not drawing a graphic change. The one that doesn't fit isn't drawn,
    # which is the same that already happens with a page whose graphic didn't
    # fit. Transparent ones don't even ask for a palette.
    for clave in graficos_de_ruta:
        if clave not in vistos and sprite_colors(
                renderer.charsets.get(clave[0]), clave[1]):
            vistos.add(clave)
            cabe(clave[0], clave[1], False)
    # The timer **before the events drawn with a chipset tile**. Its two colors
    # go to the first palette with room and are reserved there;
    # `digitos_del_timer` later finds them in place and adds nothing.
    #
    # The order matters and until now it was reversed by accident. A tile event
    # goes in "while it fits" —that is how it is written a few lines below, and
    # the one that doesn't fit isn't drawn—, while the timer is HUD and is on
    # screen always. In map 8 chipset tile 118, which is two colors, went into
    # the save point's palette and left it at fourteen: the timer no longer fit
    # anywhere and a whole character had to lose a color to make room for it.
    # Serving it first, nothing is merged and the tile settles in another
    # palette.
    if timer_colores:
        for numero, existente in enumerate(paletas):
            if numero in de_lider:
                continue        # the ROM overwrites those with the leader's colors
            union = existente + [c for c in timer_colores if c not in existente]
            if len(union) <= OBJ_COLORS:
                paletas[numero] = union
                break

    entran, afuera, salida, descartados = set(), set(), [], []
    for npc in npcs:
        for clave in claves(npc):
            if clave in vistos or clave in entran or clave in afuera:
                continue
            if cabe(clave[0], clave[1], False):
                entran.add(clave)
            else:
                afuera.add(clave)
        # The ones left out aren't drawn, from anywhere: the row is hidden if
        # it is its own, and the page that asks for it comes out with no
        # graphic.
        npc["afuera"] = {c for c in claves(npc) if c in afuera}
        descartados += [(npc["evento"], c[0]) for c in sorted(npc["afuera"])]
        if (npc["charset"], npc["index"]) in afuera:
            npc["visible"] = False
            npc["tile_pasa"] = None
            if not npc["cambia"]:
                continue
            # The row stays for the other pages, hidden, and its fields move to
            # the first of them that fits: it is the slot it starts with. If
            # none fits, the event is never drawn.
            otra = next((g for g in npc["graficos"]
                         if g is not None and g[:2] not in afuera), None)
            if otra is None:
                continue
            npc["charset"], npc["index"], npc["pose"] = otra
        salida.append(npc)
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
    topes = {}
    # Only if it really has nowhere to go: not a palette with room **nor a free
    # slot**. Without looking at the free slots, this took two colors off
    # `People4:5` in map 5 —16.85% of its pixels— when the map uses four
    # palettes of the eight and the timer had a whole one to spare.
    if timer_colores and len(paletas) >= OBJ_PALETTES and not any(
            n not in de_lider
            and len(set(p) | set(timer_colores)) <= OBJ_COLORS
            for n, p in enumerate(paletas)):
        solos = collections.Counter()
        for clave, n in paleta_de.items():
            solos[n] += 1
        mejor = None
        for clave, n in paleta_de.items():
            if n in de_lider or solos[n] != 1 or clave[0].startswith(
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
            ajeno = solo_aqui is not None and clave not in solo_aqui
            cuenta = sprite_colors(renderer.charsets.get(clave[0]), clave[1],
                                   poses.get(clave))
            if not cuenta:
                continue
            faltan = len([c for c in timer_colores if c not in paletas[n]])
            nuevo_tope = OBJ_COLORS - faltan
            m, _ = asignador.merge_least_visible(cuenta, nuevo_tope)
            movidos = sum(v for c, v in cuenta.items() if m[c] != c)
            costo = (ajeno, movidos / float(sum(cuenta.values())), clave)
            if mejor is None or costo < mejor[0]:
                mejor = (costo, clave, n, nuevo_tope, sorted(set(m.values())))
        if mejor is not None:
            _costo, clave, n, nuevo_tope, paleta_nueva = mejor
            print("  to make room for the timer, %s:%d drops to %d colors "
                  "(%.2f%% of its pixels)%s"
                  % (clave[0], clave[1], nuevo_tope, 100 * _costo[1],
                     ", and with a pose bank of its own" if _costo[0] else ""))
            paletas[n] = paleta_nueva
            topes[clave] = nuevo_tope

    # The split is returned so `build_characters` uses it as is: a second
    # first-place-that-fits in another order can give a different count, and
    # it did: map 8 fit here in eight palettes and there asked for nine.
    return salida, descartados, (paletas, paleta_de, propios, de_lider,
                                 topes, prestadas, poses)


def build_characters(images, personajes, ranuras, reparto):
    """The sprite bank that goes to VRAM: one pose per slot.

    `personajes` is the list of (charset, index) that need a palette, in the
    order they are handed out; `ranuras` that of (key, charset, index, pose), a
    block of 16 tiles for each one and in that order. Since 2026-09-05 what
    goes here is **one pose per slot** and nothing else: the twelve of the
    walkers live in the cartridge —see `banco_de_poses`— and are uploaded on
    the fly. They all used to go here, and the opening scene asked for 768
    tiles of the 512 the PPU addresses.

    **Palettes are not decided here**: they arrive in `reparto`, which is what
    `npcs_dibujables` decided for the whole map. Here only the index of each
    color inside its own is built. Until 2026-09-17 there was also a split of
    its own, first-that-fits, for when none arrived; nobody used it, and a
    second split in another order had already given a different count —map 8
    fit there in eight palettes and here asked for nine—.

    Returns (tiles, palettes, location, paleta_de): location maps the slot's
    key to (block, palette), and paleta_de each (charset, index) to its
    palette.
    """
    tiles = bytearray()
    colores = {}
    palettes = [list(p) for p in reparto[0]]
    paleta_de = dict(reparto[1])
    # The ones that share the leader's slot: their `lookup` comes from **their**
    # palette and not from the slot's, because the ROM will upload their colors
    # there when their turn to lead comes. See `npcs_dibujables`.
    propios = set(reparto[2])
    # And who had their number of colors lowered so the timer would fit. It has
    # to be the same number `npcs_dibujables` used: if here it were quantized
    # with fifteen, the cartridge's poses wouldn't match the palette the ROM
    # uploads to CGRAM.
    topes = dict(reparto[4])
    # And which poses each one can show, which is what their fifteen colors
    # were chosen over there. It has to be the same set: with another one, the
    # palette the ROM uploads to CGRAM and the tiles packed here would come
    # from two different computations.
    poses_de = dict(reparto[6])
    for charset, index in personajes:
        if (charset, index) in colores:
            continue
        palette, lookup, mapping = paleta_del_personaje(
            images[charset], index, topes.get((charset, index)),
            poses=poses_de.get((charset, index)))
        if (charset, index) not in paleta_de:
            sys.exit("%s:%d is not in the palette split" % (charset, index))
        if (charset, index) in propios:
            colores[(charset, index)] = (lookup, mapping)
            continue
        union = palettes[paleta_de[(charset, index)]]
        # The colors that aren't in the palette it got go to the nearest of the
        # ones there are. It happens when the map ran out of palettes and
        # `npcs_dibujables` lent it someone else's: it looks bad, but it shows.
        lookup = {}
        for color in palette:
            if color in union:
                lookup[color] = union.index(color) + 1
            else:
                cerca = min(union,
                            key=lambda p, c=color: asignador.luma_distance(p, c))
                lookup[color] = union.index(cerca) + 1
        colores[(charset, index)] = (lookup, mapping)

    where = {}
    for block, (clave, charset, index, pose) in enumerate(ranuras):
        lookup, mapping = colores[(charset, index)]
        where[clave] = (block, paleta_de[(charset, index)])
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
    return bytes(tiles), palettes, where, paleta_de, colores


# A pose in the cartridge: the 16 tiles in a row, by rows.
POSE_BYTES = 16 * 32


def banco_de_poses(images, personajes, colores):
    """The twelve poses of each character that changes pose, for the cartridge.

    One block per character —twelve poses of 512 bytes, 6 KB— and not one for
    all: each goes with `.bloque`, so no DMA of a pose crosses a bank. And
    **from the whole ROM, not from the map**: maps 1 and 2 share Core, Manta
    and Kersh, and with one copy per map the boot-with-window ROM went over the
    cartridge by 19 KB. `emit` splits them into poses and emits each distinct
    pose only once; the map carries its animated characters in order and
    `emit` translates.
    """
    bancos = {}
    for charset, index in personajes:
        # With the lookup from `build_characters`, which is that of the palette
        # it ended up packed in: a pose uploaded on the fly is drawn with the
        # palette already in CGRAM.
        lookup, mapping = colores[(charset, index)]
        datos = bytearray()
        for pose in range(SPRITE_POSES):
            for tile in pose_tiles(images[charset], index, pose, lookup,
                                   mapping):
                datos += tile
        bancos[(charset, index)] = bytes(datos)
    return bancos


# The timer: eleven 8x16 glyphs in the System, starting at (32, 32). Ten digits
# and the colon, which is all `Sprite_Timer::Draw` draws.
TIMER_GLIFOS = 11
TIMER_GLIFO_W, TIMER_GLIFO_H = 8, 16
TIMER_ORIGEN = (32, 32)
# Where it is drawn on screen. `Sprite_Timer` puts it at `menu_offset_x + 4`
# and `menu_offset_y + 4`, and with a screen narrower than the menu both
# offsets come out zero.
TIMER_X, TIMER_Y = 4, 4


def colores_del_timer(sys_img):
    """The colors the timer's eleven glyphs use.

    It is needed **before** splitting the palettes and not only when packing
    the digits: if a map fills all eight, someone has to be chosen to lose a
    color to make room for it, and that decision changes how that character is
    quantized.
    """
    colores = collections.Counter()
    for i in range(TIMER_GLIFOS):
        for y in range(TIMER_GLIFO_H):
            for x in range(TIMER_GLIFO_W):
                r, g, b, a = sys_img.getpixel((TIMER_ORIGEN[0] + i * 8 + x,
                                               TIMER_ORIGEN[1] + y))
                if a:
                    colores[(r >> 3, g >> 3, b >> 3)] += 1
    return colores


def digitos_del_timer(sys_img, tiles, palettes, de_lider=(),
                     tope=OBJ_PALETTES):
    """The timer's eleven glyphs, at the end of the sprite bank.

    Each goes as two stacked 8x8 tiles, and all eleven fit in a row of
    sixteen: glyph i takes tile `base + i` and `base + 16 + i`. The base is
    rounded up to a row so that computation holds.

    Returns (tiles, base, palette number). **It doesn't take a palette of its
    own unless needed**: they are two colors —black and pure red— and fit
    easily in that of any character with thirteen or fewer, exactly like the
    events drawn with a chipset tile fit. One is added only if none has room.

    Reserving it up front cost one palette of the eight, and that is not
    bookkeeping: `npcs_dibujables` decides with that number **which events are
    drawn**. On 2026-09-07, when building `demo-apertura` with the timer, map 2
    lost two events, and one was the middle one of the door Core breaks: taro
    reached the cutscene, the door didn't change tile and he couldn't get
    through. An event that isn't drawn **still takes space**, so the loss is
    not only visual.
    """
    colores = colores_del_timer(sys_img)
    if len(colores) > OBJ_COLORS:
        raise SystemExit("the timer digits use %d colors and %d fit"
                         % (len(colores), OBJ_COLORS))
    quiere = sorted(colores)
    # The first palette its colors fit in without merging anything. It is the
    # same first-fit as `build_characters` and for the same reason.
    #
    # **Except the leader slots.** The ROM overwrites those with the fifteen
    # colors of whoever is leading every time the party changes or a map
    # loads, so a digit put there would lose its red as soon as Talan hands
    # the lead to Kersh. In the seven maps of `demo-apertura` it doesn't land
    # in any today, which is exactly what made the error invisible.
    for numero, existente in enumerate(palettes):
        if numero in de_lider:
            continue
        union = list(existente) + [c for c in quiere if c not in existente]
        if len(union) <= OBJ_COLORS:
            palettes[numero] = union
            paleta, cual = union, numero
            break
    else:
        if len(palettes) >= tope:
            raise SystemExit(
                "the timer doesn't fit: the map already uses the %d sprite "
                "palettes it gets and none has room for its %d colors"
                % (tope, len(quiere)))
        paleta, cual = list(quiere), len(palettes)
        palettes.append(paleta)
    indice = {color: paleta.index(color) + 1 for color in quiere}

    tiles = bytearray(tiles)
    # The base is rounded up to a **row of blocks**, 64 tiles, and not to a
    # grid row: the 4x4 blocks of the last row of blocks take four grid rows,
    # and with the small VRAM image there is since poses go on the fly,
    # rounding to 16 left the glyphs on top of the last row of the hero's
    # block. Nothing showed there until the hero's pose was uploaded and
    # overwrote the 0 and the colon.
    base = -(-(len(tiles) // 32) // 64) * 64
    if (base + 16 + TIMER_GLIFOS) * 32 > len(tiles):
        tiles += bytes((base + 16 + TIMER_GLIFOS) * 32 - len(tiles))
    for i in range(TIMER_GLIFOS):
        for mitad in (0, 1):
            celda = []
            for y in range(CELL):
                fila = []
                for x in range(CELL):
                    r, g, b, a = sys_img.getpixel(
                        (TIMER_ORIGEN[0] + i * 8 + x,
                         TIMER_ORIGEN[1] + mitad * CELL + y))
                    fila.append(indice[(r >> 3, g >> 3, b >> 3)] if a else 0)
                celda.append(tuple(fila))
            numero = base + mitad * 16 + i
            tiles[numero * 32:(numero + 1) * 32] = pack_tile(tuple(celda),
                                                             planes=4)
    return bytes(tiles), base, cual


def gotas_de_lluvia(tiles, palettes, de_lider=(), timer_base=None,
                   tope=OBJ_PALETTES, timer_pal=None):
    """The six raindrop tiles —above and below the streak, in the three
    grays— and the palette their colors go in. See OP_WEATHER in eventos.py.

    It is the same as `digitos_del_timer`: the colors go in the first
    character palette with room, except the leader ones, and the tiles at the
    end of the bank. If the timer is there, in its same row of sixteen, which
    has five places to spare; if not, in a row of blocks of its own. Tone `t`
    above is tile `base + t` and below `base + 16 + t`. Returns (tiles, base,
    palette number).

    **And not in the timer's either.** The reason was that `subir_timer_pal`
    uploaded that whole palette again **untinted** —the digits go above the
    tint, `Priority_Timer` is 140 and `Priority_Screen` 90—, and a drop put
    there stayed gray on a tinted screen; rain is tinted in RM2k,
    `Priority_Weather` is 80. Since 2026-09-25 it uploads only the digits'
    entries, so a drop wouldn't stay gray anymore, except in a color it shared
    with them. It is still avoided because removing it can move where the
    drops land, and that wasn't measured.
    """
    quiere = [c for c in eventos.LLUVIA_COLORES]
    evitar = set(de_lider)
    if timer_pal is not None:
        evitar.add(timer_pal)
    cual = _primer_lugar(palettes, evitar, quiere, tope)
    if cual is None:
        # No room: this map doesn't draw rain. Nobody loses a color to make
        # room for it, unlike the timer: that would change the split, and the
        # split is what decides which colors each map has.
        return bytes(tiles), 0, 0
    paleta = palettes[cual]
    tiles = bytearray(tiles)
    if timer_base:
        base = timer_base + TIMER_GLIFOS
    else:
        base = -(-(len(tiles) // 32) // 64) * 64
    if (base + 16 + 3) * 32 > len(tiles):
        tiles += bytes((base + 16 + 3) * 32 - len(tiles))
    raya = set(eventos.lluvia_pixeles(0, 0))
    for tono, color in enumerate(quiere):
        indice = paleta.index(color) + 1
        for mitad in (0, 1):
            celda = tuple(tuple(indice if (x, mitad * CELL + y) in raya else 0
                                for x in range(CELL)) for y in range(CELL))
            numero = base + mitad * 16 + tono
            tiles[numero * 32:(numero + 1) * 32] = pack_tile(celda, planes=4)
    return bytes(tiles), base, cual


def cartel_de_imagen(info, tiles, palettes, base_previa=None):
    """The `ShowPicture` picture at the end of the sprite bank: its tiles and **a
    whole palette just for it**.

    It shares a palette with nobody, unlike the timer and the drops, and not
    for lack of room: the picture's fade is a tint of its fifteen CGRAM entries
    frame by frame, so a character put in that palette would fade out and back
    in with it.

    And it goes **above `SPRITE_CGRAM`**, that is outside the range
    `aplicar_tinte` and `subir_paletas` walk. That is not shuffling numbers: in
    RM2k pictures have `affected_by_tint` off by default
    —`Priority_PictureOld` is 120 and `Priority_Screen` 90—, so the screen tint
    doesn't touch them. Being outside the range, nobody has to remember to
    skip them.

    Returns (tiles, base, palette number), or (tiles, 0, 0) if the map already
    uses the eight sprite palettes: then this map doesn't draw the picture.
    """
    if len(palettes) >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    cual = len(palettes)        # the first free one, without adding it to the list
    tiles = bytearray(tiles)
    if base_previa:
        base = -(-(base_previa + 2 * 16) // 64) * 64
    else:
        base = -(-(len(tiles) // 32) // 64) * 64
    cuantos = imagen.tiles_reservados(info)
    if (base + cuantos) * 32 > len(tiles):
        tiles += bytes((base + cuantos) * 32 - len(tiles))
    for numero, celda in imagen.celdas(info).items():
        tiles[(base + numero) * 32:(base + numero + 1) * 32] = pack_tile(
            celda, planes=4)
    return bytes(tiles), base, cual


def mapa_muestra_animacion(game_map, renderer, comandos=()):
    """Whether some page of this map can draw a battle animation.

    It is looked at on the raw commands and not on the already compiled
    bytecode, and on purpose: VRAM has to be reserved when converting the map
    and the pages are compiled afterwards. It is a superset —a page that in the
    end doesn't compile leaves 64 tiles reserved and unused— and it has to be:
    if the bytecode showed an animation the map didn't reserve, the ROM would
    write the tiles on top of a character's.

    `comandos` are those of the test pages, which don't come from the map.
    """
    numeros = set()
    for cmd in list(comandos) + [cmd for evento in game_map.events
                                 for page in evento.pages
                                 for cmd in page.commands]:
        if (cmd.code == eventos.SHOW_BATTLE_ANIMATION
                and len(cmd.parameters) >= 3):
            numeros.add(cmd.parameters[0])
    return any(animacion_mod.de_numero(renderer, n) is not None
               for n in numeros)


def animacion_de_mapa(tiles, palettes, usadas=0):
    """The battle animation box at the end of the sprite bank: its 64 tiles
    and **a whole palette just for it**.

    It shares a palette with nobody for the same reason as the picture: the
    fifteen colors belong to the animation, are uploaded when it starts and
    overwritten when another starts, and a character put there would change
    color with it. And it goes **above `SPRITE_CGRAM`**, that is outside the
    range `aplicar_tinte` and `subir_paletas` walk, which is also the faithful
    thing: in `Spriteset_Map::Update` the map's tone goes to the tilemap, the
    characters, the panorama and the shadows, and not to the animations.

    The tiles are reserved **blank**: what goes inside is uploaded by the ROM
    via DMA frame by frame, from the cartridge. See `animacion.py`.

    Returns (tiles, base, palette number), or (tiles, 0, 0) if the map already
    uses the eight sprite palettes. `usadas` are the ones the picture already
    took.
    """
    cual = len(palettes) + usadas
    if cual >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    tiles = bytearray(tiles)
    # After everything else: the timer, the drops and the picture already grew
    # `tiles` to cover theirs, so the end of the bank is the length. Rounded up
    # to a **row of blocks**, which is what the arithmetic of 32x32 objects
    # needs whole.
    base = -(-(len(tiles) // 32) // 64) * 64
    if (base + animacion_mod.TILES) * 32 > len(tiles):
        tiles += bytes((base + animacion_mod.TILES) * 32 - len(tiles))
    return bytes(tiles), base, cual


def tope_de_paletas_del_mapa(renderer, game_map, lideres, graficos,
                             timer_colores, solos, poses, muestra_animacion):
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

    It lives on its own and not inside `convertir` because it is a split
    decision and not a detail of `convertir`.
    """
    if not muestra_animacion:
        return OBJ_PALETTES
    menos = OBJ_PALETTES - 1
    if timer_colores:
        reparto = npcs_dibujables(renderer, game_map, lideres, menos, graficos,
                                  timer_colores, solos, poses)[2]
        copia = [list(p) for p in reparto[0]]
        if _primer_lugar(copia, reparto[3], list(timer_colores),
                         menos) is None:
            return OBJ_PALETTES
    return menos


def _primer_lugar(palettes, de_lider, colores, tope=OBJ_PALETTES):
    """The first palette —except the leader ones— where `colores` fit without
    merging anything, or a new one if a slot is left; it adds or grows it and
    returns its number, or None if there is no room.

    `tope` is how many sprite palettes this map can use, which **isn't always
    all eight**: a map that shows battle animations reserves one for the
    animation box, and neither the timer nor the drops can take it. See
    `tope_de_paletas` in `convertir`.
    """
    for numero, existente in enumerate(palettes):
        if numero in de_lider:
            continue
        union = list(existente) + [c for c in colores if c not in existente]
        if len(union) <= OBJ_COLORS:
            palettes[numero] = union
            return numero
    if len(palettes) < tope:
        palettes.append(list(colores))
        return len(palettes) - 1
    return None


def mapas_por_personaje(renderer, map_ids, game_dir):
    """How many maps of the ROM each (CharSet, index) appears in."""
    cuenta = collections.Counter()
    for otro in map_ids:
        gm = renderer.cargar_mapa(os.path.join(game_dir, "Map%04d.lmu" % otro))
        suyos = set()
        for evento in gm.events:
            for pagina in evento.pages:
                nombre = (getattr(pagina, "character_name", "") or "").strip()
                if nombre:
                    suyos.add((nombre, pagina.character_index))
        cuenta.update(suyos)
    return cuenta


def hay_lluvia(map_ids, extra=()):
    """Whether some page of these maps sets rain: then every map of the ROM
    carries the drops, because the weather persists across map changes.
    `extra` are the commands of the test pages."""
    def llueve(cmd):
        return (cmd.code == eventos.WEATHER_EFFECTS
                and cmd.parameters[:1] == [eventos.CLIMA_LLUVIA])
    if any(llueve(cmd) for cmd in extra):
        return True
    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_juego(),
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                for cmd in page.commands:
                    if llueve(cmd):
                        return True
    return False


def npc_table(npcs, where, movibles=(), indice_animado=None, anima_quieto=()):
    """The NPCs ready for the ROM, already sorted the way RM2k draws them.

    The drawing order is first by layer and only then by Y: a "below" one stays
    below the hero even if it is further forward on screen. On the console,
    the object with the lowest OAM index is the one shown on top, so the table
    goes from front to back.

    **This initial order also rules afterwards.** The walking ones change Y
    and the ROM re-sorts them one at a time, with an insertion that respects
    the order of ties: between two tied ones the order of this list still
    holds.

    The ones in `movibles` also carry which cartridge pose bank their twelve
    are in, so the ROM uploads them on the fly while they walk.
    """
    rows = []
    for npc in sorted(npcs, key=orden_de_dibujo, reverse=True):
        camina = npc["evento"] in movibles
        clave = (("ev", npc["evento"]) if camina
                 else (npc["charset"], npc["index"], npc["pose"]))
        block, slot = where[clave]
        rows.append({
            "x": npc["x"] * 16, "y": npc["y"] * 16,
            "tile": block_tile(block), "palette": slot,
            "layer": npc["layer"], "blocks": npc["blocks"],
            "evento": npc["evento"], "dir": npc["pose"] // 3,
            "pose": npc["pose"],
            "poses": (indice_animado[(npc["charset"], npc["index"])]
                      if camina else None),
            "velocidad": npc.get("velocidad", 3),
            # The still ones with continuous animation: their column comes from
            # the game clock. The walking ones carry it in their route slot, so
            # the flag doesn't apply to them even if their page asks for it too.
            "anima": npc["evento"] in anima_quieto,
            "visible": npc.get("visible", True),
            "tile_pasa": npc.get("tile_pasa"),
        })
    return rows


# --- conversion -------------------------------------------------------------

def build_palette(grid, bg_colors, otras=()):
    """The map's colors, in a single table, merging only if there are too many.

    At 8 bits per pixel the only limit is how many CGRAM entries are left free
    below the upper layer. Map0007 uses 60, so nothing is merged; the merge
    path exists for more loaded maps and is `asignador.reduce_colors`.

    `otras` are the grids of the other drawings of the ChipSet animation. They
    count for the palette like the usual drawing —the water of map 5 brings
    three colors that aren't in its step 0, and without them step 1 couldn't
    be written with this palette— and come out merged with the same
    `mapping`, which is what keeps them comparable with each other.
    """
    counts = _colores_de((grid,) + tuple(otras))
    if len(counts) <= bg_colors:
        return sorted(counts), grid, list(otras), []

    mapping, merged = asignador.merge_least_visible(counts, bg_colors)

    def fusionar(g):
        return [[tuple(tuple(mapping.get(p) for p in line) for line in tile)
                 for tile in row] for row in g]

    return (sorted({c for c in mapping.values()}), fusionar(grid),
            [fusionar(g) for g in otras], merged)


_VERSION_CAPAS = None


def _version_capas():
    """Which version of the code produced whatever is stored under `capas`.

    It is the seven pieces that take part in drawing or converting, plus the
    two programs that aren't sources of this tree:

    * `render/render_map.py` and `render/chipset.py` **draw** the layers and
      expand the ChipSet. Until 2026-09-20 they weren't needed, because the
      key was the already drawn pixels: changing the drawing changed the key
      by itself. Since the key comes from the inputs, the only way for a change
      in the drawing to invalidate what is stored is this one.
      `rpgmaker/resources.py` goes with them because it is where `render_map`
      gets how it finds the ChipSet, and `common/project.py` because it is
      where the directories it searches in come from;
    * `port/asignador.py` decides which colors are lost, `rpgmaker/rm2k.py`
      has the constants of the split and of the animated families, and this
      file does the rest;
    * **the Voodoo binary**, which is the one that emits the tiles:
      recompiling it without touching any `.py` has to invalidate what is
      stored;
    * **the Pillow version**, which is what decodes the ChipSet's PNG and
      composes the tiles. It wasn't needed before either, for the same reason:
      the pixels that came out of Pillow *were* the key.

    What does **not** go in, on purpose: `rpgmaker/lcf.py`. What it reads from
    the dump —the two layers, the size, the ChipSet's passability— goes in by
    its value in `insumos_de_capas`, so a change in how it is read only
    matters if what is read changes, and then the key changes by itself.
    """
    global _VERSION_CAPAS
    if _VERSION_CAPAS is None:
        import PIL
        from common import disk_cache
        _VERSION_CAPAS = (disk_cache.version_of("port/snes_convert.py",
                                                "port/asignador.py",
                                                "rpgmaker/rm2k.py",
                                                "render/render_map.py",
                                                "rpgmaker/resources.py",
                                                "common/project.py",
                                                "render/chipset.py")
                          + tiles_bin.version()
                          + " Pillow " + PIL.__version__)
    return _VERSION_CAPAS


def capas_convertidas(renderer, game_map):
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

    What is lost is exactly that virtue, and that is why `insumos_de_capas`
    lives next to `render_layers` and says what it reads: now the list is
    maintained by hand, and if it falls short the cache answers stale without
    anything failing.

    Verified with `SIN_CACHE=1` and with the cache deleted: the `.sfc` is the
    same byte for byte.
    """
    from common import disk_cache
    insumos = renderer.insumos_de_capas(game_map)
    en_disco = None
    if insumos is not None:
        en_disco = disk_cache.key(_version_capas(), *insumos)
        if en_disco in _capas_en_memoria:
            return _capas_en_memoria[en_disco]
        hecho = disk_cache.read("capas", en_disco)
        if hecho is not None:
            _capas_en_memoria[en_disco] = hecho
            return hecho
    base, above_img, variantes = renderer.capas_animadas(game_map)
    if base is None:
        return None
    hecho = _convert_layers(base, above_img, variantes)
    if en_disco is not None:
        disk_cache.write("capas", en_disco, hecho)
        _capas_en_memoria[en_disco] = hecho
    return hecho


# The layers already converted in this run, keyed by the disk cache key.
# `precalcular_capas` fills it and it also works with `SIN_CACHE=1`: it is not
# a cache between runs but the same computation done earlier and in parallel.
_capas_en_memoria = {}


def precalcular_capas(renderer, map_ids, args):
    """The layers of all maps, converted in parallel before `convertir` asks
    for them.

    It is the most expensive part of a cold build —or of a warm one after
    touching this file, which invalidates the stored layers— and each map is
    independent, so there is one process per map. The processes fork with all
    the state already built, prepare the map like `convertir` does and return
    what they computed with its key; `convertir` then asks for the same key.
    **A map prepared differently here than there doesn't give a different
    ROM**: it gives another key, and `convertir` computes it as always.
    """
    if len(map_ids) < 2:
        return
    global _para_precalcular
    _para_precalcular = (renderer, args)
    procesos = min(len(map_ids), os.cpu_count() or 1)
    with multiprocessing.get_context("fork").Pool(procesos) as pool:
        for hechas in pool.map(_capas_de_un_mapa, map_ids, chunksize=1):
            _capas_en_memoria.update(hechas)
    _para_precalcular = None


_para_precalcular = None


def _capas_de_un_mapa(map_id):
    """What `precalcular_capas` does in each process: the same steps as
    `convertir` up to its two calls to `capas_convertidas`."""
    renderer, args = _para_precalcular
    try:
        # Quiet: whatever it has to say, `convertir` says it, in order.
        with open(os.devnull, "w") as nulo, contextlib.redirect_stdout(nulo):
            game_map = renderer.cargar_mapa(
                os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
            separar_del_heroe(renderer, game_map, args,
                              comandos_de_casos(args, map_id))
            capas_convertidas(renderer, game_map)
            horneados = eventos_horneables(renderer, game_map)
            if horneados:
                hornear_en_el_mapa(game_map, horneados)
                capas_convertidas(renderer, game_map)
    except BaseException:
        # If it fails, let it fail in `convertir`, which can say why.
        pass
    return _capas_en_memoria


def _convert_layers(base, above_img, variantes=None):
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
    `paleta_de_la_ventana`—, so it charges neither layer.

    Returns (what convert() returns, what convert_above() returns).
    """
    base_grid = tiles_cuantizados(base)
    above_grid = tiles_cuantizados(above_img)
    # The other drawings of the ChipSet animation, cut the same as the
    # background. See `convert`.
    grillas = {familia: [tiles_cuantizados(img) for img in imagenes]
               for familia, imagenes in (variantes or {}).items()}

    # What the background uses, and therefore the palettes of 16 it needs. The
    # +1 is the screen's backdrop color, which takes entry 0.
    #
    # **All the drawings** count: the water of map 5 brings three colors that
    # aren't in the drawing seen on entering, and if the split were decided
    # without them there would be nowhere to put them when the water moves.
    usados = len(_colores_de([base_grid] + [g for gs in grillas.values()
                                            for g in gs]))
    pide = -(-(usados + CGRAM_RESERVADAS) // COLORS_PER_PALETTE)
    libres = max(1, min(MAX_ABOVE_PALETTES, BG_PALETTES - pide))

    above_grid, paletas_encima, fusionados = repartir_encima(above_grid, libres)
    # Without an upper layer nothing is reserved, but the DMA still sends an
    # empty palette —see `convert_above`—, so the split is counted as if there
    # were one.
    primera = above_split(max(1, len(paletas_encima)))
    above = convert_above(above_grid, paletas_encima, primera, len(fusionados))
    # The background reaches **up to where the upper layer starts**, without
    # leaving palettes in between: it goes at 8 bits and needs no alignment.
    # The window doesn't charge it a palette because it lives at the very
    # bottom, inside `CGRAM_RESERVADAS`.
    tope = primera
    if tope < 1:
        # Unreachable with the game's data —it would take an upper layer that
        # asks for all eight palettes— but if it happens, the background would
        # be left with none and `bg_budget` would give a negative budget.
        raise SystemExit(
            "the upper layer took all eight palettes and none is left "
            "for the background")
    # And the background palette, with that budget and over **all** its
    # drawings. It is decided here and `convert` gets it, same as the upper
    # layer.
    presupuesto = bg_budget(tope)
    otras = [g for familia, _ in FAMILIAS for g in grillas.get(familia, ())]
    antes = len(_colores_de([base_grid]))
    palette, base_grid, otras, merged = build_palette(base_grid, presupuesto,
                                                      otras)
    fondo = convert(base_grid, palette, grillas, otras,
                    {"colores": antes, "presupuesto": presupuesto,
                     "fusionados": len(merged)})
    # Which color was merged with which, in the order it was decided, for
    # `port/parches.py` to write it. It goes **with the background's summary
    # and not inside the upper layer's tuple** even though half of it is the
    # upper layer's: `_mismo_reparto_de_cgram` compares that whole tuple, so
    # adding a field would change the criterion baking is decided by, and this
    # can't change a single byte of the ROM. The summary, instead, it compares
    # field by field, so one more key is inert —and `fusionados`, which is one
    # of the ones it compares, is still the usual number—.
    fondo[3]["fusiones"] = {"fondo": list(merged), "encima": list(fusionados)}
    return fondo, above


def paleta_de_la_ventana(primeras=None):
    """Which palette the message window goes in: **0**, always.

    The window cells are emitted only once with the three palette bits
    inside, so the palette has to be a single one for the whole ROM. It used
    to take the lowest of the upper layers of all maps —`min(primeras) - 1`—
    and the background of **all** of them was squeezed below it, even if the
    map had half of CGRAM free above.

    Putting it in 0 makes the problem go away: the window takes entries 1 to 7
    —0 is the screen's backdrop color, which in a BG2 palette is transparent
    and the window doesn't draw—, and the background is contiguous from 8 up
    to where each map's upper layer starts. `primeras` is no longer used and
    stays so as not to break callers.
    """
    return 0


# The two tile families the ChipSet animates, with how many drawings each one
# has and in the order their runs go to VRAM. It lives in rm2k.py together with
# each one's cadence, which is what says which drawing is due.
FAMILIAS = rm2k.FAMILIAS_ANIMADAS


def convert(grid, palette, variantes, otras, resumen):
    """The map grid to tiles, palette and tilemap.

    **It doesn't decide the palette**: it comes from `build_palette`, which
    chooses it in `_convert_layers` with the budget the upper layer left.
    `grid` and `otras` are the grids already merged with that same palette;
    `variantes` the original ones, which are only used to know how many
    drawings each family brings. `resumen` carries what was measured before
    merging.

    `variantes` are the grids of the **other** drawings of the ChipSet
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
    dibujos, resto = {None: [grid]}, list(otras)
    for familia, _ in FAMILIAS:
        cuantas = len(variantes.get(familia, ()))
        dibujos[familia] = [grid] + resto[:cuantas]
        resto = resto[cuantas:]

    # What the allocator decided, as indexed images: color `k` of the palette
    # is entry `CGRAM_RESERVADAS + k`, and transparent is 0. One per drawing,
    # all with the same CGRAM: `tiles` stops if two give a different color to
    # an entry that any of them draws.
    posicion = {color: CGRAM_RESERVADAS + k for k, color in enumerate(palette)}
    colores = [None] * 256
    for color, entrada in posicion.items():
        colores[entrada] = color
    transparentes = [e == 0 for e in range(256)]
    ancho, alto = len(grid[0]) * CELL, len(grid) * CELL

    def imagen(g):
        pixeles = [0] * (ancho * alto)
        for cy, row in enumerate(g):
            for cx, tile in enumerate(row):
                for y, line in enumerate(tile):
                    fila = (cy * CELL + y) * ancho + cx * CELL
                    for x, color in enumerate(line):
                        if color is not None:
                            pixeles[fila + x] = posicion[color]
        return tiles_bin.png_indexado(ancho, alto, pixeles, colores,
                                      transparentes)

    imagenes = [("fondo", imagen(grid))]
    familias, animaciones = [], []
    for familia, _ in FAMILIAS:
        if len(dibujos[familia]) < 2:
            continue
        pngs = [imagen(g) for g in dibujos[familia][1:]]
        imagenes += [("%s-%d" % (familia, d + 1), png)
                     for d, png in enumerate(pngs)]
        familias.append(familia)
        animaciones.append(pngs)

    # The cells that change from one drawing to another get their own tiles in
    # one contiguous run per family, after the still ones: Voodoo does that,
    # since it is the one that numbers them. See "Animations" in
    # tools/voodoo/README.md.
    tile_data, cgram, tilemap, corridas = tiles_bin.convertir(
        imagenes[0][1], 8, len(grid[0]), animaciones=animaciones,
        max_tiles=MAX_TILES)
    siguiente = len(tile_data) // BYTES_PER_TILE

    # And the other drawings of each run, one after the other and in VRAM
    # order: that way uploading them is writing the address and firing the
    # DMA.
    animacion = {}
    for familia, (inicio, largo, bytes_de) in zip(familias, corridas):
        if not largo:
            continue
        cuantos = dict(FAMILIAS)[familia]
        if len(bytes_de) != cuantos:
            raise SystemExit("family %r asks for %d drawings and %d arrived"
                             % (familia, cuantos, len(bytes_de)))
        animacion[familia] = {"base": inicio, "tiles": largo,
                              "dibujos": list(bytes_de)}

    # CGRAM: the map's block carries **only its colors** and is uploaded
    # starting at `CGRAM_RESERVADAS`. What is below —the screen's backdrop
    # color and the window palette— belongs to the whole ROM and `cgram_base`
    # uploads it.
    cram = [int.from_bytes(cgram[2 * e:2 * e + 2], "little")
            for e in range(CGRAM_RESERVADAS, CGRAM_RESERVADAS + len(palette))]

    summary = {
        "colores": resumen["colores"],
        "usados": len(palette),
        "presupuesto": resumen["presupuesto"],
        "fusionados": resumen["fusionados"],
        "tiles": siguiente,
        "celdas": sum(len(row) for row in tilemap),
        "animacion": animacion,
        "imagenes": imagenes,
    }
    return bytes(tile_data), cram, tilemap, summary


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
# What makes the tiles part possible is that `encima` and `ventana` end up
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
# It was needed on 2026-09-07, when drawing all the events —see `cabe`— took
# map 8 to 400 background tiles and 347 sprite ones, and there was no layout
# that gave it both.
#
# The puzzle is one of alignment and not of space: `BG12NBA` fixes the BG1 and
# BG2 bases at multiples of 8 KB, `OBSEL` that of the objects at multiples of
# 16 KB, and the tilemaps at multiples of 1 KB. The tilemaps moved to $5800
# and $7800, which are the only two gaps left aligned in the four layouts.
LAYOUT_VENTANA = {"sprites": (0x0000, 448), "ventana_map": (0x1C00, 1),
                  "tiles": (0x2000, 448), "mapa": (0x5800, 1),
                  "encima": (0x6000, 128), "ventana": (0x6800, 256)}
LAYOUT_VENTANA_FONDO = {"sprites": (0x0000, 256), "tiles": (0x1000, 480),
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
LAYOUT_VENTANA_SPRITE = {"sprites": (0x0000, 512), "tiles": (0x2000, 384),
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
# `FAR_VRAM_MAPA` instead of a constant, and by the step to the upper layer in
# `push_strips`, which masks instead of adding a fixed distance. That is why
# **both bases have to be multiples of 2048 words**, and the map's can't be
# zero: `col_addr` at zero means "no column". `_controlar_repartos` checks it.
#
# **It goes last on purpose**, for the same reason as the previous one: no
# map that already fit changes layout.
LAYOUT_VENTANA_AMBOS = {"sprites": (0x0000, 384), "mapa": (0x1800, 1),
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
# background goes in two streams —see `partes_comprimidas`—.
#
# **It goes last on purpose**, for the same reason as the two previous ones.
LAYOUT_VENTANA_FONDO_TECHO = {"sprites": (0x0000, 256), "tiles": (0x1000, 544),
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
# and `estampar_ventana` picks its own by looking at where the window ended up
# relative to the BG2 base.
#
# **It goes last on purpose**, for the same reason as the previous ones:
# `vram_layout` now also looks at the upper layer, and since all the maps that
# already converted fit in 128, none changes layout.
LAYOUT_VENTANA_ENCIMA = {"sprites": (0x0000, 384), "mapa": (0x1800, 1),
                         "tiles": (0x2000, 384), "encima": (0x5000, 256),
                         "ventana": (0x6000, 256), "ventana_map": (0x7000, 1)}

# In the order `vram_layout` tries them. **New ones are added at the end**,
# never in the middle: that way a new layout doesn't change any map's.
LAYOUTS = (("VENTANA", LAYOUT_VENTANA),
           ("VENTANA_FONDO", LAYOUT_VENTANA_FONDO),
           ("VENTANA_SPRITE", LAYOUT_VENTANA_SPRITE),
           ("VENTANA_AMBOS", LAYOUT_VENTANA_AMBOS),
           ("VENTANA_FONDO_TECHO", LAYOUT_VENTANA_FONDO_TECHO),
           ("VENTANA_ENCIMA", LAYOUT_VENTANA_ENCIMA))
# How many save slots the cartridge has. The same number is in
# `tools/runtime/partida.s` as `SRAM_RANURAS`, and the ROM checks it: if they
# didn't match, the screen would show one number of slots and the SRAM would
# have another.
RANURAS = 4

# Where the tilemap and the tiles of the slots screen live, in words. The same
# numbers are in the `.inc` as RANURA_MAP and RANURA_VRAM.
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
#   LAYOUT_VENTANA        $2000..$5800
#   LAYOUT_VENTANA_FONDO  $1000..$4C00
#   LAYOUT_VENTANA_SPRITE $2000..$5000
#   LAYOUT_VENTANA_AMBOS  $2000..$5C00
#   LAYOUT_VENTANA_FONDO_TECHO $1000..$5400
#
# A BG's tile base goes in steps of 4096 words and the tilemap in steps of
# 1024: the tiles at $2000, which with the party's faces are about 300 and can
# reach 448 —up to $3C00—, and the tilemap at $3C00. The title screen
# overwrites them —its image reaches $3E00— and it doesn't matter: coming back
# from the slots the title is uploaded whole. `_controlar_ranuras` checks it
# against the real layouts, so that moving one doesn't leave this written
# wrong.
RANURA_VRAM = 0x2000
# The row of `ranura_actor_texto`: an actor's name, the two digits of the
# level and max HP, one after the other. Its size is a power of two even if
# bytes are left over, so that the actor's index comes out of five `asl` and
# not of a multiplication written in assembly.
RANURA_TEXTO_ANCHO = 32
RANURA_TEXTO_NIVEL = 16         # the name fits in thirteen, and three are left over
RANURA_TEXTO_MAX = RANURA_TEXTO_NIVEL + menus_mod.NIVEL_CIFRAS
RANURA_MAP = 0x3C00

# The upper layer's tilemap is fixed: the background's is chosen by the layout
# —see LAYOUT_VENTANA_AMBOS—.
VRAM_ABOVE_MAP = 0x7800

# Where the window's bank starts **counted from the BG2 base**, which is where
# the upper layer begins. It comes from the layout and not from a written
# number: with the upper layer at 128 tiles, the window starts at index 128
# and not 256, and writing it by hand was the first thing that broke when the
# layout moved.
def ventana_base(layout):
    """The BG2 index of the window's first tile in that layout."""
    return (layout["ventana"][0] - layout["encima"][0]) // 16


# The bases the layouts use, in the order of their layouts in the `.inc`: the
# first one's is `ventana_celdas` —the usual one— and the second's,
# `ventana_celdas_256`. The ROM picks between the two by the distance between
# the window and the BG2 base, so **there can't be a third** without touching
# `estampar_ventana`; `_controlar_repartos` enforces it.
VENTANA_TILE_BASE = ventana_base(LAYOUT_VENTANA)
VENTANA_BASES = (VENTANA_TILE_BASE, 256)

# The block table is read with `lda tabla, x`, that is it lives in bank 0
# together with the code.
MAX_BLOCKS = 1024


def vram_layout(tiles, sprites=0, encima=0):
    """Which VRAM layout a map gets, according to what it spends.

    The three numbers are checked in every layout, and the first one that
    fits is returned. The upper layer is checked since the sixth layout, the
    one that gives it 256: with the five before it always fit, because a map
    that went over 128 didn't convert.
    """
    # The two numbers are checked in both layouts. The background used to be
    # checked in one and the sprites in the other, and that let a map with 620
    # background tiles into a bank of 512: see the comment on
    # LAYOUT_VENTANA_FONDO.
    for _nombre, layout in LAYOUTS:
        if (tiles <= layout["tiles"][1] and sprites <= layout["sprites"][1]
                and encima <= layout["encima"][1]):
            return layout
    raise SystemExit(
        "this map can't carry a message window: it spends %d background tiles, "
        "%d sprite tiles and %d upper tiles, and there is no layout that leaves "
        "8 KB of tiles plus 2 KB of tilemap for the window" % (tiles, sprites, encima))


def _controlar_ranuras(ranura_tiles):
    """That the slots screen lands in the BG1 bank of every layout.

    It is what lets `volver_al_mapa` restore the map with `load_map` and
    nothing else; see the comment on RANURA_MAP.
    """
    fin_tiles = RANURA_VRAM + ranura_tiles * 16
    fin_map = RANURA_MAP + 32 * 32
    if not (fin_tiles <= RANURA_MAP or fin_map <= RANURA_VRAM):
        raise SystemExit(
            "the %d tiles of the slots screen reach $%04X and overwrite its "
            "tilemap at $%04X" % (ranura_tiles, fin_tiles, RANURA_MAP))
    for nombre, layout in LAYOUTS:
        base, cuantos = layout["tiles"]
        tope = base + cuantos * (BYTES_PER_TILE // 2)
        for que, desde, hasta in (("the tiles", RANURA_VRAM, fin_tiles),
                                  ("the tilemap", RANURA_MAP, fin_map)):
            if desde < base or hasta > tope:
                raise SystemExit(
                    "the slots screen puts %s at $%04X..$%04X and the "
                    "BG1 bank of LAYOUT_%s is $%04X..$%04X: when coming back "
                    "from the menu `load_map` wouldn't restore it"
                    % (que, desde, hasta, nombre, base, tope))


def items_marco_primero(fuente):
    """The first 8bpp tile of the item and equipment windows, counted from
    `RANURA_VRAM`, which is the BG1 base and the BG2 one: the first free one
    after the `fuente` tiles of the font, which are 4bpp and half the size."""
    return (fuente + 1) // 2


def _controlar_marco_de_items(fuente, marco):
    """That the font and the windows of the item and equipment screens, one
    after the other, don't reach the BG1 tilemap, and that everything stays
    in the BG1 bank of the layouts, like the rest of the screen —see
    `_controlar_ranuras`—."""
    fin = RANURA_VRAM + (items_marco_primero(fuente) + marco) * 32
    if fin > menus_mod.ITEM_MARCO_MAPA:
        raise SystemExit(
            "the item screen's font (%d 4bpp tiles) and the item and "
            "equipment windows (%d 8bpp ones) reach $%04X and the windows' "
            "tilemap is at $%04X" % (fuente, marco, fin, menus_mod.ITEM_MARCO_MAPA))
    fin_map = menus_mod.ITEM_MARCO_MAPA + 32 * 32
    for nombre, layout in LAYOUTS:
        base, cuantos = layout["tiles"]
        tope = base + cuantos * (BYTES_PER_TILE // 2)
        if RANURA_VRAM < base or fin_map > tope:
            raise SystemExit(
                "the item and equipment windows reach $%04X and the BG1 "
                "bank of LAYOUT_%s is $%04X..$%04X" % (fin_map, nombre, base,
                                                       tope))


def _controlar_objetivo(tiles):
    """That the tiles and the tilemap of the actor-choice windows fit between
    their BG1 base and their tilemap, and that everything lands in the BG1
    bank of every layout, which is what `load_map` restores when closing the
    menu —like `_controlar_ranuras`—, and outside what the menu already uses:
    its tiles and its tilemap end at `RANURA_MAP` + 1024."""
    T = menus_mod
    fin_tiles = T.OBJETIVO_VRAM + tiles * 32
    fin_map = T.OBJETIVO_MAPA + 32 * 32
    if fin_tiles > T.OBJETIVO_MAPA:
        raise SystemExit(
            "the actor-choice windows are %d 8bpp tiles and "
            "reach $%04X, and their tilemap is at $%04X"
            % (tiles, fin_tiles, T.OBJETIVO_MAPA))
    if T.OBJETIVO_VRAM < RANURA_MAP + 32 * 32:
        raise SystemExit("the actor-choice windows overwrite the "
                         "menu's tilemap")
    for nombre, layout in LAYOUTS:
        base, cuantos = layout["tiles"]
        tope = base + cuantos * (BYTES_PER_TILE // 2)
        if T.OBJETIVO_VRAM < base or fin_map > tope:
            raise SystemExit(
                "the actor-choice windows go at $%04X..$%04X and "
                "the BG1 bank of LAYOUT_%s is $%04X..$%04X: when closing the "
                "menu `load_map` wouldn't restore them"
                % (T.OBJETIVO_VRAM, fin_map, nombre, base, tope))


def _controlar_tienda(tiles):
    """That the tiles of the shop windows, from their BG1 base, don't reach
    beyond what `load_map` restores when closing in any layout —like
    `_controlar_objetivo`—, nor what the screen uses: the font and the BG2
    tilemap end at `RANURA_MAP` + 1024. The tilemap is the item and equipment
    one, which `_controlar_marco_de_items` already checks."""
    P = pantallas_mod
    fin_tiles = P.TI_VRAM + tiles * 32
    if P.TI_VRAM < RANURA_MAP + 32 * 32:
        raise SystemExit("the shop windows overwrite the text "
                         "tilemap")
    for nombre, layout in LAYOUTS:
        base, cuantos = layout["tiles"]
        tope = base + cuantos * (BYTES_PER_TILE // 2)
        if P.TI_VRAM < base or fin_tiles > tope:
            raise SystemExit(
                "the shop windows are %d 8bpp tiles, at "
                "$%04X..$%04X, and the BG1 bank of LAYOUT_%s is "
                "$%04X..$%04X: when closing the shop `load_map` wouldn't "
                "restore them" % (tiles, P.TI_VRAM, fin_tiles, nombre, base,
                                  tope))


def _controlar_repartos():
    """That each layout respects the hardware and what the ROM assumes of it.

    None of this depends on the map, so it is checked once per conversion.
    """
    for nombre, layout in LAYOUTS:
        # In words: what each thing takes, and the step its base goes in. The
        # sprite and upper-layer tiles are 4bpp, 16 words.
        piezas = {
            "sprites": (layout["sprites"][1] * 16, 0x2000),
            "tiles": (layout["tiles"][1] * (BYTES_PER_TILE // 2), 0x1000),
            "encima": (layout["encima"][1] * 16, 0x1000),
            "ventana": (layout["ventana"][1] * 16, 1),
            "ventana_map": (32 * 32, 0x400),
            # 2048 and not 1024, which is what `BG1SC` asks for: `push_strips`
            # steps to the upper layer by masking eleven bits. See
            # `push_una_columna`.
            "mapa": (WINDOW_W * WINDOW_H, 0x800),
        }
        tramos = [("upper map", VRAM_ABOVE_MAP, VRAM_ABOVE_MAP
                   + WINDOW_W * WINDOW_H)]
        for pieza, (largo, paso) in piezas.items():
            base = layout[pieza][0]
            if base % paso:
                raise SystemExit("LAYOUT_%s: %s at $%04X, and its base goes in "
                                 "steps of $%X words" % (nombre, pieza, base, paso))
            tramos.append((pieza, base, base + largo))
        if layout["mapa"][0] == 0:
            raise SystemExit("LAYOUT_%s: the tilemap at $0000, and `col_addr` "
                             "at zero means there is no column" % nombre)
        if ventana_base(layout) not in VENTANA_BASES:
            raise SystemExit("LAYOUT_%s: the window starts at BG2 tile %d, "
                             "and there are layouts for %s: see VENTANA_BASES"
                             % (nombre, ventana_base(layout), VENTANA_BASES))
        # And the window has to land inside what BG2 reaches from its base: the
        # tilemap index is ten bits.
        if ventana_base(layout) + layout["ventana"][1] > 1024:
            raise SystemExit("LAYOUT_%s: the window goes past BG2 index "
                             "1023" % nombre)
        tramos.sort(key=lambda t: t[1])
        for (a, _, fin), (b, desde, _) in zip(tramos, tramos[1:]):
            if fin > desde:
                raise SystemExit("LAYOUT_%s: %s ends at $%04X and %s starts "
                                 "at $%04X" % (nombre, a, fin, b, desde))
        if tramos[-1][2] > 0x8000:
            raise SystemExit("LAYOUT_%s: %s goes past VRAM"
                             % (nombre, tramos[-1][0]))


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
VENTANA_TEXTO_FILA = 1           # the first row of cells that carries text
VENTANA_TEXTO_FILAS = 8
VENTANA_TEXTO_COL = 1
VENTANA_TEXTO_COLS = 30


def _columnas():
    """How many characters fit on a line. It lives in `ventana.py` with the
    rest of the geometry, and the reason for the number is there."""
    from port import ventana as ventana_mod
    return constantes.COLUMNAS


def _quince(imagen):
    """The pixels of an RGBA image as 15-bit colors, over black."""
    from PIL import Image
    llana = Image.alpha_composite(
        Image.new("RGBA", imagen.size, (0, 0, 0, 255)), imagen).convert("RGB")
    return [tuple(v >> 3 for v in p) for p in llana.get_flattened_data()]


def convert_ventana(sys_img, font_id=None):
    """The message window: tiles, palette, cells and what the font needs.

    The image is built by `ventana.py`, which follows easyrpg-player's rules
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
    from port import fuente as fuente_mod
    from port import ventana as ventana_mod

    if font_id is None:
        font_id = fuente_mod.MINCHO
    vacia = ventana_mod.ventana(sys_img)
    pixeles = _quince(vacia)
    ancho, alto = vacia.width, vacia.height

    # The text colors come from the System's 16x16 block, and they are the
    # ones `Font::Render` uses as a mask. Each row of the glyph takes a single
    # one —it is measured: the gradient is horizontally uniform— so they are
    # twelve colors, not a block, and the shadow is a single one.
    bloque = ventana_mod.color_de_texto(sys_img, 0)
    sombra_img = ventana_mod.color_de_sombra(sys_img)
    ox, oy = ventana_mod.TEXTO_OFS
    color_fila = []
    for py in range(fuente_mod.ALTO):
        fila = {tuple(v >> 3 for v in bloque.getpixel((ox + px, oy + py))[:3])
                for px in range(fuente_mod.ANCHO)}
        if len(fila) != 1:
            raise SystemExit(
                "row %d of the text color has %d distinct colors; the "
                "ROM composes it with a single one" % (py, len(fila)))
        color_fila.append(fila.pop())
    sombra = tuple(v >> 3 for v in sombra_img.getpixel((0, 0))[:3])

    colores = sorted(set(pixeles) | set(color_fila) | {sombra})
    if len(colores) > COLORS_PER_PALETTE - 1:
        raise SystemExit("the window uses %d colors and %d fit"
                         % (len(colores), COLORS_PER_PALETTE - 1))
    indice = {c: i + 1 for i, c in enumerate(colores)}

    def celda_de(tx, ty):
        return tuple(tuple(indice[pixeles[(ty * 8 + y) * ancho + tx * 8 + x]]
                           for x in range(8)) for y in range(8))

    # The cells without text are deduplicated as always; the ones in the text
    # area are numbered consecutively from there.
    tiles, celdas = {}, []
    for ty in range(alto // 8):
        fila = []
        for tx in range(ancho // 8):
            if (VENTANA_TEXTO_FILA <= ty < VENTANA_TEXTO_FILA + VENTANA_TEXTO_FILAS
                    and VENTANA_TEXTO_COL <= tx < VENTANA_TEXTO_COL + VENTANA_TEXTO_COLS):
                fila.append(None)       # numbered below, once it is known how many
                continue
            celda = celda_de(tx, ty)
            if celda not in tiles:
                tiles[celda] = len(tiles)
            fila.append(tiles[celda])
        celdas.append(fila)

    base = len(tiles)
    fondo = []
    for n, ty in enumerate(range(VENTANA_TEXTO_FILA,
                                VENTANA_TEXTO_FILA + VENTANA_TEXTO_FILAS)):
        for m, tx in enumerate(range(VENTANA_TEXTO_COL,
                                     VENTANA_TEXTO_COL + VENTANA_TEXTO_COLS)):
            celdas[ty][tx] = base + n * VENTANA_TEXTO_COLS + m
            fondo.append(celda_de(tx, ty))
    if base + len(fondo) > 256:
        raise SystemExit("the window needs %d tiles and the bank has 256"
                         % (base + len(fondo)))

    datos = b"".join(pack_tile(celda, planes=4)
                     for celda, _ in sorted(tiles.items(), key=lambda kv: kv[1]))
    cram = [0] + [cgram_word(c) for c in colores]
    cram += [0] * (COLORS_PER_PALETTE - len(cram))
    # The background starts where this ends, so if the window grew it would
    # step on it and the ROM would draw the text with a map color. The highest
    # index really used is checked —the shadow's or that of some row of the
    # glyph— and not how many words are nonzero: a black color has word zero
    # and wouldn't be counted.
    alto = max([indice[c] for c in color_fila] + [indice[sombra]])
    if alto >= CGRAM_RESERVADAS:
        raise SystemExit(
            "the message window uses CGRAM entry %d and the background "
            "starts at %d: raise CGRAM_RESERVADAS" % (alto, CGRAM_RESERVADAS))
    return {"tiles": datos, "cram": cram, "celdas": celdas,
            "base": base,
            "fondo": b"".join(pack_tile(c, planes=4) for c in fondo),
            "color": [indice[c] for c in color_fila],
            "sombra": indice[sombra]}


def fuente_bytes(font_id):
    """The 95 ASCII glyphs, twelve rows of six bits each.

    It is the same table as `tools/port/fuente.py`, which is generated from
    easyrpg-player, but **with the bits reversed**: there bit 0 is the
    leftmost pixel and in the console's tile format the leftmost is bit 7.
    Reversing them here and not in the ROM comes for free: it is a 1140-byte
    table generated once.
    """
    from port import fuente as fuente_mod
    out = bytearray()
    for code in range(32, 127):
        for fila in fuente_mod.filas(chr(code), font_id):
            invertida = 0
            for px in range(FUENTE_ANCHO):
                if fila >> px & 1:
                    invertida |= 1 << (7 - px)
            out.append(invertida)
    return bytes(out)


# The window glyphs already composed, for each of the four phases a character
# can land on: x is `VENTANA_BORDE + 6 * column`, so modulo 8 it gives 0, 6, 4
# or 2 and never anything else. Per glyph and phase go the cell rows of
# `FUENTE_PRE_FILAS` it touches —the glyph's twelve from `TEXTO_OFS_Y`, and
# one more of shadow— and per row the two cells it can step on, each with
# three words: what is kept from the buffer, and what is set in planes 0-1
# and in 2-3. The ROM does `buf = buf & conservar | prender`, which is what it
# used to compute on each row with `pintar`, twice —shadow and glyph— and with
# a one-bit-at-a-time shift. See `componer_char`.
#
# The shadow and the glyph come already combined, with the ordering rule of
# `Font::Render`: on a row lands the glyph from two rows up and the shadow
# from three, shifted one pixel, and where they overlap the glyph wins.
FUENTE_PRE_FILAS = FUENTE_ALTO + 1
FUENTE_PRE_CHAR = FUENTE_PRE_FILAS * 2 * 6


def fuente_prerender(fuente, colores, sombra):
    """The four tables, one per phase (0, 2, 4 and 6), in that order."""
    n = len(fuente) // FUENTE_ALTO
    tablas = []
    for fase in (0, 2, 4, 6):
        out = bytearray()
        for c in range(n):
            filas = fuente[c * FUENTE_ALTO:(c + 1) * FUENTE_ALTO]
            corrida = [(f << 8) >> fase for f in filas]
            for k in range(FUENTE_PRE_FILAS):
                glifo = corrida[k] if k < FUENTE_ALTO else 0
                color = colores[k] if k < FUENTE_ALTO else 0
                sombra_m = (corrida[k - 1] >> 1) if k >= 1 else 0
                sombra_m &= ~glifo & 0xFFFF
                for celda in (0, 1):
                    g = (glifo >> (8 if celda == 0 else 0)) & 0xFF
                    s = (sombra_m >> (8 if celda == 0 else 0)) & 0xFF
                    conservar = ~((g | s) * 0x0101) & 0xFFFF
                    prender = []
                    for bits in (0, 2):
                        palabra = 0
                        for m, col in ((g, color), (s, sombra)):
                            if col >> bits & 1:
                                palabra |= m
                            if col >> (bits + 1) & 1:
                                palabra |= m << 8
                        prender.append(palabra)
                    for palabra in [conservar] + prender:
                        out += bytes([palabra & 0xFF, palabra >> 8])
        tablas.append(bytes(out))
    return tablas


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
            abajo = game_map.lower_layer[by * width + bx]
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
                   rm2k.terreno_de(chipset, abajo) if chipset else 1)
            if key not in blocks:
                blocks[key] = len(blocks)
            cells.append(blocks[key])
            combos.setdefault((abajo,
                               game_map.upper_layer[by * width + bx]),
                              blocks[key])

    if len(blocks) > MAX_BLOCKS:
        raise SystemExit("the map uses %d distinct blocks and the table can't "
                         "go over %d" % (len(blocks), MAX_BLOCKS))

    table = bytearray(BLOCK_BYTES * len(blocks))
    pass_bytes = bytearray(len(blocks))
    terreno_bytes = bytearray(len(blocks))
    for (base, above, permisos, terreno), number in blocks.items():
        entries = list(base) + list(above)
        for i, cell in enumerate(entries):
            table[number * BLOCK_BYTES + i * 2:
                  number * BLOCK_BYTES + i * 2 + 2] = cell.to_bytes(2, "little")
        pass_bytes[number] = permisos
        if not 0 <= terreno <= 0xFF:
            raise SystemExit("a tile with terrain %d and the ROM's table "
                             "carries one byte per block" % terreno)
        terreno_bytes[number] = terreno
    return cells, table, pass_bytes, terreno_bytes, combos


# How many block pairs the ROM's substitution table can hold at once. It is
# `SUB_MAX` in tools/runtime/ram_baja.s and it is written on both sides on
# purpose —the converter has to be able to refuse **before** emitting a map
# that doesn't fit—; the test `test_sustitucion.py` compares the two.
SUB_MAX = 8


class Sustituciones:
    """`TileSubstitution` translated from RM2k tiles to ROM blocks.

    RM2k substitutes by **tile number**: every cell of the map that draws the
    old tile starts drawing the new one. In the ROM there are no RM2k tiles,
    there are 16x16 blocks that carry both layers and the passability
    together, so an RM2k substitution is as many block pairs as (lower, upper)
    combinations of the map carry that tile. Which ones they are is known when
    converting, which is why this lives here and not in `eventos.py`.

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

    def __init__(self, mapa, flags, chipset):
        self.mapa = mapa
        self.flags = flags
        self.chipset = chipset
        self.combos = mapa["combos"]
        # The four 8x8 cells each RM2k tile is drawn with, per layer. They come
        # from the blocks that already exist: a tile the map doesn't draw
        # anywhere isn't here and can't be substituted into.
        self.celdas = ({}, {})
        for (bajo, alto), bloque in self.combos.items():
            # **The lower half is only usable if the upper tile of that block
            # isn't baked into it.** An upper-layer tile **without** the
            # "Above" bit isn't drawn on BG2 but over the background —that is
            # what `draw_tiles` decides, and that is why there are upper tiles
            # whose BG2 half comes out empty—, so the lower half of that block
            # is the composition of the two and not the lower tile alone.
            # Copying it to build another combination would draw the
            # neighbor's upper tile.
            if not self._hornea(alto):
                self.celdas[0].setdefault(bajo, self._mitad(bloque, 0))
            self.celdas[1].setdefault(alto, self._mitad(bloque, 1))
        # The blocks some substitution of the map uses as a key, which is what
        # is going to take room in the RAM table.
        self.claves = set()
        # And the blocks by content, to deduplicate the ones built the same way
        # `build_blocks` deduplicates the map's. It isn't to save room: two
        # combinations that already share a block —the two water autotiles of
        # map 6 draw the same thing— have to keep sharing it after
        # substituting, or the substitution would send a single block to two
        # places and couldn't be expressed.
        self.por_bytes = {}
        for bloque in range(len(mapa["pass"])):
            self.por_bytes.setdefault(self._huella(bloque), bloque)

    def _hornea(self, alto):
        """Whether that upper-layer tile is baked into the background instead
        of going to BG2.

        It is `draw_tiles`'s computation: an upper tile goes above the hero
        —that is, to BG2— only with the `Above` bit set, and without it it is
        drawn stuck to the background. The empty tile draws nothing and bakes
        nothing.
        """
        return (alto != rm2k.UPPER_BASE
                and not self.flags[alto] & rm2k.PASS_ABOVE)

    def _mitad(self, bloque, capa):
        desde = bloque * BLOCK_BYTES + capa * 8
        return bytes(self.mapa["bloques"][desde:desde + 8])

    def _huella(self, bloque):
        desde = bloque * BLOCK_BYTES
        return (bytes(self.mapa["bloques"][desde:desde + BLOCK_BYTES]),
                self.mapa["pass"][bloque], self.mapa["terreno"][bloque])

    def _combo(self, capa_alta, viejo, nuevo):
        """The RM2k ids of the tile that goes out and the one that comes in."""
        base = rm2k.UPPER_BASE if capa_alta else rm2k.LOWER_BASE
        return base + viejo, base + nuevo

    def pares(self, capa_alta, viejo, nuevo):
        """The `(old block, new block)` pairs of a substitution, or None.

        None is "this page doesn't compile", which is what `eventos.py`
        expects from a command that can't be done.
        """
        if not (0 <= viejo < rm2k.TILES_POR_CAPA
                and 0 <= nuevo < rm2k.TILES_POR_CAPA):
            return None
        capa = 1 if capa_alta else 0
        viejo_id, nuevo_id = self._combo(capa_alta, viejo, nuevo)
        salida, vistos = [], {}
        for combinacion, bloque in sorted(self.combos.items()):
            if combinacion[capa] != viejo_id:
                continue
            destino = list(combinacion)
            destino[capa] = nuevo_id
            nuevo_bloque = self.combos.get(tuple(destino))
            if nuevo_bloque is None:
                return None     # `cerrar` should have created it
            if vistos.setdefault(bloque, nuevo_bloque) != nuevo_bloque:
                # Two distinct combinations that draw the same and have the
                # same permissions share a block, and there the substitution
                # can't be expressed: the block would have to go two ways. It
                # doesn't happen with any ChipSet of the game —drawing the
                # same means being the same tile— but if it did, substituting
                # would change cells RM2k doesn't touch.
                return None
            salida.append((bloque, nuevo_bloque))
        if len(salida) > 0xFF:
            return None         # the count operand is one byte
        self.claves.update(par[0] for par in salida)
        return salida

    def cerrar(self, triples):
        """Builds the blocks that are going to be needed, and returns what
        couldn't be done.

        `triples` are the `(upper layer, old, new)` of all the map's
        `TileSubstitution`s. It repeats until none creates a new block,
        because the block one creates is the source of the next.
        """
        faltan = []
        while True:
            antes = len(self.combos)
            for capa_alta, viejo, nuevo in triples:
                if not (0 <= viejo < rm2k.TILES_POR_CAPA
                        and 0 <= nuevo < rm2k.TILES_POR_CAPA):
                    continue
                capa = 1 if capa_alta else 0
                viejo_id, nuevo_id = self._combo(capa_alta, viejo, nuevo)
                if nuevo_id not in self.celdas[capa]:
                    if (capa_alta, viejo, nuevo) not in faltan:
                        faltan.append((capa_alta, viejo, nuevo))
                    continue
                for combinacion in sorted(self.combos):
                    if combinacion[capa] != viejo_id:
                        continue
                    destino = list(combinacion)
                    destino[capa] = nuevo_id
                    if self._crear(tuple(destino)) is None \
                            and (capa_alta, viejo, nuevo) not in faltan:
                        faltan.append((capa_alta, viejo, nuevo))
            if len(self.combos) == antes:
                return faltan

    def _crear(self, combinacion):
        """The block of a combination the map doesn't draw anywhere.

        None is "this combination can't be built without drawing the map
        again". It happens when the upper tile is baked into the background:
        then the two halves of the block aren't independent and there is
        nowhere to take the lower one from. See `_hornea`.
        """
        if combinacion in self.combos:
            return self.combos[combinacion]
        bajo, alto = combinacion
        if self._hornea(alto) or bajo not in self.celdas[0] \
                or alto not in self.celdas[1]:
            return None
        huella = (self.celdas[0][bajo] + self.celdas[1][alto],
                  rm2k.pasa_de_celda(self.flags, bajo, alto),
                  rm2k.terreno_de(self.chipset, bajo))
        numero = self.por_bytes.get(huella)
        if numero is None:
            numero = len(self.mapa["pass"])
            if numero >= MAX_BLOCKS:
                raise SystemExit(
                    "map %d goes over %d blocks building the ones "
                    "`TileSubstitution` needs"
                    % (self.mapa["id"], MAX_BLOCKS))
            self.mapa["bloques"] += huella[0]
            self.mapa["pass"].append(huella[1])
            self.mapa["terreno"].append(huella[2])
            self.por_bytes[huella] = numero
        self.combos[combinacion] = numero
        return numero


def triples_de_sustitucion(game_map, casos, map_id):
    """The `(upper layer, old, new)` of all the `TileSubstitution`s that can
    end up running in this map: those of its events and those of the test
    cases that start here —which live in the boot map but are compiled with
    this one's context, see `mapa_del_caso`—."""
    triples = []
    listas = [pagina.commands
              for evento in game_map.events for pagina in evento.pages]
    listas += [caso.comandos for caso in casos if caso.mapa == map_id]
    for comandos in listas:
        for cmd in comandos:
            if cmd.code != eventos.TILE_SUBSTITUTION or len(cmd.parameters) < 3:
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
MAPA_STRIDE = 128
MAPA_ESCALARES = [
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
    ("VRAM_VENTANA", "0 if this ROM carries no message window"),
    ("VRAM_VENTANA_MAP", "and its own 32x32 tilemap"),
    ("MAP_TILES", "how many background tiles, for the DMA"),
    ("MAP_CGRAM", "how many CGRAM words"),
    ("ABOVE_TILES", ""),
    ("ABOVE_CGRAM", ""),
    ("SPRITE_TILES", ""),
    ("SPRITE_CGRAM", ""),
    ("NPC_COUNT", "how many NPCs with a CharSet"),
    ("EV_COUNT", "how many events the map has, with or without a graphic"),
    ("TIMER_BASE", "the first tile of the timer digits, 0 if there are none"),
    ("LLUVIA_BASE", "the first tile of the raindrops, 0 if there are none"),
    ("ACTOR_COUNT", "how many party leader candidates"),
    ("PAGINA_COUNT", "how many event pages have to be resolved"),
    ("RUTA_GRAFICO_COUNT", "how many distinct graphics command 34 asks for"),
]
MAPA_BYTES = [
    ("OBSEL_VALUE", "8x8 and 32x32 objects, and the page of their tiles"),
    ("BG12NBA_VALUE", "the tile pages of BG1 and BG2"),
    ("ABOVE_FIRST", "which CGRAM entry the upper layer starts at"),
    ("TIMER_PAL", "the sprite palette of the timer digits"),
    ("LLUVIA_PAL", "the sprite palette of the raindrops"),
    # A byte and not a scalar because the record is at exactly its 128. A
    # block's tile is always a multiple of four and less than 512.
    ("GIRO_TILE4", "the tile of the turn slot divided by four, or $FF"),
    # The terrain, which is what `StoreTerrainID` answers. Both are bytes
    # because RM2k's terrain is an index into `Data.terrains` and doesn't go
    # over 255, and because the map record is at exactly its 128.
    ("TERRENO_FUERA", "the terrain of a cell outside the map"),
    ("TERRENO_PLANO", "the terrain of the whole map, or 0 if there is a table"),
]
MAPA_PUNTEROS = ["map_tiles", "map_cgram", "above_tiles", "above_cgram",
                 "sprite_tiles", "sprite_cgram", "map_celdas", "map_bloques",
                 "bloque_pass", "bloque_terreno", "npc_table", "actor_table",
                 "paginas", "ev_pos", "npc_poses", "ruta_grafico",
                 # The ChipSet animation: the two tile runs and their
                 # drawings. See `anim_bytes`.
                 "anim_tiles"]
MAPA_PTR_PASO = 4
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
MAPA_PTR_BASE = (-(-(len(MAPA_ESCALARES) * 2 + len(MAPA_BYTES))
                   // MAPA_PTR_PASO) * MAPA_PTR_PASO)
assert MAPA_PTR_BASE + len(MAPA_PUNTEROS) * MAPA_PTR_PASO <= MAPA_STRIDE, \
    "the map record doesn't fit in %d bytes" % MAPA_STRIDE

# An event page: which event it belongs to, what activates it, and where its
# code is. The pages of one event go together and in order, which is what lets
# the ROM choose the last one that meets its conditions in a single pass,
# without carrying a table per event.
PAGINA_BYTES = 32
# No turn slot: the map has no still event that turns around.
GIRO_NINGUNO = 0xFFFF
# A leader candidate: id, palette, **its fifteen colors** and twelve 24-bit
# pointers to its poses. The colors go inside the table and not in a separate
# block because there are few actors per map and that way the ROM uploads them
# with one DMA from where it already is; see `elegir_grafico_heroe`.
#
# They are there because leaders **share a CGRAM slot**: one leads at a time,
# so reserving a palette for each is having it taken by someone who isn't on
# screen. The ROM uploads the leader's when the party changes and when the map
# loads. See `npcs_dibujables`.
ACTOR_COLORES = 2 * OBJ_COLORS
ACTOR_BYTES = 2 + ACTOR_COLORES + 3 * 12

# One bit per switch. The game checks up to 1003 in page conditions, so 1024
# is more than enough: it is 128 bytes of RAM.
SWITCH_BYTES = 128

# How many distinct graphics command 34 can ask for in a map. The table is
# copied to RAM when the map loads, like the NPC one, so the cap costs bytes
# from bank 0's eight kilobytes —two per graphic— and can't be generous just
# because. **The map that asks for the most in the whole game asks for six**,
# measured over the 328; eight leaves two of slack and is sixteen bytes. The
# converter stops if any map goes over, so it can't fall short silently.
RUTA_GRAF_MAX = 8


def campos_del_mapa(mapa):
    """The values of a map's record, in the order they are emitted."""
    tilemap, above, sprite = mapa["tilemap"], mapa["above"], mapa["sprite"]
    collision, layout = mapa["collision"], mapa["layout"]
    height, width = len(tilemap), len(tilemap[0])
    return {
        "MAP_BW": collision[3], "MAP_BH": collision[4],
        "CAM_MAX_X": max(0, width * CELL - 256),
        "CAM_MAX_Y": max(0, height * CELL - 224),
        "HERO_MAX_X": width * CELL - 16, "HERO_MAX_Y": height * CELL - 16,
        "HERO_START_X": collision[1] * 16, "HERO_START_Y": collision[2] * 16,
        "VRAM_TILES": layout["tiles"][0], "VRAM_MAP": layout["mapa"][0],
        "VRAM_SPRITE": layout["sprites"][0],
        "VRAM_VENTANA": layout.get("ventana", (0, 0))[0],
        "VRAM_VENTANA_MAP": layout.get("ventana_map", (0, 0))[0],
        "MAP_TILES": len(mapa["tiles"]) // BYTES_PER_TILE,
        "MAP_CGRAM": len(mapa["cram"]) // 2,
        "ABOVE_TILES": len(above[0]) // 32,
        "ABOVE_CGRAM": len(above[1]) // 2,
        "SPRITE_TILES": len(sprite[0]) // 32 if sprite else 0,
        # One more than the colors: sprite index 0 is transparent and also
        # takes its place in CGRAM.
        "SPRITE_CGRAM": COLORS_PER_PALETTE * len(sprite[1]) if sprite else 0,
        "NPC_COUNT": len(sprite[3]) if sprite else 0,
        "EV_COUNT": len(mapa["ev_pos"]) // EV_STRIDE,
        "TIMER_BASE": sprite[5] if sprite else 0,
        "LLUVIA_BASE": sprite[10] if sprite else 0,
        "ACTOR_COUNT": len(sprite[4]) if sprite else 0,
        "PAGINA_COUNT": len(mapa["paginas"]),
        "RUTA_GRAFICO_COUNT": len(sprite[9]) if sprite else 0,
        "OBSEL_VALUE": 0x20 | (layout["sprites"][0] // 0x2000),
        "BG12NBA_VALUE": ((layout["encima"][0] // 0x1000) << 4)
                         | (layout["tiles"][0] // 0x1000),
        "ABOVE_FIRST": above[3] * COLORS_PER_PALETTE,
        "TIMER_PAL": (sprite[6] if sprite and sprite[6] is not None else 0),
        "LLUVIA_PAL": sprite[11] if sprite else 0,
        "GIRO_TILE4": (sprite[12] // 4 if sprite and sprite[12] != GIRO_NINGUNO
                       else 0xFF),
        "TERRENO_FUERA": mapa["terreno_fuera"],
        "TERRENO_PLANO": terreno_plano(mapa),
    }


def desplazamientos():
    """The names of the record's fields, so that tools/runtime/ doesn't repeat
    them.

    The converter emitting the offsets and the ROM only naming them is what
    makes it impossible for them to get out of sync: if a field is added here,
    there is no number to update there.
    """
    out = ["; Where each field falls inside a map's record."]
    usado = 0
    for nombre, _ in MAPA_ESCALARES:
        out.append("M_%-14s = %d" % (nombre, usado))
        usado += 2
    for nombre, _ in MAPA_BYTES:
        out.append("M_%-14s = %d" % (nombre, usado))
        usado += 1
    for numero, nombre in enumerate(MAPA_PUNTEROS):
        out.append("M_PTR_%-10s = %d"
                   % (nombre.upper(), MAPA_PTR_BASE + numero * MAPA_PTR_PASO))
    return "\n".join(out)


def tabla_de_mapas(mapas, etiquetas):
    """The table the ROM walks to know what to load.

    `etiquetas` says, per map, which block each pointer points to. This didn't
    exist before and the name was rebuilt here with `"%s_%d" % (nombre,
    numero)`, that is with the same computation that had emitted it: two
    places computing the same name and no way for a block to belong to more
    than one map.
    """
    out = ['.segment "RODATA"',
           "; The map table: one record of %d bytes per map, with everything"
           % MAPA_STRIDE,
           "; the ROM needs to load it. The pointers are 24 bits because the",
           "; data lives spread over all the banks.",
           ";",
           "; **It lives in RODATA and is read with `lda f:mapa_tabla + campo, x`.**",
           "; It is 144 bytes per map, and in bank 0 —where the table has to be",
           "; if it is walked with the data bank register— that was enough for",
           "; fourteen maps and no more: with the whole of Lashe City it is 33",
           "; and the bank went over by 3739 bytes. It is the third table that",
           "; moves for the same reason; the price is one byte per instruction",
           "; and that the two uses with Y had to switch to X, because long",
           "; absolute indexed addressing only exists with X.",
           ";",
           "; **Whole within one bank**, which is what `.bloque` asks for. In",
           "; LoROM what follows $03FFFF isn't bank 4's ROM but RAM, and the",
           "; first version of this landed at $03FFB1: the 144 bytes of the only",
           "; record were split in half and map 5 started black. The other maps",
           "; of the suite didn't see it because their table landed somewhere",
           "; else, which is exactly the kind of error that shows up when adding",
           "; a byte anywhere else.",
           ".bloque %d" % (MAPA_STRIDE * len(mapas)),
           "mapa_tabla:"]
    for numero, mapa in enumerate(mapas):
        campos = campos_del_mapa(mapa)
        # Stays in Spanish: `mapas_de` in rom/pruebas/arnes/consola.py reads
        # the table order from this line with a regex that expects "mapa".
        out.append("    ; --- %d: mapa %d %r ---" % (numero, mapa["id"],
                                                     mapa["nombre"]))
        usado = 0
        for nombre, comentario in MAPA_ESCALARES:
            out.append("    .word %-6d ; +%-3d %s%s"
                       % (campos[nombre], usado, nombre,
                          "  " + comentario if comentario else ""))
            usado += 2
        for nombre, comentario in MAPA_BYTES:
            out.append("    .byte $%02X    ; +%-3d %s  %s"
                       % (campos[nombre], usado, nombre, comentario))
            usado += 1
        relleno = MAPA_PTR_BASE - usado
        # Without padding the line doesn't go: a `.byte` without operands is an
        # error for `ca65`.
        if relleno:
            out.append("    .byte %s ; +%d  padding up to the pointers"
                       % (",".join(["$00"] * relleno), usado))
        usado += relleno
        for nombre in MAPA_PUNTEROS:
            etiqueta = etiquetas[numero][nombre]
            out.append("    .byte <(%s), >(%s), ^(%s), $00 ; +%d  %s"
                       % (etiqueta, etiqueta, etiqueta, usado, nombre))
            usado += MAPA_PTR_PASO
        assert usado <= MAPA_STRIDE, usado
        if usado < MAPA_STRIDE:
            out.append("    .byte " + ",".join(["$00"] * (MAPA_STRIDE - usado)))
    # And each map's RM2k id, by index: `MemorizeLocation` writes it into a
    # variable and `RecallToLocation` looks it up, because in variables the map
    # is RM2k's —any other page reads them—. It goes separately and not as a
    # record scalar because the record is at exactly its 128. See
    # `op_location`.
    out += ["",
            "; Each map's RM2k id, in the order of `mapa_tabla`.",
            ".bloque %d" % (2 * len(mapas)),
            "mapa_rm2k:",
            "    .word " + ", ".join(str(m["id"]) for m in mapas)]
    return "\n".join(out)


# The ChipSet animation block: the drawings, one after the other and in VRAM
# order —water 0, 1, 2; animated 0 to 3—, with no header.
#
# Where each one lands and which VRAM address it goes to isn't inside the
# block but in `anim_tabla`, one entry per map. It is so the ROM doesn't have
# to read anything from the cartridge to animate: the direct page is full, so
# an `lda [puntero], y` had nowhere to live, and the alternative —bringing the
# header into WRAM by DMA— asked for forty bytes of BSS that weren't there
# either. With the table built here, the ROM indexes and fires the DMA.
ANIM_STRIDE = 16
ANIM_FAM_STRIDE = ANIM_STRIDE // 2


def anim_bytes(animacion):
    """The map's drawings, one after the other. Empty if nothing animates."""
    datos = bytearray()
    for familia, _ in FAMILIAS:
        corrida = animacion.get(familia)
        if corrida:
            for dibujo in corrida["dibujos"]:
                datos += dibujo
    return bytes(datos)


def anim_tabla(mapas):
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
    `animar_quietos` would have to walk the forty NPC rows in every map.
    """
    out = ['.segment "RODATA"',
           "; The ChipSet animation, one entry of %d bytes per map."
           % ANIM_STRIDE,
           # `rom/src/` and not `tools/runtime/`, on purpose: it goes into the
           # `.inc`, and what is emitted isn't touched yet. See
           # las-herramientas-se-separan-de-abl.md.
           "; See `anim_tabla` in tools/port/snes_convert.py and `anim_flush` in rom/src/animacion_del_chipset.s.",
           ";",
           "; **It lives in RODATA and is read with `lda f:anim_tabla + campo, x`**,",
           "; for the same reason as `mapa_tabla`: it is 16 bytes per map, and",
           "; with the maps the tests ask for bank 0 went over by 361. Whole",
           "; within one bank, because what follows $xxFFFF isn't the next one's ROM.",
           ".bloque %d" % (ANIM_STRIDE * len(mapas)),
           "anim_tabla:"]
    for mapa in mapas:
        animacion = mapa["resumen"]["animacion"]
        out.append("    ; --- map %d %r ---" % (mapa["id"], mapa["nombre"]))
        desplazamiento = 0
        for familia, cuantos in FAMILIAS:
            corrida = animacion.get(familia)
            tiles = corrida["tiles"] if corrida else 0
            vram = (mapa["layout"]["tiles"][0]
                    + (corrida["base"] if corrida else 0) * BYTES_PER_TILE // 2)
            out.append("    .word %-6d ; VRAM of %s" % (vram, familia))
            out.append("    .word %-6d ; drawing 0, inside the block"
                       % desplazamiento)
            out.append("    .word %-6d ; bytes per drawing"
                       % (tiles * BYTES_PER_TILE))
            relleno = 0
            if familia == FAMILIAS[-1][0]:
                relleno = 1 if any(n.get("anima")
                                   for n in (mapa["sprite"][3]
                                             if mapa["sprite"] else ())) else 0
            out.append("    .byte %d, %d   ; %d tile(s)%s"
                       % (tiles, relleno, tiles,
                          ", and the map has still events that animate"
                          if relleno else ""))
            desplazamiento += tiles * BYTES_PER_TILE * cuantos
    return "\n".join(out)


def animaciones_de_la_rom(mapas, renderer):
    """The battle animations the already emitted bytecode shows, by RM2k
    number, each one converted by `animacion.py`.

    The bytecode is walked and not the commands, which is what makes it the
    truth and not a guess: what counts is what ended up emitted, after the
    page filter decided which ones go in. It is the same rule as
    `eventos.blancos_de_ruta`.
    """
    numeros = set()
    for mapa in mapas:
        for pagina in mapa.get("paginas", ()):
            codigo = pagina.get("codigo") or b""
            for i, c in eventos.recorrer_codigo(codigo):
                if (c[i] == eventos.OP_ANIMATION
                        and c[i + 1] != eventos.ANIM_SIN_DIBUJO):
                    numeros.add(c[i + 1])
    salida = {}
    for numero in sorted(numeros):
        info = animacion_mod.de_numero(renderer, numero)
        if info is not None:
            salida[numero] = info
    return salida


def cuadro_de_animacion(cuadro):
    """The 2 KB of a battle animation frame as they end up in VRAM: the box's
    64 4bpp tiles, in order."""
    datos = bytearray(animacion_mod.TILES * 32)
    for tile, celda in animacion_mod.celdas(cuadro).items():
        datos[tile * 32:(tile + 1) * 32] = pack_tile(celda, planes=4)
    return bytes(datos)


# The end of a frame without its empty tiles: no tile of the box reaches 64.
CUADRO_FIN = 0xFF


def cuadro_sin_vacios(datos):
    """A frame from `cuadro_de_animacion` as the cartridge stores it: only its
    tiles that aren't all zero, each with its number in front, and
    `CUADRO_FIN`.

    The frames are **almost all transparency**, so storing them whole was
    paying for zeros: what was measured is in the task
    `la-compresion-de-mapas-y-graficos.md`. What ends up in VRAM doesn't
    change: `anim_cuadro_armar` rebuilds the 2 KB in far RAM and the vblank
    uploads them whole, as before.
    """
    out = bytearray()
    for tile in range(animacion_mod.TILES):
        uno = datos[tile * 32:(tile + 1) * 32]
        if any(uno):
            out.append(tile)
            out += uno
    out.append(CUADRO_FIN)
    return bytes(out)


def animaciones_asm(animaciones, mapas):
    """The cartridge's battle animations, ready for the `.inc`.

    Four things:

      `anim_batalla_de`      by RM2k number, which entry it gets, or $FF.
                             It goes by number and not by an index of ours so
                             that neither end has to carry a counter the other
                             must guess.
      `anim_batalla_tabla`   per entry: how many frames, where its anchor
                             falls inside the box and which frame it starts at.
      `anim_batalla_cuadros` per frame, the 24-bit pointer to its tiles
                             without the empty ones: see `cuadro_sin_vacios`.
                             One per frame and not a contiguous block per
                             animation, which dates from when each frame was
                             2 KB and 28 didn't fit in a bank.
      `anim_batalla_cgram`   its sixteen colors, which the ROM uploads when the
                             animation starts.
      `anim_batalla_reparto` per map, where and with which palette it is drawn
                             here, or 0 if this map doesn't draw animations.
    """
    orden = sorted(animaciones)
    entrada = {numero: k for k, numero in enumerate(orden)}
    tope = (max(orden) + 1) if orden else 1
    out = [
        "\n; --- the drawing of the battle animations ---",
        ";",
        "; The box is a single one for the whole ROM and the reason is in",
        "; tools/port/animacion.py: four 32x32 objects in one row of blocks",
        "; of the name grid, which is the most that fits in the sprite VRAM",
        "; map 2 has left free. What changes per map is where that row lands",
        "; and with which palette, and that goes in `anim_batalla_reparto`,",
        "; one byte per map.",
        "ANIM_B_CAJA   = %d" % animacion_mod.CAJA,
        "ANIM_B_OBJ    = %d" % animacion_mod.OBJ,
        "ANIM_B_OBJETOS = %d" % animacion_mod.OBJETOS,
        "ANIM_B_TILES  = %d" % animacion_mod.TILES,
        "ANIM_B_BYTES  = %d" % (animacion_mod.TILES * 32),
        "ANIM_B_STRIDE = 8",
        "; How high an animation number `anim_batalla_de` reaches: the bytecode",
        "; carries the RM2k number as is and a larger one isn't in the table,",
        "; so the ROM compares it before reading it.",
        "ANIM_B_MAX    = %d" % tope,
        "; The center of the screen, which is where the ones with scope",
        "; `Scope_screen` land: `DrawAt(screen_width / 2, screen_height / 2)`.",
        "ANIM_B_CENTRO_X = %d" % (animacion_mod.PANTALLA[0] // 2),
        "ANIM_B_CENTRO_Y = %d" % (animacion_mod.PANTALLA[1] // 2),
        "ANIM_B_SIN      = $%02X" % eventos.ANIM_SIN_DIBUJO,
        "ANIM_B_PANTALLA = $%02X" % eventos.ANIM_BLANCO_PANTALLA,
    ]
    out.append(bloque("anim_batalla_de",
                      bytes(entrada.get(n, 0xFF) for n in range(tope))))
    tabla = bytearray()
    primero = 0
    for numero in orden:
        info = animaciones[numero]
        # The anchor **as the ROM wants it**: with the shift of
        # `Animation::Position` already baked in, so the console only
        # subtracts.
        ax, ay = animacion_mod.ancla_rom(info)
        tabla += bytes([len(info["cuadros"]), ax & 0xFF, ay & 0xFF, 0,
                        primero & 0xFF, primero >> 8, 0, 0])
        primero += len(info["cuadros"])
    out.append(bloque("anim_batalla_tabla", bytes(tabla)))
    cgram = bytearray()
    for numero in orden:
        colores = [(0, 0, 0)] + list(animaciones[numero]["paleta"])
        colores += [(0, 0, 0)] * (COLORS_PER_PALETTE - len(colores))
        for color in colores:
            cgram += cgram_word(color).to_bytes(2, "little")
    out.append(bloque("anim_batalla_cgram", bytes(cgram)))
    # The pointer table, with labels: it can't come from `bloque()`, but it
    # **is declared** with `.bloque` for the same reason as the page one —the
    # ROM reads it with a 24-bit pointer and it can't straddle two banks—.
    punteros = [".bloque %d" % (4 * primero), "anim_batalla_cuadros:"]
    for numero in orden:
        for k in range(len(animaciones[numero]["cuadros"])):
            punteros.append("    .dword anim_batalla_%d_%d" % (numero, k))
    out.append("\n".join(punteros))
    for numero in orden:
        info = animaciones[numero]
        for k, cuadro in enumerate(info["cuadros"]):
            out.append(bloque("anim_batalla_%d_%d" % (numero, k),
                              cuadro_sin_vacios(cuadro_de_animacion(cuadro))))
    reparto = bytearray()
    for mapa in mapas:
        sprite = mapa["sprite"]
        base, pal = (sprite[15], sprite[16]) if sprite else (0, 0)
        # Bit 7 is "drawn here", and below go the 64-tile block and the
        # palette, three bits each. In one byte because the map record is at
        # exactly its 128: see MAPA_STRIDE.
        reparto.append((0x80 | ((base // 64) << 3) | pal) if base else 0)
    out.append(bloque("anim_batalla_reparto", bytes(reparto)))
    return "\n".join(out) + "\n"


def experiencia_ranuras(db, actores):
    """The actors that carry experience and level, in the order of their slot.

    They are the ones that can join the party —`ranuras["actores"]`—, because
    only they fight and experience is only gained by fighting: the game
    doesn't use `ChangeExp` or `ChangeLevel` in any map. Having a slot of their
    own and not one per actor number is what makes the save grow by four bytes
    per actor that fights and not for each of the sixty in the LDB. **Always at
    least one**, even if it belongs to nobody: with zero the reset DMA would
    copy 64 KB.
    """
    return sorted(a for a in actores if a in db.actors) or [None]


def experiencia_asm(db, actores, actores_n):
    """The experience and level tables: see `port.experiencia`.

    It leaves the segment in RODATA, which is where its caller finds it.

    Per slot of `experiencia_ranuras`:

        exp_inicial    four bytes: the starting experience, 24 bits, and the
                       level. It is what the reset copies to `FAR_EXP`.
        exp_nivel_max  `GetMaxLevel()`, one byte.
        exp_curva      where its row starts in `exp_tabla`, a word.
        nivel_fila     six words: where each parameter curve starts in
                       `nivel_params`, in the order of `lcf.CURVES`.

    `exp_tabla` is `MakeExpList` of each distinct curve —four bytes per level,
    `NIVEL_MAX` levels— and `nivel_params` the six curves of each slot,
    `NIVEL_MAX` words each. Everything goes outside bank 0: it is read when
    winning a battle, when setting it up and on the equipment screen, never
    per frame.
    """
    ranuras_exp = experiencia_ranuras(db, actores)
    k_de = {a: k for k, a in enumerate(ranuras_exp) if a is not None}
    curvas, curva_de, inicial, maximo, filas, params = [], [], [], [], [], []
    for a in ranuras_exp:
        actor = db.actors[a] if a is not None else None
        lista = (X.lista_de(actor) if actor else [0])
        lista = lista + [0] * (X.NIVEL_MAX - len(lista))
        if lista not in curvas:
            curvas.append(lista)
        curva_de.append(4 * X.NIVEL_MAX * curvas.index(lista))
        exp = X.exp_inicial(actor) if actor else 0
        inicial += [exp & 0xFF, (exp >> 8) & 0xFF, exp >> 16,
                    X.nivel_inicial(actor) if actor else 1]
        maximo.append(X.nivel_max(actor) if actor else 1)
        for curva in lcf.CURVES:
            filas.append(2 * len(params))
            valores = list(actor.params.get(curva) or []) if actor else []
            valores = (valores + [0] * X.NIVEL_MAX)[:X.NIVEL_MAX]
            params += [v & 0xFFFF for v in valores]
    if 4 * len(ranuras_exp) > 0x200:
        raise SystemExit("%d actors with experience don't fit in the 512 "
                         "bytes of FAR_EXP" % len(ranuras_exp))
    out = ['.segment "RODATA"',
           "EXP_K = %d" % len(ranuras_exp),
           "EXP_NIVEL_MAX = %d" % X.NIVEL_MAX]

    def tabla(etiqueta, directiva, valores, ancho):
        out.append(".bloque %d" % max(ancho, ancho * len(valores)))
        out.append("%s:" % etiqueta)
        for i in range(0, len(valores), 16):
            out.append("    %s %s" % (directiva, ", ".join(
                str(v) for v in valores[i:i + 16])))

    tabla("actor_exp_k", ".byte",
          [k_de.get(a, 0xFF) for a in range(actores_n)], 1)
    tabla("exp_inicial", ".byte", inicial, 1)
    tabla("exp_nivel_max", ".byte", maximo, 1)
    tabla("exp_curva", ".word", curva_de, 2)
    tabla("exp_tabla", ".dword", [v for c in curvas for v in c], 4)
    tabla("nivel_fila", ".word", filas, 2)
    tabla("nivel_params", ".word", params, 2)
    return "\n".join(out) + "\n"


# What goes in the backdrop tables instead of a backdrop number: the plain one
# —no backdrop, which is zeros— and "the one of the place", which the ROM
# resolves when the battle starts with the map and the terrain. See
# `escena_de_la_rom`.
FONDO_LISO = 0xFF
FONDO_DEL_LUGAR = 0xFE


def escena_de_la_rom(db, tropas, mapas, tree, encuentros, game_dir):
    """Which backdrops and which battlers the cartridge carries, and who uses
    each one.

    It is the other half of tools/port/escena.py: there is how a backdrop or
    a battler is converted, here **which ones**. Backdrops are named by their
    number in the game —see "Which backdrops there are" there—, and a battle asks for its
    own in three ways:

    * **an `EnemyEncounter` that names it**, and then it belongs to the troop
      —that is how the baked scene worked—. If two asked for it differently
      for the same troop the first one wins, as in `Tropas.pedir`;
    * **a random encounter in a map that inherits it**, which is
      `TreeMap.map_background`: the Back Alleys areas bring no backdrop and
      take it from their map;
    * **the one of the terrain the hero is standing on**, if the map names
      none: the world, 66. The ROM resolves that one when the battle starts,
      with `fondo_terreno`. And an `EnemyEncounter` with the backdrop "of the
      place" does the same as a random encounter: `FONDO_DEL_LUGAR`.

    A backdrop goes **into the ROM**, light, if some battle of the cartridge
    asks for it; if some can land on one that isn't there —a troop of the
    place in a map without encounters—, `escena.reemplazo()` goes in too, and
    `respaldo_de` says which one of the ROM each backdrop of the game uses.
    **All of them go in the `.msu`**: `calidad` is their bytes, by number.

    A battler goes in if some troop of the cartridge uses it, **once** even if
    four use it, and it is the image with its hue: the GiantRat and the
    HairyVermin are the same `BLmouse` and two battlers.
    """
    E = escena_mod
    juego = E.fondos_del_juego(eventos.fondos_nombrados(game_dir), tree,
                               db.terrain_backdrops, game_dir)
    numero_de = {nombre.lower(): k for k, nombre in enumerate(juego)}
    if len(juego) >= FONDO_DEL_LUGAR:
        raise SystemExit("the game has %d battle backdrops and the number of "
                         "one is a byte, with $%02X and $FF reserved"
                         % (len(juego), FONDO_DEL_LUGAR))
    datos = {"juego": juego, "fondos": [], "battlers": [], "battler_de": {},
             "tropa_fondo": {}, "mapa_fondo": [], "respaldo_de": [],
             "terreno_fondo": [], "calidad": []}

    def numero(nombre):
        if nombre is None or nombre is eventos.FONDO_DEL_LUGAR:
            return FONDO_DEL_LUGAR
        return numero_de.get(nombre.lower(), FONDO_LISO) if nombre \
            else FONDO_LISO

    for n in tropas.ids:
        fondo = tropas.fondos.get(n)
        datos["tropa_fondo"][n] = numero(fondo) if fondo else FONDO_LISO
    # The map's, for random encounters and for the troops that fight with the
    # one of the place. Only in the maps where some battle can look at it:
    # without that, any cartridge would ask for the replacement.
    por_mapa = (encuentros or {}).get("por_mapa") or [0xFF] * len(mapas)
    del_lugar = FONDO_DEL_LUGAR in datos["tropa_fondo"].values()
    for mapa, registro in zip(mapas, por_mapa):
        if registro != 0xFF or del_lugar:
            datos["mapa_fondo"].append(
                numero(tree.map_background(mapa["id"])))
        else:
            datos["mapa_fondo"].append(FONDO_LISO)
    terrenos = db.terrain_backdrops
    datos["terreno_fondo"] = [numero(terrenos.get(t, "")) if terrenos.get(t)
                              else FONDO_LISO
                              for t in range(max(terrenos, default=0) + 1)]

    # The ROM's: all the ones asked for, in the order they are asked for —see
    # "Which backdrops there are" in escena.py—. A map with encounters that asks for the
    # one of the place asks for those of all the terrains of its blocks, which
    # are the ones the hero can stand on, substitutions included. A map
    # without encounters that asks for it anyway —because some troop fights
    # with the one of the place, and it isn't known where— doesn't: if its
    # terrain isn't there, the replacement goes.
    def de_los_terrenos(mapa):
        return [datos["terreno_fondo"][t]
                if t < len(datos["terreno_fondo"]) else FONDO_LISO
                for t in sorted(set(mapa["terreno"]))]
    pedidos = list(datos["tropa_fondo"].values()) + datos["mapa_fondo"]
    posibles = []
    for mapa, registro, k in zip(mapas, por_mapa, datos["mapa_fondo"]):
        if k != FONDO_DEL_LUGAR:
            continue
        if registro != 0xFF:
            pedidos += de_los_terrenos(mapa)
        else:
            posibles += de_los_terrenos(mapa)
    suyos = []
    for k in pedidos:
        if k < FONDO_DEL_LUGAR and k not in suyos:
            suyos.append(k)
    if any(k < FONDO_DEL_LUGAR and k not in suyos for k in posibles):
        reemplazo = numero_de[E.reemplazo().lower()]
        if reemplazo not in suyos:
            suyos.append(reemplazo)
    for k in suyos:
        info = E.fondo_liviano(juego[k], game_dir)
        datos["fondos"].append({"nombre": juego[k], "numero": k,
                                "respaldo": info})
    lugar = {k: i for i, k in enumerate(suyos)}
    reemplazo = lugar.get(numero_de[E.reemplazo().lower()], 0)
    datos["respaldo_de"] = [lugar.get(k, reemplazo) for k in range(len(juego))]
    # The quality ones, for the `.msu`: all of them, whether in the ROM or not.
    datos["calidad"] = in_parallel(
        lambda nombre: fondo_bytes(E.fondo(nombre, game_dir)), juego)
    battler_k = {}
    for numero in tropas.ids:
        if numero not in db.troops:
            continue
        for enemigo in db.troops[numero].members[:constantes.ENEMIGOS_MAX]:
            if enemigo in datos["battler_de"] or enemigo not in db.enemies:
                continue
            e = db.enemies[enemigo]
            nombre = e.battler_name or ""
            tono = getattr(e, "battler_hue", 0) or 0
            k = E.clave(nombre, tono)
            if k not in battler_k:
                info = E.battler(nombre, tono, game_dir) if nombre else None
                battler_k[k] = 0xFF if info is None else len(datos["battlers"])
                if info is not None:
                    datos["battlers"].append(info)
            datos["battler_de"][enemigo] = battler_k[k]
    return datos


def usos_de_los_parches(mapas, db, tree):
    """Who asks for each animation and each battler of the cartridge: per
    patch class, `{key: [origin, ...]}`, where the origin is the id of the map
    whose page or random encounter asks for it, or `"caso"` if a test page
    asks for it.

    It is what lets `parches.revisar` know what isn't the game's in the ROM
    that is played, which also carries the suite's maps and pages: an
    animation only a case asks for, or a battler that only shows up in a test
    map, isn't versioned. The bytecode is walked, as in
    `animaciones_de_la_rom`, so it counts what ended up emitted. A troop
    someone asked for and no emitted page names —a page that fell out after
    asking for it— has no origin, and `revisar` treats it as the game's: the
    doubt leans toward asking for the patch.
    """
    E = escena_mod
    animaciones = collections.defaultdict(set)
    tropas = collections.defaultdict(set)
    for mapa in mapas:
        for pagina in mapa.get("paginas", ()):
            origen = "caso" if pagina.get("prueba") else mapa["id"]
            codigo = pagina.get("codigo") or b""
            for i, c in eventos.recorrer_codigo(codigo):
                if (c[i] == eventos.OP_ANIMATION
                        and c[i + 1] != eventos.ANIM_SIN_DIBUJO):
                    animaciones[c[i + 1]].add(origen)
                elif c[i] == eventos.OP_BATTLE:
                    tropas[c[i + 1] | (c[i + 2] << 8)].add(origen)
        game_map = mapa["game_map"]
        for *_rect, cuales in eventos.zonas_de_encuentro(
                tree, mapa["id"], game_map.width, game_map.height):
            for numero in cuales:
                tropas[numero].add(mapa["id"])
    battlers = collections.defaultdict(set)
    for numero, origenes in tropas.items():
        if numero not in db.troops:
            continue
        for enemigo in db.troops[numero].members[:constantes.ENEMIGOS_MAX]:
            if enemigo not in db.enemies:
                continue
            e = db.enemies[enemigo]
            if e.battler_name:
                battlers[E.clave(e.battler_name,
                                 getattr(e, "battler_hue", 0) or 0)] |= origenes
    return {"animacion": animaciones, "battler": battlers}


def fondo_bytes(info):
    """A battle backdrop as the console reads it: `(tiles, colors)`, its 512
    8bpp tiles in tilemap order and its `COLORES` 15-bit colors, padded with
    black."""
    E = escena_mod
    tiles_ = bytearray()
    for celda in E.tiles(info["indices"]):
        tiles_ += pack_tile(celda, planes=8)
    colores = list(info["paleta"])
    colores += [(0, 0, 0)] * (E.COLORES - len(colores))
    cgram = bytearray()
    for color in colores:
        cgram += cgram_word(color).to_bytes(2, "little")
    return bytes(tiles_), bytes(cgram)


def respaldo_bytes(info):
    """The light fallback of a backdrop, as the ROM carries it: `(bytes,
    colors)`, its 4 KB of 128x64 at 4bpp and its `RESPALDO_COLORES` colors.
    They store the index **within their palette**: the ROM adds the planes of
    `CGRAM_BASE` separately, see `respaldo_alto`.

    **The bytes don't go in tile order**, but in the one `esc_doblar` enlarges
    them in without doing any arithmetic. Each small tile becomes four large
    ones, and the ROM fills them two neighbors of the same row at a time —the
    pair that comes from the same row of eight small pixels—, pair by pair in
    the scene's order. Of each pair, large row by large row two at a time (both
    come from the same small row) and planes 0/1 before 2/3.

    And within that, **each byte carries half a byte of two planes**: of the
    small row that gives planes `p` and `p+1`, the first carries the high
    nibble of both —the four leftmost pixels, which go to the left large
    tile— and the second the two low nibbles. That way each byte, duplicated
    bit by bit with `respaldo_doble`, is already the two-plane word of a row
    of a large tile, and the ROM writes it whole without separating the planes.
    """
    E = escena_mod
    liviano = info["respaldo"]
    chicos = [pack_tile([[v - E.CGRAM_BASE for v in fila] for fila in celda],
                        planes=E.RESPALDO_PLANOS)
              for celda in E.tiles(liviano["chico"])]
    columnas = E.RESPALDO_ANCHO // E.CELDA
    tiles_ = bytearray()
    for fila_grande in range(E.TILES_Y):
        mitad = fila_grande % E.RESPALDO_ESCALA     # above or below the small one
        for columna in range(columnas):
            chico = chicos[(fila_grande // E.RESPALDO_ESCALA) * columnas
                           + columna]
            for par in (0, 16):                     # planes 0/1 and 2/3
                for k in range(4):                  # the large rows 2k, 2k+1
                    fila = mitad * 4 + k            # the small row
                    p0, p1 = chico[par + 2 * fila], chico[par + 2 * fila + 1]
                    tiles_.append((p0 & 0xF0) | (p1 >> 4))
                    tiles_.append(((p0 & 0x0F) << 4) | (p1 & 0x0F))
    colores = list(liviano["paleta"])
    colores += [(0, 0, 0)] * (E.RESPALDO_COLORES - len(colores))
    cgram = bytearray()
    for color in colores:
        cgram += cgram_word(color).to_bytes(2, "little")
    return bytes(tiles_), bytes(cgram)


def respaldo_alto():
    """The upper half of an 8bpp tile of the fallback: planes 4 to 7, which
    are those of `CGRAM_BASE` in every pixel. It is what the ROM appends
    after each 4bpp tile."""
    E = escena_mod
    lleno = [[E.CGRAM_BASE] * E.CELDA for _ in range(E.CELDA)]
    return pack_tile(lleno, planes=8)[E.RESPALDO_PLANOS * 8:]


def respaldo_doble():
    """The table `esc_doblar` enlarges the fallback with: for each byte of
    `respaldo_bytes`, a word with its two nibbles duplicated bit by bit, the
    high one in the low byte. Each nibble is four pixels of one plane, and
    duplicated they are the eight of a row of that plane in a large tile."""
    def doble(nibble):
        return sum(0b11 << (2 * b) for b in range(4) if nibble >> b & 1)
    return b"".join((doble(s >> 4) | doble(s & 0xF) << 8).to_bytes(2, "little")
                    for s in range(256))


def escenas_asm(datos, tropas, db):
    """The cartridge's battle scene, ready for the `.inc`.

    The backdrops and the battlers **separately**, which the ROM composes when
    the battle starts: the reason and the format are in tools/port/escena.py.
    What is emitted:

      `escena_tropa_fondo`  per troop index —the order of `tropa_id`—, the
                            number of the backdrop its `EnemyEncounter` names,
                            `FONDO_DEL_LUGAR` or `FONDO_LISO`.
      `escena_mapa_fondo`   per map index, that of its random encounters: a
                            number, `FONDO_DEL_LUGAR` —the terrain's— or
                            `FONDO_LISO`.
      `fondo_terreno`       per terrain, the number of its backdrop or
                            `FONDO_LISO`.
      `fondo_respaldo`      per backdrop number, which one of the ROM replaces
                            it without MSU-1: its own, or that of
                            `escena.reemplazo()`.
      `fondo_dir`           per ROM backdrop, the 24-bit pointer to the 4 KB
                            of its light fallback, in the order of
                            `respaldo_bytes`.
      `fondo_cgram`         its 16 colors, which go to CGRAM from 32 on.

    Where each backdrop is in the `.msu` is emitted by `escribir_msu`, by
    number.
      `respaldo_alto`       planes 4 to 7, which the ROM appends to each tile.
      `battler_*`           per battler: how many bytes a row of one plane is,
                            how many rows, how big a plane is, where its bytes
                            are and its fifteen colors.
      `miembro_*`           per troop member —the order of `tropa_miembro`—,
                            which battler it is, where its corner falls and
                            which one of the troop goes in that place of the
                            drawing order.

    The tilemap isn't emitted: it is the 512 tiles in order and the ROM builds
    it with a loop. Emitting it would be 2 KB of cartridge to write 0, 1, 2...
    """
    E = escena_mod
    fondos, battlers = datos["fondos"], datos["battlers"]
    out = [
        "\n; --- the battle scene: the backdrops and the battlers ---",
        ";",
        "; They go separately and the ROM composes them in an 8bpp layer of",
        "; 256x128, which is the seven text lines at the top. The reason is",
        "; in tools/port/escena.py; only the bytes travel here.",
        "; The game's backdrops, which the .msu carries all of, and the ROM's.",
        "FONDOS_JUEGO    = %d" % len(datos.get("juego", ())),
        "ESCENA_FONDOS   = %d" % len(fondos),
        "FONDO_LISO      = $%02X" % FONDO_LISO,
        "FONDO_DEL_LUGAR = $%02X" % FONDO_DEL_LUGAR,
        "FONDO_TERRENOS  = %d" % len(datos.get("terreno_fondo") or [0]),
        "ESCENA_BATTLERS = %d" % len(battlers),
        "ESCENA_ANCHO    = %d" % E.ANCHO,
        "ESCENA_ALTO     = %d" % E.ALTO,
        "ESCENA_TILES    = %d" % E.TILES,
        "ESCENA_FILAS    = %d" % E.TILES_Y,
        "ESCENA_COLUMNAS = %d" % E.TILES_X,
        "ESCENA_COLORES  = %d" % E.COLORES,
        "ESCENA_CGRAM    = %d" % E.CGRAM_BASE,
        "ESCENA_VRAM     = $%04X" % E.VRAM_TILES,
        "ESCENA_MAPA     = $%04X" % E.VRAM_MAPA,
        "; The ROM's light fallback: 4bpp and a single palette. See",
        "; tools/port/escena.py.",
        "RESPALDO_COLORES = %d" % E.RESPALDO_COLORES,
        "RESPALDO_TILE   = %d" % (E.RESPALDO_PLANOS * 8),
        "RESPALDO_BYTES  = %d" % (E.RESPALDO_ANCHO * E.RESPALDO_ALTO
                                  * E.RESPALDO_PLANOS // 8),
        "RESPALDO_ESCALA = %d" % E.RESPALDO_ESCALA,
        "ESCENA_BAT_PALETA = %d" % E.BATTLER_PALETA,
        "; The tile that covers what is left below the scene. It falls",
        "; **outside** the tile block: 512 8bpp tiles are the 16,384 words",
        "; that go from ESCENA_VRAM to the end of VRAM, so 512 wraps around",
        "; and lands on word 0, which during the battle is map VRAM that",
        "; nobody uses.",
        "ESCENA_BLANCO   = %d" % E.TILES,
    ]
    usadas = [n for n in tropas if n in db.troops]
    out.append(bloque("escena_tropa_fondo", bytes(
        datos["tropa_fondo"].get(n, 0xFF) for n in usadas) or b"\xFF"))
    out.append(bloque("escena_mapa_fondo",
                      bytes(datos["mapa_fondo"]) or b"\xFF"))
    out.append(bloque("fondo_terreno",
                      bytes(datos.get("terreno_fondo") or [FONDO_LISO])))
    out.append(bloque("fondo_respaldo",
                      bytes(datos.get("respaldo_de") or [0])))
    punteros = [".bloque %d" % (4 * max(1, len(fondos))), "fondo_dir:"]
    for k in range(len(fondos)):
        punteros.append("    .dword fondo_%d" % k)
    if not fondos:
        punteros.append("    .dword 0")
    out.append("\n".join(punteros))
    bytes_de = [respaldo_bytes(info) for info in fondos]
    cgram = b"".join(colores for _tiles, colores in bytes_de)
    out.append(bloque("fondo_cgram", cgram or b"\x00\x00"))
    out.append(bloque("respaldo_alto", respaldo_alto()))
    out.append(bloque("respaldo_doble", respaldo_doble()))
    # Where each quality backdrop is in the `.msu` and the signature the ROM
    # expects to find at the start don't go here: the `.msu` also carries the
    # sound effects, which come from the audio, and that is built later. See
    # `msu_asm`.
    # Sixty-four zeros: the transparent tile that covers what is left below
    # the scene, and incidentally the fixed source of the DMA that fills the
    # plain backdrop with zero.
    out.append(bloque("escena_cero", bytes(64)))
    # Each fallback in a block, which doesn't cross a bank because the ROM
    # reads it with `[puntero]` and adds to the pointer only the low sixteen
    # bits.
    for k, (tiles_, _colores) in enumerate(bytes_de):
        out.append(bloque("fondo_%d" % k, tiles_))
    # The battlers: their tables and then their bytes, each in a block that
    # doesn't cross a bank because the ROM reads it with `[puntero], y`.
    out.append(bloque("battler_n", bytes(
        E.columnas(b) for b in battlers) or b"\x00"))
    out.append(bloque("battler_alto", bytes(
        b["alto"] for b in battlers) or b"\x00"))
    planos = bytearray()
    for b in battlers:
        planos += ((E.columnas(b) + 1) * b["alto"]).to_bytes(2, "little")
    out.append(bloque("battler_plano", bytes(planos) or b"\x00\x00"))
    punteros = [".bloque %d" % (4 * max(1, len(battlers))), "battler_dir:"]
    punteros += ["    .dword battler_%d" % k for k in range(len(battlers))]
    if not battlers:
        punteros.append("    .dword 0")
    out.append("\n".join(punteros))
    cgram = bytearray()
    for b in battlers:
        colores = [(0, 0, 0)] + list(b["paleta"])
        colores += [(0, 0, 0)] * (16 - len(colores))
        for color in colores:
            cgram += cgram_word(color).to_bytes(2, "little")
    out.append(bloque("battler_cgram", bytes(cgram) or b"\x00\x00"))
    miembro_b, miembro_x, miembro_y, miembro_orden = [], [], [], []
    for numero in usadas:
        tropa = db.troops[numero]
        suyos = list(zip(tropa.members,
                         tropa.positions))[:constantes.ENEMIGOS_MAX]
        infos = []
        for enemigo, centro in suyos:
            k = datos["battler_de"].get(enemigo, 0xFF)
            miembro_b.append(k)
            infos.append(battlers[k] if k != 0xFF else None)
            x, y = (E.posicion(centro, battlers[k]) if k != 0xFF else (0, 0))
            miembro_x.append(x)
            miembro_y.append(y)
        # And the order they are drawn in, which isn't the troop's: see
        # `escena.orden_de_dibujo`. It goes per member, with the place in the
        # troop.
        miembro_orden += E.orden_de_dibujo([c for _e, c in suyos], infos)
    out.append(bloque("miembro_battler", bytes(miembro_b) or b"\xFF"))
    out.append(bloque("miembro_x", bytes(miembro_x) or b"\x00"))
    out.append(bloque("miembro_y", bytes(miembro_y) or b"\x00"))
    out.append(bloque("miembro_orden", bytes(miembro_orden) or b"\x00"))
    for k, b in enumerate(battlers):
        out.append(bloque("battler_%d" % k, E.battler_bytes(b)))
    return "\n".join(out) + "\n"


def bloque(label, data, per_line=16, alinear=None, acomodar=True):
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

    `acomodar=False` is for what goes to TABLAS: that area lives entirely
    inside bank 0 —it ends at $7FC0—, so nothing that falls there can cross,
    and declaring it emitted a computation that always came out zero.
    """
    out = ([".align %d" % alinear if alinear else ".bloque %d" % len(data)]
           if acomodar else [])
    out.append("%s:" % label)
    for i in range(0, len(data), per_line):
        out.append("    .byte " + ",".join("$%02X" % b
                                           for b in data[i:i + per_line]))
    return "\n".join(out)


def tabla_de_paginas(mapa, numero, evcodigo):
    """The map's event pages, with the pointer to their code.

    `evcodigo` is the **label** of the code block, which can no longer be
    rebuilt here: two maps whose events compile to the same bytes share the
    block and the label doesn't carry this map's number. Rebuilding it is what
    it did —`"evcodigo_%d" % numero`— and when deduplication was turned on the
    suite caught it right away: `varios` didn't assemble because it named an
    `evcodigo_2` that no longer existed.

    It doesn't go through `bloque()` because its pointers are symbolic: they
    point inside the code block, which the linker places. But it **is
    declared** with `.bloque`: the ROM walks it with `[pag_ptr], y`, and a
    table that crosses a bank continues at `$03:0000`, which in LoROM isn't
    ROM but the WRAM mirror. Without the declaration it really happened: when
    map 2's sprites grew with the events drawn with a tile, the table ended up
    straddling `$02FFFF`, the ROM read garbage instead of the last pages
    —among them the test one— and the shake at the edge of the map never
    started. The suite caught it in pixels without saying why; the
    emulator's RAM said it.
    """
    out = [".bloque %d" % (PAGINA_BYTES * len(mapa["paginas"])),
           "paginas_%d:" % numero]
    # Which events have some page with its own route: the ROM's refresh only
    # looks at the pages of those, and doesn't spend a single read on the rest.
    con_ruta = {p["evento"] for p in mapa["paginas"] if p.get("ruta_propia")}
    # And which ones change graphic with the page: the refresh also looks at
    # those, bit 5, and copies to the row what the active page draws.
    cambian = mapa.get("cambian", set())
    # And which ones only appear and disappear with it: the ones that walk.
    # They go by the **same** bit 5, because none is left free in +13 —with an
    # own route the five low ones are the route's flags, and 4 is "the
    # animation continues while still"—. The one telling them apart is the
    # ROM, which already knows whether the row walks: `npc_buf + 9` holds
    # NPC_QUIETO or the bank of its twelve poses. See `grafico_de_pagina` in
    # tools/runtime/paginas_de_eventos.s.
    aparecen = mapa.get("aparecen", set())
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
    # `elegir_paginas` doesn't even note which one is active —it filters by
    # $E0— and `paralelos_tick` would have nowhere to get its code from.
    con_auto = {p["evento"] for p in mapa["paginas"]
                if p["trigger"] in (eventos.TRIGGER_AUTOMATICO,
                                    eventos.TRIGGER_PARALELO) and p["codigo"]}
    for pagina in mapa["paginas"]:
        if pagina["codigo"]:
            destino = "%s + %d" % (evcodigo, pagina["offset"])
            puntero = "<(%s), >(%s), ^(%s)" % (destino, destino, destino)
        else:
            puntero = "$00, $00, $00"   # no code: nothing to run
        out.append("    .word %-4d ; +0  the event it belongs to"
                   % pagina["evento"])
        out.append("    .byte %-4d ; +2  its page number" % pagina["pagina"])
        out.append("    .byte %-4d ; +3  what triggers it" % pagina["trigger"])
        out.append("    .word %-4d ; +4  switch it asks for, or 0" % pagina["switch_a"])
        out.append("    .word %-4d ; +6  the second, or 0" % pagina["switch_b"])
        out.append("    .byte %s ; +8  its code" % puntero)
        out.append("    .byte %-4d ; +11 the actor it asks for in the party, or 0"
                   % pagina["actor"])
        out.append("    .byte %-4d ; +12 its layer: 1 is the hero's, the one "
                   "that blocks its way" % pagina["capa"])
        propia = pagina.get("ruta_propia")
        if propia:
            # The page's own route, the one it walks by itself: see
            # `eventos.ruta_propia`. The flags: bit 0 it has one, 1 it
            # repeats, 2 it skips what is blocked, 3 it always faces the same
            # way, 4 the animation continues while still.
            banderas = (1 | (2 if propia["repite"] else 0)
                        | (4 if propia["saltable"] else 0)
                        | (8 if propia["dir_fija"] else 0)
                        | (16 if propia["anim_continua"] else 0) | 64
                        | (32 if pagina["evento"] in cambian
                                 or pagina["evento"] in aparecen else 0)
                        | (128 if pagina["evento"] in con_auto else 0))
            destino = "%s + %d" % (evcodigo, pagina["ruta_offset"])
            out.append("    .byte %-4d ; +13 the flags of its own route"
                       % banderas)
            out.append("    .byte %-4d ; +14 its frequency" % propia["frecuencia"])
            out.append("    .byte %-4d ; +15 and its speed" % propia["velocidad"])
            out.append("    .byte <(%s), >(%s), ^(%s) ; +16 its commands"
                       % (destino, destino, destino))
            out.append("    .byte %-4d ; +19 how many" % len(propia["ordenes"]))
        else:
            out.append("    .byte %-4d ; +13 no own route; bit 6 says whether "
                       "another page of the event has one, 5 whether the "
                       "graphic follows the page, 7 whether the event has some "
                       "automatic one"
                       % ((64 if pagina["evento"] in con_ruta else 0)
                          | (32 if pagina["evento"] in cambian
                                   or pagina["evento"] in aparecen else 0)
                          | (128 if pagina["evento"] in con_auto else 0)))
            out.append("    .byte %-4d ; +14 its frequency" % pagina["frecuencia"])
            out.append("    .byte %-4d ; +15 and its speed, that of a route "
                       "forced on the event" % pagina["velocidad"])
            out.append("    .byte 0,0,0,0")
        # +20..+23: what the page draws, for the events that change graphic:
        # the tile, the attributes with the palette and the priority of its
        # layer, the pose with bit 7 set if there is a graphic, and the
        # passage bits of its tile or $FF. It is what the refresh copies to
        # the row.
        oam = pagina.get("oam")
        if oam is None:
            out.append("    .byte $00, $00, $00, $FF ; +20 no graphic")
        else:
            out.append("    .byte $%02X, $%02X, $%02X, $%02X ; +20 its graphic: "
                       "tile, attributes, pose, passage" % oam)
        # +24..+27: the variable condition: the slot or $FF, how it is
        # compared —==, >=, <=, >, <, !=— and against what, signed. It is what
        # `condiciones_ok` passes to `comparar_var`.
        variable = pagina.get("variable")
        if variable is None:
            out.append("    .byte $FF, 0 ; +24 no variable condition")
            out.append("    .word 0")
        else:
            ranura, comparacion, contra = variable
            out.append("    .byte %d, %d ; +24 the variable it asks for and the "
                       "comparison" % (ranura, comparacion))
            out.append("    .word %d ; +26 against what" % (contra & 0xFFFF))
        # +28: the item it asks to have, or 0: `condiciones_ok` looks at its
        # count in `FAR_ITEMS`.
        out.append("    .word %-4d ; +28 the item it asks for, or 0" % pagina["item"])
        # +30 and +31: the turn toward the hero. Which entry of `npc_poses`
        # the poses of its graphic are in, or $FF if the page doesn't turn,
        # and its pose. When triggered, the ROM uploads the one facing the
        # hero; on a refresh, a change to a page that doesn't turn or has
        # another graphic undoes the turn. See TURN in eventos.py.
        grafico = pagina.get("grafico")
        k = (mapa.get("giro_k", {}).get(tuple(grafico[:2]))
             if pagina.get("gira") and grafico and pagina["evento"] in
             mapa.get("giran", ()) else None)
        out.append("    .byte $%02X, %d ; +30 the turn: its poses and its pose"
                   % (0xFF if k is None else k, grafico[2] if k is not None else 0))
        assert PAGINA_BYTES == 32
    if not mapa["paginas"]:
        out.append("    .byte $00")     # a label can't be left empty
    return "\n".join(out)


class Materiales:
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

    The poses already worked this way from before —`indice_global` in `emit`—
    and that is where the shape comes from.
    """

    def __init__(self, deduplicar=False, comprimidos=None):
        self.deduplicar = deduplicar
        self.donde = {}
        self.cuantos = collections.Counter()
        self.ahorro = collections.Counter()
        self.repetidos = collections.Counter()
        # {raw bytes: their LZ2 stream}, already compressed in one go: see
        # `comprimir_los_bloques`. And how much each class weighed and weighs,
        # of the blocks that were emitted.
        self.comprimidos = comprimidos or {}
        self.crudo = collections.Counter()
        self.lz2 = collections.Counter()

    def guardar_comprimido(self, clase, datos):
        """Like `guardar`, but what goes to the cartridge is its LZ2 stream, or
        its streams stuck together if the block goes in pieces: see
        `partes_comprimidas`. It is deduplicated by the raw content, which is
        the same as by the stream."""
        datos = bytes(datos)
        flujo = b"".join(self.comprimidos[parte]
                         for parte in partes_comprimidas(clase, datos))
        etiqueta, texto = self.guardar(clase, flujo)
        if texto:
            self.crudo[clase] += len(datos)
            self.lz2[clase] += len(flujo)
        return etiqueta, texto

    def guardar(self, clase, datos, alinear=None):
        """(label, the asm to emit). The asm is empty if the block was already
        there.

        The key includes the class and the placement, not only the content:
        two blocks with the same bytes but a different `.bloque` or `.align`
        aren't the same block for the linker.
        """
        datos = bytes(datos)
        clave = (clase, alinear, datos)
        if clave in self.donde:
            if self.deduplicar:
                self.ahorro[clase] += len(datos)
                self.repetidos[clase] += 1
                return self.donde[clave], ""
        etiqueta = "%s_%d" % (clase, self.cuantos[clase])
        self.cuantos[clase] += 1
        self.donde.setdefault(clave, etiqueta)
        return etiqueta, bloque(etiqueta, datos, alinear=alinear)

    def informe(self):
        """What was shared and how much was compressed, so that the saving is a
        number and not an idea."""
        lineas = ["  %-14s %6.1f KB in LZ2, was %6.1f"
                  % (clase, self.lz2[clase] / 1024.0,
                     self.crudo[clase] / 1024.0)
                  for clase in CLASES_COMPRIMIDAS if self.crudo[clase]]
        if self.crudo:
            lineas.append("  %-14s %6.1f KB in LZ2, was %6.1f: %.1f KB less"
                          % ("", sum(self.lz2.values()) / 1024.0,
                             sum(self.crudo.values()) / 1024.0,
                             (sum(self.crudo.values())
                              - sum(self.lz2.values())) / 1024.0))
        if not self.deduplicar or not self.ahorro:
            return lineas
        return lineas + ["  %-14s %2d shared block(s), %6.1f KB"
                % (clase, self.repetidos[clase], self.ahorro[clase] / 1024.0)
                for clase, _ in self.ahorro.most_common()] + [
            "  %-14s %2d              %6.1f KB in total"
            % ("", sum(self.repetidos.values()),
               sum(self.ahorro.values()) / 1024.0)]


def terreno_plano(mapa):
    """The terrain the whole map has, or 0 if it has more than one.

    0 isn't a terrain: RM2k's are indices into `Data.terrains` and start at 1,
    so it serves as "there is a table here" without spending another field. A
    map with terrain 0 —which doesn't exist— falls into the table branch,
    which answers the same.
    """
    unicos = set(mapa["terreno"])
    return unicos.pop() if len(unicos) == 1 else 0


def terreno_del_mapa(mapa):
    return (bytes([terreno_plano(mapa)]) if terreno_plano(mapa)
            else bytes(mapa["terreno"]))


# What the ROM decompresses when loading a map, per block class. See
# `lz2_descomprimir` in tools/runtime/descomprimir.s.
CLASES_COMPRIMIDAS = ("map_tiles", "above_tiles", "sprite_tiles", "anim_tiles",
                      "map_celdas")

# The largest each decompressed stream can be, by where it lands in WRAM: see
# the LZ2 reservation in tools/runtime/ram_lejana.s, which is where they come
# from, and the `.assert` in descomprimir.s, which checks them against the
# ones here. The background tiles are decompressed before the animation
# drawings and can step on their place; the upper layer and the sprites go
# after and can't.
#
# The background's is **per stream**, not per block: a background of more
# than 32 KB —that of map 66, with the 544-tile layout— goes in two, and the
# ROM decompresses and uploads the first before decompressing the second on
# top of it: see `lz2_fondo`.
LZ2_TOPE_FONDO = 0x8000
LZ2_TOPE_ENCIMA_Y_SPRITES = 0x6000
LZ2_TOPE_ANIM = 0x2000
LZ2_TOPE_GRILLA = 0x10000       # two halves of GRILLA_MITAD


# What decompressing costs in the ROM, in master cycles, **on the high side**:
# measured on 2026-09-26 over the forty maps of `release`, against loading
# uncompressed, what was measured doesn't exceed this model by more than half
# a frame. An NTSC frame is 357,954 master cycles. The boot computation uses
# it.
LZ2_CICLOS_POR_COMANDO = 700
LZ2_CICLOS_POR_BYTE = 60
CICLOS_POR_CUADRO = 357954


def cuadros_de_descomprimir(mapa, comprimidos):
    """How many frames decompressing a map's blocks takes."""
    ciclos = 0
    for clase, datos in crudos_del_mapa(mapa).items():
        if clase not in CLASES_COMPRIMIDAS:
            continue
        for parte in partes_comprimidas(clase, datos):
            ciclos += (comprimir.comandos(comprimidos[parte])
                       * LZ2_CICLOS_POR_COMANDO
                       + len(parte) * LZ2_CICLOS_POR_BYTE)
    return ciclos / float(CICLOS_POR_CUADRO)


def comprimir_los_bloques(mapas):
    """{raw bytes: LZ2 stream} of everything the cartridge carries
    compressed, with a single `lz2` process. Along the way it enforces the
    WRAM caps."""
    partes = []
    for mapa in mapas:
        for clase, datos in crudos_del_mapa(mapa).items():
            if clase not in CLASES_COMPRIMIDAS:
                continue
            controlar_flujos(mapa["id"], clase, datos)
            partes += partes_comprimidas(clase, datos)
    partes = list(dict.fromkeys(partes))
    return dict(zip(partes, comprimir.comprimir_varios(partes)))


# The grid goes to the upper half of the two WRAM banks —see `lz2_grilla`—, so
# it is compressed in two streams of up to 32 KB: each one lands whole in one
# bank, and the decompressor doesn't have to know how to cross.
GRILLA_MITAD = 0x8000


# And the background tiles, in streams of whatever fits in the load buffer:
# the ROM decompresses one, uploads it by DMA and only then decompresses the
# next in the same place —see `lz2_fondo`—. A background that fits in one
# goes in one, and that leaves the usual maps with the usual stream.
FONDO_FLUJOS_MAX = 2            # the ones `lz2_fondo` reads


def partes_comprimidas(clase, datos):
    """The pieces of a block that are each compressed in their own stream."""
    if clase == "map_celdas":
        return [datos[:GRILLA_MITAD], datos[GRILLA_MITAD:]]
    if clase == "map_tiles" and len(datos) > LZ2_TOPE_FONDO:
        return [datos[k:k + LZ2_TOPE_FONDO]
                for k in range(0, len(datos), LZ2_TOPE_FONDO)]
    return [datos]


# How much of each stream fits in WRAM, and how many streams the ROM reads per
# block. The grid always goes in two, one per half; the rest in one, except
# the background.
TOPES_POR_FLUJO = {"map_tiles": (LZ2_TOPE_FONDO, FONDO_FLUJOS_MAX),
                   "above_tiles": (LZ2_TOPE_ENCIMA_Y_SPRITES, 1),
                   "sprite_tiles": (LZ2_TOPE_ENCIMA_Y_SPRITES, 1),
                   "anim_tiles": (LZ2_TOPE_ANIM, 1),
                   "map_celdas": (GRILLA_MITAD, 2)}


def controlar_flujos(map_id, clase, datos):
    """That each stream of the block fits in its WRAM place, and that there
    aren't more streams than the ROM reads. A stream that goes over breaks
    nothing when building: the ROM decompresses it anyway and steps on
    whatever is behind —with map 66's background, the upper half of the
    grid—, and it shows or not depending on the map."""
    tope, cuantos = TOPES_POR_FLUJO[clase]
    partes = partes_comprimidas(clase, datos)
    for parte in partes:
        if len(parte) > tope:
            raise SystemExit(
                "map %d: a stream of %s is %d bytes and %d fit in WRAM: "
                "see the LZ2 reservation in tools/runtime/ram_lejana.s"
                % (map_id, clase, len(parte), tope))
    if len(partes) > cuantos:
        raise SystemExit(
            "map %d: %s is %d bytes, which is %d streams, and the ROM reads %d"
            % (map_id, clase, len(datos), len(partes), cuantos))


def crudos_del_mapa(mapa):
    """{class: the uncompressed bytes} of a map, for `CLASES_COMPRIMIDAS`."""
    above, sprite = mapa["above"], mapa["sprite"]
    return {"map_tiles": bytes(mapa["tiles"]),
            "above_tiles": bytes(above[0]),
            "sprite_tiles": bytes(sprite[0]) if sprite else b"",
            "anim_tiles": bytes(mapa["anim"]),
            "map_celdas": bytes(mapa["celdas"])}


def escribir_crudos(directorio, mapas):
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
    donde = os.path.join(directorio, "crudos")
    if os.path.isdir(donde):
        shutil.rmtree(donde)
    os.makedirs(donde)
    for numero, mapa in enumerate(mapas):
        for clase, datos in crudos_del_mapa(mapa).items():
            with open(os.path.join(donde, "%d.%s.bin" % (numero, clase)),
                      "wb") as f:
                f.write(datos)


def datos_del_mapa(mapa, numero, indice_global, materiales):
    """A map's data blocks, with the number attached to each label.

    `indice_global` are the labels of the twelve poses of each (CharSet,
    index) **as this map quantized it**: see `banco_de_poses`, and the pose
    split in `emit`.
    """
    above, sprite = mapa["above"], mapa["sprite"]
    pares = [
        ("map_tiles", mapa["tiles"]),
        ("map_cgram", mapa["cram"]),
        ("above_tiles", above[0]),
        ("above_cgram", above[1]),
        ("sprite_tiles", sprite[0] if sprite else b""),
        ("sprite_cgram", sprite_colors_bytes(sprite)),
        ("map_bloques", mapa["bloques"]),
        ("bloque_pass", mapa["pass"]),
        # The terrain per block. A map whose terrain is the same everywhere
        # —the 328 of this game, which have it at 1— emits **one byte** and
        # `TERRENO_PLANO` says which: the whole table would be about eight
        # kilobytes of nothing spread over the forty maps. The byte is
        # deduplicated by `materiales`, so all flat maps with the same terrain
        # share the same one.
        ("bloque_terreno", terreno_del_mapa(mapa)),
        ("npc_table", npc_bytes(sprite[3]) if sprite else b""),
        # Two bytes per graphic of command 34: its entry in `npc_poses` —or
        # $FF, which is hiding— and its palette. See `Graficos` in eventos.py.
        ("ruta_grafico",
         bytes(b for par in (sprite[9] if sprite else []) for b in par)),
        ("ev_pos", mapa["ev_pos"]),
        ("evcodigo", mapa["evcodigo"]),
        ("anim_tiles", mapa["anim"]),
    ]
    etiquetas, out = {}, []
    for nombre, datos in pares:
        if nombre in CLASES_COMPRIMIDAS:
            etiquetas[nombre], texto = materiales.guardar_comprimido(nombre, datos)
        else:
            etiquetas[nombre], texto = materiales.guardar(nombre, datos)
        if texto:
            out.append(texto)
    # The two tables of pointers to the ROM's poses: that of the NPCs that
    # walk and that of the leader candidates.
    animados = sprite[7] if sprite else []
    out.append(npc_poses_asm(numero, animados, indice_global))
    out.append(actor_table_asm(numero, sprite[4] if sprite else [],
                               animados, indice_global))
    # The grid, in its two streams: see `lz2_grilla`. Whole within one bank,
    # like everything compressed, because the decompressor doesn't cross.
    etiquetas["map_celdas"], texto = materiales.guardar_comprimido(
        "map_celdas", mapa["celdas"])
    if texto:
        out.append(texto)
    out.append(tabla_de_paginas(mapa, numero, etiquetas["evcodigo"]))
    # The three that aren't shared are the ones that carry **symbolic
    # pointers** inside —to the ROM's poses, to the events' code—: their bytes
    # are set by the linker, so here there is no content to compare them by.
    for nombre in ("npc_poses", "actor_table", "paginas"):
        etiquetas[nombre] = "%s_%d" % (nombre, numero)
    return "\n".join(out), etiquetas


def encuentros_de_la_rom(mapas, tree, pasos_de_prueba, tropas):
    """The random encounters of each map of the cartridge, ready to emit.

    The data lives in the tree and not in the `.lmu`: each node brings its
    list of troops, every how many steps, and —if it is an area— the
    rectangle it covers. See `eventos.zonas_de_encuentro`.

    Along the way it **asks for the troops**, which is what makes the
    cartridge carry their enemies and the battle's audio package: without
    that an encounter would start a battle against a troop that isn't in any
    table.

    `pasos_de_prueba` replaces the `encounter_steps` of every map. It is for
    the test ROMs: with the game's —from 25 to 85— an encounter takes more than
    a hundred steps, which is what is wanted when playing and not what is
    wanted in a case of the suite.
    """
    registros, zonas, tropas_de_zona, por_mapa = [], [], [], []
    for mapa in mapas:
        game_map = mapa["game_map"]
        suyas = eventos.zonas_de_encuentro(tree, mapa["id"],
                                           game_map.width, game_map.height)
        pasos = (pasos_de_prueba if pasos_de_prueba is not None
                 else tree.encounter_steps.get(mapa["id"],
                                               eventos.ENC_PASOS_DEFECTO))
        if not suyas or not eventos.enc_base(pasos):
            por_mapa.append(0xFF)
            continue
        por_mapa.append(len(registros))
        registro = {"base": eventos.enc_base(pasos),
                    "umbrales": eventos.enc_umbrales_de_paso(pasos),
                    "zona_ini": len(zonas), "zona_n": len(suyas)}
        for izq, arr, der, aba, cuales in suyas:
            zonas.append({"rect": (izq, arr, der, aba),
                          "tropa_ini": len(tropas_de_zona),
                          "tropa_n": len(cuales)})
            for numero in cuales:
                tropas.pedir(numero)
            tropas_de_zona += cuales
        registros.append(registro)
    if len(registros) > 0xFF or len(zonas) > 0xFF or len(tropas_de_zona) > 0xFF:
        # The three tables are indexed with one byte. With the 53 maps of the
        # whole game it is 53 records, 56 zones and 322 troops, so the one
        # that can go over is the last —and today only in a cartridge that
        # carries all of them—.
        sys.exit("the encounters don't fit in one-byte tables: %d "
                 "record(s), %d zone(s), %d troop(s)"
                 % (len(registros), len(zonas), len(tropas_de_zona)))
    return {"por_mapa": por_mapa, "registros": registros, "zonas": zonas,
            "tropas": tropas_de_zona}


# The header title of a SNES ROM: 21 bytes, at `$FFC0`.
TITULO_CABECERA = 21


def identidad_de_la_rom():
    """What the ROM says about itself, from the `[rom]` of the project file:
    the header title, already padded with blanks, and the save signature in
    SRAM. They are `.define`s because they are text: `cabecera.s` and
    `partida.s` use them, and until 2026-09-29 they had them written in."""
    titulo = settings.ascii("rom", "title", max_length=TITULO_CABECERA)
    firma = settings.ascii("rom", "sram_signature", length=4)
    return ("; Who the ROM is, from the project file: the header title and\n"
            "; the signature with which the SRAM says a slot holds a save of\n"
            "; this game.\n"
            '.define ROM_TITULO "%s"\n'
            '.define SRAM_MAGIA_TEXTO "%s"\n\n'
            % (titulo.ljust(TITULO_CABECERA), firma))


def emit(path, mapas, inicial=0, heroe_encima=False, grupo_inicial=(),
         ventana=None, titulo=None, ranuras=None, cartel=None,
         animaciones=None, tropas=(), audio_batalla=None, escenas=None,
         encuentros=None, paginas_tropa=None, comprimidos=None,
         hp_de_enemigos=False, game_over=None):
    """The .inc that is assembled together with main.s.

    `hp_de_enemigos` is `--hp-de-enemigos`: whether the battle draws the
    enemies' HP, which RM2k doesn't show.

    `comprimidos` is what `comprimir_los_bloques` returns; if missing it is
    compressed here.

    `titulo` is the title screen —the image and its menu— and may be missing;
    `game_over`, the Game Over one, too: it is what
    `pantalla_completa.comprimida` returns.
    `ranuras` is the slots screen and **always goes**: the save point opens it
    from inside the game, whether the ROM has a title or not. See
    `pantalla_ranuras` in menus.py.
    """
    for numero, mapa in enumerate(mapas):
        layout = mapa["layout"]
        for cuantos, nombre in (
                (len(mapa["tiles"]) // BYTES_PER_TILE, "tiles"),
                (len(mapa["above"][0]) // 32, "encima"),
                (len(mapa["sprite"][0]) // 32 if mapa["sprite"] else 0,
                 "sprites")):
            if cuantos > layout[nombre][1]:
                raise SystemExit(
                    "map %d: with this VRAM layout, %s needs %d tiles and "
                    "%d fit" % (mapa["id"], nombre, cuantos,
                                layout[nombre][1]))

    # Where the picture ended up: the map of the table that took its tiles, and
    # at which tile and with which palette. It comes from the already
    # converted maps and not from a variable that has to be passed around: the
    # one that has it is the only one with a nonzero `imagen_base`.
    cartel_base, cartel_pal = 0, 0
    for mapa in mapas:
        if mapa["sprite"] and mapa["sprite"][13]:
            cartel_base, cartel_pal = mapa["sprite"][13], mapa["sprite"][14]
            break

    cabecera = (
        "; Generated by tools/port/snes_convert.py. Do not edit.\n"
        "; Maps: %s\n\n"
        "MAPA_COUNT   = %d\n"
        "MAPA_STRIDE  = %d\n"
        "MAPA_INICIAL = %d\n"
        "; What doesn't depend on the map: the upper layer's tilemap always\n"
        "; lives in the same place in VRAM —the background's is chosen by the\n"
        "; layout, M_VRAM_MAP—, and the NPC table's stride doesn't change.\n"
        "VRAM_ABOVE_MAP = $%04X\n"
        "MAP_LAYOUT  = %d\n"
        "NPC_STRIDE  = %d\n"
        "NPC_MAX     = %d\n"
        "NPC_QUIETO  = $%02X\n"
        "; The event position table, and how many forced routes can be\n"
        "; running on them at once.\n"
        "EV_STRIDE   = %d\n"
        "EV_MAX      = %d\n"
        "RUTA_EV_MAX = %d\n"
        "PAGINA_BYTES = %d\n"
        "GIRO_NINGUNO = $%04X\n"
        "; And how many distinct graphics command 34 can ask for in a map:\n"
        "; its table is copied to RAM like the NPC one.\n"
        "RUTA_GRAF_MAX = %d\n"
        "; The header of a text box, which is the first byte of the one\n"
        "; `OP_MESSAGE` names: the lines in the low three bits, the\n"
        "; auto-close of `\\^` in bit 3 and how many `\\|` pauses it carries in\n"
        "; the high nibble. And how long each pause lasts, which is 61 frames\n"
        "; and not 60: see CUADROS_DE_PAUSA in eventos.py.\n"
        "CABECERA_LINEAS     = $%02X\n"
        "CABECERA_AUTOCIERRE = $%02X\n"
        "CUADROS_DE_PAUSA    = %d\n"
        "; The top bit of the flags byte of the opcodes that write a\n"
        "; variable: whether the write asks for the page refresh. The\n"
        "; converter resolves it by looking at which variables this map's\n"
        "; page conditions look at; `var_apuntar` masks the slot with\n"
        "; VAR_RANURA. See VAR_REFRESCO in eventos.py: without this half of\n"
        "; Lashe City ran at 30 frames.\n"
        "VAR_REFRESCO = $%02X\n"
        "VAR_RANURA   = $%02X\n"
        "ANIM_ENTRADA = %d\n"
        "ANIM_SONIDO  = %d\n"
        "ANIM_DESTELLO = %d\n"
        "; The ShowPicture picture: where its corner falls on the console's\n"
        "; screen and how many 32x32 objects it measures.\n"
        "; The coordinates already come scaled from 320x240 to 256x224 and X\n"
        "; can be negative: the \"1 year earlier\" picture goes off the left\n"
        "; edge, which is what RM2k shows. See tools/port/imagen.py.\n"
        "; The flags of `KeyInputProc`, which go in the second byte of\n"
        # `rom/src/` on purpose: it goes into the `.inc`, which isn't touched
        # yet.
        "; OP_KEY. See `op_key` in rom/src/interprete_teclas_y_esperas.s.\n"
        "TECLA_ESPERA   = $%02X\n"
        "TECLA_DIRS     = $%02X\n"
        "TECLA_DECISION = $%02X\n"
        "TECLA_CANCELAR = $%02X\n"
        "TECLA_ARRANCA  = $%02X\n"
        "TECLA_VALOR_DECISION = %d\n"
        "TECLA_VALOR_CANCELAR = %d\n"
        "; And the four directions, with the same number `CheckInput` gives\n"
        "; them. The order they are checked in comes from here: from highest\n"
        "; to lowest, which is what \"RPG processes keys from highest\n"
        "; variable value to lowest\" says.\n"
        "TECLA_VALOR_ARRIBA   = %d\n"
        "TECLA_VALOR_DERECHA  = %d\n"
        "TECLA_VALOR_IZQUIERDA = %d\n"
        "TECLA_VALOR_ABAJO    = %d\n"
        "; Which tile of its sprite bank it starts at and with which palette.\n"
        "; They are globals and not in the map record because the picture is\n"
        "; **a single one per ROM** and lives in a single map: the two fields\n"
        "; took the last free bytes of MAPA_STRIDE, and growing the record\n"
        "; for that would have been expensive for nothing. That no other map\n"
        "; shows it is enforced by the converter, which stops.\n"
        "IMAGEN_BASE = %d\n"
        "IMAGEN_PAL  = %d\n"
        "IMAGEN_X    = %d\n"
        "IMAGEN_Y    = %d\n"
        "IMAGEN_OBJETOS = %d\n"
        "; How many tiles of the name grid have to be skipped to go from one\n"
        "; object to the next, and from a row of four to the following one.\n"
        "IMAGEN_PASO = %d\n"
        "IMAGEN_FILA = %d\n"
        "; The rain: see OP_WEATHER in eventos.py.\n"
        "LLUVIA_GOTAS_MAX = %d\n"
        "LLUVIA_GOTAS_0 = %d\n"
        "LLUVIA_GOTAS_1 = %d\n"
        "LLUVIA_GOTAS_2 = %d\n"
        "LLUVIA_VIDA   = %d\n"
        "LLUVIA_NACE   = %d\n"
        "LLUVIA_SEMILLA = $%04X\n"
        "CLIMA_LLUVIA  = %d\n"
        "; The inventory: one byte per item of the LDB and RM2k's cap. See\n"
        "; OP_ITEM in eventos.py.\n"
        "ITEMS_N       = %d\n"
        "ITEM_MAX      = %d\n"
        "; The variables: how many slots this ROM carries —at least one,\n"
        "; because a zero length would close the save table—, the ControlVars\n"
        "; operand classes the ROM distinguishes, the sum, and the random\n"
        "; seed. See 'RM2k's variables' in eventos.py.\n"
        "VARIABLES_N   = %d\n"
        "VAR_SUMAR     = %d\n"
        "VAR_VARIABLE  = %d\n"
        "VAR_AZAR      = %d\n"
        "VAR_OTRO      = %d\n"
        "; Class 6, a character's coordinates: the target goes like that of\n"
        "; OP_ROUTE —0 the hero, the event's index plus one— and the other\n"
        "; operand says which coordinate. See VAR_PERSONAJE in eventos.py.\n"
        "VAR_PERSONAJE = %d\n"
        "PERSONAJE_X   = %d\n"
        "PERSONAJE_Y   = %d\n"
        "; The high bits of each OP_CELL_TEST write. See CELDA_Y in\n"
        "; eventos.py.\n"
        "CELDA_Y       = $%04X\n"
        "CELDA_REFRESCO = $%04X\n"
        "AZAR_SEMILLA  = $%04X\n"
        "; And the one for the encounters' randomness, which is a different\n"
        "; one on purpose: walking doesn't advance the map's randomness. See\n"
        "; ENC_SEMILLA in eventos.py.\n"
        "ENC_SEMILLA   = $%04X\n"
        "TIMER_PONER_VAR = %d\n"
        "; The ConditionalBranch condition classes we know, with the RM2k\n"
        "; number as is.\n"
        "COND_ORO    = %d\n"
        "COND_ITEM   = %d\n"
        "COND_ACTOR  = %d\n"
        "; And the two actor questions that carry two operands, with their\n"
        "; own opcode: see OP_IF_ACTOR in eventos.py.\n"
        "COND_ACTOR_HABILIDAD = %d\n"
        "COND_ACTOR_EQUIPO    = %d\n"
        "ORO_MAX     = %d\n"
        "; The two PanScreen operations that compile.\n"
        "PAN_CORRER  = %d\n"
        "PAN_VOLVER  = %d\n"
        "; The three timer operations.\n"
        "TIMER_PONER    = %d\n"
        "TIMER_ARRANCAR = %d\n"
        "; And its five glyphs on screen: where the first goes and how wide\n"
        "; each one is. The colon's is number 10.\n"
        "TIMER_X        = %d\n"
        "TIMER_Y        = %d\n"
        "TIMER_GLIFO_W  = %d\n"
        "TIMER_DOS_PUNTOS = %d\n"
        "; How many frames fit in a second, and the extra ones `SetTimer`\n"
        "; adds so that the first second shows whole.\n"
        "TIMER_CUADROS  = %d\n"
        "TIMER_DE_MAS   = %d\n"
        "; How many flashes can be running at once.\n"
        "FLASH_MAX   = %d\n"
        "; How many events with a parallel page there can be in a map.\n"
        "PARALELO_MAX = %d\n"
        "TRIGGER_AUTOMATICO = %d\n"
        "TRIGGER_ACCION     = %d\n"
        "TRIGGER_TOCA_HEROE = %d\n"
        "TRIGGER_PARALELO   = %d\n"
        "; How many frames a one-cell step lasts. It comes from eventos.py and\n"
        "; not from a computation in the ROM.\n"
        "CUADROS_POR_CELDA = %d\n"
        "; A route's highest frequency, which is where commands 30 and 31\n"
        "; cap. The lowest is capped by the ROM at 1, like RM2k; what\n"
        "; guarantees it isn't reached is the converter, which rejects the\n"
        "; route.\n"
        "RUTA_FRECUENCIA = %d\n"
        "; And how much a `wait` inside a forced route costs. **It isn't one\n"
        "; frame**: in RM2k it is `SetMaxStopCountForWait`, that is\n"
        "; `20 + (1 << (8 - frecuencia))`, and with frequency 8 —the only\n"
        "; one the converter lets through— it is twenty.\n"
        "RUTA_ESPERA = %d\n"
        "; And the jump: how much is left when it starts. How much it drops\n"
        "; per frame depends on the speed —`salto_por_vel`— and not on the\n"
        "; distance.\n"
        "SALTO_PASO = %d\n"
        "TINTE_NEUTRO = %d\n"
        "; The teleport fade: 35 frames out and 35 back, like RM2k, and of\n"
        "; each 35 the ramp is 24. The map is loaded on the first black\n"
        "; frame, which is number %d. These numbers and the table below come\n"
        "; from the fade constants of tools/port/eventos.py.\n"
        "FUNDIDO_CUADROS = %d\n"
        "FUNDIDO_TOTAL   = %d\n"
        "FUNDIDO_RAMPA   = %d\n"
        "FUNDIDO_NEGRO   = %d\n"
        "FUNDIDO_CARGA   = %d\n"
        "BRILLO_MAX      = %d\n"
        "; The teleport transitions the ROM does with the mosaic and with\n"
        "; the cut; any other is the fade. See `ChangeScreenTransitions` in\n"
        "; tools/port/eventos.py.\n"
        "TRANSICION_MOSAICO = %d\n"
        "TRANSICION_CORTE   = %d\n"
        "; The Y'CbCr luminance weights, which are the ones RM2k saturates\n"
        "; with. They add up to exactly 65536, so over five-bit channels they\n"
        "; give a five-bit luminance without rescaling anything.\n"
        "LUZ_R = %d\n"
        "LUZ_G = %d\n"
        "LUZ_B = %d\n"
        "; One bit per switch. The highest the game checks is 1003.\n"
        "SWITCH_BYTES = %d\n"
        "; The party the game starts with, and its cap. In RM2k the hero's\n"
        "; graphic is the first one's, so this decides which sprite is\n"
        "; drawn; `ChangePartyMembers` moves it on the fly.\n"
        "GRUPO_MAX      = %d\n"
        "GRUPO_INICIAL_N = %d\n"
        "ACTOR_BYTES    = %d\n"
        "; How many bytes of that entry are the actor's fifteen colors: the\n"
        "; ROM uploads them to the slot the leaders share. See\n"
        "; `elegir_grafico_heroe`.\n"
        "ACTOR_COLORES  = %d\n"
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
"VENTANA_CGADD  = %d\n"
        "VENTANA_TILES  = %d\n"
        "VENTANA_FILAS_ = %d\n"
        "VENTANA_COLS   = %d\n"
        "; The text area: where it starts in the window's tile bank and\n"
        "; which cells it takes. Its tiles aren't deduplicated —the ROM\n"
        "; rewrites them— and that is where the cap of characters per line\n"
        "; comes from.\n"
        "VENTANA_TEXTO_BASE = %d\n"
        "VENTANA_TEXTO_FILA = %d\n"
        "VENTANA_TEXTO_FILAS = %d\n"
        "VENTANA_TEXTO_COL  = %d\n"
        "VENTANA_TEXTO_COLS = %d\n"
        "MENSAJE_COLS   = %d\n"
        "; The font: 95 ASCII glyphs of six bits by twelve rows, and the\n"
        "; shadow's palette index. That of each row of the glyph is in\n"
        "; fuente_color.\n"
        "FUENTE_ALTO    = %d\n"
        "FUENTE_ANCHO   = %d\n"
        "FUENTE_SOMBRA  = %d\n"
        "FUENTE_PRE_FILAS = %d\n"
        "FUENTE_PRE_CHAR  = %d\n"
        "; The ChipSet animation. Each map has an entry in `anim_tabla` with\n"
        "; its two runs and a block with the drawings; see `anim_tabla` in\n"
        "; snes_convert.py. The cadences and the water cycle come from\n"
        "; `rm2k.py`.\n"
        "ANIM_FAMILIAS  = %d\n"
        "ANIM_STRIDE    = %d\n"
        "ANIM_FAM_STRIDE = %d\n"
        "AGUA_CUADROS   = %d\n"
        "AGUA_DIBUJOS   = %d\n"
        "AGUA_CICLO_N   = %d\n"
        "ANIMADO_CUADROS = %d\n"
        "ANIMADO_PASOS  = %d\n"
        "BYTES_POR_TILE = %d\n"
        "; The title screen. TITULO_TILES at 0 means this ROM doesn't carry\n"
        "; it and the blocks below are one byte of padding; the code in\n"
        # `rom/src/` on purpose: it goes into the `.inc`, which isn't touched
        # yet.
        "; rom/src/ turns itself off with that. It lives alone in VRAM —it\n"
        "; shares with no map, because while it is shown there is no map\n"
        "; loaded— so its addresses are fixed and don't come from the\n"
        "; `vram_layout` layout. The image is uploaded by `pantalla_subir`,\n"
        "; from its row in `pantallas_tabla`: the tiles from $0000 and the\n"
        "; tilemap at PANTALLA_MAPA.\n"
        "TITULO_TILES   = %d\n"
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
        ";   $7C00 .. $8000   the image's, PANTALLA_MAPA of game_over.s\n"
        "TITULO_MENU_CGRAM = %d\n"
        "TITULO_MENU_TILES = %d\n"
        "TITULO_MENU_VRAM  = $5000\n"
        "TITULO_MENU_MAP   = $4400\n"
        "TITULO_MENU_N     = %d\n"
        "; The slots screen, which both ends use: 'Resume the Story' and the\n"
        "; save point. It is a screen of its own —not a layer over the\n"
        "; title— so it is uploaded whole on entering. **It goes in every\n"
        "; ROM**, with a title or without: the save point opens it from\n"
        "; inside the game, and that is why its VRAM addresses are its own\n"
        "; and not the menu's: they fall in the BG1 tile bank of every\n"
        "; layout, which is what `volver_al_mapa` restores with `load_map`.\n"
        "; See RANURA_MAP in the converter.\n"
        "RANURA_VRAM       = $%04X\n"
        "RANURA_MAP        = $%04X\n"
        ";\n"
        "; The cell blocks: the header has two variants —load and save— and\n"
        "; each slot four —empty or full, with cursor or without—. Moving the\n"
        "; cursor is rewriting two rows and not a whole tilemap.\n"
        "SRAM_RANURAS_N    = %d\n"
        "RANURA_TILES      = %d\n"
        "RANURA_CAB_FILA   = %d\n"
        "RANURA_CAB_FILAS  = %d\n"
        "RANURA_CAB_CELDAS = %d\n"
        "RANURA_FILA0      = %d\n"
        "RANURA_SALTO      = %d\n"
        "RANURA_FILAS      = %d\n"
        "RANURA_CELDAS     = %d\n"
        "; And where each row goes in the tilemap, in words. It also comes\n"
        "; from a table: the computation is RANURA_FILA0 + n * RANURA_SALTO,\n"
        "; times 32, and writing it in the 65816 would be the fourth place to\n"
        "; get it wrong.\n"
        "RANURA_CAB_VRAM   = %d\n"
        "; How many blocks there are before the first of the rows: they are\n"
        "; the two headers, load and save.\n"
        "RANURA_BLOQUE_FILAS = 2\n"
        "; The saved game's party, above the row: the faces of up to\n"
        "; RANURA_CARAS_MAX, of RANURA_CARA_COLS by RANURA_CARA_FILAS cells,\n"
        "; and the first one's name and level. Which face block each actor\n"
        "; gets is said by `ranura_cara_bloque`, by actor id up to\n"
        "; RANURA_ACTORES_N, with $FF for 'has none'; and where they go,\n"
        "; `ranura_cara_vram` —four per slot— and `ranura_nombre_vram`.\n"
        ";\n"
        "; The name and the level aren't blocks: they are composed one letter\n"
        "; per cell with `ranura_glifo_celdas`, and each actor's text comes\n"
        "; from its row of `ranura_actor_texto` —the name, the two digits of\n"
        "; the level and max HP, one after the other—. See 'lo que depende\n"
        "; del actor' in titulo.py: it is what keeps the tile bank from\n"
        "; growing with the number of actors.\n"
        "RANURA_CARAS_MAX  = %d\n"
        "RANURA_CARA_COLS  = %d\n"
        "RANURA_CARA_FILAS = %d\n"
        "RANURA_NOMBRE_COLS  = %d\n"
        "; How long an actor's row is in `ranura_actor_texto` and where each\n"
        "; strip starts inside it. The width is a power of two even if bytes\n"
        "; are left over: that way the index comes from shifts and not from a\n"
        "; multiplication.\n"
        "RANURA_TEXTO_ANCHO  = %d\n"
        "RANURA_TEXTO_NOMBRE = 0\n"
        "RANURA_TEXTO_NIVEL  = %d\n"
        "RANURA_TEXTO_MAX    = %d\n"
        "RANURA_NIVEL_CIFRAS = %d\n"
        "; How many cells from the name the first digit of the level falls.\n"
        "RANURA_NIVEL_DESPL  = %d\n"
        "; And where digit 0 starts inside `ranura_glifo_celdas`, which is\n"
        "; indexed by character: it is where the gold and the HP get their\n"
        "; digits from.\n"
        "GLIFO_CIFRA_0     = %d\n"
        "RANURA_ACTORES_N  = %d\n"
        "; How many CGRAM entries the slots screen uploads: palette 0 for\n"
        "; the text and one per face, of sixteen each.\n"
        "RANURA_CGRAM_N    = %d\n"
        "; How many CGRAM entries the title menu uses: one palette of\n"
        "; sixteen, number 0. It is already defined above, with the title\n"
        "; screen; this confirms both computations give the same.\n"
        ".assert TITULO_MENU_CGRAM = %d, error, \"two computations of the menu's CGRAM\"\n\n"
        % (", ".join("%d %s" % (m["id"], m["nombre"]) for m in mapas),
           len(mapas), MAPA_STRIDE, inicial,
           VRAM_ABOVE_MAP, MAP_LAYOUT, NPC_STRIDE, NPC_MAX,
           NPC_QUIETO,
           EV_STRIDE, EV_MAX, RUTA_EV_MAX,
           PAGINA_BYTES, GIRO_NINGUNO, RUTA_GRAF_MAX,
           eventos.CABECERA_LINEAS, eventos.CABECERA_AUTOCIERRE,
           eventos.CUADROS_DE_PAUSA, eventos.VAR_REFRESCO, eventos.VAR_RANURA_MAX,
           eventos.ANIM_ENTRADA, eventos.ANIM_SONIDO, eventos.ANIM_DESTELLO, eventos.TECLA_ESPERA,
           eventos.TECLA_DIRS, eventos.TECLA_DECISION,
           eventos.TECLA_CANCELAR, eventos.TECLA_ARRANCA,
           eventos.TECLA_VALOR_DECISION, eventos.TECLA_VALOR_CANCELAR,
           eventos.TECLA_VALOR_DIR[0], eventos.TECLA_VALOR_DIR[1],
           eventos.TECLA_VALOR_DIR[3], eventos.TECLA_VALOR_DIR[2],
           cartel_base, cartel_pal,
           cartel["x"] if cartel else 0, cartel["y"] if cartel else 0,
           cartel["objetos"] if cartel else 0,
           imagen.OBJ_LADO, 4 * imagen.GRILLA,
           max(eventos.LLUVIA_GOTAS),
           eventos.LLUVIA_GOTAS[0], eventos.LLUVIA_GOTAS[1],
           eventos.LLUVIA_GOTAS[2], eventos.LLUVIA_VIDA,
           eventos.LLUVIA_NACE, eventos.LLUVIA_SEMILLA,
           eventos.CLIMA_LLUVIA,
           eventos.ITEMS_N,
           eventos.ITEM_MAX,
           variables_n(),
           eventos.VAR_SUMAR, eventos.VAR_VARIABLE, eventos.VAR_AZAR,
           eventos.VAR_OTRO,
           eventos.VAR_PERSONAJE, eventos.PERSONAJE_X, eventos.PERSONAJE_Y,
           eventos.CELDA_Y, eventos.CELDA_REFRESCO,
           eventos.AZAR_SEMILLA, eventos.ENC_SEMILLA,
           eventos.TIMER_PONER_VAR,
           eventos.COND_ORO, eventos.COND_ITEM,
           eventos.COND_ACTOR, eventos.COND_ACTOR_HABILIDAD,
           eventos.COND_ACTOR_EQUIPO,
           eventos.ORO_MAX,
           eventos.PAN_CORRER, eventos.PAN_VOLVER,
           eventos.TIMER_PONER, eventos.TIMER_ARRANCAR,
           TIMER_X, TIMER_Y, TIMER_GLIFO_W, TIMER_GLIFOS - 1,
           eventos.CUADROS_POR_SEGUNDO, eventos.TIMER_CUADROS_DE_MAS,
           FLASH_MAX, PARALELO_MAX,
           eventos.TRIGGER_AUTOMATICO, eventos.TRIGGER_ACCION,
           eventos.TRIGGER_TOCA_HEROE, eventos.TRIGGER_PARALELO,
           eventos.CUADROS_POR_CELDA, eventos.RUTA_FRECUENCIA,
           eventos.CUADROS_DE_ESPERA_DE_RUTA,
           eventos.SALTO_PASO,
           color_mod.TINTE_NEUTRO,
           eventos.FUNDIDO_RAMPA,
           eventos.FUNDIDO_CUADROS, eventos.FUNDIDO_TOTAL,
           eventos.FUNDIDO_RAMPA, eventos.FUNDIDO_NEGRO,
           eventos.FUNDIDO_RAMPA, eventos.BRILLO_MAX,
           eventos.TRANSICION_MOSAICO, eventos.TRANSICION_CORTE,
           color_mod.LUZ_R, color_mod.LUZ_G, color_mod.LUZ_B, SWITCH_BYTES,
           eventos.GRUPO_MAX, len(grupo_inicial), ACTOR_BYTES,
           ACTOR_COLORES, OBJ_COLORS,
           rm2k.LAYER_SAME,
           OBJ_PRIORITY_ABOVE if heroe_encima else OBJ_PRIORITY,
           CGRAM_RESERVADAS,
           paleta_de_la_ventana() * COLORS_PER_PALETTE,
           len(ventana["tiles"]) // 32,
           VENTANA_FILAS_INC, VENTANA_COLS_INC,
           ventana["base"],
           VENTANA_TEXTO_FILA, VENTANA_TEXTO_FILAS,
           VENTANA_TEXTO_COL, VENTANA_TEXTO_COLS, _columnas(),
           FUENTE_ALTO, FUENTE_ANCHO,
           ventana["sombra"],
           FUENTE_PRE_FILAS, FUENTE_PRE_CHAR,
           len(FAMILIAS), ANIM_STRIDE, ANIM_FAM_STRIDE,
           rm2k.AGUA_CUADROS_LENTO,
           FAMILIAS[0][1],
           len(rm2k.AGUA_CICLO), rm2k.ANIMADO_CUADROS, rm2k.ANIMADO_PASOS,
           BYTES_PER_TILE,
           0 if titulo is None else titulo["pantalla"]["tiles"],
           constantes.MENU_CGRAM,
           0 if titulo is None else len(titulo["menu_tiles"]),
           0 if titulo is None else len(titulo["menu_tilemaps"]),
           RANURA_VRAM, RANURA_MAP,
           len(ranuras["filas"]),
           len(ranuras["tiles"]),
           menus_mod.CABECERA_Y // constantes.CELL,
           menus_mod.CABECERA_FILAS,
           menus_mod.CABECERA_FILAS * constantes.COLS,
           menus_mod.RANURA_Y // constantes.CELL,
           menus_mod.RANURA_SALTO // constantes.CELL,
           menus_mod.RANURA_FILAS,
           menus_mod.RANURA_FILAS * constantes.COLS,
           menus_mod.CABECERA_Y // constantes.CELL * 32,
           menus_mod.CARAS_MAX, menus_mod.CARA_CELDAS,
           menus_mod.CARA_CELDAS, menus_mod.NOMBRE_COLS,
           RANURA_TEXTO_ANCHO, RANURA_TEXTO_NIVEL, RANURA_TEXTO_MAX,
           menus_mod.NIVEL_CIFRAS,
           ((menus_mod.NIVEL_FILA - menus_mod.NOMBRE_FILA) * 32
            + menus_mod.NIVEL_COL - menus_mod.NOMBRE_COL),
           (ord("0") - menus_mod.ITEM_PRIMER_CARACTER) * 4,
           (max(list(ranuras["caras"]) + list(ranuras["actores"]) + [-1])
            + 1),
           len(ranuras["paletas"]) * constantes.MENU_CGRAM,
           constantes.MENU_CGRAM))

    with open(path, "w") as handle:
        handle.write(cabecera)
        handle.write(identidad_de_la_rom())
        handle.write(desplazamientos())
        handle.write("\n\n")
        # The fade ramp, in bank 0 because `fundido_tick` reads it with
        # `lda fundido_rampa, x`. It comes from `eventos.rampa_de_fundido()`:
        # writing it in tools/runtime/ too would be having two copies that can
        # get out of sync without anything noticing.
        handle.write('.segment "TABLAS"\n'
                     '; The master brightness on each frame of the ramp, from\n'
                     '; black to full. Going down it is read backwards.\n'
                     'fundido_rampa:\n    .byte %s\n\n'
                     % ",".join(str(v) for v in eventos.rampa_de_fundido()))
        # The data goes in RODATA, which the linker spreads over the upper
        # banks. What stays in TABLAS —that is, in bank 0— is what the ROM
        # walks with a bare `lda tabla, x`, which addresses the data bank.
        # `mapa_tabla` is no longer among those: see `tabla_de_mapas`.
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
        indice_global, bancos, indice_por_mapa = {}, [], []
        for mapa in mapas:
            propio = {}
            for par, datos in (mapa["sprite"][8].items()
                               if mapa["sprite"] else ()):
                clave = (par, datos)
                if clave not in indice_global:
                    if any(k[0] == par for k in indice_global):
                        print("  map %d: %s:%d goes with a pose bank of its "
                              "own, quantized differently than in another map"
                              % (mapa["id"], par[0], par[1]))
                    indice_global[clave] = len(bancos)
                    bancos.append(datos)
                propio[par] = indice_global[clave]
            indice_por_mapa.append(propio)
        handle.write("; --- the poses of the characters that change pose, "
                     "for the whole ROM ---\n")
        # **Each pose once**, even if several characters or the same one
        # repeat it: the pose tables carry one pointer per pose —`npc_poses`,
        # `actor_table`—, so two equal ones point to the same block and the
        # ROM uploads the same bytes from another place. It happens a lot: the
        # equal walking frames of the same CharSet, and the characters that
        # repeat across maps with another quantization that didn't change a
        # pose. Each one with its `.bloque`, because it is uploaded by DMA.
        etiqueta_de_pose, poses_de_banco = {}, []
        for datos in bancos:
            suyas = []
            for pose in range(SPRITE_POSES):
                bytes_ = datos[pose * POSE_BYTES:(pose + 1) * POSE_BYTES]
                if bytes_ not in etiqueta_de_pose:
                    etiqueta_de_pose[bytes_] = "pose_%d" % len(etiqueta_de_pose)
                    handle.write(bloque(etiqueta_de_pose[bytes_], bytes_) + "\n")
                suyas.append(etiqueta_de_pose[bytes_])
            poses_de_banco.append(suyas)
        handle.write("\n")
        print("  poses: %d distinct out of %d, %.1f KB less"
              % (len(etiqueta_de_pose), SPRITE_POSES * len(bancos),
                 (SPRITE_POSES * len(bancos) - len(etiqueta_de_pose))
                 * POSE_BYTES / 1024.0))
        indice_por_mapa = [{par: poses_de_banco[g] for par, g in propio.items()}
                           for propio in indice_por_mapa]
        escribir_crudos(os.path.dirname(os.path.abspath(path)), mapas)
        materiales = Materiales(deduplicar=True,
                                comprimidos=comprimidos
                                or comprimir_los_bloques(mapas))
        handle.write("; The LZ2 caps, which descomprimir.s enforces\n"
                     "LZ2_TOPE_FONDO = $%04X\n"
                     "LZ2_TOPE_ENCIMA_Y_SPRITES = $%04X\n"
                     "LZ2_TOPE_ANIM = $%04X\n"
                     "LZ2_TOPE_GRILLA = $%05X\n\n"
                     % (LZ2_TOPE_FONDO, LZ2_TOPE_ENCIMA_Y_SPRITES,
                        LZ2_TOPE_ANIM, LZ2_TOPE_GRILLA))
        etiquetas = []
        for numero, mapa in enumerate(mapas):
            # Stays in Spanish: `mapas_de` in rom/pruebas/arnes/consola.py
            # reads the table order from this line with a regex that expects
            # "mapa".
            handle.write("; --- %d: mapa %d %r ---\n"
                         % (numero, mapa["id"], mapa["nombre"]))
            texto, suyas = datos_del_mapa(mapa, numero,
                                          indice_por_mapa[numero], materiales)
            etiquetas.append(suyas)
            handle.write(texto)
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
            # comes from the split —it starts at `CGRAM_RESERVADAS`— but it is
            # checked anyway: if it stepped on it, the window would come out
            # with the map's colors and no single-map comparison would see it.
            paleta = paleta_de_la_ventana()
            for m in mapas:
                if len(m["cram_words"]) + CGRAM_RESERVADAS > \
                        m["above"][3] * COLORS_PER_PALETTE:
                    raise SystemExit(
                        "the background of map %d uses %d CGRAM entries from "
                        "%d and steps on the upper layer, which starts at %d"
                        % (m["id"], len(m["cram_words"]), CGRAM_RESERVADAS,
                           m["above"][3] * COLORS_PER_PALETTE))
            handle.write("\n; --- the message window ---\n")
            handle.write(bloque("ventana_tiles", ventana["tiles"]) + "\n")
            # Only the `CGRAM_RESERVADAS` at the bottom: from 8 up it belongs
            # to the background, and uploading all sixteen would erase it.
            handle.write(bloque("ventana_cgram",
                                b"".join(w.to_bytes(2, "little")
                                         for w in ventana["cram"]
                                         [:CGRAM_RESERVADAS])) + "\n")
            # One layout for each window base the VRAM layouts use: the tile
            # index goes shifted behind the upper layer, and the upper layer
            # measures 128 or 256 depending on the layout. See
            # `VENTANA_BASES` and `estampar_ventana`.
            for base, etiqueta in zip(VENTANA_BASES, ("ventana_celdas",
                                                      "ventana_celdas_256")):
                plano = bytearray()
                for fila in ventana["celdas"]:
                    for celda in fila:
                        # With the upper layer's priority so that it covers
                        # the hero and the NPCs.
                        plano += (entry(base + celda, False, False,
                                        PRIORITY_ABOVE)
                                  | (paleta << 10)).to_bytes(2, "little")
                handle.write(bloque(etiqueta, bytes(plano)) + "\n")
            # The text area without text: the 240 tiles the ROM copies to the
            # buffer before drawing on top. They go in the order the ROM needs
            # them, that is the cells' order.
            handle.write(bloque("ventana_fondo", ventana["fondo"]) + "\n")
            # The font and the colors. `fuente_color` is the palette index of
            # each of the glyph's twelve rows: RM2k's gradient comes from a
            # 16x16 mask, but each row is a single color, so twelve bytes are
            # enough and the ROM doesn't have to sample anything.
            handle.write(bloque("fuente_tabla", ventana["fuente"]) + "\n")
            pre = fuente_prerender(ventana["fuente"], ventana["color"],
                                   ventana["sombra"])
            for fase, datos in enumerate(pre):
                handle.write(bloque("fuente_pre%d" % fase, datos) + "\n")
            handle.write(bloque("mensajes", ventana["mensajes"]) + "\n")
            # How big it is and how big it can be: the ROM doesn't use them,
            # `just espacio` reads them from the symbol table. The cap is what
            # the operand of `OP_MESSAGE` reaches, 16 bits and in steps of
            # `MENSAJES_PASO` bytes.
            handle.write("MENSAJES_BYTES = %d\nMENSAJES_TOPE = %d\n"
                         % (len(ventana["mensajes"]),
                            0x10000 * eventos.MENSAJES_PASO))
        # --- the ShowPicture picture ---
        #
        # Its fifteen colors as they came out of `imagen.convertir`, in the
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
        colores = ([(0, 0, 0)] + list(cartel["paleta"])) if cartel else [(0, 0, 0)]
        handle.write(bloque("imagen_cgram",
                            b"".join(cgram_word(c).to_bytes(2, "little")
                                     for c in colores)) + "\n")
        # The screen flash products: `d * nivel // 31` for d and level from 0
        # to 31, in the level's row. It is `destellar_canal`'s computation, and
        # the ROM read it from the multiplier and the divider for each of the
        # 96 entries of its tables on every odd frame: see
        # `una_tabla_de_destello`.
        handle.write(bloque("prod31_tabla", bytes(
            d * n // 31 for n in range(32) for d in range(32))) + "\n")
        handle.write(animaciones_asm(animaciones or {}, mapas))
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
        # row of `pantallas_tabla`: see "the full screens", below. What stays
        # here is the menu, which isn't part of the image.
        handle.write("\n; --- the title screen ---\n")
        if titulo is None:
            handle.write(bloque("titulo_menu_tiles", b"\x00") + "\n")
            handle.write(bloque("titulo_menu_celdas", b"\x00") + "\n")
        else:
            # The menu: a 4-bit tile bank and one tilemap per selected option.
            # Moving the cursor is uploading the other tilemap, and that is why
            # they go one after the other and the same size: the ROM indexes
            # them by multiplying.
            menu = bytearray()
            for celda in titulo["menu_tiles"]:
                menu += pack_tile(celda, planes=4)
            handle.write(bloque("titulo_menu_tiles", bytes(menu)) + "\n")
            plano = bytearray()
            for mapa_menu in titulo["menu_tilemaps"]:
                for indice in mapa_menu:
                    plano += entry(indice, False, False,
                                   PRIORITY_ABOVE).to_bytes(2, "little")
            handle.write(bloque("titulo_menu_celdas", bytes(plano)) + "\n")

        # --- the full screens: Game Over and the title ---
        #
        # Each one is an LZ2 stream with the tiles, the tilemap and the
        # colors, and its row in `pantallas_tabla`, which is what
        # `pantalla_subir` reads: see tools/port/pantalla_completa.py. Without
        # a Game Over image, GAME_OVER_TILES at 0 and the ROM goes back to the
        # title without a screen, as until 2026-09-28; without a title screen,
        # TITULO_TILES at 0 and no row. Without either of them PANTALLA_FILA
        # isn't defined, and `pantalla_subir` isn't assembled.
        handle.write("\n; --- the full screens ---\n")
        handle.write("GAME_OVER_TILES = %d\n"
                     % (0 if game_over is None else game_over["tiles"]))
        filas = []
        if game_over is not None:
            filas.append(("GAME_OVER", "game_over_lz2", game_over))
        if titulo is not None:
            filas.append(("TITULO", "titulo_lz2", titulo["pantalla"]))
        if not filas:
            handle.write(bloque("pantallas_tabla", b"\x00") + "\n")
        else:
            handle.write(
                "; Each screen's row in `pantallas_tabla`: where its stream is,\n"
                "; how many bytes of tiles and colors it brings, and from which\n"
                "; CGRAM color they go. See `pantalla_subir`.\n"
                "PANTALLA_FILA = 8\n")
            for numero, (nombre, _, _) in enumerate(filas):
                handle.write("PANTALLA_%s = %d\n" % (nombre, numero))
            handle.write(".bloque %d\npantallas_tabla:\n" % (8 * len(filas)))
            for _, etiqueta, datos in filas:
                handle.write("    .word .loword(%s)\n"
                             "    .byte ^%s\n"
                             "    .word %d, %d\n"
                             "    .byte %d\n"
                             % (etiqueta, etiqueta, datos["tiles"] * 64,
                                datos["colores"] * 2, datos["primer_color"]))
            handle.write("\n")
            for _, etiqueta, datos in filas:
                handle.write(bloque(etiqueta, datos["flujo"]) + "\n")

        # The slots screen, which **goes in every ROM** and not only in the
        # ones that carry a title: the save point opens it from inside the
        # game. Until 2026-09-10 it came out only with the title screen and
        # without it a byte of padding was left with `RANURA_TILES` at zero;
        # and a DMA of "zero bytes" is 65536, so opening it from a ROM without
        # a title filled VRAM with garbage. It is the "black screen with
        # garbage on top" that for a while was noted down as a mystery of the
        # interpreter's context.
        #
        # Its tile bank is its own: it shares the VRAM address with the title
        # menu's, but not the tiles, because both screens are uploaded whole
        # every time one is entered.
        handle.write("\n; --- the slots screen ---\n")
        datos = bytearray()
        for celda in ranuras["tiles"]:
            datos += pack_tile(celda, planes=4)
        handle.write(bloque("ranura_tiles", bytes(datos)) + "\n")

        # The bank of the slots and the menu goes **with the priority bit
        # set**, like the item glyphs: the actor choice turns on BG1 with its
        # windows, and in mode 3 BG1 at priority 0 stays above BG2 at priority
        # 0 —the red bar would cover the row—. In the other screens of this
        # bank BG1 is off and the bit doesn't change a pixel; the experience
        # sprites discard it.
        def celdas_asm(bloques):
            plano = bytearray()
            for celdas in bloques:
                for indice in celdas:
                    plano += entry(indice, False, False,
                                   priority=1).to_bytes(2, "little")
            return bytes(plano)

        # Each cell block goes with its own label and is named by a pointer
        # table, just like the music songs. It is more ROM than computing the
        # offset with shifts —three one-byte tables per block— and in exchange
        # the ROM doesn't have to multiply by 96 or by 192 anywhere. That
        # multiplication would be written here and there, which is exactly
        # the shape of error this repo has already paid for three times.
        #
        # The order: first the two headers —load and save— and then, per slot,
        # the four variants as full * 2 + cursor.
        bloques_ranura = []
        for modo, celdas in enumerate(ranuras["cabeceras"]):
            nombre = "ranura_cab_%d" % modo
            handle.write(bloque(nombre, celdas_asm([celdas])) + "\n")
            bloques_ranura.append(nombre)
        for numero, fila in enumerate(ranuras["filas"]):
            for llena in (0, 1):
                for cursor in (0, 1):
                    nombre = "ranura_%d_%d%d" % (numero, llena, cursor)
                    handle.write(
                        bloque(nombre, celdas_asm([fila[llena][cursor]]))
                        + "\n")
                    bloques_ranura.append(nombre)
        # And behind, per actor that can join the party, its face: the ROM
        # writes it over the row according to what the save stored. The face
        # cells carry the palette in their three bits, which are used here: it
        # is BG2 at 4bpp.
        #
        # Its name and its level are **not** blocks: the ROM composes them with
        # glyphs, see "what depends on the actor" in menus.py. That is what
        # keeps the bank from growing with the number of actors.
        bloque_de_cara = {}
        for actor in sorted(ranuras["caras"]):
            nombre = "ranura_cara_%d" % actor
            handle.write(bloque(nombre, celdas_asm([ranuras["caras"][actor]]))
                         + "\n")
            bloque_de_cara[actor] = len(bloques_ranura)
            bloques_ranura.append(nombre)
        # And the pause menu's, which live in the same tile bank: each command
        # in its two variants —1 is disabled, in the gray palette—, the coin,
        # and the text of a party row, which is a single one for the four and
        # for every actor. The cursor and the glyphs don't go as blocks: they
        # are two cells each and the ROM writes them word by word, see
        # `ranura_glifo_celdas`.
        menu = ranuras["menu"]
        bloque_menu_opcion = len(bloques_ranura)
        for orden, variantes in enumerate(menu["opciones"]):
            for deshabilitada, celdas in enumerate(variantes):
                nombre = "menu_opcion_%d_%d" % (orden, deshabilitada)
                handle.write(bloque(nombre, celdas_asm([celdas])) + "\n")
                bloques_ranura.append(nombre)
        bloque_menu_moneda = len(bloques_ranura)
        handle.write(bloque("menu_moneda", celdas_asm([menu["moneda"]]))
                     + "\n")
        bloques_ranura.append("menu_moneda")
        bloque_menu_fila = len(bloques_ranura)
        handle.write(bloque("menu_fila", celdas_asm([menu["fila"]])) + "\n")
        bloques_ranura.append("menu_fila")
        # And the item screen, which has a bank of its own: the font one
        # letter per cell, its two palettes, and the text of each item the ROM
        # knows —name and two lines of description—, in ASCII.
        datos = bytearray()
        for celda in ranuras["items_tiles"]:
            datos += pack_tile(celda, planes=4)
        handle.write(bloque("items_tiles", bytes(datos)) + "\n")
        def paletas_cgram(paletas):
            return b"".join(
                cgram_word(c).to_bytes(2, "little") for paleta in paletas
                for c in list(paleta) + [(0, 0, 0)] * (constantes.MENU_CGRAM
                                                       - len(paleta)))

        # The first two, which are uploaded with the bank on every screen that
        # uses it; the "goes up" one and the red one go separately and only
        # the equipment screen uploads them, because in battle the entries
        # from the third palette on are the backdrop's —`escena.CGRAM_BASE`—
        # and uploading them there wouldn't help anyone.
        handle.write(bloque("items_cgram", paletas_cgram(
            ranuras["items_paletas"][:menus_mod.ITEM_SUBE])) + "\n")
        handle.write(bloque("item_cgram_sube", paletas_cgram(
            ranuras["items_paletas"][menus_mod.ITEM_SUBE:])) + "\n")
        # The windows of the item and equipment screens, on BG1: see
        # `ITEM_VENTANAS` and `pantallas.EQ_VENTANAS`. The tiles and the
        # colors are the same for both. Each tilemap goes without the bottom
        # rows the screen doesn't show, and each cursor as the two rows of
        # cells it takes, which the ROM copies on top: 128 bytes.
        marco_tiles, marco_colores, ((marco_mapa, marco_barras),
                                     (eq_mapa, eq_barras)) = \
            ranuras["items_marco"]
        handle.write(bloque("items_marco_tiles", b"".join(
            pack_tile(celda, planes=8) for celda in marco_tiles)) + "\n")
        handle.write(bloque("items_marco_mapa", b"".join(
            palabra.to_bytes(2, "little") for palabra in marco_mapa)) + "\n")
        handle.write(bloque("items_marco_barras", b"".join(
            palabra.to_bytes(2, "little") for barra in marco_barras
            for palabra in barra)) + "\n")
        handle.write(bloque("eq_marco_mapa", b"".join(
            palabra.to_bytes(2, "little") for palabra in eq_mapa)) + "\n")
        handle.write(bloque("eq_marco_barras", b"".join(
            palabra.to_bytes(2, "little") for barra in eq_barras
            for palabra in barra)) + "\n")
        handle.write(bloque("items_marco_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little")
            for c in marco_colores)) + "\n")
        # The shop windows, on BG1 with their own base: see
        # `pantallas.TI_VENTANAS` and `tienda_compacta`, which says what is
        # stored. The stretches of each layer are `(VRAM word, source byte in
        # `ti_marco_filas`, bytes)`, terminated by three zeros; the bars,
        # `(VRAM word, source byte in `ti_marco_parches`, bytes per row,
        # rows)`.
        PM = pantallas_mod
        ti_tiles, ti_colores, ti_mapas = ranuras["tienda_marco"]
        ti_filas, ti_arriba, ti_capas, ti_parches, ti_barras = \
            PM.tienda_compacta(ti_mapas)

        def palabras_le(valores):
            return b"".join(v.to_bytes(2, "little") for v in valores)

        handle.write(bloque("ti_marco_tiles", b"".join(
            pack_tile(celda, planes=8) for celda in ti_tiles)) + "\n")
        handle.write(bloque("ti_marco_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little") for c in ti_colores)) + "\n")
        handle.write(bloque("ti_marco_filas", palabras_le(
            p for f in ti_filas for p in f)) + "\n")
        handle.write(bloque("ti_marco_parches", palabras_le(ti_parches))
                     + "\n")
        cols = constantes.COLS
        tramos, capa_tramos = [], []
        for capa in ti_capas:
            capa_tramos.append(2 * len(tramos))
            for fila, origen, cuantas in capa:
                tramos += [PM.TI_MAPA + fila * cols, origen * 2 * cols,
                           cuantas * 2 * cols]
            tramos += [0, 0, 0]
        handle.write(bloque("ti_tramos", palabras_le(tramos)) + "\n")
        handle.write(bloque("ti_capa_tramos", palabras_le(capa_tramos))
                     + "\n")
        handle.write(bloque("ti_barras", palabras_le(
            v for capa in ti_barras for fila, col, filas, ancho, origen in capa
            for v in (PM.TI_MAPA + fila * cols + col, 2 * origen, 2 * ancho,
                      filas))) + "\n")
        base_barras = [0]
        for capa in ti_barras:
            base_barras.append(base_barras[-1] + len(capa))
        handle.write(bloque("ti_barra_base", bytes(base_barras[:-1])) + "\n")
        handle.write(bloque("ti_capa_de_modo", bytes(PM.TI_CAPA_DE_MODO))
                     + "\n")
        handle.write(
            "TI_MARCO_VRAM     = $%04X\n"
            "TI_MARCO_MAPA     = $%04X\n"
            "TI_MARCO_TILES    = %d\n"
            "TI_MARCO_COLORES  = %d\n"
            "TI_MARCO_ARRIBA   = %d\n"
            % (PM.TI_VRAM, PM.TI_MAPA, len(ti_tiles), len(ti_colores),
               ti_arriba))
        # The End Game screen, whole: see tools/port/fin_del_juego.py. The two
        # palettes go one after the other, the "Yes" one first: the ROM picks
        # one by multiplying.
        fin_tiles, fin_filas, fin_fila0, fin_paletas = ranuras["fin"]
        handle.write(bloque("fin_tiles", b"".join(
            pack_tile(celda, planes=4) for celda in fin_tiles)) + "\n")
        handle.write(bloque("fin_mapa", b"".join(
            palabra.to_bytes(2, "little") for palabra in fin_filas)) + "\n")
        handle.write(bloque("fin_cgram", paletas_cgram(fin_paletas)) + "\n")
        handle.write(bloque("fin_rampa", bytes(fin_mod.rampa())) + "\n")
        handle.write(
            "FIN_TILES   = %d\n"
            "FIN_FILA0   = %d\n"
            "FIN_FILAS   = %d\n"
            "FIN_ENTRA   = %d\n"
            "FIN_NO      = %d\n"
            "FIN_CUADROS = %d\n"
            "FIN_PASO_TEMA = %d\n"
            % (len(fin_tiles), fin_fila0, len(fin_filas) // constantes.COLS,
               fin_mod.ENTRA, fin_mod.NO, fin_mod.CUADROS_FUNDIDO,
               eventos.paso_de_fundido(fin_mod.MS_FUNDIDO_TEMA)))
        item_textos, item_textos_ofs = bytearray(), []

        def texto_nuevo(texto):
            texto = menus_mod.texto_de_item(texto, 255)
            item_textos_ofs.append((len(item_textos), len(texto)))
            item_textos.extend(texto.encode("ascii"))
            return len(item_textos_ofs) - 1

        for numero in ranuras["items"]:
            item = ranuras["items_db"][numero]
            for texto in ([menus_mod.texto_de_item(
                    item.name, menus_mod.ITEM_NOMBRE_ANCHO)]
                    + menus_mod.partir_descripcion(item.description)):
                texto_nuevo(texto)
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
        # lines, see `texto_escribir`—, so a dead text before the first one
        # shifts every item and the ROM ends up drawing the dead ones, which
        # measure zero: the battle's "Use Item" list came out with the cursor
        # and the quantities and without a single name. With the padding here
        # the flag goes back to doing what it promises, which is not changing
        # a pixel.
        for _ in range(ranuras.get("relleno_textos") or 0):
            item_textos_ofs.append((0, 0))
        # And the fixed ones, behind: the parameters and the equipment slots,
        # and the name of each actor that can join the party. See pantallas.py.
        P = pantallas_mod
        B = batalla_mod
        db = ranuras["db"]
        texto_param = [texto_nuevo(t[:P.EQ_PARAM_VALOR - 1])
                       for t in db.term_params]
        texto_ranura = [texto_nuevo(t[:P.EQ_RANURA_TERM_ANCHO])
                        for t in db.term_equipment]
        texto_actor = {a: texto_nuevo(db.actors[a].name)
                       for a in ranuras["actores"]}
        # The shop's: the eleven messages of each of the three sets, two lines
        # each —`partir_descripcion`, as in pantallas.py—, and "Owned Items",
        # "Equipped Items" and the currency.
        texto_tienda = None
        for juego in range(3):
            term = P.terminos_tienda(db, juego)
            for nombre, _termino in P.TI_TERMINOS:
                renglones = menus_mod.partir_descripcion(term[nombre])
                # Outside the main one, the message goes in a one-line window:
                # `ti_mensaje` writes only the first.
                if renglones[1] and nombre not in ("saludo", "resaludo"):
                    raise SystemExit(
                        "the shop message %r, of set %d, takes two "
                        "lines and its window has one"
                        % (term[nombre], juego))
                for renglon in renglones:
                    t = texto_nuevo(renglon)
                    if texto_tienda is None:
                        texto_tienda = t
        texto_tengo = texto_nuevo(P.lcf_termino(db, P.TI_TERMINO_TENGO))
        texto_llevo = texto_nuevo(P.lcf_termino(db, P.TI_TERMINO_LLEVO))
        texto_moneda = texto_nuevo(db.term_gold)
        # And the battle's: the fifteen LDB terms the screen uses —in the order
        # of `reglas.BA_TERMINOS`, which is the one the ROM indexes— and the
        # name of each enemy some troop of the cartridge brings. The three
        # commands go **already trimmed**, by `pantallas.texto_de_orden`: the
        # LDB brings them with leading spaces and that would shift the text of
        # their column.
        term_batalla = reglas.terminos_batalla(db)
        texto_batalla = None
        victoria = P.renglones_de_la_victoria(term_batalla["victoria"])
        if len(victoria) > P.BA_VIC_TERMINO_MAX:
            raise SystemExit("the victory term takes %d lines and "
                             "the window leaves it %d: %r"
                             % (len(victoria), P.BA_VIC_TERMINO_MAX, victoria))
        for nombre, _termino in reglas.BA_TERMINOS:
            texto = term_batalla[nombre]
            if nombre in ("atacar", "defender", "huir"):
                texto = P.texto_de_orden(texto)
            if nombre == "victoria":
                texto = victoria[0]
            t = texto_nuevo(texto)
            if texto_batalla is None:
                texto_batalla = t
        # And the line for a fallen one an item revived: the dead state's
        # `message_recovery`, which goes stuck to the name —"Core has
        # revived!"—. It isn't a term but a piece of the state's data, so it
        # goes separately and with its own index. See `ba_mensaje`.
        texto_revivio = texto_nuevo(P.texto_revivio(db))
        # The second line of the victory, empty if it fits in one: it goes
        # separately so as not to shift the indices of `BA_TERMINOS`.
        texto_victoria2 = texto_nuevo((victoria + [""])[1])
        enemigos_rom = sorted({e for numero in tropas
                               if numero in db.troops
                               for e in db.troops[numero].members})
        texto_enemigo = {e: texto_nuevo(menus_mod.texto_de_item(
            db.enemies[e].name, P.BA_NOMBRE_ANCHO)) for e in enemigos_rom}
        # And the skills': the ones some actor that can join the party knows,
        # **at their LDB level** —see `batalla.habilidades_de`—, sorted by
        # number, which is the order the menu puts them in. With the intro's
        # party they are seven: 129, 130, 131, 143, 144, 146 and 150.
        #
        # **All the ones they can end up knowing**, and not only the LDB's: a
        # `ChangeSkills` teaches the actor what the learning table doesn't
        # have, and since 2026-09-21 that shows in battle. They are those of
        # their pairs in `eventos.HABILIDAD_RANURA` that the battle knows how
        # to offer.
        #
        # And the ones some enemy of the cartridge's troops uses, since
        # 2026-09-27: `ShortCircuit`, from the ones at the recycling plant. See
        # `batalla.acciones_de_enemigo`.
        acciones_rom = {e: B.acciones_de_enemigo(db, e) for e in enemigos_rom}
        habilidades_rom = sorted(
            {h for (a, h) in eventos.HABILIDAD_RANURA
             if a in ranuras["actores"] and B.habilidad_usable(db.skills[h])}
            | {skill.id for lista in acciones_rom.values()
               for _r, skill, _ef in lista if skill is not None})
        texto_hab = {h: texto_nuevo(menus_mod.texto_de_item(
            db.skills[h].name, P.BA_HAB_NOMBRE_ANCHO))
            for h in habilidades_rom}
        texto_hab_desc = {h: texto_nuevo(menus_mod.texto_de_item(
            db.skills[h].description, P.BA_HAB_DESC_ANCHO))
            for h in habilidades_rom}
        # And the **whole** name of the ones learned on leveling up, which is
        # what "<skill> acquired!" says at the victory: the list's is cut to
        # its column, and some of these the battle doesn't know how to offer
        # —Lurk In Shadows, Arden's— and aren't in the list. See
        # `hab_par_aprende_txt`.
        ensenadas = {h for (a, h) in eventos.HABILIDAD_RANURA
                     if a in ranuras["actores"] and a in db.actors
                     and B.nivel_en_que_aprende(db, a, h)
                     > X.nivel_inicial(db.actors[a])}
        texto_hab_entero = {
            h: texto_nuevo(menus_mod.texto_de_item(db.skills[h].name, 255))
            for h in sorted(ensenadas)}
        # The two lines RM2k says when using it: `using_message1` goes after
        # the name of the one using it and `using_message2` alone, on the line
        # below. `GetSkillFirstStartMessage2k` and its sibling.
        texto_hab_msg1 = {h: texto_nuevo(db.skills[h].using_message1)
                          for h in habilidades_rom}
        texto_hab_msg2 = {h: texto_nuevo(db.skills[h].using_message2)
                          for h in habilidades_rom}
        # And what each actor's command is called: `Game_Actor::GetSkillName`,
        # that is its `skill_name` —"AgentTrain", "Telepathy", "Slicing"— and
        # not the LDB's `command_skill`. It goes trimmed like the other four
        # commands.
        texto_hab_orden = {a: texto_nuevo(P.texto_de_orden(
            B.nombre_de_orden_habilidad(db, a))) for a in ranuras["actores"]}
        handle.write(bloque("item_textos", bytes(item_textos) or b"\x00")
                     + "\n")
        if len(bloques_ranura) > 255:
            raise SystemExit("the slots screen has %d blocks and the "
                             "tables that name them are one byte"
                             % len(bloques_ranura))
        # The tables that name them **don't go here**: the ROM reads them with
        # `lda ranura_bloque_lo, x`, which addresses the data bank, so they
        # have to live in bank 0 together with the code. They are emitted
        # further down, in the TABLAS segment.
        #
        # The palette goes padded up to the TITULO_MENU_CGRAM entries, which
        # is what the ROM uploads at once: if the text uses fewer colors, the
        # DMA would read whatever follows in the cartridge.
        colores = []
        for paleta in ranuras["paletas"]:
            paleta = list(paleta)
            colores += paleta + [(0, 0, 0)] * (constantes.MENU_CGRAM
                                               - len(paleta))
        handle.write(bloque("ranura_cgram",
                            b"".join(cgram_word(c).to_bytes(2, "little")
                                     for c in colores)) + "\n")

        handle.write('\n.segment "TABLAS"\n')
        # The cell blocks of the slots screen are named by pointers, and the
        # three tables go in bank 0 because the ROM reads them with
        # `lda ranura_bloque_lo, x`. The same for `ranura_vram`, which says
        # which tilemap address each row goes to: the computation comes from
        # the same geometry that drew the text and that is why it lives in a
        # single place.
        for campo, prefijo in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write("ranura_bloque_%s:\n    .byte %s\n"
                         % (campo, ", ".join(prefijo + e
                                             for e in bloques_ranura)))
        fila_de = [RANURA_MAP + (menus_mod.RANURA_Y
                                 + n * menus_mod.RANURA_SALTO)
                   // constantes.CELL * 32 for n in range(RANURAS)]
        handle.write("ranura_vram:\n    .word %s\n" % ", ".join(
            str(v) for v in fila_de))
        # Where the faces go —four entries per slot, so that the index is the
        # slot times four plus the place, without multiplying by three— and
        # the leader's name.
        handle.write("ranura_cara_vram:\n    .word %s\n" % ", ".join(
            str(fila_de[n] + menus_mod.CARA_COL
                + lugar * menus_mod.CARA_PASO if lugar < menus_mod.CARAS_MAX
                else 0)
            for n in range(RANURAS) for lugar in range(4)))
        handle.write("ranura_nombre_vram:\n    .word %s\n" % ", ".join(
            str(fila_de[n] + menus_mod.NOMBRE_FILA * 32
                + menus_mod.NOMBRE_COL) for n in range(RANURAS)))
        actores_n = max(list(bloque_de_cara) + list(ranuras["actores"])
                        + [-1]) + 1
        handle.write("ranura_cara_bloque:\n    .byte %s\n" % (", ".join(
            str(bloque_de_cara.get(actor, 0xFF))
            for actor in range(actores_n)) or "$FF"))
        # The pause menu: its blocks, and where each thing goes in the
        # tilemap, in words. The geometry is `menus.py`'s and comes from
        # there.
        T = menus_mod
        from port import fuente as fuente_mod

        def celda_vram(fila, col):
            return RANURA_MAP + fila * 32 + col

        filas_opcion = [(T.MENU_OPC_Y + n * T.MENU_OPC_SALTO)
                        // constantes.CELL for n in range(T.MENU_OPCIONES)]
        handle.write(
            "MENU_OPCIONES     = %d\n"
            "MENU_GUARDAR      = %d\n"
            "MENU_FIN          = %d\n"
            "MENU_BLQ_OPCION   = %d\n"
            "MENU_BLQ_MONEDA   = %d\n"
            "MENU_BLQ_FILA     = %d\n"
            "MENU_OPC_COLS     = %d\n"
            "MENU_MONEDA_COLS  = %d\n"
            "MENU_MONEDA_VRAM  = %d\n"
            "MENU_ACTOR_COLS   = %d\n"
            "MENU_ACTOR_FILAS  = %d\n"
            "MENU_FILAS_GRUPO  = %d\n"
            "MENU_ACTORES_N    = %d\n"
            "MENU_HP_CIFRAS    = %d\n"
            "MENU_HP_DESPL     = %d\n"
            "MENU_CARA_CELDAS  = %d\n"
            "MENU_NOMBRE_COLS  = %d\n"
            "MENU_NOMBRE_DESPL = %d\n"
            "MENU_NIVEL_DESPL  = %d\n"
            "MENU_MAX_CIFRAS   = %d\n"
            "MENU_MAX_DESPL    = %d\n"
            % (T.MENU_OPCIONES, T.MENU_GUARDAR, T.MENU_FIN, bloque_menu_opcion,
               bloque_menu_moneda, bloque_menu_fila,
               T.MENU_OPC_COLS, T.MENU_MONEDA_COLS,
               celda_vram(T.MENU_ORO_Y // constantes.CELL, T.MENU_MONEDA_COL),
               T.MENU_ACTOR_COLS, T.MENU_ACTOR_FILAS, T.MENU_FILAS_GRUPO,
               actores_n,
               # And how many cells from the first of the actor's block the
               # hundreds of its HP fall, which is what `menu_hp_escribir`
               # adds to `menu_fila_vram`.
               T.MENU_HP_CIFRAS,
               T.MENU_HP_FILA * 32 + T.MENU_HP_COL - T.MENU_ACTOR_COL,
               # The face goes in the top-left corner of the row —that is why
               # it carries no offset— and the three strips the ROM composes,
               # each in its own.
               T.CARA_CELDAS, T.MENU_NOMBRE_COLS,
               T.MENU_NOMBRE_FILA * 32 + T.MENU_NOMBRE_COL - T.MENU_ACTOR_COL,
               T.MENU_NIVEL_FILA * 32 + T.MENU_NIVEL_COL - T.MENU_ACTOR_COL,
               T.MENU_MAX_CIFRAS,
               T.MENU_HP_FILA * 32 + T.MENU_MAX_COL - T.MENU_ACTOR_COL))
        # Which commands do something: 1 yes, 0 no. The save one also checks
        # the permission, in the ROM.
        handle.write("menu_hecha:\n    .byte %s\n" % ", ".join(
            "1" if n in T.MENU_HECHAS else "0"
            for n in range(T.MENU_OPCIONES)))
        handle.write("menu_opcion_vram:\n    .word %s\n" % ", ".join(
            str(celda_vram(f, T.MENU_OPC_COL)) for f in filas_opcion))
        handle.write("menu_cursor_vram:\n    .word %s\n" % ", ".join(
            str(celda_vram(f, T.MENU_CURSOR_COL)) for f in filas_opcion))
        handle.write("menu_fila_vram:\n    .word %s\n" % ", ".join(
            str(celda_vram(r * T.MENU_ACTOR_FILAS, T.MENU_ACTOR_COL))
            for r in range(T.MENU_FILAS_GRUPO)))
        # The cursor's two cells, top and bottom: the ROM writes them one word
        # at a time.
        handle.write("menu_cursor_celdas:\n    .word %s\n" % ", ".join(
            "$%04X" % entry(c, False, False, priority=1)
            for c in menu["cursor"]))
        # And what the screen composes on the fly, which goes **outside bank
        # 0**: it is read with `lda f:`, and it is almost a thousand bytes the
        # code's bank would miss. The glyphs are indexed by character —from
        # ITEM_PRIMER_CARACTER, like those of the item screen— and the letters
        # this cartridge doesn't use stay in the empty cell: nobody asks for
        # them, and a complete table is indexed without subtracting anything
        # else.
        handle.write('.segment "RODATA"\n')
        vacio = "$%04X, $%04X" % (entry(0, False, False),
                                  entry(0, False, False))
        handle.write(".bloque %d\nranura_glifo_celdas:\n    .word %s\n"
                     % (menus_mod.ITEM_CARACTERES * 4, ", ".join(
                         ", ".join("$%04X" % entry(c, False, False,
                                                   priority=1)
                                   for c in menu["glifos"][letra])
                         if letra in menu["glifos"] else vacio
                         for letra in map(
                             chr, range(menus_mod.ITEM_PRIMER_CARACTER,
                                        menus_mod.ITEM_PRIMER_CARACTER
                                        + menus_mod.ITEM_CARACTERES)))))
        # The experience line, which the ROM draws with sprites: see
        # `MENU_EXP_X` in menus.py. The term is four tiles —two wide, top and
        # bottom— and the digits come from `ranura_glifo_celdas`.
        handle.write(".bloque %d\nmenu_exp_termino:\n    .word %s\n" % (
            2 * len(menu["exp_termino"]), ", ".join(
                "$%04X" % entry(c, False, False)
                for c in menu["exp_termino"])))
        # The actor choice: its windows on BG1 —see `OBJETIVO_VENTANAS` in
        # menus.py—. A single tilemap, the one with an item, and the bar only
        # in the rectangle that changes: see `menus.objetivo_compacto`. And
        # the name of each medicine on two lines, in ASCII, with a table of
        # one byte per `k` that says which one it is —$FF if it isn't a
        # medicine—: only medicines open this screen.
        obj_tiles, obj_colores, obj_mapas = ranuras["objetivo"]
        (obj_mapa, obj_barras, obj_fila0, obj_filas, obj_col0, obj_cols,
         obj_borrar_filas, obj_borrar_cols) = T.objetivo_compacto(obj_mapas)
        handle.write(bloque("objetivo_tiles", b"".join(
            pack_tile(celda, planes=8) for celda in obj_tiles)) + "\n")
        handle.write(bloque("objetivo_mapa", b"".join(
            palabra.to_bytes(2, "little") for palabra in obj_mapa)) + "\n")
        handle.write(bloque("objetivo_barras", b"".join(
            palabra.to_bytes(2, "little") for barra in obj_barras
            for palabra in barra)) + "\n")
        handle.write(bloque("objetivo_cgram", b"".join(
            cgram_word(c).to_bytes(2, "little") for c in obj_colores)) + "\n")
        medicinas = [n for n in ranuras["items"]
                     if ranuras["items_db"][n].type == lcf.ITEM_TYPE_MEDICINE]
        if len(medicinas) > 255:
            raise SystemExit("%d medicines don't fit in `objetivo_nombre_de`"
                             % len(medicinas))
        handle.write(bloque("objetivo_nombre_de", bytes(
            medicinas.index(n) if n in medicinas else 0xFF
            for n in ranuras["items"])) + "\n")
        handle.write(bloque("objetivo_nombres", b"".join(
            "".join(T.nombre_en_renglones(ranuras["items_db"][n].name))
            .encode("ascii", "replace") for n in medicinas)) + "\n")
        handle.write(
            "OBJETIVO_VRAM     = $%04X\n"
            "OBJETIVO_MAPA     = $%04X\n"
            "OBJETIVO_TILES    = %d\n"
            "OBJETIVO_CGRAM    = %d\n"
            "OBJETIVO_COLORES  = %d\n"
            "OBJETIVO_NOMBRE_ANCHO = %d\n"
            "OBJETIVO_NOMBRE_VRAM = %d\n"
            "OBJETIVO_CUANTOS_VRAM = %d\n"
            "OBJETIVO_BARRA_FILA0 = %d\n"
            "OBJETIVO_BARRA_FILAS = %d\n"
            "OBJETIVO_BARRA_COL0 = %d\n"
            "OBJETIVO_BARRA_COLS = %d\n"
            "OBJETIVO_BORRAR_FILAS = %d\n"
            "OBJETIVO_BORRAR_COLS = %d\n"
            % (T.OBJETIVO_VRAM, T.OBJETIVO_MAPA, len(obj_tiles),
               T.OBJETIVO_CGRAM, len(obj_colores), T.OBJETIVO_NOMBRE_ANCHO,
               celda_vram(T.OBJETIVO_NOMBRE_FILA, T.OBJETIVO_NOMBRE_COL),
               celda_vram(T.OBJETIVO_CUANTOS_FILA, T.OBJETIVO_CUANTOS_COL),
               obj_fila0, obj_filas, obj_col0, obj_cols, obj_borrar_filas,
               obj_borrar_cols))
        handle.write(
            "MENU_EXP_X        = %d\n"
            "MENU_EXP_NUM_X    = %d\n"
            "MENU_EXP_Y        = %d\n"
            "MENU_EXP_PASO     = %d\n"
            "MENU_EXP_CIFRAS   = %d\n"
            "MENU_EXP_LETRAS   = %d\n"
            "MENU_ACTOR_ALTO   = %d\n"
            % (T.MENU_EXP_X,
               T.MENU_EXP_X + T.MENU_EXP_NUM_DX - T.GLIFO_DX,
               T.MENU_EXP_Y - T.GLIFO_DY, fuente_mod.ANCHO, T.MENU_EXP_CIFRAS,
               T.MENU_EXP_LETRAS, T.MENU_ACTOR_FILAS * constantes.CELL))
        # Each actor's text, in ASCII: the name —with trailing spaces, which
        # are what erase whatever was there—, the two digits of the level and
        # max HP after its bar. **The three together, in one row per actor**,
        # so the ROM has a single address to compute and three offsets that
        # are constants.
        db_ranuras = ranuras["db"]
        if (RANURA_TEXTO_NIVEL < menus_mod.MENU_NOMBRE_COLS
                or RANURA_TEXTO_MAX + menus_mod.MENU_MAX_CIFRAS
                > RANURA_TEXTO_ANCHO):
            raise SystemExit("the actor's three strips don't fit in the %d "
                             "bytes of its row" % RANURA_TEXTO_ANCHO)
        tira = bytearray()
        for a in range(actores_n):
            fila = (menus_mod.texto_de_nombre(db_ranuras, a)
                    .ljust(RANURA_TEXTO_NIVEL)
                    + menus_mod.texto_de_nivel(db_ranuras, a)
                    + menus_mod.texto_de_maximo(db_ranuras, a))
            tira += fila.ljust(RANURA_TEXTO_ANCHO).encode("ascii")
        handle.write(".bloque %d\nranura_actor_texto:\n    .byte %s\n"
                     % (max(1, len(tira)),
                        ", ".join(str(b) for b in tira) or "0"))
        handle.write('.segment "TABLAS"\n')
        # The item screen. `item_k` goes from the RM2k number to its place in
        # the ROM's tables, $FF if this ROM doesn't know it; the rest is per
        # place. `item_uso`: bit 0 if it goes in white and A does something,
        # bit 1 if using it spends one —the switch ones with uses—, bit 2 if it
        # opens the actor choice —the medicines—, bit 3 if it is a two-handed
        # weapon. The texts go three per item —the name and the two lines of
        # the description—: text `t` is `3k + field`.
        items = ranuras["items"]
        db_items = ranuras["items_db"]
        if len(items) > 255:
            raise SystemExit("%d items don't fit in one-byte tables"
                             % len(items))
        k_de = {numero: k for k, numero in enumerate(items)}
        handle.write(
            "ITEMS_ROM         = %d\n"
            "ITEMS_TILES       = %d\n"
            "ITEMS_CGRAM_N     = %d\n"
            "ITEM_FILAS        = %d\n"
            "ITEM_CURSOR_COL   = %d\n"
            "ITEM_NOMBRE_COL   = %d\n"
            "ITEM_DOS_PUNTOS_COL = %d\n"
            "ITEM_CIFRAS_COL   = %d\n"
            "ITEM_DESC_VRAM    = %d\n"
            "ITEM_DESC_COL     = %d\n"
            "ITEM_PRIMER_CARACTER = %d\n"
            "ITEM_GLIFOS_GRIS  = %d\n"
            "ITEM_MARCO_VRAM   = $%04X\n"
            "ITEM_MARCO_TILES  = %d\n"
            "ITEM_MARCO_MAPA   = $%04X\n"
            "ITEM_MARCO_CGRAM  = %d\n"
            "ITEM_MARCO_COLORES = %d\n"
            "ITEM_MARCO_FILAS  = %d\n"
            "ITEM_MARCO_LISTA  = %d\n"
            % (len(items), len(ranuras["items_tiles"]),
               menus_mod.ITEM_SUBE * constantes.MENU_CGRAM,
               T.ITEM_FILAS, T.ITEM_CURSOR_COL, T.ITEM_NOMBRE_COL,
               T.ITEM_DOS_PUNTOS_COL, T.ITEM_CIFRAS_COL,
               celda_vram(T.ITEM_DESC_Y // constantes.CELL, T.ITEM_DESC_COL),
               T.ITEM_DESC_COL,
               T.ITEM_PRIMER_CARACTER, T.ITEM_CARACTERES * 4,
               RANURA_VRAM
               + items_marco_primero(len(ranuras["items_tiles"])) * 32,
               len(marco_tiles), T.ITEM_MARCO_MAPA, T.ITEM_MARCO_CGRAM,
               len(marco_colores), constantes.FILAS,
               T.ITEM_LISTA_Y // constantes.CELL))

        def bytes_asm(etiqueta, valores, formato="%d", declarar=False):
            if declarar:
                handle.write(".bloque %d\n" % max(1, len(valores)))
            handle.write("%s:\n    .byte %s\n" % (etiqueta, ", ".join(
                formato % v for v in valores) or "$FF"))

        def words_asm(etiqueta, valores, formato="%d", declarar=False):
            if declarar:
                handle.write(".bloque %d\n" % max(2, 2 * len(valores)))
            handle.write("%s:\n    .word %s\n" % (etiqueta, ", ".join(
                formato % v for v in valores) or "0"))

        # `item_k` goes outside bank 0 —it is read with `lda f:item_k, x`—:
        # the code's bank filled up with the audio package.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_k", [k_de.get(n, 0xFF)
                             for n in range(eventos.ITEMS_N)],
                  declarar=True)
        handle.write('.segment "TABLAS"\n')
        words_asm("item_id", items)
        bytes_asm("item_uso", [
            (1 if T.item_usable(db_items[n]) else 0)
            | (2 if T.item_usable(db_items[n])
               and not T.item_pide_actor(db_items[n])
               and db_items[n].uses else 0)
            | (4 if T.item_pide_actor(db_items[n]) else 0)
            | (8 if db_items[n].two_handed else 0)
            for n in items])
        # `item_switch` goes outside bank 0 —it is read with
        # `lda f:item_switch, x`, only once per item used— because the random
        # encounters pushed it over by 34 bytes on 2026-09-13. It is 124: the
        # largest of the tables that are read with X and aren't in any
        # per-frame loop.
        handle.write('.segment "RODATA"\n')
        words_asm("item_switch", [db_items[n].switch_id for n in items],
                  declarar=True)
        handle.write('.segment "TABLAS"\n')
        # What each item does in a battle: whether it goes in the list that is
        # offered and how much it heals. The rule for which ones go in is
        # `batalla.item_usable_en_batalla`, that is `Game_Party::IsItemUsable`
        # with the battle open plus what this port knows how to do; the
        # computation of how much it heals is
        # `Game_BattleAlgorithm::Item::vExecute`.
        # **Outside bank 0**, like `item_k` and for the same reason: with the
        # maps of `abl` the code area ended up at 32775 of 32704 when putting
        # them here. The battle reads them with `lda f:item_batalla, x`.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_batalla", [
            1 if B.item_usable_en_batalla(db_items[n]) else 0 for n in items],
            declarar=True)
        bytes_asm("item_cura_rate", [db_items[n].recover_hp_rate
                                     for n in items], declarar=True)
        words_asm("item_cura_hp", [min(db_items[n].recover_hp, 0xFFFF)
                                   for n in items], declarar=True)
        # And what a medicine does outside battle, which is the whole of
        # `Game_Battler::UseItem`: the SP, like the HP, and `item_medicina`
        # with three bits —1 if it is `ko_only`, 2 if it removes the dead
        # state, which is the first of `state_set` and what revives a fallen
        # one, 4 if using it spends one, which is `uses` nonzero—. The other
        # states of `state_set` don't go: outside battle this port has no
        # states, so removing them is never useful. See `medicina_usar`.
        bytes_asm("item_cura_sp_rate", [db_items[n].recover_sp_rate
                                        for n in items], declarar=True)
        words_asm("item_cura_sp", [min(db_items[n].recover_sp, 0xFFFF)
                                   for n in items], declarar=True)
        bytes_asm("item_medicina", [
            (1 if db_items[n].ko_only else 0)
            | (2 if db_items[n].state_set[:1] == [True] else 0)
            | (4 if db_items[n].uses else 0)
            for n in items], declarar=True)
        handle.write('.segment "TABLAS"\n')
        # The four text ones go **outside bank 0**, like `item_k` and for the
        # same reason: they don't fit there. With the ten maps of `abl` the
        # code area was at 32622 of 32704 —eighty-two free bytes— and the
        # `ShowPicture` picture didn't fit. They are read with
        # `lda f:item_txt_lo, x`, which costs one byte and one cycle per read
        # in thirteen places, none inside a per-frame loop.
        handle.write('.segment "RODATA"\n')
        for campo, prefijo in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write(".bloque %d\n" % max(1, len(item_textos_ofs)))
            handle.write("item_txt_%s:\n    .byte %s\n" % (campo, ", ".join(
                "%s(item_textos + %d)" % (prefijo, ofs)
                for ofs, _ in item_textos_ofs) or "0"))
        bytes_asm("item_txt_n", [n for _, n in item_textos_ofs],
                  declarar=True)
        handle.write('.segment "TABLAS"\n')
        words_asm("item_fila_vram", [
            celda_vram(T.ITEM_LISTA_Y // constantes.CELL + 2 * f, 0)
            for f in range(T.ITEM_FILAS)])
        # The two cells of each character, top and bottom: first the 95 in
        # white, then in gray and then in the "goes up" color. Character `c`
        # in variant `g` is at
        # `g * ITEM_GLIFOS_GRIS + (c - ITEM_PRIMER_CARACTER) * 4`.
        # --- the equipment ---
        # Per known item: its type, what it adds —attack, defense, spirit,
        # agility, signed— and who can equip it, one bit per actor. Per actor,
        # from 0 to the LDB's last: its level parameters and its initial
        # equipment, which the ROM copies to `FAR_EQUIPO` on reset. And where
        # each thing goes in the screen's buffer, in bytes: row * 64 + col * 2.
        actores_n = max(db.actors) + 1

        def pos(fila, col):
            return fila * 64 + col * 2

        bytes_asm("item_tipo", [db_items[n].type for n in items])
        handle.write('.segment "RODATA"\n')     # same: see `item_txt_lo`
        words_asm("item_puntos", [p & 0xFFFF for n in items
                                  for p in db_items[n].points],
                  declarar=True)
        # And what attacking with each one costs: the weapons' `sp_cost`, zero
        # for the rest —`batalla.sp_del_arma`—. The battle reads it once per
        # actor when it is set up.
        bytes_asm("item_sp", [db_items[n].sp_cost
                              if db_items[n].type == lcf.ITEM_TYPE_WEAPON
                              else 0 for n in items], declarar=True)
        # `item_actores` also goes outside bank 0 —it is read with
        # `lda f:item_actores, x`—: it is 496 bytes, the fattest ones `TABLAS`
        # had left, and bank 0 overflowed. It isn't a precaution: on
        # 2026-09-13 `just demo` stopped with "el área no
        # entra: 32719 bytes en 32704" and no case of the suite saw it.
        # It is read once per item when building the equipment screen's list,
        # so the extra cycle of long addressing doesn't show.
        bytes_asm("item_actores", [
            sum(1 << b for b in range(8)
                if 8 * byte + b + 1 < actores_n
                and db_items[n].equippable_by(8 * byte + b + 1))
            for n in items for byte in range(8)], declarar=True)
        # `actor_params` goes outside bank 0 —it is read with
        # `lda f:actor_params, x`, only once per equipment screen— for the same
        # reason as `item_k`: it is 488 bytes and the code's bank filled up,
        # and this time with the drawing of the battle animations.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_params", [
            (reglas.parametro_de(db.actors[a], k)
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)
            for k in ("attack", "defense", "spirit", "agility")],
            declarar=True)
        handle.write('.segment "TABLAS"\n')
        handle.write('\n.segment "RODATA"\n')
        handle.write(".bloque %d\n"
                     % (2 * actores_n * constantes.RANURAS_EQUIPO))
        handle.write("equipo_inicial:\n    .word %s\n" % ", ".join(
            str(db.actors[a].initial_equipment[r] if a in db.actors else 0)
            for a in range(actores_n)
            for r in range(constantes.RANURAS_EQUIPO)))
        handle.write('\n.segment "TABLAS"\n')
        words_asm("actor_txt", [texto_actor.get(a, 0xFFFF)
                                for a in range(actores_n)], "$%04X")
        words_asm("eq_param_pos", [pos(f, c) for f, c in P.EQ_PARAMS])
        words_asm("item_precio", [db_items[n].price for n in items])
        handle.write(
            "TI_TEXTO          = %d\n"
            "TI_TEXTO_TENGO    = %d\n"
            "TI_TEXTO_LLEVO    = %d\n"
            "TI_TEXTO_MONEDA   = %d\n"
            "TI_SEGUNDO        = %d\n"
            "TI_PRINCIPAL_MSG_POS = %d\n"
            "TI_MSG_POS        = %d\n"
            "TI_ORDEN_POS0     = %d\n"
            "TI_ORO_POS        = %d\n"
            "TI_TENGO_POS      = %d\n"
            "TI_TENGO_NUM      = %d\n"
            "TI_LLEVO_POS      = %d\n"
            "TI_LLEVO_NUM      = %d\n"
            "TI_LISTA_POS0     = %d\n"
            "TI_LISTA_FILAS_COMPRA = %d\n"
            "TI_LISTA_FILAS_VENTA = %d\n"
            "TI_NOMBRE         = %d\n"
            "TI_PRECIO         = %d\n"
            "TI_CUANTOS_POS    = %d\n"
            "TI_CUANTOS_X_POS  = %d\n"
            "TI_CUANTOS_NUM_POS = %d\n"
            "TI_TOTAL_POS      = %d\n"
            "TI_ROJO           = %d\n"
            % (texto_tienda, texto_tengo, texto_llevo, texto_moneda,
               P.TI_SEGUNDO,
               pos(P.TI_PRINCIPAL_MSG_FILA, T.ITEM_DESC_COL),
               pos(P.TI_MSG_FILA, T.ITEM_DESC_COL),
               pos(P.TI_PRINCIPAL_MSG_FILA + 2, P.TI_ORDEN_COL),
               pos(P.TI_ORO_FILA, P.TI_ORO_COL),
               pos(P.TI_TENGO_FILA, P.TI_ESTADO_COL),
               pos(P.TI_TENGO_FILA, P.TI_ESTADO_NUM),
               pos(P.TI_LLEVO_FILA, P.TI_ESTADO_COL),
               pos(P.TI_LLEVO_FILA, P.TI_ESTADO_NUM),
               pos(P.TI_LISTA_FILA0, 0), P.TI_LISTA_FILAS_COMPRA,
               P.TI_LISTA_FILAS_VENTA, P.TI_LISTA_COL * 2,
               P.TI_PRECIO_COL * 2,
               pos(P.TI_CUANTOS_FILA, P.TI_LISTA_COL),
               pos(P.TI_CUANTOS_FILA, P.TI_CUANTOS_X_COL),
               pos(P.TI_CUANTOS_FILA, P.TI_CUANTOS_COL),
               pos(P.TI_TOTAL_FILA, P.TI_ORO_COL), T.ITEM_ROJO))
        # `eq_barra` counts the rows of the slots and those of the list from
        # the same one: they are the same window.
        if P.EQ_LISTA_FILA0 != P.EQ_RANURA_FILA0:
            raise SystemExit("the equipment list starts at row %d and the "
                             "slots at %d" % (P.EQ_LISTA_FILA0,
                                              P.EQ_RANURA_FILA0))
        handle.write(
            "ACTORES_N         = %d\n"
            "RANURAS_EQUIPO    = %d\n"
            "EQ_TEXTO_PARAM    = %d\n"
            "EQ_TEXTO_RANURA   = %d\n"
            "EQ_ACTOR_POS      = %d\n"
            "EQ_BARRA_FILA0    = %d\n"
            "EQ_MARCO_TEXTO    = %d\n"
            "EQ_MARCO_TEXTO_N  = %d\n"
            "EQ_PARAM_VALOR    = %d\n"
            "EQ_PARAM_FLECHA   = %d\n"
            "EQ_RANURA_POS0    = %d\n"
            "EQ_RANURA_TERM    = %d\n"
            "EQ_RANURA_NOMBRE  = %d\n"
            "EQ_RANURA_ANCHO   = %d\n"
            "EQ_LISTA_POS0     = %d\n"
            "EQ_LISTA_FILAS    = %d\n"
            "EQ_LISTA_NOMBRE   = %d\n"
            "PANT_DOS_PUNTOS   = %d\n"
            "PANT_DESC_POS     = %d\n"
            % (actores_n, constantes.RANURAS_EQUIPO, texto_param[0],
               texto_ranura[0],
               pos(P.EQ_ACTOR_FILA, P.EQ_ACTOR_COL), P.EQ_RANURA_FILA0,
               P.EQ_RANURA_FILA0,
               max(constantes.RANURAS_EQUIPO, P.EQ_LISTA_FILAS) * 2,
               P.EQ_PARAM_VALOR * 2,
               P.EQ_PARAM_FLECHA * 2, pos(P.EQ_RANURA_FILA0, 0),
               P.EQ_RANURA_TERM_COL * 2, P.EQ_RANURA_NOMBRE_COL * 2,
               P.EQ_RANURA_NOMBRE_ANCHO, pos(P.EQ_LISTA_FILA0, 0),
               P.EQ_LISTA_FILAS,
               P.EQ_LISTA_NOMBRE_COL * 2,
               T.ITEM_DOS_PUNTOS_COL * 2,
               pos(T.ITEM_DESC_Y // constantes.CELL, T.ITEM_DESC_COL)))
        # --- the battle ---
        # Each actor's max HP at its level, by actor number. They go separately
        # from `actor_params`, which carries the four the equipment screen
        # shows; the equipment doesn't touch the HP, as in RM2k.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_hpmax", [
            (reglas.parametro_de(db.actors[a], "maxhp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)], declarar=True)
        # And the SP, which are state since 2026-09-13 for the same reason as
        # the HP: the skills spend them. See `hp_inicial_poner` in
        # tools/runtime/banco1.s.
        words_asm("actor_spmax", [
            (reglas.parametro_de(db.actors[a], "maxsp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)], declarar=True)
        handle.write(experiencia_asm(db, ranuras["actores"], actores_n))
        # --- the skills ---
        #
        # One row per skill the cartridge carries, in the order of
        # `habilidades_rom`, which is by RM2k number. The fields are those of
        # `lcf.Skill` and the computations that use them are in `batalla.py`:
        # `efecto_habilidad` is `Algo::CalcSkillEffect` and `costo_de` is
        # `CalcSkillCost`.
        #
        # They go **outside bank 0** and declared with `.bloque`, like
        # everything the battle reads with `lda f:`: the code's bank is full,
        # and a table split between two banks would be read wrong from the
        # middle on.
        lugar_hab = {h: k for k, h in enumerate(habilidades_rom)}
        # That all the ones that reach here are of the kind the battle knows
        # how to offer is guaranteed by `batalla.habilidad_usable`, which is
        # the filter `habilidades_de` applies on both sides. It is checked
        # again in case they were ever emitted from somewhere else: a
        # multi-target scope or a three-digit cost would be drawn wrong
        # silently.
        for h in habilidades_rom:
            if not B.habilidad_usable(db.skills[h]):
                raise SystemExit(
                    "skill %d —type %d, scope %d, %d SP— isn't one of the "
                    "ones this battle knows how to offer" % (h, db.skills[h].type,
                                                             db.skills[h].scope,
                                                             db.skills[h].sp_cost))
        words_asm("hab_id", habilidades_rom, declarar=True)
        words_asm("hab_txt", [texto_hab[h] for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_desc", [texto_hab_desc[h] for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_msg1", [texto_hab_msg1[h] for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_msg2", [texto_hab_msg2[h] for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_power", [db.skills[h].power for h in habilidades_rom],
                  declarar=True)
        words_asm("hab_switch", [db.skills[h].switch_id
                                 for h in habilidades_rom], declarar=True)
        bytes_asm("hab_sp", [db.skills[h].sp_cost for h in habilidades_rom],
                  declarar=True)
        # The type: 0 is `normal` and 3 is `switch`, which is the one that
        # turns on a switch and does nothing else. See `Skill::vExecute`.
        bytes_asm("hab_tipo", [db.skills[h].type for h in habilidades_rom],
                  declarar=True)
        bytes_asm("hab_fis", [db.skills[h].physical_rate
                              for h in habilidades_rom], declarar=True)
        bytes_asm("hab_mag", [db.skills[h].magical_rate
                              for h in habilidades_rom], declarar=True)
        bytes_asm("hab_var", [db.skills[h].variance
                              for h in habilidades_rom], declarar=True)
        bytes_asm("hab_hit", [db.skills[h].hit for h in habilidades_rom],
                  declarar=True)
        # What it touches, one bit per thing, in the order `Skill::vExecute`
        # looks at them —which is the order it consumes randomness in and
        # that is why it matters—: HP, SP, attack, defense, spirit and
        # agility. Bit 6 says whether it targets enemies
        # —`Algo::SkillTargetsEnemies`— and 7 whether it ignores defense.
        bytes_asm("hab_afecta", [
            (1 if db.skills[h].affect_hp else 0)
            | (2 if db.skills[h].affect_sp else 0)
            | (4 if db.skills[h].affect_attack else 0)
            | (8 if db.skills[h].affect_defense else 0)
            | (16 if db.skills[h].affect_spirit else 0)
            | (32 if db.skills[h].affect_agility else 0)
            | (64 if db.skills[h].targets_enemies else 0)
            | (128 if db.skills[h].ignore_defense else 0)
            for h in habilidades_rom], "$%02X", declarar=True)
        # And the scope as is, `rpg::Skill::Scope`: 0 one enemy, 1 all, 2
        # oneself, 3 one ally, 4 the whole party. Since 2026-09-27 the battle
        # knows all five: see `batalla.blancos_de_la_habilidad`.
        bytes_asm("hab_alcance", [db.skills[h].scope for h in habilidades_rom],
                  declarar=True)
        # The parallel common events that only look at the equipment,
        # compiled: the ROM runs them when closing the menu if their switch is
        # on. For each one, where its switch is in the bitmap —byte and mask—
        # and its code. See `eventos.COMUNES_DEL_EQUIPO`.
        del_equipo = sorted(eventos.COMUNES_DEL_EQUIPO.items())
        handle.write("COMEQ_N = %d\n" % len(del_equipo))
        words_asm("comeq_byte", [sw >> 3 for sw, _n in del_equipo],
                  declarar=True)
        bytes_asm("comeq_mascara", ["$%02X" % (1 << (sw & 7))
                                    for sw, _n in del_equipo], "%s",
                  declarar=True)
        words_asm("comeq_cod", [".loword(comun_equipo_%d)" % n
                                for _sw, n in del_equipo], "%s",
                  declarar=True)
        # The bank goes as a word —its high byte isn't read— so that the ROM
        # indexes it with the same X as `comeq_cod`.
        words_asm("comeq_banco", ["^comun_equipo_%d" % n
                                  for _sw, n in del_equipo], "%s",
                  declarar=True)
        for _sw, n in del_equipo:
            handle.write(bloque("comun_equipo_%d" % n,
                                eventos.compilar_comun_del_equipo(n)) + "\n")
        # And what each actor knows, which since 2026-09-21 is state: one bit
        # per (actor, skill) pair in `FAR_HAB`, with the slots of
        # `eventos.HABILIDAD_RANURA`. It is answered by branch 4 of
        # `ConditionalBranch` —which already brings the slot in the bytecode—
        # and by the battle's list, which walks the actor's pairs: where they
        # start —`hab_par_ini`, as words because there are more than 255—,
        # how many there are, and the `k` of each one in the `hab_*` tables
        # above, or $FF if this one doesn't know how to offer it. Since an
        # actor's pairs go together and by number, the list comes out sorted
        # like `LearnSkill`'s.
        #
        # The bits start with `reglas.aprendidas_de`, which is what the LDB
        # says at its initial level: `hab_inicial_poner` copies them on reset.
        pares = sorted(eventos.HABILIDAD_RANURA.items(), key=lambda x: x[1])
        hab_par_ini, hab_par_n = [], []
        for a in range(actores_n):
            suyos = [r for (actor, _s), r in pares if actor == a]
            hab_par_ini.append(suyos[0] if suyos else 0)
            hab_par_n.append(len(suyos))
            if suyos and suyos != list(range(suyos[0], suyos[0] + len(suyos))):
                raise SystemExit("the skill pairs of actor %d aren't "
                                 "contiguous" % a)
        if max(hab_par_n, default=0) > 255:
            raise SystemExit("an actor has more than 255 skill pairs and "
                             "`hab_par_n` is one byte")
        hab_bytes = max(1, (len(pares) + 7) // 8)
        sabe_de = {a: set(reglas.aprendidas_de(db, a)) for a in db.actors}
        bits = [0] * hab_bytes
        for (a, h), r in pares:
            if h in sabe_de.get(a, ()):
                bits[r >> 3] |= 1 << (r & 7)
        handle.write("; How many bytes the skill bits take in `FAR_HAB`.\n"
                     "HAB_BYTES = %d\n" % hab_bytes)
        handle.write("; The signature of the save format: see `SRAM_FIRMA`.\n"
                     "PARTIDA_FIRMA = $%04X\n" % firma_de_la_partida(
                         pares, experiencia_ranuras(db, ranuras["actores"]),
                         actores_n))
        words_asm("hab_par_ini", hab_par_ini, declarar=True)
        bytes_asm("hab_par_n", hab_par_n, declarar=True)
        bytes_asm("hab_par_k", [lugar_hab.get(h, 0xFF)
                                if a in ranuras["actores"] else 0xFF
                                for (a, h), _r in pares], declarar=True)
        bytes_asm("hab_inicial", bits, "$%02X", declarar=True)
        # And at which level the LDB's learning table teaches each pair, or 0
        # if it doesn't —the ones only a `ChangeSkills` gives—: on leveling
        # up, `exp_sumar` sets the bits of the pairs whose level it just
        # passed, which is `LearnLevelSkills(old_level + 1, new_level)`.
        bytes_asm("hab_par_nivel", [B.nivel_en_que_aprende(db, a, h)
                                    if a in db.actors else 0
                                    for (a, h), _r in pares], declarar=True)
        # And the name the victory tells it by —"<skill> acquired!"—, or $FFFF
        # if it isn't learned by leveling up from the starting one.
        words_asm("hab_par_aprende_txt", [
            texto_hab_entero[h] if a in ranuras["actores"]
            and B.nivel_en_que_aprende(db, a, h) > 0 and h in texto_hab_entero
            else 0xFFFF for (a, h), _r in pares], "$%04X", declarar=True)
        # 254 and not 256: `eacc_hab` uses $FF for the attack and
        # `ba_accion_enemiga` answers $FE when it has none left.
        if len(habilidades_rom) > 254:
            raise SystemExit("the cartridge's skills are %d and `hab_par_k` "
                             "is one byte" % len(habilidades_rom))
        # And what each actor's skills command is called in the menu.
        words_asm("actor_hab_txt", [texto_hab_orden.get(a, 0xFFFF)
                                    for a in range(actores_n)], "$%04X",
                  declarar=True)
        # The troops some battle of the cartridge asks for, and the enemies
        # that form them. The bytecode carries the troop's **RM2k number**, so
        # `tropa_id` is what the ROM looks up; the list being only that of the
        # used troops doesn't change a byte of any page. See
        # `eventos.Tropas`.
        usadas = [n for n in tropas if n in db.troops]
        lugar_de = {e: k for k, e in enumerate(enemigos_rom)}
        miembros, inicios = [], []
        for numero in usadas:
            lista = db.troops[numero].members[:constantes.ENEMIGOS_MAX]
            inicios.append(len(miembros))
            miembros += [lugar_de[e] for e in lista]
        if len(miembros) > 255 or len(usadas) > 255:
            raise SystemExit("the cartridge's troops don't fit in one-byte "
                             "tables: %d troops, %d members"
                             % (len(usadas), len(miembros)))
        words_asm("tropa_id", usadas, declarar=True)
        # The experience beating each one gives, already added up: see
        # `experiencia.exp_de_la_tropa`. It goes outside bank 0, like
        # everything here, because it is read once per battle.
        exp_tropa = [X.exp_de_la_tropa(db, n) for n in usadas]
        for n, exp in zip(usadas, exp_tropa):
            if exp > 0xFFFF:
                raise SystemExit("troop %d gives %d experience and the ROM "
                                 "adds it in sixteen bits" % (n, exp))
        words_asm("tropa_exp", exp_tropa, declarar=True)
        # And the gold, the same: `batalla.oro_de_la_tropa`. The victory tells
        # it with `ba_vic_numero`, which reaches five digits.
        oro_tropa = [B.oro_de_la_tropa(db, n) for n in usadas]
        for n, oro in zip(usadas, oro_tropa):
            if oro > 0xFFFF:
                raise SystemExit("troop %d gives %d gold and the ROM adds it "
                                 "in sixteen bits" % (n, oro))
        words_asm("tropa_oro", oro_tropa, declarar=True)
        # What the victory writes has to fit on its line: the ROM builds it
        # with a number or a name in the middle and doesn't split it.
        P.cobrar_la_victoria(
            term_batalla, max(exp_tropa, default=0),
            [db.actors[a].name for a in ranuras["actores"] if a in db.actors],
            [db.skills[h].name for h in sorted(ensenadas)],
            max(oro_tropa, default=0),
            [db_items[i].name for i in sorted({db.enemies[e].drop_id
                                               for e in enemigos_rom}
                                              - {0})])
        bytes_asm("tropa_ini", inicios, declarar=True)
        # Which members of each troop start **hidden** —the troop's
        # `invisible`—, one bit per place: a page with `ShowHiddenMonster`
        # makes them appear. It is the Rat King, who calls his rats. See
        # `BAF_OCULTO`.
        bytes_asm("tropa_ocultos", [
            sum(1 << k for k, oculto in enumerate(
                db.troops[n].hidden[:constantes.ENEMIGOS_MAX]) if oculto)
            for n in usadas], "$%02X", declarar=True)
        bytes_asm("tropa_n",
                  [len(db.troops[n].members[:constantes.ENEMIGOS_MAX])
                   for n in usadas], declarar=True)
        bytes_asm("tropa_miembro", miembros, declarar=True)
        # And the event pages of each troop, in LDB order —which is the order
        # `ScheduleNextPage` tries them in—, without the ones that didn't
        # compile: skipping them doesn't change the order of the others. Per
        # troop, where they start and how many there are; per page, its
        # trigger and where its code is inside `tropa_codigo`, which
        # deduplicates them. See `eventos.PaginasDeTropa` and `ba_pag_probar`
        # in tools/runtime/batalla_tropa.s.
        #
        # **The small tables go to bank 1, `FAR`; the two big blocks —the code
        # and the messages—, to RODATA.** Until 2026-09-27 all four went to
        # bank 1, because with them in RODATA the `juego` cartridge went over
        # 4 MB (measured on 2026-09-21); that cartridge no longer exists,
        # `release` is around 71%, and in bank 1 the two blocks were almost
        # eleven KB of which the battle's hand-written code didn't have even
        # four hundred bytes. Both are read with a long pointer whose bank
        # comes from `^tropa_codigo` and `^mensajes_tropa`, so it is enough
        # for each to fit whole in one bank, which is what `bloque` asks for.
        pt = paginas_tropa or eventos.PaginasDeTropa()
        entradas, pag_ini, pag_n = [], [], []
        for numero in usadas:
            suyas = pt.por_tropa.get(numero, [])
            pag_ini.append(len(entradas))
            pag_n.append(len(suyas))
            entradas += suyas
        if max(pag_n, default=0) > eventos.TROPA_PAGINAS_MAX:
            raise SystemExit("a troop brings %d pages and the battle tracks %d"
                             % (max(pag_n), eventos.TROPA_PAGINAS_MAX))
        handle.write('.segment "FAR"\n')
        words_asm("tropa_pag_ini", pag_ini)
        bytes_asm("tropa_pag_n", pag_n)
        bytes_asm("tpag_flags", [d.flags for d, _ofs in entradas], "$%02X")
        words_asm("tpag_sw_a", [d.switch_a for d, _ofs in entradas])
        words_asm("tpag_cod", [".loword(tropa_codigo + %d)" % ofs
                               for _d, ofs in entradas], "%s")
        # The three for `switch_b` and the variable only if some page uses
        # them: the characters' 32 systems only look at `switch_a`, and with
        # none the ROM never reads them —the bit in `tpag_flags` is zero—, so
        # the label is enough. The turn and the HP have no table: they go in
        # front of the code, see `eventos.cabecera_de_tropa`.
        for nombre, campo, bit in (
                ("tpag_sw_b", "switch_b", eventos.TROPA_DISPARO_SWITCH_B),
                ("tpag_var", "ranura", eventos.TROPA_DISPARO_VARIABLE),
                ("tpag_valor", "valor", eventos.TROPA_DISPARO_VARIABLE)):
            usa = any(d.flags & bit for d, _ofs in entradas)
            words_asm(nombre, [getattr(d, campo) & 0xFFFF
                               for d, _ofs in entradas] if usa else [])
        handle.write('.segment "RODATA"\n')
        handle.write(bloque("tropa_codigo", bytes(pt.cuerpos) or b"\x00")
                     + "\n")
        handle.write(bloque("mensajes_tropa", pt.mensajes.bytes())
                     + "\n")
        # And the random encounters, which also talk about troops by their
        # RM2k number. They go here outside bank 0 —they are read with
        # `lda f:tabla, x`— because eighty-five bytes were left there and this
        # is about two hundred. See `encuentros_de_la_rom` and
        # `tools/runtime/encuentros.s`.
        enc = encuentros or {"por_mapa": [0xFF] * len(mapas), "registros": [],
                             "zonas": [], "tropas": []}
        bytes_asm("enc_mapa", enc["por_mapa"], declarar=True)
        words_asm("enc_base", [r["base"] for r in enc["registros"]],
                  declarar=True)
        umbrales = []
        for r in enc["registros"]:
            # Seven thresholds and one of padding: with eight the record's
            # index is a shift and not a multiplication. See ENC_STRIDE.
            umbrales += list(r["umbrales"]) + [0xFF]
        bytes_asm("enc_umbral_n", umbrales, declarar=True)
        bytes_asm("enc_zona_ini", [r["zona_ini"] for r in enc["registros"]],
                  declarar=True)
        bytes_asm("enc_zona_n", [r["zona_n"] for r in enc["registros"]],
                  declarar=True)
        for k, etiqueta in enumerate(("enc_izq", "enc_arr", "enc_der",
                                      "enc_aba")):
            words_asm(etiqueta, [z["rect"][k] for z in enc["zonas"]],
                      declarar=True)
        bytes_asm("enc_tropa_ini", [z["tropa_ini"] for z in enc["zonas"]],
                  declarar=True)
        bytes_asm("enc_tropa_n", [z["tropa_n"] for z in enc["zonas"]],
                  declarar=True)
        words_asm("enc_tropa", enc["tropas"], declarar=True)
        words_asm("enemigo_hp", [db.enemies[e].max_hp for e in enemigos_rom],
                  declarar=True)
        words_asm("enemigo_atk", [db.enemies[e].attack for e in enemigos_rom],
                  declarar=True)
        words_asm("enemigo_def", [db.enemies[e].defense for e in enemigos_rom],
                  declarar=True)
        words_asm("enemigo_agi", [db.enemies[e].agility for e in enemigos_rom],
                  declarar=True)
        # The spirit and the SP: `CalcSkillEffect` asks for them, subtracting
        # `magical_rate * spi_del_blanco / 80` from the effect. Until
        # 2026-09-13 nobody read them because no computation of the battle
        # used them.
        words_asm("enemigo_spi", [db.enemies[e].spirit for e in enemigos_rom],
                  declarar=True)
        words_asm("enemigo_sp", [db.enemies[e].max_sp for e in enemigos_rom],
                  declarar=True)
        bytes_asm("enemigo_hit", [db.enemies[e].hit for e in enemigos_rom],
                  declarar=True)
        # The critical hit, already as a whole percentage:
        # `CalcCriticalHitChance` computes it as `1 / critical_hit_chance`
        # times a hundred and truncates it.
        bytes_asm("enemigo_crit", [
            (100 // (db.enemies[e].critical_hit_chance or 30))
            if db.enemies[e].critical_hit else 0 for e in enemigos_rom],
            declarar=True)
        words_asm("enemigo_txt", [texto_enemigo[e] for e in enemigos_rom],
                  declarar=True)
        # Each one's experience and gold, which the victory subtracts from the
        # troop's for each enemy that stayed hidden: see `ba_sin_ocultos`.
        words_asm("enemigo_exp", [db.enemies[e].exp for e in enemigos_rom],
                  declarar=True)
        words_asm("enemigo_oro", [db.enemies[e].gold for e in enemigos_rom],
                  declarar=True)
        # What it drops on dying: the LDB item, or 0 if it drops nothing, and
        # the chance as a percentage. See `ba_vic_botin` and
        # `batalla.tirar_el_botin`. Every item that can be dropped is in
        # `items`: see `items_del_botin`, which adds it.
        for e in enemigos_rom:
            if db.enemies[e].drop_id and db.enemies[e].drop_id not in k_de:
                raise SystemExit("enemy %d drops item %d and the "
                                 "cartridge doesn't carry it"
                                 % (e, db.enemies[e].drop_id))
        words_asm("enemigo_botin", [db.enemies[e].drop_id
                                    for e in enemigos_rom], declarar=True)
        bytes_asm("enemigo_botin_pct", [db.enemies[e].drop_prob
                                        for e in enemigos_rom], declarar=True)
        # What each enemy can do on its turn: its list from
        # `batalla.acciones_de_enemigo`, contiguous in `eacc_*` —where it
        # starts and how many there are—. Per action, the skill as a `k` of the
        # `hab_*` tables or $FF for the attack, and its `rating` with bit 7 set
        # if it isn't `efectiva`: it counts for the maximum and then weighs
        # zero. See `ba_accion_enemiga` in tools/runtime/batalla.s.
        eacc_ini, eacc_hab, eacc_peso = [], [], []
        for e in enemigos_rom:
            if len(acciones_rom[e]) > B.ACCIONES_MAX:
                raise SystemExit("enemy %d brings %d actions and the ROM "
                                 "weighs %d: see `batalla.ACCIONES_MAX`"
                                 % (e, len(acciones_rom[e]), B.ACCIONES_MAX))
            eacc_ini.append(len(eacc_hab))
            for rating, skill, efectiva in acciones_rom[e]:
                if not 0 < rating < 0x80:
                    raise SystemExit("enemy %d brings an action with rating "
                                     "%d and the ROM carries it in seven bits"
                                     % (e, rating))
                eacc_hab.append(0xFF if skill is None
                                else lugar_hab[skill.id])
                eacc_peso.append(rating | (0 if efectiva else 0x80))
        if len(eacc_hab) > 255:
            raise SystemExit("the actions of the cartridge's enemies are %d "
                             "and `enemigo_acc_ini` is one byte"
                             % len(eacc_hab))
        handle.write("ACCIONES_MAX = %d\n" % B.ACCIONES_MAX)
        bytes_asm("enemigo_acc_ini", eacc_ini, declarar=True)
        bytes_asm("enemigo_acc_n", [len(acciones_rom[e]) for e in enemigos_rom],
                  declarar=True)
        bytes_asm("eacc_hab", eacc_hab, declarar=True)
        bytes_asm("eacc_peso", eacc_peso, declarar=True)
        # And the battle scene: the backdrops and the battlers separately.
        # `usadas` is the same order as `tropa_id`, which is what
        # `escena_tropa_fondo` indexes, and that of `tropa_miembro`.
        handle.write(escenas_asm(escenas or {"fondos": [], "battlers": [],
                                             "battler_de": {},
                                             "tropa_fondo": {},
                                             "mapa_fondo": [0xFF] * len(mapas)},
                                 usadas, db))
        handle.write('.segment "TABLAS"\n')
        # The product of the hit computation has to fit in sixteen bits:
        # (100 - hit rate) times the sum of both agilities. With the minimum
        # hit rate of 70 that is 30 times 1998, and the agility cap is guarded
        # by `BA_AGI_TOPE`; an enemy with a lower hit rate would overflow it
        # without warning, so it stops here.
        # `recover_hp_rate * hp_max` has to fit in sixteen bits: the ROM does
        # it with the hardware multiplier, which gives a word. With the
        # percentage capped at 100 that is hp_max of up to 655, and this
        # game's actors are around 40. A fatter actor would overflow without
        # warning, so it stops here.
        for a in range(actores_n):
            maximo = (reglas.parametro_de(db.actors[a], "maxhp")
                      if a in db.actors else 0)
            if maximo * 100 > 0xFFFF:
                raise SystemExit(
                    "actor %d has %d HP and the ROM's healing computation "
                    "is sized for 655" % (a, maximo))
        for e in enemigos_rom:
            if db.enemies[e].hit < 70:
                raise SystemExit("enemy %d has a hit rate of %d, and the ROM's "
                                 "hit computation is sized for 70"
                                 % (e, db.enemies[e].hit))
        handle.write(
            "TROPAS_N          = %d\n"
            "BATALLA_SEMILLA   = $%04X\n"
            "BA_TXT_BASE       = %d\n"
            "BA_ENEMIGO_POS0   = %d\n"
            "BA_GRUPO_POS0     = %d\n"
            "BA_MSG_POS1       = %d\n"
            "BA_MSG_POS2       = %d\n"
            "BA_FILA_BYTES     = %d\n"
            "BA_CURSOR_DX      = %d\n"
            "BA_NOMBRE_DX      = %d\n"
            "BA_NOMBRE_ANCHO   = %d\n"
            "BA_HP_DX          = %d\n"
            "BA_HP_NUM_DX      = %d\n"
            "BA_HP_ENEMIGOS    = %d\n"
            "BA_BARRA_DX       = %d\n"
            "BA_HPMAX_DX       = %d\n"
            "BA_MSG_DX         = %d\n"
            "BA_PAG_MSG_POS0   = %d\n"
            "BA_PAG_MSG_DX     = %d\n"
            "BA_PAG_MSG_ANCHO  = %d\n"
            "TROPA_PAG_MAX     = %d\n"
            "TPAG_SWITCH_A     = $%02X\n"
            "TPAG_SWITCH_B     = $%02X\n"
            "TPAG_VARIABLE     = $%02X\n"
            "TPAG_TURNO        = $%02X\n"
            "TPAG_ENEMIGO      = $%02X\n"
            "TPAG_ACTOR        = $%02X\n"
            "TPAG_CON_CABECERA = $%02X\n"
            "TPAG_CABECERA     = %d\n"
            % (len(usadas), B.BATALLA_SEMILLA, texto_batalla,
               pos(P.BA_ENEMIGO_FILA0, 0), pos(P.BA_GRUPO_FILA0, 0),
               pos(P.BA_MSG_FILA1, 0), pos(P.BA_MSG_FILA2, 0), 2 * 64,
               P.BA_CURSOR_COL * 2, P.BA_NOMBRE_COL * 2, P.BA_NOMBRE_ANCHO,
               P.BA_HP_COL * 2, P.BA_HP_NUM * 2, int(hp_de_enemigos),
               P.BA_BARRA_COL * 2,
               P.BA_HP_MAX_NUM * 2, 1 * 2,
               pos(P.BA_PAG_MSG_FILA0, 0), P.BA_PAG_MSG_COL * 2,
               P.BA_PAG_MSG_ANCHO, eventos.TROPA_PAGINAS_MAX,
               eventos.TROPA_DISPARO_SWITCH_A, eventos.TROPA_DISPARO_SWITCH_B,
               eventos.TROPA_DISPARO_VARIABLE, eventos.TROPA_DISPARO_TURNO,
               eventos.TROPA_DISPARO_ENEMIGO, eventos.TROPA_DISPARO_ACTOR,
               eventos.TROPA_CON_CABECERA, eventos.TROPA_CABECERA_BYTES))
        # The audio: the battle song, the victory one and the five sound
        # effects, with the index they got from `Temas`. $FF and $FFFF mean
        # "the LDB has it turned off", which is the case of `battle_se` in
        # this game. Who sounds at which moment is in `eventos.AUDIO_BATALLA`,
        # taken from easyrpg-player; only the numbers travel here.
        audio = audio_batalla or {}
        # The battle's audio package goes after the maps' ones, so its index
        # is how many maps the ROM carries. It is emitted here and checked by
        # the music section, which is the one that builds the list.
        #
        # Sixteen bits, and "there is none" is $FFFF: with the 328 maps of the
        # whole game the index doesn't fit in a byte, same as `mapa_actual`.
        # See `batalla_audio_cargar`.
        handle.write(
            "BA_TEMA           = $%02X\n"
            "BA_TEMA_FIN       = $%02X\n"
            "BA_PAQUETE        = $%04X\n"
            % (audio.get("battle_music", 0xFF),
               audio.get("battle_end_music", 0xFF),
               len(mapas) if audio else 0xFFFF))
        for nombre, constante in (("dodge_se", "BA_SE_ERRAR"),
                                  ("enemy_attack_se", "BA_SE_ATAQUE"),
                                  ("enemy_damaged_se", "BA_SE_DANO_ENEMIGO"),
                                  ("actor_damaged_se", "BA_SE_DANO_ACTOR"),
                                  ("enemy_death_se", "BA_SE_MUERTE"),
                                  ("escape_se", "BA_SE_HUIR"),
                                  ("item_se", "BA_SE_ITEM")):
            handle.write("%-18s= $%04X\n"
                         % (constante, audio.get(nombre, 0xFFFF)))
        handle.write("BA_TXT_VICTORIA2  = %d\n"
                     "BA_VIC_TERMINO_N  = %d\n"
                     % (texto_victoria2, len(victoria)))
        # The terms, by their place in `reglas.BA_TERMINOS`.
        for k, (nombre, _termino) in enumerate(reglas.BA_TERMINOS):
            handle.write("BA_TXT_%-11s= BA_TXT_BASE + %d\n"
                         % (nombre.upper(), k))
        handle.write("BA_TXT_REVIVIO    = %d\n" % texto_revivio)
        # The menu's five commands, with what the ROM needs of each one: which
        # line and which column it goes in, which term names it and whether it
        # always goes in gray. They go in tables and not in a computation
        # because since 2026-09-13 **they aren't three in a row on one line**:
        # they are the five of ABL's menu spread over two. See
        # `pantallas.BA_ORDENES`.
        handle.write("BA_ORDENES_N      = %d\n" % len(P.BA_ORDENES))
        handle.write("BA_ITEM_CUENTA_DX = %d\n" % (P.BA_ITEM_CUENTA_COL * 2))
        handle.write("BA_ORDEN_USAR     = %d\n" % P.BA_ORDEN_USAR)
        handle.write("BA_ORDEN_HUIR     = %d\n" % P.BA_ORDEN_HUIR)
        handle.write("BA_ORDEN_ATACAR   = %d\n" % P.BA_ORDEN_ATACAR)
        handle.write("BA_ORDEN_DEFENDER = %d\n" % P.BA_ORDEN_DEFENDER)
        handle.write("BA_ORDEN_HABILIDAD= %d\n" % P.BA_ORDEN_HABILIDAD)
        # The skills screen: two columns with the name and the cost, and the
        # description of the one under the cursor at the very top. The
        # geometry comes from `pantallas.py`, like the item list's.
        handle.write(
            "HABILIDADES_N     = %d\n"
            "BA_HAB_DESC_POS   = %d\n"
            "BA_HAB_POS0       = %d\n"
            "BA_HAB_FILAS      = %d\n"
            "BA_HAB_COLUMNAS   = %d\n"
            "BA_HAB_COLUMNA_DX = %d\n"
            "BA_HAB_NOMBRE_DX  = %d\n"
            "BA_HAB_NOMBRE_ANCHO = %d\n"
            "BA_HAB_GUION_DX   = %d\n"
            "BA_HAB_COSTO_DX   = %d\n"
            "BA_HAB_COSTO_CIFRAS = %d\n"
            % (len(habilidades_rom),
               pos(P.BA_HAB_DESC_FILA, P.BA_HAB_DESC_COL),
               pos(P.BA_HAB_FILA0, 0), P.BA_HAB_FILAS, P.BA_HAB_COLUMNAS,
               P.BA_HAB_COLUMNA_DX * 2, P.BA_HAB_NOMBRE_COL * 2,
               P.BA_HAB_NOMBRE_ANCHO, P.BA_HAB_GUION_COL * 2,
               P.BA_HAB_COSTO_COL * 2, P.BA_HAB_COSTO_CIFRAS))
        handle.write('.segment "RODATA"\n')
        words_asm("ba_orden_fila", [
            pos((P.BA_MSG_FILA1, P.BA_MSG_FILA2)[f], 0)
            for _n, f, _c in P.BA_ORDENES], declarar=True)
        words_asm("ba_orden_dx", [c * 2 for _n, _f, c in P.BA_ORDENES],
                  declarar=True)
        # **Two bytes.** A text index doesn't fit in one: with the 29 maps of
        # `abl` the battle's start at 273, and the one-byte table that was here
        # until 2026-09-14 emitted them anyway —`.byte 273`— for the assembler
        # to truncate them without saying anything.
        words_asm("ba_orden_txt", [
            texto_batalla + [n for n, _c in reglas.BA_TERMINOS].index(nombre)
            for nombre, _f, _c in P.BA_ORDENES], declarar=True)
        bytes_asm("ba_orden_gris", [
            1 if k in P.BA_ORDEN_SIN_HACER else 0
            for k in range(len(P.BA_ORDENES))], declarar=True)
        handle.write('.segment "TABLAS"\n')

        glifos = ranuras["items_glifos"]
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
        words_asm("item_glifo_celdas", [
            entry(celda, False, False, priority=1)
            for gris in (T.ITEM_BLANCO, T.ITEM_GRIS, T.ITEM_SUBE,
                         T.ITEM_ROJO)
            for n in range(T.ITEM_CARACTERES)
            for celda in glifos[gris].get(
                chr(T.ITEM_PRIMER_CARACTER + n),
                glifos[T.ITEM_BLANCO][chr(T.ITEM_PRIMER_CARACTER + n)])],
            "$%04X", declarar=True)
        handle.write('.segment "TABLAS"\n')
        handle.write("\n")
        # `fuente_color` goes in bank 0 and not with the rest of the window:
        # the ROM reads it with `lda fuente_color, y`, and that mode addresses
        # the data bank. With it in RODATA it read garbage, and the text came
        # out black.
        handle.write(bloque("fuente_color", bytes(ventana["color"]),
                            acomodar=False) + "\n")
        handle.write("grupo_inicial:\n    .byte %s\n\n"
                     % ",".join("%d" % a for a in grupo_inicial) or "0")
        handle.write(tabla_de_senos() + "\n")
        # How many frames a character stays still after a step and after a
        # turn, per route frequency: RM2k's stop counter, in two tables of
        # nine to index with the frequency as is. They come from
        # `eventos.espera_tras_paso` and `espera_tras_giro`. 0 and 1 aren't
        # compiled; they carry zero so that the table has no holes.
        handle.write("ruta_tras_paso:\n    .byte %s\n" % ",".join(
            "%d" % (eventos.espera_tras_paso(f)
                    if f >= eventos.RUTA_FRECUENCIA_MIN else 0)
            for f in range(eventos.RUTA_FRECUENCIA + 1)))
        handle.write("ruta_tras_giro:\n    .byte %s\n\n" % ",".join(
            "%d" % (eventos.espera_tras_giro(f)
                    if f >= eventos.RUTA_FRECUENCIA_MIN else 0)
            for f in range(eventos.RUTA_FRECUENCIA + 1)))
        handle.write(tabla_de_mapas(mapas, etiquetas))
        handle.write("\n\n")
        # After the map one, which already left the segment in RODATA.
        handle.write(anim_tabla(mapas))
        handle.write("\n")
    return materiales.informe()


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
# `ev_pos_buf` and `eleg_por_ev`.
EV_MAX = 120
# How many forced routes can be running at once on events. The page that sends
# the most walking in this game moves four distinct events, and a route
# survives the end of its page, so there can be another running on top. Eight
# gives margin and costs 88 bytes of RAM.
RUTA_EV_MAX = 12
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
# What it costs: eight bytes of `FAR_PAR_LISTA` per slot —far RAM, not the
# BSS; see `PAR_LISTA_BYTES` in `tools/runtime/ram_lejana.s`, which besides the
# event stores the page the refresh chose for it— and **one interpreter pass
# per frame for each one**. It is the second that has to be watched if the
# race gets slow: the first is gone, because the page stopped being resolved
# every frame.
#
# 48 times eight is 384 bytes, and from `FAR_PAR_LISTA` to `FAR_AZAR` there
# are 508.
PARALELO_MAX = 48
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
NPC_QUIETO = 0xFF        # in +9: this NPC doesn't walk

# The table of NPCs of the loaded map is copied to RAM, because build_oam walks
# it with an index and that addresses the data bank. The ceiling above is set
# by OAM: 128 objects fit and one is the hero, so no map can **show** more
# than 127.
#
# The number isn't that since 2026-09-06, and not by choice: the row is
# sixteen bytes, so the cap takes two kilobytes of the eight bank 0 of RAM
# has, and the RAM ran out —see `PILA` in tools/ensamblado/bancos.py—. **The
# map with the most rows in the whole game has 99**, measured over the 328, so
# 104 leaves five of headroom and gives back 368 bytes. It can't fall short
# silently: the converter stops if any map goes over.
NPC_MAX = 104


def orden_de_dibujo(npc):
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
    return (npc["layer"], npc["y"], npc["x"], npc["evento"])


def sort_key(layer, y):
    """How RM2k sorts: first the layer and only then the Y.

    A "below" event stays below the hero even if it is further forward on the
    screen, and an "above" one always covers it. Putting the layer in the high
    bits makes a single 16-bit comparison decide both things.
    """
    return (layer << 12) | (y & 0x0FFF)


# How much each opcode takes, to walk the bytecode without running it. The
# variable-length ones go with None and are measured separately.
# The bytecode walk lives in eventos.py, with the length table: there was a
# copy here and the one there went stale without anyone seeing it.
recorrer_codigo = eventos.recorrer_codigo


def orden_de_mapas(args):
    """The ROM's maps, in table order and without repeats.

    It is in a function and not written three times because **the order is
    the contract**: a compiled teleport stores the index in this table, not
    the RM2k id. Two lists built differently would take the same bytecode to
    different maps.
    """
    return [args.map_id] + [m for m in (args.mapas or []) if m != args.map_id]


# How many still events with continuous animation a map animates. See the
# reason —and the measured number— inside `eventos_movibles`.
# Measured against A Blurred Line: an assumption of the engine, not a piece of
# the game's data. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
ANIMA_QUIETO_MAX = 4


def eventos_movibles(game_map, indice_de_mapa, asociaciones=()):
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
    compile the same pages, with the same text block. Without `Graficos` here
    a route with command 34 wouldn't compile in this pass and would in the
    other, and the two lists would drift apart.

    The pages are compiled to find out and what was compiled is thrown away.
    It is repeated work —main() compiles them again with the real text
    block— but it isn't a repeated **rule**: the decision of what compiles is
    made by the same function both times.
    """
    graficos = eventos.Graficos(asociaciones)
    paginas = eventos.paginas_del_mapa(
        game_map, indice_de_mapa,
        eventos.Mensajes(), graficos=graficos)
    npcs = rm2k.collect_npcs(game_map)
    visibles = {npc["evento"] for npc in npcs}
    # And the ones that walk on their own with some page's own route, which
    # need the twelve poses just like the ones a MoveEvent sends walking.
    propios = {p["evento"] for p in paginas if p.get("ruta_propia")}
    # And the still ones with continuous animation —the save point in Lashe
    # City—, which don't walk but **change column all the same**. Without the
    # twelve poses their VRAM slot would carry a single one and there would be
    # nothing to animate them with: the still ones share a slot by (CharSet,
    # index, pose) and don't have one of their own.
    con_ruta = (eventos.blancos_de_ruta(paginas) | propios) & visibles
    animados = {npc["evento"] for npc in npcs
                if npc.get("anima")} & visibles - con_ruta
    # And the cap: a still event that animates **costs a whole VRAM slot**
    # —twelve tiles— because it stops sharing that of its (CharSet, index,
    # pose) and gets the twelve poses of its own, like the walking ones. A map
    # with thirty —52 has thirty— asks for 572 sprite tiles and 384 fit.
    #
    # So a map with more than `ANIMA_QUIETO_MAX` animates **none**, and not
    # some yes and some no: two equal fountains, one moving and the other
    # frozen, looks worse than both still. Measured over the 328 maps of the
    # game: 312 have four or fewer, and of the maps the ROMs carry today the
    # only one that goes over is 52.
    if len(animados) > ANIMA_QUIETO_MAX:
        animados = set()
    # And the ones that turn toward the hero when it talks to them: the events
    # with some action or touch page that compiled and turns —see TURN in
    # eventos.py—, with the graphics of **all** their pages that turn. The
    # twelve poses of each go to the cartridge, which is where the ROM takes
    # the one facing the hero from; the refresh compares the pages' graphics
    # to know whether the turn survives a page change.
    giran = {}
    for p in paginas:
        if (p["codigo"] and p.get("gira")
                and p["trigger"] in (eventos.TRIGGER_ACCION,
                                     eventos.TRIGGER_TOCA_HEROE)):
            giran[p["evento"]] = set()
    for p in paginas:
        if p["evento"] in giran and p.get("gira") and p["grafico"]:
            giran[p["evento"]].add(tuple(p["grafico"][:2]))
    return con_ruta | animados, list(graficos.pares), animados, giran


def graficos_de_prueba(argumento):
    """The (CharSet, index) pairs of `--grafico-de-prueba`, or () if none."""
    return tuple((charset, int(indice)) for charset, indice in argumento or ())


def firma_de_la_partida(pares, ranuras_exp, actores_n):
    """Sixteen bits that change when **what each byte of the saved game
    means** changes, so that the ROM rejects one from another build.

    The size is guarded by the ROM on its own —`PARTIDA_BYTES`, which comes
    from the same constants—; this covers what the size doesn't see: which
    RM2k variable goes in each slot, which actor each skill pair and each
    experience slot belongs to. Two builds can carry the same number of
    variables and slot 5 be a different variable in each; then the save would
    load with the same length and everything shifted.

    It is the assignments and not the whole ROM on purpose: two builds whose
    save reads the same have to be able to share it, even if everything else
    changes.
    """
    forma = {
        "variables": sorted(eventos.VARIABLE_SLOT.items(), key=lambda x: x[1]),
        "items": eventos.ITEMS_N,
        "switches": SWITCH_BYTES,
        "actores": actores_n,
        "habilidades": [[a, h, r] for (a, h), r in pares],
        "experiencia": ranuras_exp,
    }
    return zlib.crc32(json.dumps(forma).encode()) & 0xFFFF


def variables_n():
    """How many variable slots the ROM carries: at least one —a zero length
    would close the save table— and up to 256, which is what fits between
    `FAR_VARIABLES` and `FAR_ITEMS`."""
    n = max(1, len(eventos.VARIABLE_SLOT))
    if n > 256:
        sys.exit("%d variables don't fit in far RAM: FAR_ITEMS is "
                 "512 bytes from FAR_VARIABLES" % n)
    return n


def tabla_de_senos():
    """The sine the screen shake reads by index, for the bank."""
    out = ["; The sine at scale 127, for the screen shake: it is the same",
           "; list `SENO_SACUDIDA` builds in eventos.py.",
           ";",
           "; It goes outside bank 0 —`lda f:seno_sacudida, x`, one read per",
           "; shake frame— for the same reason as `item_k`: it is 256 bytes",
           "; and the code's bank filled up.",
           '.segment "RODATA"',
           ".bloque 256",
           "seno_sacudida:"]
    valores = eventos.SENO_SACUDIDA
    for i in range(0, 256, 16):
        out.append("    .byte " + ",".join("$%02X" % (v & 0xFF)
                                            for v in valores[i:i + 16]))
    # And back to bank 0: what follows —`ruta_tras_paso` and company— is read
    # with absolute indexed addressing and has to stay here.
    out.append('.segment "TABLAS"')
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
    is exactly what `eventos.Eventos` does.
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
        prioridad = (OBJ_PRIORITY_ABOVE
                     if npc["layer"] == rm2k.LAYER_ABOVE
                     else OBJ_PRIORITY)
        out.append(prioridad | ((npc["palette"] & 0x07) << 1)
                   | ((npc["tile"] >> 8) & 0x01))
        # The event's index goes **always**, even if the NPC doesn't walk: it
        # is the last tie-breaker of the drawing order, and it applies to all.
        # What sets the walking ones apart is the pose table.
        out.append(npc["evento"])
        out.append(NPC_QUIETO if npc["poses"] is None else npc["poses"])
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
        # `animar_quietos` in tools/runtime/quietos_que_animan.s.
        out.append(npc["velocidad"] | (0x80 if npc.get("anima") else 0))
        # +14: whether it is drawn. An event whose active page has no graphic
        # is in the table hidden, to appear when another page wins.
        out.append(1 if npc["visible"] else 0)
        # +15: the passage bits its tile imposes on the cell, or $FF: see
        # `rm2k.pasabilidad_del_tile`. The refresh redoes both.
        out.append(0xFF if npc["tile_pasa"] is None else npc["tile_pasa"])
    assert len(out) == NPC_STRIDE * len(table)
    return bytes(out)


def puntero(destino):
    """The three bytes of a symbolic pointer, for `.byte`."""
    return "<(%s), >(%s), ^(%s)" % (destino, destino, destino)


def npc_poses_asm(numero, animados, indice_global):
    """The pointers to the twelve poses of each character that changes pose.

    One entry per animated character —`k`, the same index the NPC's row
    carries in +9 and the actor in its table— and in each one twelve 24-bit
    pointers to its poses, `pose_N`. They are symbolic because they point to
    blocks the linker places, like the pages' ones; two equal poses are the
    same block.
    """
    out = [".bloque %d" % (3 * SPRITE_POSES * max(1, len(animados))),
           "npc_poses_%d:" % numero]
    for par in animados:
        for pose in range(SPRITE_POSES):
            out.append("    .byte " + puntero(indice_global[par][pose]))
    if not animados:
        out.append("    .byte $00")     # a label can't be left empty
    return "\n".join(out)


def actor_table_asm(numero, actores, animados, indice_global):
    """The leader candidates: id, palette, and the pointer to each of their
    poses.

    ACTOR_BYTES per actor. The ROM walks the table looking for the id of the
    party's first; there are two or three entries, so searching linearly is
    cheaper than indexing by id, which would take 256 gaps. An actor without
    a graphic carries twelve pointers at $FFFFFF, which is the sentinel
    `place_hero` looks at.
    """
    out = [".bloque %d" % (ACTOR_BYTES * max(1, len(actores))),
           "actor_table_%d:" % numero]
    for actor, paleta, k, colores in actores:
        out.append("    .byte $%02X, $%02X" % (actor & 0xFF, paleta & 0x07))
        # Its fifteen colors, in the order its poses index them. An actor
        # without a graphic carries them at zero and the ROM doesn't upload
        # them: it isn't drawn.
        palabras = list(colores) + [0] * (OBJ_COLORS - len(colores))
        out.append("    .byte " + ",".join(
            "$%02X,$%02X" % (w & 0xFF, w >> 8) for w in palabras))
        for pose in range(SPRITE_POSES):
            if k is None:
                out.append("    .byte $FF, $FF, $FF")
            else:
                out.append("    .byte " + puntero(
                    indice_global[animados[k]][pose]))
    if not actores:
        out.append("    .byte $00")
    return "\n".join(out)


def parser_de_flags():
    """The converter's flags. Separate from `main` for whoever needs to read a
    command line without converting anything."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Mandatory, but without `required`: `casos_de_prueba` reads the flags of
    # each `--caso` again with this same parser, and there it doesn't go.
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
    parser.add_argument("--relleno-de-textos", type=int, default=0,
                        help="dead texts after the item ones, so that\n"
                             "the battle's indices go past 255 without\n"
                             "building a twenty-nine-map cartridge. It\n"
                             "doesn't change a pixel, and that is why they\n"
                             "don't go first: item k's name is text 3k")
    parser.add_argument("--sin-titulo", action="store_true",
                        help="without the game's title screen and its "
                             "start and load menu: the ROM boots straight "
                             "into the map. It is what the regression "
                             "suite's cartridges ask for: the title screen "
                             "would add frames to the boot, and the cases "
                             "compare frames counted from reset.")
    parser.add_argument("--aire-de-medida", type=float, metavar="HEADROOM",
                        help="the same headroom for every song, instead of "
                             "the volume ceiling table: it is what "
                             "`tools/audio/techos.py` builds the ROM where it "
                             "measures each song's peak with. See "
                             "`leer_techos` in tools/audio/snes_music.py")
    parser.add_argument("--hp-de-enemigos", action="store_true",
                        help="the battle shows the enemies' HP, which RM2k "
                             "never shows: for debugging. It is asked for by "
                             "`[debug] enemy_hp` of the project file")
    parser.add_argument("--sin-timer", action="store_true",
                        help="the timer digits —eleven glyphs of the System "
                             "image at the end of the sprite bank, which "
                             "share a palette with a character— only in the "
                             "maps where a case that uses them runs, and not "
                             "in all. It is what the suite's cartridges ask "
                             "for: see `args.timer_en`")
    parser.add_argument("--grafico-de-prueba", nargs=2, action="append",
                        default=None, metavar=("CHARSET", "INDEX"),
                        help="puts this graphic in the sprite bank of the\n"
                             "maps where some case runs, so that the test\n"
                             "page can change someone's graphic with\n"
                             "command 34 or with ChangeSpriteAssociation.\n"
                             "It can be repeated. No page that compiles\n"
                             "today changes graphic, so without this\n"
                             "nothing runs that path")
    parser.add_argument("--encuentros-de-prueba", type=int, default=None,
                        metavar="STEPS",
                        help="every how many steps there is a random "
                             "encounter, for every map of the cartridge. "
                             "Without this the game tree's value applies, "
                             "which goes from 25 to 85 steps; 0 turns them off")
    parser.add_argument("--heroe-encima", action="store_true",
                        help="the hero at object priority 2, above the "
                             "layer that should cover it. It is the only "
                             "way to exercise it: the game's only above "
                             "event never gets to step on the upper layer")
    parser.add_argument("--grupo", nargs="+", type=int, default=None,
                        metavar="ACTOR",
                        help="the party it starts with, by actor ids. The "
                             "hero's graphic is the first one's, which is how "
                             "RM2k decides it. By default, the database's: "
                             "this game starts with actor 10, DummyHero, whose "
                             "sprite is an empty cell on purpose")
    parser.add_argument("--comandos-de-prueba", default=None,
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
    parser.add_argument("--mapas", nargs="+", type=int, metavar="ID",
                        help="other maps to put in the same ROM. The one "
                             "from --map-id goes first in the table")
    parser.add_argument("--inicial", type=int, default=0, metavar="N",
                        help="which table index the ROM boots at. It serves "
                             "to test a map other than the first, which is "
                             "the only case where the record's offset isn't "
                             "zero")
    return parser


def main():
    project.from_command_line()
    parser = parser_de_flags()
    argv, tramos = partir_en_casos(sys.argv[1:])
    args = parser.parse_args(argv)
    if args.map_id is None:
        parser.error("--map-id is missing, the boot map")
    environment.from_arguments(args, "game_dir", "rtp_dir", "soundfont",
                               "cache")
    args.game_dir = environment.game()
    args.casos = casos_de_prueba(parser, args, tramos)
    orden = orden_de_mapas(args)
    if not 0 <= args.inicial < len(orden):
        sys.exit("--inicial %d but there are %d maps" % (args.inicial, len(orden)))
    for caso in args.casos:
        caso.mapa = mapa_del_caso(caso, orden, args.inicial)
    de_archivo = comandos_de_casos(args)
    # Which maps carry the timer digits, which cost a sprite palette.
    # Normally, all: it is what the game asks for, where the countdown starts
    # in one map and is seen in the following ones. With `--sin-timer`, the
    # maps where a case that touches it runs: until step 9e one was enough for
    # every map of the cartridge to carry them, and in the single cartridge of
    # 9f that took the palette away from every map —measured, fifteen goldens
    # moved—. A map without digits doesn't draw them: `TIMER_BASE` at zero,
    # see `timer_oam`.
    args.timer_en = set(orden) if not args.sin_timer else {
        caso.mapa for caso in args.casos
        if any(cmd.code == eventos.TIMER_OPERATION for cmd in caso.comandos)}

    renderer = Renderer(args.game_dir)

    # The hero's graphic comes from the party, not from here. In RM2k the
    # first of the list gives it, and this game starts with actor 10
    # —'DummyHero', which is Chubby2[2]—. Until now there was a hand-set
    # default that gave Future1[0], that is another character's sprite.
    # --charset stays to force it by hand when needed.
    grupo = args.grupo if args.grupo else renderer.database.party
    if args.charset is None:
        args.charset, indice = renderer.database.leader(grupo)
        if args.charset_index is None:
            args.charset_index = indice
    if args.charset_index is None:
        args.charset_index = 0

    # The leader candidates are computed with all the ROM's maps together,
    # because the party is global state: a page of map A can add someone who
    # then walks around map B.
    args_game_dir[0] = args.game_dir
    todos = orden_de_mapas(args)
    # **The indices go before anything that compiles a page**, and
    # `lideres_posibles` compiles pages. They were after, and the price was
    # concrete: without `indexar_variables`, no `ControlVars` compiles, so
    # `RaceController1` of map 49 —which starts with a `PlayBGM` and goes on
    # with two `ControlVars`— didn't compile **in that pass** and did in the
    # real one. The actors it adds to the party were lost: `CarRED` didn't go
    # into the map's actor table and the chase's hero was drawn **with no
    # graphic**, that is the car wasn't visible. It is the same hole that was
    # already noted for the page counts, in another place.
    #
    # The variables of the whole game, with their slot.
    extra = eventos.variables_de_comandos(de_archivo)
    if len(args.casos) > 1:
        # The one that picks the case: see `eventos.VARIABLE_DE_CASO`. With a
        # single one it isn't needed, and that way that cartridge comes out
        # the same as before `--caso`.
        extra.add(eventos.VARIABLE_DE_CASO)
    eventos.indexar_variables(args.game_dir, extra)
    # And the battle animations, which `ShowBattleAnimation` compiles with its
    # timeline inside: see OP_ANIMATION.
    eventos.indexar_animaciones(args.game_dir)
    # And the common events, which `CallEvent` compiles in place.
    eventos.indexar_comunes(args.game_dir)
    eventos.indexar_audio_de_batalla(args.game_dir)
    # And the inn terms, which `ShowInn` builds its greeting with.
    eventos.indexar_terminos(args.game_dir)
    # And the equipment and skills of each actor of the LDB: it is what the
    # two actor branches with two operands answer. **Before
    # `lideres_posibles`**, which compiles pages: see its comment.
    eventos.indexar_actores(args.game_dir)
    # And the (actor, skill) pairs of the whole game, with those of the test
    # pages: it is the operand of `ChangeSkills` and of the branch that asks
    # whether it knows one, so it goes before compiling anything, same as the
    # variables.
    eventos.indexar_habilidades(
        args.game_dir, eventos.pares_de_habilidad_de_comandos(de_archivo))
    args.lideres = lideres_posibles(renderer, todos, grupo)
    # And those of the party each test page continues with, behind: the test
    # can start with it in any map of the cartridge.
    for caso in args.casos:
        de_prueba = grupo_de_la_pagina(caso, grupo)
        if de_prueba:
            for actor in lideres_posibles(renderer, todos, de_prueba):
                if actor not in args.lideres:
                    args.lideres.append(actor)
    # If some map sets rain, all of them carry the drops: see `hay_lluvia`.
    args.con_lluvia = hay_lluvia(todos, de_archivo)
    # How many maps of this ROM each character appears in. The palette split
    # uses it to choose who can lose a color without breaking anything: the
    # pose bank is **the whole ROM's**, so a character that is in two maps has
    # to be quantized the same in both. Quantizing it differently doesn't give
    # an ugly image but a `sys.exit` when emitting, which is what happened the
    # first time this was written: `Future1:4` dropped in one map and not in
    # the other.
    args.mapas_por_personaje = mapas_por_personaje(renderer, todos,
                                                   args.game_dir)
    # The `ShowPicture` picture, one per ROM: see `eventos.Imagenes`. The first
    # map of the table that shows it keeps it, which is the order `convertir`
    # walks them in.
    args.imagenes = eventos.Imagenes(args.game_dir)
    args.imagenes.mapa = None
    # And the slots `ChangeSpriteAssociation` reserves in the graphics table
    # of **all** maps, for the same reason as the picture: the graphic it gives
    # an actor crosses the teleport, so its index has to mean the same in both
    # maps. See `eventos.asociaciones_de`.
    #
    # The test pages' ones come in through the same door: if they went by
    # `--grafico-de-prueba` they would have an index only in the maps where a
    # case runs, and what the command does —crossing the teleport— couldn't
    # be tested.
    args.asociaciones = eventos.asociaciones_de(
        [lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % m))
         for m in todos], de_archivo)

    precalcular_capas(renderer, todos, args)
    mapas = [convertir(renderer, map_id, args) for map_id in todos]
    # The maps whose upper layer started higher than the window's palette used
    # to be reconverted here, to squeeze their background below it. With the
    # window in palette 0 there is nothing to squeeze: each map's background
    # starts at `CGRAM_RESERVADAS` and reaches up to its own upper layer,
    # without depending on what the other maps of the ROM need.
    # Teleports are resolved when all the maps are there: one can lead to any
    # other, so the destination index isn't known until the end.
    indices = {mapa["id"]: numero for numero, mapa in enumerate(mapas)}

    # The blocks the map's `TileSubstitution`s are going to need, built
    # **before** compiling any page: see `Sustituciones`. A map without that
    # command builds nothing and doesn't grow a byte, which is the case of the
    # game's 328 maps as of today.
    for mapa in mapas:
        chipset = renderer.database.chipsets[mapa["game_map"].chipset_id]
        mapa["sustituciones"] = Sustituciones(
            mapa, build_passability(chipset), chipset)
        # It hangs from the map so it reaches `eventos.Eventos`, which is what
        # the compiler already passes around.
        mapa["game_map"].sustituciones = mapa["sustituciones"]
        triples = triples_de_sustitucion(mapa["game_map"], args.casos,
                                         mapa["id"])
        for faltante in mapa["sustituciones"].cerrar(triples):
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
            # independent. See `Sustituciones._hornea`.
            print("  map %d: TileSubstitution %d -> %d on the %s layer: the "
                  "block that would be needed can't be built. Either the new "
                  "tile isn't drawn in any cell of the map, or one of the two "
                  "is an upper tile without 'Above' and is baked into the "
                  "background. The page doesn't compile."
                  % (mapa["id"], faltante[1], faltante[2],
                     "upper" if faltante[0] else "lower"))

    # The text block belongs to the whole ROM and is built while the pages
    # are compiled: each `ShowMessage` leaves its text here and takes an
    # offset, which is what goes in the bytecode.
    mensajes = eventos.Mensajes(paso=eventos.MENSAJES_PASO)
    # The songs the pages' PlayBGMs ask for, numbered in the order they
    # appear. The ROM carries a single one —see `Temas`— and picks it further
    # down, when all are compiled and it is known which ones are asked for.
    temas = eventos.Temas()
    # And the troops the EnemyEncounters ask for. It doesn't number anything
    # —the bytecode carries the RM2k id— so it only says which enemy tables
    # have to be emitted. See `eventos.Tropas`.
    tropas = eventos.Tropas()
    # The test pages' texts go **first**, before all the maps, and that isn't
    # aesthetic: that way their offset doesn't depend on how many texts the
    # map the ROM boots in brings nor on the order they are compiled in —the
    # first is 0—. They are stored here and the page's compilation, further
    # down, finds them stored, because the block deduplicates by content.
    for cmd, extra_lineas in eventos.agrupar(de_archivo):
        if cmd.code == eventos.SHOW_MESSAGE:
            mensajes.agregar([cmd.string] + extra_lineas)
    # The test pages already compiled, per case: see the second round.
    de_prueba = {}

    for mapa in mapas:
        # The automatic events: their pages with the conditions, and the code
        # of the ones that can be run, all together in a single block.
        # One graphics registry per map: command 34 carries the index and the
        # map's `ruta_grafico` table resolves it. See `eventos.Graficos`.
        graficos = eventos.Graficos(args.asociaciones)
        temas.mapa = mapas.index(mapa)      # for its audio package
        paginas = eventos.paginas_del_mapa(mapa["game_map"], indices.get,
                                           mensajes, temas, graficos,
                                           args.imagenes, tropas)
        temas.mapa = None
        # One interpreter per event with some parallel page that compiles. The
        # ROM carries them in a fixed-cap list and **doesn't warn** if it goes
        # over —the extra ones wouldn't run and nothing would say so—, so the
        # stop goes here.
        con_paralela = {p["evento"] for p in paginas
                        if p["trigger"] == eventos.TRIGGER_PARALELO
                        and p["codigo"]}
        if len(con_paralela) > PARALELO_MAX:
            sys.exit("map %d has %d events with a parallel page and %d "
                     "fit: see PARALELO_MAX"
                     % (mapa["id"], len(con_paralela), PARALELO_MAX))
        if con_paralela:
            print("  map %d: %d event(s) with a parallel page"
                  % (mapa["id"], len(con_paralela)))
        if args.grafico_de_prueba and mapa["id"] in mapas_de_prueba(args):
            for charset, index in graficos_de_prueba(args.grafico_de_prueba):
                graficos.indice(charset, index)
        # **Only the map that took its tiles can show the picture.** The sprite
        # bank belongs to each map, so from another one the six objects would
        # read whatever was in those tiles. It doesn't happen today —the "1
        # year earlier" picture is shown by a single page— and that is why this
        # stops instead of choosing: the day two maps show the same one, it
        # has to be decided whether its tiles go in both, and the converter
        # can't make that decision alone.
        if (args.imagenes.nombre is not None
                and mapa["id"] != args.imagenes.mapa):
            for pagina in paginas:
                codigo = pagina["codigo"]
                if codigo and any(codigo[i] == eventos.OP_PICTURE
                                  for i, _c in eventos.recorrer_codigo(codigo)):
                    sys.exit(
                        "map %d: shows the picture %r and its tiles ended up in "
                        "map %d; the ROM carries it in a single one. See "
                        "`cartel_de_imagen`."
                        % (mapa["id"], args.imagenes.nombre,
                           args.imagenes.mapa))
        if graficos.pares != mapa["graficos_de_ruta"]:
            # The two passes compiled different things. It can't happen —both
            # use `paginas_del_mapa` with the same text block— and if it did,
            # the bytecode would end up pointing at the wrong table without
            # anything saying so.
            sys.exit("map %d: the two passes numbered the route graphics "
                     "differently: %s against %s"
                     % (mapa["id"], graficos.pares, mapa["graficos_de_ruta"]))
        # The pages of the cases that run in this map, compiled with its
        # context even though they will live in the boot map: see
        # `mapa_del_caso`. They are put there in the second round, when all
        # are done.
        for k, caso in enumerate(args.casos):
            if caso.mapa == mapa["id"]:
                de_prueba[k] = pagina_de_caso(caso, mapa, temas, graficos,
                                              mensajes, indices,
                                              args.imagenes)
        mapa["paginas"] = paginas
        # And which maps outside the ROM the ones that don't compile point to.
        #
        # A `Teleport` to a map that didn't make it cuts the whole page, and a
        # page that doesn't compile does **nothing**: neither the teleport nor
        # what came before. `evento` has always said so in its comment, but
        # the count above doesn't tell this reason apart from the others a
        # page falls out for, and it is the only one that is fixed from
        # outside —adding the map— and not by touching the compiler. That is
        # how the elevator page of map 2 was overlooked, which was seen
        # opening and led nowhere because it ends up jumping to map 3.
        afuera_de, cuantas = set(), 0
        for pagina in paginas:
            if pagina["codigo"] or pagina["trigger"] not in eventos.TRIGGERS \
                    or pagina.get("prueba"):
                continue        # the test page doesn't come from the game
            evento = mapa["game_map"].events[pagina["evento"]]
            faltan = {cmd.parameters[0]
                      for cmd in evento.pages[pagina["pagina"]].commands
                      if cmd.code == eventos.TELEPORT and cmd.parameters
                      and indices.get(cmd.parameters[0]) is None}
            if faltan:
                afuera_de |= faltan
                cuantas += 1
        if afuera_de:
            print("  map %d: %d of those %s because of a teleport to a map "
                  "that didn't make it into the ROM: %s"
                  % (mapa["id"], cuantas,
                     "doesn't compile" if cuantas == 1 else "don't compile",
                     ", ".join(str(m) for m in sorted(afuera_de))))
        # Debts are warned about. A page that is accepted without doing
        # everything it asks for is a difference from the original game, and
        # keeping quiet about it is how it becomes invisible: here the command
        # and what is lost are named.
        deudas = set()
        for evento in mapa["game_map"].events:
            for page in evento.pages:
                if page.trigger != eventos.TRIGGER_AUTOMATICO:
                    continue
                # With the same text block as above: if it were None here, a
                # page with a text box wouldn't compile and its debt —a
                # PlayBGM, say— would go unwarned even though the ROM does run
                # it. Adding a text that is already there again doesn't grow
                # the block: the key is the content.
                if eventos.compilar_pagina(page, indices.get,
                                           mensajes) is None:
                    continue
                deudas |= set(eventos.deudas_de_la_pagina(page,
                                                          args.imagenes))
        for codigo_cmd in sorted(deudas):
            print("  map %d: WARNING, a page uses %s and the ROM doesn't do it; "
                  "see ACEPTADOS_SIN_HACER in tools/port/eventos.py"
                  % (mapa["id"], event_codes.EVENT_CODES.get(codigo_cmd,
                                                             codigo_cmd)))


    # The second round: with the pages of all the cases compiled, they are
    # put in the boot map and each map's block is built.
    for mapa in mapas:
        paginas = mapa["paginas"]
        if args.casos and mapa is mapas[args.inicial]:
            # The test pages, only in the map the ROM boots in. They don't come
            # from the game but from `rom/pruebas/casos/`: they exist because
            # there are interpreter paths no page of the game that compiles
            # exercises —the first was a wait—.
            #
            # It goes at **index 0**, that of the empty event `convertir` put
            # at the start of the map: the ROM walks the events from lowest to
            # highest, and this page has to run before the game's. Until
            # 2026-09-17 it went at the first free index, at the end.
            #
            # **One page per case**, and page k asks for `VARIABLE_DE_CASO` to
            # be at least k: see its comment. Page 0 asks for nothing, so a
            # single-case cartridge is the usual one.
            paginas = paginas + [{
                "evento": 0, "pagina": k, "prueba": True,
                "trigger": eventos.TRIGGER_AUTOMATICO,
                "switch_a": 0, "switch_b": 0, "actor": 0,
                "variable": ((eventos.ranura_de_variable(
                    eventos.VARIABLE_DE_CASO),
                    eventos.COMPARAR_AL_MENOS, k) if k else None),
                "item": 0, "capa": 0,
                "frecuencia": eventos.RUTA_FRECUENCIA, "velocidad": 4,
                "codigo": de_prueba[k]} for k in range(len(args.casos))] + [{
                # And the one that turns it off: it asks for
                # `SWITCH_DE_PRUEBA` and has no code, so as soon as it wins,
                # the invented event no longer has an automatic page to run and
                # the first one doesn't repeat.
                "evento": 0, "pagina": len(args.casos), "prueba": True,
                "trigger": eventos.TRIGGER_AUTOMATICO,
                "switch_a": eventos.SWITCH_DE_PRUEBA, "switch_b": 0,
                "actor": 0, "variable": None, "item": 0, "capa": 0,
                "frecuencia": eventos.RUTA_FRECUENCIA, "velocidad": 4,
                "codigo": b""}]
        codigo = bytearray()
        for pagina in paginas:
            pagina["offset"] = len(codigo)
            if pagina["codigo"]:
                codigo += pagina["codigo"]
            # And the commands of the own route, behind, one byte per command.
            propia = pagina.get("ruta_propia")
            if propia:
                pagina["ruta_offset"] = len(codigo)
                codigo += bytes(propia["ordenes"])
        mapa["paginas"] = paginas
        # What each page of the events that change graphic draws, already as
        # OAM wants it: it is what the ROM copies to the NPC's row when the
        # active page changes. See `tabla_de_paginas`, +20.
        for pagina in paginas:
            sigue = pagina["evento"] in mapa["cambian"]
            if not sigue and pagina["evento"] not in mapa["aparecen"]:
                continue
            grafico = pagina.get("grafico")
            if grafico is None \
                    or grafico[:2] in mapa["afuera"].get(pagina["evento"], ()):
                continue
            if not sigue:
                # The one that only appears carries no tile or attributes: its
                # own point to its slot of twelve poses and the ROM doesn't
                # touch them. The pose goes —with bit 7, which is "this page
                # draws something"— and what its tile imposes on the cell.
                pagina["oam"] = (0, 0, grafico[2] | 0x80,
                                 0xFF if pagina.get("tile_pasa") is None
                                 else pagina["tile_pasa"])
                continue
            block, slot = mapa["where"][grafico]
            tile = block_tile(block)
            prioridad = (OBJ_PRIORITY_ABOVE
                         if pagina["capa"] == rm2k.LAYER_ABOVE
                         else OBJ_PRIORITY)
            pagina["oam"] = (tile & 0xFF,
                             prioridad | ((slot & 0x07) << 1) | ((tile >> 8) & 1),
                             grafico[2] | 0x80,
                             0xFF if pagina.get("tile_pasa") is None
                             else pagina["tile_pasa"])
        mapa["evcodigo"] = bytes(codigo)
        # The ROM's substitution table has a fixed cap and **doesn't warn** if
        # it goes over: the pairs that don't fit wouldn't be applied and the
        # map would draw too much. How many entries it can end up having is
        # known here, and it is the number of distinct blocks some substitution
        # of the map uses as a key, because a key is never overwritten: the
        # second round changes its value. See `op_tile_sub` in
        # tools/runtime/interprete_mapa.s.
        claves = len(mapa["sustituciones"].claves)
        if claves > SUB_MAX:
            sys.exit("map %d substitutes %d distinct blocks and the RAM "
                     "table carries %d: see SUB_MAX"
                     % (mapa["id"], claves, SUB_MAX))
        # How many distinct events this map can end up sending walking. The
        # ROM has RUTA_EV_MAX slots and a route that finds no room is
        # discarded **without saying anything**: the NPC stays still and, if
        # the golden is taken like that, the test defends the error. With this
        # game's data the worst map uses two, so the check bothers nobody; it
        # is there so that a future change doesn't throw them away silently.
        #
        # The pages that **run** here: the map's and those of the cases that
        # jump to it, which live in the boot one. See `mapa_del_caso`.
        corren_aca = [p["codigo"] for p in paginas
                      if p["codigo"] and not p.get("prueba")]
        corren_aca += [de_prueba[k] for k, caso in enumerate(args.casos)
                       if caso.mapa == mapa["id"]]
        blancos = {c[i + 1] for codigo in corren_aca
                   for i, c in recorrer_codigo(codigo)
                   if c[i] == eventos.OP_ROUTE and c[i + 1]}
        # And that nobody flashes someone who shares a graphic with another.
        # On the console the flash is done on the character's palette, so two
        # that share a graphic would flash together. `eventos.py` already
        # rejects the case of two events; here the one it can't see there is
        # covered, which is the hero's: which graphic it has depends on the
        # party, and the converter knows that and the compiler doesn't.
        #
        # `separar_del_heroe` already avoids this in the maps whose pages flash
        # the hero. This stays for what that one doesn't see: a `FlashSprite`
        # that arrives inside a common event, which is compiled in place from
        # any `CallEvent` and isn't in the map's pages.
        graficos = collections.Counter(
            (npc["charset"], npc["index"])
            for npc in rm2k.collect_npcs(mapa["game_map"]))
        for actor in args.lideres:
            a = renderer.database.actors[actor]
            graficos[(a.charset, a.charset_index)] += 1
        for codigo in corren_aca:
            for i, c in recorrer_codigo(codigo):
                if c[i] != eventos.OP_FLASH or c[i + 1] != 0:
                    continue
                for actor in args.lideres:
                    a = renderer.database.actors[actor]
                    if graficos[(a.charset, a.charset_index)] > 1:
                        raise SystemExit(
                            "map %d: a page makes the hero flash, and "
                            "actor %d is drawn with %s[%d], which an NPC of "
                            "the map also uses. On the console they share a "
                            "palette and both would flash"
                            % (mapa["id"], actor, a.charset, a.charset_index))

        if len(blancos) > RUTA_EV_MAX:
            raise SystemExit(
                "map %d: its pages send %d distinct events walking and "
                "the ROM has %d route slots"
                % (mapa["id"], len(blancos), RUTA_EV_MAX))
        corribles = sum(1 for p in paginas if p["codigo"])
        if paginas:
            print("  map %d: %d automatic event page(s), %d runnable"
                  % (mapa["id"], len(paginas), corribles))

    if not 0 <= args.inicial < len(mapas):
        sys.exit("--inicial %d but there are %d maps" % (args.inicial, len(mapas)))
    from port import ventana as ventana_mod
    skin = ventana_mod.skin(args.game_dir, renderer.database.system_name)
    font_id = renderer.database.font_id
    ventana_datos = convert_ventana(skin, font_id)
    ventana_datos["fuente"] = fuente_bytes(font_id)
    ventana_datos["mensajes"] = mensajes.bytes()
    print("  message window: %d fixed tiles + %d of text, %d colors; "
          "font %d B, %d text box(es) in %d B"
          % (len(ventana_datos["tiles"]) // 32,
             len(ventana_datos["fondo"]) // 32,
             sum(1 for w in ventana_datos["cram"] if w),
             len(ventana_datos["fuente"]), len(mensajes.textos),
             len(ventana_datos["mensajes"])))
    # The slots screen goes in every ROM: the save point opens it from inside
    # the game, and "Resume the Story" from the title when there is one. It is
    # drawn with the same font and the same skin as the message window, and
    # lives in the title's VRAM, where there is no map.
    # The actors that can be in the party when saving, to have their face and
    # their name in the cartridge: the starting ones and all the ones some
    # `ChangePartyMembers` of these maps adds, whether their pages compile or
    # not. It is a superset on purpose: one face too many costs 36 tiles and
    # one too few leaves a hole in the menu.
    miembros = miembros_posibles(todos, grupo, de_archivo)
    # And the items that can be in the inventory, to carry their name and
    # their description: see "la pantalla de ítems" in menus.py.
    items_rom = items_posibles(todos, miembros, renderer.database,
                               de_archivo)
    # With the letters of the medicines, which the actor choice writes with
    # the bank's glyphs: see `OBJETIVO_VENTANAS`.
    letras_medicinas = "".join(
        renderer.database.items[n].name for n in items_rom
        if renderer.database.items[n].type == lcf.ITEM_TYPE_MEDICINE)
    (ranura_tiles, ranura_paletas, ranura_cabs, ranura_filas, ranura_caras,
     ranura_menu) = menus_mod.pantalla_ranuras(
        skin, renderer.database, RANURAS, renderer.database.font_id,
        miembros, args.game_dir, letras_medicinas)
    objetivo = menus_mod.marcos(
        skin, 0, menus_mod.capas_objetivo(skin, renderer.database,
                                           renderer.database.font_id),
        menus_mod.OBJETIVO_CGRAM,
        menus_mod.OBJETIVO_CGRAM + menus_mod.OBJETIVO_COLORES_MAX)
    _controlar_objetivo(len(objetivo[0]))
    items_tiles, items_paletas, items_glifos = menus_mod.pantalla_items(
        skin, renderer.database.font_id)
    # The item and equipment windows share tiles and colors: see
    # `menus.marcos`.
    items_marco = menus_mod.marcos(
        skin, items_marco_primero(len(items_tiles)),
        [menus_mod.capas_items(skin), pantallas_mod.capas_equipo(skin)])
    _controlar_marco_de_items(len(items_tiles), len(items_marco[0]))
    # The shop's, with their own tiles and colors: see
    # `pantallas.TI_VENTANAS`.
    tienda_marco = menus_mod.marcos(
        skin, 0, pantallas_mod.capas_tienda(skin),
        menus_mod.ITEM_MARCO_CGRAM, menus_mod.OBJETIVO_CGRAM)
    _controlar_tienda(len(tienda_marco[0]))
    # The End Game screen's tiles go where the slots' do, so what is checked
    # is the same.
    fin = fin_mod.convertir(skin, renderer.database, renderer.database.font_id)
    _controlar_ranuras(len(fin[0]))
    ranuras_datos = {"tiles": ranura_tiles, "paletas": ranura_paletas,
                     "cabeceras": ranura_cabs, "filas": ranura_filas,
                     "caras": ranura_caras,
                     "menu": ranura_menu, "items": items_rom,
                     "db": renderer.database, "actores": miembros,
                     "relleno_textos": args.relleno_de_textos,
                     "items_db": renderer.database.items,
                     "items_tiles": items_tiles,
                     "items_paletas": items_paletas,
                     "items_glifos": items_glifos,
                     "items_marco": items_marco, "fin": fin,
                     "tienda_marco": tienda_marco,
                     "objetivo": objetivo}
    _controlar_ranuras(len(ranura_tiles))
    _controlar_repartos()
    print("  slots screen: %d, %d 4bpp tiles (%d B) + %d palettes, "
          "%d B of cells; %d actors with a face: %s"
          % (RANURAS, len(ranura_tiles), len(ranura_tiles) * 32,
             len(ranura_paletas),
             (len(ranura_cabs) * len(ranura_cabs[0])
              + RANURAS * 4 * len(ranura_filas[0][0][0])) * 2,
             len(ranura_caras),
             ", ".join("%d %s" % (a, renderer.database.actors[a].name)
                       for a in sorted(ranura_caras)) or "none"))
    titulo_datos = None
    if not args.sin_titulo:
        from PIL import Image
        nombre = renderer.database.title_name
        imagen = Image.open(os.path.join(args.game_dir, "Title",
                                         nombre + ".png"))
        textos = titulo_mod.opciones(renderer.database)
        menu_tiles, menu_paleta, menu_mapas = titulo_mod.menu(
            skin, textos, renderer.database.font_id)
        # The image, compressed like the Game Over one, and with the menu's
        # colors below its own in the same stream: the whole CGRAM at once,
        # the menu's palette at the bottom because a 4-bit BG only reaches
        # those. The tiles' indices already come shifted from
        # `paleta.convertir`.
        debajo = list(menu_paleta)
        debajo += [(0, 0, 0)] * (constantes.MENU_CGRAM - len(debajo))
        pantalla = pantalla_completa.comprimida(
            imagen, constantes.MENU_CGRAM, constantes.COLORES, debajo)
        titulo_datos = {"pantalla": pantalla,
                        "menu_tiles": menu_tiles, "menu_paleta": menu_paleta,
                        "menu_tilemaps": menu_mapas}
        print("  title screen %r: %d 8bpp tiles + %d colors, "
              "%d B in an LZ2 stream of %d B"
              % (nombre, pantalla["tiles"],
                 pantalla["colores"] - len(debajo), pantalla["crudo"],
                 len(pantalla["flujo"])))
        print("    menu (%s): %d 4bpp tiles (%d B) + %d colors, %d tilemap(s)"
              % (", ".join(repr(t) for t in textos), len(menu_tiles),
                 len(menu_tiles) * 32, len(menu_paleta), len(menu_mapas)))
    # The Game Over screen: the image the LDB's `System` names, in the game's
    # or the RTP's `GameOver/` —as RM2k looks for it—, compressed. It goes in
    # every ROM that finds it: any cartridge can lose a battle or run a
    # `GameOver`. See tools/port/pantalla_completa.py.
    game_over_datos = None
    ruta = find_resource([args.game_dir, resources.RTP_DIR], "GameOver",
                         renderer.database.gameover_name)
    if renderer.database.gameover_name and ruta:
        from PIL import Image
        game_over_datos = pantalla_completa.comprimida(Image.open(ruta))
        print("  Game Over screen %r: %d 8bpp tiles + %d colors, "
              "%d B in an LZ2 stream of %d B"
              % (os.path.basename(ruta), game_over_datos["tiles"],
                 game_over_datos["colores"], game_over_datos["crudo"],
                 len(game_over_datos["flujo"])))
    # The battle animations the already emitted bytecode shows: their
    # prerendered frames go to the cartridge and the ROM uploads them by DMA.
    animaciones = animaciones_de_la_rom(mapas, renderer)
    for numero in sorted(animaciones):
        datos = animacion_mod.informe(numero, animaciones[numero])
        print("  animation %d: %d frames of %dx%d, shrunk from %dx%d to %d%%,"
              " %d colors, %d B"
              % (datos["animacion"], datos["cuadros"], datos["caja"][0],
                 datos["caja"][1], datos["original"][0], datos["original"][1],
                 datos["porciento"], datos["colores"], datos["bytes"]))
    # The random encounters of each map, which ask for their troops. They go
    # **before** those of the test pages, which go at the end: that way the
    # cartridge's troops are numbered by the maps and the invented one goes
    # last, which is the same `temas_de_la_rom` does with the map's song.
    # Asking for it first always gave it index 0, and with that no case of the
    # suite exercised that `escena_tropa_fondo` and `tropa_id` are really
    # indexed. That is why `pagina_de_caso` compiles without `Tropas`.
    encuentros = encuentros_de_la_rom(mapas, renderer.tree,
                                      args.encuentros_de_prueba, tropas)
    cuantas = sum(z["tropa_n"] for z in encuentros["zonas"])
    if encuentros["registros"]:
        print("  random encounters: %d map(s), %d zone(s), %d troop(s)"
              % (len(encuentros["registros"]), len(encuentros["zonas"]),
                 cuantas))
    for cmd in de_archivo:
        if cmd.code == eventos.ENEMY_ENCOUNTER:
            tropas.pedir(eventos.tropa_de_encuentro(cmd),
                         eventos.fondo_de_encuentro(cmd))
    # The battle's audio, with the indices it already got from `temas` while
    # the pages compiled. It is asked for again only to read them: `Temas`
    # numbers once and returns the same, and what was noted goes to the
    # battle's package and not to any map's.
    audio_batalla = eventos.audio_de_batalla(temas) if tropas.ids else None
    # The backdrops and the battlers the cartridge's battles ask for, each one
    # once: the ROM composes them when each battle starts. See
    # tools/port/escena.py, which is where the reason and the budget are.
    escenas = escena_de_la_rom(renderer.database, tropas, mapas, renderer.tree,
                               encuentros, args.game_dir)
    # The `.msu` is written after the audio, because it also carries the
    # quality sound effects: see `msu_asm`.
    for info in escenas["fondos"]:
        rom_tiles, rom_colores = respaldo_bytes(info)
        msu_tiles, msu_colores = escenas["calidad"][info["numero"]]
        print("  battle backdrop %d %r: %dx%d, %d tiles from CGRAM entry %d; "
              "in the ROM %dx%d at 4bpp and %d colors (%d B), in "
              "the .msu 8bpp and %d colors (%d B)"
              % (info["numero"], info["nombre"], escena_mod.ANCHO,
                 escena_mod.ALTO, escena_mod.TILES, escena_mod.CGRAM_BASE,
                 escena_mod.RESPALDO_ANCHO, escena_mod.RESPALDO_ALTO,
                 len(info["respaldo"]["paleta"]),
                 len(rom_tiles) + len(rom_colores), escena_mod.COLORES,
                 len(msu_tiles) + len(msu_colores)))
    # And the ones that aren't in the ROM, with which one replaces them
    # without MSU-1.
    en_rom = {info["numero"] for info in escenas["fondos"]}
    fuera = [k for k in range(len(escenas["juego"])) if k not in en_rom]
    if fuera and escenas["fondos"]:
        print("  battle backdrops only in the .msu, which without MSU-1 fall "
              "back to %r: %s" % (escenas["fondos"][escenas["respaldo_de"][fuera[0]]]
                                  ["nombre"], ", ".join(
                                      "%d %s" % (k, escenas["juego"][k])
                                      for k in fuera)))
    for info in escenas["battlers"]:
        d = escena_mod.informe_battler(info)
        print("  battler %r: %dx%d, %d B, %d colors of %d"
              % (d["clave"], d["ancho"], d["alto"], d["bytes"], d["quedan"],
                 d["colores"]))
    # The event pages of the troops some battle of the cartridge asks for,
    # with **all** the troops already asked for: the maps', the random
    # encounters' and the test pages'. See `eventos.PaginasDeTropa`, which is
    # also why their messages go to a separate block. With `temas`, because a
    # page's `PlaySound` sounds in the battle's package, which isn't built
    # yet: it is built further down.
    paginas_tropa = eventos.PaginasDeTropa()
    for numero in tropas.ids:
        if numero in renderer.database.troops:
            paginas_tropa.compilar(numero, renderer.database.troops[numero],
                                   temas)
    print("  troop pages: %d of %d in %d distinct body(ies), %d B of "
          "code and %d B in %d message(s)"
          % (paginas_tropa.paginas - paginas_tropa.afuera,
             paginas_tropa.paginas, len(paginas_tropa.donde),
             len(paginas_tropa.cuerpos), len(paginas_tropa.mensajes.datos),
             len(paginas_tropa.mensajes.textos)))
    # The items the enemies of those troops drop can also reach the
    # inventory: see `items_del_botin`.
    ranuras_datos["items"] = sorted(
        set(items_rom) | items_del_botin(renderer.database, tropas.ids))
    comprimidos = comprimir_los_bloques(mapas)
    informe = emit(args.output, mapas, args.inicial, args.heroe_encima, grupo,
                   ventana_datos, titulo_datos, ranuras_datos,
                   args.imagenes.info, animaciones, tropas.ids, audio_batalla,
                   escenas, encuentros, paginas_tropa, comprimidos,
                   hp_de_enemigos=args.hp_de_enemigos,
                   game_over=game_over_datos)
    # Which entries of their palette the timer digits use, one bit per entry
    # and one word per map, in the order of `mapa_tabla`. `subir_timer_pal`
    # uploads **those** again untinted and not the whole palette, because the
    # palette belongs to a character that is tinted. It goes separately and
    # not as a record field because the record is at exactly its 128. The
    # index is the same `index + 1` `digitos_del_timer` painted the glyphs
    # with: the first one that has that color.
    colores_timer = sorted(colores_del_timer(skin))
    mascaras = []
    for mapa in mapas:
        sprite, mascara = mapa["sprite"], 0
        if sprite and sprite[5]:
            paleta = sprite[1][sprite[6]]
            for color in colores_timer:
                mascara |= 1 << (paleta.index(color) + 1)
        mascaras.append(mascara)
    with open(args.output, "a") as handle:
        handle.write('\n.segment "RODATA"\n.bloque %d\ntimer_mascara:\n'
                     '    .word %s\n'
                     % (2 * len(mascaras),
                        ", ".join("$%04X" % m for m in mascaras)))
    if len(args.casos) > 1:
        # Where the harness writes the case number: see `--caso`.
        with open(args.output, "a") as handle:
            handle.write("\nCASO_RANURA = %d\n" % eventos.ranura_de_variable(
                eventos.VARIABLE_DE_CASO))
    print("%d map(s) -> %s, boots at %d (map %d)"
          % (len(mapas), args.output, args.inicial, mapas[args.inicial]["id"]))
    # What the allocator decided, as images: to look at which colors were lost
    # and which palette each cell ended up in without building or running the
    # ROM. They are indexed and their indices are CGRAM entries, so an editor
    # in indexed mode opens them just as `tiles` is going to see them.
    asignador = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                             "asignador")
    os.makedirs(asignador, exist_ok=True)
    for mapa in mapas:
        imagenes = list(mapa["imagenes_fondo"]) + [("encima", mapa["above"][5])]
        for nombre, png in imagenes:
            with open(os.path.join(asignador, "%04d-%s.png"
                                   % (mapa["id"], nombre)), "wb") as handle:
                handle.write(png)
    # And **what it decided to lose**, written down: which color was merged
    # with which in each layer. It goes next to the images because it comes
    # from the same decision, but it is something else: the images are for
    # looking at and this is for reading back and for the diff to warn. What
    # is versioned is in `rom/parches/`, and `just parches --check` compares.
    # See tools/port/parches.py.
    destino_parches = os.path.dirname(os.path.abspath(args.output))
    cuantos, pesan = parches_mod.escribir(destino_parches, mapas)
    print("patches of %d map(s) -> %s (%d B)"
          % (cuantos, parches_mod.EN_BUILD, pesan))
    # And the other decision that is already written down: **at what size
    # each battle animation is drawn**. It comes from the same round above;
    # here it is joined with the name and the sheet the animation has in the
    # LDB, which nobody looks at to draw and are there so that the diff says
    # which one it is about.
    cuantos, pesan = parches_mod.escribir_animaciones(
        destino_parches,
        [dict(animacion_mod.informe(numero, animaciones[numero]),
              nombre=eventos.ANIMACIONES[numero].get("nombre", ""),
              hoja=eventos.ANIMACIONES[numero].get("imagen", ""),
              lado=animacion_mod.CAJA)
         for numero in sorted(animaciones)])
    print("patches of %d animation(s) -> %s (%d B)"
          % (cuantos, parches_mod.EN_BUILD_ANIM, pesan))
    # And **which fifteen colors each battler is reduced to**, which is the
    # decision the scene composed on the console brought: see
    # tools/port/escena.py.
    cuantos, pesan = parches_mod.escribir_battlers(destino_parches,
                                                   escenas["battlers"])
    print("patches of %d battler(s) -> %s (%d B)"
          % (cuantos, parches_mod.EN_BUILD_BAT, pesan))
    # And who asked for each one, which isn't versioned: it is what separates,
    # in the ROM that is played, what belongs to the game from what only
    # exists because of the suite.
    parches_mod.escribir_usos(destino_parches, usos_de_los_parches(
        mapas, renderer.database, renderer.tree))
    if informe:
        print("material compressed and shared between maps:")
        for linea in informe:
            print(linea)

    # The music comes from here and not from a separate recipe.
    # `musicdata.inc` was global state as `mapdata.inc` was, with the
    # aggravating factor that nobody regenerated it: a ROM built for maps 4, 7,
    # 19 and 1 —which have no music— played the song of map 348, which was the
    # last one somebody had generated by hand. Emitting them together is the
    # only thing that guarantees both describe the same ROM.
    #
    # **All the songs** go, sharing a single sample bank, and the one of the
    # map the ROM boots in plays; the others are started by a `PlayBGM`, or
    # by the map that is entered if it brings its own —see `mapa_tema_callar`
    # in tools/runtime/cargar_mapa.s—. What rate each sample ends up at is
    # decided by the ARAM, package by package: see `Banco` in snes_music.py.
    musica = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                          "musicdata.inc")
    pedidos, arranque, tema_titulo, tema_de_mapa, tema_game_over = (
        temas_de_la_rom(
            mapas[args.inicial]["id"], temas, args.game_dir,
            renderer.database.title_music if not args.sin_titulo else None,
            [m["id"] for m in mapas],
            renderer.database.gameover_music if game_over_datos else None))
    # The sound effects, in the order the compiled pages ask for them: the
    # maps are compiled in ROM order, so those of the map where it boots go
    # first —in the demo, the rain and the thunder of the opening—. Only the
    # ones that are in some package: one that isn't in any doesn't sound
    # anywhere —its row of `sonido_tabla` stays at $FF— and building it would
    # cost the music, because `snes_music.copias` counts the cartridge's
    # sound effects. It happens with the route ones of
    # `se_de_ruta_sin_paquete`.
    empaquetados = {n for pide in temas.por_mapa.values()
                    for n in pide["sonidos"]}
    pedidos_se = []
    for nombre, _v, _t, _b in temas.sonidos:
        if nombre not in pedidos_se and nombre in empaquetados:
            pedidos_se.append(nombre)
    # Each map's audio package, in the order of the map table: the songs its
    # pages can start —plus, in the boot one, the one that plays from the
    # start, and in all the map's own— and its sound effects, in the order
    # they appear, which is the priority the ROM uploads them with if they
    # don't all fit. See `paquete_cargar` in tools/runtime/paquete_de_audio.s.
    # They are built **before** the bank, by name, because each sample's
    # budget comes from them: see `snes_music.Banco`.
    paquetes, apartes = [], []
    for i, _mapa in enumerate(mapas):
        pide = temas.por_mapa.get(i, {"temas": [], "sonidos": []})
        suyos = list(pide["temas"])
        if i == args.inicial and arranque != 0xFF and arranque not in suyos:
            suyos.insert(0, arranque)
        # And the map's own song, **in front**: it is the only one on the list
        # that surely plays on entering, so if the ARAM isn't enough for
        # everything it is the last one that has to fall. Without it in the
        # package, its samples would have to be uploaded by `tema_asegurar`
        # when starting it, rebuilding the whole package a second time.
        if tema_de_mapa[i] != 0xFF:
            if tema_de_mapa[i] in suyos:
                suyos.remove(tema_de_mapa[i])
            suyos.insert(0, tema_de_mapa[i])
        # And the exit ones, separate and after the sound effects: the ones
        # the map starts only to leave have no reason to go in with its sound
        # effects. See `Temas.de_salida`. Not the map's own nor the boot one:
        # those play on entering.
        salida = [t for t in temas.de_salida(i)
                  if t in suyos and t != tema_de_mapa[i]
                  and not (i == args.inicial and t == arranque)]
        suyos = [t for t in suyos if t not in salida]
        # And the separate ones, which don't go with the other songs either:
        # their `PlayBGM` uploads them with the package's sound effects. See
        # `temas_aparte`.
        aparte = [t for t in suyos if pedidos[t] in snes_music.temas_aparte().get(
                      _mapa["id"], ()) and t != tema_de_mapa[i]
                  and not (i == args.inicial and t == arranque)]
        suyos = [t for t in suyos if t not in aparte]
        apartes.append(aparte)
        paquetes.append((suyos, list(pide["sonidos"]), salida))
    # And the battle's package, after the maps: the battle song and its sound
    # effects, which the ROM uploads when opening the battle and unloads when
    # closing it. It goes separately and not inside the map's package because
    # the battle song alone fills the ARAM; see `eventos.PAQUETE_BATALLA`.
    pide = temas.por_mapa.get(eventos.PAQUETE_BATALLA)
    if pide:
        paquetes.append((list(pide["temas"]), list(pide["sonidos"]), []))
        apartes.append([])
    nombres_de_paquete = ([str(m["id"]) for m in mapas]
                          + (["pelea"] if pide else []))
    # And the Game Over screen's, last: its song alone and no sound effects.
    # The ROM uploads it with the screen black, before the fade in —see
    # `game_over_negro` in tools/runtime/game_over.s—, and with a package of
    # its own it uploads only that: arriving with `tema_asegurar` would
    # rebuild the whole map package behind it, which is one more second of
    # black. For the allocation it is a one-song package, which doesn't lower
    # anyone's rate: its samples fit alone in the ARAM.
    paquete_game_over = 0xFFFF
    if tema_game_over != 0xFF:
        paquete_game_over = len(paquetes)
        paquetes.append(([tema_game_over], [], []))
        apartes.append([])
        nombres_de_paquete.append("gameover")
    por_nombre = [(nombre, suyos, suyas, salida, aparte)
                  for nombre, (suyos, suyas, salida), aparte
                  in zip(nombres_de_paquete, paquetes, apartes)]
    # And the title screen's, which isn't in the table: `tema_asegurar`
    # uploads its song with the boot map's package behind.
    if tema_titulo != 0xFF:
        suyos, suyas, _salida = paquetes[args.inicial]
        por_nombre.append(("titulo", [tema_titulo] + suyos, suyas))
    herencia = temas_heredados(temas, tema_de_mapa, args.inicial,
                               tema_titulo, nombres_de_paquete,
                               [suyos for suyos, _e, _s in paquetes],
                               apartes, no_se_dan=settings.value(
                                   "music", "jumps_that_never_happen",
                                   kind=list))
    driver, muestras, hechos, banco = snes_music.build_varios(
        pedidos, args.game_dir, pedidos_se, por_nombre, herencia,
        aire_de_medida=args.aire_de_medida)
    # And what `tools/audio/techos.py` needs from each song —how long it lasts
    # and the fingerprint of its mix—, written next to it: the bank can no
    # longer be rebuilt without compiling the pages, which is where the
    # packages come from.
    with open(os.path.join(os.path.dirname(musica), "musica.json"),
              "w") as handle:
        json.dump({"temas": [
            {"nombre": t["nombre"],
             "largo": t["escrituras"][-1][0] + 1 if t["escrituras"] else 0,
             "huella": t.get("huella", ""),
             # `tools/audio/msu.py` reads it from here, which builds only the
             # tracks of the cartridge's songs.
             "pista": t["pista"]} for t in hechos]},
            handle, indent=1)
    # Each package's sound effects go by number and not by SRCN: several share
    # the directory's place. See `snes_music.lugares_de_efectos`.
    efectos = getattr(banco, "efectos", {})
    efecto_id = getattr(banco, "efecto_id", {})
    paquetes = [(suyos, [efecto_id[n] for n in suyas if n in efectos], salida)
                for suyos, suyas, salida in paquetes]
    directorio = (len(banco.voces), getattr(banco, "lugares", 0))
    efecto_lugar = [srcn - directorio[0] for srcn, _e in sorted(
        efectos.values(), key=lambda v: efecto_id[v[1].name])]
    if pide:
        assert nombres_de_paquete[len(mapas)] == "pelea", (
            "the battle's package has to end up at the index `emit` emitted "
            "as PAQUETE_BATALLA")
        print("  battle audio package: %d song(s), %d sound effect(s)"
              % (len(pide["temas"]), len(paquetes[-1][1])))
    # **And that the boot fits in `BOOT_CUADROS`**: the ROM waits until that
    # frame so that the loop always starts on the same one, and if uploading
    # the boot map's package took longer, it would come out later and the
    # tests —which count from there— would count wrong. See the comment on
    # `BOOT_CUADROS` in tools/runtime/ram_lejana.s.
    cuadros, del_paquete = snes_music.cuadros_del_arranque(
        driver, muestras, hechos, paquetes[args.inicial],
        cuadros_de_descomprimir(mapas[args.inicial], comprimidos),
        directorio)
    tope = snes_music.boot_cuadros()
    if cuadros > tope:
        raise SystemExit(
            "the boot doesn't fit in BOOT_CUADROS: the boot map's package is "
            "%d B and with the map, the driver and the directory the "
            "computation gives %.0f frames, against %d. Raise BOOT_CUADROS in "
            "tools/runtime/ram_lejana.s, or shrink that package"
            % (del_paquete, cuadros, tope))
    print("  boot: the boot map's package is %d B, %.0f of "
          "the %d frames of BOOT_CUADROS" % (del_paquete, cuadros, tope))
    snes_music.emit(musica, hechos, driver, muestras, arranque, tema_titulo,
                    snes_music.tabla_de_sonidos(temas.sonidos, banco),
                    [p + (aparte,) for p, aparte in zip(paquetes, apartes)],
                    tema_de_mapa, directorio, efecto_lugar,
                    game_over=(tema_game_over, paquete_game_over))
    # The `.msu`: the quality backdrops and the quality sound effects, to read
    # them through the MSU-1 when it is there. It is always written, even if
    # the cartridge carries neither backdrops nor sound effects, because it is
    # also the file that turns on the MSU-1 for the tracks.
    escribir_msu(args.msu or os.path.join(os.path.dirname(os.path.abspath(
        args.output)), "datos.msu"), musica, escenas["calidad"],
        por_nombre[:len(paquetes)], paquetes, hechos, muestras, banco,
        temas.sonidos, args.game_dir)
    for i, (suyos, suyas, salida) in enumerate(paquetes[:len(mapas)]):
        if suyos or suyas or salida or apartes[i]:
            print("  audio package of map %d: %d song(s), %d sound effect(s)%s%s"
                  % (mapas[i]["id"], len(suyos), len(suyas),
                     ", and for exit %s" % ", ".join(hechos[t]["nombre"]
                                                     for t in salida)
                     if salida else "",
                     ", and separate %s" % ", ".join(hechos[t]["nombre"]
                                                     for t in apartes[i])
                     if apartes[i] else ""))
    if pedidos_se:
        print("  sound effects: %d, %d B in the cartridge"
              % (len(efectos), sum(len(e.data) for _s, e in efectos.values())))
    print("music -> %s: %s"
          % (musica, ", ".join(t["nombre"] for t in hechos)
             or "none, it comes out silent"))

    # **And only here is the bank packing decided**, with both files already
    # written: it spreads everything both send to RODATA, and the banks end up
    # at the end of the last one. See `tools/ensamblado/bancos.py`.
    piezas, usados = bancos.resolver([musica, args.output])
    print("bank packing: %d piece(s) in %d bank(s)" % (piezas, usados))
    # And the memory map for `ld65`, next to it: it comes from here and not
    # from a hand-written file so that which bank the data starts at is
    # written only once, in `bancos.PRIMER_BANCO`.
    with open(os.path.join(os.path.dirname(os.path.abspath(args.output)),
                           "memoria.cfg"), "w") as handle:
        handle.write(bancos.cfg())
    for i, tema in enumerate(hechos):
        # The percentage of notes that reach the stream goes here and not
        # hidden: it is what is heard as "it's missing voices", and until
        # 2026-09-14 nobody said it. See
        # workflow/decisiones/un-solo-banco-de-muestras.md.
        suenan = tema["resumen"].get("notas")
        # And how much of what does have a sample is lost for lack of voices,
        # against what would be lost with no remedy with eight: it is what
        # the allocation of `snes_music.assign` measures.
        perdido, piso = tema["resumen"].get("perdido", (0.0, 0.0))
        print("  %d. %-16s %4.0f s, %6d B of stream and %4d of sounds, "
              "%s of the notes, %.0f%% of note-time without a voice (floor %.0f%%)%s"
              % (i, tema["nombre"], tema["segundos"], len(tema["stream"]),
                 6 * len(tema["sonidos"]),
                 "all" if suenan is None or suenan > 0.999
                 else "%.0f%%" % (100 * suenan), 100 * perdido, 100 * piso,
                 ", plays from boot" if i == arranque else ""))
    if hechos:
        print("  shared bank: %d samples, %d B in the cartridge; each "
              "package has %d B of ARAM for its samples"
              % (len(banco.voces), sum(len(v.data) for v in banco.voces),
                 banco.libre))
        # What rate each sample ended up at and which package limited it: it
        # is what is heard, and what says where to look for room if needed. A
        # key with copies comes out once per copy, with the songs that use it:
        # see `snes_music.copias`.
        usan = collections.defaultdict(list)
        for tema, suya in zip(hechos, banco.asignacion):
            for muestra in suya.values():
                usan[muestra].append(tema["nombre"])
        for clave, voz in zip(banco.claves, banco.voces):
            print("    %s %3d %-10s %5.1f kHz, %5d B%s%s%s"
                  % ("program " if clave[0] == "p" else "hit     ", clave[1],
                     voz.name.strip()[:10], voz.rate / 1000.0, len(voz.data),
                     ", root %d" % voz.root if clave[0] == "p" else "",
                     ", limited by " + banco.limita[clave]
                     if clave in banco.limita else "",
                     ", for " + " ".join(usan[clave])
                     if len(clave) > (3 if clave[0] == "p" else 2)
                     or any(len(k) > len(clave) and k[:len(clave)] == clave
                            for k in banco.claves) else ""))
        # And how much each package has left over, with its sound effects: the
        # whole ones with what they really take, not with what the music
        # budgeted for them. The bank's constraints already bring them that way
        # —they are those of `reales`, see `snes_music.copias`—: subtracting
        # the extra again gave packages that didn't fit and did fit.
        for r in banco.restricciones:
            print("    package %-28s %5d B of samples, %5d left over"
                  % (r.nombre[:28], banco.ocupa(r.claves),
                     r.libre - banco.ocupa(r.claves)))


def escribir_msu(ruta, musica, fondos, por_nombre, paquetes, hechos, muestras,
                 banco, sonidos, game_dir):
    """Writes the `.msu` to `ruta` and appends to `musica` —the
    `musicdata.inc`— what the ROM needs to read it: the signature, where each
    backdrop is and, per package, where each sound effect is and at which
    pitch each sound plays.

    The backdrops go first —`fondos` are the `(tiles, colors)` of **all the
    game's**, by number, each in its fixed place: see `msu_datos.fondo_en`—
    and behind them the quality sound effects of each package, in the order
    of the package table and each package with its own in order of place in
    the directory —their SRCN—: it is the order `subir_colocadas` uploads them
    in, so the ROM reads them in one go, with a single seek per package. A
    sound effect that is in two packages goes twice even if at the same rate:
    a seek costs Mednafen one or two frames, and the file has no cap.

    `por_nombre` are the ROM's packages as `build_varios` sees them —with the
    names of their sound effects— and `paquetes` the same as `emit` emits them
    —with their sound effect numbers—, in the same order. See
    tools/audio/efectos_msu.py.
    """
    efectos = getattr(banco, "efectos", {})
    de_numero = {i: n for n, i in getattr(banco, "efecto_id", {}).items()}
    # What the music takes with MSU-1 in each package: only the songs without
    # a track, which `tema_por_msu` doesn't skip.
    pesa = {}

    def musica_de(temas):
        suyas = set()
        for t in temas:
            if hechos[t]["pista"] is None:
                if t not in pesa:
                    pesa[t] = snes_music.muestras_del_tema(hechos[t])
                suyas |= set(pesa[t])
        return sum(len(muestras[i].data) for i in suyas)
    pedidos = [(str(p[0]), list(p[2]), musica_de(p[1]))
               for p in por_nombre]
    tasas = efectos_msu.tasas(pedidos, efectos, banco.libre, game_dir)
    unicas = sorted({(e, t) for suyas in tasas.values()
                     for e, t in suyas.items()})
    hechas = dict(zip(unicas, in_parallel(
        lambda par: efectos_msu.armar(par[0], par[1], game_dir), unicas)))

    entradas = [parte for par in fondos for parte in par]
    # Which entry each sound effect of each package is, in SRCN order: two of
    # the same package never share a place.
    del_paquete = []
    for (nombre, _t, _e, *_s), (_temas, numeros, _salida) in zip(por_nombre,
                                                                 paquetes):
        suyas = tasas.get(str(nombre), {})
        lista = []
        for e in sorted({de_numero[i] for i in numeros},
                        key=lambda e: efectos[e][0]):
            lista.append((e, len(entradas), hechas[e, suyas[e]]))
            entradas.append(hechas[e, suyas[e]].data)
        del_paquete.append(lista)
    archivo, donde = msu_datos.armar(entradas, fondos=len(fondos))
    firma = archivo[:msu_datos.FIRMA]
    with open(ruta + ".nuevo", "wb") as handle:
        handle.write(archivo)
    os.replace(ruta + ".nuevo", ruta)
    print("  .msu: %d backdrop(s) and %d sound effect(s) in %d B, signature %s -> %s"
          % (len(fondos), sum(len(l) for l in del_paquete), len(archivo),
             firma.hex(), ruta))

    # Per package, one row per sound effect of its list —that of `paquetes`,
    # in the order the ROM walks it—: where it is in the `.msu`, how long it
    # is and where it loops back, which is always to the start because they
    # go whole.
    filas, desde_filas = bytearray(), bytearray()
    alturas, desde_alturas, ya_listas = bytearray(), bytearray(), {}
    for (nombre, *_r), (_temas, numeros, _salida), lista in zip(
            por_nombre, paquetes, del_paquete):
        desde_filas += (len(filas)).to_bytes(2, "little")
        de_efecto = {e: (donde[k], v) for e, k, v in lista}
        for i in numeros:
            pos, version = de_efecto[de_numero[i]]
            filas += (pos.to_bytes(4, "little")
                      + len(version.data).to_bytes(2, "little")
                      + bytes(2))
        # And the pitch of each sound of `sonido_tabla` with this package's
        # version: with that the ROM does no arithmetic, not even in the
        # interrupt. **Only the sounds whose sound effect is from here**, as
        # (index, pitch) pairs sorted by index and closed with $FFFF, which
        # `altura_msu` walks: until 2026-09-27 it was one row per package with
        # all the sounds, almost all zeros, and with the whole world chapter
        # it went over a bank. Two packages with the same list share it.
        suyas = tasas.get(str(nombre), {})
        lista = bytearray()
        for k, (efecto, _volumen, tempo, _balance) in enumerate(sonidos):
            altura = 0
            if efecto in suyas:
                altura = snes_music.altura_de_efecto(
                    hechas[efecto, suyas[efecto]], tempo)
            # Zero is "not from here" for the ROM, so it isn't stored.
            if altura:
                lista += k.to_bytes(2, "little") + altura.to_bytes(2, "little")
        lista += b"\xFF\xFF"
        lista = bytes(lista)
        if lista not in ya_listas:
            ya_listas[lista] = len(alturas)
            alturas += lista
        desde_alturas += ya_listas[lista].to_bytes(2, "little")
    for tabla in (filas, alturas):
        if len(tabla) > 0x8000:
            raise SystemExit("the .msu sound effect tables go over a "
                             "bank: %d B" % len(tabla))
    posiciones = [(donde[2 * k], donde[2 * k + 1]) for k in range(len(fondos))]
    fondo_pos = b"".join(a.to_bytes(4, "little") + b.to_bytes(4, "little")
                         for a, b in posiciones) or bytes(8)
    with open(musica, "a") as handle:
        handle.write(
            "\n; The `.msu`: see `escribir_msu` in tools/port/snes_convert.py.\n"
            "; How many entries of the .msu are backdrops —two per backdrop,\n"
            "; the first ones— and how many are sound effects, behind: for\n"
            "; the tests.\n"
            "MSU_FONDOS_N = %d\n"
            "MSU_EFECTOS_N = %d\n"
            '.segment "RODATA"\n%s\n'
            % (len(fondos),
               sum(len(lista) for lista in del_paquete),
               "\n".join(bloque(etiqueta, datos or bytes(2)) for etiqueta, datos
                         in (("msu_datos_firma", firma),
                             ("msu_fondo_pos", fondo_pos),
                             ("se_msu_paq", desde_filas),
                             ("se_msu_filas", filas),
                             ("se_msu_altura_paq", desde_alturas),
                             ("se_msu_altura", alturas)))))
    # And the same, readable, next to it: which sound each row of
    # `sonido_tabla` is and at which rate each sound effect of each package
    # goes in the `.msu`. The ROM doesn't read it; it is for the tools that
    # touch a sound effect from outside and to look at what the allocation
    # decided.
    with open(os.path.join(os.path.dirname(musica), "efectos.json"),
              "w") as handle:
        json.dump({"sonidos": [list(s) for s in sonidos],
                   "srcn": {e: srcn for e, (srcn, _v) in efectos.items()},
                   "tasas": tasas}, handle, indent=1)
    for (nombre, *_r) in por_nombre:
        suyas = tasas.get(str(nombre), {})
        if suyas:
            print("  quality sound effects of package %s: %s"
                  % (nombre, ", ".join(
                      "%d Hz: %d" % (t, sum(1 for v in suyas.values()
                                            if v == t))
                      for t in sorted(set(suyas.values()), reverse=True))))


def temas_heredados(temas, tema_de_mapa, inicial, titulo, nombres_de_paquete,
                    del_paquete=None, apartes=None, no_se_dan=()):
    """[(package name, index of a song that can be already playing when it
    loads)], for `snes_music.build_varios`.

    Almost no map of the game brings its own song: a page starts it, and
    until then the previous map's keeps going, and `paquete_cargar_ya`
    doesn't move its samples. So the package of a map without its own song
    has to fit next to whatever can be already playing.

    The teleports of the compiled pages are followed —`destinos` of
    `Temas.por_mapa`— without looking at conditions, with a rule that is what
    makes the count realistic and not "any song to any map" (4 is the game's
    router): **a map with `PlayBGM` leaves with one of its own**, because the
    page that jumps is almost always the one that started the song before. A
    map with its own song silences what plays before loading its own
    —`mapa_tema_callar`—, so it inherits nothing; and the boot map is reached
    with the title's playing. It is what step 6 of
    `workflow/tasks/todo/la-calidad-de-la-musica.md` measured with a separate
    script.

    `del_paquete` are the songs each map's package uploads on entering
    —without the exit ones, see `Temas.de_salida`—: a song that arrives
    playing and isn't there has to fit next to it. Without it, the ones its
    pages start. What leaves a map is still any of the ones they start, exit
    ones included: they are precisely the ones that leave with it.

    **Except in a map whose `PlayBGM`s are all exit ones**: there the rule
    above doesn't hold, because each one goes stuck to its jump and the map's
    other jumps carry none. Each jump carries what `Temas.salto` says: the
    exit song that precedes it, or whatever came into the map. It is the
    game's 41 and 40: `Kfmus5` comes into 41 from the page of 37 and goes on
    through 40, 42, 43, 44 and 45, while `golden_axe-turtlevillage2` and
    `tsmedit` play only to leave. From 2026-09-27; until then those maps
    inherited only their exit songs. The boot one keeps the rule above: see
    `lleva`.

    `apartes` are the separate songs of each package —see
    `snes_music.temas_aparte()`—: they don't leave the map, so they don't
    count in what goes out.

    `no_se_dan` are the jumps of compiled pages that can't happen, as
    [map, destination] pairs: a jump that never happens makes it reserve room
    for a song that never arrives, at the expense of the ones that do. The
    game declares them, in `[music] jumps_that_never_happen` of the project
    file.
    """
    n = len(tema_de_mapa)
    pide = [temas.por_mapa.get(i, {}) for i in range(n)]
    apartes = apartes or [()] * n
    indice = {nombre: i for i, nombre in enumerate(nombres_de_paquete[:n])}
    no_se_dan = {(indice[str(a)], indice[str(b)])
                 for a, b in no_se_dan
                 if str(a) in indice and str(b) in indice}
    saltos = getattr(temas, "saltos", {})
    entra = [set() for _ in range(n)]
    if titulo != 0xFF:
        entra[inicial].add(titulo)

    def lleva(i, destino):
        if tema_de_mapa[i] != 0xFF:
            return {tema_de_mapa[i]}
        suyos = set(pide[i].get("temas", ())) - set(apartes[i])
        # Not the boot one: it is the router, which jumps to mid-game
        # according to variables, and without looking at conditions whatever
        # comes in there would go out anywhere.
        if suyos and suyos <= set(temas.de_salida(i)) and i != inicial:
            # A destination no noted jump names —that of a page that didn't
            # compile whole— carries what came in.
            con = saltos.get(i, {}).get(destino, {None})
            return ({t for t in con if t is not None}
                    | (entra[i] if None in con else set()))
        return suyos or entra[i]

    cambio = True
    while cambio:
        cambio = False
        for i in range(n):
            for destino in pide[i].get("destinos", ()):
                if (i, destino) in no_se_dan:
                    continue
                sale = lleva(i, destino)
                if (destino != i and tema_de_mapa[destino] == 0xFF
                        and not sale <= entra[destino]):
                    entra[destino] |= sale
                    cambio = True
    if del_paquete is None:
        del_paquete = [pide[i].get("temas", ()) for i in range(n)]
    return [(nombres_de_paquete[i], t) for i in range(n)
            for t in sorted(entra[i])
            if t not in del_paquete[i] and t != tema_de_mapa[i]]


def temas_de_la_rom(map_id, temas, game_dir, titulo=None, map_ids=(),
                    game_over=None):
    """Which songs the cartridge asks for, which one plays at boot and which
    one each map starts on entering.

    **All** are asked for: the ones the compiled `PlayBGM`s name, plus that of
    the map where the ROM boots, which is the one that plays without anything
    happening. **And all of them fit**: the index is given by the list and
    costs no ARAM. What the ARAM limits is the samples, and that is allocated
    by `snes_music.build_varios` per package: at the rate the worst package of
    each one gives, but all of them.

    The indices are those of `Temas` and aren't touched: the bytecode already
    carries them emitted. That is why the map's is added **at the end**,
    which is the only thing that doesn't renumber the others. Going last
    costs nothing: since the per-package budget no song loses samples for its
    place in the list.

    And the own song of each map in `map_ids` —in the order of the map
    table—, which is easyrpg's `Game_Map::PlayBgm`: what plays when entering
    through a teleport. They go behind all, for the same reason, and as each
    one's index or $FF, which is "entering doesn't change the music".
    """
    propio = snes_music.tema_del_mapa(map_id, game_dir)
    if propio:
        temas.indice(propio)            # adds it at the end if it wasn't there
    # The title screen's goes after, for the same reason: adding at the end is
    # the only thing that doesn't renumber the ones the bytecode already
    # names. It comes from the LDB —`title_music`, which in ABL is
    # Fantasia_Of_The_Wind— and not from the command line: it is a piece of
    # the game's data, not a choice of ours.
    if titulo:
        temas.indice(titulo)
    # And the Game Over screen's, for the same reason: `gameover_music`,
    # which in ABL is `GameOver3` and comes from the RTP. See
    # `PAQUETE_GAME_OVER`.
    if game_over:
        temas.indice(game_over)
    de_cada_mapa = []
    for nombre in snes_music.temas_de_los_mapas(map_ids, game_dir):
        indice = temas.indice(nombre) if nombre else 0xFF
        # $FF is "doesn't change": a song with that number couldn't be
        # started. A `PlayBGM`, which carries the index in one byte, wouldn't
        # start it either.
        assert indice <= 0xFF, "song %r doesn't fit in a byte" % nombre
        de_cada_mapa.append(indice)
    nombres = list(temas.nombres)
    return (nombres, (nombres.index(propio) if propio else 0xFF),
            (nombres.index(titulo) if titulo else 0xFF), de_cada_mapa,
            (nombres.index(game_over) if game_over else 0xFF))


def inicio_del_mapa(renderer, map_id, passable, width, height, ocupadas=()):
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
        return hero_start(passable, width, height, ocupadas)
    except ValueError:
        return width // 2, height // 2


def images_de(renderer, args, charset):
    """An actor's CharSet, loaded and cached."""
    if charset not in _charsets:
        _charsets[charset] = renderer.charsets.get(charset)
        if _charsets[charset] is None:
            sys.exit("can't find CharSet %r" % charset)
    return _charsets[charset]


_charsets = {}


def lideres_posibles(renderer, map_ids, grupo):
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
    rules as `Estado.cambiar_grupo`. It is an approximation —which page runs
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
    actores = list(grupo[:1])
    for cambios in _cambios_de_grupo(map_ids):
        estado = eventos.Estado(grupo)
        for tanda in cambios:
            for quien, operacion in tanda:
                estado.cambiar_grupo(quien, operacion)
            lider = estado.lider()
            if lider is not None and lider not in actores:
                actores.append(lider)
    return actores


def _cambios_de_grupo(map_ids):
    """The `ChangePartyMembers` of the pages that compile, map by map and in
    order: the only thing of each map `lideres_posibles` looks at.

    **It is computed once per conversion**, because it doesn't depend on the
    party: `lideres_posibles` runs again for each test case that touches the
    party, and each run loaded and compiled all the maps again. The
    compilation only reads the global indices of `eventos`, which are filled
    before the first call and don't change afterwards.
    """
    clave = (_juego(), tuple(map_ids))
    if clave not in _cambios_por_mapas:
        _cambios_por_mapas[clave] = [_cambios_del_mapa(map_id, map_ids)
                                     for map_id in map_ids]
    return _cambios_por_mapas[clave]


_cambios_por_mapas = {}


def _cambios_del_mapa(map_id, map_ids):
    indices = {m: i for i, m in enumerate(map_ids)}
    cambios = []
    game_map = lcf.Map(os.path.join(_juego(),
                                    "Map%04d.lmu" % map_id))
    del_mapa = eventos.Eventos(game_map)
    for evento in game_map.events:
        for page in evento.pages:
            # With the map's context, which is the same the real filter uses.
            # Without it, a page that sends another event walking doesn't
            # compile here even though it does compile there, and the actors
            # it adds are lost: the opening cutscene adds Kersh to the party
            # right after sending event 8 walking, so the hero was left
            # without a pose table and wasn't drawn.
            # **With the same context as the real compilation**, and not only
            # with the text block. `Temas`, `Graficos` and `Imagenes` were
            # missing, and without them a page that starts with a `PlayBGM`
            # doesn't compile **here** and does compile there: the actors it
            # adds to the party are lost. It is exactly what happened to the
            # chase car —`RaceController1` of map 49 starts with `PlayBGM`
            # and then adds `CarRED`—, and the symptom was that the hero
            # wasn't drawn: `hero_poses` at zero because the actor wasn't in
            # the map's table.
            if eventos.compilar_pagina(
                    page, indices.get,
                    eventos.Mensajes(),
                    del_mapa.para(evento.id), eventos.Temas(),
                    eventos.Graficos(), eventos.Imagenes(
                        _juego())) is None:
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
            tanda = None
            for cmd in page.commands:
                if cmd.code != eventos.CHANGE_PARTY_MEMBERS:
                    tanda = None
                    continue
                p = cmd.parameters
                if len(p) < 3 or p[1] != eventos.GRUPO_ID_FIJO:
                    tanda = None
                    continue
                if tanda is None:
                    tanda = []
                    cambios.append(tanda)
                tanda.append((p[0], p[2]))
    return cambios


# The game directory, for `lideres_posibles`. It is ugly but it is a single
# place: the alternative was passing it through three functions that don't
# use it. `main` sets it, from `--game-dir`.
args_game_dir = [None]


def _juego():
    """`main`'s or, if it didn't go through there —a test that calls these
    functions on their own—, the environment's, which is the same
    `--game-dir`."""
    return args_game_dir[0] or resources.GAME_DIR


def items_posibles(map_ids, actores=(), db=None, extra=()):
    """The items that can be in the inventory with these maps in the ROM: the
    ones some `ChangeItems` of any page gives, whether it compiles or not,
    the ones some `OpenShop` sells, the equipment the `actores` start with
    and the ones the test page gives. It is a superset, like
    `miembros_posibles`, and for the same reason: one item too many costs its
    text in the cartridge, one too few isn't seen in the list. `extra` are
    the commands of the test pages, which are swept the same as the maps'."""
    items = set()
    for actor in actores:
        if db is not None and actor in db.actors:
            items.update(i for i in db.actors[actor].initial_equipment if i)

    def barrer(comandos):
        for cmd in comandos:
            p = cmd.parameters
            if (cmd.code == eventos.CHANGE_ITEMS and len(p) >= 5
                    and p[0] == 0 and p[1] == 0):
                items.add(p[2])
            elif cmd.code == eventos.OPEN_SHOP:
                items.update(p[4:])

    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_juego(),
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                barrer(page.commands)
    barrer(extra)
    return sorted(i for i in items if 0 < i < eventos.ITEMS_N)


def items_del_botin(db, tropas):
    """The items some enemy of these troops can drop on losing a battle —its
    `drop_id`—, so that the cartridge carries their name: the victory tells
    it and the menu's list shows it. The ones `items_posibles` doesn't find
    in any page. All the members, like `enemigos_rom`."""
    return {db.enemies[e].drop_id for n in tropas if n in db.troops
            for e in db.troops[n].members
            if 0 < db.enemies[e].drop_id < eventos.ITEMS_N}


def miembros_posibles(map_ids, grupo, extra=()):
    """The actors that can be in the party with these maps in the ROM.

    The starting ones plus the ones any `ChangePartyMembers` of any page of
    these maps adds. Whether the page compiles isn't looked at: it is for the
    slots screen, which needs the face and the name of whoever can show up in
    a saved game, and one face too many costs nothing that matters. `extra`
    are the commands of the test pages.

    `grupo` can bring repeats —the cartridge's plus that of each test case,
    which is usually the same— and they are counted once: repeated, an actor
    took one face for each case that asked for it.
    """
    actores = list(dict.fromkeys(grupo))

    def barrer(comandos):
        for cmd in comandos:
            if cmd.code != eventos.CHANGE_PARTY_MEMBERS:
                continue
            p = cmd.parameters
            if len(p) < 3 or p[1] != eventos.GRUPO_ID_FIJO:
                continue
            if p[0] == 0 and p[2] not in actores:
                actores.append(p[2])

    for map_id in map_ids:
        game_map = lcf.Map(os.path.join(_juego(),
                                        "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                barrer(page.commands)
    barrer(extra)
    return sorted(actores)


def grupo_de_la_pagina(caso, grupo):
    """Which party the test continues with after its page, if the page
    touches it: the case's `ChangePartyMembers` applied to the cartridge's
    party, with the same rules as the interpreter. None if it doesn't touch
    it."""
    estado = eventos.Estado(grupo)
    toca = False
    for cmd in caso.comandos:
        p = cmd.parameters
        if (cmd.code == eventos.CHANGE_PARTY_MEMBERS and len(p) >= 3
                and p[1] == eventos.GRUPO_ID_FIJO):
            estado.cambiar_grupo(p[0], p[2])
            toca = True
    return estado.grupo if toca else None


def separar_del_heroe(renderer, game_map, args, comandos=()):
    """If something flashes the hero, the NPCs with its graphic go with
    another palette.

    On the console the flash is done on the character's palette, and a leader
    that is also an NPC in the map shares a palette with that NPC —so that the
    NPC isn't drawn with another leader's colors—, so both flashed. It is
    solved by counting those NPCs' graphic as another one, with the suffix
    `rm2k.COPIA_SUFIJO`: the same drawing, with its own palette. It costs one
    palette per graphic, and only in the maps where something flashes the
    hero. `comandos` are those of the test pages.
    """
    destella = any(
        cmd.code == eventos.FLASH_SPRITE and cmd.parameters
        and cmd.parameters[0] == eventos.RUTA_HEROE
        for cmd in list(comandos) + [cmd for ev in game_map.events
                                     for page in ev.pages
                                     for cmd in page.commands])
    if not destella:
        return
    de_lider = set()
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        de_lider.add((a.charset, a.charset_index))
    for ev in game_map.events:
        for page in ev.pages:
            if (page.character_name, page.character_index) in de_lider:
                page.character_name += rm2k.COPIA_SUFIJO


# The flags that describe **a test case** —what its page does— and not the
# cartridge. They are the ones that can go after a `--caso`; the rest belong
# to the whole cartridge and go before the first one. Since cut 3 of step 9d
# there is a single one, the file with the page: what the page does is RM2k
# data, not flags. `--grafico-de-prueba` belongs to the cartridge on purpose:
# it says which graphics are in the sprite bank of the maps where the cases
# run, not what the page does. And where a case runs isn't a flag either: the
# `Teleport` it starts with says so, see `mapa_del_caso`.
FLAGS_DE_CASO = ("comandos_de_prueba",)


def partir_en_casos(argv):
    """The command line split at `--caso`: the cartridge's part, and the
    flags of each case that goes after."""
    tramos = [[]]
    for token in argv:
        if token == "--caso":
            tramos.append([])
        else:
            tramos[-1].append(token)
    return tramos[0], tramos[1:]


def casos_de_prueba(parser, args, tramos):
    """The cartridge's test pages, one per case, in the order of their pages.
    Each one is a copy of `args` with its case's flags.

    Case 0 is the flags before the first `--caso`, so a single-case cartridge
    is built as before this existed. If there are none, the first `--caso`
    becomes 0. Each case takes the commands of its file in `comandos`.
    """
    import copy
    casos = [args] if pide_pagina_de_prueba(args) else []
    defecto = parser.parse_args([])
    for tramo in tramos:
        suelto = parser.parse_args(tramo)
        for dest, valor in vars(suelto).items():
            if dest not in FLAGS_DE_CASO and valor != getattr(defecto, dest):
                sys.exit("--%s belongs to the cartridge and not to a case: it "
                         "goes before the first --caso" % dest.replace("_", "-"))
        caso = copy.copy(args)
        for dest in FLAGS_DE_CASO:
            setattr(caso, dest, getattr(suelto, dest))
        if not pide_pagina_de_prueba(caso):
            sys.exit("a --caso with nothing for the test page to do")
        casos.append(caso)
    for caso in casos:
        with open(caso.comandos_de_prueba, encoding="utf-8") as archivo:
            caso.comandos = lcf.handwritten_commands(json.load(archivo))
    return casos


def comandos_de_casos(args, map_id=None):
    """The commands of all the test pages, one after the other.

    It is what the functions that look at the map's pages to decide what the
    cartridge carries —variables, items, members, rain— sweep: a test page is
    one more page.

    With `map_id`, only those of the cases that **run** in that map —see
    `mapa_del_caso`—: they are the ones that decide what belongs to each map,
    like who walks or which graphics go in its sprite bank.
    """
    return [cmd for caso in args.casos
            if map_id is None or caso.mapa == map_id
            for cmd in caso.comandos]


def mapa_del_caso(caso, orden, inicial):
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
    primero = caso.comandos[0] if caso.comandos else None
    if primero is None or primero.code != eventos.TELEPORT:
        return orden[inicial]
    destino = primero.parameters[0]
    if destino not in orden:
        sys.exit("%s: the case jumps to map %d, which isn't in the cartridge "
                 "(it carries %s)" % (caso.comandos_de_prueba, destino,
                                      " ".join(str(m) for m in orden)))
    return destino


def mapas_de_prueba(args):
    """The maps where some case runs, which are the ones that carry the
    graphics of `--grafico-de-prueba` in their bank."""
    if args.casos:
        return {caso.mapa for caso in args.casos}
    return {orden_de_mapas(args)[args.inicial]}


def pagina_de_caso(caso, mapa, temas, graficos, mensajes, indices, imagenes):
    """The bytecode of a case's test page.

    It is compiled like any page of the game, with the context of the map
    where it runs —see `mapa_del_caso`—; the only thing the converter puts in
    front of it is the `ControlSwitches` that turns it off, which is a
    convention of the harness and not of the case —see
    `eventos.SWITCH_DE_PRUEBA`—. The troops aren't noted here but at the end,
    in `main`: the test's goes last.
    """
    apagar = lcf.EventCommand(
        eventos.CONTROL_SWITCHES, 0, "",
        [eventos.SWITCH_UNICO, eventos.SWITCH_DE_PRUEBA,
         eventos.SWITCH_DE_PRUEBA, eventos.SWITCH_ON])
    codigo = eventos.compilar_pagina(
        eventos._Comandos([apagar] + list(caso.comandos)), indices.get,
        mensajes, eventos.Eventos(mapa["game_map"]).para(0), temas,
        graficos, imagenes)
    if codigo is None:
        sys.exit("%s: the test page doesn't compile"
                 % caso.comandos_de_prueba)
    return codigo

def pide_pagina_de_prueba(args):
    """Whether there is a test page before the first `--caso`."""
    return bool(args.comandos_de_prueba)

def convertir(renderer, map_id, args):
    """A whole map: tiles, colors, sprites, collision and blocks."""
    game_map = renderer.cargar_mapa(
        os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    if args.casos and map_id == orden_de_mapas(args)[args.inicial]:
        # The test page's event goes **first**: the ROM walks the events from
        # lowest to highest, and the test page has to run before the game's.
        # It builds the party the test starts with, and a map whose page
        # touches the party on entering —21 adds Talan— found it already
        # changed. It is an event without pages: nothing is drawn or compiled,
        # it only takes index 0 so that everything that numbers events after
        # reading the map numbers the same.
        vacio = lcf.Event.__new__(lcf.Event)
        vacio.id, vacio.name, vacio.x, vacio.y, vacio.pages = (
            0, "prueba", 0, 0, [])
        game_map.events.insert(0, vacio)
    separar_del_heroe(renderer, game_map, args,
                      comandos_de_casos(args, map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    capas = capas_convertidas(renderer, game_map)
    if capas is None:
        sys.exit("can't find the chipset of map %d" % map_id)

    # And the layers again, with the opaque events baked into the map. **Both**
    # are converted and compared because baking adds colors to the
    # background: if that made it merge colors, or shifted the upper layer's
    # CGRAM split, what is seen in cells that have nothing to do with the
    # baking would change. In that case the map goes unbaked, which is the
    # usual. The second conversion isn't paid twice in a warm build: both stay
    # in the disk cache, with their key.
    sin_horneado = capas
    horneados = eventos_horneables(renderer, game_map)
    if horneados:
        capas, horneados = _hornear_si_no_mueve_la_cgram(
            renderer, game_map, map_id, sin_horneado, horneados)

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
    orden = orden_de_mapas(args)
    movibles, graficos_de_ruta, anima_quieto, giran = eventos_movibles(
        game_map, {m: i for i, m in enumerate(orden)}.get,
        asociaciones=args.asociaciones)
    # And the ones from `--grafico-de-prueba`, which go only in the maps where
    # some case runs, and for the same reason their pages are compiled with
    # that map's context. They are added **after** the game's, which is the
    # order the real compilation numbers them in.
    if args.grafico_de_prueba and map_id in mapas_de_prueba(args):
        for charset, index in graficos_de_prueba(args.grafico_de_prueba):
            if (charset, index) not in graficos_de_ruta:
                graficos_de_ruta.append((charset, index))
    if comandos_de_casos(args, map_id):
        # And the ones the test pages send walking, which don't come from
        # `paginas_del_mapa`: they have to be added by hand or the NPC would
        # walk with a single pose. It goes **before** the palette split: since
        # the palette is chosen over the poses that are seen, knowing who walks
        # is part of choosing the colors and not only of splitting the VRAM.
        # The event goes by its RM2k id and the same `Eventos` the compilation
        # uses translates it.
        del_mapa = eventos.Eventos(game_map)
        for cmd in comandos_de_casos(args, map_id):
            if cmd.code == eventos.MOVE_EVENT and cmd.parameters \
                    and cmd.parameters[0] != eventos.RUTA_HEROE:
                blanco = del_mapa.blanco(cmd.parameters[0])
                if blanco:
                    movibles = movibles | {blanco - 1}
    # And with that, which poses each graphic can show: it is what decides
    # over which pixels its fifteen colors are chosen. See `poses_del_mapa`.
    poses_por_grafico = poses_del_mapa(renderer, game_map, args.lideres,
                                       movibles, giran, graficos_de_ruta,
                                       anima_quieto)

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
    muestra_animacion = mapa_muestra_animacion(
        game_map, renderer,
        comandos_de_casos(args, map_id))
    # The timer's colors are passed to the split and not only to the packing:
    # in a map that fills the eight palettes someone has to be chosen to lose
    # a color to make room for it, and that changes how that character is
    # quantized.
    timer_colores = ()
    if map_id in args.timer_en:
        from port import ventana as ventana_mod
        timer_colores = sorted(colores_del_timer(ventana_mod.skin(
            args.game_dir, renderer.database.system_name)))
    solos = {c for c, n in getattr(args, "mapas_por_personaje", {}).items()
             if n == 1}
    tope_de_paletas = tope_de_paletas_del_mapa(
        renderer, game_map, args.lideres, graficos_de_ruta, timer_colores,
        solos, poses_por_grafico, muestra_animacion)

    npcs, descartados, reparto = npcs_dibujables(renderer, game_map,
                                                 args.lideres, tope_de_paletas,
                                                 graficos_de_ruta,
                                                 timer_colores,
                                                 solos,
                                                 poses_por_grafico)
    prestadas = reparto[5]
    if prestadas:
        print("  map %d: %d graphic(s) without a palette of their own, drawn "
              "with someone else's: %s" % (map_id, len(prestadas),
                                          ", ".join(sorted("%s:%d" % k for k in prestadas))))
    # A baked event that was drawn with someone else's palette can't be
    # hidden: the sprite and the background tile would show different colors
    # —the lent ones and the real ones— and covering it with the second
    # changes what is seen. So that one is unbaked and goes back to being a
    # sprite, with the lent colors: it looks as it would without the baking.
    # It is asked here and not in `eventos_horneables` because the lent ones
    # come from the split, which runs after drawing the layers. The first was
    # `PawnDoorTop`, event 11 of map 37: until 2026-09-26 this was a
    # `sys.exit`.
    horneado_prestado = sorted(
        evento for evento in horneados
        for npc in npcs
        if npc["evento"] == evento and (npc["charset"], npc["index"]) in prestadas)
    if horneado_prestado:
        print("  map %d: event %s is drawn with someone else's palette, so "
              "it isn't baked" % (map_id, ", ".join(str(e + 1)
                                                    for e in horneado_prestado)))
        for evento in horneado_prestado:
            celda, _tile = horneados.pop(evento)
            game_map.upper_layer[celda] = rm2k.UPPER_BASE
        capas = sin_horneado
        if horneados:
            capas, horneados = _hornear_si_no_mueve_la_cgram(
                renderer, game_map, map_id, sin_horneado, horneados)
    (tile_data, cram, tilemap, summary), above_data = capas
    if horneados:
        print("  map %d: %d opaque event(s) baked into the map: %s"
              % (map_id, len(horneados),
                 ", ".join(str(e + 1) for e in sorted(horneados))))
    for evento, tile in descartados:
        aviso_de_descarte(
            "map %d: event %d, drawn with tile %s, doesn't fit in "
            "the %d sprite palettes and isn't drawn"
            % (map_id, evento + 1, tile[len(rm2k.TILE_PREFIX):],
               tope_de_paletas),
            cambia_de_grafico(game_map.events[evento]))
    # Who changes pose and therefore carries their twelve to the cartridge:
    # the leader candidates with a graphic and the NPCs that walk. In that
    # order, with the initial leader first, which is the order the rest
    # expects.
    actores_con_grafico = []
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        if not sprite_colors(images_de(renderer, args, a.charset),
                             a.charset_index):
            continue            # not a single opaque pixel: it isn't drawn
        actores_con_grafico.append(actor)
    primero = renderer.database.leader(args.lideres)   # (CharSet, index)
    animados = []
    for actor in actores_con_grafico:
        a = renderer.database.actors[actor]
        if (a.charset, a.charset_index) not in animados:
            animados.append((a.charset, a.charset_index))
    animados.sort(key=lambda par: par != primero)   # the initial leader first
    for npc in npcs:
        if npc["evento"] in movibles \
                and (npc["charset"], npc["index"]) not in animados:
            animados.append((npc["charset"], npc["index"]))
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
    grafico_se_ve = []
    for charset, index in graficos_de_ruta:
        # It is drawn if it has an opaque pixel **and** it made it into the
        # palette split. The second is almost always yes; when not, the
        # command hides it just like a transparent one, which is what the ROM
        # does with any graphic that didn't make it.
        grafico_se_ve.append(
            bool(sprite_colors(images_de(renderer, args, charset), index))
            and (charset, index) in reparto[1])
        if grafico_se_ve[-1] and (charset, index) not in animados:
            animados.append((charset, index))
    # And the ones that turn toward the hero: their twelve poses, to upload
    # the one facing it. They go at the end so as not to move anyone else's
    # index.
    for pares in giran.values():
        for par in sorted(pares):
            if par in reparto[1] and par not in animados:
                animados.append(par)
    afuera_de_ruta = [par for par, se_ve in zip(graficos_de_ruta, grafico_se_ve)
                      if not se_ve and sprite_colors(
                          images_de(renderer, args, par[0]), par[1])]
    for charset, index in afuera_de_ruta:
        aviso_de_descarte(
            "map %d: graphic %s:%d, which a route changes to, doesn't fit "
            "in the %d sprite palettes: that command hides the event instead "
            "of changing it" % (map_id, charset, index, tope_de_paletas),
            # A command 34 **is** a graphic change, so it always counts.
            True)

    # The slots of the VRAM bank, one pose each: the hero in block 0 —if some
    # leader candidate has a graphic—, then each NPC that walks with its own,
    # and the still ones shared by (CharSet, index, pose), which never change.
    # An NPC that walks doesn't share even with an identical one: each changes
    # pose on its own.
    ranuras = []
    if actores_con_grafico:
        charset, index = animados[0]
        ranuras.append(("heroe", charset, index, POSE_INICIAL))
    for npc in npcs:
        if npc["evento"] in movibles:
            if npc["cambia"]:
                # Two mechanisms on the same row: the cartridge's twelve poses
                # and the page's graphic. The ROM doesn't know both at once, so
                # **walking wins** and its graphic stops following the page. It
                # is the same it did before `collect_npcs` counted "nothing" as
                # a state —see `cambia` there—, that is nothing that used to
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
                # loading the map no page qualifies. See `grafico_de_pagina` in
                # tools/runtime/paginas_de_eventos.s.
                npc["aparece"] = True
                npc["cambia"] = False
            ranuras.append((("ev", npc["evento"]), npc["charset"],
                            npc["index"], npc["pose"]))
        else:
            # The pose of its row and, if the graphic follows the page, that of
            # each page: the ROM's refresh chooses between slots that are
            # already in VRAM.
            poses = [(npc["charset"], npc["index"], npc["pose"])]
            if npc["cambia"]:
                poses += [g for g in npc["graficos"]
                          if g is not None and g[:2] not in npc["afuera"]]
            for clave in poses:
                if clave not in {r[0] for r in ranuras}:
                    ranuras.append((clave,) + clave)
    # The turn slot: one more pose, for the still one that turns toward the
    # hero. The still ones share a slot by (CharSet, index, pose), so turning
    # its own would also turn the others that use it; the one that turns
    # moves to this one while its page lasts. It is a single one because only
    # the event the hero triggered turns, and there is one at a time. The
    # ones that walk or animate don't need it: they have their own. See TURN
    # in eventos.py.
    quietos_que_giran = [npc for npc in npcs
                         if npc["evento"] in giran
                         and npc["evento"] not in movibles
                         and any(par in reparto[1]
                                 for par in giran[npc["evento"]])]
    if quietos_que_giran:
        npc = quietos_que_giran[0]
        ranuras.append(("giro", npc["charset"], npc["index"], npc["pose"]))
    personajes = list(animados)
    for _clave, charset, index, _pose in ranuras:
        if (charset, index) not in personajes:
            personajes.append((charset, index))

    images = {}
    for charset, _index in personajes:
        if charset not in images:
            # Through the renderer's loader, which also builds the CharSet of
            # an event drawn with a chipset tile.
            images[charset] = renderer.charsets.get(charset)
            if images[charset] is None:
                sys.exit("can't find CharSet %r" % charset)

    tiles, palettes, where, paleta_de, colores = build_characters(
        images, personajes, ranuras, reparto)
    # It is counted here and not inside because the message has to name the
    # culprit, which is the map. With `npcs_dibujables` above this shouldn't
    # fail because of a tile anymore; if it fails it is because of the
    # CharSets.
    if len(palettes) > tope_de_paletas:
        sys.exit("the map uses %d characters in %d palettes and there are %d "
                 "sprite ones" % (len(personajes), len(palettes), tope_de_paletas))
    bancos = banco_de_poses(images, animados, colores)
    indice_animado = {p: k for k, p in enumerate(animados)}
    # The table of command 34: for each graphic a route asks for, which entry
    # of `npc_poses` it is in and with which palette. $FF in the entry is
    # "hide the row", which is what a transparent CharSet does.
    ruta_graficos = [
        (indice_animado[par], paleta_de[par]) if se_ve else (0xFF, 0)
        for par, se_ve in zip(graficos_de_ruta, grafico_se_ve)]
    # The timer, if this ROM carries it: its glyphs go at the end of the bank
    # and share a palette with whoever has room, which there almost always is.
    timer_base, timer_pal = 0, None
    if map_id in args.timer_en:
        from port import ventana as ventana_mod
        sys_img = ventana_mod.skin(args.game_dir, renderer.database.system_name)
        tiles, timer_base, timer_pal = digitos_del_timer(
            sys_img, tiles, palettes, reparto[3],
            tope_de_paletas)
    lluvia_base, lluvia_pal = 0, 0
    if args.con_lluvia:
        tiles, lluvia_base, lluvia_pal = gotas_de_lluvia(
            tiles, palettes, reparto[3],
            timer_base, tope_de_paletas, timer_pal)
        if not lluvia_base:
            print("  map %d: WARNING, the raindrops don't fit in the "
                  "sprite palettes and it doesn't rain here" % map_id)
    # The `ShowPicture` picture, if its own belongs to this map. The slot is
    # chosen by `Imagenes.elegir` **in the order of the map table**, which is
    # this same loop.
    imagen_base, imagen_pal = 0, 0
    registro = getattr(args, "imagenes", None)
    if registro is not None:
        info = registro.elegir([game_map])
        if info is not None and registro.mapa is None:
            registro.mapa = map_id
        if info is not None and registro.mapa == map_id:
            tiles, imagen_base, imagen_pal = cartel_de_imagen(
                info, tiles, palettes, lluvia_base or timer_base)
            if not imagen_base:
                sys.exit("map %d: the picture %r doesn't fit: the map already uses "
                         "the %d sprite palettes and the fade needs a whole "
                         "one. See `cartel_de_imagen`."
                         % (map_id, registro.nombre, OBJ_PALETTES))
            print("  map %d: the picture %r, %d objects in %d tiles from "
                  "%d, palette %d" % (map_id, registro.nombre,
                                      info["objetos"],
                                      imagen.tiles_reservados(info),
                                      imagen_base, imagen_pal))
    # And the battle animation box, if some page of this map can show one that
    # is drawn. It goes last because it takes the end of the bank and the
    # palette left free after the picture. The criterion for it to fit is a
    # computation and the converter emits it: if there is no palette or no
    # VRAM, **this map doesn't draw animations** and says so.
    anim_base, anim_pal = 0, 0
    if muestra_animacion:
        probando, probando_base, probando_pal = animacion_de_mapa(
            tiles, palettes, 1 if imagen_base else 0)
        if not probando_base:
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
            cuantos = len(probando) // 32
            try:
                layout = vram_layout(len(tile_data) // BYTES_PER_TILE, cuantos,
                                     len(above_data[0]) // 32)
            except SystemExit:
                layout = None
            if layout is None or cuantos > layout["sprites"][1]:
                sys.exit(
                    "map %d: shows battle animations and the %d tiles of its "
                    "box don't fit in the sprite bank: it spends %d of %d. "
                    "See `animacion_de_mapa`."
                    % (map_id, animacion_mod.TILES, cuantos,
                       layout["sprites"][1] if layout else 0))
            tiles, anim_base, anim_pal = probando, probando_base, probando_pal
            print("  map %d: battle animations are drawn in %d "
                  "tiles from %d, palette %d"
                  % (map_id, animacion_mod.TILES, anim_base, anim_pal))
    # And the rows of the baked events start hidden: their tile is already
    # drawn in the map. The row is still whole —the event triggers, blocks the
    # way and is the target of a route like any other—, and `build_oam` skips
    # it without building an object, which is what is being saved.
    # `tile_pasa` is left set on purpose: the cell is already resolved by the
    # map's table with the same bits, and if a page ever showed this row
    # again, the data it needs is there.
    for npc in npcs:
        if npc["evento"] in horneados:
            npc["visible"] = False
    table = npc_table(npcs, where, movibles, indice_animado, anima_quieto)
    # For each leader candidate, its palette and which pose bank its twelve
    # are in. The ROM computes nothing from the pose: it looks up the pointer
    # here and queues it.
    actores = []
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        if actor not in actores_con_grafico:
            # An actor with an empty graphic. `DummyHero`, 10, is like that:
            # its eight poses don't have an opaque pixel, and RM2k draws
            # nothing. It goes with the sentinel pointer and the ROM skips the
            # object.
            actores.append((actor, 0, None, []))
            continue
        # Its colors, in the same order as the `lookup` its poses were packed
        # with: `paleta_del_personaje` returns the sorted palette and
        # `build_characters` indexes 1..15 over it. If the two orders drifted
        # apart, the hero would come out with its colors swapped around.
        propia, _, _ = paleta_del_personaje(
            images[a.charset], a.charset_index)
        actores.append((actor, paleta_de[(a.charset, a.charset_index)],
                        indice_animado[(a.charset, a.charset_index)],
                        [cgram_word(c) for c in propia]))
    giro_tile = (block_tile(where["giro"][0]) if "giro" in where
                 else GIRO_NINGUNO)
    sprite = (tiles, palettes, where, table, actores, timer_base, timer_pal,
              animados, bancos, ruta_graficos, lluvia_base, lluvia_pal,
              giro_tile, imagen_base, imagen_pal, anim_base, anim_pal)

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
    ocupadas = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
    start_x, start_y = inicio_del_mapa(
        renderer, map_id, passable, game_map.width, game_map.height, ocupadas)
    collision = (passable, start_x, start_y, game_map.width, game_map.height)

    if len(table) > NPC_MAX:
        sys.exit("map %d has %d NPCs and %d fit in OAM"
                 % (map_id, len(table), NPC_MAX))
    if len(ruta_graficos) > RUTA_GRAF_MAX:
        sys.exit("map %d has %d graphics of command 34 and %d fit: see "
                 "RUTA_GRAF_MAX" % (map_id, len(ruta_graficos), RUTA_GRAF_MAX))

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
          % (len(personajes), len(where), len(tiles) // 32, len(palettes),
             len(animados)))
    print("  %d NPCs with a CharSet out of %d events" % (len(table), len(game_map.events)))

    abiertos = sum(1 for b in passable if b == 0x0F)
    print("  collision: %d cells, %d open on all four sides (%.0f%%), "
          "the hero starts at (%d,%d)"
          % (len(passable), abiertos, 100.0 * abiertos / len(passable),
             start_x, start_y))

    print("  layer above the hero: %d tiles, %d colors in %d palette(s) "
          "from %d, %d merged"
          % (len(above_data[0]) // 32, len(above_data[1]) // 2,
             BG_PALETTES - above_data[3], above_data[3], above_data[4]))

    celdas, bloques, block_pass, block_terreno, combos = build_blocks(
        game_map, tilemap, above_data[2], passable,
        game_map.width, game_map.height, chipset)
    print("  the map fits in %d 16x16 blocks for %d cells: %d B of "
          "grid plus %d B of table, against the %d B of the expanded tilemap"
          % (len(bloques) // BLOCK_BYTES, len(celdas), 2 * len(celdas),
             len(bloques), 2 * summary["celdas"]))
    ventanas_x = (len(tilemap[0]) + WINDOW_W - 1) // WINDOW_W
    ventanas_y = (len(tilemap) + WINDOW_H - 1) // WINDOW_H
    if ventanas_x > 1 or ventanas_y > 1:
        print("  it doesn't fit in the %dx%d window: the ROM is going to redraw"
              % (WINDOW_W, WINDOW_H))

    words = bytearray()
    for cell in celdas:
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
        "graficos_de_ruta": graficos_de_ruta,
        "collision": collision, "celdas": bytes(words),
        "ev_pos": ev_pos_bytes(game_map),
        # Both grow while the pages are compiled, if some substitutes tiles:
        # see `Sustituciones`. That is why they are mutable and are frozen
        # only when emitted.
        "bloques": bloques, "pass": block_pass, "terreno": block_terreno,
        "combos": combos,
        # The terrain of a cell **outside the map**: `GetTerrainTag` uses the
        # ChipSet's index 0, that is the first autotile, and not that of any
        # cell. See `op_terrain`.
        "terreno_fuera": rm2k.terreno_de(chipset, 0),
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
        "giro_k": {par: indice_animado[par] for par in animados},
        "giran": set(giran),
        "cambian": {npc["evento"] for npc in npcs if npc["cambia"]},
        # And the ones that only appear and disappear with it: the ones that
        # walk, whose graphic was pinned further up.
        "aparecen": {npc["evento"] for npc in npcs if npc.get("aparece")},
        "afuera": {npc["evento"]: npc["afuera"] for npc in npcs},
    }


if __name__ == "__main__":
    main()

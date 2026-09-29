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
lcf.DECORAR_TRANSLUCIDO = rm2k.decorar_translucido
# And the text boxes, rebuilt for the SNES window: see
# `lcf.REAJUSTAR_TEXTOS` and `port/textos.py`.
from port import textos
lcf.REAJUSTAR_TEXTOS = textos.reajustar_comandos
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
from comun import perillas
from comun import proyecto
from comun.paralelo import en_paralelo
from audio import snes_music
from port.asignador import CELL, tile_colors
from port.formato_snes import cgram_word, entry, pack_tile
from rpgmaker.rm2k import TILE, collect_npcs, hero_start, passability_map
from render.render_map import Renderer, build_passability, load_image
from comun import ambiente
from rpgmaker import recursos
from rpgmaker.recursos import find_resource

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
# the suite charged 79 pixels in the text lines. What rules is the highest
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
    pesos = perillas.valor("graphics", "palette_weight", tipo=dict)
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
    """The `ShowPicture` sign at the end of the sprite bank: its tiles and **a
    whole palette just for it**.

    It shares a palette with nobody, unlike the timer and the drops, and not
    for lack of room: the sign's fade is a tint of its fifteen CGRAM entries
    frame by frame, so a character put in that palette would fade out and back
    in with it.

    And it goes **above `SPRITE_CGRAM`**, that is outside the range
    `aplicar_tinte` and `subir_paletas` walk. That is not shuffling numbers: in
    RM2k pictures have `affected_by_tint` off by default
    —`Priority_PictureOld` is 120 and `Priority_Screen` 90—, so the screen tint
    doesn't touch them. Being outside the range, nobody has to remember to
    skip them.

    Returns (tiles, base, palette number), or (tiles, 0, 0) if the map already
    uses the eight sprite palettes: then this map doesn't draw the sign.
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

    It shares a palette with nobody for the same reason as the sign: the
    fifteen colors belong to the animation, are uploaded when it starts and
    overwritten when another starts, and a character put there would change
    color with it. And it goes **above `SPRITE_CGRAM`**, that is outside the
    range `aplicar_tinte` and `subir_paletas` walk, which is also the faithful
    thing: in `Spriteset_Map::Update` the map's tone goes to the tilemap, the
    characters, the panorama and the shadows, and not to the animations.

    The tiles are reserved **blank**: what goes inside is uploaded by the ROM
    via DMA frame by frame, from the cartridge. See `animacion.py`.

    Returns (tiles, base, palette number), or (tiles, 0, 0) if the map already
    uses the eight sprite palettes. `usadas` are the ones the sign already
    took.
    """
    cual = len(palettes) + usadas
    if cual >= OBJ_PALETTES:
        return bytes(tiles), 0, 0
    tiles = bytearray(tiles)
    # After everything else: the timer, the drops and the sign already grew
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
      `rpgmaker/recursos.py` goes with them because it is where `render_map`
      gets how it finds the ChipSet, and `comun/proyecto.py` because it is
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
        from comun import cache_disco
        _VERSION_CAPAS = (cache_disco.version_de("port/snes_convert.py",
                                                 "port/asignador.py",
                                                 "rpgmaker/rm2k.py",
                                                 "render/render_map.py",
                                                 "rpgmaker/recursos.py",
                                                 "comun/proyecto.py",
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
    from comun import cache_disco
    insumos = renderer.insumos_de_capas(game_map)
    en_disco = None
    if insumos is not None:
        en_disco = cache_disco.clave(_version_capas(), *insumos)
        if en_disco in _capas_en_memoria:
            return _capas_en_memoria[en_disco]
        hecho = cache_disco.leer("capas", en_disco)
        if hecho is not None:
            _capas_en_memoria[en_disco] = hecho
            return hecho
    base, above_img, variantes = renderer.capas_animadas(game_map)
    if base is None:
        return None
    hecho = _convert_layers(base, above_img, variantes)
    if en_disco is not None:
        cache_disco.guardar("capas", en_disco, hecho)
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
    """Cuántos caracteres entran en una línea. Vive en `ventana.py` con el
    resto de la geometría, y el porqué del número está ahí."""
    from port import ventana as ventana_mod
    return constantes.COLUMNAS


def _quince(imagen):
    """Los pixeles de una imagen RGBA como colores de 15 bits, sobre negro."""
    from PIL import Image
    llana = Image.alpha_composite(
        Image.new("RGBA", imagen.size, (0, 0, 0, 255)), imagen).convert("RGB")
    return [tuple(v >> 3 for v in p) for p in llana.get_flattened_data()]


def convert_ventana(sys_img, font_id=None):
    """La ventana de mensaje: tiles, paleta, celdas y lo que la fuente necesita.

    La imagen la arma `ventana.py`, que sigue las reglas de easyrpg-player y
    está verificada contra una captura del juego original corriendo en
    EasyRPG.
    Acá se la corta en celdas de 8x8 y se separa lo fijo de lo que la ROM
    compone.

    La paleta lleva los colores de la ventana vacía **más** los del texto y la
    sombra, aunque la ventana vacía no los use: son los que la ROM va a
    escribir. El índice 0 queda libre a propósito, que es el transparente de
    BG2 y ningún tile de la ventana lo usa.

    Devuelve un dict con:
        tiles     los de la ventana vacía, deduplicados
        cram      las 16 palabras de la paleta
        celdas    el tilemap de 32x10, con los tiles de texto ya numerados
        fondo     los 240 tiles del área de texto, sin texto, en orden
        color     el índice de paleta de cada una de las 12 filas del glifo
        sombra    el índice de la sombra
    """
    from port import fuente as fuente_mod
    from port import ventana as ventana_mod

    if font_id is None:
        font_id = fuente_mod.MINCHO
    vacia = ventana_mod.ventana(sys_img)
    pixeles = _quince(vacia)
    ancho, alto = vacia.width, vacia.height

    # Los colores del texto salen del bloque de 16x16 del System, y son los que
    # `Font::Render` usa como máscara. Cada fila del glifo toma uno solo —está
    # medido: el degradé es horizontal-uniforme— así que son doce colores, no
    # un bloque, y la sombra es uno solo.
    bloque = ventana_mod.color_de_texto(sys_img, 0)
    sombra_img = ventana_mod.color_de_sombra(sys_img)
    ox, oy = ventana_mod.TEXTO_OFS
    color_fila = []
    for py in range(fuente_mod.ALTO):
        fila = {tuple(v >> 3 for v in bloque.getpixel((ox + px, oy + py))[:3])
                for px in range(fuente_mod.ANCHO)}
        if len(fila) != 1:
            raise SystemExit(
                "la fila %d del color de texto tiene %d colores distintos; la "
                "ROM la compone con uno solo" % (py, len(fila)))
        color_fila.append(fila.pop())
    sombra = tuple(v >> 3 for v in sombra_img.getpixel((0, 0))[:3])

    colores = sorted(set(pixeles) | set(color_fila) | {sombra})
    if len(colores) > COLORS_PER_PALETTE - 1:
        raise SystemExit("la ventana usa %d colores y entran %d"
                         % (len(colores), COLORS_PER_PALETTE - 1))
    indice = {c: i + 1 for i, c in enumerate(colores)}

    def celda_de(tx, ty):
        return tuple(tuple(indice[pixeles[(ty * 8 + y) * ancho + tx * 8 + x]]
                           for x in range(8)) for y in range(8))

    # Las celdas que no llevan texto se deduplican como siempre; las del área de
    # texto se numeran de corrido a partir de ahí.
    tiles, celdas = {}, []
    for ty in range(alto // 8):
        fila = []
        for tx in range(ancho // 8):
            if (VENTANA_TEXTO_FILA <= ty < VENTANA_TEXTO_FILA + VENTANA_TEXTO_FILAS
                    and VENTANA_TEXTO_COL <= tx < VENTANA_TEXTO_COL + VENTANA_TEXTO_COLS):
                fila.append(None)       # se numera abajo, cuando se sepa cuántos
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
        raise SystemExit("la ventana necesita %d tiles y el banco tiene 256"
                         % (base + len(fondo)))

    datos = b"".join(pack_tile(celda, planes=4)
                     for celda, _ in sorted(tiles.items(), key=lambda kv: kv[1]))
    cram = [0] + [cgram_word(c) for c in colores]
    cram += [0] * (COLORS_PER_PALETTE - len(cram))
    # El fondo arranca donde termina esto, así que si la ventana creciera se le
    # metería encima y la ROM dibujaría el texto con un color del mapa. Se mira
    # el índice más alto que se usa de verdad —el de la sombra o el de alguna
    # fila del glifo— y no cuántas palabras son distintas de cero: un color
    # negro tiene palabra cero y no se contaría.
    alto = max([indice[c] for c in color_fila] + [indice[sombra]])
    if alto >= CGRAM_RESERVADAS:
        raise SystemExit(
            "la ventana de mensaje usa la entrada %d de CGRAM y el fondo "
            "arranca en la %d: subí CGRAM_RESERVADAS" % (alto, CGRAM_RESERVADAS))
    return {"tiles": datos, "cram": cram, "celdas": celdas,
            "base": base,
            "fondo": b"".join(pack_tile(c, planes=4) for c in fondo),
            "color": [indice[c] for c in color_fila],
            "sombra": indice[sombra]}


def fuente_bytes(font_id):
    """Los 95 glifos ASCII, doce filas de seis bits cada uno.

    Es la misma tabla que `tools/port/fuente.py`, que se genera desde
    easyrpg-player, pero **con los bits dados vuelta**: allá el bit 0 es el
    pixel de la izquierda y en el formato de tiles de la consola el de la
    izquierda es el bit 7. Darlos vuelta acá y no en la ROM sale gratis: es una
    tabla de 1140 bytes que se genera una vez.
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


# Los glifos de la ventana ya compuestos, para cada una de las cuatro fases en
# que puede caer un carácter: la x es `VENTANA_BORDE + 6 * columna`, así que
# módulo 8 da 0, 6, 4 o 2 y nunca otra cosa. Por glifo y fase van las filas
# de celda de `FUENTE_PRE_FILAS` que toca —las doce del glifo desde
# `TEXTO_OFS_Y`, y una más de sombra— y por fila las dos celdas que puede
# pisar, cada una con tres palabras: qué se conserva del buffer, y qué se
# prende en los planos 0-1 y en los 2-3. La ROM hace
# `buf = buf & conservar | prender`, que es lo que antes calculaba en cada
# fila con `pintar`, dos veces —sombra y glifo— y con un corrimiento de a un
# bit. Ver `componer_char`.
#
# La sombra y el glifo van ya combinados, con la regla del orden de
# `Font::Render`: en una fila cae el glifo de dos filas más arriba y la sombra
# del de tres, corrida un pixel, y donde se pisan gana el glifo.
FUENTE_PRE_FILAS = FUENTE_ALTO + 1
FUENTE_PRE_CHAR = FUENTE_PRE_FILAS * 2 * 6


def fuente_prerender(fuente, colores, sombra):
    """Las cuatro tablas, una por fase (0, 2, 4 y 6), en ese orden."""
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
    """El mapa como índices a bloques de 16x16, con su tabla.

    Devuelve (celdas, tabla de bloques, pasabilidad por bloque, combinaciones).
    Las celdas van fila por fila, que es como las recorre la ROM.

    Las **combinaciones** son `(tile de abajo, tile de arriba) -> bloque`, con
    los ids de RM2k y no con nada de la consola. No participan de la clave del
    bloque, así que no cambian un solo byte de lo que sale: son lo que
    `TileSubstitution` necesita para saber a qué bloque va a dar un tile que se
    sustituye por otro, porque el bytecode habla de tiles y la ROM de bloques.
    Un bloque es exactamente una celda de 16x16 de RM2k, así que la
    correspondencia existe.
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
                   # El terreno entra en la clave por lo mismo que la
                   # pasabilidad: dos celdas que se dibujan igual pueden venir
                   # de tiles con distinto terreno, y la ROM lo lee por bloque.
                   # No parte un bloque de más en este juego, donde el terreno
                   # de todos los ChipSets es 1.
                   rm2k.terreno_de(chipset, abajo) if chipset else 1)
            if key not in blocks:
                blocks[key] = len(blocks)
            cells.append(blocks[key])
            combos.setdefault((abajo,
                               game_map.upper_layer[by * width + bx]),
                              blocks[key])

    if len(blocks) > MAX_BLOCKS:
        raise SystemExit("el mapa usa %d bloques distintos y la tabla no puede "
                         "pasar de %d" % (len(blocks), MAX_BLOCKS))

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
            raise SystemExit("un tile con terreno %d y la tabla de la ROM "
                             "lleva un byte por bloque" % terreno)
        terreno_bytes[number] = terreno
    return cells, table, pass_bytes, terreno_bytes, combos


# Cuántos pares de bloques puede tener puestos a la vez la tabla de
# sustituciones de la ROM. Es `SUB_MAX` en tools/runtime/ram_baja.s y está escrito de los dos
# lados a propósito —el conversor tiene que poder negarse **antes** de emitir
# un mapa que no entre—; la prueba `test_sustitucion.py` compara los dos.
SUB_MAX = 8


class Sustituciones:
    """`TileSubstitution` traducido de tiles de RM2k a bloques de la ROM.

    RM2k sustituye por **número de tile**: todas las celdas del mapa que
    dibujen el tile viejo pasan a dibujar el nuevo. En la ROM no hay tiles de
    RM2k, hay bloques de 16x16 que llevan las dos capas y la pasabilidad
    juntas, así que una sustitución de RM2k son tantos pares de bloques como
    combinaciones de (abajo, arriba) del mapa lleven ese tile. Cuáles son se
    sabe al convertir, que es por qué esto vive acá y no en `eventos.py`.

    El bloque de destino puede no existir —nadie dibujó esa combinación en
    ningún lado del mapa— y entonces se arma: las cuatro celdas de 8x8 de la
    capa que cambia salen de otro bloque que ya dibuje el tile nuevo, las de
    la otra capa salen del bloque de origen, y la pasabilidad se recalcula con
    las mismas reglas de RM2k. De ahí sale el único límite de verdad que esto
    tiene: **el tile nuevo tiene que estar dibujado en alguna celda del mapa**,
    en su capa. Si no está, sus 8x8 no entraron en la VRAM y no hay con qué
    dibujarlo; la página no compila y se dice por qué.

    Los bloques se arman todos **antes** de compilar ninguna página, y no a
    medida que aparecen los comandos: las sustituciones se encadenan —prender
    es 80→80A y apagar es 80A→80— así que el bloque que necesita una lo crea
    otra, y en qué orden se compilan las páginas no puede decidir qué compila.
    """

    def __init__(self, mapa, flags, chipset):
        self.mapa = mapa
        self.flags = flags
        self.chipset = chipset
        self.combos = mapa["combos"]
        # Las cuatro celdas de 8x8 con que se dibuja cada tile de RM2k, por
        # capa. Salen de los bloques que ya hay: un tile que el mapa no dibuja
        # en ningún lado no está acá y no se puede sustituir hacia él.
        self.celdas = ({}, {})
        for (bajo, alto), bloque in self.combos.items():
            # **La mitad de abajo sólo sirve si el tile de arriba de ese bloque
            # no se hornea en ella.** Un tile de la capa alta **sin** el bit
            # "Above" no se dibuja en BG2 sino encima del fondo —es lo que
            # decide `draw_tiles`, y por eso hay tiles altos cuya mitad de BG2
            # sale vacía—, así que la mitad de abajo de ese bloque es la
            # composición de los dos y no el tile de abajo solo. Copiarla para
            # armar otra combinación dibujaría el tile alto del vecino.
            if not self._hornea(alto):
                self.celdas[0].setdefault(bajo, self._mitad(bloque, 0))
            self.celdas[1].setdefault(alto, self._mitad(bloque, 1))
        # Los bloques que alguna sustitución del mapa usa como clave, que es
        # lo que va a ocupar lugar en la tabla de la RAM.
        self.claves = set()
        # Y los bloques por contenido, para deduplicar los que se arman igual
        # que `build_blocks` deduplica los del mapa. No es por ahorrar lugar:
        # dos combinaciones que ya comparten bloque —los dos autotiles de agua
        # del mapa 6 dibujan lo mismo— tienen que seguir compartiéndolo después
        # de sustituir, o la sustitución mandaría un solo bloque a dos lados y
        # no se podría expresar.
        self.por_bytes = {}
        for bloque in range(len(mapa["pass"])):
            self.por_bytes.setdefault(self._huella(bloque), bloque)

    def _hornea(self, alto):
        """Si ese tile de la capa alta se hornea en el fondo en vez de ir a BG2.

        Es la cuenta de `draw_tiles`: un tile alto va por encima del héroe
        —o sea a BG2— sólo con el bit `Above` puesto, y sin él se dibuja
        pegado al fondo. El tile vacío no dibuja nada y no hornea nada.
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
        """Los ids de RM2k del tile que sale y del que entra."""
        base = rm2k.UPPER_BASE if capa_alta else rm2k.LOWER_BASE
        return base + viejo, base + nuevo

    def pares(self, capa_alta, viejo, nuevo):
        """Los `(bloque viejo, bloque nuevo)` de una sustitución, o None.

        None es "esta página no compila", que es lo que `eventos.py` espera de
        un comando que no se puede hacer.
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
                return None     # lo tenía que haber creado `cerrar`
            if vistos.setdefault(bloque, nuevo_bloque) != nuevo_bloque:
                # Dos combinaciones distintas que dibujan igual y tienen los
                # mismos permisos comparten bloque, y ahí la sustitución no se
                # puede expresar: el bloque tendría que ir a dos lados. No
                # pasa con ningún ChipSet del juego —dibujar igual quiere decir
                # ser el mismo tile— pero si pasara, sustituir sería cambiar
                # celdas que RM2k no toca.
                return None
            salida.append((bloque, nuevo_bloque))
        if len(salida) > 0xFF:
            return None         # el operando de la cuenta es de un byte
        self.claves.update(par[0] for par in salida)
        return salida

    def cerrar(self, triples):
        """Arma los bloques que van a hacer falta, y devuelve qué no se pudo.

        `triples` son los `(capa alta, viejo, nuevo)` de todas las
        `TileSubstitution` del mapa. Se repite hasta que ninguna crea un bloque
        nuevo, porque el bloque que crea una es el origen de la siguiente.
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
        """El bloque de una combinación que el mapa no dibuja en ningún lado.

        None es "esta combinación no se puede armar sin volver a dibujar el
        mapa". Pasa cuando el tile de arriba se hornea en el fondo: ahí las dos
        mitades del bloque no son independientes y no hay de dónde sacar la de
        abajo. Ver `_hornea`.
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
                    "el mapa %d se pasa de %d bloques armando los que "
                    "`TileSubstitution` necesita"
                    % (self.mapa["id"], MAX_BLOCKS))
            self.mapa["bloques"] += huella[0]
            self.mapa["pass"].append(huella[1])
            self.mapa["terreno"].append(huella[2])
            self.por_bytes[huella] = numero
        self.combos[combinacion] = numero
        return numero


def triples_de_sustitucion(game_map, casos, map_id):
    """Los `(capa alta, viejo, nuevo)` de todas las `TileSubstitution` que
    pueden llegar a correr en este mapa: las de sus eventos y las de los casos
    de prueba que arrancan acá —que viven en el mapa de arranque pero se
    compilan con el contexto de éste, ver `mapa_del_caso`—."""
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


# El registro de un mapa en la tabla. El paso es potencia de dos para que pasar
# de índice a desplazamiento sean corrimientos y no una multiplicación, y sobra
# lugar a propósito: agregar un campo no tiene que mover nada de lo que ya está.
#
# Los punteros van de a cuatro bytes aunque midan tres. El byte que sobra no se
# usa; lo que se gana es que la parte baja de cada puntero caiga siempre en una
# dirección par, que es como se la lee con el acumulador en 16 bits.
MAPA_STRIDE = 128
MAPA_ESCALARES = [
    ("MAP_BW", "ancho en celdas de 16x16"),
    ("MAP_BH", "alto en celdas de 16x16"),
    ("CAM_MAX_X", "hasta dónde llega la cámara sin salirse"),
    ("CAM_MAX_Y", ""),
    ("HERO_MAX_X", "hasta dónde llega el héroe"),
    ("HERO_MAX_Y", ""),
    ("HERO_START_X", "dónde arranca, en pixeles"),
    ("HERO_START_Y", ""),
    ("VRAM_TILES", "el reparto de la VRAM, en palabras"),
    # Dónde va el tilemap del fondo. La base de la capa de encima no tiene
    # campo: es el nibble alto de BG12NBA_VALUE, y el registro está lleno.
    ("VRAM_MAP", ""),
    ("VRAM_SPRITE", ""),
    ("VRAM_VENTANA", "0 si esta ROM no lleva ventana de mensaje"),
    ("VRAM_VENTANA_MAP", "y su tilemap propio de 32x32"),
    ("MAP_TILES", "cuántos tiles de fondo, para el DMA"),
    ("MAP_CGRAM", "cuántas palabras de CGRAM"),
    ("ABOVE_TILES", ""),
    ("ABOVE_CGRAM", ""),
    ("SPRITE_TILES", ""),
    ("SPRITE_CGRAM", ""),
    ("NPC_COUNT", "cuántos NPCs con CharSet"),
    ("EV_COUNT", "cuántos eventos tiene el mapa, con o sin gráfico"),
    ("TIMER_BASE", "el primer tile de los dígitos del cronómetro, 0 si no hay"),
    ("LLUVIA_BASE", "el primer tile de las gotas de lluvia, 0 si no hay"),
    ("ACTOR_COUNT", "cuántos candidatos a líder del grupo"),
    ("PAGINA_COUNT", "cuántas páginas de evento hay que resolver"),
    ("RUTA_GRAFICO_COUNT", "cuántos gráficos distintos pide la orden 34"),
]
MAPA_BYTES = [
    ("OBSEL_VALUE", "objetos de 8x8 y 32x32, y la página de sus tiles"),
    ("BG12NBA_VALUE", "las páginas de tiles de BG1 y BG2"),
    ("ABOVE_FIRST", "en qué entrada de CGRAM arranca la capa de encima"),
    ("TIMER_PAL", "la paleta de sprite de los dígitos del cronómetro"),
    ("LLUVIA_PAL", "la paleta de sprite de las gotas de lluvia"),
    # Un byte y no un escalar porque el registro está en sus 128 justos. El
    # tile de un bloque es siempre múltiplo de cuatro y menor que 512.
    ("GIRO_TILE4", "el tile de la ranura de giro sobre cuatro, o $FF"),
    # El terreno, que es lo que `StoreTerrainID` contesta. Los dos son bytes
    # porque el terreno de RM2k es un índice de `Data.terrains` y no pasa de
    # 255, y porque el registro de mapa está en sus 128 justos.
    ("TERRENO_FUERA", "el terreno de una celda fuera del mapa"),
    ("TERRENO_PLANO", "el terreno de todo el mapa, o 0 si hay tabla"),
]
MAPA_PUNTEROS = ["map_tiles", "map_cgram", "above_tiles", "above_cgram",
                 "sprite_tiles", "sprite_cgram", "map_celdas", "map_bloques",
                 "bloque_pass", "bloque_terreno", "npc_table", "actor_table",
                 "paginas", "ev_pos", "npc_poses", "ruta_grafico",
                 # La animación del ChipSet: las dos corridas de tiles y sus
                 # dibujos. Ver `anim_bytes`.
                 "anim_tiles"]
MAPA_PTR_PASO = 4
# Dónde arrancan los punteros: justo después de los escalares y de los bytes,
# redondeado al paso. **Se calcula y no se escribe a mano**, porque escrito a
# mano ya falló: agregar un escalar más dejó `ABOVE_FIRST` y el primer puntero
# en el mismo desplazamiento, la ROM leyó el byte de la paleta como puntero a
# los tiles del mapa y la pantalla salió de un color plano.
#
# Es de las que no puede ver ninguna de las dos puntas: el ensamblador ve dos
# nombres distintos con el mismo valor, que es legal, y la comparación pixel a
# pixel dice "todo mal" sin decir dónde. La única defensa es que el número
# salga de los datos.
MAPA_PTR_BASE = (-(-(len(MAPA_ESCALARES) * 2 + len(MAPA_BYTES))
                   // MAPA_PTR_PASO) * MAPA_PTR_PASO)
assert MAPA_PTR_BASE + len(MAPA_PUNTEROS) * MAPA_PTR_PASO <= MAPA_STRIDE, \
    "el registro de mapa no entra en %d bytes" % MAPA_STRIDE

# Una página de evento: a qué evento pertenece, qué la activa, y dónde está su
# código. Las páginas de un mismo evento van seguidas y en orden, que es lo que
# le permite a la ROM elegir la última que cumple sus condiciones en una sola
# pasada, sin llevar una tabla por evento.
PAGINA_BYTES = 32
# Sin ranura de giro: el mapa no tiene ningún quieto que se dé vuelta.
GIRO_NINGUNO = 0xFFFF
# Un candidato a líder: id, paleta, **sus quince colores** y doce punteros de 24
# bits a sus poses. Los colores van adentro de la tabla y no en un bloque aparte
# porque son pocos actores por mapa y así la ROM los sube con un DMA desde donde
# ya está parada; ver `elegir_grafico_heroe`.
#
# Están porque los líderes **comparten una ranura de CGRAM**: lidera uno a la
# vez, así que reservarle una paleta a cada uno es tenerla ocupada por alguien
# que no está en pantalla. La ROM sube los del que lidera al cambiar el grupo y
# al cargar el mapa. Ver `npcs_dibujables`.
ACTOR_COLORES = 2 * OBJ_COLORS
ACTOR_BYTES = 2 + ACTOR_COLORES + 3 * 12

# Un bit por switch. El juego consulta hasta el 1003 en las condiciones de
# página, así que con 1024 alcanza y sobra: son 128 bytes de RAM.
SWITCH_BYTES = 128

# Cuántos gráficos distintos puede pedir la orden 34 en un mapa. La tabla se
# copia a la RAM al cargar el mapa, como la de NPCs, así que el tope cuesta
# bytes de los ocho kilos del banco 0 —dos por gráfico— y no puede ser
# generoso porque sí. **El mapa que más pide de todo el juego pide seis**,
# medido sobre los 328; ocho deja dos de aire y son dieciséis bytes. El
# conversor corta si algún mapa se pasa, así que no puede quedar corto en
# silencio.
RUTA_GRAF_MAX = 8


def campos_del_mapa(mapa):
    """Los valores del registro de un mapa, en el orden en que se emiten."""
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
        # Una más que los colores: el índice 0 del sprite es transparente y
        # también ocupa su lugar en CGRAM.
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
    """Los nombres de los campos del registro, para que tools/runtime/ no los repita.

    Que el conversor emita los desplazamientos y la ROM sólo los nombre es lo
    que hace imposible que se desincronicen: si acá se agrega un campo, allá no
    hay ningún número que actualizar.
    """
    out = ["; Dónde cae cada campo dentro del registro de un mapa."]
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
    """La tabla que la ROM recorre para saber qué cargar.

    `etiquetas` dice, por mapa, a qué bloque apunta cada puntero. Antes esto no
    existía y el nombre se rearmaba acá con `"%s_%d" % (nombre, numero)`, o sea
    con la misma cuenta que lo había emitido: dos lugares calculando el mismo
    nombre y ninguna manera de que un bloque fuera de más de un mapa.
    """
    out = ['.segment "RODATA"',
           "; La tabla de mapas: un registro de %d bytes por mapa, con todo lo"
           % MAPA_STRIDE,
           "; que la ROM necesita para cargarlo. Los punteros son de 24 bits",
           "; porque los datos viven repartidos por todos los bancos.",
           ";",
           "; **Vive en RODATA y se lee con `lda f:mapa_tabla + campo, x`.**",
           "; Son 144 bytes por mapa, y en el banco 0 —donde la tabla tiene que",
           "; estar si se la recorre con el registro de banco de datos— eso",
           "; alcanzaba para catorce mapas y nada más: con Lashe City entera son",
           "; 33 y el banco se pasaba por 3739 bytes. Es la tercera tabla que se",
           "; muda por la misma razón; el precio es un byte por instrucción y",
           "; que los dos usos con Y hayan tenido que pasar a X, porque el",
           "; direccionamiento absoluto largo indexado sólo existe con X.",
           ";",
           "; **Entera en un banco**, que es lo que pide el `.bloque`. En LoROM",
           "; lo que sigue a $03FFFF no es la ROM del banco 4 sino la RAM, y la",
           "; primera versión de esto cayó en $03FFB1: los 144 bytes del único",
           "; registro se partían al medio y el mapa 5 arrancaba en negro. Los",
           "; demás mapas de la tanda no lo veían porque su tabla caía en otro",
           "; lado, que es exactamente la clase de error que aparece al agregar",
           "; un byte en cualquier otra parte.",
           ".bloque %d" % (MAPA_STRIDE * len(mapas)),
           "mapa_tabla:"]
    for numero, mapa in enumerate(mapas):
        campos = campos_del_mapa(mapa)
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
        # Sin relleno no va la línea: un `.byte` sin operandos es un error
        # para `ca65`.
        if relleno:
            out.append("    .byte %s ; +%d  relleno hasta los punteros"
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
    # Y el id de RM2k de cada mapa, por índice: `MemorizeLocation` lo escribe
    # en una variable y `RecallToLocation` lo busca, porque en las variables
    # el mapa es el de RM2k —cualquier otra página las lee—. Va aparte y no
    # como escalar del registro porque el registro está en sus 128 justos.
    # Ver `op_location`.
    out += ["",
            "; El id de RM2k de cada mapa, en el orden de `mapa_tabla`.",
            ".bloque %d" % (2 * len(mapas)),
            "mapa_rm2k:",
            "    .word " + ", ".join(str(m["id"]) for m in mapas)]
    return "\n".join(out)


# El bloque de la animación del ChipSet: los dibujos, uno detrás del otro y en
# el orden de la VRAM —agua 0, 1, 2; animados 0 a 3—, sin cabecera.
#
# Dónde cae cada uno y a qué dirección de VRAM va no está adentro del bloque
# sino en `anim_tabla`, una entrada por mapa. Es para que la ROM no tenga que
# leer nada del cartucho para animar: la página directa está llena, así que un
# `lda [puntero], y` no tenía dónde vivir, y la alternativa —traer la cabecera
# por DMA a la WRAM— pedía cuarenta bytes de BSS que tampoco había. Con la tabla
# armada acá, la ROM indexa y dispara el DMA.
ANIM_STRIDE = 16
ANIM_FAM_STRIDE = ANIM_STRIDE // 2


def anim_bytes(animacion):
    """Los dibujos del mapa, uno detrás del otro. Vacío si no anima nada."""
    datos = bytearray()
    for familia, _ in FAMILIAS:
        corrida = animacion.get(familia)
        if corrida:
            for dibujo in corrida["dibujos"]:
                datos += dibujo
    return bytes(datos)


def anim_tabla(mapas):
    """Una entrada por mapa, con las dos corridas ya resueltas.

    Por familia, y en el orden en que la ROM las mira:

        +0 word  dirección de VRAM, en palabras
        +2 word  desplazamiento del dibujo 0 adentro del bloque
        +4 word  cuántos bytes mide un dibujo
        +6 byte  cuántos tiles son; 0 si esta familia no anima en este mapa
        +7 byte  relleno, para que la entrada de cada familia sea de ocho

    La dirección de VRAM sale de acá y no de una cuenta en la consola porque
    acá están las dos mitades: el reparto de la VRAM del mapa y en qué tile de
    su banco arranca la corrida.

    El relleno de la segunda familia —el byte +15 de la entrada— lleva **si el
    mapa tiene algún evento quieto con animación continua**. Va acá porque es
    lo mismo que el resto: algo por mapa que la ROM mira una vez por cuadro y
    que en el registro del mapa ya no entraba. Sin él, `animar_quietos` tendría
    que recorrer las cuarenta filas de NPC en todos los mapas.
    """
    out = ['.segment "RODATA"',
           "; La animación del ChipSet, una entrada de %d bytes por mapa."
           % ANIM_STRIDE,
           # `rom/src/` y no `tools/runtime/`, a propósito: va al `.inc`, y lo
           # que se emite no se toca todavía. Ver las-herramientas-se-separan-de-abl.md.
           "; Ver `anim_tabla` en tools/port/snes_convert.py y `anim_flush` en rom/src/animacion_del_chipset.s.",
           ";",
           "; **Vive en RODATA y se lee con `lda f:anim_tabla + campo, x`**, por",
           "; lo mismo que `mapa_tabla`: son 16 bytes por mapa, y con los mapas",
           "; que piden las pruebas el banco 0 se pasaba por 361. Entera en un",
           "; banco, porque lo que sigue a $xxFFFF no es la ROM del siguiente.",
           ".bloque %d" % (ANIM_STRIDE * len(mapas)),
           "anim_tabla:"]
    for mapa in mapas:
        animacion = mapa["resumen"]["animacion"]
        out.append("    ; --- mapa %d %r ---" % (mapa["id"], mapa["nombre"]))
        desplazamiento = 0
        for familia, cuantos in FAMILIAS:
            corrida = animacion.get(familia)
            tiles = corrida["tiles"] if corrida else 0
            vram = (mapa["layout"]["tiles"][0]
                    + (corrida["base"] if corrida else 0) * BYTES_PER_TILE // 2)
            out.append("    .word %-6d ; VRAM de %s" % (vram, familia))
            out.append("    .word %-6d ; el dibujo 0, adentro del bloque"
                       % desplazamiento)
            out.append("    .word %-6d ; bytes por dibujo"
                       % (tiles * BYTES_PER_TILE))
            relleno = 0
            if familia == FAMILIAS[-1][0]:
                relleno = 1 if any(n.get("anima")
                                   for n in (mapa["sprite"][3]
                                             if mapa["sprite"] else ())) else 0
            out.append("    .byte %d, %d   ; %d tile(s)%s"
                       % (tiles, relleno, tiles,
                          ", y el mapa tiene quietos que animan"
                          if relleno else ""))
            desplazamiento += tiles * BYTES_PER_TILE * cuantos
    return "\n".join(out)


def animaciones_de_la_rom(mapas, renderer):
    """Las animaciones de batalla que el bytecode ya emitido muestra, por
    número de RM2k, cada una convertida por `animacion.py`.

    Se recorre el bytecode y no los comandos, que es lo que hace que sea la
    verdad y no una conjetura: lo que cuenta es lo que quedó emitido, después
    de que el filtro de páginas decidiera cuáles entran. Es la misma regla de
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
    """Los 2 KB de un cuadro de animación de batalla tal como quedan en la VRAM:
    los 64 tiles de 4bpp de la caja, en orden."""
    datos = bytearray(animacion_mod.TILES * 32)
    for tile, celda in animacion_mod.celdas(cuadro).items():
        datos[tile * 32:(tile + 1) * 32] = pack_tile(celda, planes=4)
    return bytes(datos)


# El fin de un cuadro sin sus tiles vacíos: ningún tile de la caja llega a 64.
CUADRO_FIN = 0xFF


def cuadro_sin_vacios(datos):
    """Un cuadro de `cuadro_de_animacion` como lo guarda el cartucho: sólo sus
    tiles que no son todo cero, cada uno con su número delante, y `CUADRO_FIN`.

    Los cuadros son **casi todos transparencia**, así que guardarlos enteros
    era pagar ceros: lo medido está en la tarea
    `la-compresion-de-mapas-y-graficos.md`. Lo que queda en la VRAM no cambia:
    `anim_cuadro_armar` rearma los 2 KB en la RAM lejana y el vblank los sube
    enteros, como antes.
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
    """Las animaciones de batalla del cartucho, listas para el `.inc`.

    Cuatro cosas:

      `anim_batalla_de`      por número de RM2k, qué entrada le toca, o $FF.
                             Va por número y no por un índice nuestro para que
                             ninguna de las dos puntas tenga que llevar un
                             contador que la otra adivine.
      `anim_batalla_tabla`   por entrada: cuántos cuadros, dónde cae su ancla
                             adentro de la caja y en qué cuadro arranca.
      `anim_batalla_cuadros` por cuadro, el puntero de 24 bits a sus tiles sin
                             los vacíos: ver `cuadro_sin_vacios`. Uno por
                             cuadro y no un bloque seguido por animación, que
                             es de cuando cada cuadro medía 2 KB y 28 no
                             entraban en un banco.
      `anim_batalla_cgram`   sus dieciséis colores, que la ROM sube cuando la
                             animación empieza.
      `anim_batalla_reparto` por mapa, dónde y con qué paleta se dibuja acá, o
                             0 si este mapa no dibuja animaciones.
    """
    orden = sorted(animaciones)
    entrada = {numero: k for k, numero in enumerate(orden)}
    tope = (max(orden) + 1) if orden else 1
    out = [
        "\n; --- el dibujo de las animaciones de batalla ---",
        ";",
        "; La caja es una sola para toda la ROM y el porqué está en",
        "; tools/port/animacion.py: cuatro objetos de 32x32 en una fila de bloques",
        "; de la grilla de nombres, que es lo máximo que entra en la VRAM de",
        "; sprites que le queda libre al mapa 2. Lo que cambia por mapa es",
        "; dónde cae esa fila y con qué paleta, y eso va en",
        "; `anim_batalla_reparto`, un byte por mapa.",
        "ANIM_B_CAJA   = %d" % animacion_mod.CAJA,
        "ANIM_B_OBJ    = %d" % animacion_mod.OBJ,
        "ANIM_B_OBJETOS = %d" % animacion_mod.OBJETOS,
        "ANIM_B_TILES  = %d" % animacion_mod.TILES,
        "ANIM_B_BYTES  = %d" % (animacion_mod.TILES * 32),
        "ANIM_B_STRIDE = 8",
        "; Hasta qué número de animación llega `anim_batalla_de`: el bytecode",
        "; lleva el número de RM2k tal cual y uno más grande no está en la",
        "; tabla, así que la ROM lo compara antes de leerla.",
        "ANIM_B_MAX    = %d" % tope,
        "; El centro de la pantalla, que es donde caen las de alcance",
        "; `Scope_screen`: `DrawAt(screen_width / 2, screen_height / 2)`.",
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
        # El ancla **como la quiere la ROM**: con la corrida de
        # `Animation::Position` ya horneada, así que la consola sólo resta.
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
    # La tabla de punteros, con etiquetas: no puede salir de `bloque()`, pero
    # **sí se declara** con `.bloque` por lo mismo que la de páginas —la ROM la
    # lee con un puntero de 24 bits y no puede quedar a caballo de dos bancos—.
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
        # El bit 7 es "acá se dibuja", y abajo van el bloque de 64 tiles y la
        # paleta, de tres bits cada uno. En un byte porque el registro de mapa
        # está en sus 128 justos: ver MAPA_STRIDE.
        reparto.append((0x80 | ((base // 64) << 3) | pal) if base else 0)
    out.append(bloque("anim_batalla_reparto", bytes(reparto)))
    return "\n".join(out) + "\n"


def experiencia_ranuras(db, actores):
    """Los actores que llevan experiencia y nivel, en el orden de su ranura.

    Son los que pueden entrar al grupo —`ranuras["actores"]`—, porque sólo
    ellos pelean y la experiencia sólo se gana peleando: el juego no usa
    `ChangeExp` ni `ChangeLevel` en ningún mapa. Tener ranura propia y no una
    por número de actor es lo que hace que la partida crezca en cuatro bytes
    por actor que pelea y no por cada uno de los sesenta del LDB. **Siempre al
    menos una**, aunque sea de nadie: con cero el DMA del reset copiaría 64 KB.
    """
    return sorted(a for a in actores if a in db.actors) or [None]


def experiencia_asm(db, actores, actores_n):
    """Las tablas de la experiencia y del nivel: ver `port.experiencia`.

    Deja el segmento en RODATA, que es donde lo encuentra quien la llama.

    Por ranura de `experiencia_ranuras`:

        exp_inicial    cuatro bytes: la experiencia de arranque, de 24 bits,
                       y el nivel. Es lo que el reset copia a `FAR_EXP`.
        exp_nivel_max  `GetMaxLevel()`, un byte.
        exp_curva      dónde arranca su fila en `exp_tabla`, palabra.
        nivel_fila     seis palabras: dónde arranca en `nivel_params` cada
                       curva de parámetro, en el orden de `lcf.CURVAS`.

    `exp_tabla` es `MakeExpList` de cada curva distinta —cuatro bytes por
    nivel, `NIVEL_MAX` niveles— y `nivel_params` las seis curvas de cada
    ranura, `NIVEL_MAX` palabras cada una. Todo va fuera del banco 0: se lee
    al ganar una pelea, al armarla y en la pantalla de equipo, nunca por
    cuadro.
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
        for curva in lcf.CURVAS:
            filas.append(2 * len(params))
            valores = list(actor.params.get(curva) or []) if actor else []
            valores = (valores + [0] * X.NIVEL_MAX)[:X.NIVEL_MAX]
            params += [v & 0xFFFF for v in valores]
    if 4 * len(ranuras_exp) > 0x200:
        raise SystemExit("%d actores con experiencia no entran en los 512 "
                         "bytes de FAR_EXP" % len(ranuras_exp))
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


# Lo que va en las tablas de fondo en vez de un número de fondo: el liso —sin
# fondo, que es ceros— y "el del lugar", que la ROM resuelve al empezar la
# pelea con el mapa y el terreno. Ver `escena_de_la_rom`.
FONDO_LISO = 0xFF
FONDO_DEL_LUGAR = 0xFE


def escena_de_la_rom(db, tropas, mapas, tree, encuentros, game_dir):
    """Qué fondos y qué battlers lleva el cartucho, y quién usa cada uno.

    Es la otra mitad de tools/port/escena.py: allá está cómo se convierte un
    fondo o un battler, acá **cuáles**. Los fondos se nombran por su número
    en el juego —ver "Qué fondos hay" allá—, y una pelea pide el suyo de tres
    maneras:

    * **un `EnemyEncounter` que lo nombra**, y entonces es de la tropa —así
      funcionaba la escena horneada—. Si dos lo pidieran distinto para la
      misma tropa gana el primero, como en `Tropas.pedir`;
    * **un encuentro al azar en un mapa que lo hereda**, que es
      `TreeMap.map_background`: las áreas de los Back Alleys no traen fondo y
      lo sacan de su mapa;
    * **el del terreno que pisa el héroe**, si el mapa no nombra ninguno: el
      mundo, el 66. Ése lo resuelve la ROM al empezar la pelea, con
      `fondo_terreno`. Y un `EnemyEncounter` con el fondo "del lugar" hace lo
      mismo que un encuentro al azar: `FONDO_DEL_LUGAR`.

    Un fondo entra **en la ROM**, liviano, si alguna pelea del cartucho lo
    pide; si alguna puede caer en uno que no está —una tropa del lugar en un
    mapa sin encuentros—, entra también `escena.reemplazo()`, y `respaldo_de`
    dice cuál de la ROM usa cada fondo del juego. **En el `.msu` van todos**:
    `calidad` son sus bytes, por número.

    Un battler entra si lo usa alguna tropa del cartucho, **una vez** aunque lo
    usen cuatro, y es la imagen con su tono: la GiantRat y la HairyVermin son
    el mismo `BLmouse` y dos battlers.
    """
    E = escena_mod
    juego = E.fondos_del_juego(eventos.fondos_nombrados(game_dir), tree,
                               db.terrain_backdrops, game_dir)
    numero_de = {nombre.lower(): k for k, nombre in enumerate(juego)}
    if len(juego) >= FONDO_DEL_LUGAR:
        raise SystemExit("el juego tiene %d fondos de batalla y el número de "
                         "uno es un byte, con $%02X y $FF reservados"
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
    # El del mapa, para los encuentros al azar y para las tropas que pelean
    # con el del lugar. Sólo en los mapas donde alguna pelea lo puede mirar:
    # sin eso, cualquier cartucho pediría el reemplazo.
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

    # Los de la ROM: todos los que se piden, en el orden en que se piden —ver
    # "Qué fondos hay" en escena.py—. Un mapa con encuentros que pide el del
    # lugar pide los de todos los terrenos de sus bloques, que son los que el
    # héroe puede pisar, con las sustituciones incluidas. Un mapa sin
    # encuentros que igual lo pide —porque alguna tropa pelea con el del
    # lugar, y no se sabe dónde— no: si su terreno no está, va el reemplazo.
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
    # Los de calidad, para el `.msu`: todos, estén o no en la ROM.
    datos["calidad"] = en_paralelo(
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
    """Quién pide cada animación y cada battler del cartucho: por clase de
    parche, `{clave: [origen, ...]}`, donde el origen es el id del mapa cuya
    página o cuyo encuentro al azar lo pide, o `"caso"` si lo pide una página
    de prueba.

    Es lo que deja a `parches.revisar` saber qué no es del juego en la ROM que
    se juega, que lleva también los mapas y las páginas de la tanda: una
    animación que sólo pide un caso, o un battler que sólo aparece en un mapa
    de prueba, no se versiona. Se recorre el bytecode, como en
    `animaciones_de_la_rom`, así que cuenta lo que quedó emitido. Una tropa
    que alguien pidió y ninguna página emitida nombra —una página que se cayó
    después de pedirla— no tiene origen, y `revisar` la trata como del juego:
    la duda va para el lado de pedir el parche.
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
    """Un fondo de batalla como lo lee la consola: `(tiles, colores)`, sus 512
    tiles de 8bpp en el orden del tilemap y sus `COLORES` colores de 15 bits,
    rellenos con negro."""
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
    """El respaldo liviano de un fondo, como lo lleva la ROM: `(bytes,
    colores)`, sus 4 KB de 128x64 en 4bpp y sus `RESPALDO_COLORES` colores.
    Guardan el índice **dentro de su paleta**: la ROM les pone los planos de
    `CGRAM_BASE` aparte, ver `respaldo_alto`.

    **Los bytes no van en el orden de los tiles**, sino en el que los agranda
    `esc_doblar` sin hacer cuentas. Cada tile chico se vuelve cuatro grandes,
    y la ROM los llena de a dos vecinos de la misma fila —el par que sale de
    la misma fila de ocho pixeles chicos—, par por par en el orden de la
    escena. De cada par, fila grande por fila grande de a dos (las dos salen
    de la misma fila chica) y los planos 0/1 antes que los 2/3.

    Y dentro de eso, **cada byte lleva medio byte de dos planos**: de la fila
    chica que da los planos `p` y `p+1`, el primero lleva el nibble alto de
    los dos —los cuatro pixeles de la izquierda, que van al tile grande de la
    izquierda— y el segundo los dos nibbles bajos. Así cada byte, duplicado
    bit a bit con `respaldo_doble`, es ya la palabra de dos planos de una fila
    de un tile grande, y la ROM la escribe entera sin separar los planos.
    """
    E = escena_mod
    liviano = info["respaldo"]
    chicos = [pack_tile([[v - E.CGRAM_BASE for v in fila] for fila in celda],
                        planes=E.RESPALDO_PLANOS)
              for celda in E.tiles(liviano["chico"])]
    columnas = E.RESPALDO_ANCHO // E.CELDA
    tiles_ = bytearray()
    for fila_grande in range(E.TILES_Y):
        mitad = fila_grande % E.RESPALDO_ESCALA     # arriba o abajo del chico
        for columna in range(columnas):
            chico = chicos[(fila_grande // E.RESPALDO_ESCALA) * columnas
                           + columna]
            for par in (0, 16):                     # planos 0/1 y 2/3
                for k in range(4):                  # las filas grandes 2k, 2k+1
                    fila = mitad * 4 + k            # la fila chica
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
    """La mitad de arriba de un tile de 8bpp del respaldo: los planos 4 a 7,
    que son los de `CGRAM_BASE` en todos los pixeles. Es lo que la ROM pega
    detrás de cada tile de 4bpp."""
    E = escena_mod
    lleno = [[E.CGRAM_BASE] * E.CELDA for _ in range(E.CELDA)]
    return pack_tile(lleno, planes=8)[E.RESPALDO_PLANOS * 8:]


def respaldo_doble():
    """La tabla con la que `esc_doblar` agranda el respaldo: por cada byte de
    `respaldo_bytes`, una palabra con sus dos nibbles duplicados bit a bit,
    el alto en el byte bajo. Cada nibble son cuatro pixeles de un plano, y
    duplicado son los ocho de una fila de ese plano en un tile grande."""
    def doble(nibble):
        return sum(0b11 << (2 * b) for b in range(4) if nibble >> b & 1)
    return b"".join((doble(s >> 4) | doble(s & 0xF) << 8).to_bytes(2, "little")
                    for s in range(256))


def escenas_asm(datos, tropas, db):
    """La escena de batalla del cartucho, lista para el `.inc`.

    Los fondos y los battlers **por separado**, que la ROM compone al empezar
    la pelea: el porqué y el formato están en tools/port/escena.py. Lo que se
    emite:

      `escena_tropa_fondo`  por índice de tropa —el orden de `tropa_id`—, el
                            número del fondo que nombra su `EnemyEncounter`,
                            `FONDO_DEL_LUGAR` o `FONDO_LISO`.
      `escena_mapa_fondo`   por índice de mapa, el de sus encuentros al azar:
                            un número, `FONDO_DEL_LUGAR` —el del terreno— o
                            `FONDO_LISO`.
      `fondo_terreno`       por terreno, el número de su fondo o `FONDO_LISO`.
      `fondo_respaldo`      por número de fondo, cuál de la ROM lo reemplaza
                            sin MSU-1: el suyo, o el de `escena.reemplazo()`.
      `fondo_dir`           por fondo de la ROM, el puntero de 24 bits a los
                            4 KB de su respaldo liviano, en el orden de
                            `respaldo_bytes`.
      `fondo_cgram`         sus 16 colores, que van a la CGRAM desde la 32.

    Dónde está cada fondo en el `.msu` lo emite `escribir_msu`, por número.
      `respaldo_alto`       los planos 4 a 7 que la ROM le pega a cada tile.
      `battler_*`           por battler: cuántos bytes mide una fila de un
                            plano, cuántas filas, cuánto mide un plano, dónde
                            están sus bytes y sus quince colores.
      `miembro_*`           por miembro de tropa —el orden de `tropa_miembro`—,
                            qué battler es, dónde cae su esquina y cuál de la
                            tropa va en ese lugar del orden de dibujo.

    El tilemap no se emite: son los 512 tiles en orden y la ROM lo arma con un
    lazo. Emitirlo serían 2 KB de cartucho para escribir 0, 1, 2...
    """
    E = escena_mod
    fondos, battlers = datos["fondos"], datos["battlers"]
    out = [
        "\n; --- la escena de la batalla: los fondos y los battlers ---",
        ";",
        "; Van por separado y la ROM los compone en una capa de 8bpp de",
        "; 256x128, que son los siete renglones de texto de arriba. El porqué",
        "; está en tools/port/escena.py; acá sólo viajan los bytes.",
        "; Los fondos del juego, que el .msu lleva todos, y los de la ROM.",
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
        "; El respaldo liviano de la ROM: 4bpp y una sola paleta. Ver",
        "; tools/port/escena.py.",
        "RESPALDO_COLORES = %d" % E.RESPALDO_COLORES,
        "RESPALDO_TILE   = %d" % (E.RESPALDO_PLANOS * 8),
        "RESPALDO_BYTES  = %d" % (E.RESPALDO_ANCHO * E.RESPALDO_ALTO
                                  * E.RESPALDO_PLANOS // 8),
        "RESPALDO_ESCALA = %d" % E.RESPALDO_ESCALA,
        "ESCENA_BAT_PALETA = %d" % E.BATTLER_PALETA,
        "; El tile con el que se tapa lo que queda abajo de la escena. Cae",
        "; **fuera** del bloque de tiles: 512 tiles de 8bpp son las 16.384",
        "; palabras que van de ESCENA_VRAM al final de la VRAM, así que el 512",
        "; da la vuelta y cae en la palabra 0, que mientras dura la pelea es",
        "; VRAM del mapa y no la usa nadie.",
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
    # Dónde está cada fondo de calidad en el `.msu` y la firma que la ROM
    # espera encontrar al principio no van acá: el `.msu` lleva también los
    # efectos de sonido, que salen del audio, y ése se arma después. Ver
    # `msu_asm`.
    # Sesenta y cuatro ceros: el tile transparente con el que se tapa lo que
    # queda abajo de la escena, y de paso el origen fijo del DMA que llena de
    # cero el fondo liso.
    out.append(bloque("escena_cero", bytes(64)))
    # Cada respaldo en un bloque, que no cruza de banco porque la ROM lo lee
    # con `[puntero]` y le suma al puntero sólo los dieciséis bits de abajo.
    for k, (tiles_, _colores) in enumerate(bytes_de):
        out.append(bloque("fondo_%d" % k, tiles_))
    # Los battlers: sus tablas y después sus bytes, cada uno en un bloque que
    # no cruza de banco porque la ROM lo lee con `[puntero], y`.
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
                         tropa.posiciones))[:constantes.ENEMIGOS_MAX]
        infos = []
        for enemigo, centro in suyos:
            k = datos["battler_de"].get(enemigo, 0xFF)
            miembro_b.append(k)
            infos.append(battlers[k] if k != 0xFF else None)
            x, y = (E.posicion(centro, battlers[k]) if k != 0xFF else (0, 0))
            miembro_x.append(x)
            miembro_y.append(y)
        # Y en qué orden se dibujan, que no es el de la tropa: ver
        # `escena.orden_de_dibujo`. Va por miembro, con el lugar en la tropa.
        miembro_orden += E.orden_de_dibujo([c for _e, c in suyos], infos)
    out.append(bloque("miembro_battler", bytes(miembro_b) or b"\xFF"))
    out.append(bloque("miembro_x", bytes(miembro_x) or b"\x00"))
    out.append(bloque("miembro_y", bytes(miembro_y) or b"\x00"))
    out.append(bloque("miembro_orden", bytes(miembro_orden) or b"\x00"))
    for k, b in enumerate(battlers):
        out.append(bloque("battler_%d" % k, E.battler_bytes(b)))
    return "\n".join(out) + "\n"


def bloque(label, data, per_line=16, alinear=None, acomodar=True):
    """Un bloque de datos con su declaración de acomodo.

    Cada bloque se declara antes de emitirlo: casi todos se suben por DMA, y un
    DMA que cruce de banco lee basura de la mitad para adelante. La grilla de
    celdas no se sube por DMA sino que se recorre con un puntero, así que no le
    hace falta el banco entero: sólo que sus palabras no queden partidas entre
    el final de un banco y el principio del siguiente.

    Lo mismo vale para una tabla que se recorre con `[ptr], y` o con
    `lda f:tabla, x`: tiene que quedar entera de un lado, y que sus punteros
    sean simbólicos no alcanza. Partida, la ROM lee la segunda mitad desde el
    `$0000` del banco siguiente, que en LoROM es el espejo de la WRAM. Así
    quedó la tabla de páginas de evento a caballo de `$02FFFF` el día que los
    sprites de un mapa crecieron, y lo que se vio fue un fondo corrido seis
    pixeles: es un error que aparece o desaparece al agregar un byte en
    cualquier otra parte del cartucho.

    `acomodar=False` es para lo que va a TABLAS: esa área vive entera adentro
    del banco 0 —termina en $7FC0—, así que nada de lo que caiga ahí puede
    cruzar, y declararlo emitía una cuenta que siempre daba cero.
    """
    out = ([".align %d" % alinear if alinear else ".bloque %d" % len(data)]
           if acomodar else [])
    out.append("%s:" % label)
    for i in range(0, len(data), per_line):
        out.append("    .byte " + ",".join("$%02X" % b
                                           for b in data[i:i + per_line]))
    return "\n".join(out)


def tabla_de_paginas(mapa, numero, evcodigo):
    """Las páginas de evento del mapa, con el puntero a su código.

    `evcodigo` es la **etiqueta** del bloque de código, que ya no se puede
    rearmar acá: dos mapas cuyos eventos compilan a los mismos bytes comparten
    el bloque y la etiqueta no lleva el número de este mapa. Rearmarla era lo
    que hacía —`"evcodigo_%d" % numero`— y al encender la deduplicación la
    tanda lo cobró enseguida: `varios` no ensamblaba porque nombraba un
    `evcodigo_2` que ya no existía.

    No pasa por `bloque()` porque sus punteros son simbólicos: apuntan adentro
    del bloque de código, que el enlazador ubica. Pero **sí se declara** con
    `.bloque`: la ROM la recorre con `[pag_ptr], y`, y una tabla que cruce de
    banco sigue en `$03:0000`, que en LoROM no es ROM sino el espejo de la
    WRAM. Sin la declaración pasó de verdad: al crecer los sprites del mapa 2
    con los eventos dibujados con un tile, la tabla quedó a caballo de
    `$02FFFF`, la ROM leyó basura en vez de las últimas páginas —entre ellas la
    de prueba— y la sacudida al borde del mapa no arrancaba nunca. La tanda lo
    cobró en pixeles sin decir por qué; lo dijo la RAM del emulador.
    """
    out = [".bloque %d" % (PAGINA_BYTES * len(mapa["paginas"])),
           "paginas_%d:" % numero]
    # Qué eventos tienen alguna página con ruta propia: el refresco de la ROM
    # sólo mira las páginas de ésos, y con los demás no gasta ni una lectura.
    con_ruta = {p["evento"] for p in mapa["paginas"] if p.get("ruta_propia")}
    # Y cuáles cambian de gráfico con la página: el refresco también mira las
    # de ésos, bit 5, y les copia a la fila lo que la página activa dibuja.
    cambian = mapa.get("cambian", set())
    # Y cuáles sólo aparecen y desaparecen con ella: los que caminan. Van por
    # el **mismo** bit 5, porque en +13 no queda ninguno libre —con ruta propia
    # los cinco de abajo son las banderas de la ruta, y el 4 es "la animación
    # sigue quieto"—. Quien los distingue es la ROM, que ya sabe si la fila
    # camina: `npc_buf + 9` vale NPC_QUIETO o el banco de sus doce poses. Ver
    # `grafico_de_pagina` en tools/runtime/paginas_de_eventos.s.
    aparecen = mapa.get("aparecen", set())
    # Y cuáles tienen alguna página automática que compiló: bit 7. El refresco
    # de la ROM tiene que saber si la página activa de un evento es automática
    # —de ahí sale qué arranca solo— y con esto se ahorra leer las páginas de
    # los eventos que no pueden serlo nunca. Es el mismo truco que el bit 6.
    #
    # Las **paralelas** van por este mismo bit, y no por uno propio: en +13 no
    # queda ninguno libre. El bit quiere decir "mirale las páginas a este
    # evento en el refresco", que es lo que las dos necesitan; quién es
    # automática y quién paralela lo dice el trigger de la que gane. Sin esto,
    # `elegir_paginas` ni siquiera anota cuál es la activa —filtra por $E0— y
    # `paralelos_tick` no tendría de dónde sacar su código.
    con_auto = {p["evento"] for p in mapa["paginas"]
                if p["trigger"] in (eventos.TRIGGER_AUTOMATICO,
                                    eventos.TRIGGER_PARALELO) and p["codigo"]}
    for pagina in mapa["paginas"]:
        if pagina["codigo"]:
            destino = "%s + %d" % (evcodigo, pagina["offset"])
            puntero = "<(%s), >(%s), ^(%s)" % (destino, destino, destino)
        else:
            puntero = "$00, $00, $00"   # sin código: no hay nada que correr
        out.append("    .word %-4d ; +0  el evento al que pertenece"
                   % pagina["evento"])
        out.append("    .byte %-4d ; +2  su número de página" % pagina["pagina"])
        out.append("    .byte %-4d ; +3  qué la dispara" % pagina["trigger"])
        out.append("    .word %-4d ; +4  switch que pide, o 0" % pagina["switch_a"])
        out.append("    .word %-4d ; +6  el segundo, o 0" % pagina["switch_b"])
        out.append("    .byte %s ; +8  su código" % puntero)
        out.append("    .byte %-4d ; +11 el actor que pide en el grupo, o 0"
                   % pagina["actor"])
        out.append("    .byte %-4d ; +12 su capa: 1 es la del héroe, la que "
                   "le cierra el paso" % pagina["capa"])
        propia = pagina.get("ruta_propia")
        if propia:
            # La ruta propia de la página, la que camina sola: ver
            # `eventos.ruta_propia`. Las banderas: bit 0 la tiene, 1 se
            # repite, 2 se saltea lo bloqueado, 3 mira siempre igual, 4 la
            # animación sigue quieto.
            banderas = (1 | (2 if propia["repite"] else 0)
                        | (4 if propia["saltable"] else 0)
                        | (8 if propia["dir_fija"] else 0)
                        | (16 if propia["anim_continua"] else 0) | 64
                        | (32 if pagina["evento"] in cambian
                                 or pagina["evento"] in aparecen else 0)
                        | (128 if pagina["evento"] in con_auto else 0))
            destino = "%s + %d" % (evcodigo, pagina["ruta_offset"])
            out.append("    .byte %-4d ; +13 las banderas de su ruta propia"
                       % banderas)
            out.append("    .byte %-4d ; +14 su frecuencia" % propia["frecuencia"])
            out.append("    .byte %-4d ; +15 y su velocidad" % propia["velocidad"])
            out.append("    .byte <(%s), >(%s), ^(%s) ; +16 sus órdenes"
                       % (destino, destino, destino))
            out.append("    .byte %-4d ; +19 cuántas" % len(propia["ordenes"]))
        else:
            out.append("    .byte %-4d ; +13 sin ruta propia; el bit 6 dice si "
                       "otra página del evento la tiene, el 5 si el gráfico "
                       "sigue a la página, el 7 si el evento tiene alguna "
                       "automática"
                       % ((64 if pagina["evento"] in con_ruta else 0)
                          | (32 if pagina["evento"] in cambian
                                   or pagina["evento"] in aparecen else 0)
                          | (128 if pagina["evento"] in con_auto else 0)))
            out.append("    .byte %-4d ; +14 su frecuencia" % pagina["frecuencia"])
            out.append("    .byte %-4d ; +15 y su velocidad, la de una ruta "
                       "forzada sobre el evento" % pagina["velocidad"])
            out.append("    .byte 0,0,0,0")
        # +20..+23: lo que dibuja la página, para los eventos que cambian de
        # gráfico: el tile, los atributos con la paleta y la prioridad de su
        # capa, la pose con el bit 7 puesto si hay gráfico, y los bits de
        # paso de su tile o $FF. Es lo que el refresco copia a la fila.
        oam = pagina.get("oam")
        if oam is None:
            out.append("    .byte $00, $00, $00, $FF ; +20 sin gráfico")
        else:
            out.append("    .byte $%02X, $%02X, $%02X, $%02X ; +20 su gráfico: "
                       "tile, atributos, pose, paso" % oam)
        # +24..+27: la condición por variable: la ranura o $FF, cómo se
        # compara —==, >=, <=, >, <, !=— y contra qué, con signo. Es lo que
        # `condiciones_ok` le pasa a `comparar_var`.
        variable = pagina.get("variable")
        if variable is None:
            out.append("    .byte $FF, 0 ; +24 sin condición por variable")
            out.append("    .word 0")
        else:
            ranura, comparacion, contra = variable
            out.append("    .byte %d, %d ; +24 la variable que pide y la "
                       "comparación" % (ranura, comparacion))
            out.append("    .word %d ; +26 contra qué" % (contra & 0xFFFF))
        # +28: el ítem que pide tener, o 0: `condiciones_ok` mira su cuenta
        # en `FAR_ITEMS`.
        out.append("    .word %-4d ; +28 el ítem que pide, o 0" % pagina["item"])
        # +30 y +31: el giro hacia el héroe. En qué entrada de `npc_poses`
        # están las poses de su gráfico, o $FF si la página no gira, y su
        # pose. Al dispararse, la ROM sube la que mira al héroe; en un
        # refresco, un cambio a una página que no gira o con otro gráfico
        # deshace el giro. Ver GIRO en eventos.py.
        grafico = pagina.get("grafico")
        k = (mapa.get("giro_k", {}).get(tuple(grafico[:2]))
             if pagina.get("gira") and grafico and pagina["evento"] in
             mapa.get("giran", ()) else None)
        out.append("    .byte $%02X, %d ; +30 el giro: sus poses y su pose"
                   % (0xFF if k is None else k, grafico[2] if k is not None else 0))
        assert PAGINA_BYTES == 32
    if not mapa["paginas"]:
        out.append("    .byte $00")     # una etiqueta no puede quedar vacía
    return "\n".join(out)


class Materiales:
    """Los bloques de datos de la ROM, con identidad propia y no del mapa.

    Antes cada mapa emitía sus bloques con su número pegado —`map_tiles_0`,
    `map_tiles_1`— y el registro del mapa armaba el nombre del puntero con esa
    misma cuenta. O sea que la identidad de un bloque **era** el mapa que lo
    pidió, y dos mapas con los mismos tiles se los pagaban dos veces sin que
    hubiera dónde notarlo.

    Acá el bloque tiene nombre propio y el mapa guarda a cuál apunta, que es lo
    que hay que tener antes de poder compartir nada. La numeración sigue siendo
    por clase y en orden de mapa, así que sin deduplicar los nombres son los
    mismos de siempre y la ROM sale byte por byte igual: es a propósito, para
    que este paso se pueda verificar sin depender de la tanda.

    Las poses ya funcionaban así desde antes —`indice_global` en `emit`— y es
    de donde sale la forma.
    """

    def __init__(self, deduplicar=False, comprimidos=None):
        self.deduplicar = deduplicar
        self.donde = {}
        self.cuantos = collections.Counter()
        self.ahorro = collections.Counter()
        self.repetidos = collections.Counter()
        # {bytes crudos: su flujo LZ2}, ya comprimidos de una vez: ver
        # `comprimir_los_bloques`. Y cuánto pesaba y pesa cada clase, de los
        # bloques que sí se emitieron.
        self.comprimidos = comprimidos or {}
        self.crudo = collections.Counter()
        self.lz2 = collections.Counter()

    def guardar_comprimido(self, clase, datos):
        """Como `guardar`, pero lo que va al cartucho es su flujo LZ2, o sus
        flujos pegados si el bloque va en trozos: ver `partes_comprimidas`.
        Se deduplica por el contenido crudo, que es lo mismo que por el
        flujo."""
        datos = bytes(datos)
        flujo = b"".join(self.comprimidos[parte]
                         for parte in partes_comprimidas(clase, datos))
        etiqueta, texto = self.guardar(clase, flujo)
        if texto:
            self.crudo[clase] += len(datos)
            self.lz2[clase] += len(flujo)
        return etiqueta, texto

    def guardar(self, clase, datos, alinear=None):
        """(etiqueta, el asm a emitir). El asm es vacío si el bloque ya estaba.

        La clave incluye la clase y el acomodo, no sólo el contenido: dos
        bloques con los mismos bytes pero distinto `.bloque` o `.align` no
        son el mismo bloque para el enlazador.
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
        """Qué se compartió y cuánto se comprimió, para que el ahorro sea un
        número y no una idea."""
        lineas = ["  %-14s %6.1f KB en LZ2, eran %6.1f"
                  % (clase, self.lz2[clase] / 1024.0,
                     self.crudo[clase] / 1024.0)
                  for clase in CLASES_COMPRIMIDAS if self.crudo[clase]]
        if self.crudo:
            lineas.append("  %-14s %6.1f KB en LZ2, eran %6.1f: %.1f KB menos"
                          % ("", sum(self.lz2.values()) / 1024.0,
                             sum(self.crudo.values()) / 1024.0,
                             (sum(self.crudo.values())
                              - sum(self.lz2.values())) / 1024.0))
        if not self.deduplicar or not self.ahorro:
            return lineas
        return lineas + ["  %-14s %2d bloque(s) compartido(s), %6.1f KB"
                % (clase, self.repetidos[clase], self.ahorro[clase] / 1024.0)
                for clase, _ in self.ahorro.most_common()] + [
            "  %-14s %2d              %6.1f KB en total"
            % ("", sum(self.repetidos.values()),
               sum(self.ahorro.values()) / 1024.0)]


def terreno_plano(mapa):
    """El terreno que tiene todo el mapa, o 0 si tiene más de uno.

    El 0 no es un terreno: los de RM2k son índices de `Data.terrains` y
    empiezan en 1, así que sirve de "acá hay tabla" sin gastar otro campo. Un
    mapa con el terreno en 0 —que no existe— cae en la rama de la tabla, que
    contesta lo mismo.
    """
    unicos = set(mapa["terreno"])
    return unicos.pop() if len(unicos) == 1 else 0


def terreno_del_mapa(mapa):
    return (bytes([terreno_plano(mapa)]) if terreno_plano(mapa)
            else bytes(mapa["terreno"]))


# Lo que la ROM descomprime al cargar un mapa, por clase de bloque. Ver
# `lz2_descomprimir` en tools/runtime/descomprimir.s.
CLASES_COMPRIMIDAS = ("map_tiles", "above_tiles", "sprite_tiles", "anim_tiles",
                      "map_celdas")

# Lo más grande que puede medir cada flujo descomprimido, por dónde cae en la
# WRAM: ver la reserva de LZ2 en tools/runtime/ram_lejana.s, que es de donde salen, y
# `.assert` de descomprimir.s, que los cobra contra los de acá. Los tiles del
# fondo se descomprimen antes que los dibujos de la animación y pueden pisar
# su lugar; la capa de encima y los sprites van después y no.
#
# El del fondo es **por flujo**, no por bloque: un fondo de más de 32 KB —el
# del mapa 66, con el reparto de 544 tiles— va en dos, y la ROM descomprime y
# sube el primero antes de descomprimir el segundo encima: ver `lz2_fondo`.
LZ2_TOPE_FONDO = 0x8000
LZ2_TOPE_ENCIMA_Y_SPRITES = 0x6000
LZ2_TOPE_ANIM = 0x2000
LZ2_TOPE_GRILLA = 0x10000       # dos mitades de GRILLA_MITAD


# Lo que cuesta descomprimir en la ROM, en ciclos maestros, **por lo alto**:
# medido el 2026-09-26 sobre los cuarenta mapas de `release`, contra la carga
# sin comprimir, lo medido no pasa de este modelo por más de medio cuadro. Un
# cuadro de NTSC son 357.954 ciclos maestros. Lo usa la cuenta del arranque.
LZ2_CICLOS_POR_COMANDO = 700
LZ2_CICLOS_POR_BYTE = 60
CICLOS_POR_CUADRO = 357954


def cuadros_de_descomprimir(mapa, comprimidos):
    """Cuántos cuadros se lleva descomprimir los bloques de un mapa."""
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
    """{bytes crudos: flujo LZ2} de todo lo que el cartucho lleva comprimido,
    con un solo proceso de `lz2`. De paso cobra los topes de la WRAM."""
    partes = []
    for mapa in mapas:
        for clase, datos in crudos_del_mapa(mapa).items():
            if clase not in CLASES_COMPRIMIDAS:
                continue
            controlar_flujos(mapa["id"], clase, datos)
            partes += partes_comprimidas(clase, datos)
    partes = list(dict.fromkeys(partes))
    return dict(zip(partes, comprimir.comprimir_varios(partes)))


# La grilla va a la mitad alta de los dos bancos de la WRAM —ver
# `lz2_grilla`—, así que se comprime en dos flujos de hasta 32 KB: cada uno cae
# entero en un banco, y el descompresor no tiene que saber cruzar.
GRILLA_MITAD = 0x8000


# Y los tiles del fondo, en flujos de a lo que entra en el buffer de carga: la
# ROM descomprime uno, lo sube por DMA y recién ahí descomprime el siguiente
# en el mismo lugar —ver `lz2_fondo`—. Un fondo que entra en uno va en uno, y
# eso deja a los mapas de siempre con el flujo de siempre.
FONDO_FLUJOS_MAX = 2            # los que lee `lz2_fondo`


def partes_comprimidas(clase, datos):
    """Los trozos de un bloque que se comprimen cada uno en su flujo."""
    if clase == "map_celdas":
        return [datos[:GRILLA_MITAD], datos[GRILLA_MITAD:]]
    if clase == "map_tiles" and len(datos) > LZ2_TOPE_FONDO:
        return [datos[k:k + LZ2_TOPE_FONDO]
                for k in range(0, len(datos), LZ2_TOPE_FONDO)]
    return [datos]


# Cuánto entra en la WRAM de cada flujo, y cuántos flujos lee la ROM por
# bloque. La grilla va siempre en dos, uno por mitad; los demás en uno, salvo
# el fondo.
TOPES_POR_FLUJO = {"map_tiles": (LZ2_TOPE_FONDO, FONDO_FLUJOS_MAX),
                   "above_tiles": (LZ2_TOPE_ENCIMA_Y_SPRITES, 1),
                   "sprite_tiles": (LZ2_TOPE_ENCIMA_Y_SPRITES, 1),
                   "anim_tiles": (LZ2_TOPE_ANIM, 1),
                   "map_celdas": (GRILLA_MITAD, 2)}


def controlar_flujos(map_id, clase, datos):
    """Que cada flujo del bloque entre en su lugar de la WRAM, y que no haya
    más flujos que los que la ROM lee. Un flujo que se pasa no rompe nada al
    armar: la ROM lo descomprime igual y pisa lo que haya detrás —con el fondo
    del 66, la mitad alta de la grilla—, y se ve o no según el mapa."""
    tope, cuantos = TOPES_POR_FLUJO[clase]
    partes = partes_comprimidas(clase, datos)
    for parte in partes:
        if len(parte) > tope:
            raise SystemExit(
                "mapa %d: un flujo de %s mide %d bytes y en la WRAM entran %d: "
                "ver la reserva de LZ2 en tools/runtime/ram_lejana.s"
                % (map_id, clase, len(parte), tope))
    if len(partes) > cuantos:
        raise SystemExit(
            "mapa %d: %s mide %d bytes, que son %d flujos, y la ROM lee %d"
            % (map_id, clase, len(datos), len(partes), cuantos))


def crudos_del_mapa(mapa):
    """{clase: los bytes sin comprimir} de un mapa, para `CLASES_COMPRIMIDAS`."""
    above, sprite = mapa["above"], mapa["sprite"]
    return {"map_tiles": bytes(mapa["tiles"]),
            "above_tiles": bytes(above[0]),
            "sprite_tiles": bytes(sprite[0]) if sprite else b"",
            "anim_tiles": bytes(mapa["anim"]),
            "map_celdas": bytes(mapa["celdas"])}


def escribir_crudos(directorio, mapas):
    """Deja en `directorio/crudos/` lo que la ROM tiene que tener en la VRAM y
    en la WRAM después de cargar cada mapa, sin comprimir: `<índice>.<clase>
    .bin`, con el índice del mapa en la ROM.

    Es la otra punta de las pruebas de la compresión: `test_lz2.py` hace la ida
    y vuelta de cada bloque, y `test_carga_descomprimida.py` compara contra
    esto lo que la ROM descomprimió. Viene del conversor y no de la ROM
    justamente para que no sea la ROM la que se contesta a sí misma.

    Se borra entero antes de escribir: un mapa que salió del cartucho dejaría
    su archivo, y una prueba que recorra el directorio lo miraría.
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
    """Los bloques de datos de un mapa, con el número pegado a cada etiqueta.

    `indice_global` son las etiquetas de las doce poses de cada (CharSet,
    índice) **tal como este mapa lo cuantizó**: ver `banco_de_poses`, y el
    reparto de poses en `emit`.
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
        # El terreno por bloque. Un mapa cuyo terreno es el mismo en todos
        # lados —los 328 de este juego, que lo tienen en 1— emite **un byte**
        # y `TERRENO_PLANO` dice cuál: la tabla entera serían unos ocho
        # kilobytes de la nada repartidos entre los cuarenta mapas. El byte lo
        # deduplica `materiales`, así que todos los mapas planos con el mismo
        # terreno comparten el mismo.
        ("bloque_terreno", terreno_del_mapa(mapa)),
        ("npc_table", npc_bytes(sprite[3]) if sprite else b""),
        # Dos bytes por gráfico de la orden 34: su entrada en `npc_poses` —o
        # $FF, que es esconder— y su paleta. Ver `Graficos` en eventos.py.
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
    # Las dos tablas de punteros a las poses de la ROM: la de los NPCs que
    # caminan y la de los candidatos a líder.
    animados = sprite[7] if sprite else []
    out.append(npc_poses_asm(numero, animados, indice_global))
    out.append(actor_table_asm(numero, sprite[4] if sprite else [],
                               animados, indice_global))
    # La grilla, en sus dos flujos: ver `lz2_grilla`. Entera en un banco, como
    # todo lo comprimido, porque el descompresor no cruza.
    etiquetas["map_celdas"], texto = materiales.guardar_comprimido(
        "map_celdas", mapa["celdas"])
    if texto:
        out.append(texto)
    out.append(tabla_de_paginas(mapa, numero, etiquetas["evcodigo"]))
    # Las tres que no se comparten son las que llevan **punteros simbólicos**
    # adentro —a las poses de la ROM, al código de los eventos—: sus bytes los
    # pone el enlazador, así que acá no hay contenido con el cual compararlas.
    for nombre in ("npc_poses", "actor_table", "paginas"):
        etiquetas[nombre] = "%s_%d" % (nombre, numero)
    return "\n".join(out), etiquetas


def encuentros_de_la_rom(mapas, tree, pasos_de_prueba, tropas):
    """Los encuentros al azar de cada mapa del cartucho, listos para emitir.

    Los datos viven en el árbol y no en el `.lmu`: cada nodo trae su lista de
    tropas, cada cuántos pasos, y —si es un área— el rectángulo que tapa. Ver
    `eventos.zonas_de_encuentro`.

    De paso **pide las tropas**, que es lo que hace que el cartucho lleve sus
    enemigos y el paquete de audio de la pelea: sin eso un encuentro arrancaría
    una batalla contra una tropa que no está en ninguna tabla.

    `pasos_de_prueba` reemplaza el `encounter_steps` de todos los mapas. Es
    para las ROMs de prueba: con los del juego —de 25 a 85— un encuentro tarda
    más de cien pasos, que es lo que se quiere jugando y no lo que se quiere
    en un caso de la tanda.
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
        # Las tres tablas se indexan con un byte. Con los 53 mapas del juego
        # entero son 53 registros, 56 zonas y 322 tropas, así que la que puede
        # pasarse es la última —y hoy sólo en un cartucho que los lleve todos—.
        sys.exit("los encuentros no entran en tablas de un byte: %d "
                 "registro(s), %d zona(s), %d tropa(s)"
                 % (len(registros), len(zonas), len(tropas_de_zona)))
    return {"por_mapa": por_mapa, "registros": registros, "zonas": zonas,
            "tropas": tropas_de_zona}


# El título de la cabecera de una ROM de SNES: 21 bytes, en `$FFC0`.
TITULO_CABECERA = 21


def identidad_de_la_rom():
    """Lo que la ROM dice de sí misma, del `[rom]` del archivo de proyecto:
    el título de la cabecera, ya rellenado con blancos, y la firma de la
    partida en la SRAM. Son `.define` porque son texto: `cabecera.s` y
    `partida.s` los usan, y hasta el 2026-09-29 los tenían escritos."""
    titulo = perillas.ascii("rom", "title", hasta=TITULO_CABECERA)
    firma = perillas.ascii("rom", "sram_signature", largo=4)
    return ("; Quién es la ROM, del archivo de proyecto: el título de la\n"
            "; cabecera y la firma con que la SRAM dice que una ranura tiene\n"
            "; una partida de este juego.\n"
            '.define ROM_TITULO "%s"\n'
            '.define SRAM_MAGIA_TEXTO "%s"\n\n'
            % (titulo.ljust(TITULO_CABECERA), firma))


def emit(path, mapas, inicial=0, heroe_encima=False, grupo_inicial=(),
         ventana=None, titulo=None, ranuras=None, cartel=None,
         animaciones=None, tropas=(), audio_batalla=None, escenas=None,
         encuentros=None, paginas_tropa=None, comprimidos=None,
         hp_de_enemigos=False, game_over=None):
    """El .inc que se ensambla junto con main.s.

    `hp_de_enemigos` es `--hp-de-enemigos`: si la pelea dibuja los HP de los
    enemigos, que RM2k no muestra.

    `comprimidos` es lo de `comprimir_los_bloques`; si falta se comprime acá.

    `titulo` es la pantalla de título —la imagen y su menú— y puede faltar;
    `game_over`, la de Game Over, también: es lo de
    `pantalla_completa.comprimida`.
    `ranuras` es la pantalla de ranuras y **va siempre**: la abre el save point
    desde adentro del juego, tenga la ROM título o no. Ver `pantalla_ranuras`
    en menus.py.
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
                    "mapa %d: con este reparto de VRAM, %s necesita %d tiles y "
                    "entran %d" % (mapa["id"], nombre, cuantos,
                                   layout[nombre][1]))

    # Dónde quedó el cartel: el mapa de la tabla que se llevó sus tiles, y en
    # qué tile y con qué paleta. Sale de los mapas ya convertidos y no de una
    # variable que haya que ir pasando: el que lo tiene es el único con
    # `imagen_base` distinto de cero.
    cartel_base, cartel_pal = 0, 0
    for mapa in mapas:
        if mapa["sprite"] and mapa["sprite"][13]:
            cartel_base, cartel_pal = mapa["sprite"][13], mapa["sprite"][14]
            break

    cabecera = (
        "; Generado por tools/port/snes_convert.py. No editar.\n"
        "; Mapas: %s\n\n"
        "MAPA_COUNT   = %d\n"
        "MAPA_STRIDE  = %d\n"
        "MAPA_INICIAL = %d\n"
        "; Lo que no depende del mapa: el tilemap de la capa de encima vive\n"
        "; siempre en el mismo lugar de la VRAM —el del fondo lo elige el\n"
        "; reparto, M_VRAM_MAP—, y el paso de la tabla de NPCs no cambia.\n"
        "VRAM_ABOVE_MAP = $%04X\n"
        "MAP_LAYOUT  = %d\n"
        "NPC_STRIDE  = %d\n"
        "NPC_MAX     = %d\n"
        "NPC_QUIETO  = $%02X\n"
        "; La tabla de posiciones de eventos, y cuántas rutas forzadas\n"
        "; pueden estar corriendo a la vez sobre ellos.\n"
        "EV_STRIDE   = %d\n"
        "EV_MAX      = %d\n"
        "RUTA_EV_MAX = %d\n"
        "PAGINA_BYTES = %d\n"
        "GIRO_NINGUNO = $%04X\n"
        "; Y cuántos gráficos distintos puede pedir la orden 34 en un mapa:\n"
        "; su tabla se copia a la RAM como la de NPCs.\n"
        "RUTA_GRAF_MAX = %d\n"
        "; La cabecera de un cuadro de texto, que es el primer byte del que\n"
        "; `OP_MESSAGE` nombra: los renglones en los tres bits de abajo, el\n"
        "; autocierre del `\\^` en el bit 3 y cuantas pausas de `\\|` lleva en\n"
        "; el nibble de arriba. Y cuanto dura cada pausa, que son 61 cuadros y\n"
        "; no 60: ver CUADROS_DE_PAUSA en eventos.py.\n"
        "CABECERA_LINEAS     = $%02X\n"
        "CABECERA_AUTOCIERRE = $%02X\n"
        "CUADROS_DE_PAUSA    = %d\n"
        "; El bit de arriba del byte de banderas de los opcodes que escriben\n"
        "; una variable: si la escritura pide el refresco de páginas. Lo\n"
        "; resuelve el conversor mirando qué variables miran las condiciones\n"
        "; de página de este mapa; `var_apuntar` enmascara la ranura con\n"
        "; VAR_RANURA. Ver VAR_REFRESCO en eventos.py: sin esto media Lashe\n"
        "; City corría a 30 cuadros.\n"
        "VAR_REFRESCO = $%02X\n"
        "VAR_RANURA   = $%02X\n"
        "ANIM_ENTRADA = %d\n"
        "ANIM_SONIDO  = %d\n"
        "ANIM_DESTELLO = %d\n"
        "; El cartel del ShowPicture: dónde cae su esquina en la pantalla\n"
        "; de la consola y cuántos objetos de 32x32 mide.\n"
        "; Las coordenadas ya vienen escaladas de 320x240 a 256x224 y la X\n"
        "; puede ser negativa: el cartel del \"1 year earlier\" se sale por la\n"
        "; izquierda, que es lo que RM2k muestra. Ver tools/port/imagen.py.\n"
        "; Las banderas de `KeyInputProc`, que van en el segundo byte de\n"
        # `rom/src/` a propósito: va al `.inc`, que no se toca todavía.
        "; OP_KEY. Ver `op_key` en rom/src/interprete_teclas_y_esperas.s.\n"
        "TECLA_ESPERA   = $%02X\n"
        "TECLA_DIRS     = $%02X\n"
        "TECLA_DECISION = $%02X\n"
        "TECLA_CANCELAR = $%02X\n"
        "TECLA_ARRANCA  = $%02X\n"
        "TECLA_VALOR_DECISION = %d\n"
        "TECLA_VALOR_CANCELAR = %d\n"
        "; Y las cuatro direcciones, con el mismo número que les da\n"
        "; `CheckInput`. El orden en que se miran sale de acá: de mayor a\n"
        "; menor, que es lo que dice \"RPG processes keys from highest\n"
        "; variable value to lowest\".\n"
        "TECLA_VALOR_ARRIBA   = %d\n"
        "TECLA_VALOR_DERECHA  = %d\n"
        "TECLA_VALOR_IZQUIERDA = %d\n"
        "TECLA_VALOR_ABAJO    = %d\n"
        "; En qué tile de su banco de sprites arranca y con qué paleta.\n"
        "; Van de globales y no en el registro del mapa porque el cartel es\n"
        "; **uno solo por ROM** y vive en un solo mapa: los dos campos\n"
        "; ocupaban los últimos bytes libres de MAPA_STRIDE, y agrandar el\n"
        "; registro para eso habría sido caro por nada. Que ningún otro mapa\n"
        "; lo muestre lo controla el conversor, que corta.\n"
        "IMAGEN_BASE = %d\n"
        "IMAGEN_PAL  = %d\n"
        "IMAGEN_X    = %d\n"
        "IMAGEN_Y    = %d\n"
        "IMAGEN_OBJETOS = %d\n"
        "; Cuántos tiles de la grilla de nombres hay que saltear para pasar\n"
        "; de un objeto al siguiente, y de una fila de cuatro a la que sigue.\n"
        "IMAGEN_PASO = %d\n"
        "IMAGEN_FILA = %d\n"
        "; La lluvia: ver OP_WEATHER en eventos.py.\n"
        "LLUVIA_GOTAS_MAX = %d\n"
        "LLUVIA_GOTAS_0 = %d\n"
        "LLUVIA_GOTAS_1 = %d\n"
        "LLUVIA_GOTAS_2 = %d\n"
        "LLUVIA_VIDA   = %d\n"
        "LLUVIA_NACE   = %d\n"
        "LLUVIA_SEMILLA = $%04X\n"
        "CLIMA_LLUVIA  = %d\n"
        "; El inventario: un byte por ítem del LDB y el tope de RM2k. Ver\n"
        "; OP_ITEM en eventos.py.\n"
        "ITEMS_N       = %d\n"
        "ITEM_MAX      = %d\n"
        "; Las variables: cuántas ranuras lleva esta ROM —al menos una, porque\n"
        "; un largo cero cerraría la tabla de la partida—, las clases de\n"
        "; operando de ControlVars que la ROM distingue, la suma, y la\n"
        "; semilla del azar. Ver 'las variables de RM2k' en eventos.py.\n"
        "VARIABLES_N   = %d\n"
        "VAR_SUMAR     = %d\n"
        "VAR_VARIABLE  = %d\n"
        "VAR_AZAR      = %d\n"
        "VAR_OTRO      = %d\n"
        "; La clase 6, las coordenadas de un personaje: el blanco va como el de\n"
        "; OP_ROUTE —0 el héroe, el índice del evento más uno— y el otro operando\n"
        "; dice cuál coordenada. Ver VAR_PERSONAJE en eventos.py.\n"
        "VAR_PERSONAJE = %d\n"
        "PERSONAJE_X   = %d\n"
        "PERSONAJE_Y   = %d\n"
        "; Los bits de arriba de cada escritura de OP_CELL_TEST. Ver CELDA_Y en\n"
        "; eventos.py.\n"
        "CELDA_Y       = $%04X\n"
        "CELDA_REFRESCO = $%04X\n"
        "AZAR_SEMILLA  = $%04X\n"
        "; Y la del azar de los encuentros, que es otra a propósito: caminar no\n"
        "; le corre el azar al mapa. Ver ENC_SEMILLA en eventos.py.\n"
        "ENC_SEMILLA   = $%04X\n"
        "TIMER_PONER_VAR = %d\n"
        "; Las clases de condición de ConditionalBranch que sabemos,\n"
        "; con el número de RM2k tal cual.\n"
        "COND_ORO    = %d\n"
        "COND_ITEM   = %d\n"
        "COND_ACTOR  = %d\n"
        "; Y las dos preguntas de actor que llevan dos operandos, con su\n"
        "; opcode propio: ver OP_IF_ACTOR en eventos.py.\n"
        "COND_ACTOR_HABILIDAD = %d\n"
        "COND_ACTOR_EQUIPO    = %d\n"
        "ORO_MAX     = %d\n"
        "; Las dos operaciones de PanScreen que compilan.\n"
        "PAN_CORRER  = %d\n"
        "PAN_VOLVER  = %d\n"
        "; Las tres operaciones del cronómetro.\n"
        "TIMER_PONER    = %d\n"
        "TIMER_ARRANCAR = %d\n"
        "; Y sus cinco glifos en pantalla: dónde va el primero y cuánto\n"
        "; mide cada uno. El de los dos puntos es el número 10.\n"
        "TIMER_X        = %d\n"
        "TIMER_Y        = %d\n"
        "TIMER_GLIFO_W  = %d\n"
        "TIMER_DOS_PUNTOS = %d\n"
        "; Cuántos cuadros entran en un segundo, y los que `SetTimer` le\n"
        "; suma de más para que el primer segundo se vea entero.\n"
        "TIMER_CUADROS  = %d\n"
        "TIMER_DE_MAS   = %d\n"
        "; Cuántos destellos pueden estar corriendo a la vez.\n"
        "FLASH_MAX   = %d\n"
        "; Cuántos eventos con página paralela puede haber en un mapa.\n"
        "PARALELO_MAX = %d\n"
        "TRIGGER_AUTOMATICO = %d\n"
        "TRIGGER_ACCION     = %d\n"
        "TRIGGER_TOCA_HEROE = %d\n"
        "TRIGGER_PARALELO   = %d\n"
        "; Cuántos cuadros dura un paso de una celda. Sale de eventos.py y no\n"
        "; de una cuenta en la ROM.\n"
        "CUADROS_POR_CELDA = %d\n"
        "; La frecuencia más alta de una ruta, que es donde topan las\n"
        "; órdenes 30 y 31. La más baja la topa la ROM en 1, como RM2k;\n"
        "; lo que garantiza que no se llegue es el conversor, que rechaza\n"
        "; la ruta.\n"
        "RUTA_FRECUENCIA = %d\n"
        "; Y cuánto cuesta un `wait` adentro de una ruta forzada. **No es un\n"
        "; cuadro**: en RM2k es `SetMaxStopCountForWait`, o sea\n"
        "; `20 + (1 << (8 - frecuencia))`, y con la frecuencia 8 —la única\n"
        "; que el conversor deja pasar— son veinte.\n"
        "RUTA_ESPERA = %d\n"
        "; Y el salto: cuánto le queda al arrancar. Cuánto baja por cuadro\n"
        "; depende de la velocidad —`salto_por_vel`— y no de la distancia.\n"
        "SALTO_PASO = %d\n"
        "TINTE_NEUTRO = %d\n"
        "; El fundido de los teletransportes: 35 cuadros de ida y 35 de\n"
        "; vuelta, como RM2k, y de cada 35 la rampa son 24. El mapa se carga\n"
        "; en el primer cuadro negro, que es el %d. Estos números y la tabla\n"
        "; de más abajo salen de las constantes del fundido de\n"
        "; tools/port/eventos.py.\n"
        "FUNDIDO_CUADROS = %d\n"
        "FUNDIDO_TOTAL   = %d\n"
        "FUNDIDO_RAMPA   = %d\n"
        "FUNDIDO_NEGRO   = %d\n"
        "FUNDIDO_CARGA   = %d\n"
        "BRILLO_MAX      = %d\n"
        "; Las transiciones del teletransporte que la ROM hace con el mosaico\n"
        "; y con el corte; cualquier otra es el fundido. Ver\n"
        "; `ChangeScreenTransitions` en tools/port/eventos.py.\n"
        "TRANSICION_MOSAICO = %d\n"
        "TRANSICION_CORTE   = %d\n"
        "; Los pesos de luminancia del Y'CbCr, que son con los que RM2k\n"
        "; satura. Suman 65536 exactos, así que sobre canales de cinco bits\n"
        "; dan una luminancia de cinco bits sin reescalar nada.\n"
        "LUZ_R = %d\n"
        "LUZ_G = %d\n"
        "LUZ_B = %d\n"
        "; Un bit por switch. El más alto que el juego consulta es el 1003.\n"
        "SWITCH_BYTES = %d\n"
        "; El grupo con el que arranca la partida, y su tope. En RM2k el\n"
        "; gráfico del héroe es el del primero, así que esto decide qué\n"
        "; sprite se dibuja; `ChangePartyMembers` lo mueve en caliente.\n"
        "GRUPO_MAX      = %d\n"
        "GRUPO_INICIAL_N = %d\n"
        "ACTOR_BYTES    = %d\n"
        "; Cuántos bytes de esa entrada son los quince colores del\n"
        "; actor: la ROM los sube a la ranura que los líderes\n"
        "; comparten. Ver `elegir_grafico_heroe`.\n"
        "ACTOR_COLORES  = %d\n"
        "OBJ_COLORS     = %d\n"
        "; La capa del héroe, para ordenarlo contra los NPCs.\n"
        "HERO_LAYER  = %d\n"
        "; Su prioridad de objeto. $10 —debajo de la capa de encima— en\n"
        "; toda ROM que no sea la de `encima`, que la sube a $20\n"
        "; para ejercitar la prioridad 2. Ningún evento del juego llega\n"
        "; a ejercitarla: ver `test_encima` en test_caminar_golden.py.\n"
        "HERO_PRIORITY = $%02X\n"
        "; La ventana de mensaje: sus tiles viven en la segunda mitad del\n"
        "; banco de BG2, o sea a partir del índice 256, y sus celdas ya\n"
        "; vienen armadas con ese corrimiento y con la prioridad de la capa\n"
        "; de encima.\n"
"; Y dónde arranca el fondo en CGRAM: abajo de él viven el color de\n"
        "; fondo de la pantalla y la paleta de la ventana de mensaje, que\n"
        "; son de toda la ROM. El fondo va a 8 bits y direcciona CGRAM en\n"
        "; directo, así que le alcanza con arrancar corrido.\n"
        "CGRAM_BASE     = %d\n"
"VENTANA_CGADD  = %d\n"
        "VENTANA_TILES  = %d\n"
        "VENTANA_FILAS_ = %d\n"
        "VENTANA_COLS   = %d\n"
        "; El área de texto: dónde arranca en el banco de tiles de la\n"
        "; ventana y qué celdas ocupa. Sus tiles no están deduplicados —la\n"
        "; ROM los reescribe— y de ahí sale el tope de caracteres por línea.\n"
        "VENTANA_TEXTO_BASE = %d\n"
        "VENTANA_TEXTO_FILA = %d\n"
        "VENTANA_TEXTO_FILAS = %d\n"
        "VENTANA_TEXTO_COL  = %d\n"
        "VENTANA_TEXTO_COLS = %d\n"
        "MENSAJE_COLS   = %d\n"
        "; La fuente: 95 glifos ASCII de seis bits por doce filas, y el\n"
        "; índice de paleta de la sombra. El de cada fila del glifo está en\n"
        "; fuente_color.\n"
        "FUENTE_ALTO    = %d\n"
        "FUENTE_ANCHO   = %d\n"
        "FUENTE_SOMBRA  = %d\n"
        "FUENTE_PRE_FILAS = %d\n"
        "FUENTE_PRE_CHAR  = %d\n"
        "; La animación del ChipSet. Cada mapa tiene una entrada en\n"
        "; `anim_tabla` con sus dos corridas y un bloque con los dibujos;\n"
        "; ver `anim_tabla` en snes_convert.py. Las cadencias y el ciclo\n"
        "; del agua salen de `rm2k.py`.\n"
        "ANIM_FAMILIAS  = %d\n"
        "ANIM_STRIDE    = %d\n"
        "ANIM_FAM_STRIDE = %d\n"
        "AGUA_CUADROS   = %d\n"
        "AGUA_DIBUJOS   = %d\n"
        "AGUA_CICLO_N   = %d\n"
        "ANIMADO_CUADROS = %d\n"
        "ANIMADO_PASOS  = %d\n"
        "BYTES_POR_TILE = %d\n"
        "; La pantalla de título. TITULO_TILES en 0 quiere decir que esta ROM\n"
        "; no la lleva y que los bloques de abajo son un byte de relleno; el\n"
        # `rom/src/` a propósito: va al `.inc`, que no se toca todavía.
        "; código de rom/src/ se apaga solo con eso. Vive sola en la VRAM —no\n"
        "; comparte con ningún mapa, porque mientras se ve no hay mapa\n"
        "; cargado— así que sus direcciones son fijas y no salen del reparto\n"
        "; de `vram_layout`. La imagen la sube `pantalla_subir`, desde su fila\n"
        "; en `pantallas_tabla`: los tiles desde $0000 y el tilemap en\n"
        "; PANTALLA_MAPA.\n"
        "TITULO_TILES   = %d\n"
        "; El menú, en BG2 a cuatro bits por pixel: su banco de tiles, cuántas\n"
        "; opciones tiene y cuál está elegida al entrar. El cursor no se dibuja\n"
        "; aparte: hay un tilemap por opción y moverlo es subir el otro.\n"
        ";\n"
        "; El reparto de la VRAM en esta pantalla, en palabras, y por qué cada\n"
        "; uno está donde está: los tiles de la imagen arrancan en 0 y se\n"
        "; llevan 15872, así que todo lo demás va **arriba** de eso. La base de\n"
        "; tiles de un BG va de a 4096 palabras, que es lo que fija $5000 para\n"
        "; el menú; los tilemaps van de a 1024 y entran en el hueco de al lado.\n"
        ";\n"
        ";   $0000 .. $3E00   los 496 tiles de la imagen, a 8bpp\n"
        ";   $4400 .. $4800   el tilemap del menú\n"
        ";   $5000 ..         los tiles del menú, a 4bpp\n"
        ";   $7C00 .. $8000   el de la imagen, PANTALLA_MAPA de game_over.s\n"
        "TITULO_MENU_CGRAM = %d\n"
        "TITULO_MENU_TILES = %d\n"
        "TITULO_MENU_VRAM  = $5000\n"
        "TITULO_MENU_MAP   = $4400\n"
        "TITULO_MENU_N     = %d\n"
        "; La pantalla de ranuras, que usan las dos puntas: 'Resume the Story'\n"
        "; y el save point. Es una pantalla propia —no una capa encima del\n"
        "; título— así que se sube entera al entrar. **Va en toda ROM**, con\n"
        "; título o sin él: el save point la abre desde adentro del juego, y\n"
        "; por eso sus direcciones de VRAM son suyas y no las del menú: caen\n"
        "; en el banco de tiles de BG1 de todos los repartos, que es lo que\n"
        "; `volver_al_mapa` repone con `load_map`. Ver RANURA_MAP en el\n"
        "; conversor.\n"
        "RANURA_VRAM       = $%04X\n"
        "RANURA_MAP        = $%04X\n"
        ";\n"
        "; Los bloques de celdas: la cabecera tiene dos variantes —cargar y\n"
        "; guardar— y cada ranura cuatro —vacía o llena, con cursor o sin él—.\n"
        "; Mover el cursor es reescribir dos filas y no un tilemap entero.\n"
        "SRAM_RANURAS_N    = %d\n"
        "RANURA_TILES      = %d\n"
        "RANURA_CAB_FILA   = %d\n"
        "RANURA_CAB_FILAS  = %d\n"
        "RANURA_CAB_CELDAS = %d\n"
        "RANURA_FILA0      = %d\n"
        "RANURA_SALTO      = %d\n"
        "RANURA_FILAS      = %d\n"
        "RANURA_CELDAS     = %d\n"
        "; Y dónde va cada fila en el tilemap, en palabras. También sale de una\n"
        "; tabla: la cuenta es RANURA_FILA0 + n * RANURA_SALTO, por 32, y\n"
        "; escribirla en el 65816 sería el cuarto lugar donde equivocarse.\n"
        "RANURA_CAB_VRAM   = %d\n"
        "; Cuántos bloques hay antes del primero de las filas: son las dos\n"
        "; cabeceras, cargar y guardar.\n"
        "RANURA_BLOQUE_FILAS = 2\n"
        "; El grupo de la partida guardada, encima de la fila: las caras de\n"
        "; hasta RANURA_CARAS_MAX, de RANURA_CARA_COLS por RANURA_CARA_FILAS\n"
        "; celdas, y el nombre y el nivel del primero. Qué bloque de cara le\n"
        "; toca a cada actor lo dice `ranura_cara_bloque`, por id de actor\n"
        "; hasta RANURA_ACTORES_N, con $FF para 'no tiene'; y a dónde van,\n"
        "; `ranura_cara_vram` —de a cuatro por ranura— y `ranura_nombre_vram`.\n"
        ";\n"
        "; El nombre y el nivel no son bloques: se componen de a una letra por\n"
        "; celda con `ranura_glifo_celdas`, y el texto de cada actor sale de\n"
        "; su fila de `ranura_actor_texto` —el nombre, las dos cifras del\n"
        "; nivel y el máximo de HP, uno detrás del otro—. Ver 'lo que depende\n"
        "; del actor' en titulo.py: es lo que hace que el banco de tiles no\n"
        "; crezca con la cantidad de actores.\n"
        "RANURA_CARAS_MAX  = %d\n"
        "RANURA_CARA_COLS  = %d\n"
        "RANURA_CARA_FILAS = %d\n"
        "RANURA_NOMBRE_COLS  = %d\n"
        "; Cuánto mide la fila de un actor en `ranura_actor_texto` y dónde\n"
        "; arranca cada tira adentro de ella. El ancho es una potencia de dos\n"
        "; aunque sobren bytes: así el índice sale de corrimientos y no de una\n"
        "; multiplicación.\n"
        "RANURA_TEXTO_ANCHO  = %d\n"
        "RANURA_TEXTO_NOMBRE = 0\n"
        "RANURA_TEXTO_NIVEL  = %d\n"
        "RANURA_TEXTO_MAX    = %d\n"
        "RANURA_NIVEL_CIFRAS = %d\n"
        "; A cuántas celdas del nombre cae la primera cifra del nivel.\n"
        "RANURA_NIVEL_DESPL  = %d\n"
        "; Y dónde arranca la cifra 0 adentro de `ranura_glifo_celdas`, que\n"
        "; está indexada por carácter: es de ahí de donde el oro y los HP\n"
        "; sacan sus dígitos.\n"
        "GLIFO_CIFRA_0     = %d\n"
        "RANURA_ACTORES_N  = %d\n"
        "; Cuántas entradas de CGRAM sube la pantalla de ranuras: la paleta 0\n"
        "; del texto y una por cara, de dieciséis cada una.\n"
        "RANURA_CGRAM_N    = %d\n"
        "; Cuántas entradas de CGRAM usa el menú del título: una paleta de\n"
        "; dieciséis, la 0. Ya está definida más arriba, con la pantalla de\n"
        "; título; esto confirma que las dos cuentas den lo mismo.\n"
        ".assert TITULO_MENU_CGRAM = %d, error, \"dos cuentas del CGRAM del menú\"\n\n"
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
        # La rampa del fundido, en el banco 0 porque `fundido_tick` la lee con
        # `lda fundido_rampa, x`. Sale de `eventos.rampa_de_fundido()`:
        # escribirla también en tools/runtime/ sería tener dos copias que se pueden
        # desincronizar sin que nada lo note.
        handle.write('.segment "TABLAS"\n'
                     '; El brillo maestro en cada cuadro de la rampa, de negro\n'
                     '; a lleno. Bajando se lee al revés.\n'
                     'fundido_rampa:\n    .byte %s\n\n'
                     % ",".join(str(v) for v in eventos.rampa_de_fundido()))
        # Los datos van en RODATA, que el enlazador reparte por los bancos de
        # arriba. Lo que queda en TABLAS —o sea en el banco 0— es lo que la ROM
        # recorre con `lda tabla, x` a secas, que direcciona el banco de datos.
        # `mapa_tabla` ya no está entre ésas: ver `tabla_de_mapas`.
        handle.write('.segment "RODATA"\n')
        # Las doce poses de cada personaje que cambia de pose, **una vez por
        # cuantización** y no una por ROM: dos mapas que dibujen al mismo
        # personaje con la misma paleta comparten el banco, y si uno lo
        # cuantizó distinto —porque le prestó una paleta ajena, como el mapa 8
        # a Chara2:0, o le bajó un color— lleva el suyo. Hasta el 2026-09-10
        # esto era un `sys.exit`, y el reparto de paletas tenía una regla para
        # esquivarlo que el préstamo no miraba: agregar Lashe City 33,36 a la
        # demo cortaba ahí. Un banco de más son 6 KB de cartucho; un corte es
        # un mapa que no entra.
        indice_global, bancos, indice_por_mapa = {}, [], []
        for mapa in mapas:
            propio = {}
            for par, datos in (mapa["sprite"][8].items()
                               if mapa["sprite"] else ()):
                clave = (par, datos)
                if clave not in indice_global:
                    if any(k[0] == par for k in indice_global):
                        print("  mapa %d: %s:%d va con un banco de poses "
                              "propio, cuantizado distinto que en otro mapa"
                              % (mapa["id"], par[0], par[1]))
                    indice_global[clave] = len(bancos)
                    bancos.append(datos)
                propio[par] = indice_global[clave]
            indice_por_mapa.append(propio)
        handle.write("; --- las poses de los personajes que cambian de pose, "
                     "de toda la ROM ---\n")
        # **Cada pose una vez**, aunque la repitan varios personajes o el
        # mismo: las tablas de poses llevan un puntero por pose —`npc_poses`,
        # `actor_table`—, así que dos iguales apuntan al mismo bloque y la ROM
        # sube los mismos bytes desde otro lugar. Pasa mucho: los cuadros de
        # caminata iguales de un mismo CharSet, y los personajes que se
        # repiten entre mapas con otra cuantización que no cambió una pose.
        # Cada una con su `.bloque`, porque se sube por DMA.
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
        print("  poses: %d distintas de %d, %.1f KB menos"
              % (len(etiqueta_de_pose), SPRITE_POSES * len(bancos),
                 (SPRITE_POSES * len(bancos) - len(etiqueta_de_pose))
                 * POSE_BYTES / 1024.0))
        indice_por_mapa = [{par: poses_de_banco[g] for par, g in propio.items()}
                           for propio in indice_por_mapa]
        escribir_crudos(os.path.dirname(os.path.abspath(path)), mapas)
        materiales = Materiales(deduplicar=True,
                                comprimidos=comprimidos
                                or comprimir_los_bloques(mapas))
        handle.write("; Los topes de LZ2, que cobra descomprimir.s\n"
                     "LZ2_TOPE_FONDO = $%04X\n"
                     "LZ2_TOPE_ENCIMA_Y_SPRITES = $%04X\n"
                     "LZ2_TOPE_ANIM = $%04X\n"
                     "LZ2_TOPE_GRILLA = $%05X\n\n"
                     % (LZ2_TOPE_FONDO, LZ2_TOPE_ENCIMA_Y_SPRITES,
                        LZ2_TOPE_ANIM, LZ2_TOPE_GRILLA))
        etiquetas = []
        for numero, mapa in enumerate(mapas):
            handle.write("; --- %d: mapa %d %r ---\n"
                         % (numero, mapa["id"], mapa["nombre"]))
            texto, suyas = datos_del_mapa(mapa, numero,
                                          indice_por_mapa[numero], materiales)
            etiquetas.append(suyas)
            handle.write(texto)
            handle.write("\n")
        if True:
            # La ventana de mensaje es una sola para toda la ROM —el mismo
            # skin, el mismo tamaño— así que va como bloque global y no en la
            # tabla de mapas. Lo único que depende del mapa es en qué paleta
            # entra, y eso se resuelve arriba, al elegir el reparto de CGRAM.
            #
            # BG2 va en 4 bits, así que su celda **sí** usa los tres bits de
            # paleta —a diferencia del fondo, que va en 8 y los ignora—. La
            # ventana va en la 0 y es la misma para todos los mapas: sus celdas
            # se emiten una sola vez. Que el fondo no la pise sale del reparto
            # —arranca en `CGRAM_RESERVADAS`— pero se controla igual: si la
            # pisara, la ventana saldría con los colores del mapa y ninguna
            # comparación de un solo mapa lo vería.
            paleta = paleta_de_la_ventana()
            for m in mapas:
                if len(m["cram_words"]) + CGRAM_RESERVADAS > \
                        m["above"][3] * COLORS_PER_PALETTE:
                    raise SystemExit(
                        "el fondo del mapa %d usa %d entradas de CGRAM desde "
                        "la %d y pisa la capa de encima, que arranca en la %d"
                        % (m["id"], len(m["cram_words"]), CGRAM_RESERVADAS,
                           m["above"][3] * COLORS_PER_PALETTE))
            handle.write("\n; --- la ventana de mensaje ---\n")
            handle.write(bloque("ventana_tiles", ventana["tiles"]) + "\n")
            # Sólo las `CGRAM_RESERVADAS` de abajo: de la 8 para arriba es
            # del fondo, y subir las dieciséis se lo borraría.
            handle.write(bloque("ventana_cgram",
                                b"".join(w.to_bytes(2, "little")
                                         for w in ventana["cram"]
                                         [:CGRAM_RESERVADAS])) + "\n")
            # Un plano por cada base de la ventana que usan los repartos: el
            # índice de tile va corrido detrás de la capa de encima, y la
            # capa de encima mide 128 o 256 según el reparto. Ver
            # `VENTANA_BASES` y `estampar_ventana`.
            for base, etiqueta in zip(VENTANA_BASES, ("ventana_celdas",
                                                      "ventana_celdas_256")):
                plano = bytearray()
                for fila in ventana["celdas"]:
                    for celda in fila:
                        # Con la prioridad de la capa de encima para que tape
                        # al héroe y a los NPCs.
                        plano += (entry(base + celda, False, False,
                                        PRIORITY_ABOVE)
                                  | (paleta << 10)).to_bytes(2, "little")
                handle.write(bloque(etiqueta, bytes(plano)) + "\n")
            # El área de texto sin texto: los 240 tiles que la ROM copia al
            # buffer antes de dibujar encima. Van en el orden en que la ROM los
            # necesita, o sea el de las celdas.
            handle.write(bloque("ventana_fondo", ventana["fondo"]) + "\n")
            # La fuente y los colores. `fuente_color` es el índice de paleta de
            # cada una de las doce filas del glifo: el degradé de RM2k sale de
            # una máscara de 16x16, pero cada fila es de un solo color, así que
            # doce bytes alcanzan y la ROM no tiene que muestrear nada.
            handle.write(bloque("fuente_tabla", ventana["fuente"]) + "\n")
            pre = fuente_prerender(ventana["fuente"], ventana["color"],
                                   ventana["sombra"])
            for fase, datos in enumerate(pre):
                handle.write(bloque("fuente_pre%d" % fase, datos) + "\n")
            handle.write(bloque("mensajes", ventana["mensajes"]) + "\n")
            # Cuánto mide y cuánto puede medir: la ROM no los usa, los lee
            # `just espacio` de la tabla de símbolos. El tope es lo que
            # alcanza el operando de `OP_MESSAGE`, de 16 bits y de a
            # `MENSAJES_PASO` bytes.
            handle.write("MENSAJES_BYTES = %d\nMENSAJES_TOPE = %d\n"
                         % (len(ventana["mensajes"]),
                            0x10000 * eventos.MENSAJES_PASO))
        # --- el cartel del ShowPicture ---
        #
        # Sus quince colores tal cual salieron de `imagen.convertir`, en el
        # orden en que los tiles los indexan. Van en un bloque global y no en
        # la tabla de mapas porque el cartel es uno solo por ROM; lo que sí es
        # del mapa es en qué tile y en qué paleta quedó, que va en el registro.
        #
        # La entrada 0 va también, en negro, y no porque se dibuje —el índice 0
        # de un sprite es transparente— sino para que la ROM suba las dieciséis
        # de una: el DMA arranca en la entrada de la paleta, no una más
        # adelante, y descontar uno acá es justo la cuenta que se escribe bien
        # de un lado y mal del otro.
        handle.write("\n; --- el cartel del ShowPicture ---\n")
        colores = ([(0, 0, 0)] + list(cartel["paleta"])) if cartel else [(0, 0, 0)]
        handle.write(bloque("imagen_cgram",
                            b"".join(cgram_word(c).to_bytes(2, "little")
                                     for c in colores)) + "\n")
        # Los productos del destello de pantalla: `d * nivel // 31` para d y
        # nivel de 0 a 31, en la fila del nivel. Es la cuenta de
        # `destellar_canal`, y la ROM la leía del multiplicador y el divisor
        # para cada una de las 96 entradas de sus tablas en cada cuadro
        # impar: ver `una_tabla_de_destello`.
        handle.write(bloque("prod31_tabla", bytes(
            d * n // 31 for n in range(32) for d in range(32))) + "\n")
        handle.write(animaciones_asm(animaciones or {}, mapas))
        # --- la pantalla de título ---
        #
        # Va entera en BG1, que en modo 3 tiene ocho bits por pixel: la imagen
        # direcciona CGRAM en directo y no hay que repartirla en paletas de
        # dieciséis, que es lo que un mapa sí tiene que hacer porque los
        # sprites necesitan las suyas. Acá no hay sprites.
        #
        # Los tiles se deduplican como los del mapa. La imagen tiene mucho negro
        # —la mitad de abajo, que es donde va el menú— así que de las 1024
        # celdas quedan menos de 500.
        #
        # La imagen va comprimida, junto con los colores del menú, en su fila
        # de `pantallas_tabla`: ver "las pantallas completas", abajo. Acá
        # queda el menú, que no es de la imagen.
        handle.write("\n; --- la pantalla de título ---\n")
        if titulo is None:
            handle.write(bloque("titulo_menu_tiles", b"\x00") + "\n")
            handle.write(bloque("titulo_menu_celdas", b"\x00") + "\n")
        else:
            # El menú: un banco de tiles de 4 bits y un tilemap por opción
            # seleccionada. Mover el cursor es subir el otro tilemap, y por eso
            # van seguidos y del mismo tamaño: la ROM los indexa multiplicando.
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

        # --- las pantallas completas: la de Game Over y la de título ---
        #
        # Cada una es un flujo LZ2 con los tiles, el tilemap y los colores, y
        # su fila en `pantallas_tabla`, que es lo que lee `pantalla_subir`: ver
        # tools/port/pantalla_completa.py. Sin imagen de Game Over,
        # GAME_OVER_TILES en 0 y la ROM vuelve al título sin pantalla, como
        # hasta el 2026-09-28; sin pantalla de título, TITULO_TILES en 0 y
        # ninguna fila. Sin ninguna de las dos PANTALLA_FILA no se define, y
        # `pantalla_subir` no se arma.
        handle.write("\n; --- las pantallas completas ---\n")
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
                "; La fila de cada pantalla en `pantallas_tabla`: dónde está su\n"
                "; flujo, cuántos bytes de tiles y de colores trae, y desde qué\n"
                "; color de CGRAM van. Ver `pantalla_subir`.\n"
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

        # La pantalla de ranuras, que **va en toda ROM** y no sólo en las que
        # llevan título: la abre el save point desde adentro del juego. Hasta
        # el 2026-09-10 salía sólo con la pantalla de título y sin ella quedaba un byte
        # de relleno con `RANURA_TILES` en cero; y un DMA de "cero bytes" son
        # 65536, así que abrirla desde una ROM sin título llenaba la VRAM de
        # basura. Es la "pantalla negra con basura arriba" que durante un
        # tiempo se anotó como un misterio del contexto del intérprete.
        #
        # Su banco de tiles es propio: comparte la dirección de VRAM con el del
        # menú del título, pero no los tiles, porque las dos pantallas se suben
        # enteras cada vez que se entra a una.
        handle.write("\n; --- la pantalla de ranuras ---\n")
        datos = bytearray()
        for celda in ranuras["tiles"]:
            datos += pack_tile(celda, planes=4)
        handle.write(bloque("ranura_tiles", bytes(datos)) + "\n")

        # El banco de las ranuras y del menú va **con el bit de prioridad
        # puesto**, como los glifos de ítems: la elección de actor prende
        # BG1 con sus ventanas, y en modo 3 BG1 de prioridad 0 queda arriba
        # de BG2 de prioridad 0 —la barra roja taparía la fila—. En las
        # demás pantallas de este banco BG1 está apagado y el bit no cambia
        # un pixel; los sprites de la experiencia lo descartan.
        def celdas_asm(bloques):
            plano = bytearray()
            for celdas in bloques:
                for indice in celdas:
                    plano += entry(indice, False, False,
                                   priority=1).to_bytes(2, "little")
            return bytes(plano)

        # Cada bloque de celdas va con etiqueta propia y se nombra por una
        # tabla de punteros, igual que los temas de música. Es más ROM que
        # calcular el desplazamiento con corrimientos —tres tablas de un byte
        # por bloque— y a cambio la ROM no tiene que multiplicar por 96 ni por
        # 192 en ningún lado. Esa multiplicación estaría escrita acá y allá,
        # que es exactamente la forma de error que este repo ya pagó tres
        # veces.
        #
        # El orden: primero las dos cabeceras —cargar y guardar— y después, por
        # ranura, las cuatro variantes como llena * 2 + cursor.
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
        # Y detrás, por actor que pueda entrar al grupo, su cara: la ROM la
        # escribe encima de la fila según lo que la partida guardó. Las celdas
        # de las caras llevan la paleta en sus tres bits, que acá sí se usan:
        # es BG2 a 4bpp.
        #
        # Su nombre y su nivel **no** son bloques: los compone la ROM con
        # glifos, ver "lo que depende del actor" en menus.py. Eso es lo que
        # hace que el banco no crezca con la cantidad de actores.
        bloque_de_cara = {}
        for actor in sorted(ranuras["caras"]):
            nombre = "ranura_cara_%d" % actor
            handle.write(bloque(nombre, celdas_asm([ranuras["caras"][actor]]))
                         + "\n")
            bloque_de_cara[actor] = len(bloques_ranura)
            bloques_ranura.append(nombre)
        # Y los del menú de pausa, que viven en el mismo banco de tiles: cada
        # orden en sus dos variantes —la 1 es deshabilitada, en la paleta de
        # lo gris—, la moneda, y el texto de una fila del grupo, que es uno
        # solo para las cuatro y para todos los actores. El cursor y los
        # glifos no van como bloques: son dos celdas cada uno y la ROM las
        # escribe palabra por palabra, ver `ranura_glifo_celdas`.
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
        # Y la pantalla de ítems, que tiene banco propio: la fuente de a una
        # letra por celda, sus dos paletas, y el texto de cada ítem que la ROM
        # conoce —nombre y dos renglones de descripción—, en ASCII.
        datos = bytearray()
        for celda in ranuras["items_tiles"]:
            datos += pack_tile(celda, planes=4)
        handle.write(bloque("items_tiles", bytes(datos)) + "\n")
        def paletas_cgram(paletas):
            return b"".join(
                cgram_word(c).to_bytes(2, "little") for paleta in paletas
                for c in list(paleta) + [(0, 0, 0)] * (constantes.MENU_CGRAM
                                                       - len(paleta)))

        # Las dos primeras, que suben con el banco en todas las pantallas que
        # lo usan; la de "sube" y la roja van aparte y las sube sólo la de
        # equipo, porque en la pelea las entradas de la tercera paleta en
        # adelante son las del fondo —`escena.CGRAM_BASE`— y subirlas ahí no
        # le serviría a nadie.
        handle.write(bloque("items_cgram", paletas_cgram(
            ranuras["items_paletas"][:menus_mod.ITEM_SUBE])) + "\n")
        handle.write(bloque("item_cgram_sube", paletas_cgram(
            ranuras["items_paletas"][menus_mod.ITEM_SUBE:])) + "\n")
        # Las ventanas de las pantallas de ítems y de equipo, en BG1: ver
        # `ITEM_VENTANAS` y `pantallas.EQ_VENTANAS`. Los tiles y los colores
        # son los mismos para las dos. Cada tilemap va sin las filas de abajo
        # que la pantalla no muestra, y cada cursor como las dos filas de
        # celdas que ocupa, que la ROM copia encima: 128 bytes.
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
        # Las ventanas de la tienda, en BG1 con su propia base: ver
        # `pantallas.TI_VENTANAS` y `tienda_compacta`, que dice qué se guarda.
        # Los tramos de cada capa son `(palabra de la VRAM, byte de origen en
        # `ti_marco_filas`, bytes)`, terminados en tres ceros; las barras,
        # `(palabra de la VRAM, byte de origen en `ti_marco_parches`, bytes
        # por fila, filas)`.
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
        # La pantalla de End Game, entera: ver tools/port/fin_del_juego.py.
        # Las dos paletas van seguidas, la de "Yes" primero: la ROM elige
        # una multiplicando.
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
        # Textos muertos **detrás de los de los ítems y delante de todos los
        # demás**, para que los índices de la batalla pasen de 255 en un
        # cartucho de un mapa: reproducirlo de verdad pide los cincuenta y
        # siete ítems de `abl`, o sea sus veintinueve mapas y dos minutos y
        # medio de conversor por caso. Tuvo un hermano, `--relleno-de-mensajes`,
        # que hacía lo mismo con el bloque de textos; ése se fue el 2026-09-20
        # porque el empujón lo puede dar un caso —ver el cartucho `test-special` en
        # el archivo de proyecto— y éste no, porque lo que corre no es un
        # texto sino un índice.
        #
        # **Van acá y no al principio, que es donde estaban hasta el
        # 2026-09-20.** El nombre de un ítem no se nombra por una tabla sino
        # por la cuenta `3k` —`3k + 1` y `3k + 2` son sus dos renglones de
        # descripción, ver `texto_escribir`—, así que un texto muerto delante
        # del primero corre todos los ítems y la ROM termina dibujando los
        # muertos, que miden cero: la lista "Use Item" de la pelea salía con
        # el cursor y las cantidades y sin un solo nombre. Con el relleno acá
        # el flag vuelve a cumplir lo que promete, que es no cambiar un pixel.
        for _ in range(ranuras.get("relleno_textos") or 0):
            item_textos_ofs.append((0, 0))
        # Y los fijos, detrás: los parámetros y las ranuras del equipo, y el
        # nombre de cada actor que puede entrar al grupo. Ver pantallas.py.
        P = pantallas_mod
        B = batalla_mod
        db = ranuras["db"]
        texto_param = [texto_nuevo(t[:P.EQ_PARAM_VALOR - 1])
                       for t in db.term_params]
        texto_ranura = [texto_nuevo(t[:P.EQ_RANURA_TERM_ANCHO])
                        for t in db.term_equipo]
        texto_actor = {a: texto_nuevo(db.actors[a].name)
                       for a in ranuras["actores"]}
        # Los de la tienda: los once mensajes de cada uno de los tres juegos,
        # de a dos renglones —`partir_descripcion`, como en pantallas.py—, y
        # "Owned Items", "Equipped Items" y la moneda.
        texto_tienda = None
        for juego in range(3):
            term = P.terminos_tienda(db, juego)
            for nombre, _termino in P.TI_TERMINOS:
                renglones = menus_mod.partir_descripcion(term[nombre])
                # Fuera de la principal, el mensaje va en una ventana de un
                # renglón: `ti_mensaje` escribe sólo el primero.
                if renglones[1] and nombre not in ("saludo", "resaludo"):
                    raise SystemExit(
                        "el mensaje %r de la tienda, del juego %d, ocupa dos "
                        "renglones y su ventana tiene uno"
                        % (term[nombre], juego))
                for renglon in renglones:
                    t = texto_nuevo(renglon)
                    if texto_tienda is None:
                        texto_tienda = t
        texto_tengo = texto_nuevo(P.lcf_termino(db, P.TI_TERMINO_TENGO))
        texto_llevo = texto_nuevo(P.lcf_termino(db, P.TI_TERMINO_LLEVO))
        texto_moneda = texto_nuevo(db.term_gold)
        # Y los de la batalla: los quince términos del LDB que la pantalla usa
        # —en el orden de `reglas.BA_TERMINOS`, que es el que la ROM
        # indexa— y el nombre de cada enemigo que alguna tropa del cartucho
        # traiga. Las tres órdenes van **ya recortadas**, por
        # `pantallas.texto_de_orden`: el LDB las trae con espacios adelante y
        # eso correría el texto de su columna.
        term_batalla = reglas.terminos_batalla(db)
        texto_batalla = None
        victoria = P.renglones_de_la_victoria(term_batalla["victoria"])
        if len(victoria) > P.BA_VIC_TERMINO_MAX:
            raise SystemExit("el término de la victoria ocupa %d renglones y "
                             "la ventana le deja %d: %r"
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
        # Y el renglón de un caído que un ítem levantó: el `message_recovery`
        # del estado de muerto, que va pegado al nombre —"Core has revived!"—.
        # No es un término sino un dato del estado, así que va aparte y con su
        # propio índice. Ver `ba_mensaje`.
        texto_revivio = texto_nuevo(P.texto_revivio(db))
        # El segundo renglón de la victoria, vacío si entra en uno: va aparte
        # para no correr los índices de `BA_TERMINOS`.
        texto_victoria2 = texto_nuevo((victoria + [""])[1])
        enemigos_rom = sorted({e for numero in tropas
                               if numero in db.troops
                               for e in db.troops[numero].members})
        texto_enemigo = {e: texto_nuevo(menus_mod.texto_de_item(
            db.enemies[e].name, P.BA_NOMBRE_ANCHO)) for e in enemigos_rom}
        # Y los de las habilidades: las que sabe algún actor que puede entrar
        # al grupo, **a su nivel del LDB** —ver `batalla.habilidades_de`—,
        # ordenadas por número, que es el orden en que el menú las pone. Con el
        # grupo de la intro son siete: 129, 130, 131, 143, 144, 146 y 150.
        #
        # **Todas las que pueden llegar a saber**, y no sólo las del LDB: un
        # `ChangeSkills` le enseña al actor lo que la tabla de aprendizaje no
        # tiene, y desde el 2026-09-21 eso se ve en la pelea. Son las de sus
        # pares de `eventos.HABILIDAD_RANURA` que la pelea sabe ofrecer.
        #
        # Y las que usa algún enemigo de las tropas del cartucho, desde el
        # 2026-09-27: `ShortCircuit`, de los de la planta de reciclaje. Ver
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
        # Y el nombre **entero** de las que se aprenden al subir de nivel, que
        # es lo que dice "<habilidad> acquired!" en la victoria: el de la lista
        # va cortado a su columna, y hay de éstas que la pelea no sabe ofrecer
        # —Lurk In Shadows, de Arden— y no están en la lista. Ver
        # `hab_par_aprende_txt`.
        ensenadas = {h for (a, h) in eventos.HABILIDAD_RANURA
                     if a in ranuras["actores"] and a in db.actors
                     and B.nivel_en_que_aprende(db, a, h)
                     > X.nivel_inicial(db.actors[a])}
        texto_hab_entero = {
            h: texto_nuevo(menus_mod.texto_de_item(db.skills[h].name, 255))
            for h in sorted(ensenadas)}
        # Los dos renglones que RM2k dice al usarla: `using_message1` va detrás
        # del nombre del que la usa y `using_message2` solo, en el renglón de
        # abajo. `GetSkillFirstStartMessage2k` y su hermana.
        texto_hab_msg1 = {h: texto_nuevo(db.skills[h].using_message1)
                          for h in habilidades_rom}
        texto_hab_msg2 = {h: texto_nuevo(db.skills[h].using_message2)
                          for h in habilidades_rom}
        # Y cómo se llama la orden de cada actor: `Game_Actor::GetSkillName`,
        # o sea su `skill_name` —"AgentTrain", "Telepathy", "Slicing"— y no el
        # `command_skill` del LDB. Va recortada como las otras cuatro órdenes.
        texto_hab_orden = {a: texto_nuevo(P.texto_de_orden(
            B.nombre_de_orden_habilidad(db, a))) for a in ranuras["actores"]}
        handle.write(bloque("item_textos", bytes(item_textos) or b"\x00")
                     + "\n")
        if len(bloques_ranura) > 255:
            raise SystemExit("la pantalla de ranuras tiene %d bloques y las "
                             "tablas que los nombran son de un byte"
                             % len(bloques_ranura))
        # Las tablas que los nombran **no van acá**: la ROM las lee con
        # `lda ranura_bloque_lo, x`, que direcciona el banco de datos, así que
        # tienen que vivir en el banco 0 junto con el código. Se emiten más
        # abajo, en el segmento TABLAS.
        #
        # La paleta va rellena hasta las TITULO_MENU_CGRAM entradas, que es lo
        # que la ROM sube de una vez: si el texto usa menos colores, el DMA
        # leería lo que siga en el cartucho.
        colores = []
        for paleta in ranuras["paletas"]:
            paleta = list(paleta)
            colores += paleta + [(0, 0, 0)] * (constantes.MENU_CGRAM
                                               - len(paleta))
        handle.write(bloque("ranura_cgram",
                            b"".join(cgram_word(c).to_bytes(2, "little")
                                     for c in colores)) + "\n")

        handle.write('\n.segment "TABLAS"\n')
        # Los bloques de celdas de la pantalla de ranuras se nombran por
        # punteros, y las tres tablas van en el banco 0 porque la ROM las lee
        # con `lda ranura_bloque_lo, x`. Lo mismo `ranura_vram`, que dice a qué
        # dirección del tilemap va cada fila: la cuenta sale de la misma
        # geometría que dibujó el texto y por eso vive en un solo lado.
        for campo, prefijo in (("lo", "<"), ("hi", ">"), ("bk", "^")):
            handle.write("ranura_bloque_%s:\n    .byte %s\n"
                         % (campo, ", ".join(prefijo + e
                                             for e in bloques_ranura)))
        fila_de = [RANURA_MAP + (menus_mod.RANURA_Y
                                 + n * menus_mod.RANURA_SALTO)
                   // constantes.CELL * 32 for n in range(RANURAS)]
        handle.write("ranura_vram:\n    .word %s\n" % ", ".join(
            str(v) for v in fila_de))
        # A dónde van las caras —de a cuatro entradas por ranura, para que el
        # índice sea la ranura por cuatro más el lugar, sin multiplicar por
        # tres— y el nombre del líder.
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
        # El menú de pausa: sus bloques, y a dónde va cada cosa en el tilemap,
        # en palabras. La geometría es la de `menus.py` y sale de ahí.
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
               # Y a cuántas celdas de la primera del bloque del actor cae la
               # de las centenas de sus HP, que es lo que `menu_hp_escribir`
               # le suma a `menu_fila_vram`.
               T.MENU_HP_CIFRAS,
               T.MENU_HP_FILA * 32 + T.MENU_HP_COL - T.MENU_ACTOR_COL,
               # La cara va en la esquina de arriba a la izquierda de la fila
               # —de ahí que no lleve desplazamiento— y las tres tiras que la
               # ROM compone, cada una en la suya.
               T.CARA_CELDAS, T.MENU_NOMBRE_COLS,
               T.MENU_NOMBRE_FILA * 32 + T.MENU_NOMBRE_COL - T.MENU_ACTOR_COL,
               T.MENU_NIVEL_FILA * 32 + T.MENU_NIVEL_COL - T.MENU_ACTOR_COL,
               T.MENU_MAX_CIFRAS,
               T.MENU_HP_FILA * 32 + T.MENU_MAX_COL - T.MENU_ACTOR_COL))
        # Qué órdenes hacen algo: 1 sí, 0 no. La de guardar además mira el
        # permiso, en la ROM.
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
        # Las dos celdas del cursor, arriba y abajo: la ROM las escribe de a
        # una palabra.
        handle.write("menu_cursor_celdas:\n    .word %s\n" % ", ".join(
            "$%04X" % entry(c, False, False, priority=1)
            for c in menu["cursor"]))
        # Y lo que la pantalla compone en caliente, que va **fuera del banco
        # 0**: se lee con `lda f:`, y son casi mil bytes que al banco del
        # código le harían falta. Los glifos están indexados por carácter
        # —desde ITEM_PRIMER_CARACTER, como los de la pantalla de ítems— y las
        # letras que este cartucho no usa quedan en la celda vacía: nadie las
        # pide, y una tabla completa se indexa sin restar nada más.
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
        # La línea de la experiencia, que la ROM dibuja con sprites: ver
        # `MENU_EXP_X` en menus.py. El término son cuatro tiles —dos de
        # ancho, arriba y abajo— y las cifras salen de `ranura_glifo_celdas`.
        handle.write(".bloque %d\nmenu_exp_termino:\n    .word %s\n" % (
            2 * len(menu["exp_termino"]), ", ".join(
                "$%04X" % entry(c, False, False)
                for c in menu["exp_termino"])))
        # La elección de actor: sus ventanas en BG1 —ver `OBJETIVO_VENTANAS`
        # en menus.py—. Un solo tilemap, el con ítem, y la barra sólo en el
        # rectángulo que cambia: ver `menus.objetivo_compacto`. Y el nombre
        # de cada medicina en dos renglones, en ASCII, con una tabla de un
        # byte por `k` que dice cuál es —$FF si no es medicina—: sólo las
        # medicinas abren esta pantalla.
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
                     if ranuras["items_db"][n].type == lcf.ITEM_TIPO_MEDICINA]
        if len(medicinas) > 255:
            raise SystemExit("%d medicinas no entran en `objetivo_nombre_de`"
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
        # El texto de cada actor, en ASCII: el nombre —con espacios detrás,
        # que son los que borran lo que hubiera—, las dos cifras del nivel y
        # el máximo de HP detrás de su barra. **Las tres juntas, en una fila
        # por actor**, para que la ROM tenga una sola dirección que calcular y
        # tres desplazamientos que son constantes.
        db_ranuras = ranuras["db"]
        if (RANURA_TEXTO_NIVEL < menus_mod.MENU_NOMBRE_COLS
                or RANURA_TEXTO_MAX + menus_mod.MENU_MAX_CIFRAS
                > RANURA_TEXTO_ANCHO):
            raise SystemExit("las tres tiras del actor no entran en los %d "
                             "bytes de su fila" % RANURA_TEXTO_ANCHO)
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
        # La pantalla de ítems. `item_k` va del número de RM2k a su lugar en
        # las tablas de la ROM, $FF si esta ROM no lo conoce; lo demás es por
        # lugar. `item_uso`: bit 0 si va en blanco y A hace algo, bit 1 si
        # usarlo gasta uno —los de switch con usos—, bit 2 si abre la elección
        # de actor —las medicinas—, bit 3 si es un arma a dos manos. Los textos
        # van de a tres por ítem —el nombre y los
        # dos renglones de la descripción—: el texto `t` es el `3k + campo`.
        items = ranuras["items"]
        db_items = ranuras["items_db"]
        if len(items) > 255:
            raise SystemExit("%d ítems no entran en las tablas de un byte"
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

        # `item_k` va fuera del banco 0 —se lee con `lda f:item_k, x`—: el
        # banco del código se llenó con el paquete de audio.
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
        # `item_switch` va fuera del banco 0 —se lee con `lda f:item_switch, x`,
        # una sola vez por ítem usado— porque los encuentros al azar lo pasaron
        # por 34 bytes el 2026-09-13. Son 124: la tabla más grande de las que
        # se leen con X y no están en ningún lazo por cuadro.
        handle.write('.segment "RODATA"\n')
        words_asm("item_switch", [db_items[n].switch_id for n in items],
                  declarar=True)
        handle.write('.segment "TABLAS"\n')
        # Lo que cada ítem hace en una pelea: si entra en la lista que se
        # ofrece y cuánto cura. La regla de cuáles entran es
        # `batalla.item_usable_en_batalla`, o sea `Game_Party::IsItemUsable`
        # con la pelea abierta más lo que este port sabe hacer; la cuenta de
        # cuánto cura es `Game_BattleAlgorithm::Item::vExecute`.
        # **Fuera del banco 0**, como `item_k` y por lo mismo: con los mapas de
        # `abl` el área de código quedó en 32775 de 32704 al ponerlas
        # acá. La pelea las lee con `lda f:item_batalla, x`.
        handle.write('.segment "RODATA"\n')
        bytes_asm("item_batalla", [
            1 if B.item_usable_en_batalla(db_items[n]) else 0 for n in items],
            declarar=True)
        bytes_asm("item_cura_rate", [db_items[n].recover_hp_rate
                                     for n in items], declarar=True)
        words_asm("item_cura_hp", [min(db_items[n].recover_hp, 0xFFFF)
                                   for n in items], declarar=True)
        # Y lo que una medicina hace fuera de la pelea, que es
        # `Game_Battler::UseItem` entero: los SP, como los HP, y
        # `item_medicina` con tres bits —1 si es `ko_only`, 2 si saca el
        # estado de muerto, que es el primero de `state_set` y lo que levanta
        # a un caído, 4 si usarla gasta uno, que es `uses` distinto de cero—.
        # Los demás estados de `state_set` no van: fuera de la pelea este port
        # no tiene estados, así que sacarlos nunca sirve. Ver `medicina_usar`.
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
        # Las cuatro de los textos van **fuera del banco 0**, como `item_k` y
        # por lo mismo: ahí no entran. Con los diez mapas de `abl` el
        # área de código quedaba en 32622 de 32704 —ochenta y dos bytes
        # libres— y el cartel del `ShowPicture` no entraba. Se leen con
        # `lda f:item_txt_lo, x`, que cuesta un byte y un ciclo por lectura en
        # trece lugares, ninguno adentro de un lazo por cuadro.
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
        # Las dos celdas de cada carácter, arriba y abajo: primero los 95 en
        # blanco, después en gris y después en el color de "sube". El carácter
        # `c` en la variante `g` está en
        # `g * ITEM_GLIFOS_GRIS + (c - ITEM_PRIMER_CARACTER) * 4`.
        # --- el equipo ---
        # Por ítem conocido: su tipo, lo que suma —ataque, defensa, espíritu,
        # agilidad, con signo— y quién puede ponérselo, un bit por actor. Por
        # actor, del 0 al último del LDB: sus parámetros del nivel y su equipo
        # inicial, que la ROM copia a `FAR_EQUIPO` en el reset. Y dónde va
        # cada cosa en el búfer de la pantalla, en bytes: fila * 64 + col * 2.
        actores_n = max(db.actors) + 1

        def pos(fila, col):
            return fila * 64 + col * 2

        bytes_asm("item_tipo", [db_items[n].type for n in items])
        handle.write('.segment "RODATA"\n')     # ídem: ver `item_txt_lo`
        words_asm("item_puntos", [p & 0xFFFF for n in items
                                  for p in db_items[n].puntos],
                  declarar=True)
        # Y lo que cuesta atacar con cada uno: el `sp_cost` de las armas, cero
        # para lo demás —`batalla.sp_del_arma`—. La pelea lo lee una vez por
        # actor al armarse.
        bytes_asm("item_sp", [db_items[n].sp_cost
                              if db_items[n].type == lcf.ITEM_TIPO_ARMA
                              else 0 for n in items], declarar=True)
        # `item_actores` va también fuera del banco 0 —se lee con
        # `lda f:item_actores, x`—: son 496 bytes, los más gordos que le
        # quedaban a `TABLAS`, y el banco 0 se pasó. No es una previsión: el
        # 2026-09-13 `just demo` cortaba con "el área no
        # entra: 32719 bytes en 32704" y ningún caso de la tanda lo veía.
        # Se lee una vez por ítem al armar la lista de la pantalla de equipo,
        # así que el ciclo de más del direccionamiento largo no se nota.
        bytes_asm("item_actores", [
            sum(1 << b for b in range(8)
                if 8 * byte + b + 1 < actores_n
                and db_items[n].equipable_por(8 * byte + b + 1))
            for n in items for byte in range(8)], declarar=True)
        # `actor_params` va fuera del banco 0 —se lee con
        # `lda f:actor_params, x`, una sola vez por pantalla de equipo— por lo
        # mismo que `item_k`: son 488 bytes y el banco del código se llenó, y
        # esta vez con el dibujo de las animaciones de batalla.
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
        # `eq_barra` cuenta las filas de las ranuras y las de la lista desde
        # la misma: son la misma ventana.
        if P.EQ_LISTA_FILA0 != P.EQ_RANURA_FILA0:
            raise SystemExit("la lista del equipo arranca en la fila %d y las "
                             "ranuras en la %d" % (P.EQ_LISTA_FILA0,
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
        # --- la batalla ---
        # Los HP máximos de cada actor a su nivel, por número de actor. Van
        # aparte de `actor_params`, que lleva los cuatro que la pantalla de
        # equipo muestra; los HP no los toca el equipo, como en RM2k.
        handle.write('.segment "RODATA"\n')
        words_asm("actor_hpmax", [
            (reglas.parametro_de(db.actors[a], "maxhp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)], declarar=True)
        # Y los SP, que son estado desde el 2026-09-13 por lo mismo que los HP:
        # las habilidades los gastan. Ver `hp_inicial_poner` en tools/runtime/banco1.s.
        words_asm("actor_spmax", [
            (reglas.parametro_de(db.actors[a], "maxsp")
             if a in db.actors else 0) & 0xFFFF
            for a in range(actores_n)], declarar=True)
        handle.write(experiencia_asm(db, ranuras["actores"], actores_n))
        # --- las habilidades ---
        #
        # Una fila por habilidad que el cartucho lleva, en el orden de
        # `habilidades_rom`, que es por número de RM2k. Los campos son los de
        # `lcf.Skill` y las cuentas que los usan están en `batalla.py`:
        # `efecto_habilidad` es `Algo::CalcSkillEffect` y `costo_de` es
        # `CalcSkillCost`.
        #
        # Van **fuera del banco 0** y declaradas con `.bloque`, como todo lo
        # que la pelea lee con `lda f:`: el banco del código está lleno, y una
        # tabla partida entre dos bancos se leería mal desde la mitad.
        lugar_hab = {h: k for k, h in enumerate(habilidades_rom)}
        # Que todas las que llegan acá sean de las que la pelea sabe ofrecer lo
        # garantiza `batalla.habilidad_usable`, que es el filtro que
        # `habilidades_de` aplica de los dos lados. Se vuelve a comprobar por
        # si alguna vez se emitieran desde otro lado: un alcance de a muchos o
        # un costo de tres cifras se dibujarían mal en silencio.
        for h in habilidades_rom:
            if not B.habilidad_usable(db.skills[h]):
                raise SystemExit(
                    "la habilidad %d —tipo %d, alcance %d, %d SP— no es de las "
                    "que esta pelea sabe ofrecer" % (h, db.skills[h].type,
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
        # El tipo: 0 es `normal` y 3 es `switch`, que es la que prende un
        # switch y no hace nada más. Ver `Skill::vExecute`.
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
        # Qué toca, un bit por cosa, en el orden en que `Skill::vExecute` las
        # mira —que es el orden en que consume azar y por eso importa—: HP, SP,
        # ataque, defensa, espíritu y agilidad. El bit 6 dice si apunta a
        # enemigos —`Algo::SkillTargetsEnemies`— y el 7 si ignora la defensa.
        bytes_asm("hab_afecta", [
            (1 if db.skills[h].affect_hp else 0)
            | (2 if db.skills[h].affect_sp else 0)
            | (4 if db.skills[h].affect_attack else 0)
            | (8 if db.skills[h].affect_defense else 0)
            | (16 if db.skills[h].affect_spirit else 0)
            | (32 if db.skills[h].affect_agility else 0)
            | (64 if db.skills[h].apunta_a_enemigos else 0)
            | (128 if db.skills[h].ignore_defense else 0)
            for h in habilidades_rom], "$%02X", declarar=True)
        # Y el alcance tal cual, `rpg::Skill::Scope`: 0 un enemigo, 1 todos,
        # 2 uno mismo, 3 un aliado, 4 todo el grupo. Desde el 2026-09-27 la
        # pelea sabe los cinco: ver `batalla.blancos_de_la_habilidad`.
        bytes_asm("hab_alcance", [db.skills[h].scope for h in habilidades_rom],
                  declarar=True)
        # Los eventos comunes paralelos que sólo miran el equipo, compilados:
        # la ROM los corre al cerrar el menú si su switch está prendido. Por
        # cada uno, dónde está su switch en el bitmap —byte y máscara— y su
        # código. Ver `eventos.COMUNES_DEL_EQUIPO`.
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
        # El banco va de a palabra —su byte alto no se lee— para que la ROM
        # lo indexe con el mismo X que `comeq_cod`.
        words_asm("comeq_banco", ["^comun_equipo_%d" % n
                                  for _sw, n in del_equipo], "%s",
                  declarar=True)
        for _sw, n in del_equipo:
            handle.write(bloque("comun_equipo_%d" % n,
                                eventos.compilar_comun_del_equipo(n)) + "\n")
        # Y qué sabe cada actor, que desde el 2026-09-21 es estado: un bit por
        # par (actor, habilidad) en `FAR_HAB`, con las ranuras de
        # `eventos.HABILIDAD_RANURA`. Lo contestan la rama 4 de
        # `ConditionalBranch` —que ya trae la ranura en el bytecode— y la lista
        # de la pelea, que recorre los pares del actor: dónde arrancan
        # —`hab_par_ini`, de a palabra porque son más de 255—, cuántos son, y
        # el `k` de cada uno en las tablas `hab_*` de arriba, o $FF si ésta no
        # la sabe ofrecer. Como los pares de un actor van seguidos y por
        # número, la lista sale ordenada como la de `LearnSkill`.
        #
        # Los bits arrancan con `reglas.aprendidas_de`, que es lo que el LDB
        # dice a su nivel inicial: `hab_inicial_poner` los copia en el reset.
        pares = sorted(eventos.HABILIDAD_RANURA.items(), key=lambda x: x[1])
        hab_par_ini, hab_par_n = [], []
        for a in range(actores_n):
            suyos = [r for (actor, _s), r in pares if actor == a]
            hab_par_ini.append(suyos[0] if suyos else 0)
            hab_par_n.append(len(suyos))
            if suyos and suyos != list(range(suyos[0], suyos[0] + len(suyos))):
                raise SystemExit("los pares de habilidad del actor %d no van "
                                 "seguidos" % a)
        if max(hab_par_n, default=0) > 255:
            raise SystemExit("un actor tiene más de 255 pares de habilidad y "
                             "`hab_par_n` es de un byte")
        hab_bytes = max(1, (len(pares) + 7) // 8)
        sabe_de = {a: set(reglas.aprendidas_de(db, a)) for a in db.actors}
        bits = [0] * hab_bytes
        for (a, h), r in pares:
            if h in sabe_de.get(a, ()):
                bits[r >> 3] |= 1 << (r & 7)
        handle.write("; Cuántos bytes ocupan los bits de las habilidades en `FAR_HAB`.\n"
                     "HAB_BYTES = %d\n" % hab_bytes)
        handle.write("; La firma del formato de la partida: ver `SRAM_FIRMA`.\n"
                     "PARTIDA_FIRMA = $%04X\n" % firma_de_la_partida(
                         pares, experiencia_ranuras(db, ranuras["actores"]),
                         actores_n))
        words_asm("hab_par_ini", hab_par_ini, declarar=True)
        bytes_asm("hab_par_n", hab_par_n, declarar=True)
        bytes_asm("hab_par_k", [lugar_hab.get(h, 0xFF)
                                if a in ranuras["actores"] else 0xFF
                                for (a, h), _r in pares], declarar=True)
        bytes_asm("hab_inicial", bits, "$%02X", declarar=True)
        # Y en qué nivel enseña cada par la tabla de aprendizaje del LDB, o 0
        # si no lo enseña —los que sólo da un `ChangeSkills`—: al subir de
        # nivel, `exp_sumar` prende los bits de los pares cuyo nivel acaba de
        # pasar, que es `LearnLevelSkills(old_level + 1, new_level)`.
        bytes_asm("hab_par_nivel", [B.nivel_en_que_aprende(db, a, h)
                                    if a in db.actors else 0
                                    for (a, h), _r in pares], declarar=True)
        # Y con qué nombre lo cuenta la victoria —"<habilidad> acquired!"—,
        # o $FFFF si no se aprende subiendo de nivel desde el de arranque.
        words_asm("hab_par_aprende_txt", [
            texto_hab_entero[h] if a in ranuras["actores"]
            and B.nivel_en_que_aprende(db, a, h) > 0 and h in texto_hab_entero
            else 0xFFFF for (a, h), _r in pares], "$%04X", declarar=True)
        # 254 y no 256: `eacc_hab` usa $FF para el ataque y `ba_accion_enemiga`
        # contesta $FE cuando no le queda ninguna.
        if len(habilidades_rom) > 254:
            raise SystemExit("las habilidades del cartucho son %d y `hab_par_k` "
                             "es de un byte" % len(habilidades_rom))
        # Y cómo se llama la orden de habilidades de cada actor en el menú.
        words_asm("actor_hab_txt", [texto_hab_orden.get(a, 0xFFFF)
                                    for a in range(actores_n)], "$%04X",
                  declarar=True)
        # Las tropas que alguna pelea del cartucho pide, y los enemigos que las
        # forman. El bytecode lleva el **número de RM2k** de la tropa, así que
        # `tropa_id` es lo que la ROM busca; que la lista sea sólo la de las
        # tropas usadas no cambia un byte de ninguna página. Ver
        # `eventos.Tropas`.
        usadas = [n for n in tropas if n in db.troops]
        lugar_de = {e: k for k, e in enumerate(enemigos_rom)}
        miembros, inicios = [], []
        for numero in usadas:
            lista = db.troops[numero].members[:constantes.ENEMIGOS_MAX]
            inicios.append(len(miembros))
            miembros += [lugar_de[e] for e in lista]
        if len(miembros) > 255 or len(usadas) > 255:
            raise SystemExit("las tropas del cartucho no entran en las tablas "
                             "de un byte: %d tropas, %d miembros"
                             % (len(usadas), len(miembros)))
        words_asm("tropa_id", usadas, declarar=True)
        # La experiencia que da ganarle a cada una, ya sumada: ver
        # `experiencia.exp_de_la_tropa`. Va fuera del banco 0, como todo lo de
        # acá, porque la lee una vez por pelea.
        exp_tropa = [X.exp_de_la_tropa(db, n) for n in usadas]
        for n, exp in zip(usadas, exp_tropa):
            if exp > 0xFFFF:
                raise SystemExit("la tropa %d da %d de experiencia y la ROM "
                                 "la suma en dieciséis bits" % (n, exp))
        words_asm("tropa_exp", exp_tropa, declarar=True)
        # Y el oro, igual: `batalla.oro_de_la_tropa`. La victoria lo cuenta
        # con `ba_vic_numero`, que llega a cinco cifras.
        oro_tropa = [B.oro_de_la_tropa(db, n) for n in usadas]
        for n, oro in zip(usadas, oro_tropa):
            if oro > 0xFFFF:
                raise SystemExit("la tropa %d da %d de oro y la ROM lo suma "
                                 "en dieciséis bits" % (n, oro))
        words_asm("tropa_oro", oro_tropa, declarar=True)
        # Lo que la victoria escribe tiene que entrar en su renglón: la ROM lo
        # arma con un número o un nombre en el medio y no lo parte.
        P.cobrar_la_victoria(
            term_batalla, max(exp_tropa, default=0),
            [db.actors[a].name for a in ranuras["actores"] if a in db.actors],
            [db.skills[h].name for h in sorted(ensenadas)],
            max(oro_tropa, default=0),
            [db_items[i].name for i in sorted({db.enemies[e].drop_id
                                               for e in enemigos_rom}
                                              - {0})])
        bytes_asm("tropa_ini", inicios, declarar=True)
        # Qué miembros de cada tropa empiezan **ocultos** —el `invisible` de
        # la tropa—, un bit por lugar: los aparece una página con
        # `ShowHiddenMonster`. Es el Rat King, que llama a sus ratas. Ver
        # `BAF_OCULTO`.
        bytes_asm("tropa_ocultos", [
            sum(1 << k for k, oculto in enumerate(
                db.troops[n].ocultos[:constantes.ENEMIGOS_MAX]) if oculto)
            for n in usadas], "$%02X", declarar=True)
        bytes_asm("tropa_n",
                  [len(db.troops[n].members[:constantes.ENEMIGOS_MAX])
                   for n in usadas], declarar=True)
        bytes_asm("tropa_miembro", miembros, declarar=True)
        # Y las páginas de evento de cada tropa, en el orden del LDB —que es el
        # orden en que `ScheduleNextPage` las prueba—, sin las que no
        # compilaron: saltearlas no le cambia el orden a las demás. Por tropa,
        # dónde arrancan y cuántas son; por página, su disparador y dónde está
        # su código adentro de `tropa_codigo`, que las deduplica. Ver
        # `eventos.PaginasDeTropa` y `ba_pag_probar` en tools/runtime/batalla_tropa.s.
        #
        # **Las tablas chicas van al banco 1, `FAR`; los dos bloques grandes
        # —el código y los mensajes—, a RODATA.** Hasta el 2026-09-27 iban los
        # cuatro al banco 1, porque con ellos en RODATA el cartucho `juego` se
        # pasaba de los 4 MB (medido el 2026-09-21); ese cartucho ya no existe,
        # `release` anda por el 71%, y en el banco 1 los dos bloques eran casi
        # once KB de los que el código a mano de la pelea no tenía ni
        # cuatrocientos bytes. Los dos se leen con un puntero largo cuyo banco
        # sale de `^tropa_codigo` y `^mensajes_tropa`, así que alcanza con que
        # cada uno entre entero en un banco, que es lo que pide `bloque`.
        pt = paginas_tropa or eventos.PaginasDeTropa()
        entradas, pag_ini, pag_n = [], [], []
        for numero in usadas:
            suyas = pt.por_tropa.get(numero, [])
            pag_ini.append(len(entradas))
            pag_n.append(len(suyas))
            entradas += suyas
        if max(pag_n, default=0) > eventos.TROPA_PAGINAS_MAX:
            raise SystemExit("una tropa trae %d páginas y la pelea anota %d"
                             % (max(pag_n), eventos.TROPA_PAGINAS_MAX))
        handle.write('.segment "FAR"\n')
        words_asm("tropa_pag_ini", pag_ini)
        bytes_asm("tropa_pag_n", pag_n)
        bytes_asm("tpag_flags", [d.flags for d, _ofs in entradas], "$%02X")
        words_asm("tpag_sw_a", [d.switch_a for d, _ofs in entradas])
        words_asm("tpag_cod", [".loword(tropa_codigo + %d)" % ofs
                               for _d, ofs in entradas], "%s")
        # Las tres del `switch_b` y la variable sólo si alguna página las usa:
        # los 32 sistemas de los personajes miran sólo el `switch_a`, y sin
        # ninguna la ROM no las lee nunca —el bit de `tpag_flags` está en
        # cero—, así que alcanza con la etiqueta. Lo del turno y los HP no
        # tiene tabla: va delante del código, ver `eventos.cabecera_de_tropa`.
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
        # Y los encuentros al azar, que también hablan de tropas por su número
        # de RM2k. Van acá afuera del banco 0 —se leen con `lda f:tabla, x`—
        # porque allá quedaban ochenta y cinco bytes y esto son unos doscientos.
        # Ver `encuentros_de_la_rom` y `tools/runtime/encuentros.s`.
        enc = encuentros or {"por_mapa": [0xFF] * len(mapas), "registros": [],
                             "zonas": [], "tropas": []}
        bytes_asm("enc_mapa", enc["por_mapa"], declarar=True)
        words_asm("enc_base", [r["base"] for r in enc["registros"]],
                  declarar=True)
        umbrales = []
        for r in enc["registros"]:
            # Siete umbrales y uno de relleno: con ocho el índice del registro
            # es un corrimiento y no una multiplicación. Ver ENC_STRIDE.
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
        # El espíritu y los SP: los pide `CalcSkillEffect`, que le resta al
        # efecto `magical_rate * spi_del_blanco / 80`. Hasta el 2026-09-13 no
        # los leía nadie porque ninguna cuenta de la pelea los usaba.
        words_asm("enemigo_spi", [db.enemies[e].spirit for e in enemigos_rom],
                  declarar=True)
        words_asm("enemigo_sp", [db.enemies[e].max_sp for e in enemigos_rom],
                  declarar=True)
        bytes_asm("enemigo_hit", [db.enemies[e].hit for e in enemigos_rom],
                  declarar=True)
        # El crítico, ya en por ciento entero: `CalcCriticalHitChance` lo
        # calcula como `1 / critical_hit_chance` por cien y lo trunca.
        bytes_asm("enemigo_crit", [
            (100 // (db.enemies[e].critical_hit_chance or 30))
            if db.enemies[e].critical_hit else 0 for e in enemigos_rom],
            declarar=True)
        words_asm("enemigo_txt", [texto_enemigo[e] for e in enemigos_rom],
                  declarar=True)
        # La experiencia y el oro de cada uno, que la victoria le resta a los
        # de la tropa por cada enemigo que siguió oculto: ver `ba_sin_ocultos`.
        words_asm("enemigo_exp", [db.enemies[e].exp for e in enemigos_rom],
                  declarar=True)
        words_asm("enemigo_oro", [db.enemies[e].gold for e in enemigos_rom],
                  declarar=True)
        # Lo que deja al morir: el ítem del LDB, o 0 si no deja nada, y la
        # chance en por ciento. Ver `ba_vic_botin` y `batalla.tirar_el_botin`.
        # Todo ítem que se puede soltar está en `items`: ver
        # `items_del_botin`, que lo agrega.
        for e in enemigos_rom:
            if db.enemies[e].drop_id and db.enemies[e].drop_id not in k_de:
                raise SystemExit("el enemigo %d suelta el ítem %d y el "
                                 "cartucho no lo lleva"
                                 % (e, db.enemies[e].drop_id))
        words_asm("enemigo_botin", [db.enemies[e].drop_id
                                    for e in enemigos_rom], declarar=True)
        bytes_asm("enemigo_botin_pct", [db.enemies[e].drop_prob
                                        for e in enemigos_rom], declarar=True)
        # Lo que cada enemigo puede hacer en su turno: su lista de
        # `batalla.acciones_de_enemigo`, seguida en `eacc_*` —dónde arranca y
        # cuántas son—. Por acción, la habilidad como `k` de las tablas `hab_*`
        # o $FF para el ataque, y su `rating` con el bit 7 prendido si no es
        # `efectiva`: cuenta para el máximo y después pesa cero. Ver
        # `ba_accion_enemiga` en tools/runtime/batalla.s.
        eacc_ini, eacc_hab, eacc_peso = [], [], []
        for e in enemigos_rom:
            if len(acciones_rom[e]) > B.ACCIONES_MAX:
                raise SystemExit("el enemigo %d trae %d acciones y la ROM "
                                 "pesa %d: ver `batalla.ACCIONES_MAX`"
                                 % (e, len(acciones_rom[e]), B.ACCIONES_MAX))
            eacc_ini.append(len(eacc_hab))
            for rating, skill, efectiva in acciones_rom[e]:
                if not 0 < rating < 0x80:
                    raise SystemExit("el enemigo %d trae una acción de rating "
                                     "%d y la ROM lo lleva en siete bits"
                                     % (e, rating))
                eacc_hab.append(0xFF if skill is None
                                else lugar_hab[skill.id])
                eacc_peso.append(rating | (0 if efectiva else 0x80))
        if len(eacc_hab) > 255:
            raise SystemExit("las acciones de los enemigos del cartucho son %d "
                             "y `enemigo_acc_ini` es de un byte"
                             % len(eacc_hab))
        handle.write("ACCIONES_MAX = %d\n" % B.ACCIONES_MAX)
        bytes_asm("enemigo_acc_ini", eacc_ini, declarar=True)
        bytes_asm("enemigo_acc_n", [len(acciones_rom[e]) for e in enemigos_rom],
                  declarar=True)
        bytes_asm("eacc_hab", eacc_hab, declarar=True)
        bytes_asm("eacc_peso", eacc_peso, declarar=True)
        # Y la escena de la pelea: los fondos y los battlers por separado.
        # `usadas` es el mismo orden que `tropa_id`, que es lo que
        # `escena_tropa_fondo` indexa, y el de `tropa_miembro`.
        handle.write(escenas_asm(escenas or {"fondos": [], "battlers": [],
                                             "battler_de": {},
                                             "tropa_fondo": {},
                                             "mapa_fondo": [0xFF] * len(mapas)},
                                 usadas, db))
        handle.write('.segment "TABLAS"\n')
        # El producto de la cuenta del acierto tiene que entrar en dieciséis
        # bits: (100 - acierto) por la suma de las dos agilidades. Con el
        # acierto mínimo de 70 son 30 por 1998, y el tope de agilidad lo cuida
        # `BA_AGI_TOPE`; un enemigo que acertara menos lo desbordaría sin
        # avisar, así que se corta acá.
        # `recover_hp_rate * hp_max` tiene que entrar en dieciséis bits: la
        # ROM lo hace con el multiplicador del hardware, que da una palabra.
        # Con el por ciento topado en 100 eso son hp_max de hasta 655, y los
        # actores de este juego andan en 40. Un actor más gordo desbordaría sin
        # avisar, así que se corta acá.
        for a in range(actores_n):
            maximo = (reglas.parametro_de(db.actors[a], "maxhp")
                      if a in db.actors else 0)
            if maximo * 100 > 0xFFFF:
                raise SystemExit(
                    "el actor %d tiene %d HP y la cuenta de la curación de la "
                    "ROM está dimensionada para 655" % (a, maximo))
        for e in enemigos_rom:
            if db.enemies[e].hit < 70:
                raise SystemExit("el enemigo %d acierta %d, y la cuenta del "
                                 "acierto de la ROM está dimensionada para 70"
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
        # El audio: el tema de la pelea, el de la victoria y los cinco efectos,
        # con el índice que sacaron de `Temas`. $FF y $FFFF quieren decir "el
        # LDB lo tiene apagado", que es el caso de `battle_se` en este juego.
        # Quién suena en qué momento está en `eventos.AUDIO_BATALLA`, sacado de
        # easyrpg-player; acá sólo viajan los números.
        audio = audio_batalla or {}
        # El paquete de audio de la pelea va detrás de los de los mapas, así
        # que su índice es cuántos mapas lleva la ROM. Lo emite acá y lo
        # comprueba la sección de música, que es la que arma la lista.
        #
        # De dieciséis bits, y el "no hay" es $FFFF: con los 328 mapas del
        # juego entero el índice no entra en un byte, igual que `mapa_actual`.
        # Ver `batalla_audio_cargar`.
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
        # Los términos, por su lugar en `reglas.BA_TERMINOS`.
        for k, (nombre, _termino) in enumerate(reglas.BA_TERMINOS):
            handle.write("BA_TXT_%-11s= BA_TXT_BASE + %d\n"
                         % (nombre.upper(), k))
        handle.write("BA_TXT_REVIVIO    = %d\n" % texto_revivio)
        # Las cinco órdenes del menú, con lo que la ROM necesita de cada una:
        # en qué renglón y en qué columna va, qué término la nombra y si va
        # siempre en gris. Van en tablas y no en una cuenta porque desde el
        # 2026-09-13 **no son tres seguidas en un renglón**: son las cinco del
        # menú del ABL repartidas en dos. Ver `pantallas.BA_ORDENES`.
        handle.write("BA_ORDENES_N      = %d\n" % len(P.BA_ORDENES))
        handle.write("BA_ITEM_CUENTA_DX = %d\n" % (P.BA_ITEM_CUENTA_COL * 2))
        handle.write("BA_ORDEN_USAR     = %d\n" % P.BA_ORDEN_USAR)
        handle.write("BA_ORDEN_HUIR     = %d\n" % P.BA_ORDEN_HUIR)
        handle.write("BA_ORDEN_ATACAR   = %d\n" % P.BA_ORDEN_ATACAR)
        handle.write("BA_ORDEN_DEFENDER = %d\n" % P.BA_ORDEN_DEFENDER)
        handle.write("BA_ORDEN_HABILIDAD= %d\n" % P.BA_ORDEN_HABILIDAD)
        # La pantalla de habilidades: dos columnas con el nombre y el costo, y
        # la descripción de la que marca el cursor arriba de todo. La geometría
        # sale de `pantallas.py`, como la de la lista de ítems.
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
        # **De dos bytes.** Un índice de texto no entra en uno: con los 29
        # mapas de `abl` los de la batalla arrancan en el 273, y la
        # tabla de un byte que había acá hasta el 2026-09-14 los emitía igual
        # —`.byte 273`— para que el ensamblador los truncara sin decir nada.
        words_asm("ba_orden_txt", [
            texto_batalla + [n for n, _c in reglas.BA_TERMINOS].index(nombre)
            for nombre, _f, _c in P.BA_ORDENES], declarar=True)
        bytes_asm("ba_orden_gris", [
            1 if k in P.BA_ORDEN_SIN_HACER else 0
            for k in range(len(P.BA_ORDENES))], declarar=True)
        handle.write('.segment "TABLAS"\n')

        glifos = ranuras["items_glifos"]
        # Fuera del banco 0, como `item_k`: se lee con `lda f:`.
        handle.write('.segment "RODATA"\n')
        # **Con el bit de prioridad puesto**, desde que la pelea dibuja la
        # escena en BG1: en modo 3 el orden del PPU deja BG1 de prioridad 0
        # **arriba** de BG2 de prioridad 0, así que sin esto el fondo taparía
        # las letras. En las otras pantallas que usan estos glifos —ítems,
        # equipo, tienda— BG1 está apagado y el bit no cambia un pixel, y en
        # las celdas vacías tampoco, porque sus pixeles son transparentes.
        # La variante de "sube" trae sólo las cifras; las demás letras caen en
        # las blancas, que nadie pide en ese color pero así la tabla se indexa
        # igual que las otras.
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
        # `fuente_color` va en el banco 0 y no con el resto de la ventana: la
        # ROM la lee con `lda fuente_color, y`, y ese modo direcciona el banco
        # de datos. Con ella en RODATA leía basura, y el texto salía en negro.
        handle.write(bloque("fuente_color", bytes(ventana["color"]),
                            acomodar=False) + "\n")
        handle.write("grupo_inicial:\n    .byte %s\n\n"
                     % ",".join("%d" % a for a in grupo_inicial) or "0")
        handle.write(tabla_de_senos() + "\n")
        # Cuántos cuadros se queda quieto un personaje después de un paso y
        # después de un giro, por frecuencia de ruta: el contador de parada de
        # RM2k, en dos tablas de nueve para indexar con la frecuencia tal cual.
        # Salen de `eventos.espera_tras_paso` y `espera_tras_giro`. La 0 y la
        # 1 no se compilan; llevan cero para que la tabla no tenga agujeros.
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
        # Después de la de mapas, que ya dejó el segmento en RODATA.
        handle.write(anim_tabla(mapas))
        handle.write("\n")
    return materiales.informe()


def sprite_colors_bytes(sprite):
    """Las paletas de los sprites como bytes de CGRAM.

    Cada una son 16 entradas: el índice 0 es transparente y no se dibuja, pero
    igual ocupa su lugar, y las que sobran se rellenan para que la siguiente
    empiece donde el hardware la espera.
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


# Un evento en la tabla de posiciones: x e y en celdas, las dos de 16 bits
# porque hay mapas de 500 celdas de ancho.
EV_STRIDE = 4
# Cuántos eventos guarda la RAM. El mapa más poblado de este juego tiene 114
# —medido sobre los 328—; el conversor corta si alguno se pasa, así que el
# número no puede quedar corto en silencio. Cada uno cuesta seis bytes de RAM
# entre `ev_pos_buf` y `eleg_por_ev`.
EV_MAX = 120
# Cuántas rutas forzadas pueden estar corriendo a la vez sobre eventos. La
# página que más manda a caminar de este juego mueve cuatro eventos distintos, y
# una ruta sobrevive al final de su página, así que puede haber otra corriendo
# encima. Ocho da margen y cuesta 88 bytes de RAM.
RUTA_EV_MAX = 12
# Cuántos destellos pueden estar corriendo a la vez. Las páginas de este juego
# los encadenan de a uno —casi todos esperan a que termine— así que cuatro sobra;
# el conversor no lo puede comprobar porque depende de qué corra cuándo, y una
# ranura que falte hace que el destello no se vea.
FLASH_MAX = 4
# Cuántos eventos con página paralela puede haber a la vez en un mapa. Era 12
# porque el más cargado era el 8 —Lashe City— con ocho: los cuatro autos y los
# cuatro que los reubican.
#
# **Con `ChangeSpriteAssociation` hecho son 40**, y los pone un solo mapa: cada
# obstáculo de la persecución en auto es un evento con una página paralela que
# compara la celda del auto con la suya, y los mapas 49, 52 y 54 tienen
# cuarenta cada uno. Antes no contaban porque ninguna de esas páginas compilaba.
# Medido sobre los 328 mapas con todo lo que hay hecho hoy; el conversor corta
# si alguno se pasa.
#
# Lo que cuesta: ocho bytes de `FAR_PAR_LISTA` por ranura —RAM lejana, no la
# BSS; ver `PAR_LISTA_BYTES` en `tools/runtime/ram_lejana.s`, que además del evento guarda la página
# que el refresco le eligió— y **una vuelta de intérprete por cuadro por cada
# uno**. Es lo segundo lo que hay que mirar si la carrera se pone lenta: lo
# primero ya no está, porque la página dejó de resolverse en cada cuadro.
#
# 48 por ocho son 384 bytes, y de `FAR_PAR_LISTA` a `FAR_AZAR` hay 508.
PARALELO_MAX = 48
# Un NPC en la RAM de la ROM. Eran ocho bytes; los cuatro de más son para los
# que caminan: a cuál evento corresponden y dónde está su tabla de poses.
#
#   +0 x, +2 y   en pixeles
#   +4 clave     capa y Y, que es lo que compara `build_oam`
#   +6 tile, +7 atributos
#   +8 evento    su índice en la tabla de eventos, o $FF si no camina
#   +9 poses     su entrada en `npc_poses`, o $FF
#   +10 dir      hacia dónde mira su página, para la primera pose de una ruta
#   +11 relleno, para que la ranura se indexe con dos corrimientos
NPC_STRIDE = 16
NPC_QUIETO = 0xFF        # en +9: este NPC no camina

# La tabla de NPCs del mapa que está cargado se copia a RAM, porque build_oam la
# recorre con un índice y eso direcciona el banco de datos. El techo de arriba
# lo pone OAM: entran 128 objetos y uno es el héroe, así que ningún mapa puede
# **mostrar** más de 127.
#
# El número no es ése desde el 2026-09-06, y no por gusto: la fila mide
# dieciséis bytes, así que el tope se lleva dos kilos de los ocho que tiene el
# banco 0 de RAM, y la RAM se acabó —ver `PILA` en
# tools/ensamblado/bancos.py—. **El mapa con más filas de todo el juego tiene 99**,
# medido sobre los 328, así que 104 deja cinco de aire y devuelve 368 bytes. No
# puede quedar corto en silencio: el conversor corta si algún mapa se pasa.
NPC_MAX = 104


def orden_de_dibujo(npc):
    """Con qué se ordena un evento para dibujarlo, de adelante hacia atrás.

    RM2k ordena por **mayor Y, después mayor X, y después mayor id**. Sale de
    `Game_Character::GetScreenZ` en easyrpg-player, que arma un Z de 64 bits con
    la capa arriba, la Y, la X y el id abajo, con el comentario puesto:

        The rendering order of characters is: Highest Y, Highest X, Highest ID

    Los dos desempates faltaban. Con NPCs quietos casi no se
    nota —hay que tener dos en la misma fila y que alguno tape al otro— pero en
    cuanto uno camina cambia de fila todo el tiempo y empata con cualquiera.

    El índice de la tabla vale por el id: los eventos vienen ordenados por id,
    así que el orden es el mismo.
    """
    return (npc["layer"], npc["y"], npc["x"], npc["evento"])


def sort_key(layer, y):
    """Cómo ordena RM2k: primero la capa y recién después la Y.

    Un evento "below" queda debajo del héroe aunque esté más adelante en la
    pantalla, y uno "above" lo tapa siempre. Meter la capa en los bits altos
    hace que una sola comparación de 16 bits decida las dos cosas.
    """
    return (layer << 12) | (y & 0x0FFF)


# Cuánto ocupa cada opcode, para recorrer el bytecode sin ejecutarlo. Los que
# llevan largo variable van con None y se miden aparte.
# El recorrido del bytecode vive en eventos.py, con la tabla de largos: acá
# había una copia y la de allá se quedó vieja sin que nadie lo viera.
recorrer_codigo = eventos.recorrer_codigo


def orden_de_mapas(args):
    """Los mapas de la ROM, en el orden de la tabla y sin repetidos.

    Está en una función y no escrito tres veces porque **el orden es el
    contrato**: un teletransporte compilado guarda el índice en esta tabla, no
    el id de RM2k. Dos listas que se armen distinto llevarían el mismo bytecode
    a mapas distintos.
    """
    return [args.map_id] + [m for m in (args.mapas or []) if m != args.map_id]


# Cuántos eventos quietos con animación continua anima un mapa. Ver el porqué
# —y el número medido— adentro de `eventos_movibles`.
# Medido contra A Blurred Line: un supuesto del motor, no un dato del juego.
# Ver `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
ANIMA_QUIETO_MAX = 4


def eventos_movibles(game_map, indice_de_mapa, asociaciones=()):
    """Los eventos con gráfico a los que alguna página compilable manda a
    caminar, y los gráficos a los que alguna ruta cambia con la orden 34.

    Hace falta antes de armar el banco de sprites: a los que se mueven hay que
    darles **las doce poses** del ciclo de caminata, y a los demás la única que
    declaran. Dárselas a cualquiera que aparezca en un MoveEvent sería más
    simple y no entra: hay mapas con siete, y son 1232 tiles de sprite.

    Los gráficos de la orden 34 salen de la misma pasada y por lo mismo: a un
    evento que cambia de gráfico hay que meterle en el cartucho las doce poses
    del gráfico nuevo, y eso se decide antes de armar el banco. **El orden
    tiene que ser el mismo que el de la compilación de verdad**, porque el
    bytecode lleva el índice: lo garantiza que las dos pasadas compilen las
    mismas páginas, con el mismo bloque de textos. Sin `Graficos` acá una
    ruta con la 34 no compilaría en esta pasada y sí en la otra, y las dos
    listas se irían.

    Se compilan las páginas para saberlo y se tira lo compilado. Es trabajo
    repetido —main() las vuelve a compilar con el bloque de textos de verdad—
    pero no es una **regla** repetida: la decisión de qué compila la toma la
    misma función las dos veces.
    """
    graficos = eventos.Graficos(asociaciones)
    paginas = eventos.paginas_del_mapa(
        game_map, indice_de_mapa,
        eventos.Mensajes(), graficos=graficos)
    npcs = rm2k.collect_npcs(game_map)
    visibles = {npc["evento"] for npc in npcs}
    # Y los que caminan solos con la ruta propia de alguna página, que
    # necesitan las doce poses igual que los que manda a caminar un MoveEvent.
    propios = {p["evento"] for p in paginas if p.get("ruta_propia")}
    # Y los quietos con animación continua —el save point de Lashe City—, que
    # no caminan pero **cambian de columna igual**. Sin las doce poses su ranura
    # de VRAM llevaría una sola y no habría con qué animarlos: los quietos
    # comparten ranura por (CharSet, índice, pose) y no tienen una propia.
    con_ruta = (eventos.blancos_de_ruta(paginas) | propios) & visibles
    animados = {npc["evento"] for npc in npcs
                if npc.get("anima")} & visibles - con_ruta
    # Y el tope: un evento quieto que anima **cuesta una ranura entera de VRAM**
    # —doce tiles— porque deja de compartir la de su (CharSet, índice, pose) y
    # pasa a tener las doce poses suyas, como los que caminan. Un mapa con
    # treinta —el 52 tiene treinta— pide 572 tiles de sprite y entran 384.
    #
    # Así que un mapa con más de `ANIMA_QUIETO_MAX` no anima **ninguno**, y no
    # unos sí y otros no: dos fuentes iguales, una moviéndose y la otra
    # congelada, se ve peor que las dos quietas. Medido sobre los 328 mapas del
    # juego: 312 tienen cuatro o menos, y de los mapas que hoy llevan las ROMs
    # el único que se pasa es el 52.
    if len(animados) > ANIMA_QUIETO_MAX:
        animados = set()
    # Y los que se dan vuelta hacia el héroe cuando les habla: los eventos con
    # alguna página de acción o de contacto que compiló y gira —ver GIRO en
    # eventos.py—, con los gráficos de **todas** sus páginas que giran. Las
    # doce poses de cada uno van al cartucho, que es de donde la ROM saca la
    # que mira al héroe; el refresco compara los gráficos de las páginas para
    # saber si el giro sobrevive a un cambio de página.
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
    """Los (CharSet, índice) de `--grafico-de-prueba`, o () si no hay."""
    return tuple((charset, int(indice)) for charset, indice in argumento or ())


def firma_de_la_partida(pares, ranuras_exp, actores_n):
    """Dieciséis bits que cambian cuando cambia **qué significa** cada byte de
    la partida guardada, para que la ROM rechace una de otro build.

    El tamaño lo cuida la ROM sola —`PARTIDA_BYTES`, que sale de las mismas
    constantes—; esto cubre lo que el tamaño no ve: qué variable de RM2k va
    en cada ranura, de qué actor es cada par de habilidad y cada ranura de
    experiencia. Dos builds pueden llevar el mismo número de variables y que
    la ranura 5 sea otra variable en cada uno; ahí la partida cargaría con
    el mismo largo y todo corrido.

    Son las asignaciones y no la ROM entera a propósito: dos builds cuya
    partida se lee igual tienen que poder compartirla, aunque cambie todo
    lo demás.
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
    """Cuántas ranuras de variables lleva la ROM: al menos una —un largo cero
    cerraría la tabla de la partida— y hasta 256, que es lo que entra entre
    `FAR_VARIABLES` y `FAR_ITEMS`."""
    n = max(1, len(eventos.VARIABLE_SLOT))
    if n > 256:
        sys.exit("%d variables no entran en la RAM lejana: FAR_ITEMS está a "
                 "512 bytes de FAR_VARIABLES" % n)
    return n


def tabla_de_senos():
    """El seno que la sacudida de pantalla lee por índice, para el banco."""
    out = ["; El seno a escala 127, para la sacudida de pantalla: es la misma",
           "; lista que arma `SENO_SACUDIDA` en eventos.py.",
           ";",
           "; Va fuera del banco 0 —`lda f:seno_sacudida, x`, una lectura por",
           "; cuadro de sacudida— por lo mismo que `item_k`: son 256 bytes y",
           "; el banco del código se llenó.",
           '.segment "RODATA"',
           ".bloque 256",
           "seno_sacudida:"]
    valores = eventos.SENO_SACUDIDA
    for i in range(0, 256, 16):
        out.append("    .byte " + ",".join("$%02X" % (v & 0xFF)
                                            for v in valores[i:i + 16]))
    # Y se vuelve al banco 0: lo que sigue —`ruta_tras_paso` y compañía— se lee
    # con direccionamiento absoluto indexado y tiene que quedar acá.
    out.append('.segment "TABLAS"')
    return "\n".join(out) + "\n"


def ev_pos_bytes(game_map):
    """Dónde arranca cada evento del mapa, en celdas y en orden de índice.

    Va **todo** el mapa y no sólo los eventos con gráfico: una ruta forzada
    puede caer sobre uno invisible, y de hecho la mitad de las de este juego lo
    hacen. La ROM la copia a RAM al cargar el mapa porque una ruta la cambia, y
    la siguiente ruta sobre el mismo evento arranca de donde quedó: hay una
    página que manda a caminar nueve veces al mismo.

    El orden es el índice de la tabla, que es lo que lleva el bytecode. **No es
    el id de RM2k**: 39 mapas tienen huecos en la numeración, y traducir es
    justamente lo que hace `eventos.Eventos`.
    """
    if len(game_map.events) > EV_MAX:
        raise SystemExit("el mapa tiene %d eventos y la RAM de la ROM guarda %d"
                         % (len(game_map.events), EV_MAX))
    out = bytearray()
    for event in game_map.events:
        out += event.x.to_bytes(2, "little")
        out += event.y.to_bytes(2, "little")
    return bytes(out)


def npc_bytes(table):
    """La tabla de NPCs: NPC_STRIDE bytes por cada uno.

    Posición en el mapa, la clave con la que se ordena contra el héroe, qué tile
    de sprite le toca, y el byte de atributos ya armado con su paleta. La ROM
    sólo resta la cámara y lo copia a OAM.

    Los que caminan llevan además a qué evento corresponden y dónde está su
    tabla de doce poses, que es lo que le permite a la ROM cambiarles el tile
    mientras dan un paso.
    """
    out = bytearray()
    for npc in table:
        out += npc["x"].to_bytes(2, "little")
        out += npc["y"].to_bytes(2, "little")
        # La clave va con la Y en pixeles, que es como la calcula la ROM a
        # partir de la posición del héroe. Con la Y en celdas, la del héroe
        # sería siempre mayor y quedaría siempre adelante de todos.
        #
        # Y `npc["y"]` **ya está en pixeles**: lo pasa a pixeles `npc_table`.
        # Multiplicarlo otra vez por 16 —que es lo que hacía acá— daba una clave
        # dieciséis veces más grande que la del héroe, y como `sort_key` recorta
        # a doce bits, encima daba la vuelta. La comparación no lo veía porque
        # el orden **entre** NPCs lo fija el `sorted` del conversor y esta clave
        # sólo decide dónde entra el héroe: hacía falta que el héroe pisara a un
        # NPC para que se notara, y ninguna prueba lo hacía.
        out += sort_key(npc["layer"], npc["y"]).to_bytes(2, "little")
        out.append(npc["tile"] & 0xFF)
        # vhoopppN: la prioridad son los bits 5 y 4, así que el valor va corrido
        # cuatro lugares. Los eventos marcados "above" van en prioridad 2, que
        # es lo único que queda por encima de BG2 1; el resto comparten con el
        # héroe la prioridad 1, y como esa capa los tapa, caminan por debajo.
        prioridad = (OBJ_PRIORITY_ABOVE
                     if npc["layer"] == rm2k.LAYER_ABOVE
                     else OBJ_PRIORITY)
        out.append(prioridad | ((npc["palette"] & 0x07) << 1)
                   | ((npc["tile"] >> 8) & 0x01))
        # El índice del evento va **siempre**, aunque el NPC no camine: es el
        # último desempate del orden de dibujado, y vale para todos. Lo que
        # distingue a los que caminan es la tabla de poses.
        out.append(npc["evento"])
        out.append(NPC_QUIETO if npc["poses"] is None else npc["poses"])
        # Hacia dónde mira su página. Una ruta forzada que todavía no dio
        # ninguna orden de girar lo deja mirando para acá, que es de donde sale
        # la primera pose que se dibuja.
        out.append(npc["dir"])
        out.append(0)               # relleno
        # +12: la pose que hay en VRAM, que al cargar es la de su página. La
        # ROM la compara con la que quiere dibujar y sube la nueva si difiere.
        out.append(npc["pose"])
        # +13: la velocidad de su página, para una ruta forzada sobre él, y en
        # el bit 7 si es un quieto con animación continua. Van juntos porque la
        # fila no tiene un byte libre —el +11 lo usa el salto— y porque los dos
        # los lee la misma cuenta: cada cuántos cuadros cambia de columna sale
        # de la velocidad. Ver `animar_quietos` en tools/runtime/quietos_que_animan.s.
        out.append(npc["velocidad"] | (0x80 if npc.get("anima") else 0))
        # +14: si se dibuja. Un evento cuya página activa no tiene gráfico
        # está en la tabla escondido, para aparecer cuando otra página gane.
        out.append(1 if npc["visible"] else 0)
        # +15: los bits de paso que su tile le impone a la celda, o $FF: ver
        # `rm2k.pasabilidad_del_tile`. Los dos los rehace el refresco.
        out.append(0xFF if npc["tile_pasa"] is None else npc["tile_pasa"])
    assert len(out) == NPC_STRIDE * len(table)
    return bytes(out)


def puntero(destino):
    """Los tres bytes de un puntero simbólico, para `.byte`."""
    return "<(%s), >(%s), ^(%s)" % (destino, destino, destino)


def npc_poses_asm(numero, animados, indice_global):
    """Los punteros a las doce poses de cada personaje que cambia de pose.

    Una entrada por personaje animado —`k`, el mismo índice que lleva la fila
    del NPC en +9 y el actor en su tabla— y en cada una doce punteros de 24
    bits a sus poses, `pose_N`. Son simbólicos porque apuntan a bloques que
    ubica el enlazador, como los de las páginas; dos poses iguales son el
    mismo bloque.
    """
    out = [".bloque %d" % (3 * SPRITE_POSES * max(1, len(animados))),
           "npc_poses_%d:" % numero]
    for par in animados:
        for pose in range(SPRITE_POSES):
            out.append("    .byte " + puntero(indice_global[par][pose]))
    if not animados:
        out.append("    .byte $00")     # una etiqueta no puede quedar vacía
    return "\n".join(out)


def actor_table_asm(numero, actores, animados, indice_global):
    """Los candidatos a líder: id, paleta, y el puntero a cada una de sus poses.

    ACTOR_BYTES por actor. La ROM recorre la tabla buscando el id del primero
    del grupo; son dos o tres entradas, así que buscar linealmente sale más
    barato que indexar por id, que pediría 256 huecos. Un actor sin gráfico
    lleva doce punteros en $FFFFFF, que es el centinela que `place_hero` mira.
    """
    out = [".bloque %d" % (ACTOR_BYTES * max(1, len(actores))),
           "actor_table_%d:" % numero]
    for actor, paleta, k, colores in actores:
        out.append("    .byte $%02X, $%02X" % (actor & 0xFF, paleta & 0x07))
        # Sus quince colores, en el orden en que sus poses los indexan. Un actor
        # sin gráfico los lleva en cero y la ROM no los sube: no se dibuja.
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
    """Los flags del conversor. Aparte de `main` para quien necesite leer una
    línea de comandos sin convertir nada."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Obligatorio, pero sin `required`: `casos_de_prueba` vuelve a leer los
    # flags de cada `--caso` con este mismo parser, y ahí no va. Lo cobra
    # `main`.
    parser.add_argument("--map-id", type=int, default=None,
                        help="el mapa de arranque, que va primero en la "
                             "tabla. Obligatorio y sin valor por omisión: "
                             "es del juego, y lo declara su archivo de "
                             "proyecto")
    proyecto.argumento(parser)
    # Sin valor por omisión, y sin `required` por lo mismo que `--map-id`:
    # los cobra `ambiente` cuando se leen.
    ambiente.argumentos(parser, "game_dir", "rtp_dir", "soundfont", "cache")
    parser.add_argument("-o", "--output",
                        default=os.path.join(proyecto.build(), "inc", "mapdata.inc"))
    parser.add_argument("--msu",
                        help="dónde escribir el .msu con los datos que el\n"
                             "MSU-1 le sirve a la ROM: al lado del .sfc y con\n"
                             "su nombre, para que el emulador lo encuentre.\n"
                             "Sin esto, datos.msu al lado del --output")
    parser.add_argument("--relleno-de-textos", type=int, default=0,
                        help="textos muertos detrás de los de los ítems, para\n"
                             "que los índices de la batalla pasen de 255 sin\n"
                             "armar un cartucho de veintinueve mapas. No\n"
                             "cambia un pixel, y por eso no van delante de\n"
                             "todo: el nombre del ítem k es el texto 3k")
    parser.add_argument("--sin-titulo", action="store_true",
                        help="sin la pantalla de título del juego y su menú "
                             "de empezar y cargar: la ROM arranca directo en "
                             "el mapa. Es lo que piden los cartuchos de la "
                             "tanda de regresión: la pantalla de título le "
                             "agregaría cuadros al arranque, y los casos "
                             "comparan cuadros contados desde el reset.")
    parser.add_argument("--aire-de-medida", type=float, metavar="AIRE",
                        help="el mismo aire para todos los temas, en vez de "
                             "la tabla de techos: es con lo que "
                             "`tools/audio/techos.py` arma la ROM en que mide "
                             "el pico de cada tema. Ver `leer_techos` en "
                             "tools/audio/snes_music.py")
    parser.add_argument("--hp-de-enemigos", action="store_true",
                        help="la pelea muestra los HP de los enemigos, que "
                             "RM2k no muestra nunca: para depurar. Lo pide "
                             "`[debug] enemy_hp` del archivo de "
                             "proyecto")
    parser.add_argument("--sin-timer", action="store_true",
                        help="los dígitos del cronómetro —once glifos de la "
                             "imagen de System al final del banco de sprites, "
                             "que comparten paleta con un personaje— sólo en "
                             "los mapas donde corre un caso que los usa, y no "
                             "en todos. Es lo que piden los cartuchos de la "
                             "tanda: ver `args.timer_en`")
    parser.add_argument("--grafico-de-prueba", nargs=2, action="append",
                        default=None, metavar=("CHARSET", "INDICE"),
                        help="mete este gráfico en el banco de sprites\n"
                             "de los mapas donde corre algún caso, para que la\n"
                             "página de prueba pueda cambiarle el gráfico a\n"
                             "alguien con la orden 34 o con\n"
                             "ChangeSpriteAssociation. Se puede repetir.\n"
                             "Ninguna página que compile hoy cambia de\n"
                             "gráfico, así que sin esto el camino no lo\n"
                             "corre nada")
    parser.add_argument("--encuentros-de-prueba", type=int, default=None,
                        metavar="PASOS",
                        help="cada cuántos pasos hay un encuentro al azar, "
                             "para todos los mapas del cartucho. Sin esto vale "
                             "el del árbol del juego, que va de 25 a 85 pasos; "
                             "0 los apaga")
    parser.add_argument("--heroe-encima", action="store_true",
                        help="el héroe en prioridad 2 de objeto, por "
                             "encima de la capa que debería taparlo. "
                             "Es la única forma de ejercitarla: el "
                             "único evento above del juego no llega a "
                             "pisar la capa de encima")
    parser.add_argument("--grupo", nargs="+", type=int, default=None,
                        metavar="ACTOR",
                        help="el grupo con el que arranca, por ids de actor. El gráfico "
                             "del héroe es el del primero, que es como lo decide "
                             "RM2k. Por defecto, el de la base: este juego "
                             "arranca con el actor 10, DummyHero, cuyo sprite es "
                             "una celda vacía a propósito")
    parser.add_argument("--comandos-de-prueba", default=None,
                        metavar="ARCHIVO",
                        help="la página de prueba de este caso, como la lista "
                             "de comandos de una página de RM2k en el JSON de "
                             "Ditto —ver rom/pruebas/casos/—. La compila el mismo "
                             "camino que una página del juego, con el "
                             "contexto del mapa donde corre: el de su "
                             "Teleport si empieza con uno, y si no el de "
                             "arranque")
    parser.add_argument("--charset", default=None,
                        help="forzar el CharSet del héroe; por defecto sale "
                             "del primero del grupo, que es como lo decide RM2k")
    parser.add_argument("--charset-index", type=int, default=None,
                        help="cuál de los 8 personajes del CharSet")
    parser.add_argument("--mapas", nargs="+", type=int, metavar="ID",
                        help="otros mapas para meter en la misma ROM. El de "
                             "--map-id va primero en la tabla")
    parser.add_argument("--inicial", type=int, default=0, metavar="N",
                        help="en qué índice de la tabla arranca la ROM. Sirve "
                             "para probar un mapa que no sea el primero, que "
                             "es el único caso donde el desplazamiento del "
                             "registro no es cero")
    return parser


def main():
    proyecto.desde_la_linea_de_comandos()
    parser = parser_de_flags()
    argv, tramos = partir_en_casos(sys.argv[1:])
    args = parser.parse_args(argv)
    if args.map_id is None:
        parser.error("falta --map-id, el mapa de arranque")
    ambiente.desde_argumentos(args, "game_dir", "rtp_dir", "soundfont",
                              "cache")
    args.game_dir = ambiente.juego()
    args.casos = casos_de_prueba(parser, args, tramos)
    orden = orden_de_mapas(args)
    if not 0 <= args.inicial < len(orden):
        sys.exit("--inicial %d pero hay %d mapas" % (args.inicial, len(orden)))
    for caso in args.casos:
        caso.mapa = mapa_del_caso(caso, orden, args.inicial)
    de_archivo = comandos_de_casos(args)
    # Qué mapas llevan los dígitos del cronómetro, que cuestan una paleta de
    # sprite. Normalmente, todos: es lo que pide el juego, donde la cuenta
    # atrás arranca en un mapa y se ve en los que siguen. Con `--sin-timer`,
    # los mapas donde corre un caso que lo toca: hasta el paso 9e bastaba uno para
    # que los llevaran todos los del cartucho, y en el cartucho único del 9f
    # eso le sacaba la paleta a cada mapa —medido, quince goldens se movían—.
    # Un mapa sin dígitos no los dibuja: `TIMER_BASE` en cero, ver
    # `timer_oam`.
    args.timer_en = set(orden) if not args.sin_timer else {
        caso.mapa for caso in args.casos
        if any(cmd.code == eventos.TIMER_OPERATION for cmd in caso.comandos)}

    renderer = Renderer(args.game_dir)

    # El gráfico del héroe sale del grupo, no de acá. En RM2k lo da el primero
    # de la lista, y este juego arranca con el actor 10 —'DummyHero', que es
    # Chubby2[2]—. Hasta ahora había un default puesto a mano que daba
    # Future1[0], o sea el sprite de otro personaje.
    # --charset queda para forzarlo a mano cuando hace falta.
    grupo = args.grupo if args.grupo else renderer.database.party
    if args.charset is None:
        args.charset, indice = renderer.database.lider(grupo)
        if args.charset_index is None:
            args.charset_index = indice
    if args.charset_index is None:
        args.charset_index = 0

    # Los candidatos a líder se calculan con todos los mapas de la ROM juntos,
    # porque el grupo es estado global: una página del mapa A puede meter a
    # alguien que después camina por el mapa B.
    args_game_dir[0] = args.game_dir
    todos = orden_de_mapas(args)
    # **Los índices van antes que todo lo que compile una página**, y
    # `lideres_posibles` compila páginas. Estaban después, y el precio era
    # concreto: sin `indexar_variables`, ninguna `ControlVars` compila, así que
    # `RaceController1` del mapa 49 —que arranca con un `PlayBGM` y sigue con
    # dos `ControlVars`— no compilaba **en esa pasada** y sí en la de verdad.
    # Los actores que mete al grupo se perdían: `CarRED` no entraba en la tabla
    # de actores del mapa y el héroe de la persecución se dibujaba **sin
    # gráfico**, o sea que el auto no se veía. Es el mismo agujero que ya
    # estaba anotado para las cuentas de páginas, en otro lugar.
    #
    # Las variables del juego entero, con su ranura.
    extra = eventos.variables_de_comandos(de_archivo)
    if len(args.casos) > 1:
        # La que elige el caso: ver `eventos.VARIABLE_DE_CASO`. Con uno solo
        # no hace falta, y así ese cartucho sale igual que antes de `--caso`.
        extra.add(eventos.VARIABLE_DE_CASO)
    eventos.indexar_variables(args.game_dir, extra)
    # Y las animaciones de batalla, que `ShowBattleAnimation` compila con su
    # línea de tiempo adentro: ver OP_ANIMATION.
    eventos.indexar_animaciones(args.game_dir)
    # Y los eventos comunes, que `CallEvent` compila en el lugar.
    eventos.indexar_comunes(args.game_dir)
    eventos.indexar_audio_de_batalla(args.game_dir)
    # Y los términos de la posada, con los que `ShowInn` arma su saludo.
    eventos.indexar_terminos(args.game_dir)
    # Y el equipo y las habilidades de cada actor del LDB: es lo que contestan
    # las dos ramas de actor con dos operandos. **Antes de
    # `lideres_posibles`**, que compila páginas: ver
    # su comentario.
    eventos.indexar_actores(args.game_dir)
    # Y los pares (actor, habilidad) del juego entero, con los de las páginas
    # de prueba: es el operando de `ChangeSkills` y de la rama que pregunta si
    # sabe una, así que va antes de compilar nada, igual que las variables.
    eventos.indexar_habilidades(
        args.game_dir, eventos.pares_de_habilidad_de_comandos(de_archivo))
    args.lideres = lideres_posibles(renderer, todos, grupo)
    # Y los del grupo con que sigue cada página de prueba, detrás: la prueba
    # puede arrancar con él en cualquier mapa del cartucho.
    for caso in args.casos:
        de_prueba = grupo_de_la_pagina(caso, grupo)
        if de_prueba:
            for actor in lideres_posibles(renderer, todos, de_prueba):
                if actor not in args.lideres:
                    args.lideres.append(actor)
    # Si algún mapa pone lluvia, todos llevan las gotas: ver `hay_lluvia`.
    args.con_lluvia = hay_lluvia(todos, de_archivo)
    # En cuántos mapas de esta ROM aparece cada personaje. Lo usa el reparto de
    # paletas para elegir a quién puede bajarle un color sin romper nada: el
    # banco de poses es **de la ROM entera**, así que un personaje que está en
    # dos mapas tiene que quedar cuantizado igual en los dos. Cuantizarlo
    # distinto no da una imagen fea sino un `sys.exit` al emitir, que es lo que
    # pasó la primera vez que esto se escribió: `Future1:4` bajaba en un mapa y
    # no en el otro.
    args.mapas_por_personaje = mapas_por_personaje(renderer, todos,
                                                   args.game_dir)
    # El cartel del `ShowPicture`, uno por ROM: ver `eventos.Imagenes`. Se lo
    # queda el primer mapa de la tabla que lo muestre, que es el orden en que
    # `convertir` los recorre.
    args.imagenes = eventos.Imagenes(args.game_dir)
    args.imagenes.mapa = None
    # Y las ranuras que `ChangeSpriteAssociation` le reserva a la tabla de
    # gráficos de **todos** los mapas, por la misma razón que el cartel: el
    # gráfico que le pone a un actor cruza el teletransporte, así que su índice
    # tiene que valer lo mismo en los dos mapas. Ver `eventos.asociaciones_de`.
    #
    # Los de las páginas de prueba entran por la misma puerta: si fueran por
    # `--grafico-de-prueba` tendrían índice sólo en los mapas donde corre un
    # caso, y lo que el comando hace —cruzar el teletransporte— no se podría
    # probar.
    args.asociaciones = eventos.asociaciones_de(
        [lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % m))
         for m in todos], de_archivo)

    precalcular_capas(renderer, todos, args)
    mapas = [convertir(renderer, map_id, args) for map_id in todos]
    # Antes acá se reconvertían los mapas cuya capa de encima arrancaba más
    # arriba que la paleta de la ventana, para apretarles el fondo debajo de
    # ella. Con la ventana en la paleta 0 no hay nada que apretar: el fondo de
    # cada mapa arranca en `CGRAM_RESERVADAS` y llega hasta su propia capa de
    # encima, sin depender de lo que necesiten los otros mapas de la ROM.
    # Los teletransportes se resuelven cuando están todos los mapas: uno puede
    # llevar a cualquier otro, así que el índice de destino no se sabe hasta el
    # final.
    indices = {mapa["id"]: numero for numero, mapa in enumerate(mapas)}

    # Los bloques que las `TileSubstitution` del mapa van a necesitar, armados
    # **antes** de compilar ninguna página: ver `Sustituciones`. Un mapa sin
    # ese comando no arma nada y no crece un byte, que es el caso de los 328
    # mapas del juego al día de hoy.
    for mapa in mapas:
        chipset = renderer.database.chipsets[mapa["game_map"].chipset_id]
        mapa["sustituciones"] = Sustituciones(
            mapa, build_passability(chipset), chipset)
        # Le cuelga al mapa para que llegue a `eventos.Eventos`, que es lo que
        # el compilador ya se pasa de mano en mano.
        mapa["game_map"].sustituciones = mapa["sustituciones"]
        triples = triples_de_sustitucion(mapa["game_map"], args.casos,
                                         mapa["id"])
        for faltante in mapa["sustituciones"].cerrar(triples):
            # No corta la conversión: la página que lo pide no compila, que es
            # lo que hace cualquier comando que no se puede ejecutar. Pero se
            # dice, porque desde afuera se ve como un evento que no hace nada.
            #
            # Los dos motivos por los que una sustitución no se puede armar, y
            # los dos se arreglan del lado de la data: o el tile nuevo no está
            # dibujado en ninguna celda del mapa —y entonces sus 8x8 no
            # entraron en la VRAM—, o la combinación que haría falta lleva un
            # tile alto **sin el bit "Above"**, que no se dibuja en BG2 sino
            # horneado en el fondo, y ahí las dos capas del bloque dejan de ser
            # independientes. Ver `Sustituciones._hornea`.
            print("  mapa %d: TileSubstitution %d -> %d en la capa de %s: no "
                  "se puede armar el bloque que haría falta. O el tile nuevo "
                  "no está dibujado en ninguna celda del mapa, o alguno de los "
                  "dos es un tile alto sin 'Above' y se hornea en el fondo. La "
                  "página no compila."
                  % (mapa["id"], faltante[1], faltante[2],
                     "arriba" if faltante[0] else "abajo"))

    # El bloque de textos es de la ROM entera y se arma mientras se compilan las
    # páginas: cada `ShowMessage` deja su texto acá y se lleva un
    # desplazamiento, que es lo que va en el bytecode.
    mensajes = eventos.Mensajes(paso=eventos.MENSAJES_PASO)
    # Los temas que los PlayBGM de las páginas piden, numerados en el orden en
    # que aparecen. La ROM lleva uno solo —ver `Temas`— y lo elige más abajo,
    # cuando ya están todos compilados y se sabe cuáles se piden.
    temas = eventos.Temas()
    # Y las tropas que los EnemyEncounter piden. No numera nada —el bytecode
    # lleva el id de RM2k— así que sólo dice qué tablas de enemigos hay que
    # emitir. Ver `eventos.Tropas`.
    tropas = eventos.Tropas()
    # Los textos de las páginas de prueba van **primero**, antes de todos los
    # mapas, y eso no es estético: así su desplazamiento no depende de cuántos
    # textos traiga el mapa donde arranca la ROM ni de en qué orden se
    # compilen —el primero es el 0—. Se guardan acá y la compilación de la
    # página, más abajo, los encuentra guardados, porque el bloque deduplica
    # por contenido.
    for cmd, extra_lineas in eventos.agrupar(de_archivo):
        if cmd.code == eventos.SHOW_MESSAGE:
            mensajes.agregar([cmd.string] + extra_lineas)
    # Las páginas de prueba ya compiladas, por caso: ver la segunda vuelta.
    de_prueba = {}

    for mapa in mapas:
        # Los eventos automáticos: sus páginas con las condiciones, y el código
        # de las que se pueden ejecutar, todo seguido en un solo bloque.
        # Un registro de gráficos por mapa: la orden 34 lleva el índice y la
        # tabla `ruta_grafico` del mapa lo resuelve. Ver `eventos.Graficos`.
        graficos = eventos.Graficos(args.asociaciones)
        temas.mapa = mapas.index(mapa)      # para su paquete de audio
        paginas = eventos.paginas_del_mapa(mapa["game_map"], indices.get,
                                           mensajes, temas, graficos,
                                           args.imagenes, tropas)
        temas.mapa = None
        # Un intérprete por evento con alguna página paralela que compile. La
        # ROM los lleva en una lista de tope fijo y **no avisa** si se le pasa
        # —los que sobran no correrían y nada lo diría—, así que el corte va acá.
        con_paralela = {p["evento"] for p in paginas
                        if p["trigger"] == eventos.TRIGGER_PARALELO
                        and p["codigo"]}
        if len(con_paralela) > PARALELO_MAX:
            sys.exit("el mapa %d tiene %d eventos con página paralela y entran "
                     "%d: ver PARALELO_MAX"
                     % (mapa["id"], len(con_paralela), PARALELO_MAX))
        if con_paralela:
            print("  mapa %d: %d evento(s) con página paralela"
                  % (mapa["id"], len(con_paralela)))
        if args.grafico_de_prueba and mapa["id"] in mapas_de_prueba(args):
            for charset, index in graficos_de_prueba(args.grafico_de_prueba):
                graficos.indice(charset, index)
        # **Sólo el mapa que se llevó sus tiles puede mostrar el cartel.** El
        # banco de sprites es de cada mapa, así que desde otro los seis objetos
        # leerían lo que hubiera en esos tiles. No pasa hoy —el cartel del "1
        # year earlier" lo muestra una sola página— y por eso esto corta en vez
        # de elegir: el día que dos mapas muestren el mismo, hay que decidir si
        # sus tiles van en los dos, y esa decisión no la puede tomar el
        # conversor solo.
        if (args.imagenes.nombre is not None
                and mapa["id"] != args.imagenes.mapa):
            for pagina in paginas:
                codigo = pagina["codigo"]
                if codigo and any(codigo[i] == eventos.OP_PICTURE
                                  for i, _c in eventos.recorrer_codigo(codigo)):
                    sys.exit(
                        "mapa %d: muestra el cartel %r y sus tiles quedaron en "
                        "el mapa %d; la ROM lo lleva en uno solo. Ver "
                        "`cartel_de_imagen`."
                        % (mapa["id"], args.imagenes.nombre,
                           args.imagenes.mapa))
        if graficos.pares != mapa["graficos_de_ruta"]:
            # Las dos pasadas compilaron cosas distintas. No puede pasar —las
            # dos usan `paginas_del_mapa` con el mismo bloque de textos— y si
            # pasara, el bytecode quedaría apuntando a la tabla equivocada sin
            # que nada lo diga.
            sys.exit("mapa %d: las dos pasadas numeraron distinto los gráficos "
                     "de ruta: %s contra %s"
                     % (mapa["id"], graficos.pares, mapa["graficos_de_ruta"]))
        # Las páginas de los casos que corren en este mapa, compiladas con su
        # contexto aunque vayan a vivir en el mapa de arranque: ver
        # `mapa_del_caso`. Se ponen allá en la segunda vuelta, cuando ya
        # están todas.
        for k, caso in enumerate(args.casos):
            if caso.mapa == mapa["id"]:
                de_prueba[k] = pagina_de_caso(caso, mapa, temas, graficos,
                                              mensajes, indices,
                                              args.imagenes)
        mapa["paginas"] = paginas
        # Y a qué mapas de afuera de la ROM apuntan las que no compilan.
        #
        # Un `Teleport` a un mapa que no entró corta la página entera, y una
        # página que no compila no hace **nada**: ni el teletransporte ni lo que
        # venía antes. `evento` lo dice en su comentario desde siempre,
        # pero el conteo de arriba no distingue esta razón de las otras por las
        # que una página se cae, y es la única que se arregla desde afuera
        # —sumando el mapa— y no tocando el compilador. Así se pasó por alto la
        # página del ascensor del mapa 2, que se veía abrirse y no llevaba a
        # ningún lado porque termina saltando al mapa 3.
        afuera_de, cuantas = set(), 0
        for pagina in paginas:
            if pagina["codigo"] or pagina["trigger"] not in eventos.TRIGGERS \
                    or pagina.get("prueba"):
                continue        # la página de prueba no sale del juego
            evento = mapa["game_map"].events[pagina["evento"]]
            faltan = {cmd.parameters[0]
                      for cmd in evento.pages[pagina["pagina"]].commands
                      if cmd.code == eventos.TELEPORT and cmd.parameters
                      and indices.get(cmd.parameters[0]) is None}
            if faltan:
                afuera_de |= faltan
                cuantas += 1
        if afuera_de:
            print("  mapa %d: %d de ésas no %s por un teletransporte a un mapa "
                  "que no entró en la ROM: %s"
                  % (mapa["id"], cuantas,
                     "compila" if cuantas == 1 else "compilan",
                     ", ".join(str(m) for m in sorted(afuera_de))))
        # Las deudas se avisan. Una página que se acepta sin hacer todo lo que
        # pide es una diferencia con el juego original, y callarla es cómo se
        # vuelve invisible: acá se nombra el comando y qué se pierde.
        deudas = set()
        for evento in mapa["game_map"].events:
            for page in evento.pages:
                if page.trigger != eventos.TRIGGER_AUTOMATICO:
                    continue
                # Con el mismo bloque de textos que arriba: si acá fuera
                # None, una página con un cuadro de texto no compilaría y su
                # deuda —un PlayBGM, digamos— quedaría sin avisar aunque la ROM
                # sí la corra. Volver a agregar un texto que ya está no crece
                # el bloque: la clave es el contenido.
                if eventos.compilar_pagina(page, indices.get,
                                           mensajes) is None:
                    continue
                deudas |= set(eventos.deudas_de_la_pagina(page,
                                                          args.imagenes))
        for codigo_cmd in sorted(deudas):
            print("  mapa %d: AVISO, una página usa %s y la ROM no lo hace; "
                  "ver ACEPTADOS_SIN_HACER en tools/port/eventos.py"
                  % (mapa["id"], event_codes.EVENT_CODES.get(codigo_cmd,
                                                             codigo_cmd)))


    # La segunda vuelta: con las páginas de todos los casos compiladas, se
    # ponen en el mapa de arranque y se arma el bloque de cada mapa.
    for mapa in mapas:
        paginas = mapa["paginas"]
        if args.casos and mapa is mapas[args.inicial]:
            # Las páginas de prueba, sólo en el mapa donde arranca la ROM. No
            # salen del juego sino de `rom/pruebas/casos/`: existen porque hay
            # caminos del intérprete que ninguna página del juego que compile
            # ejercita —la primera fue una espera—.
            #
            # Va en el **índice 0**, el del evento vacío que `convertir` puso
            # al principio del mapa: la ROM recorre los eventos de menor a
            # mayor, y esta página tiene que correr antes que las del juego.
            # Hasta el 2026-09-17 iba en el primer índice libre, al final.
            #
            # **Una página por caso**, y la k pide que `VARIABLE_DE_CASO`
            # valga al menos k: ver su comentario. La 0 no pide nada, así que
            # un cartucho de un solo caso es el de siempre.
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
                # Y la que la apaga: pide `SWITCH_DE_PRUEBA` y no tiene
                # código, así que en cuanto
                # gana, el evento inventado deja de tener una automática que
                # correr y la primera no se repite.
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
            # Y las órdenes de la ruta propia, detrás, un byte por orden.
            propia = pagina.get("ruta_propia")
            if propia:
                pagina["ruta_offset"] = len(codigo)
                codigo += bytes(propia["ordenes"])
        mapa["paginas"] = paginas
        # Lo que dibuja cada página de los eventos que cambian de gráfico, ya
        # como lo quiere OAM: es lo que la ROM copia a la fila del NPC cuando
        # la página activa cambia. Ver `tabla_de_paginas`, +20.
        for pagina in paginas:
            sigue = pagina["evento"] in mapa["cambian"]
            if not sigue and pagina["evento"] not in mapa["aparecen"]:
                continue
            grafico = pagina.get("grafico")
            if grafico is None \
                    or grafico[:2] in mapa["afuera"].get(pagina["evento"], ()):
                continue
            if not sigue:
                # El que sólo aparece no lleva tile ni atributos: los suyos
                # apuntan a su ranura de doce poses y la ROM no los toca. Va
                # la pose —con el bit 7, que es "esta página dibuja algo"— y
                # lo que su tile le impone a la celda.
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
        # La tabla de sustituciones de la ROM es de tope fijo y **no avisa** si
        # se le pasa: los pares que no entren no se aplicarían y el mapa
        # dibujaría de más. Cuántas entradas puede llegar a tener se sabe acá,
        # y es la cantidad de bloques distintos que alguna sustitución del mapa
        # usa como clave, porque una clave nunca se pisa: la segunda vuelta
        # cambia su valor. Ver `op_tile_sub` en tools/runtime/interprete_mapa.s.
        claves = len(mapa["sustituciones"].claves)
        if claves > SUB_MAX:
            sys.exit("el mapa %d sustituye %d bloques distintos y la tabla de "
                     "la RAM lleva %d: ver SUB_MAX"
                     % (mapa["id"], claves, SUB_MAX))
        # Cuántos eventos distintos puede llegar a mandar a caminar este mapa.
        # La ROM tiene RUTA_EV_MAX ranuras y una ruta que no encuentre lugar se
        # descarta **sin decir nada**: el NPC se queda quieto y, si la golden
        # se saca así, la prueba defiende el error. Con los
        # datos de este juego el peor mapa usa dos, así que el control no molesta
        # a nadie; está para que un cambio futuro no las tire en silencio.
        #
        # Las páginas que **corren** acá: las del mapa y las de los casos que
        # saltan a él, que viven en el de arranque. Ver `mapa_del_caso`.
        corren_aca = [p["codigo"] for p in paginas
                      if p["codigo"] and not p.get("prueba")]
        corren_aca += [de_prueba[k] for k, caso in enumerate(args.casos)
                       if caso.mapa == mapa["id"]]
        blancos = {c[i + 1] for codigo in corren_aca
                   for i, c in recorrer_codigo(codigo)
                   if c[i] == eventos.OP_ROUTE and c[i + 1]}
        # Y que nadie destelle a alguien que comparte gráfico con otro. En la
        # consola el destello se hace sobre la paleta del personaje, así que dos
        # que compartan gráfico destellarían juntos. `eventos.py` ya rechaza el
        # caso de dos eventos; acá se cubre el que allá no se puede ver, que es
        # el del héroe: qué gráfico tiene depende del grupo, y eso lo sabe el
        # conversor y no el compilador.
        #
        # `separar_del_heroe` ya evita esto en los mapas cuyas páginas destellan
        # al héroe. Esto queda para lo que aquél no ve: un `FlashSprite` que
        # llega adentro de un evento común, que se compila en el lugar desde
        # cualquier `CallEvent` y no está en las páginas del mapa.
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
                            "mapa %d: una página hace destellar al héroe, y el "
                            "actor %d se dibuja con %s[%d], que también usa un "
                            "NPC del mapa. En la consola comparten paleta y "
                            "destellarían los dos"
                            % (mapa["id"], actor, a.charset, a.charset_index))

        if len(blancos) > RUTA_EV_MAX:
            raise SystemExit(
                "mapa %d: sus páginas mandan a caminar %d eventos distintos y "
                "la ROM tiene %d ranuras de ruta"
                % (mapa["id"], len(blancos), RUTA_EV_MAX))
        corribles = sum(1 for p in paginas if p["codigo"])
        if paginas:
            print("  mapa %d: %d página(s) de evento automático, %d ejecutable(s)"
                  % (mapa["id"], len(paginas), corribles))

    if not 0 <= args.inicial < len(mapas):
        sys.exit("--inicial %d pero hay %d mapas" % (args.inicial, len(mapas)))
    from port import ventana as ventana_mod
    skin = ventana_mod.skin(args.game_dir, renderer.database.system_name)
    font_id = renderer.database.font_id
    ventana_datos = convert_ventana(skin, font_id)
    ventana_datos["fuente"] = fuente_bytes(font_id)
    ventana_datos["mensajes"] = mensajes.bytes()
    print("  ventana de mensaje: %d tiles fijos + %d de texto, %d colores; "
          "fuente %d B, %d cuadro(s) de texto en %d B"
          % (len(ventana_datos["tiles"]) // 32,
             len(ventana_datos["fondo"]) // 32,
             sum(1 for w in ventana_datos["cram"] if w),
             len(ventana_datos["fuente"]), len(mensajes.textos),
             len(ventana_datos["mensajes"])))
    # La pantalla de ranuras va en toda ROM: la abre el save point desde
    # adentro del juego, y "Resume the Story" desde el título cuando lo hay.
    # Se dibuja con la misma fuente y la misma skin que la ventana de mensaje,
    # y vive en la VRAM del título, donde no hay mapa.
    # Los actores que pueden estar en el grupo cuando se guarda, para tener
    # su cara y su nombre en el cartucho: los de arranque y todos los que
    # agrega algún `ChangePartyMembers` de estos mapas, compilen sus páginas o
    # no. Es un superconjunto a propósito: una cara de más cuesta 36 tiles y
    # una de menos deja un hueco en el menú.
    miembros = miembros_posibles(todos, grupo, de_archivo)
    # Y los ítems que pueden estar en el inventario, para llevar su nombre y
    # su descripción: ver "la pantalla de ítems" en menus.py.
    items_rom = items_posibles(todos, miembros, renderer.database,
                               de_archivo)
    # Con las letras de las medicinas, que la elección de actor escribe con
    # los glifos del banco: ver `OBJETIVO_VENTANAS`.
    letras_medicinas = "".join(
        renderer.database.items[n].name for n in items_rom
        if renderer.database.items[n].type == lcf.ITEM_TIPO_MEDICINA)
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
    # Las ventanas de ítems y de equipo comparten tiles y colores: ver
    # `menus.marcos`.
    items_marco = menus_mod.marcos(
        skin, items_marco_primero(len(items_tiles)),
        [menus_mod.capas_items(skin), pantallas_mod.capas_equipo(skin)])
    _controlar_marco_de_items(len(items_tiles), len(items_marco[0]))
    # Las de la tienda, con sus propios tiles y colores: ver
    # `pantallas.TI_VENTANAS`.
    tienda_marco = menus_mod.marcos(
        skin, 0, pantallas_mod.capas_tienda(skin),
        menus_mod.ITEM_MARCO_CGRAM, menus_mod.OBJETIVO_CGRAM)
    _controlar_tienda(len(tienda_marco[0]))
    # Los tiles de la pantalla de End Game van donde los de las ranuras, así
    # que lo que se controla es lo mismo.
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
    print("  pantalla de ranuras: %d, %d tiles de 4bpp (%d B) + %d paletas, "
          "%d B de celdas; %d actores con cara: %s"
          % (RANURAS, len(ranura_tiles), len(ranura_tiles) * 32,
             len(ranura_paletas),
             (len(ranura_cabs) * len(ranura_cabs[0])
              + RANURAS * 4 * len(ranura_filas[0][0][0])) * 2,
             len(ranura_caras),
             ", ".join("%d %s" % (a, renderer.database.actors[a].name)
                       for a in sorted(ranura_caras)) or "ninguno"))
    titulo_datos = None
    if not args.sin_titulo:
        from PIL import Image
        nombre = renderer.database.title_name
        imagen = Image.open(os.path.join(args.game_dir, "Title",
                                         nombre + ".png"))
        textos = titulo_mod.opciones(renderer.database)
        menu_tiles, menu_paleta, menu_mapas = titulo_mod.menu(
            skin, textos, renderer.database.font_id)
        # La imagen, comprimida como la de Game Over, y con los colores del
        # menú debajo de los suyos en el mismo flujo: CGRAM entera de una vez,
        # la paleta del menú abajo porque un BG de 4 bits sólo alcanza ésas.
        # Los índices de los tiles ya vienen corridos desde
        # `paleta.convertir`.
        debajo = list(menu_paleta)
        debajo += [(0, 0, 0)] * (constantes.MENU_CGRAM - len(debajo))
        pantalla = pantalla_completa.comprimida(
            imagen, constantes.MENU_CGRAM, constantes.COLORES, debajo)
        titulo_datos = {"pantalla": pantalla,
                        "menu_tiles": menu_tiles, "menu_paleta": menu_paleta,
                        "menu_tilemaps": menu_mapas}
        print("  pantalla de título %r: %d tiles de 8bpp + %d colores, "
              "%d B en un flujo LZ2 de %d B"
              % (nombre, pantalla["tiles"],
                 pantalla["colores"] - len(debajo), pantalla["crudo"],
                 len(pantalla["flujo"])))
        print("    menú (%s): %d tiles de 4bpp (%d B) + %d colores, %d tilemap(s)"
              % (", ".join(repr(t) for t in textos), len(menu_tiles),
                 len(menu_tiles) * 32, len(menu_paleta), len(menu_mapas)))
    # La pantalla de Game Over: la imagen que nombra el `System` del LDB, en
    # `GameOver/` del juego o del RTP —como la busca RM2k—, comprimida. Va en
    # toda ROM que la encuentre: cualquier cartucho puede perder una pelea o
    # correr un `GameOver`. Ver tools/port/pantalla_completa.py.
    game_over_datos = None
    ruta = find_resource([args.game_dir, recursos.RTP_DIR], "GameOver",
                         renderer.database.gameover_name)
    if renderer.database.gameover_name and ruta:
        from PIL import Image
        game_over_datos = pantalla_completa.comprimida(Image.open(ruta))
        print("  pantalla de Game Over %r: %d tiles de 8bpp + %d colores, "
              "%d B en un flujo LZ2 de %d B"
              % (os.path.basename(ruta), game_over_datos["tiles"],
                 game_over_datos["colores"], game_over_datos["crudo"],
                 len(game_over_datos["flujo"])))
    # Las animaciones de batalla que el bytecode ya emitido muestra: sus
    # cuadros prerenderizados van al cartucho y la ROM los sube por DMA.
    animaciones = animaciones_de_la_rom(mapas, renderer)
    for numero in sorted(animaciones):
        datos = animacion_mod.informe(numero, animaciones[numero])
        print("  animación %d: %d cuadros de %dx%d, achicada de %dx%d al %d%%,"
              " %d colores, %d B"
              % (datos["animacion"], datos["cuadros"], datos["caja"][0],
                 datos["caja"][1], datos["original"][0], datos["original"][1],
                 datos["porciento"], datos["colores"], datos["bytes"]))
    # Los encuentros al azar de cada mapa, que piden sus tropas. Van **antes**
    # que las de las páginas de prueba, que van al final: así las tropas del
    # cartucho se numeran por los mapas y la inventada va última, que es lo
    # mismo que hace `temas_de_la_rom` con el tema del mapa. Pedirla antes le
    # daba siempre el índice 0, y con eso ningún caso de la tanda ejercitaba
    # que `escena_tropa_fondo` y `tropa_id` se indexen de verdad. Por eso
    # `pagina_de_caso` compila sin `Tropas`.
    encuentros = encuentros_de_la_rom(mapas, renderer.tree,
                                      args.encuentros_de_prueba, tropas)
    cuantas = sum(z["tropa_n"] for z in encuentros["zonas"])
    if encuentros["registros"]:
        print("  encuentros al azar: %d mapa(s), %d zona(s), %d tropa(s)"
              % (len(encuentros["registros"]), len(encuentros["zonas"]),
                 cuantas))
    for cmd in de_archivo:
        if cmd.code == eventos.ENEMY_ENCOUNTER:
            tropas.pedir(eventos.tropa_de_encuentro(cmd),
                         eventos.fondo_de_encuentro(cmd))
    # El audio de la pelea, con los índices que ya sacó de `temas` mientras las
    # páginas compilaban. Se vuelve a pedir sólo para leerlos: `Temas` numera
    # una vez y devuelve lo mismo, y lo anotado va al paquete de la pelea y no
    # al de ningún mapa.
    audio_batalla = eventos.audio_de_batalla(temas) if tropas.ids else None
    # Los fondos y los battlers que las peleas del cartucho piden, cada uno
    # una vez: la ROM los compone al empezar cada pelea. Ver
    # tools/port/escena.py, que es donde está el porqué y el presupuesto.
    escenas = escena_de_la_rom(renderer.database, tropas, mapas, renderer.tree,
                               encuentros, args.game_dir)
    # El `.msu` se escribe después del audio, porque lleva también los efectos
    # de sonido de calidad: ver `msu_asm`.
    for info in escenas["fondos"]:
        rom_tiles, rom_colores = respaldo_bytes(info)
        msu_tiles, msu_colores = escenas["calidad"][info["numero"]]
        print("  fondo de batalla %d %r: %dx%d, %d tiles desde la entrada %d "
              "de la CGRAM; en la ROM %dx%d en 4bpp y %d colores (%d B), en "
              "el .msu 8bpp y %d colores (%d B)"
              % (info["numero"], info["nombre"], escena_mod.ANCHO,
                 escena_mod.ALTO, escena_mod.TILES, escena_mod.CGRAM_BASE,
                 escena_mod.RESPALDO_ANCHO, escena_mod.RESPALDO_ALTO,
                 len(info["respaldo"]["paleta"]),
                 len(rom_tiles) + len(rom_colores), escena_mod.COLORES,
                 len(msu_tiles) + len(msu_colores)))
    # Y los que no están en la ROM, con cuál se reemplazan sin MSU-1.
    en_rom = {info["numero"] for info in escenas["fondos"]}
    fuera = [k for k in range(len(escenas["juego"])) if k not in en_rom]
    if fuera and escenas["fondos"]:
        print("  fondos de batalla sólo en el .msu, que sin MSU-1 van sobre "
              "%r: %s" % (escenas["fondos"][escenas["respaldo_de"][fuera[0]]]
                          ["nombre"], ", ".join(
                              "%d %s" % (k, escenas["juego"][k])
                              for k in fuera)))
    for info in escenas["battlers"]:
        d = escena_mod.informe_battler(info)
        print("  battler %r: %dx%d, %d B, %d colores de %d"
              % (d["clave"], d["ancho"], d["alto"], d["bytes"], d["quedan"],
                 d["colores"]))
    # Las páginas de evento de las tropas que alguna pelea del cartucho pide,
    # con **todas** las tropas ya pedidas: las de los mapas, las de los
    # encuentros al azar y las de las páginas de prueba. Ver
    # `eventos.PaginasDeTropa`, que es también por qué sus mensajes van a un
    # bloque aparte. Con `temas`, porque un `PlaySound` de página suena en el
    # paquete de la pelea, que todavía no se armó: se arma más abajo.
    paginas_tropa = eventos.PaginasDeTropa()
    for numero in tropas.ids:
        if numero in renderer.database.troops:
            paginas_tropa.compilar(numero, renderer.database.troops[numero],
                                   temas)
    print("  páginas de tropa: %d de %d en %d cuerpo(s) distinto(s), %d B de "
          "código y %d B en %d mensaje(s)"
          % (paginas_tropa.paginas - paginas_tropa.afuera,
             paginas_tropa.paginas, len(paginas_tropa.donde),
             len(paginas_tropa.cuerpos), len(paginas_tropa.mensajes.datos),
             len(paginas_tropa.mensajes.textos)))
    # Los ítems que sueltan los enemigos de esas tropas también pueden llegar
    # al inventario: ver `items_del_botin`.
    ranuras_datos["items"] = sorted(
        set(items_rom) | items_del_botin(renderer.database, tropas.ids))
    comprimidos = comprimir_los_bloques(mapas)
    informe = emit(args.output, mapas, args.inicial, args.heroe_encima, grupo,
                   ventana_datos, titulo_datos, ranuras_datos,
                   args.imagenes.info, animaciones, tropas.ids, audio_batalla,
                   escenas, encuentros, paginas_tropa, comprimidos,
                   hp_de_enemigos=args.hp_de_enemigos,
                   game_over=game_over_datos)
    # Qué entradas de su paleta usan los dígitos del cronómetro, un bit por
    # entrada y una palabra por mapa, en el orden de `mapa_tabla`.
    # `subir_timer_pal` vuelve a subir sin teñir **ésas** y no la paleta
    # entera, porque la paleta es de un personaje que sí se tiñe. Va aparte y
    # no como campo del registro porque el registro está en sus 128 justos.
    # El índice es el mismo `index + 1` con el que `digitos_del_timer` pintó
    # los glifos: el primero que tiene ese color.
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
        # Dónde escribe el arnés el número de caso: ver `--caso`.
        with open(args.output, "a") as handle:
            handle.write("\nCASO_RANURA = %d\n" % eventos.ranura_de_variable(
                eventos.VARIABLE_DE_CASO))
    print("%d mapa(s) -> %s, arranca en el %d (mapa %d)"
          % (len(mapas), args.output, args.inicial, mapas[args.inicial]["id"]))
    # Lo que decidió el asignador, como imágenes: para mirar qué colores se
    # perdieron y en qué paleta quedó cada celda sin armar ni correr la ROM.
    # Son indexadas y sus índices son entradas de CGRAM, así que un editor en
    # modo indexado las abre tal como las va a ver `tiles`.
    asignador = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                             "asignador")
    os.makedirs(asignador, exist_ok=True)
    for mapa in mapas:
        imagenes = list(mapa["imagenes_fondo"]) + [("encima", mapa["above"][5])]
        for nombre, png in imagenes:
            with open(os.path.join(asignador, "%04d-%s.png"
                                   % (mapa["id"], nombre)), "wb") as handle:
                handle.write(png)
    # Y **lo que decidió perder**, escrito: qué color se fusionó con cuál en
    # cada capa. Va al lado de las imágenes porque sale de la misma decisión,
    # pero es otra cosa: las imágenes son para mirar y esto es para leer de
    # vuelta y para que el diff avise. Lo versionado está en `rom/parches/`, y
    # `just parches --check` compara. Ver tools/port/parches.py.
    destino_parches = os.path.dirname(os.path.abspath(args.output))
    cuantos, pesan = parches_mod.escribir(destino_parches, mapas)
    print("parches de %d mapa(s) -> %s (%d B)"
          % (cuantos, parches_mod.EN_BUILD, pesan))
    # Y la otra decisión que ya está escrita: **a qué tamaño se dibuja cada
    # animación de batalla**. Sale de la misma vuelta de arriba; acá se junta
    # con el nombre y la hoja que la animación tiene en el LDB, que no los mira
    # nadie para dibujar y están para que el diff diga de cuál se habla.
    cuantos, pesan = parches_mod.escribir_animaciones(
        destino_parches,
        [dict(animacion_mod.informe(numero, animaciones[numero]),
              nombre=eventos.ANIMACIONES[numero].get("nombre", ""),
              hoja=eventos.ANIMACIONES[numero].get("imagen", ""),
              lado=animacion_mod.CAJA)
         for numero in sorted(animaciones)])
    print("parches de %d animación(es) -> %s (%d B)"
          % (cuantos, parches_mod.EN_BUILD_ANIM, pesan))
    # Y **a qué quince colores se reduce cada battler**, que es la decisión que
    # trajo la escena compuesta en la consola: ver tools/port/escena.py.
    cuantos, pesan = parches_mod.escribir_battlers(destino_parches,
                                                   escenas["battlers"])
    print("parches de %d battler(s) -> %s (%d B)"
          % (cuantos, parches_mod.EN_BUILD_BAT, pesan))
    # Y quién pidió cada uno, que no se versiona: es lo que separa, en la ROM
    # que se juega, lo del juego de lo que sólo existe por la tanda.
    parches_mod.escribir_usos(destino_parches, usos_de_los_parches(
        mapas, renderer.database, renderer.tree))
    if informe:
        print("material comprimido y compartido entre mapas:")
        for linea in informe:
            print(linea)

    # La música sale de acá y no de una receta aparte. `musicdata.inc` era
    # estado global como lo fue `mapdata.inc`, con el agravante de que nadie lo
    # regeneraba: una ROM armada para los mapas 4, 7, 19 y 1 —que no tienen
    # música— sonaba con el tema del mapa 348, que era el último que alguien
    # había generado a mano. Emitirlos juntos es lo único que garantiza que los
    # dos describan la misma ROM.
    #
    # Van **todos los temas**, compartiendo un solo banco de muestras, y
    # suena el del mapa donde la ROM arranca; los demás los prende un
    # `PlayBGM`, o el mapa al que se entra si trae uno propio —ver
    # `mapa_tema_callar` en tools/runtime/cargar_mapa.s—. A qué tasa queda cada
    # muestra lo decide la ARAM, paquete por paquete: ver `Banco` en
    # snes_music.py.
    musica = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                          "musicdata.inc")
    pedidos, arranque, tema_titulo, tema_de_mapa, tema_game_over = (
        temas_de_la_rom(
            mapas[args.inicial]["id"], temas, args.game_dir,
            renderer.database.title_music if not args.sin_titulo else None,
            [m["id"] for m in mapas],
            renderer.database.gameover_music if game_over_datos else None))
    # Los efectos, en el orden en que los piden las páginas compiladas: los
    # mapas se compilan en el orden de la ROM, así que los del mapa donde
    # arranca van primero —en la demo, la lluvia y el trueno de la apertura—.
    # Sólo los que están en algún paquete: uno que no está en ninguno no
    # suena en ningún lado —su fila de `sonido_tabla` queda en $FF— y
    # armarlo le costaría a la música, porque `snes_music.copias` cuenta los
    # efectos del cartucho. Pasa con los de ruta de `se_de_ruta_sin_paquete`.
    empaquetados = {n for pide in temas.por_mapa.values()
                    for n in pide["sonidos"]}
    pedidos_se = []
    for nombre, _v, _t, _b in temas.sonidos:
        if nombre not in pedidos_se and nombre in empaquetados:
            pedidos_se.append(nombre)
    # El paquete de audio de cada mapa, en el orden de la tabla de mapas: los
    # temas que sus páginas pueden prender —más, en el de arranque, el que
    # suena desde el principio, y en todos el propio del mapa— y sus efectos,
    # en el orden en que aparecen, que es la prioridad con que la ROM los sube
    # si no entran todos. Ver `paquete_cargar` en tools/runtime/paquete_de_audio.s.
    # Se arman **antes** que el banco, por nombre, porque el presupuesto de
    # cada muestra sale de ellos: ver `snes_music.Banco`.
    paquetes, apartes = [], []
    for i, _mapa in enumerate(mapas):
        pide = temas.por_mapa.get(i, {"temas": [], "sonidos": []})
        suyos = list(pide["temas"])
        if i == args.inicial and arranque != 0xFF and arranque not in suyos:
            suyos.insert(0, arranque)
        # Y el tema propio del mapa, **adelante**: es el único de la lista que
        # suena seguro al entrar, así que si la ARAM no alcanza para todo es
        # el último que se tiene que caer. Sin él en el paquete, sus muestras
        # las tendría que subir `tema_asegurar` al prenderlo, rearmando el
        # paquete entero una segunda vez.
        if tema_de_mapa[i] != 0xFF:
            if tema_de_mapa[i] in suyos:
                suyos.remove(tema_de_mapa[i])
            suyos.insert(0, tema_de_mapa[i])
        # Y los de salida, aparte y detrás de los efectos: los que el mapa
        # prende sólo para irse no tienen por qué entrar con sus efectos. Ver
        # `Temas.de_salida`. El propio del mapa y el del arranque no: ésos
        # suenan al entrar.
        salida = [t for t in temas.de_salida(i)
                  if t in suyos and t != tema_de_mapa[i]
                  and not (i == args.inicial and t == arranque)]
        suyos = [t for t in suyos if t not in salida]
        # Y los aparte, que tampoco van con los otros temas: los sube su
        # `PlayBGM` con los efectos del paquete. Ver `temas_aparte`.
        aparte = [t for t in suyos if pedidos[t] in snes_music.temas_aparte().get(
                      _mapa["id"], ()) and t != tema_de_mapa[i]
                  and not (i == args.inicial and t == arranque)]
        suyos = [t for t in suyos if t not in aparte]
        apartes.append(aparte)
        paquetes.append((suyos, list(pide["sonidos"]), salida))
    # Y el paquete de la pelea, detrás de los mapas: el tema de batalla y sus
    # efectos, que la ROM sube al abrir la pelea y descarga al cerrarla. Va
    # aparte y no adentro del paquete del mapa porque el tema de batalla solo
    # llena la ARAM; ver `eventos.PAQUETE_BATALLA`.
    pide = temas.por_mapa.get(eventos.PAQUETE_BATALLA)
    if pide:
        paquetes.append((list(pide["temas"]), list(pide["sonidos"]), []))
        apartes.append([])
    nombres_de_paquete = ([str(m["id"]) for m in mapas]
                          + (["pelea"] if pide else []))
    # Y el de la pantalla de Game Over, último: su tema solo y ningún efecto.
    # La ROM lo sube con la pantalla en negro, antes del fundido de entrada
    # —ver `game_over_negro` en tools/runtime/game_over.s—, y con un paquete propio
    # sube sólo eso: llegar con `tema_asegurar` rearmaría el paquete del mapa
    # entero detrás, que es un segundo de negro más. Para el reparto es un
    # paquete de un tema, que no le baja la tasa a nadie: sus muestras entran
    # solas en la ARAM.
    paquete_game_over = 0xFFFF
    if tema_game_over != 0xFF:
        paquete_game_over = len(paquetes)
        paquetes.append(([tema_game_over], [], []))
        apartes.append([])
        nombres_de_paquete.append("gameover")
    por_nombre = [(nombre, suyos, suyas, salida, aparte)
                  for nombre, (suyos, suyas, salida), aparte
                  in zip(nombres_de_paquete, paquetes, apartes)]
    # Y el de la pantalla de título, que no está en la tabla: `tema_asegurar`
    # sube su tema con el paquete del mapa de arranque detrás.
    if tema_titulo != 0xFF:
        suyos, suyas, _salida = paquetes[args.inicial]
        por_nombre.append(("titulo", [tema_titulo] + suyos, suyas))
    herencia = temas_heredados(temas, tema_de_mapa, args.inicial,
                               tema_titulo, nombres_de_paquete,
                               [suyos for suyos, _e, _s in paquetes],
                               apartes, no_se_dan=perillas.valor(
                                   "music", "jumps_that_never_happen",
                                   tipo=list))
    driver, muestras, hechos, banco = snes_music.build_varios(
        pedidos, args.game_dir, pedidos_se, por_nombre, herencia,
        aire_de_medida=args.aire_de_medida)
    # Y lo que `tools/audio/techos.py` necesita de cada tema —cuánto dura y
    # la huella de su mezcla—, escrito al lado: el banco ya no se puede
    # rearmar sin compilar las páginas, que es de donde salen los paquetes.
    with open(os.path.join(os.path.dirname(musica), "musica.json"),
              "w") as handle:
        json.dump({"temas": [
            {"nombre": t["nombre"],
             "largo": t["escrituras"][-1][0] + 1 if t["escrituras"] else 0,
             "huella": t.get("huella", ""),
             # De acá la lee `tools/audio/msu.py`, que arma sólo las pistas
             # de los temas del cartucho.
             "pista": t["pista"]} for t in hechos]},
            handle, indent=1)
    # Los efectos de cada paquete van por número y no por SRCN: varios
    # comparten el lugar del directorio. Ver `snes_music.lugares_de_efectos`.
    efectos = getattr(banco, "efectos", {})
    efecto_id = getattr(banco, "efecto_id", {})
    paquetes = [(suyos, [efecto_id[n] for n in suyas if n in efectos], salida)
                for suyos, suyas, salida in paquetes]
    directorio = (len(banco.voces), getattr(banco, "lugares", 0))
    efecto_lugar = [srcn - directorio[0] for srcn, _e in sorted(
        efectos.values(), key=lambda v: efecto_id[v[1].name])]
    if pide:
        assert nombres_de_paquete[len(mapas)] == "pelea", (
            "el paquete de la pelea tiene que quedar en el índice que emitió "
            "`emit` como PAQUETE_BATALLA")
        print("  paquete de audio de la pelea: %d tema(s), %d efecto(s)"
              % (len(pide["temas"]), len(paquetes[-1][1])))
    # **Y que el arranque entre en `BOOT_CUADROS`**: la ROM espera hasta ese
    # cuadro para que el lazo arranque siempre en el mismo, y si subir el
    # paquete del mapa de arranque tardara más, saldría más tarde y las
    # pruebas —que cuentan desde ahí— contarían mal. Ver el comentario de
    # `BOOT_CUADROS` en tools/runtime/ram_lejana.s.
    cuadros, del_paquete = snes_music.cuadros_del_arranque(
        driver, muestras, hechos, paquetes[args.inicial],
        cuadros_de_descomprimir(mapas[args.inicial], comprimidos),
        directorio)
    tope = snes_music.boot_cuadros()
    if cuadros > tope:
        raise SystemExit(
            "el arranque no entra en BOOT_CUADROS: el paquete del mapa de "
            "arranque son %d B y con el mapa, el driver y el directorio la "
            "cuenta da %.0f cuadros, contra %d. Subir BOOT_CUADROS en "
            "tools/runtime/ram_lejana.s, o achicar ese paquete"
            % (del_paquete, cuadros, tope))
    print("  arranque: el paquete del mapa de arranque son %d B, %.0f de "
          "los %d cuadros de BOOT_CUADROS" % (del_paquete, cuadros, tope))
    snes_music.emit(musica, hechos, driver, muestras, arranque, tema_titulo,
                    snes_music.tabla_de_sonidos(temas.sonidos, banco),
                    [p + (aparte,) for p, aparte in zip(paquetes, apartes)],
                    tema_de_mapa, directorio, efecto_lugar,
                    game_over=(tema_game_over, paquete_game_over))
    # El `.msu`: los fondos de calidad y los efectos de calidad, para leerlos
    # por el MSU-1 cuando está. Se escribe siempre, aunque el cartucho no
    # lleve ni fondos ni efectos, porque es también el archivo que enciende el
    # MSU-1 para las pistas.
    escribir_msu(args.msu or os.path.join(os.path.dirname(os.path.abspath(
        args.output)), "datos.msu"), musica, escenas["calidad"],
        por_nombre[:len(paquetes)], paquetes, hechos, muestras, banco,
        temas.sonidos, args.game_dir)
    for i, (suyos, suyas, salida) in enumerate(paquetes[:len(mapas)]):
        if suyos or suyas or salida or apartes[i]:
            print("  paquete de audio del mapa %d: %d tema(s), %d efecto(s)%s%s"
                  % (mapas[i]["id"], len(suyos), len(suyas),
                     ", y de salida %s" % ", ".join(hechos[t]["nombre"]
                                                    for t in salida)
                     if salida else "",
                     ", y aparte %s" % ", ".join(hechos[t]["nombre"]
                                                 for t in apartes[i])
                     if apartes[i] else ""))
    if pedidos_se:
        print("  efectos de sonido: %d, %d B en el cartucho"
              % (len(efectos), sum(len(e.data) for _s, e in efectos.values())))
    print("música -> %s: %s"
          % (musica, ", ".join(t["nombre"] for t in hechos)
             or "ninguna, sale muda"))

    # **Y recién acá se decide el acomodo de bancos**, con los dos archivos ya
    # escritos: reparte todo lo que los dos mandan a RODATA, y los bancos
    # quedan al final del último. Ver `tools/ensamblado/bancos.py`.
    piezas, usados = bancos.resolver([musica, args.output])
    print("acomodo de bancos: %d pieza(s) en %d banco(s)" % (piezas, usados))
    # Y el mapa de memoria para `ld65`, al lado: sale de acá y no de un
    # archivo a mano para que en qué banco arrancan los datos esté escrito
    # una sola vez, en `bancos.PRIMER_BANCO`.
    with open(os.path.join(os.path.dirname(os.path.abspath(args.output)),
                           "memoria.cfg"), "w") as handle:
        handle.write(bancos.cfg())
    for i, tema in enumerate(hechos):
        # El porcentaje de notas que llegan al stream va acá y no escondido:
        # es lo que se oye como "le faltan voces", y hasta el 2026-09-14 no lo
        # decía nadie. Ver workflow/decisiones/un-solo-banco-de-muestras.md.
        suenan = tema["resumen"].get("notas")
        # Y cuánto de lo que sí tiene muestra se pierde por falta de voces,
        # contra lo que se perdería sin remedio con ocho: es lo que mide el
        # reparto de `snes_music.assign`.
        perdido, piso = tema["resumen"].get("perdido", (0.0, 0.0))
        print("  %d. %-16s %4.0f s, %6d B de stream y %4d de sonidos, "
              "%s de las notas, %.0f%% del tiempo-nota sin voz (piso %.0f%%)%s"
              % (i, tema["nombre"], tema["segundos"], len(tema["stream"]),
                 6 * len(tema["sonidos"]),
                 "todas" if suenan is None or suenan > 0.999
                 else "%.0f%%" % (100 * suenan), 100 * perdido, 100 * piso,
                 ", suena desde el arranque" if i == arranque else ""))
    if hechos:
        print("  banco compartido: %d muestras, %d B en el cartucho; cada "
              "paquete tiene %d B de ARAM para sus muestras"
              % (len(banco.voces), sum(len(v.data) for v in banco.voces),
                 banco.libre))
        # A qué tasa quedó cada muestra y qué paquete la limitó: es lo que se
        # oye, y lo que dice dónde buscar lugar si hace falta. Una clave con
        # copias sale una vez por copia, con los temas que la usan: ver
        # `snes_music.copias`.
        usan = collections.defaultdict(list)
        for tema, suya in zip(hechos, banco.asignacion):
            for muestra in suya.values():
                usan[muestra].append(tema["nombre"])
        for clave, voz in zip(banco.claves, banco.voces):
            print("    %s %3d %-10s %5.1f kHz, %5d B%s%s%s"
                  % ("programa" if clave[0] == "p" else "golpe   ", clave[1],
                     voz.name.strip()[:10], voz.rate / 1000.0, len(voz.data),
                     ", raíz %d" % voz.root if clave[0] == "p" else "",
                     ", la limita " + banco.limita[clave]
                     if clave in banco.limita else "",
                     ", para " + " ".join(usan[clave])
                     if len(clave) > (3 if clave[0] == "p" else 2)
                     or any(len(k) > len(clave) and k[:len(clave)] == clave
                            for k in banco.claves) else ""))
        # Y cuánto le sobra a cada paquete, con sus efectos: los enteros con
        # lo que ocupan de verdad, no con lo que la música les presupuestó.
        # Las restricciones del banco ya los traen así —son las de `reales`,
        # ver `snes_music.copias`—: restarles otra vez lo de más daba
        # paquetes que no entraban y entraban.
        for r in banco.restricciones:
            print("    paquete %-28s %5d B de muestras, sobran %5d"
                  % (r.nombre[:28], banco.ocupa(r.claves),
                     r.libre - banco.ocupa(r.claves)))


def escribir_msu(ruta, musica, fondos, por_nombre, paquetes, hechos, muestras,
                 banco, sonidos, game_dir):
    """Escribe el `.msu` en `ruta` y le agrega a `musica` —el `musicdata.inc`—
    lo que la ROM necesita para leerlo: la firma, dónde está cada fondo y,
    por paquete, dónde está cada efecto y con qué altura suena cada sonido.

    Van primero los fondos —`fondos` son los `(tiles, colores)` de **todos
    los del juego**, por número, cada uno en su lugar fijo: ver
    `msu_datos.fondo_en`— y detrás los efectos de calidad de cada paquete, en
    el orden de la tabla de paquetes y cada paquete con los suyos en orden de
    lugar en el directorio —su SRCN—: es el orden en que `subir_colocadas`
    los sube, así que la ROM los lee
    de corrido, con una sola búsqueda por paquete. Un efecto que está en dos
    paquetes va dos veces aunque sea a la misma tasa: una búsqueda le cuesta
    a Mednafen uno o dos cuadros, y el archivo no tiene tope.

    `por_nombre` son los paquetes de la ROM como los ve `build_varios` —con
    los nombres de sus efectos— y `paquetes` los mismos como los emite `emit`
    —con sus números de efecto—, en el mismo orden. Ver
    tools/audio/efectos_msu.py.
    """
    efectos = getattr(banco, "efectos", {})
    de_numero = {i: n for n, i in getattr(banco, "efecto_id", {}).items()}
    # Lo que la música ocupa con MSU-1 en cada paquete: sólo los temas sin
    # pista, que `tema_por_msu` no saltea.
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
    hechas = dict(zip(unicas, en_paralelo(
        lambda par: efectos_msu.armar(par[0], par[1], game_dir), unicas)))

    entradas = [parte for par in fondos for parte in par]
    # Qué entrada es cada efecto de cada paquete, en orden de SRCN: dos del
    # mismo paquete nunca comparten lugar.
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
    print("  .msu: %d fondo(s) y %d efecto(s) en %d B, firma %s -> %s"
          % (len(fondos), sum(len(l) for l in del_paquete), len(archivo),
             firma.hex(), ruta))

    # Por paquete, una fila por efecto de su lista —la de `paquetes`, en el
    # orden en que la ROM la recorre—: dónde está en el `.msu`, cuánto mide y
    # dónde vuelve, que es siempre al principio porque van enteros.
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
        # Y la altura de cada sonido de `sonido_tabla` con la versión de este
        # paquete: con eso la ROM no hace cuentas, ni en la interrupción.
        # **Sólo los sonidos cuyo efecto es de acá**, como pares (índice,
        # altura) ordenados por índice y cerrados con $FFFF, que `altura_msu`
        # recorre: hasta el 2026-09-27 era una fila por paquete con todos los
        # sonidos, casi toda ceros, y con el capítulo del mundo entero pasaba
        # de un banco. Dos paquetes con la misma lista la comparten.
        suyas = tasas.get(str(nombre), {})
        lista = bytearray()
        for k, (efecto, _volumen, tempo, _balance) in enumerate(sonidos):
            altura = 0
            if efecto in suyas:
                altura = snes_music.altura_de_efecto(
                    hechas[efecto, suyas[efecto]], tempo)
            # Cero es "no es de acá" para la ROM, así que no se guarda.
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
            raise SystemExit("las tablas de los efectos del .msu pasan de un "
                             "banco: %d B" % len(tabla))
    posiciones = [(donde[2 * k], donde[2 * k + 1]) for k in range(len(fondos))]
    fondo_pos = b"".join(a.to_bytes(4, "little") + b.to_bytes(4, "little")
                         for a, b in posiciones) or bytes(8)
    with open(musica, "a") as handle:
        handle.write(
            "\n; El `.msu`: ver `escribir_msu` en tools/port/snes_convert.py.\n"
            "; Cuántas entradas del .msu son de fondos —dos por fondo, las\n"
            "; primeras— y cuántas de efectos, detrás: para las pruebas.\n"
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
    # Y lo mismo, legible, al lado: qué sonido es cada fila de `sonido_tabla`
    # y a qué tasa va cada efecto de cada paquete en el `.msu`. No lo lee la
    # ROM; es para las herramientas que tocan un efecto desde afuera y para
    # mirar qué decidió el reparto.
    with open(os.path.join(os.path.dirname(musica), "efectos.json"),
              "w") as handle:
        json.dump({"sonidos": [list(s) for s in sonidos],
                   "srcn": {e: srcn for e, (srcn, _v) in efectos.items()},
                   "tasas": tasas}, handle, indent=1)
    for (nombre, *_r) in por_nombre:
        suyas = tasas.get(str(nombre), {})
        if suyas:
            print("  efectos de calidad del paquete %s: %s"
                  % (nombre, ", ".join(
                      "%d Hz: %d" % (t, sum(1 for v in suyas.values()
                                            if v == t))
                      for t in sorted(set(suyas.values()), reverse=True))))


def temas_heredados(temas, tema_de_mapa, inicial, titulo, nombres_de_paquete,
                    del_paquete=None, apartes=None, no_se_dan=()):
    """[(nombre del paquete, índice de un tema que puede venir sonando al
    cargarlo)], para `snes_music.build_varios`.

    Casi ningún mapa del juego trae tema propio: lo prende una página, y
    hasta entonces sigue el del mapa de antes, y `paquete_cargar_ya` no mueve
    sus muestras. Así que el paquete de un mapa sin tema propio tiene que
    entrar al lado de lo que puede venir sonando.

    Se siguen los teletransportes de las páginas compiladas —`destinos` de
    `Temas.por_mapa`— sin mirar condiciones, con una regla que es la que
    hace que la cuenta sea realista y no "cualquier tema a cualquier mapa"
    (el 4 es el enrutador del juego): **un mapa con `PlayBGM` se va con uno
    de los suyos**, porque la página que salta es casi siempre la que antes
    prendió el tema. Un mapa con tema propio calla lo que suena antes de
    cargar el suyo —`mapa_tema_callar`—, así que no hereda nada; y al de
    arranque se llega con el del título sonando. Es lo que midió el paso 6 de
    `workflow/tasks/todo/la-calidad-de-la-musica.md` con un script aparte.

    `del_paquete` son los temas que el paquete de cada mapa sube al entrar
    —sin los de salida, ver `Temas.de_salida`—: un tema que llega sonando y
    no está ahí tiene que entrar al lado. Sin él, los que prenden sus
    páginas. Lo que sale de un mapa sigue siendo cualquiera de los que
    prenden, los de salida incluidos: son justamente los que se van con él.

    **Salvo en un mapa cuyos `PlayBGM` son todos de salida**: ahí la regla
    de arriba no vale, porque cada uno va pegado a su salto y los otros
    saltos del mapa no llevan ninguno. Cada salto lleva lo que dice
    `Temas.salto`: el tema de salida que lo precede, o lo que entró al mapa.
    Es el 41 y el 40 del juego: `Kfmus5` entra al 41 desde la página del 37
    y sigue por el 40, el 42, el 43, el 44 y el 45, mientras que
    `golden_axe-turtlevillage2` y `tsmedit` suenan sólo para irse. Del
    2026-09-27; hasta entonces esos mapas heredaban sólo sus temas de
    salida. El de arranque sigue con la regla de arriba: ver `lleva`.

    `apartes` son los temas aparte de cada paquete —ver
    `snes_music.temas_aparte()`—: no se van del mapa, así que no cuentan en lo
    que sale.

    `no_se_dan` son los saltos de páginas compiladas que no se pueden dar,
    como pares [mapa, destino]: un salto que nunca pasa le hace reservar
    lugar a un tema que nunca llega, a costa de los que sí. Los declara el
    juego, en `[music] jumps_that_never_happen` del archivo de proyecto.
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
        # El de arranque no: es el enrutador, que salta a medio juego según
        # variables, y sin mirar condiciones lo que entra ahí saldría para
        # cualquier lado.
        if suyos and suyos <= set(temas.de_salida(i)) and i != inicial:
            # Un destino que ningún salto anotado nombra —el de una página
            # que no compiló entera— lleva lo que entró.
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
    """Qué temas pide el cartucho, cuál suena al arrancar y cuál prende cada
    mapa al entrar.

    Se piden **todos**: los que los `PlayBGM` compilados nombran, más el del
    mapa donde la ROM arranca, que es el que suena sin que pase nada. **Y
    entran todos**: el índice lo da la lista y no cuesta ARAM. Lo que la ARAM
    limita son las muestras, y eso lo reparte `snes_music.build_varios` por
    paquete: a la tasa que dé el peor paquete de cada una, pero todas.

    Los índices son los de `Temas` y no se tocan: el bytecode ya los lleva
    emitidos. Por eso el del mapa se agrega **al final**, que es lo único que
    no renumera a los demás. Ir último no cuesta nada: desde el presupuesto
    por paquete ningún tema pierde muestras por su lugar en la lista.

    Y el tema propio de cada mapa de `map_ids` —en el orden de la tabla de
    mapas—, que es el `Game_Map::PlayBgm` de easyrpg: lo que suena al entrar
    por un teletransporte. Van detrás de todos, por la misma razón, y como el
    índice de cada uno o $FF, que es "entrar no cambia la música".
    """
    propio = snes_music.tema_del_mapa(map_id, game_dir)
    if propio:
        temas.indice(propio)            # lo agrega al final si no estaba
    # El de la pantalla de título va después, por lo mismo: agregar al final es
    # lo único que no renumera a los que el bytecode ya nombra. Sale del LDB
    # —`title_music`, que en el ABL es Fantasia_Of_The_Wind— y no de la línea
    # de comandos: es un dato del juego, no una elección nuestra.
    if titulo:
        temas.indice(titulo)
    # Y el de la pantalla de Game Over, por lo mismo: `gameover_music`, que
    # en el ABL es `GameOver3` y sale del RTP. Ver `PAQUETE_GAME_OVER`.
    if game_over:
        temas.indice(game_over)
    de_cada_mapa = []
    for nombre in snes_music.temas_de_los_mapas(map_ids, game_dir):
        indice = temas.indice(nombre) if nombre else 0xFF
        # $FF es "no cambia": un tema con ese número no se podría prender.
        # Tampoco lo prendería un `PlayBGM`, que lleva el índice en un byte.
        assert indice <= 0xFF, "el tema %r no entra en un byte" % nombre
        de_cada_mapa.append(indice)
    nombres = list(temas.nombres)
    return (nombres, (nombres.index(propio) if propio else 0xFF),
            (nombres.index(titulo) if titulo else 0xFF), de_cada_mapa,
            (nombres.index(game_over) if game_over else 0xFF))


def inicio_del_mapa(renderer, map_id, passable, width, height, ocupadas=()):
    """Dónde se para el héroe al entrar a este mapa, en celdas de 16x16.

    En el mapa donde el juego arranca de verdad, lo dice el LCF y no hay nada
    que elegir: A Blurred Line empieza en Map0004, que es una habitación vacía
    cuyo único trabajo es disparar un evento y teletransportar. Esa habitación
    no tiene ni una celda abierta por los cuatro lados, así que la heurística de
    abajo no tendría dónde poner a nadie.

    En cualquier otro mapa todavía no hay una respuesta real —se llega por
    teletransporte, y de dónde viene uno depende de por dónde entró—, así que se
    usa el tile abierto más cercano al centro, que es lo que las pruebas
    necesitan: un lugar desde el cual se pueda caminar.

    **Y hay mapas donde ninguna celda está abierta por los cuatro lados**: los
    cuartos de cinemática, que son una pantalla negra a la que siempre se llega
    por teletransporte con las coordenadas puestas. `LasheCityVehicle` —el mapa
    36, el que pregunta a dónde ir con el auto— es uno, y sin él no compila el
    teletransporte del 34 y se cae la cadena entera del auto. Ahí el número que
    se emite no lo usa nadie, pero la tabla lo lleva igual, así que se pone el
    centro geométrico en vez de cortar. El error de `hero_start` sigue valiendo
    para quien le pregunte por un mapa donde sí se va a caminar.
    """
    if map_id == renderer.tree.start_map_id:
        return renderer.tree.start_x, renderer.tree.start_y
    try:
        return hero_start(passable, width, height, ocupadas)
    except ValueError:
        return width // 2, height // 2


def images_de(renderer, args, charset):
    """El CharSet de un actor, cargado y cacheado."""
    if charset not in _charsets:
        _charsets[charset] = renderer.charsets.get(charset)
        if _charsets[charset] is None:
            sys.exit("no encuentro el CharSet %r" % charset)
    return _charsets[charset]


_charsets = {}


def lideres_posibles(renderer, map_ids, grupo):
    """Los actores que pueden llegar a dibujarse como héroe en esta ROM.

    El grupo con el que se arranca, más todos los que agregue un
    `ChangePartyMembers` de alguna página que compile. Sacar a alguien también
    cambia el líder, pero al siguiente de la lista, que ya está contado.

    Se compila con un bloque de textos, igual que la compilación de verdad:
    una página que agregue a alguien al grupo después de un cuadro de texto
    compila sólo con él. Filtrar distinto acá que allá dejaría a ese actor sin
    sus tiles en la VRAM y la ROM lo dibujaría con los del anterior. El bloque de textos que se arma es de
    descarte: acá sólo importa el sí o el no.

    Hace falta porque los tiles del héroe viven en VRAM y no se cargan en
    caliente: si el líder puede cambiar a mitad de mapa, los sprites de todos
    los candidatos tienen que estar puestos desde el principio.

    **Y son los que pueden ir primeros, no todos los que entran al grupo.** El
    gráfico del héroe es el del primero; alguien que siempre entra detrás de
    otro no se dibuja nunca, y sus doce poses son 192 tiles que no entran. Se
    nota en la cinemática de apertura, que saca al 10 y mete al 11, al 12 y al
    13: con los cuatro son 628 tiles de sprite y el reparto da 512.

    Quién va primero se sabe simulando: se aplican los `ChangePartyMembers` de
    las páginas que compilan, en el orden en que aparecen, con las mismas reglas
    que `Estado.cambiar_grupo`. Es una aproximación —qué página corre y cuándo
    depende de switches que acá no se saben— y por eso el orden importa: si
    alguna vez una ROM dibuja al héroe sin gráfico, empezar mirando acá.

    **El grupo se reinicia en cada mapa**, y ésa es la parte que costó. Antes se
    arrastraba de un mapa al siguiente en el orden de los archivos, que no es el
    orden en que se juegan: la página del "1 year earlier" del mapa 4 pone a
    Talan, y como el 4 va antes que el 1, cuando la simulación llegaba a la
    apertura el grupo ya tenía a Talan. El `pone Kersh` de la apertura lo metía
    **detrás**, así que Kersh nunca era líder, no entraba en la tabla de actores
    y el héroe se dibujaba sin gráfico. taro lo vio jugando: Core y Manta
    aparecían al final de la escalera y Kersh no.

    Reiniciar por mapa no es más correcto en general —sigue sin saberse con qué
    grupo se llega a cada uno— pero es la aproximación que corresponde: la tabla
    de actores es **por mapa**, así que la pregunta es quién puede liderar
    mientras ese mapa está cargado, y no qué pasó en los mapas anteriores del
    directorio.
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
    """Los `ChangePartyMembers` de las páginas que compilan, mapa por mapa y
    en orden: lo único de cada mapa que mira `lideres_posibles`.

    **Se calcula una vez por conversión**, porque no depende del grupo:
    `lideres_posibles` corre otra vez por cada caso de prueba que toca el
    grupo, y cada corrida cargaba y compilaba todos los mapas de nuevo. La
    compilación sólo lee los índices globales de `eventos`, que se llenan
    antes de la primera llamada y no cambian después.
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
            # Con el contexto del mapa, que es el mismo que usa el filtro de
            # verdad. Sin él, una página que mande a caminar a otro evento no
            # compila acá aunque sí compile allá, y los actores que agregue
            # se pierden: la cinemática de apertura suma a Kersh al grupo
            # justo después de mandar a caminar al evento 8, así que el héroe
            # se quedaba sin tabla de poses y no se dibujaba.
            # **Con el mismo contexto que la compilación de verdad**, y
            # no sólo con el bloque de textos. Faltaban `Temas`,
            # `Graficos` e `Imagenes`, y sin ellos una página que empieza
            # con un `PlayBGM` no compila **acá** y sí compila allá: los
            # actores que meta al grupo se pierden. Es exactamente lo que
            # le pasaba al auto de la persecución —`RaceController1` del
            # mapa 49 arranca con `PlayBGM` y después mete a `CarRED`—, y
            # el síntoma era que el héroe no se dibujaba: `hero_poses` en
            # cero porque el actor no estaba en la tabla del mapa.
            if eventos.compilar_pagina(
                    page, indices.get,
                    eventos.Mensajes(),
                    del_mapa.para(evento.id), eventos.Temas(),
                    eventos.Graficos(), eventos.Imagenes(
                        _juego())) is None:
                continue
            # **De a tandas de comandos seguidos**, y el líder se mira al
            # final de cada una: los `ChangePartyMembers` pegados corren en el
            # mismo cuadro —ninguno espera— así que el héroe no se dibuja con
            # el líder de a mitad de tanda. Mirándolo después de cada comando,
            # el 41 —que saca a todos antes de volver a meter a Talan, y lo
            # hace en dos páginas seguidas— dejaba de líderes posibles a
            # Arden, Saldra y AG7, con sus poses y sus colores en todos los
            # mapas del cartucho, y movía las paletas de mapas que no tienen
            # nada que ver.
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


# El directorio del juego, para `lideres_posibles`. Es feo pero es un solo
# lugar: la alternativa era pasarlo por tres funciones que no lo usan. Lo
# pone `main`, desde `--game-dir`.
args_game_dir = [None]


def _juego():
    """El de `main` o, si no pasó por ahí —una prueba que llama a estas
    funciones sueltas—, el del ambiente, que es el mismo `--game-dir`."""
    return args_game_dir[0] or recursos.GAME_DIR


def items_posibles(map_ids, actores=(), db=None, extra=()):
    """Los ítems que pueden estar en el inventario con estos mapas en la ROM:
    los que da algún `ChangeItems` de cualquier página, compile o no, los que
    vende alguna `OpenShop`, el equipo con el que arrancan los `actores` y los
    que da la página de prueba. Es un superconjunto, como `miembros_posibles`,
    y por la misma razón: un ítem de más cuesta su texto en el cartucho, uno
    de menos no se ve en la lista. `extra` son los comandos de las páginas de
    prueba, que se barren igual que los de los mapas."""
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
    """Los ítems que puede soltar algún enemigo de estas tropas al perder una
    pelea —su `drop_id`—, para que el cartucho lleve su nombre: la victoria
    lo cuenta y la lista del menú lo muestra. Los que `items_posibles` no
    encuentra en ninguna página. Todos los miembros, como `enemigos_rom`."""
    return {db.enemies[e].drop_id for n in tropas if n in db.troops
            for e in db.troops[n].members
            if 0 < db.enemies[e].drop_id < eventos.ITEMS_N}


def miembros_posibles(map_ids, grupo, extra=()):
    """Los actores que pueden estar en el grupo con estos mapas en la ROM.

    Los de arranque más los que agrega cualquier `ChangePartyMembers` de
    cualquier página de estos mapas. No se mira si la página compila: es para
    la pantalla de ranuras, que necesita la cara y el nombre de quien pueda
    aparecer en una partida guardada, y una cara de más no cuesta nada que
    importe. `extra` son los comandos de las páginas de prueba.

    `grupo` puede traer repetidos —el del cartucho más el de cada caso de
    prueba, que suele ser el mismo— y se cuentan una vez: repetido, un actor
    ocupaba una cara por cada caso que lo pedía.
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
    """Con qué grupo sigue la prueba después de su página, si la página lo
    toca: los `ChangePartyMembers` del caso aplicados al grupo del cartucho,
    con las mismas reglas que el intérprete. None si no lo toca."""
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
    """Si algo destella al héroe, los NPCs con su gráfico van con otra paleta.

    En la consola el destello se hace sobre la paleta del personaje, y un líder
    que además está como NPC en el mapa comparte paleta con ese NPC —para que el
    NPC no se dibuje con los colores de otro líder—, así que destellaban los
    dos. Se resuelve contando el gráfico de esos NPCs como otro, con el sufijo
    `rm2k.COPIA_SUFIJO`: el mismo dibujo, con su propia paleta. Cuesta una
    paleta por gráfico, y sólo en los mapas donde algo destella al héroe.
    `comandos` son los de las páginas de prueba.
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


# Los flags que describen **un caso** de prueba —lo que hace su página— y no
# el cartucho. Son los que pueden ir detrás de un `--caso`; los demás son del
# cartucho entero y van antes del primero. Desde el corte 3 del paso 9d es uno
# solo, el archivo con la página: lo que la página hace es dato de RM2k, no
# flags. `--grafico-de-prueba` es del cartucho a propósito: dice qué gráficos
# hay en el banco de sprites de los mapas donde corren los casos, no qué hace
# la página. Y dónde corre un caso tampoco es flag: lo dice el `Teleport` con
# que empieza, ver `mapa_del_caso`.
FLAGS_DE_CASO = ("comandos_de_prueba",)


def partir_en_casos(argv):
    """La línea de comandos partida en `--caso`: lo del cartucho, y los flags
    de cada caso que va detrás."""
    tramos = [[]]
    for token in argv:
        if token == "--caso":
            tramos.append([])
        else:
            tramos[-1].append(token)
    return tramos[0], tramos[1:]


def casos_de_prueba(parser, args, tramos):
    """Las páginas de prueba del cartucho, una por caso, en el orden de sus
    páginas. Cada una es una copia de `args` con los flags de su caso.

    El caso 0 son los flags de antes del primer `--caso`, así que un cartucho
    de un solo caso se arma como antes de que existiera esto. Si no hay, el
    primer `--caso` pasa a ser el 0. Cada caso se lleva los comandos de su
    archivo en `comandos`.
    """
    import copy
    casos = [args] if pide_pagina_de_prueba(args) else []
    defecto = parser.parse_args([])
    for tramo in tramos:
        suelto = parser.parse_args(tramo)
        for dest, valor in vars(suelto).items():
            if dest not in FLAGS_DE_CASO and valor != getattr(defecto, dest):
                sys.exit("--%s es del cartucho y no de un caso: va antes del "
                         "primer --caso" % dest.replace("_", "-"))
        caso = copy.copy(args)
        for dest in FLAGS_DE_CASO:
            setattr(caso, dest, getattr(suelto, dest))
        if not pide_pagina_de_prueba(caso):
            sys.exit("un --caso sin nada que la página de prueba haga")
        casos.append(caso)
    for caso in casos:
        with open(caso.comandos_de_prueba, encoding="utf-8") as archivo:
            caso.comandos = lcf.comandos_escritos(json.load(archivo))
    return casos


def comandos_de_casos(args, map_id=None):
    """Los comandos de todas las páginas de prueba, seguidos.

    Es lo que barren las funciones que miran las páginas del mapa para
    decidir qué lleva el cartucho —variables, ítems, miembros, lluvia—: una
    página de prueba es una página más.

    Con `map_id`, sólo los de los casos que **corren** en ese mapa —ver
    `mapa_del_caso`—: son los que deciden lo que es de cada mapa, como quién
    camina o qué gráficos van en su banco de sprites.
    """
    return [cmd for caso in args.casos
            if map_id is None or caso.mapa == map_id
            for cmd in caso.comandos]


def mapa_del_caso(caso, orden, inicial):
    """El mapa donde corre un caso: el de su `Teleport`, si empieza con uno, y
    si no el mapa donde arranca la ROM.

    Es como un caso elige dónde arrancar desde el paso 9e, en vez de un
    `--map-id` y una celda de arranque por cartucho: con el `Teleport` de
    RM2k, que es dato y no flag. La página vive igual en el evento 0 del mapa de
    arranque —ahí la encuentra la ROM y ahí corre primero—, pero lo que viene
    después del salto corre en el otro mapa, así que se compila con su
    contexto: sus eventos, las variables que miran sus páginas, sus gráficos.
    Compilada con el del mapa de arranque, una escritura a una variable que
    sólo mira el destino no pedía refresco, y el cofre del mapa 133 no
    aparecía aunque la variable ya valía lo que su página pide.
    """
    primero = caso.comandos[0] if caso.comandos else None
    if primero is None or primero.code != eventos.TELEPORT:
        return orden[inicial]
    destino = primero.parameters[0]
    if destino not in orden:
        sys.exit("%s: el caso salta al mapa %d, que no está en el cartucho "
                 "(lleva %s)" % (caso.comandos_de_prueba, destino,
                                 " ".join(str(m) for m in orden)))
    return destino


def mapas_de_prueba(args):
    """Los mapas donde corre algún caso, que son los que llevan en su banco
    los gráficos de `--grafico-de-prueba`."""
    if args.casos:
        return {caso.mapa for caso in args.casos}
    return {orden_de_mapas(args)[args.inicial]}


def pagina_de_caso(caso, mapa, temas, graficos, mensajes, indices, imagenes):
    """El bytecode de la página de prueba de un caso.

    Se compila como cualquier página del juego, con el contexto del mapa donde
    corre —ver `mapa_del_caso`—; lo único que el conversor le antepone es el
    `ControlSwitches` que la apaga, que es convención del arnés y no del caso
    —ver `eventos.SWITCH_DE_PRUEBA`—. Las tropas no se anotan acá sino al
    final, en `main`: la de la prueba va última.
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
        sys.exit("%s: la página de prueba no compila"
                 % caso.comandos_de_prueba)
    return codigo

def pide_pagina_de_prueba(args):
    """Si hay una página de prueba antes del primer `--caso`."""
    return bool(args.comandos_de_prueba)

def convertir(renderer, map_id, args):
    """Un mapa entero: tiles, colores, sprites, colisión y bloques."""
    game_map = renderer.cargar_mapa(
        os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    if args.casos and map_id == orden_de_mapas(args)[args.inicial]:
        # El evento de la página de prueba va **primero**: la ROM recorre los
        # eventos de menor a mayor, y la página de prueba tiene que correr
        # antes que las del juego. Arma el grupo con el que arranca la prueba,
        # y un mapa cuya página toca el grupo al entrar —el 21 agrega a Talan—
        # lo encontraba ya cambiado. Es un evento sin páginas: no se dibuja ni
        # compila nada, sólo ocupa el índice 0 para que todo lo que numera
        # eventos después de leer el mapa numere igual.
        vacio = lcf.Event.__new__(lcf.Event)
        vacio.id, vacio.name, vacio.x, vacio.y, vacio.pages = (
            0, "prueba", 0, 0, [])
        game_map.events.insert(0, vacio)
    separar_del_heroe(renderer, game_map, args,
                      comandos_de_casos(args, map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    capas = capas_convertidas(renderer, game_map)
    if capas is None:
        sys.exit("no encuentro el chipset del mapa %d" % map_id)

    # Y las capas otra vez, con los eventos opacos horneados adentro del mapa.
    # Se convierten **las dos** y se comparan porque hornear le agrega colores
    # al fondo: si eso le hiciera fusionar colores, o le corriera el reparto de
    # CGRAM a la capa de encima, cambiaría lo que se ve en celdas que no tienen
    # nada que ver con el horneado. En ese caso el mapa va sin hornear, que es
    # lo de siempre. La segunda conversión no se paga dos veces en un build
    # caliente: las dos quedan en el caché en disco, con su clave.
    sin_horneado = capas
    horneados = eventos_horneables(renderer, game_map)
    if horneados:
        capas, horneados = _hornear_si_no_mueve_la_cgram(
            renderer, game_map, map_id, sin_horneado, horneados)

    # Los personajes: el héroe con sus 12 poses porque camina, y cada NPC con la
    # que declara su página. Si un NPC usa el mismo personaje que el héroe,
    # comparten paleta y tiles sin que haya que hacer nada.
    #
    # Los dígitos del cronómetro se llevan una de las ocho paletas de sprite,
    # así que el techo baja a siete. Los eventos dibujados con un tile del
    # chipset entran mientras quepan en ese techo.
    # Quiénes van a caminar y a qué gráficos cambian las rutas. Va **antes**
    # del reparto de paletas porque un gráfico de la orden 34 es un personaje
    # más y pide paleta como cualquiera: repartiendo sin contarlo, entraría
    # después y podía no haber lugar.
    orden = orden_de_mapas(args)
    movibles, graficos_de_ruta, anima_quieto, giran = eventos_movibles(
        game_map, {m: i for i, m in enumerate(orden)}.get,
        asociaciones=args.asociaciones)
    # Y los de `--grafico-de-prueba`, que van sólo en los mapas donde corre
    # algún caso, y por lo mismo que sus páginas se compilan con el contexto
    # de ese mapa. Se agregan **después** de los del juego, que es el orden
    # en que los numera la compilación de verdad.
    if args.grafico_de_prueba and map_id in mapas_de_prueba(args):
        for charset, index in graficos_de_prueba(args.grafico_de_prueba):
            if (charset, index) not in graficos_de_ruta:
                graficos_de_ruta.append((charset, index))
    if comandos_de_casos(args, map_id):
        # Y los que mandan a caminar las páginas de prueba, que no salen de
        # `paginas_del_mapa`: hay que sumarlos a mano o el NPC caminaría con
        # una sola pose. Va **antes** del reparto de paletas: desde que la
        # paleta se elige sobre las poses que se ven, saber quién camina es
        # parte de elegir los colores y no sólo de repartir la VRAM. El evento
        # va por su id de RM2k y lo traduce el mismo `Eventos` que usa la
        # compilación.
        del_mapa = eventos.Eventos(game_map)
        for cmd in comandos_de_casos(args, map_id):
            if cmd.code == eventos.MOVE_EVENT and cmd.parameters \
                    and cmd.parameters[0] != eventos.RUTA_HEROE:
                blanco = del_mapa.blanco(cmd.parameters[0])
                if blanco:
                    movibles = movibles | {blanco - 1}
    # Y con eso, qué poses puede mostrar cada gráfico: es lo que decide sobre
    # qué píxeles se eligen sus quince colores. Ver `poses_del_mapa`.
    poses_por_grafico = poses_del_mapa(renderer, game_map, args.lideres,
                                       movibles, giran, graficos_de_ruta,
                                       anima_quieto)

    # Las ocho, con o sin cronómetro: sus dos colores entran en la paleta de
    # algún personaje. Reservarle una acá le sacaba eventos al mapa, porque este
    # número es el que decide cuáles se dibujan.
    #
    # **Menos una en los mapas que muestran animaciones de batalla**, desde el
    # 2026-09-12: la caja necesita una paleta entera para ella sola —sus quince
    # colores son de la animación y se pisan cuando empieza otra— y los mapas
    # 2 y 3, que son los de la intro, llenaban las ocho. Sin esto la escena del
    # Emitter Room se quedaba sin dibujo, que es justo lo que se estaba
    # haciendo. Lo que cuesta —qué personajes fusionan más colores— lo dice el
    # informe de cada mapa.
    muestra_animacion = mapa_muestra_animacion(
        game_map, renderer,
        comandos_de_casos(args, map_id))
    # Los colores del cronómetro se pasan al reparto y no sólo al empaquetado:
    # en un mapa que llene las ocho paletas hay que decidir a quién bajarle un
    # color para hacerle lugar, y eso cambia cómo se cuantiza a ese personaje.
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
        print("  mapa %d: %d gráfico(s) sin paleta propia, dibujados con una "
              "ajena: %s" % (map_id, len(prestadas),
                             ", ".join(sorted("%s:%d" % k for k in prestadas))))
    # Un evento horneado que se dibujaba con una paleta ajena no se puede
    # esconder: el sprite y el tile del fondo mostrarían colores distintos —el
    # prestado y los de verdad— y taparlo con el segundo cambia lo que se ve.
    # Así que ése se deshornea y vuelve a ser sprite, con los colores
    # prestados: se ve como se vería sin el horneado. Se pregunta acá y no en
    # `eventos_horneables` porque las prestadas salen del reparto, que corre
    # después de dibujar las capas. El primero fue `PawnDoorTop`, el evento 11
    # del mapa 37: hasta el 2026-09-26 esto era un `sys.exit`.
    horneado_prestado = sorted(
        evento for evento in horneados
        for npc in npcs
        if npc["evento"] == evento and (npc["charset"], npc["index"]) in prestadas)
    if horneado_prestado:
        print("  mapa %d: el evento %s se dibuja con una paleta ajena, así que "
              "no se hornea" % (map_id, ", ".join(str(e + 1)
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
        print("  mapa %d: %d evento(s) opaco(s) horneados en el mapa: %s"
              % (map_id, len(horneados),
                 ", ".join(str(e + 1) for e in sorted(horneados))))
    for evento, tile in descartados:
        aviso_de_descarte(
            "mapa %d: el evento %d, dibujado con el tile %s, no entra en "
            "las %d paletas de sprite y no se dibuja"
            % (map_id, evento + 1, tile[len(rm2k.TILE_PREFIX):],
               tope_de_paletas),
            cambia_de_grafico(game_map.events[evento]))
    # Quiénes cambian de pose y por lo tanto llevan sus doce al cartucho: los
    # candidatos a líder con gráfico y los NPCs que caminan. En ese orden, con
    # el líder inicial primero, que es el orden que espera el resto.
    actores_con_grafico = []
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        if not sprite_colors(images_de(renderer, args, a.charset),
                             a.charset_index):
            continue            # no tiene un solo pixel opaco: no se dibuja
        actores_con_grafico.append(actor)
    primero = renderer.database.lider(args.lideres)   # (CharSet, índice)
    animados = []
    for actor in actores_con_grafico:
        a = renderer.database.actors[actor]
        if (a.charset, a.charset_index) not in animados:
            animados.append((a.charset, a.charset_index))
    animados.sort(key=lambda par: par != primero)   # el líder inicial primero
    for npc in npcs:
        if npc["evento"] in movibles \
                and (npc["charset"], npc["index"]) not in animados:
            animados.append((npc["charset"], npc["index"]))
    # Y los gráficos a los que una orden 34 cambia. Van al banco por lo mismo
    # que los que caminan: después de cambiar, el evento sigue caminando, así
    # que le hacen falta las doce poses del gráfico nuevo y no la que declaraba
    # su página.
    #
    # Los que no tienen **un solo pixel opaco** no entran, y no es un caso
    # raro: `nobodyhere` son 185 de las 437 órdenes 34 del juego. Un CharSet
    # transparente no tiene colores, así que no tiene paleta que pedirle al
    # banco; y no hace falta, porque lo que la orden hace ahí es esconder la
    # fila. Es el mismo `sprite_colors` con que se descarta a un actor sin
    # gráfico.
    grafico_se_ve = []
    for charset, index in graficos_de_ruta:
        # Se dibuja si tiene un pixel opaco **y** entró en el reparto de
        # paletas. Lo segundo casi siempre es que sí; cuando no, la orden lo
        # esconde igual que a un transparente, que es lo que hace la ROM con
        # cualquier gráfico que no entró.
        grafico_se_ve.append(
            bool(sprite_colors(images_de(renderer, args, charset), index))
            and (charset, index) in reparto[1])
        if grafico_se_ve[-1] and (charset, index) not in animados:
            animados.append((charset, index))
    # Y los que giran hacia el héroe: sus doce poses, para subir la que mira
    # hacia él. Van al final para no mover el índice de nadie más.
    for pares in giran.values():
        for par in sorted(pares):
            if par in reparto[1] and par not in animados:
                animados.append(par)
    afuera_de_ruta = [par for par, se_ve in zip(graficos_de_ruta, grafico_se_ve)
                      if not se_ve and sprite_colors(
                          images_de(renderer, args, par[0]), par[1])]
    for charset, index in afuera_de_ruta:
        aviso_de_descarte(
            "mapa %d: el gráfico %s:%d, al que cambia una ruta, no entra "
            "en las %d paletas de sprite: esa orden esconde al evento en vez "
            "de cambiarlo" % (map_id, charset, index, tope_de_paletas),
            # Una orden 34 **es** un cambio de gráfico, así que siempre cuenta.
            True)

    # Las ranuras del banco de VRAM, una pose cada una: el héroe en el bloque
    # 0 —si algún candidato a líder tiene gráfico—, después cada NPC que camina
    # con la suya, y los quietos compartidas por (CharSet, índice, pose), que
    # nunca cambian. Un NPC que camina no comparte ni con otro igual: cambian
    # de pose cada uno por su cuenta.
    ranuras = []
    if actores_con_grafico:
        charset, index = animados[0]
        ranuras.append(("heroe", charset, index, POSE_INICIAL))
    for npc in npcs:
        if npc["evento"] in movibles:
            if npc["cambia"]:
                # Dos mecanismos sobre la misma fila: las doce poses del
                # cartucho y el gráfico de la página. La ROM no sabe las dos a
                # la vez, así que **gana caminar** y su gráfico deja de seguir a
                # la página. Es lo mismo que hacía antes de que `collect_npcs`
                # contara el "nada" como un estado —ver `cambia` allá—, o sea
                # que no se pierde nada que antes anduviera.
                #
                # Esto era un `sys.exit`, y estaba bien mientras ningún evento
                # lo pidiera. Al contar el estado "nada" lo pide el evento 10
                # del mapa 8, y cortar por eso sería no armar la ROM por un
                # detalle de un NPC que camina.
                # Lo que **sí** sigue a la página es si la fila se ve: eso es
                # el bit 4 y no pisa el tile. Sin separarlos, un evento que
                # camina y aparece con la página no aparecía nunca, porque la
                # fila nace escondida cuando al cargar el mapa ninguna página
                # cumple. Ver `grafico_de_pagina` en tools/runtime/paginas_de_eventos.s.
                npc["aparece"] = True
                npc["cambia"] = False
            ranuras.append((("ev", npc["evento"]), npc["charset"],
                            npc["index"], npc["pose"]))
        else:
            # La pose de su fila y, si el gráfico sigue a la página, la de
            # cada página: el refresco de la ROM elige entre ranuras que ya
            # están en la VRAM.
            poses = [(npc["charset"], npc["index"], npc["pose"])]
            if npc["cambia"]:
                poses += [g for g in npc["graficos"]
                          if g is not None and g[:2] not in npc["afuera"]]
            for clave in poses:
                if clave not in {r[0] for r in ranuras}:
                    ranuras.append((clave,) + clave)
    # La ranura de giro: una pose más, para el quieto que se da vuelta hacia
    # el héroe. Los quietos comparten ranura por (CharSet, índice, pose), así
    # que girar la suya giraría también a los demás que la usan; el que gira
    # se muda a ésta mientras dura su página. Es una sola porque sólo gira el
    # evento que el héroe disparó, y hay uno a la vez. Los que caminan o
    # animan no la necesitan: tienen la suya. Ver GIRO en eventos.py.
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
            # Por el cargador del renderer, que también fabrica el CharSet de
            # un evento dibujado con un tile del chipset.
            images[charset] = renderer.charsets.get(charset)
            if images[charset] is None:
                sys.exit("no encuentro el CharSet %r" % charset)

    tiles, palettes, where, paleta_de, colores = build_characters(
        images, personajes, ranuras, reparto)
    # Se cuenta acá y no adentro porque el mensaje tiene que nombrar al
    # culpable, que es el mapa. Con `npcs_dibujables` arriba esto ya no
    # tendría que fallar por un tile; si falla es por los CharSets.
    if len(palettes) > tope_de_paletas:
        sys.exit("el mapa usa %d personajes en %d paletas y hay %d de sprite"
                 % (len(personajes), len(palettes), tope_de_paletas))
    bancos = banco_de_poses(images, animados, colores)
    indice_animado = {p: k for k, p in enumerate(animados)}
    # La tabla de la orden 34: por cada gráfico que una ruta pide, en qué
    # entrada de `npc_poses` está y con qué paleta. $FF en la entrada es
    # "esconder la fila", que es lo que hace un CharSet transparente.
    ruta_graficos = [
        (indice_animado[par], paleta_de[par]) if se_ve else (0xFF, 0)
        for par, se_ve in zip(graficos_de_ruta, grafico_se_ve)]
    # El cronómetro, si esta ROM lo lleva: sus glifos van al final del banco y
    # comparten paleta con quien tenga lugar, que casi siempre hay.
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
            print("  mapa %d: AVISO, las gotas de lluvia no entran en las "
                  "paletas de sprite y acá no llueve" % map_id)
    # El cartel del `ShowPicture`, si el suyo es de este mapa. La ranura la
    # elige `Imagenes.elegir` **en el orden de la tabla de mapas**, que es este
    # mismo lazo.
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
                sys.exit("mapa %d: el cartel %r no entra: el mapa ya usa las "
                         "%d paletas de sprite y el fundido necesita una "
                         "entera. Ver `cartel_de_imagen`."
                         % (map_id, registro.nombre, OBJ_PALETTES))
            print("  mapa %d: el cartel %r, %d objetos en %d tiles desde el "
                  "%d, paleta %d" % (map_id, registro.nombre,
                                     info["objetos"],
                                     imagen.tiles_reservados(info),
                                     imagen_base, imagen_pal))
    # Y la caja de la animación de batalla, si alguna página de este mapa
    # puede mostrar una que se dibuje. Va última porque se lleva el final del
    # banco y la paleta que quede libre después del cartel. El criterio de
    # que entre es una cuenta y la emite el conversor: si no hay paleta o no
    # hay VRAM, **este mapa no dibuja animaciones** y lo dice.
    anim_base, anim_pal = 0, 0
    if muestra_animacion:
        probando, probando_base, probando_pal = animacion_de_mapa(
            tiles, palettes, 1 if imagen_base else 0)
        if not probando_base:
            # Sin paleta este mapa no dibuja animaciones. Es lo mismo que se
            # hace con las gotas de lluvia: se declara y se sigue.
            print("  mapa %d: AVISO, las animaciones de batalla no se dibujan "
                  "acá: el mapa ya usa las %d paletas de sprite y la caja "
                  "necesita una entera" % (map_id, OBJ_PALETTES))
        else:
            # La VRAM, en cambio, **corta**: que entre o no depende del reparto
            # de tiles y no de las paletas. Cortaba porque la referencia de
            # Python no lo podía recalcular sin rehacer el banco entero; sin
            # ella podría avisar y seguir, como con las paletas.
            cuantos = len(probando) // 32
            try:
                layout = vram_layout(len(tile_data) // BYTES_PER_TILE, cuantos,
                                     len(above_data[0]) // 32)
            except SystemExit:
                layout = None
            if layout is None or cuantos > layout["sprites"][1]:
                sys.exit(
                    "mapa %d: muestra animaciones de batalla y los %d tiles de "
                    "su caja no entran en el banco de sprites: gasta %d de %d. "
                    "Ver `animacion_de_mapa`."
                    % (map_id, animacion_mod.TILES, cuantos,
                       layout["sprites"][1] if layout else 0))
            tiles, anim_base, anim_pal = probando, probando_base, probando_pal
            print("  mapa %d: las animaciones de batalla se dibujan en %d "
                  "tiles desde el %d, paleta %d"
                  % (map_id, animacion_mod.TILES, anim_base, anim_pal))
    # Y las filas de los eventos horneados nacen escondidas: su tile ya está
    # dibujado en el mapa. La fila sigue estando entera —el evento dispara,
    # cierra el paso y es blanco de una ruta como cualquiera—, y `build_oam` la
    # saltea sin armar un objeto, que es lo que se está ahorrando. `tile_pasa`
    # se deja puesto a propósito: la celda ya la resuelve la tabla del mapa con
    # los mismos bits, y si alguna vez una página volviera a mostrar esta fila,
    # el dato que necesita está.
    for npc in npcs:
        if npc["evento"] in horneados:
            npc["visible"] = False
    table = npc_table(npcs, where, movibles, indice_animado, anima_quieto)
    # Por cada candidato a líder, su paleta y en qué banco de poses están las
    # doce suyas. La ROM no calcula nada a partir de la pose: busca el puntero
    # acá y lo encola.
    actores = []
    for actor in args.lideres:
        a = renderer.database.actors[actor]
        if actor not in actores_con_grafico:
            # Un actor con el gráfico vacío. `DummyHero`, el 10, es así: sus
            # ocho poses no tienen un pixel opaco, y RM2k no dibuja nada. Va con
            # el puntero centinela y la ROM se saltea el objeto.
            actores.append((actor, 0, None, []))
            continue
        # Sus colores, en el mismo orden que el `lookup` con que se empaquetaron
        # sus poses: `paleta_del_personaje` devuelve la paleta ordenada y
        # `build_characters` indexa 1..15 sobre ella. Si los dos órdenes se
        # fueran, el héroe saldría con los colores cambiados de lugar.
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

    # La colisión: un byte por celda de 16x16 con los cuatro bits de dirección
    # ya resueltos. Toda la lógica de RM2k —que la capa alta manda salvo que sea
    # decorado, que las caras de pared se cruzan siempre— se decide acá, no en
    # la consola.
    chipset = renderer.database.chipsets[game_map.chipset_id]
    flags = build_passability(chipset)
    passable = passability_map(game_map, flags)
    # Las celdas con un NPC quedan afuera: si el héroe arrancara sobre uno, los
    # dos tendrían la misma clave de orden y cuál queda encima dependería de un
    # desempate que no tiene por qué coincidir entre la consola y el render.
    # Con **todos** los que se dibujan en alguna página: un tile que quedó
    # afuera de las paletas igual ocupa.
    ocupadas = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
    start_x, start_y = inicio_del_mapa(
        renderer, map_id, passable, game_map.width, game_map.height, ocupadas)
    collision = (passable, start_x, start_y, game_map.width, game_map.height)

    if len(table) > NPC_MAX:
        sys.exit("el mapa %d tiene %d NPCs y en OAM entran %d"
                 % (map_id, len(table), NPC_MAX))
    if len(ruta_graficos) > RUTA_GRAF_MAX:
        sys.exit("el mapa %d tiene %d gráficos de orden 34 y entran %d: ver "
                 "RUTA_GRAF_MAX" % (map_id, len(ruta_graficos), RUTA_GRAF_MAX))

    print("Mapa %d %r: %dx%d celdas de %dx%d px"
          % (map_id, name, len(tilemap[0]), len(tilemap),
             CELL, CELL))
    print("  %d colores distintos, %d en CGRAM de %d disponibles, %d fusionados"
          % (summary["colores"], summary["usados"], summary["presupuesto"],
             summary["fusionados"]))
    print("  %d tiles únicos de %d celdas (%.0f%% de reuso)"
          % (summary["tiles"], summary["celdas"],
             100.0 * (1 - summary["tiles"] / summary["celdas"])))

    print("  sprites: %d personajes, %d ranuras, %d tiles en VRAM, %d paletas; "
          "%d con sus doce poses en el cartucho"
          % (len(personajes), len(where), len(tiles) // 32, len(palettes),
             len(animados)))
    print("  %d NPCs con CharSet de %d eventos" % (len(table), len(game_map.events)))

    abiertos = sum(1 for b in passable if b == 0x0F)
    print("  colisión: %d celdas, %d abiertas por los cuatro lados (%.0f%%), "
          "el héroe arranca en (%d,%d)"
          % (len(passable), abiertos, 100.0 * abiertos / len(passable),
             start_x, start_y))

    print("  capa por encima del héroe: %d tiles, %d colores en %d paleta(s) "
          "desde la %d, %d fusionados"
          % (len(above_data[0]) // 32, len(above_data[1]) // 2,
             BG_PALETTES - above_data[3], above_data[3], above_data[4]))

    celdas, bloques, block_pass, block_terreno, combos = build_blocks(
        game_map, tilemap, above_data[2], passable,
        game_map.width, game_map.height, chipset)
    print("  el mapa entra en %d bloques de 16x16 para %d celdas: %d B de "
          "grilla más %d B de tabla, contra los %d B del tilemap expandido"
          % (len(bloques) // BLOCK_BYTES, len(celdas), 2 * len(celdas),
             len(bloques), 2 * summary["celdas"]))
    ventanas_x = (len(tilemap[0]) + WINDOW_W - 1) // WINDOW_W
    ventanas_y = (len(tilemap) + WINDOW_H - 1) // WINDOW_H
    if ventanas_x > 1 or ventanas_y > 1:
        print("  no entra en la ventana de %dx%d: la ROM va a ir redibujando"
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
        # Los gráficos de la orden 34 tal como los numeró la pasada que arma
        # el banco. `main()` compara contra los que junte compilando de
        # verdad: si las dos pasadas se fueran, el bytecode llevaría índices
        # de una tabla que dice otra cosa.
        "graficos_de_ruta": graficos_de_ruta,
        "collision": collision, "celdas": bytes(words),
        "ev_pos": ev_pos_bytes(game_map),
        # Los dos crecen mientras se compilan las páginas, si alguna sustituye
        # tiles: ver `Sustituciones`. Por eso son mutables y se congelan recién
        # al emitirlos.
        "bloques": bloques, "pass": block_pass, "terreno": block_terreno,
        "combos": combos,
        # El terreno de una celda **fuera del mapa**: `GetTerrainTag` usa el
        # índice 0 del ChipSet, o sea el primer autotile, y no el de ninguna
        # celda. Ver `op_terrain`.
        "terreno_fuera": rm2k.terreno_de(chipset, 0),
        "layout": vram_layout(
            len(tile_data) // BYTES_PER_TILE,
            len(sprite[0]) // 32 if sprite else 0,
            len(above_data[0]) // 32),
        "resumen": summary,
        "anim": anim_bytes(summary["animacion"]),
        "imagenes_fondo": summary["imagenes"],
        # Se guarda el mapa entero porque las páginas de los eventos no se
        # pueden compilar hasta que estén todos los mapas: un `Teleport`
        # traduce ids de mapa a índices de la tabla.
        "game_map": game_map,
        # Para la tabla de páginas: dónde quedó cada (CharSet, índice, pose)
        # en el banco de sprites, qué eventos cambian de gráfico con la
        # página y qué gráficos suyos quedaron afuera de las paletas.
        "where": where,
        # Para el giro hacia el héroe: en qué entrada de `npc_poses` están las
        # doce poses de cada gráfico, que es el +30 de la página.
        "giro_k": {par: indice_animado[par] for par in animados},
        "giran": set(giran),
        "cambian": {npc["evento"] for npc in npcs if npc["cambia"]},
        # Y los que sólo aparecen y desaparecen con ella: los que caminan, a
        # los que el gráfico se les fijó más arriba.
        "aparecen": {npc["evento"] for npc in npcs if npc.get("aparece")},
        "afuera": {npc["evento"]: npc["afuera"] for npc in npcs},
    }


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Adeleine's primitives: which colors are lost and how they are grouped.

Everything here **changes what is seen**: merging one color into another,
deciding which colors go together in a palette, measuring how much an image
moves if a color is taken out of it. It is the artistic half of the graphics
pipeline, and that is why it is not in `tools/snes/voodoo/`, which only converts
what already fits and never touches a pixel: see "`tools/snes/voodoo/` no decide
colores" in `AGENTS.md`.

Its users are `map_layers.py` —`split_above`, `build_palette`—,
`sprites.py` —`drawable_npcs`— and `menus.py`. The day Adeleine
moves to Rust, this is what goes first.

Until 2026-09-17 it was called `pixeles.py` and also did the part that
decides nothing —indexing a tile into its palette, trying its mirrored
versions—, which moved to Voodoo.
"""

import collections
import sys

import numpy

CELL = 8

# How many colors fit in a four-bit palette, minus index 0, which is
# transparent: that of the sprites and the upper layer. The lower layer is at
# eight bits and passes its own limit as a parameter.
COLORS_PER_PALETTE = 16
USABLE_COLORS = COLORS_PER_PALETTE - 1


def tile_colors(tile):
    """The colors of a tile, not counting the transparent pixels."""
    return frozenset(p for row in tile for p in row if p is not None)


def try_pack(sets, limit, per_palette=USABLE_COLORS):
    """Splits the colors into palettes so that each tile uses only one.

    Colors may repeat across palettes: what has to be achieved is that the
    set of colors of each tile is contained in one of them. Best-fit, the
    tiles with the most colors first, each into the group that grows the
    least.

    Tiles with the same number of colors go **in the order of their
    colors**. Until 2026-09-29 they went in the order of the Python `set`
    they came in, which is the order of CPython's hashes: nothing a program
    in another language can reproduce, and Adeleine was moving to Rust.
    """
    groups = []
    for colors in sorted(sets, key=lambda s: (-len(s), sorted(s))):
        best = None
        for index, group in enumerate(groups):
            size = len(group | colors)
            if size <= per_palette and (best is None or size < best[1]):
                best = (index, size)
        if best is not None:
            groups[best[0]] |= colors
        elif len(groups) < limit:
            groups.append(set(colors))
        else:
            return None
    return groups


def luma_distance(a, b):
    """Distance between colors, weighted as the eye perceives it.

    The weights are the usual luma ones —0.30 / 0.59 / 0.11— multiplied by a
    hundred so the math is **integer**. The order it produces is the same as
    with the fractional coefficients, and in exchange two equal distances
    compare equal: `merge_least_visible` multiplies this by the pixel count
    and then sorts, and there a tie resolved by the last bit of a float is
    exactly the kind of difference that changes the ROM without anyone having
    touched anything.
    """
    return (30 * (a[0] - b[0]) ** 2 + 59 * (a[1] - b[1]) ** 2
            + 11 * (a[2] - b[2]) ** 2)


def merge_least_visible(counts, keep, accept=None):
    """Merges the pair of colors that shows the least, until it passes.

    "What shows the least" is **how many pixels move times how far they
    move**: the cost of sending color `a` to color `b` is
    `pixeles(a) * luma_distance(a, b)`, which is the error the change adds to
    the image. The cheapest pair is merged, the pixels of the one that went
    are added to the one that stayed, and it repeats.

    The criterion used to be just `pixeles(a)`: the least used color was
    killed without looking at how far away its neighbor was. That is what
    left Talan and the save point gray. A color can cover few pixels and
    still **define the drawing** —a highlight, an eye, the edge of a
    helmet—, and sending it ten steps away shows; meanwhile two nearly equal
    grays covering half the sheet both survived because neither was the least
    used. With the cost above it is exactly the other way around: the two
    grays melt into one —it costs almost nothing— and the highlight stays,
    which is a CGRAM entry well spent.

    It does not invent colors: the one that stays is always one of those that
    were already there, so there is no need to quantize to 15 bits again and
    it does not depend on the PIL version. And it is deterministic: the cost
    is an integer and ties are broken by the color.

    `accept` decides when to stop: for the map it is "the tiles fit in the
    palettes", for the sprite it is "15 colors or fewer are left". Returns
    the mapping from old color to new color and the list of merges done.

    Without `accept` it is memoized: the same character is quantized the
    same way on every map where it appears, and the math is pure. The key
    carries the colors **in their order**, because the mapping comes out in
    that order, and copies are returned, because some callers complete the
    mapping they receive.
    """
    if accept is None:
        key = (tuple(counts.items()), keep)
        if key not in _merged_cache:
            _merged_cache[key] = _merge_least_visible(counts, keep, None)
        mapping, merged = _merged_cache[key]
        return dict(mapping), list(merged)
    return _merge_least_visible(counts, keep, accept)


_merged_cache = {}


def _merge_least_visible(counts, keep, accept):
    mapping = {c: c for c in counts}
    merged = []
    # With numpy, and each color by its rank in the order of the tuples: that
    # way the by-color tie-break of the `min`s —the neighbor by
    # `(distancia, color)`, the victim by `(costo, color)`— is the tie-break
    # by rank, integer and without floats. `luma_distance` and the cost are
    # the usual ones.
    colors = sorted(counts)
    position = {c: i for i, c in enumerate(colors)}
    n = len(colors)
    red, green, blue = (numpy.array([c[k] for c in colors], dtype=numpy.int64)
                        for k in range(3))
    order = numpy.arange(n, dtype=numpy.int64)
    weight = numpy.array([counts[c] for c in colors], dtype=numpy.int64)
    alive = numpy.ones(n, dtype=bool)
    never = numpy.iinfo(numpy.int64).max
    # Which original colors are in each one today, so as not to walk the
    # whole mapping on every merge.
    members = [[c] for c in colors]
    # The cheapest neighbor of each living color, and what it costs to send
    # it there. It is recomputed only for those whose neighbor was the dead
    # one —and for the one that grew—, which is what keeps this from being
    # cubic: the lower layer's sheets reach three hundred colors and merge a
    # hundred.
    cost = numpy.zeros(n, dtype=numpy.int64)
    neighbor = numpy.full(n, -1, dtype=numpy.int64)

    def recompute(i):
        distance = (30 * (red - red[i]) ** 2 + 59 * (green - green[i]) ** 2
                    + 11 * (blue - blue[i]) ** 2)
        key = numpy.where(alive, distance * n + order, never)
        key[i] = never
        j = int(key.argmin())
        if key[j] == never:
            neighbor[i] = -1
            return
        cost[i] = weight[i] * distance[j]
        neighbor[i] = j

    for i in range(n):
        recompute(i)
    n_alive = n

    while True:
        if accept is None:
            if n_alive <= keep:
                return mapping, merged
        else:
            result = accept(mapping)
            if result is not None:
                return mapping, merged, result

        if n_alive <= 1:
            sys.exit("The palette could not be reduced enough.")

        candidates = numpy.where(alive, cost, never)
        victim_i = int(numpy.flatnonzero(alive & (candidates
                                                  == candidates.min()))[0])
        target_i = int(neighbor[victim_i])
        victim, target = colors[victim_i], colors[target_i]
        for original in members[victim_i]:
            mapping[original] = target
        members[target_i] += members[victim_i]
        merged.append((victim, target, int(weight[victim_i])))
        weight[target_i] += weight[victim_i]
        alive[victim_i] = False
        n_alive -= 1
        recompute(target_i)
        for i in numpy.flatnonzero(alive & (neighbor == victim_i)).tolist():
            if i != target_i:
                recompute(i)


def reduce_colors(grid, budget):
    """Merges colors until the tiles fit in `budget` palettes.

    The real limit is not the number of colors but how they are distributed:
    a tile with 14 colors forces those 14 to be in the same palette. The tail
    of the distribution is usually colors of one or two pixels, so merging
    the least used one into its nearest neighbor and retrying costs very
    little.

    The work is done on the unique tiles, which are a few hundred, and not on
    the map's cells, which in Lashe City are 22500.
    """
    counts = collections.Counter(p for row in grid for tile in row
                                 for line in tile for p in line
                                 if p is not None)
    unique = {tile for row in grid for tile in row}

    def accept(mapping):
        remap = {tile: tuple(tuple(mapping.get(p) for p in line)
                             for line in tile)
                 for tile in unique}
        sets = {tile_colors(t) for t in remap.values()}
        groups = try_pack(sets, budget)
        return (remap, groups) if groups is not None else None

    mapping, merged, (remap, groups) = merge_least_visible(counts, 0, accept)
    return ([[remap[tile] for tile in row] for row in grid],
            groups, merged, counts)

#!/usr/bin/env python3
"""Adeleine, as the converter calls it: which colors are lost and how they
are grouped.

Everything Adeleine decides **changes what is seen**: merging one color
into another, deciding which colors go together in a palette. It is the
artistic half of the graphics pipeline, and that is why it is not in
`tools/snes/voodoo/`, which only converts what already fits and never
touches a pixel: see "`tools/snes/voodoo/` no decide colores" in
`AGENTS.md`.

**The decisions are made by `adeleine`**, a Rust binary on the PATH
—`tools/snes/adeleine/`—, which this runs with `stage.run`: the colors go
in a request, what was decided comes back. What stays here is the shape
the converter wants them in —tuples, `Counter`s, grids of tiles— and
`luma_distance`, which is not a decision but the distance the callers
look the nearest color up with, and is called too often to cross a
process: see its comment.

Its users are `map_layers.py` —`split_above`, `build_palette`—,
`sprites.py` —`drawable_npcs`—, `menus.py` and `scene.py`.

Until 2026-09-17 it was called `pixeles.py` and also did the part that
decides nothing —indexing a tile into its palette, trying its mirrored
versions—, which moved to Voodoo. Until 2026-09-29 the decisions were made
here, in Python.
"""

import collections
import hashlib
import json
import shutil

from port import stage

CELL = 8

# How many colors fit in a four-bit palette, minus index 0, which is
# transparent: that of the sprites and the upper layer. The lower layer is at
# eight bits and passes its own limit as a parameter.
COLORS_PER_PALETTE = 16
USABLE_COLORS = COLORS_PER_PALETTE - 1

BINARY = "adeleine"


def version():
    """The installed binary's hash, for the key of whatever caches what it
    decided: recompiling it without touching any `.py` has to invalidate
    it."""
    path = shutil.which(BINARY)
    if path is None:
        raise SystemExit(stage.MISSING % (BINARY, BINARY))
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tile_colors(tile):
    """The colors of a tile, not counting the transparent pixels."""
    return frozenset(p for row in tile for p in row if p is not None)


def luma_distance(a, b):
    """Distance between colors, weighted as the eye perceives it: the same
    function `adeleine` merges with —see `luma_distance` in its `merge.rs`,
    which says why it is integer—.

    It stays in Python because its callers do not ask for a decision but
    for the nearest color of a palette, inside a `min`, for every color of
    every character: tens of thousands of calls a build, where a process
    each would cost minutes. It goes to Rust when they do.
    """
    return (30 * (a[0] - b[0]) ** 2 + 59 * (a[1] - b[1]) ** 2
            + 11 * (a[2] - b[2]) ** 2)


def _run(command, request):
    written = stage.run(BINARY, BINARY, command, request)
    return json.loads(written[command + ".json"])


def _color(c):
    return tuple(c)


def _merges(answer):
    return [(_color(v), _color(t), n) for v, t, n in answer["merges"]]


def _palettes(answer):
    return [set(map(_color, p)) for p in answer["palettes"]]


def _counts(counts):
    return [list(c) + [n] for c, n in counts.items()]


def try_pack(sets, limit, per_palette=USABLE_COLORS):
    """Splits the colors into palettes so that each tile uses only one.

    Colors may repeat across palettes: what has to be achieved is that the
    set of colors of each tile is contained in one of them. `None` if they
    do not fit in `limit` palettes. How they are split is `adeleine pack`'s
    business.
    """
    answer = _run("pack", {"tiles": [sorted(s) for s in sets],
                           "palettes": limit, "per_palette": per_palette})
    if answer["palettes"] is None:
        return None
    return _palettes(answer)


def merge_least_visible(counts, keep):
    """Merges the pair of colors that shows the least until `keep` are left.

    What shows the least and why is `adeleine merge`'s business. Returns
    the mapping from old color to new color, in the order of `counts`, and
    the list of merges done.

    It is memoized: the same character is quantized the same way on every
    map where it appears, and the answer depends only on the colors. The key
    carries them **in their order**, because the mapping comes out in that
    order, and copies are returned, because some callers complete the
    mapping they receive. It is also what keeps the processes few: most
    of the questions a build asks are repeated.
    """
    key = (tuple(counts.items()), keep)
    if key not in _merged_cache:
        answer = _run("merge", {"counts": _counts(counts), "keep": keep})
        mapping = dict(zip(counts, map(_color, answer["mapping"])))
        _merged_cache[key] = mapping, _merges(answer)
    mapping, merged = _merged_cache[key]
    return dict(mapping), list(merged)


_merged_cache = {}


def reduce_colors(grid, budget):
    """Merges colors until the tiles fit in `budget` palettes.

    Adeleine gets the pixels of each color over the whole grid and the
    colors of each distinct tile, which are a few hundred, and not the
    map's cells, which in Lashe City are 22500. Returns the grid with the
    merges applied, the palettes and the merges.
    """
    counts = collections.Counter(p for row in grid for tile in row
                                 for line in tile for p in line
                                 if p is not None)
    unique = {tile for row in grid for tile in row}
    answer = _run("reduce", {"counts": _counts(counts),
                             "tiles": [sorted(tile_colors(t)) for t in unique],
                             "palettes": budget})
    mapping = dict(zip(counts, map(_color, answer["mapping"])))
    remap = {tile: tuple(tuple(mapping.get(p) for p in line) for line in tile)
             for tile in unique}
    return ([[remap[tile] for tile in row] for row in grid],
            _palettes(answer), _merges(answer))

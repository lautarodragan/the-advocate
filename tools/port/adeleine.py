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
the converter wants them in —tuples, `Counter`s— and
`luma_distance`, which is not a decision but the distance the callers
look the nearest color up with, and is called too often to cross a
process: see its comment.

Its users are `menus.py` and `scene.py`. A map's layers and characters,
which used to be the rest, are `rm2k-snes-maps`'s since 2026-09-30, and it
uses Adeleine as a library.

Until 2026-09-17 it was called `pixeles.py` and also did the part that
decides nothing —indexing a tile into its palette, trying its mirrored
versions—, which moved to Voodoo. Until 2026-09-29 the decisions were made
here, in Python.
"""

import json

from port import stage

CELL = 8

# How many colors fit in a four-bit palette, minus index 0, which is
# transparent: that of the sprites and the upper layer. The lower layer is at
# eight bits and passes its own limit as a parameter.
COLORS_PER_PALETTE = 16
USABLE_COLORS = COLORS_PER_PALETTE - 1

BINARY = "adeleine"


def _run(command, request):
    written = stage.run(BINARY, BINARY, command, request)
    return json.loads(written[command + ".json"])


def _color(c):
    return tuple(c)


def _merges(answer):
    return [(_color(v), _color(t), n) for v, t, n in answer["merges"]]


def _counts(counts):
    return [list(c) + [n] for c, n in counts.items()]


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



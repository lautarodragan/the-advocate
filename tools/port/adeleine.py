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
the converter wants them in: tuples, `Counter`s.

Its user is `scene.py`. A map's layers and characters and the screens'
faces, which used to be the rest, are `rm2k-snes-maps`'s and
`rm2k-snes-screens`'s since 2026-09-30, and they use Adeleine as a
library.

Until 2026-09-17 it was called `pixeles.py` and also did the part that
decides nothing —indexing a tile into its palette, trying its mirrored
versions—, which moved to Voodoo. Until 2026-09-29 the decisions were made
here, in Python.
"""

CELL = 8

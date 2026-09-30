"""The map's two background layers in mode 3, as the rest of the converter
reads them.

**They are converted by `rm2k-snes-maps`** —the lower half of CGRAM split
between them, the 15-bit quantization, what Adeleine merges, the tiles
Voodoo cuts; see `layers.rs` in `rm2k-snes-map-background`—. What stays
here is its answer in the shape `map_record`, `mapdata` and the patches read
(`layers_answer`), and the constants of the split the emission needs: where
the background starts in CGRAM, the upper layer's priority, the backdrop
color and the palette of the message window.

Until 2026-09-30 all of it was here, in Python, with a disk cache of what
came out and a precomputation in parallel, which went with it.
"""

import json

from rpgmaker import rm2k


# CGRAM has 256 entries. The upper half belongs to the sprites; the lower half
# is shared by the background, which goes at 8 bits per pixel and addresses
# CGRAM directly, and the layer that goes above the hero, which goes at 4 bits
# and therefore counts its index within a palette of 16.
#
# Where the split between the two falls is not fixed: the converter decides it
# map by map, in `rm2k-snes-maps`. With one palette above, the background has
# 111 colors; with three, 79. It used to be two always, and 27 maps didn't fit
# —the first three of the game among them— while the background left colors
# unused.
#
# The cap below is not a quality decision but the shape of the hardware: the
# background has to keep at least one palette. How many the upper layer really
# takes comes from what the background doesn't need.
BG_PALETTES = 8                          # the lower half of CGRAM, in palettes


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


# --- conversion -------------------------------------------------------------


# The families by the name the stage gives them.
_FAMILY_NAMES = {"water": "agua", "animated": "animado"}


def layers_answer(written):
    """What `rm2k-snes-maps` wrote of a map's layers —`layers` and `map`
    write them the same—, in the shape the rest of the converter reads:
    (background, above), each a tuple, the background's with its summary."""
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
        # The map in blocks of 16x16 and each cell's passability, which the
        # stage makes from the same map and the two tilemaps. They go in the
        # summary and not in a third element, where the rest of the converter
        # reads the layers' tuples by position.
        "pasabilidad": bytes(answer["passability"]),
        "bloques": {"celdas": answer["blocks"]["cells"],
                    "tabla": written["blocks.bin"],
                    "pass": written["block-passability.bin"],
                    "terreno": written["block-terrain.bin"],
                    "combos": [tuple(c) for c in answer["blocks"]["combos"]]},
    }
    return ((written["background.bin"], bg["cgram"], bg["tilemap"], stats),
            (written["above.bin"], written["above-cgram.bin"],
             above["tilemap"], above["first"], len(above["merges"]),
             above_png))


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



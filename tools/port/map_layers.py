"""The map's two background layers in mode 3, as the rest of the converter
reads them.

**They are converted by `rm2k-snes-maps`** —the lower half of CGRAM split
between them, the 15-bit quantization, what Adeleine merges, the tiles
Voodoo cuts; see `layers.rs` in `rm2k-snes-map-background`—. What stays
here is its answer in the shape the rest of the converter and the patches
read (`layers_answer`), and how many palettes the background has. Where the
background starts in CGRAM, the upper layer's priority, the backdrop color
and the message window's palette are the emission's: `cgram.rs` in
`rm2k-snes-mapdata`.

Until 2026-09-30 all of it was here, in Python, with a disk cache of what
came out and a precomputation in parallel, which went with it.
"""

import json


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

"""How the 64 KB of VRAM are laid out, as `rm2k-snes-mapdata vram`
publishes it: the six layouts a map can get, which one each map gets, and
the constants of the cartridge's memory the converter reads —the tilemap
window, the save slots screen, the window's bases—.

**The layouts are the emission's**, `vram.rs` in `rm2k-snes-mapdata`: they
are the contract with the runtime, and the maps, the screens and the
emission read them from there. Until 2026-10-01 they lived here. What
stays is their answer in the shape the converter reads: each layout as a
dict of `(base in words, tiles)` by the names it always had.
"""

from port import stage

BINARY = "rm2k-snes-mapdata"
PROJECT = "mapdata"

# The stage's names of a layout's pieces, by the converter's.
_PIECES = {"sprites": "sprites", "tiles": "tiles", "mapa": "map",
           "encima": "above", "ventana": "window",
           "ventana_map": "window_map"}

# The constants, by the name the converter imports them with.
_CONSTANTS = {"MAP_LAYOUT": "map_layout", "VRAM_ABOVE_MAP": "above_map",
              "SLOTS": "slots", "SLOT_VRAM": "slot_vram",
              "SLOT_MAP": "slot_map", "SLOT_TEXT_WIDTH": "slot_text_width",
              "SLOT_TEXT_LEVEL": "slot_text_level"}

_PUBLISHED = {}
_CHOSEN = {}


def _ask(maps):
    import json
    written = stage.run(BINARY, PROJECT, "vram", {"maps": maps})
    return json.loads(written["vram.json"])


def published():
    """What the stage publishes, asked once per conversion. The layouts are
    checked against the hardware on every call: if one does not respect
    it, the conversion stops there."""
    if not _PUBLISHED:
        answer = _ask([])
        answer["layouts"] = [
            (layout["name"], {mine: tuple(layout[theirs])
                              for mine, theirs in _PIECES.items()})
            for layout in answer["layouts"]]
        _PUBLISHED.update(answer)
    return _PUBLISHED


def __getattr__(name):
    if name in _CONSTANTS:
        return published()[_CONSTANTS[name]]
    if name == "LAYOUTS":
        return published()["layouts"]
    if name == "WINDOW_BASES":
        return tuple(published()["window_bases"])
    if name == "WINDOW_W":
        return published()["window"][0]
    if name == "WINDOW_H":
        return published()["window"][1]
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


def choose(tiles, sprites=0, above=0):
    """`(name, layout)` of the VRAM layout a map gets, according to what it
    spends: the first that fits, as the stage answers it. The same three
    numbers give the same layout, so each answer is asked once."""
    key = (tiles, sprites, above)
    if key not in _CHOSEN:
        _CHOSEN[key] = _ask([list(key)])["maps"][0]
    chosen = _CHOSEN[key]
    if "refused" in chosen:
        raise SystemExit(chosen["refused"])
    return chosen["layout"], dict(published()["layouts"])[chosen["layout"]]


def vram_layout(tiles, sprites=0, above=0):
    """The layout of `choose`, without its name."""
    return choose(tiles, sprites, above)[1]


def _check_splits():
    """That each layout respects the hardware: the stage checks it every
    time it is asked."""
    published()

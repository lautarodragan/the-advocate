"""The battle animations the cartridge carries: which ones the emitted
bytecode shows, and their frames as they end up in VRAM, as the emission
takes them (`animations_request`): `rm2k-snes-mapdata` writes them, without
their empty tiles. The images themselves come from `animation.py`.
"""

from port import events
from port import animation as animation_mod
from port.snes_format import pack_tile


def rom_animations(maps, renderer):
    """The battle animations the already emitted bytecode shows, by RM2k
    number, each one converted by `animation.py`.

    The bytecode is walked and not the commands, which is what makes it the
    truth and not a guess: what counts is what ended up emitted, after the
    page filter decided which ones go in. It is the same rule as
    `route_targets` in the event compiler's scan.
    """
    numbers = set()
    for map_info in maps:
        for page in map_info.get("pages", ()):
            code = page.get("codigo") or b""
            for i, c in events.walk_code(code):
                if (c[i] == events.OP_ANIMATION
                        and c[i + 1] != events.ANIM_NO_DRAWING):
                    numbers.add(c[i + 1])
    converted = animation_mod.by_numbers(renderer, sorted(numbers))
    return {number: info for number, info in converted.items()
            if info is not None}


def animation_frame(frame):
    """The 2 KB of a battle animation frame as they end up in VRAM: the box's
    64 4bpp tiles, in order."""
    data = bytearray(animation_mod.TILES * 32)
    for tile, cell in animation_mod.cells(frame).items():
        data[tile * 32:(tile + 1) * 32] = pack_tile(cell, planes=4)
    return bytes(data)


def animations_request(animations):
    """The cartridge's battle animations as `rm2k-snes-mapdata emit` takes
    them: the box they are drawn in, and per animation its frames as they
    end up in VRAM, its anchor as the console's table carries it and its
    colors. How a frame is cut into the box and where its anchor falls are
    `animation.py`'s; the emission only writes them."""
    return {
        "box": animation_mod.BOX, "obj": animation_mod.OBJ,
        "objects": animation_mod.OBJECTS, "tiles": animation_mod.TILES,
        "screen": list(animation_mod.SCREEN),
        "list": [{"number": number,
                  "frames": [animation_frame(f).hex()
                             for f in info["cuadros"]],
                  "anchor": list(animation_mod.rom_anchor(info)),
                  "palette": [list(c) for c in info["paleta"]]}
                 for number, info in sorted(animations.items())],
    }

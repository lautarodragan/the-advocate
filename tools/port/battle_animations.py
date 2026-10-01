"""The battle animations the cartridge carries: which ones the emitted
bytecode shows, and their frames as the cartridge stores them, ready for the
`.inc`. The images themselves come from `animation.py`.
"""

from port import events
from port import animation as animation_mod
from port.snes_format import COLORS_PER_PALETTE, cgram_word, pack_tile
from port.asm import block


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


# The end of a frame without its empty tiles: no tile of the box reaches 64.
FRAME_END = 0xFF


def frame_without_gaps(data):
    """A frame from `animation_frame` as the cartridge stores it: only its
    tiles that aren't all zero, each with its number in front, and
    `FRAME_END`.

    The frames are **almost all transparency**, so storing them whole was
    paying for zeros: what was measured is in the task
    `la-compresion-de-mapas-y-graficos.md`. What ends up in VRAM doesn't
    change: `anim_frame_build` rebuilds the 2 KB in far RAM and the vblank
    uploads them whole, as before.
    """
    out = bytearray()
    for tile in range(animation_mod.TILES):
        one = data[tile * 32:(tile + 1) * 32]
        if any(one):
            out.append(tile)
            out += one
    out.append(FRAME_END)
    return bytes(out)


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


def animations_asm(animations, maps):
    """The cartridge's battle animations, ready for the `.inc`.

    Four things:

      `anim_battle`          by RM2k number, which entry it gets, or $FF.
                             It goes by number and not by an index of ours so
                             that neither end has to carry a counter the other
                             must guess.
      `anim_battle_table`    per entry: how many frames, where its anchor
                             falls inside the box and which frame it starts at.
      `anim_battle_frames` per frame, the 24-bit pointer to its tiles
                             without the empty ones: see `frame_without_gaps`.
                             One per frame and not a contiguous block per
                             animation, which dates from when each frame was
                             2 KB and 28 didn't fit in a bank.
      `anim_battle_cgram`    its sixteen colors, which the ROM uploads when the
                             animation starts.
      `anim_battle_split` per map, where and with which palette it is drawn
                             here, or 0 if this map doesn't draw animations.
    """
    order = sorted(animations)
    slot_of = {number: k for k, number in enumerate(order)}
    cap = (max(order) + 1) if order else 1
    out = [
        "\n; --- the drawing of the battle animations ---",
        ";",
        "; The box is a single one for the whole ROM and the reason is in",
        "; tools/port/animation.py: four 32x32 objects in one row of blocks",
        "; of the name grid, which is the most that fits in the sprite VRAM",
        "; map 2 has left free. What changes per map is where that row lands",
        "; and with which palette, and that goes in `anim_battle_split`,",
        "; one byte per map.",
        "ANIM_B_BOX    = %d" % animation_mod.BOX,
        "ANIM_B_OBJ    = %d" % animation_mod.OBJ,
        "ANIM_B_OBJECTS = %d" % animation_mod.OBJECTS,
        "ANIM_B_TILES  = %d" % animation_mod.TILES,
        "ANIM_B_BYTES  = %d" % (animation_mod.TILES * 32),
        "ANIM_B_STRIDE = 8",
        "; How high an animation number `anim_battle` reaches: the bytecode",
        "; carries the RM2k number as is and a larger one isn't in the table,",
        "; so the ROM compares it before reading it.",
        "ANIM_B_MAX    = %d" % cap,
        "; The center of the screen, which is where the ones with scope",
        "; `Scope_screen` land: `DrawAt(screen_width / 2, screen_height / 2)`.",
        "ANIM_B_CENTER_X = %d" % (animation_mod.SCREEN[0] // 2),
        "ANIM_B_CENTER_Y = %d" % (animation_mod.SCREEN[1] // 2),
        "ANIM_B_NO       = $%02X" % events.ANIM_NO_DRAWING,
        "ANIM_B_SCREEN = $%02X" % events.ANIM_TARGET_SCREEN,
    ]
    out.append(block("anim_battle",
                     bytes(slot_of.get(n, 0xFF) for n in range(cap))))
    table = bytearray()
    first = 0
    for number in order:
        info = animations[number]
        # The anchor **as the ROM wants it**: with the shift of
        # `Animation::Position` already baked in, so the console only
        # subtracts.
        ax, ay = animation_mod.rom_anchor(info)
        table += bytes([len(info["cuadros"]), ax & 0xFF, ay & 0xFF, 0,
                        first & 0xFF, first >> 8, 0, 0])
        first += len(info["cuadros"])
    out.append(block("anim_battle_table", bytes(table)))
    cgram = bytearray()
    for number in order:
        colors = [(0, 0, 0)] + list(animations[number]["paleta"])
        colors += [(0, 0, 0)] * (COLORS_PER_PALETTE - len(colors))
        for color in colors:
            cgram += cgram_word(color).to_bytes(2, "little")
    out.append(block("anim_battle_cgram", bytes(cgram)))
    # The pointer table, with labels: it can't come from `block()`, but it
    # **is declared** with `.block` for the same reason as the page one —the
    # ROM reads it with a 24-bit pointer and it can't straddle two banks—.
    pointers = [".block %d" % (4 * first), "anim_battle_frames:"]
    for number in order:
        for k in range(len(animations[number]["cuadros"])):
            pointers.append("    .dword anim_battle_%d_%d" % (number, k))
    out.append("\n".join(pointers))
    for number in order:
        info = animations[number]
        for k, frame in enumerate(info["cuadros"]):
            out.append(block("anim_battle_%d_%d" % (number, k),
                             frame_without_gaps(animation_frame(frame))))
    split = bytearray()
    for map_info in maps:
        sprite = map_info["sprite"]
        base, pal = (sprite[15], sprite[16]) if sprite else (0, 0)
        # Bit 7 is "drawn here", and below go the 64-tile block and the
        # palette, three bits each. In one byte because the map record is at
        # exactly its 128: see MAP_STRIDE.
        split.append((0x80 | ((base // 64) << 3) | pal) if base else 0)
    out.append(block("anim_battle_split", bytes(split)))
    return "\n".join(out) + "\n"

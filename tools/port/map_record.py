"""What the ROM carries per map, ready for ca65: the map record and its
table, the event pages, the NPC and leader tables, the ChipSet animation
runs, and each map's data blocks.

Everything here reads what `convert_map` already left in the map's
`map_info`, and writes text; nothing here decides anything about the map.
"""

from port import events
from rpgmaker import rm2k
from port.adeleine import CELL
from port.snes_format import BYTES_PER_TILE, COLORS_PER_PALETTE, cgram_word
from port.asm import pointer
from port.map_layers import BACKDROP, FAMILIES
from port.sprites import (OBJ_COLORS, OBJ_PRIORITY, OBJ_PRIORITY_ABOVE,
                          SPRITE_POSES, block_tile)
from port.materials import COMPRESSED_KINDS


def npc_table(npcs, where, movable=(), animated_index=None, animates_still=()):
    """The NPCs ready for the ROM, already sorted the way RM2k draws them.

    The drawing order is first by layer and only then by Y: a "below" one stays
    below the hero even if it is further forward on screen. On the console,
    the object with the lowest OAM index is the one shown on top, so the table
    goes from front to back.

    **This initial order also rules afterwards.** The walking ones change Y
    and the ROM re-sorts them one at a time, with an insertion that respects
    the order of ties: between two tied ones the order of this list still
    holds.

    The ones in `movable` also carry which cartridge pose bank their twelve
    are in, so the ROM uploads them on the fly while they walk.
    """
    rows = []
    for npc in sorted(npcs, key=drawing_order, reverse=True):
        walks = npc["event"] in movable
        key = (("ev", npc["event"]) if walks
               else (npc["charset"], npc["index"], npc["pose"]))
        block, slot = where[key]
        rows.append({
            "x": npc["x"] * 16, "y": npc["y"] * 16,
            "tile": block_tile(block), "palette": slot,
            "layer": npc["layer"], "blocks": npc["blocks"],
            "event": npc["event"], "dir": npc["pose"] // 3,
            "pose": npc["pose"],
            "poses": (animated_index[(npc["charset"], npc["index"])]
                      if walks else None),
            "speed": npc.get("speed", 3),
            # The still ones with continuous animation: their column comes from
            # the game clock. The walking ones carry it in their route slot, so
            # the flag doesn't apply to them even if their page asks for it too.
            "animates": npc["event"] in animates_still,
            "visible": npc.get("visible", True),
            "tile_pass": npc.get("tile_pass"),
        })
    return rows


# A map's record in the table. The stride is a power of two so that going from
# index to offset is shifts and not a multiplication, and there is room to
# spare on purpose: adding a field must not move anything already there.
#
# The pointers go four bytes at a time even though they are three. The spare
# byte is unused; what is gained is that the low part of each pointer always
# lands on an even address, which is how it is read with the accumulator in 16
# bits.
MAP_STRIDE = 128
MAP_SCALARS = [
    ("MAP_BW", "width in 16x16 cells"),
    ("MAP_BH", "height in 16x16 cells"),
    ("CAM_MAX_X", "how far the camera reaches without going out"),
    ("CAM_MAX_Y", ""),
    ("HERO_MAX_X", "how far the hero reaches"),
    ("HERO_MAX_Y", ""),
    ("HERO_START_X", "where it starts, in pixels"),
    ("HERO_START_Y", ""),
    ("VRAM_TILES", "the VRAM layout, in words"),
    # Where the background tilemap goes. The upper layer's base has no field:
    # it is the high nibble of BG12NBA_VALUE, and the record is full.
    ("VRAM_MAP", ""),
    ("VRAM_SPRITE", ""),
    ("VRAM_WINDOW", "0 if this ROM carries no message window"),
    ("VRAM_WINDOW_MAP", "and its own 32x32 tilemap"),
    ("MAP_TILES", "how many background tiles, for the DMA"),
    ("MAP_CGRAM", "how many CGRAM words"),
    ("ABOVE_TILES", ""),
    ("ABOVE_CGRAM", ""),
    ("SPRITE_TILES", ""),
    ("SPRITE_CGRAM", ""),
    ("NPC_COUNT", "how many NPCs with a CharSet"),
    ("EV_COUNT", "how many events the map has, with or without a graphic"),
    ("TIMER_BASE", "the first tile of the timer digits, 0 if there are none"),
    ("RAIN_BASE", "the first tile of the raindrops, 0 if there are none"),
    ("ACTOR_COUNT", "how many party leader candidates"),
    ("PAGE_COUNT", "how many event pages have to be resolved"),
    ("ROUTE_GRAPHIC_COUNT", "how many distinct graphics command 34 asks for"),
]
MAP_BYTES = [
    ("OBSEL_VALUE", "8x8 and 32x32 objects, and the page of their tiles"),
    ("BG12NBA_VALUE", "the tile pages of BG1 and BG2"),
    ("ABOVE_FIRST", "which CGRAM entry the upper layer starts at"),
    ("TIMER_PAL", "the sprite palette of the timer digits"),
    ("RAIN_PAL", "the sprite palette of the raindrops"),
    # A byte and not a scalar because the record is at exactly its 128. A
    # block's tile is always a multiple of four and less than 512.
    ("TURN_TILE4", "the tile of the turn slot divided by four, or $FF"),
    # The terrain, which is what `StoreTerrainID` answers. Both are bytes
    # because RM2k's terrain is an index into `Data.terrains` and doesn't go
    # over 255, and because the map record is at exactly its 128.
    ("TERRAIN_OUTSIDE", "the terrain of a cell outside the map"),
    ("TERRAIN_PLANE", "the terrain of the whole map, or 0 if there is a table"),
]
MAP_POINTERS = ["map_tiles", "map_cgram", "above_tiles", "above_cgram",
                "sprite_tiles", "sprite_cgram", "map_cells", "map_blocks",
                "block_pass", "block_terrain", "npc_table", "actor_table",
                "pages", "ev_pos", "npc_poses", "route_graphic",
                # The ChipSet animation: the two tile runs and their
                # drawings. See `anim_bytes`.
                "anim_tiles"]
MAP_PTR_STEP = 4
# Where the pointers start: right after the scalars and the bytes, rounded up
# to the stride. **It is computed and not written by hand**, because written by
# hand it already failed: adding one more scalar left `ABOVE_FIRST` and the
# first pointer at the same offset, the ROM read the palette byte as a pointer
# to the map tiles and the screen came out a flat color.
#
# It is one of those neither end can see: the assembler sees two different
# names with the same value, which is legal, and the pixel-by-pixel comparison
# says "all wrong" without saying where. The only defense is for the number to
# come from the data.
MAP_PTR_BASE = (-(-(len(MAP_SCALARS) * 2 + len(MAP_BYTES))
                  // MAP_PTR_STEP) * MAP_PTR_STEP)
assert MAP_PTR_BASE + len(MAP_POINTERS) * MAP_PTR_STEP <= MAP_STRIDE, \
    "the map record doesn't fit in %d bytes" % MAP_STRIDE

# An event page: which event it belongs to, what activates it, and where its
# code is. The pages of one event go together and in order, which is what lets
# the ROM choose the last one that meets its conditions in a single pass,
# without carrying a table per event.
PAGE_BYTES = 32
# No turn slot: the map has no still event that turns around.
TURN_NONE = 0xFFFF
# A leader candidate: id, palette, **its fifteen colors** and twelve 24-bit
# pointers to its poses. The colors go inside the table and not in a separate
# block because there are few actors per map and that way the ROM uploads them
# with one DMA from where it already is; see `pick_hero_graphic`.
#
# They are there because leaders **share a CGRAM slot**: one leads at a time,
# so reserving a palette for each is having it taken by someone who isn't on
# screen. The ROM uploads the leader's when the party changes and when the map
# loads. See `drawable_npcs`.
ACTOR_COLORS = 2 * OBJ_COLORS
ACTOR_BYTES = 2 + ACTOR_COLORS + 3 * 12


# How many distinct graphics command 34 can ask for in a map. The table is
# copied to RAM when the map loads, like the NPC one, so the cap costs bytes
# from bank 0's eight kilobytes —two per graphic— and can't be generous just
# because. **The map that asks for the most in the whole game asks for six**,
# measured over the 328; eight leaves two of slack and is sixteen bytes. The
# converter stops if any map goes over, so it can't fall short silently.
ROUTE_GFX_MAX = 8


def map_fields(map_info):
    """The values of a map's record, in the order they are emitted."""
    tilemap, above, sprite = map_info["tilemap"], map_info["above"], map_info["sprite"]
    collision, layout = map_info["collision"], map_info["layout"]
    height, width = len(tilemap), len(tilemap[0])
    return {
        "MAP_BW": collision[3], "MAP_BH": collision[4],
        "CAM_MAX_X": max(0, width * CELL - 256),
        "CAM_MAX_Y": max(0, height * CELL - 224),
        "HERO_MAX_X": width * CELL - 16, "HERO_MAX_Y": height * CELL - 16,
        "HERO_START_X": collision[1] * 16, "HERO_START_Y": collision[2] * 16,
        "VRAM_TILES": layout["tiles"][0], "VRAM_MAP": layout["mapa"][0],
        "VRAM_SPRITE": layout["sprites"][0],
        "VRAM_WINDOW": layout.get("ventana", (0, 0))[0],
        "VRAM_WINDOW_MAP": layout.get("ventana_map", (0, 0))[0],
        "MAP_TILES": len(map_info["tiles"]) // BYTES_PER_TILE,
        "MAP_CGRAM": len(map_info["cram"]) // 2,
        "ABOVE_TILES": len(above[0]) // 32,
        "ABOVE_CGRAM": len(above[1]) // 2,
        "SPRITE_TILES": len(sprite[0]) // 32 if sprite else 0,
        # One more than the colors: sprite index 0 is transparent and also
        # takes its place in CGRAM.
        "SPRITE_CGRAM": COLORS_PER_PALETTE * len(sprite[1]) if sprite else 0,
        "NPC_COUNT": len(sprite[3]) if sprite else 0,
        "EV_COUNT": len(map_info["ev_pos"]) // EV_STRIDE,
        "TIMER_BASE": sprite[5] if sprite else 0,
        "RAIN_BASE": sprite[10] if sprite else 0,
        "ACTOR_COUNT": len(sprite[4]) if sprite else 0,
        "PAGE_COUNT": len(map_info["pages"]),
        "ROUTE_GRAPHIC_COUNT": len(sprite[9]) if sprite else 0,
        "OBSEL_VALUE": 0x20 | (layout["sprites"][0] // 0x2000),
        "BG12NBA_VALUE": ((layout["encima"][0] // 0x1000) << 4)
                         | (layout["tiles"][0] // 0x1000),
        "ABOVE_FIRST": above[3] * COLORS_PER_PALETTE,
        "TIMER_PAL": (sprite[6] if sprite and sprite[6] is not None else 0),
        "RAIN_PAL": sprite[11] if sprite else 0,
        "TURN_TILE4": (sprite[12] // 4 if sprite and sprite[12] != TURN_NONE
                       else 0xFF),
        "TERRAIN_OUTSIDE": map_info["terreno_fuera"],
        "TERRAIN_PLANE": terrain_plane(map_info),
    }


def offsets():
    """The names of the record's fields, so that tools/runtime/ doesn't repeat
    them.

    The converter emitting the offsets and the ROM only naming them is what
    makes it impossible for them to get out of sync: if a field is added here,
    there is no number to update there.
    """
    out = ["; Where each field falls inside a map's record."]
    used = 0
    for name, _ in MAP_SCALARS:
        out.append("M_%-14s = %d" % (name, used))
        used += 2
    for name, _ in MAP_BYTES:
        out.append("M_%-14s = %d" % (name, used))
        used += 1
    for number, name in enumerate(MAP_POINTERS):
        out.append("M_PTR_%-10s = %d"
                   % (name.upper(), MAP_PTR_BASE + number * MAP_PTR_STEP))
    return "\n".join(out)


def map_table(maps, labels):
    """The table the ROM walks to know what to load.

    `labels` says, per map, which block each pointer points to. This didn't
    exist before and the name was rebuilt here with `"%s_%d" % (nombre,
    numero)`, that is with the same computation that had emitted it: two
    places computing the same name and no way for a block to belong to more
    than one map.
    """
    out = ['.segment "RODATA"',
           "; The map table: one record of %d bytes per map, with everything"
           % MAP_STRIDE,
           "; the ROM needs to load it. The pointers are 24 bits because the",
           "; data lives spread over all the banks.",
           ";",
           "; **It lives in RODATA and is read with `lda f:map_table + campo, x`.**",
           "; It is 144 bytes per map, and in bank 0 —where the table has to be",
           "; if it is walked with the data bank register— that was enough for",
           "; fourteen maps and no more: with the whole of Lashe City it is 33",
           "; and the bank went over by 3739 bytes. It is the third table that",
           "; moves for the same reason; the price is one byte per instruction",
           "; and that the two uses with Y had to switch to X, because long",
           "; absolute indexed addressing only exists with X.",
           ";",
           "; **Whole within one bank**, which is what `.block` asks for. In",
           "; LoROM what follows $03FFFF isn't bank 4's ROM but RAM, and the",
           "; first version of this landed at $03FFB1: the 144 bytes of the only",
           "; record were split in half and map 5 started black. The other maps",
           "; of the suite didn't see it because their table landed somewhere",
           "; else, which is exactly the kind of error that shows up when adding",
           "; a byte anywhere else.",
           ".block %d" % (MAP_STRIDE * len(maps)),
           "map_table:"]
    for number, map_info in enumerate(maps):
        fields = map_fields(map_info)
        # `mapas_de` in rom/pruebas/arnes/consola.py reads the table order
        # from this line with a regex that expects "map".
        out.append("    ; --- %d: map %d %r ---" % (number, map_info["id"],
                                                     map_info["nombre"]))
        used = 0
        for name, comment in MAP_SCALARS:
            out.append("    .word %-6d ; +%-3d %s%s"
                       % (fields[name], used, name,
                          "  " + comment if comment else ""))
            used += 2
        for name, comment in MAP_BYTES:
            out.append("    .byte $%02X    ; +%-3d %s  %s"
                       % (fields[name], used, name, comment))
            used += 1
        padding = MAP_PTR_BASE - used
        # Without padding the line doesn't go: a `.byte` without operands is an
        # error for `ca65`.
        if padding:
            out.append("    .byte %s ; +%d  padding up to the pointers"
                       % (",".join(["$00"] * padding), used))
        used += padding
        for name in MAP_POINTERS:
            label = labels[number][name]
            out.append("    .byte <(%s), >(%s), ^(%s), $00 ; +%d  %s"
                       % (label, label, label, used, name))
            used += MAP_PTR_STEP
        assert used <= MAP_STRIDE, used
        if used < MAP_STRIDE:
            out.append("    .byte " + ",".join(["$00"] * (MAP_STRIDE - used)))
    # And each map's RM2k id, by index: `MemorizeLocation` writes it into a
    # variable and `RecallToLocation` looks it up, because in variables the map
    # is RM2k's —any other page reads them—. It goes separately and not as a
    # record scalar because the record is at exactly its 128. See
    # `op_location`.
    out += ["",
            "; Each map's RM2k id, in the order of `map_table`.",
            ".block %d" % (2 * len(maps)),
            "map_rm2k:",
            "    .word " + ", ".join(str(m["id"]) for m in maps)]
    return "\n".join(out)


# The ChipSet animation block: the drawings, one after the other and in VRAM
# order —water 0, 1, 2; animated 0 to 3—, with no header.
#
# Where each one lands and which VRAM address it goes to isn't inside the
# block but in `anim_table`, one entry per map. It is so the ROM doesn't have
# to read anything from the cartridge to animate: the direct page is full, so
# an `lda [puntero], y` had nowhere to live, and the alternative —bringing the
# header into WRAM by DMA— asked for forty bytes of BSS that weren't there
# either. With the table built here, the ROM indexes and fires the DMA.
ANIM_STRIDE = 16
ANIM_FAM_STRIDE = ANIM_STRIDE // 2


def anim_bytes(animation):
    """The map's drawings, one after the other. Empty if nothing animates."""
    data = bytearray()
    for family, _ in FAMILIES:
        run = animation.get(family)
        if run:
            for drawing in run["dibujos"]:
                data += drawing
    return bytes(data)


def anim_table(maps):
    """One entry per map, with both runs already resolved.

    Per family, and in the order the ROM looks at them:

        +0 word  VRAM address, in words
        +2 word  offset of drawing 0 inside the block
        +4 word  how many bytes a drawing is
        +6 byte  how many tiles it is; 0 if this family doesn't animate in this map
        +7 byte  padding, so each family's entry is eight

    The VRAM address comes from here and not from a computation on the console
    because both halves are here: the map's VRAM layout and which tile of its
    bank the run starts at.

    The padding of the second family —byte +15 of the entry— carries **whether
    the map has some still event with continuous animation**. It goes here
    because it is the same as the rest: something per map that the ROM looks
    at once per frame and that no longer fit in the map record. Without it,
    `animate_still` would have to walk the forty NPC rows in every map.
    """
    out = ['.segment "RODATA"',
           "; The ChipSet animation, one entry of %d bytes per map."
           % ANIM_STRIDE,
           # `rom/src/` and not `tools/runtime/`, on purpose: it goes into the
           # `.inc`, and what is emitted isn't touched yet. See
           # las-herramientas-se-separan-de-abl.md.
           "; See `anim_table` in tools/port/snes_convert.py and `anim_flush` in rom/src/chipset_animation.s.",
           ";",
           "; **It lives in RODATA and is read with `lda f:anim_table + campo, x`**,",
           "; for the same reason as `map_table`: it is 16 bytes per map, and",
           "; with the maps the tests ask for bank 0 went over by 361. Whole",
           "; within one bank, because what follows $xxFFFF isn't the next one's ROM.",
           ".block %d" % (ANIM_STRIDE * len(maps)),
           "anim_table:"]
    for map_info in maps:
        animation = map_info["resumen"]["animacion"]
        out.append("    ; --- map %d %r ---" % (map_info["id"], map_info["nombre"]))
        offset = 0
        for family, count in FAMILIES:
            run = animation.get(family)
            tiles = run["tiles"] if run else 0
            vram = (map_info["layout"]["tiles"][0]
                    + (run["base"] if run else 0) * BYTES_PER_TILE // 2)
            out.append("    .word %-6d ; VRAM of %s" % (vram, family))
            out.append("    .word %-6d ; drawing 0, inside the block"
                       % offset)
            out.append("    .word %-6d ; bytes per drawing"
                       % (tiles * BYTES_PER_TILE))
            padding = 0
            if family == FAMILIES[-1][0]:
                padding = 1 if any(n.get("animates")
                                   for n in (map_info["sprite"][3]
                                             if map_info["sprite"] else ())) else 0
            out.append("    .byte %d, %d   ; %d tile(s)%s"
                       % (tiles, padding, tiles,
                          ", and the map has still events that animate"
                          if padding else ""))
            offset += tiles * BYTES_PER_TILE * count
    return "\n".join(out)


def page_table(map_info, number, evcode):
    """The map's event pages, with the pointer to their code.

    `evcode` is the **label** of the code block, which can no longer be
    rebuilt here: two maps whose events compile to the same bytes share the
    block and the label doesn't carry this map's number. Rebuilding it is what
    it did —`"evcode_%d" % numero`— and when deduplication was turned on the
    suite caught it right away: `varios` didn't assemble because it named an
    `evcode_2` that no longer existed.

    It doesn't go through `block()` because its pointers are symbolic: they
    point inside the code block, which the linker places. But it **is
    declared** with `.block`: the ROM walks it with `[page_ptr], y`, and a
    table that crosses a bank continues at `$03:0000`, which in LoROM isn't
    ROM but the WRAM mirror. Without the declaration it really happened: when
    map 2's sprites grew with the events drawn with a tile, the table ended up
    straddling `$02FFFF`, the ROM read garbage instead of the last pages
    —among them the test one— and the shake at the edge of the map never
    started. The suite caught it in pixels without saying why; the
    emulator's RAM said it.
    """
    out = [".block %d" % (PAGE_BYTES * len(map_info["pages"])),
           "pages_%d:" % number]
    # Which events have some page with its own route: the ROM's refresh only
    # looks at the pages of those, and doesn't spend a single read on the rest.
    with_route = {p["event"] for p in map_info["pages"] if p.get("ruta_propia")}
    # And which ones change graphic with the page: the refresh also looks at
    # those, bit 5, and copies to the row what the active page draws.
    changing = map_info.get("cambian", set())
    # And which ones only appear and disappear with it: the ones that walk.
    # They go by the **same** bit 5, because none is left free in +13 —with an
    # own route the five low ones are the route's flags, and 4 is "the
    # animation continues while still"—. The one telling them apart is the
    # ROM, which already knows whether the row walks: `npc_buf + 9` holds
    # NPC_STILL or the bank of its twelve poses. See `page_graphic` in
    # tools/runtime/event_pages.s.
    appear = map_info.get("aparecen", set())
    # And which ones have some automatic page that compiled: bit 7. The ROM's
    # refresh has to know whether an event's active page is automatic —that
    # is where what starts on its own comes from— and with this it saves
    # reading the pages of the events that can never be. It is the same trick
    # as bit 6.
    #
    # The **parallel** ones go by this same bit, and not by one of their own:
    # none is left free in +13. The bit means "look at this event's pages in
    # the refresh", which is what both need; which is automatic and which is
    # parallel is said by the trigger of the one that wins. Without this,
    # `pick_pages` doesn't even note which one is active —it filters by
    # $E0— and `parallel_tick` would have nowhere to get its code from.
    with_autostart = {p["event"] for p in map_info["pages"]
                      if p["trigger"] in (events.TRIGGER_AUTOSTART,
                                          events.TRIGGER_PARALLEL) and p["codigo"]}
    for page in map_info["pages"]:
        if page["codigo"]:
            dest = "%s + %d" % (evcode, page["offset"])
            pointer = "<(%s), >(%s), ^(%s)" % (dest, dest, dest)
        else:
            pointer = "$00, $00, $00"   # no code: nothing to run
        out.append("    .word %-4d ; +0  the event it belongs to"
                   % page["event"])
        out.append("    .byte %-4d ; +2  its page number" % page["pagina"])
        out.append("    .byte %-4d ; +3  what triggers it" % page["trigger"])
        out.append("    .word %-4d ; +4  switch it asks for, or 0" % page["switch_a"])
        out.append("    .word %-4d ; +6  the second, or 0" % page["switch_b"])
        out.append("    .byte %s ; +8  its code" % pointer)
        out.append("    .byte %-4d ; +11 the actor it asks for in the party, or 0"
                   % page["actor"])
        out.append("    .byte %-4d ; +12 its layer: 1 is the hero's, the one "
                   "that blocks its way" % page["capa"])
        own = page.get("ruta_propia")
        if own:
            # The page's own route, the one it walks by itself: see `own`
            # in the compiler's `route.rs`. The flags: bit 0 it has one, 1 it
            # repeats, 2 it skips what is blocked, 3 it always faces the same
            # way, 4 the animation continues while still.
            flags = (1 | (2 if own["repite"] else 0)
                     | (4 if own["saltable"] else 0)
                     | (8 if own["dir_fija"] else 0)
                     | (16 if own["anim_continues"] else 0) | 64
                     | (32 if page["event"] in changing
                                 or page["event"] in appear else 0)
                     | (128 if page["event"] in with_autostart else 0))
            dest = "%s + %d" % (evcode, page["ruta_offset"])
            out.append("    .byte %-4d ; +13 the flags of its own route"
                       % flags)
            out.append("    .byte %-4d ; +14 its frequency" % own["frecuencia"])
            out.append("    .byte %-4d ; +15 and its speed" % own["speed"])
            out.append("    .byte <(%s), >(%s), ^(%s) ; +16 its commands"
                       % (dest, dest, dest))
            out.append("    .byte %-4d ; +19 how many" % len(own["ordenes"]))
        else:
            out.append("    .byte %-4d ; +13 no own route; bit 6 says whether "
                       "another page of the event has one, 5 whether the "
                       "graphic follows the page, 7 whether the event has some "
                       "automatic one"
                       % ((64 if page["event"] in with_route else 0)
                          | (32 if page["event"] in changing
                                   or page["event"] in appear else 0)
                          | (128 if page["event"] in with_autostart else 0)))
            out.append("    .byte %-4d ; +14 its frequency" % page["frecuencia"])
            out.append("    .byte %-4d ; +15 and its speed, that of a route "
                       "forced on the event" % page["speed"])
            out.append("    .byte 0,0,0,0")
        # +20..+23: what the page draws, for the events that change graphic:
        # the tile, the attributes with the palette and the priority of its
        # layer, the pose with bit 7 set if there is a graphic, and the
        # passage bits of its tile or $FF. It is what the refresh copies to
        # the row.
        oam = page.get("oam")
        if oam is None:
            out.append("    .byte $00, $00, $00, $FF ; +20 no graphic")
        else:
            out.append("    .byte $%02X, $%02X, $%02X, $%02X ; +20 its graphic: "
                       "tile, attributes, pose, passage" % oam)
        # +24..+27: the variable condition: the slot or $FF, how it is
        # compared —==, >=, <=, >, <, !=— and against what, signed. It is what
        # `conditions_ok` passes to `compare_var`.
        variable = page.get("variable")
        if variable is None:
            out.append("    .byte $FF, 0 ; +24 no variable condition")
            out.append("    .word 0")
        else:
            slot, comparison, against = variable
            out.append("    .byte %d, %d ; +24 the variable it asks for and the "
                       "comparison" % (slot, comparison))
            out.append("    .word %d ; +26 against what" % (against & 0xFFFF))
        # +28: the item it asks to have, or 0: `conditions_ok` looks at its
        # count in `FAR_ITEMS`.
        out.append("    .word %-4d ; +28 the item it asks for, or 0" % page["item"])
        # +30 and +31: the turn toward the hero. Which entry of `npc_poses`
        # the poses of its graphic are in, or $FF if the page doesn't turn,
        # and its pose. When triggered, the ROM uploads the one facing the
        # hero; on a refresh, a change to a page that doesn't turn or has
        # another graphic undoes the turn. See TURN in events.py.
        graphic = page.get("grafico")
        k = (map_info.get("giro_k", {}).get(tuple(graphic[:2]))
             if page.get("gira") and graphic and page["event"] in
             map_info.get("giran", ()) else None)
        out.append("    .byte $%02X, %d ; +30 the turn: its poses and its pose"
                   % (0xFF if k is None else k, graphic[2] if k is not None else 0))
        assert PAGE_BYTES == 32
    if not map_info["pages"]:
        out.append("    .byte $00")     # a label can't be left empty
    return "\n".join(out)


def terrain_plane(map_info):
    """The terrain the whole map has, or 0 if it has more than one.

    0 isn't a terrain: RM2k's are indices into `Data.terrains` and start at 1,
    so it serves as "there is a table here" without spending another field. A
    map with terrain 0 —which doesn't exist— falls into the table branch,
    which answers the same.
    """
    unique = set(map_info["terreno"])
    return unique.pop() if len(unique) == 1 else 0


def map_terrain(map_info):
    return (bytes([terrain_plane(map_info)]) if terrain_plane(map_info)
            else bytes(map_info["terreno"]))


def map_data(map_info, number, global_index, materials):
    """A map's data blocks, with the number attached to each label.

    `global_index` are the labels of the twelve poses of each (CharSet,
    index) **as this map quantized it**: see `pose_bank`, and the pose
    split in `emit`.
    """
    above, sprite = map_info["above"], map_info["sprite"]
    pairs = [
        ("map_tiles", map_info["tiles"]),
        ("map_cgram", map_info["cram"]),
        ("above_tiles", above[0]),
        ("above_cgram", above[1]),
        ("sprite_tiles", sprite[0] if sprite else b""),
        ("sprite_cgram", sprite_colors_bytes(sprite)),
        ("map_blocks", map_info["bloques"]),
        ("block_pass", map_info["pass"]),
        # The terrain per block. A map whose terrain is the same everywhere
        # —the 328 of this game, which have it at 1— emits **one byte** and
        # `TERRENO_PLANO` says which: the whole table would be about eight
        # kilobytes of nothing spread over the forty maps. The byte is
        # deduplicated by `materials`, so all flat maps with the same terrain
        # share the same one.
        ("block_terrain", map_terrain(map_info)),
        ("npc_table", npc_bytes(sprite[3]) if sprite else b""),
        # Two bytes per graphic of command 34: its entry in `npc_poses` —or
        # $FF, which is hiding— and its palette. See `Graphics` in events.py.
        ("route_graphic",
         bytes(b for pair in (sprite[9] if sprite else []) for b in pair)),
        ("ev_pos", map_info["ev_pos"]),
        ("evcode", map_info["evcode"]),
        ("anim_tiles", map_info["anim"]),
    ]
    labels, out = {}, []
    for name, data in pairs:
        if name in COMPRESSED_KINDS:
            labels[name], text = materials.store_compressed(name, data)
        else:
            labels[name], text = materials.store(name, data)
        if text:
            out.append(text)
    # The two tables of pointers to the ROM's poses: that of the NPCs that
    # walk and that of the leader candidates.
    animated = sprite[7] if sprite else []
    out.append(npc_poses_asm(number, animated, global_index))
    out.append(actor_table_asm(number, sprite[4] if sprite else [],
                               animated, global_index))
    # The grid, in its two streams: see `lz2_grid`. Whole within one bank,
    # like everything compressed, because the decompressor doesn't cross.
    labels["map_cells"], text = materials.store_compressed(
        "map_cells", map_info["celdas"])
    if text:
        out.append(text)
    out.append(page_table(map_info, number, labels["evcode"]))
    # The three that aren't shared are the ones that carry **symbolic
    # pointers** inside —to the ROM's poses, to the events' code—: their bytes
    # are set by the linker, so here there is no content to compare them by.
    for name in ("npc_poses", "actor_table", "pages"):
        labels[name] = "%s_%d" % (name, number)
    return "\n".join(out), labels


def sprite_colors_bytes(sprite):
    """The sprite palettes as CGRAM bytes.

    Each one is 16 entries: index 0 is transparent and isn't drawn, but it
    still takes its place, and the leftover ones are padded so that the next
    starts where the hardware expects it.
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


# An event in the position table: x and y in cells, both 16 bits because
# there are maps 500 cells wide.
EV_STRIDE = 4
# How many events the RAM holds. The most populated map of this game has 114
# —measured over the 328—; the converter stops if any goes over, so the number
# can't fall short silently. Each one costs six bytes of RAM between
# `ev_pos_buf` and `pick_by_ev`.
EV_MAX = 120
# How many forced routes can be running at once on events. The page that sends
# the most walking in this game moves four distinct events, and a route
# survives the end of its page, so there can be another running on top. Eight
# gives margin and costs 88 bytes of RAM.
ROUTE_EV_MAX = 12
# How many flashes can be running at once. This game's pages chain them one at
# a time —almost all wait for it to finish— so four is plenty; the converter
# can't check it because it depends on what runs when, and a missing slot
# makes the flash not show.
FLASH_MAX = 4
# How many events with a parallel page there can be at once in a map. It was
# 12 because the most loaded one was 8 —Lashe City— with eight: the four cars
# and the four that relocate them.
#
# **With `ChangeSpriteAssociation` done it is 40**, and a single map sets it:
# each obstacle of the car chase is an event with a parallel page that
# compares the car's cell with its own, and maps 49, 52 and 54 have forty each.
# They didn't count before because none of those pages compiled. Measured over
# the 328 maps with everything that is done today; the converter stops if any
# goes over.
#
# What it costs: eight bytes of `FAR_PAIR_LIST` per slot —far RAM, not the
# BSS; see `PAIR_LIST_BYTES` in `tools/runtime/far_ram.s`, which besides the
# event stores the page the refresh chose for it— and **one interpreter pass
# per frame for each one**. It is the second that has to be watched if the
# race gets slow: the first is gone, because the page stopped being resolved
# every frame.
#
# 48 times eight is 384 bytes, and from `FAR_PAIR_LIST` to `FAR_RANDOM` there
# are 508.
PARALLEL_MAX = 48
# An NPC in the ROM's RAM. It was eight bytes; the four extra are for the ones
# that walk: which event they correspond to and where their pose table is.
#
#   +0 x, +2 y   in pixels
#   +4 key       layer and Y, which is what `build_oam` compares
#   +6 tile, +7 attributes
#   +8 event     its index in the event table, or $FF if it doesn't walk
#   +9 poses     its entry in `npc_poses`, or $FF
#   +10 dir      where its page faces, for the first pose of a route
#   +11 padding, so that the slot is indexed with two shifts
NPC_STRIDE = 16
NPC_STILL = 0xFF        # in +9: this NPC doesn't walk

# The table of NPCs of the loaded map is copied to RAM, because build_oam walks
# it with an index and that addresses the data bank. The ceiling above is set
# by OAM: 128 objects fit and one is the hero, so no map can **show** more
# than 127.
#
# The number isn't that since 2026-09-06, and not by choice: the row is
# sixteen bytes, so the cap takes two kilobytes of the eight bank 0 of RAM
# has, and the RAM ran out —see `STACK` in tools/rm2k-snes/cartridge/src/banks.rs—. **The
# map with the most rows in the whole game has 99**, measured over the 328, so
# 104 leaves five of headroom and gives back 368 bytes. It can't fall short
# silently: the converter stops if any map goes over.
NPC_MAX = 104


def drawing_order(npc):
    """What an event is sorted by to draw it, from front to back.

    RM2k sorts by **highest Y, then highest X, and then highest id**. It comes
    from `Game_Character::GetScreenZ` in easyrpg-player, which builds a 64-bit
    Z with the layer on top, the Y, the X and the id at the bottom, with the
    comment right there:

        The rendering order of characters is: Highest Y, Highest X, Highest ID

    The two tie-breakers were missing. With still NPCs it barely shows —you
    need two on the same row and one covering the other— but as soon as one
    walks it changes row all the time and ties with anybody.

    The table index stands for the id: the events come sorted by id, so the
    order is the same.
    """
    return (npc["layer"], npc["y"], npc["x"], npc["event"])


def sort_key(layer, y):
    """How RM2k sorts: first the layer and only then the Y.

    A "below" event stays below the hero even if it is further forward on the
    screen, and an "above" one always covers it. Putting the layer in the high
    bits makes a single 16-bit comparison decide both things.
    """
    return (layer << 12) | (y & 0x0FFF)


def ev_pos_bytes(game_map):
    """Where each event of the map starts, in cells and in index order.

    The **whole** map goes and not only the events with a graphic: a forced
    route can land on an invisible one, and in fact half of this game's do.
    The ROM copies it to RAM when loading the map because a route changes it,
    and the next route on the same event starts from where it was left: there
    is a page that sends the same one walking nine times.

    The order is the table index, which is what the bytecode carries. **It
    isn't the RM2k id**: 39 maps have gaps in the numbering, and translating
    is exactly what `events.MapEvents` does.
    """
    if len(game_map.events) > EV_MAX:
        raise SystemExit("the map has %d events and the ROM's RAM holds %d"
                         % (len(game_map.events), EV_MAX))
    out = bytearray()
    for event in game_map.events:
        out += event.x.to_bytes(2, "little")
        out += event.y.to_bytes(2, "little")
    return bytes(out)


def npc_bytes(table):
    """The NPC table: NPC_STRIDE bytes for each one.

    Position on the map, the key it is sorted against the hero by, which
    sprite tile it gets, and the attribute byte already built with its
    palette. The ROM only subtracts the camera and copies it to OAM.

    The ones that walk also carry which event they correspond to and where
    their table of twelve poses is, which is what lets the ROM change their
    tile while they take a step.
    """
    out = bytearray()
    for npc in table:
        out += npc["x"].to_bytes(2, "little")
        out += npc["y"].to_bytes(2, "little")
        # The key goes with the Y in pixels, which is how the ROM computes it
        # from the hero's position. With the Y in cells, the hero's would
        # always be greater and it would always stay in front of everyone.
        #
        # And `npc["y"]` **is already in pixels**: `npc_table` converts it.
        # Multiplying it by 16 again —which is what it did here— gave a key
        # sixteen times larger than the hero's, and since `sort_key` clips to
        # twelve bits, on top of that it wrapped around. The comparison didn't
        # see it because the order **between** NPCs is fixed by the
        # converter's `sorted` and this key only decides where the hero goes
        # in: the hero had to step on an NPC for it to show, and no test did.
        out += sort_key(npc["layer"], npc["y"]).to_bytes(2, "little")
        out.append(npc["tile"] & 0xFF)
        # vhoopppN: the priority is bits 5 and 4, so the value goes shifted
        # four places. The events marked "above" go at priority 2, which is
        # the only thing left above BG2 1; the rest share priority 1 with the
        # hero, and since that layer covers them, they walk underneath.
        priority = (OBJ_PRIORITY_ABOVE
                    if npc["layer"] == rm2k.LAYER_ABOVE
                    else OBJ_PRIORITY)
        out.append(priority | ((npc["palette"] & 0x07) << 1)
                   | ((npc["tile"] >> 8) & 0x01))
        # The event's index goes **always**, even if the NPC doesn't walk: it
        # is the last tie-breaker of the drawing order, and it applies to all.
        # What sets the walking ones apart is the pose table.
        out.append(npc["event"])
        out.append(NPC_STILL if npc["poses"] is None else npc["poses"])
        # Where its page faces. A forced route that hasn't given any turning
        # command yet leaves it facing here, which is where the first pose
        # drawn comes from.
        out.append(npc["dir"])
        out.append(0)               # padding
        # +12: the pose that is in VRAM, which on loading is its page's. The
        # ROM compares it with the one it wants to draw and uploads the new
        # one if it differs.
        out.append(npc["pose"])
        # +13: its page's speed, for a forced route on it, and in bit 7
        # whether it is a still one with continuous animation. They go
        # together because the row has no free byte —+11 is used by the
        # jump— and because both are read by the same computation: how many
        # frames between column changes comes from the speed. See
        # `animate_still` in tools/runtime/animated_stills.s.
        out.append(npc["speed"] | (0x80 if npc.get("animates") else 0))
        # +14: whether it is drawn. An event whose active page has no graphic
        # is in the table hidden, to appear when another page wins.
        out.append(1 if npc["visible"] else 0)
        # +15: the passage bits its tile imposes on the cell, or $FF: see
        # `rm2k.event_tile_passability`. The refresh redoes both.
        out.append(0xFF if npc["tile_pass"] is None else npc["tile_pass"])
    assert len(out) == NPC_STRIDE * len(table)
    return bytes(out)


def npc_poses_asm(number, animated, global_index):
    """The pointers to the twelve poses of each character that changes pose.

    One entry per animated character —`k`, the same index the NPC's row
    carries in +9 and the actor in its table— and in each one twelve 24-bit
    pointers to its poses, `pose_N`. They are symbolic because they point to
    blocks the linker places, like the pages' ones; two equal poses are the
    same block.
    """
    out = [".block %d" % (3 * SPRITE_POSES * max(1, len(animated))),
           "npc_poses_%d:" % number]
    for pair in animated:
        for pose in range(SPRITE_POSES):
            out.append("    .byte " + pointer(global_index[pair][pose]))
    if not animated:
        out.append("    .byte $00")     # a label can't be left empty
    return "\n".join(out)


def actor_table_asm(number, actors, animated, global_index):
    """The leader candidates: id, palette, and the pointer to each of their
    poses.

    ACTOR_BYTES per actor. The ROM walks the table looking for the id of the
    party's first; there are two or three entries, so searching linearly is
    cheaper than indexing by id, which would take 256 gaps. An actor without
    a graphic carries twelve pointers at $FFFFFF, which is the sentinel
    `place_hero` looks at.
    """
    out = [".block %d" % (ACTOR_BYTES * max(1, len(actors))),
           "actor_table_%d:" % number]
    for actor, palette, k, colors in actors:
        out.append("    .byte $%02X, $%02X" % (actor & 0xFF, palette & 0x07))
        # Its fifteen colors, in the order its poses index them. An actor
        # without a graphic carries them at zero and the ROM doesn't upload
        # them: it isn't drawn.
        words = list(colors) + [0] * (OBJ_COLORS - len(colors))
        out.append("    .byte " + ",".join(
            "$%02X,$%02X" % (w & 0xFF, w >> 8) for w in words))
        for pose in range(SPRITE_POSES):
            if k is None:
                out.append("    .byte $FF, $FF, $FF")
            else:
                out.append("    .byte " + pointer(
                    global_index[animated[k]][pose]))
    if not actors:
        out.append("    .byte $00")
    return "\n".join(out)

#!/usr/bin/env python3
"""What things mean in RPG Maker 2000, for the tests: where one can walk,
what a page draws and on which layer, a cell's terrain.

It was `rpgmaker/rm2k.py`, the converter's copy of these rules, until
the converter moved to Rust on 2026-10-02: the rules are `rm2k-rules`'
now, and what is left here is what A Blurred Line's tests compute on their
own to know what to expect —the walk planner, the terrain of a cell, the
passability a fork must keep—. It is the tests' oracle, written apart from
the converter on purpose: a rule wrong in both would compare equal.

What these rules say is checked against liblcf and easyrpg-player; none of
these numbers was written from memory.
"""

TILE = 16


# --- collision ---------------------------------------------------------------
#
# Each RM2k tile has four bits that say from which sides it can be crossed.
# Moving from a tile to the next one asks both for permission: the origin has
# to let you out on that side and the destination let you in on the opposite
# one.
#
# The upper layer overrides the lower one, unless it has the "Above" bit
# —which means "drawn above the hero", that is, decoration— in which case the
# lower one decides. Port of EasyRPG's Game_Map::IsPassableTile.

PASS_DOWN = 0x01
PASS_LEFT = 0x02
PASS_RIGHT = 0x04
PASS_UP = 0x08
PASS_ABOVE = 0x10
PASS_WALL = 0x20
PASS_ALL = PASS_DOWN | PASS_LEFT | PASS_RIGHT | PASS_UP

# The combinations of a terrain autotile that are the face of a wall. With
# the Wall bit set, those can always be crossed.
WALL_FACES = frozenset(list(range(20, 24)) + list(range(33, 38))
                       + [42, 43, 45, 46])


def lower_passable(flags, raw, bit):
    if 4000 <= raw < 5000 and (flags[raw] & PASS_WALL):
        if (raw - 4000) % 50 in WALL_FACES:
            return True
    return bool(flags[raw] & bit)


def cell_passability(flags, lower, upper):
    """A cell's four direction bits, given its two tiles."""
    byte = 0
    for bit in (PASS_DOWN, PASS_LEFT, PASS_RIGHT, PASS_UP):
        if not (flags[upper] & bit):
            continue                       # the upper layer blocks
        if not (flags[upper] & PASS_ABOVE):
            byte |= bit                    # the upper layer decides, and allows
        elif lower_passable(flags, lower, bit):
            byte |= bit                    # it is decoration: the lower decides
    return byte


def passability_map(game_map, flags):
    """One byte per map tile with the four direction bits already resolved.

    All of RM2k's logic is resolved here; the ROM only looks at the table.
    """
    result = bytearray(game_map.width * game_map.height)
    for i in range(len(result)):
        result[i] = cell_passability(flags, game_map.lower_layer[i],
                                     game_map.upper_layer[i])
    return bytes(result)


LAYER_BELOW = 0
LAYER_SAME = 1     # the hero's, and the only one that collides with him
LAYER_ABOVE = 2


# An event without a CharSet is drawn with a tile from the chipset's upper
# page: that is how doors, chests and a good part of the decoration are
# made. For the rest of the program it is one more CharSet, with this made-up
# name, which carries the chipset and the tile's index; `rm2k-render
# charset` draws its image; `wally` asks for it (`sheets.rs`).
TILE_PREFIX = "@tile:"


BAKED_SUFFIX = "~horneado"


def baked_parts(name):
    """(base name, (map, x, y)) of a baked CharSet, or (name, None).

    Everything that looks at *which* graphic it is —the tile's passability,
    which is a tile and which a real CharSet— has to ask about the base: the
    suffix carries where it stands, not what it draws.
    """
    base, mark, rest = name.partition(BAKED_SUFFIX + ":")
    if not mark:
        return name, None
    return base, tuple(int(n) for n in rest.split(":"))


def unbaked(name):
    return baked_parts(name)[0]


def tile_name(chipset, index):
    return "%s%s:%d" % (TILE_PREFIX, chipset, index)


def page_graphic(page, chipset):
    """(CharSet, index, pose) of what the page draws, or None if nothing.

    Those drawn with a chipset tile go with a made-up CharSet —see
    `tile_name`—, as long as whoever loaded the map set
    `chipset_filename` on it; tile 0 is "no graphic".
    """
    if not page.character_name and (page.character_index == 0
                                    or chipset is None):
        return None
    # The walk is four phases over three columns: the middle one goes twice,
    # so the fourth draws the same as the second.
    column = 1 if page.character_pattern == 3 else page.character_pattern
    return (page.character_name or tile_name(chipset, page.character_index),
            page.character_index if page.character_name else 0,
            page.character_direction * 3 + column)


def event_tile_passability(game_map, charset, layer):
    """The four passage bits an event drawn with `charset` on layer `layer`
    imposes on its cell, or None if it imposes nothing.

    It is `Game_Map::IsPassableTile`'s rule: an event on the lower layer with
    a tile graphic replaces the terrain's passability with its tile's, unless
    the tile is one of those that go above. That is how a door "opens" in
    this game: the cell is wall, and with the switch on the page shows the
    rubble tile, which can be stepped on. The bits come from the same table
    as the map's upper layer, which whoever loaded the map leaves in
    `passability_table`.
    """
    flags = getattr(game_map, "passability_table", None)
    base = unbaked(charset)
    if flags is None or layer != LAYER_BELOW \
            or not base.startswith(TILE_PREFIX):
        return None
    value = flags[UPPER_BASE + int(base.rsplit(":", 1)[1])]
    if value & PASS_ABOVE:
        return None
    return value & PASS_ALL


UPPER_BASE = 10000      # the first tile of the upper layer, in the map and in the table
# And the first of the loose tiles of the lower layer: the format's "block
# E", the 144 the editor's palette shows below the autotiles. They are the two
# ranges `TileSubstitution` speaks in, numbering from the first of each. The
# autotiles are left out: not even RM2k substitutes them.
LOWER_BASE = 5000
TILES_PER_LAYER = 144

# The format's six tile id blocks, as in easyrpg's `map_data.h`: (first id,
# how many, how much each one takes, first index). The **index** is what the
# ChipSet's terrain table and passability table are read with, and it is not
# the id: autotiles take 50 or 1000 ids each —the edge combinations— and a
# single index.
CHIP_BLOCKS = ((0, 2, 1000, 0), (2000, 1, 1000, 2), (3000, 3, 50, 3),
               (4000, 12, 50, 6), (LOWER_BASE, 144, 1, 18),
               (UPPER_BASE, 144, 1, 162))
# How many entries the terrain table has: those of the lower layer.
TERRAINS_PER_CHIPSET = 162


def chip_index(chip_id):
    """`ChipIdToIndex`: from a map tile id to its ChipSet entry."""
    for base, count, step, index in CHIP_BLOCKS:
        if base <= chip_id < base + count * step:
            return index + (chip_id - base) // step
    return 0


def terrain_of(chipset, chip_id):
    """The terrain of a lower-layer tile, as `GetTerrainTag`.

    A ChipSet whose terrain is all 1 **does not store the table**: it is an
    RPG_RT optimization the format lets show, and the answer then is 1. Every
    ChipSet in this game is like that.
    """
    if not chipset.terrain:
        return 1
    return chipset.terrain[chip_index(chip_id)]

# The `animation_type` values that ask for continuous animation:
# "Continuous" and "Fixed Dir/Continuous". Lashe City's save point is of the
# second type.


# The `Teleport` command code, from liblcf. The harness's route planner uses
# it to know where an event's page leads.
TELEPORT = 10810

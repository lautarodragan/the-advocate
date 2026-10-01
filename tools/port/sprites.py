"""The characters as SNES objects, from the side of the converter.

**The characters are converted by `rm2k-snes-maps`** —which poses each
shows, how the eight OBJ palettes are split, the VRAM bank and the pose
bank; see `rm2k-snes-map-sprites`—, and so is who walks, animates standing
still or turns toward the hero (`moves.rs`). What stays here is what that
stage gets from other domains and what the emission reads: the graphics
drawn apart from the hero so its
flash does not spread (`separate_from_hero`); how many maps of the ROM
each character is in; the constants of the objects; and the warning that
stops the build when a mechanism is not drawn (`discard_warning`).
"""

import collections
import os
import sys

from port import events
from rpgmaker import rm2k


# The priorities for objects, already shifted into place in the vhoopppN
# byte: the priority is bits 5 and 4, not 0 and 1: writing $20 thinking it
# is priority 1 gives priority 2, and in the order of mode 3 —see
# `PRIORITY_ABOVE` in map_layers.py— that one extra place
# crosses exactly the upper layer. Nothing fails and the sprite is still
# visible: only on the wrong side of a layer, that is covering the roof it
# should be walking under.
#
# These two values are the only ones in the program: the ROM gets the hero's
# in HERO_PRIORITY and each NPC's comes built into its attribute byte. They are
# not written in `tools/runtime/` too: a second copy is one more place to get
# it wrong without anything noticing.
OBJ_PRIORITY = 0x10                      # priority 1: below BG2 1
OBJ_PRIORITY_ABOVE = 0x20                # priority 2: above it


# --- the character sprite ---------------------------------------------------
#
# An RM2k CharSet is 4 characters wide by 2 high; each one takes 72x128 and has
# 12 poses of 24x32: 3 walking frames for 4 directions.
#
# The SNES has no 24x32 sprites. The smallest one that covers that pose is
# 32x32, so it is padded with transparency at the sides and a quarter of the
# tiles is lost. The alternative was splitting each pose into several 16x32
# objects, which spends the same and multiplies the OAM entries.
#
# Sprites are always 4 bits per pixel, no exceptions: there is no mode 3 for
# them. That is, Talan has to fit in 15 colors, and has 36.


# --- the NPCs ---------------------------------------------------------------
#
# They are the map events that have a CharSet, standing still in the pose their
# page declares. Their scripts are not evaluated. Each one is one more OAM
# object.
#
# Two console limits rule here. One is how many sprite tiles fit in VRAM: 512
# addressable, and each pose is 16. The other, harder, is that a single screen
# line cannot have more than 34 8x8 sprite tiles; a 32x32 object contributes 4,
# so from nine characters together onward the console starts not drawing the
# last ones.

BLOCKS_PER_ROW = 4              # 4x4-tile blocks that fit in the grid


def block_tile(block):
    """The tile number where a 32x32 block starts."""
    return (block // BLOCKS_PER_ROW) * 64 + (block % BLOCKS_PER_ROW) * 4


def discard_warning(text, dangerous):
    """An event that isn't drawn. If it is one of those that break, it stops
    the conversion.

    **And it stops on purpose.** This was a `print` among fifty others, and on
    2026-09-07 it cost an afternoon: `demo-apertura` was built with the timer,
    map 2 lost event 30 —the middle cell of the door Core breaks— and the
    warning went by unnoticed in the build output. taro reached the cutscene,
    the door didn't change tile and he couldn't get through.

    It is the same criterion as `enter_panic` in the ROM: something that
    shouldn't happen is not discarded silently. The difference is where the
    noise is made. A discard is decided **when converting**, and by the time
    the ROM runs the event is no longer in any table: there is nothing left
    for the console to look at. Making it blow up when loading the map would be
    the same as not building the ROM, but later and without being able to say
    which event.

    Stopping on **all** discards doesn't work either: today there are
    decorative ones that don't fit in several maps, so every recipe would have
    to ask to continue and the stop wouldn't protect against anything. That is
    why the cap is `changes_graphic`, which is exactly the class event 30
    belonged to.

    There is no way to ask it to continue: there was a `--descartar-eventos`,
    and it went away in step 9e, when no cartridge discarded anything that
    needed it anymore.
    """
    if not dangerous:
        print("  " + text)
        return
    sys.exit(
        "%s\n\n"
        "The ROM is not built: that event **changes graphic between its pages**,\n"
        "that is, it is a mechanism and not decoration. Without being drawn, the\n"
        "change is never seen, and since the event still blocks the way and\n"
        "triggers, what is left is an invisible wall where the game expected a door." % text)


def maps_per_character(renderer, map_ids, game_dir):
    """How many maps of the ROM each (CharSet, index) appears in."""
    counts = collections.Counter()
    for other in map_ids:
        gm = renderer.load_map(os.path.join(game_dir, "Map%04d.lmu" % other))
        theirs = set()
        for event in gm.events:
            for page in event.pages:
                name = (getattr(page, "character_name", "") or "").strip()
                if name:
                    theirs.add((name, page.character_index))
        counts.update(theirs)
    return counts


def separate_from_hero(renderer, game_map, args, commands=()):
    """If something flashes the hero, the NPCs with its graphic go with
    another palette.

    On the console the flash is done on the character's palette, and a leader
    that is also an NPC in the map shares a palette with that NPC —so that the
    NPC isn't drawn with another leader's colors—, so both flashed. It is
    solved by counting those NPCs' graphic as another one, with the suffix
    `rm2k.COPY_SUFFIX`: the same drawing, with its own palette. It costs one
    palette per graphic, and only in the maps where something flashes the
    hero. `commands` are those of the test pages.
    """
    flashes = any(
        cmd.code == events.FLASH_SPRITE and cmd.parameters
        and cmd.parameters[0] == events.ROUTE_HERO
        for cmd in list(commands) + [cmd for ev in game_map.events
                                     for page in ev.pages
                                     for cmd in page.commands])
    if not flashes:
        return
    leader_owned = set()
    for actor in args.leaders:
        a = renderer.database.actors[actor]
        leader_owned.add((a.charset, a.charset_index))
    for ev in game_map.events:
        for page in ev.pages:
            if (page.character_name, page.character_index) in leader_owned:
                page.character_name += rm2k.COPY_SUFFIX

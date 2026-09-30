"""The characters as SNES objects, from the side of the converter that
still decides who walks.

**The characters are converted by `rm2k-snes-maps`** —which poses each
shows, how the eight OBJ palettes are split, the VRAM bank and the pose
bank; see `rm2k-snes-map-sprites`—. What stays here is what that stage
gets from other domains and what the emission reads: who walks, animates
standing still or turns toward the hero, which the event compiler's answer
says (`movable_events`); the graphics drawn apart from the hero so its
flash does not spread (`separate_from_hero`); how many maps of the ROM
each character is in; the constants of the objects; and the warning that
stops the build when a mechanism is not drawn (`discard_warning`).
"""

import collections
import os
import sys

from port import compiler, events
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

OBJ_COLORS = 15                    # 4 bits per pixel, and 0 is transparent
SPRITE_POSES = 12
OBJ_PALETTES = 8                   # 8 to 15, with or without the timer


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


# A pose in the cartridge: the 16 tiles in a row, by rows.
POSE_BYTES = 16 * 32


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


# How many still events with continuous animation a map animates. See the
# reason —and the measured number— inside `movable_events`.
# Measured against A Blurred Line: an assumption of the engine, not a piece of
# the game's data. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
ANIMATES_STILL_MAX = 4


def movable_events(game_map, scanned):
    """The events with a graphic that some compilable page sends walking, and
    the graphics some route changes to with command 34.

    `scanned` is what the compiler's first call answered for this map —see
    `compiler.scan`—: its pages compiled with a text block of their own and
    without songs, and the graphics they numbered.

    It is needed before building the sprite bank: the ones that move have to
    get **the twelve poses** of the walking cycle, and the others the single
    one they declare. Giving them to anyone that shows up in a MoveEvent would
    be simpler and doesn't fit: there are maps with seven, and that is 1232
    sprite tiles.

    The graphics of command 34 come from the same pass and for the same
    reason: an event that changes graphic needs the twelve poses of the new
    graphic put in the cartridge, and that is decided before building the
    bank. **The order has to be the same as the real compilation's**, because
    the bytecode carries the index: what guarantees it is that both passes
    compile the same pages, with the same text block. Without `Graphics` here
    a route with command 34 wouldn't compile in this pass and would in the
    other, and the two lists would drift apart.

    The pages are compiled to find out and what was compiled is thrown away.
    It is repeated work —the second call compiles them again with the real
    text block— but it isn't a repeated **rule**: the decision of what
    compiles is made by the same compiler both times.
    """
    pages = compiler.pages(scanned["pages"], game_map)
    route_graphics = [tuple(g) for g in scanned["graphics"]]
    npcs = rm2k.collect_npcs(game_map)
    visible = {npc["event"] for npc in npcs}
    # And the ones that walk on their own with some page's own route, which
    # need the twelve poses just like the ones a MoveEvent sends walking.
    own = {p["event"] for p in pages if p.get("ruta_propia")}
    # And the still ones with continuous animation —the save point in Lashe
    # City—, which don't walk but **change column all the same**. Without the
    # twelve poses their VRAM slot would carry a single one and there would be
    # nothing to animate them with: the still ones share a slot by (CharSet,
    # index, pose) and don't have one of their own.
    with_route = (events.route_targets(pages) | own) & visible
    animated = {npc["event"] for npc in npcs
                if npc.get("animates")} & visible - with_route
    # And the cap: a still event that animates **costs a whole VRAM slot**
    # —twelve tiles— because it stops sharing that of its (CharSet, index,
    # pose) and gets the twelve poses of its own, like the walking ones. A map
    # with thirty —52 has thirty— asks for 572 sprite tiles and 384 fit.
    #
    # So a map with more than `ANIMATES_STILL_MAX` animates **none**, and not
    # some yes and some no: two equal fountains, one moving and the other
    # frozen, looks worse than both still. Measured over the 328 maps of the
    # game: 312 have four or fewer, and of the maps the ROMs carry today the
    # only one that goes over is 52.
    if len(animated) > ANIMATES_STILL_MAX:
        animated = set()
    # And the ones that turn toward the hero when it talks to them: the events
    # with some action or touch page that compiled and turns —see TURN in
    # events.py—, with the graphics of **all** their pages that turn. The
    # twelve poses of each go to the cartridge, which is where the ROM takes
    # the one facing the hero from; the refresh compares the pages' graphics
    # to know whether the turn survives a page change.
    turning = {}
    for p in pages:
        if (p["codigo"] and p.get("gira")
                and p["trigger"] in (events.TRIGGER_ACTION,
                                     events.TRIGGER_TOUCH_HERO)):
            turning[p["event"]] = set()
    for p in pages:
        if p["event"] in turning and p.get("gira") and p["grafico"]:
            turning[p["event"]].add(tuple(p["grafico"][:2]))
    return with_route | animated, route_graphics, animated, turning


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

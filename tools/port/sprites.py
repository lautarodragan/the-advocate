"""The characters as SNES objects: their poses, their palettes, which NPCs
of a map get drawn, and the bank of poses that goes to VRAM.

The input is the map, its CharSets and the leader candidates; the output,
the sprite tiles and how the eight OBJ palettes are split among the
characters.
"""

import collections
import os
import sys

import numpy

from port import compiler, events
from rpgmaker import rm2k
from port import adeleine
from common import settings
from port.adeleine import CELL
from rpgmaker.rm2k import collect_npcs


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


def pack_tiles(tiles, planes=8):
    """`pack_tile` for several tiles at once: `tiles` is a numpy array of
    (n, 8, 8) indices, and out comes the list of the n packed tiles."""
    bits = (tiles[..., None] >> numpy.arange(planes, dtype=numpy.uint8)) & 1
    # (n, y, x, plane) -> one byte per row and plane, the leftmost pixel in
    # the high bit; and from there to the PPU order: pairs of planes, and
    # within each pair row by row.
    rows = numpy.packbits(bits, axis=2, bitorder="big")[:, :, 0, :]
    ppu = rows.reshape(-1, CELL, planes // 2, 2).transpose(0, 2, 1, 3)
    data = numpy.ascontiguousarray(ppu).reshape(len(tiles), planes * 8)
    return [bytes(row) for row in data]


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

SPRITE_W, SPRITE_H = 24, 32
OBJ_W = OBJ_H = 32                 # the real size of the object on screen
OBJ_COLORS = 15                    # 4 bits per pixel, and 0 is transparent
SPRITE_POSES = 12
INITIAL_POSE = 2 * 3 + 1           # facing down, the middle frame
OBJ_PALETTES = 8                   # 8 to 15, with or without the timer

# The OAM name table is 16 tiles wide, so a 32x32 object doesn't take 16 tiles
# in a row but a 4x4 block inside that grid.
OBJ_ROW = 16


def pose_origin(index, pose):
    """Where a pose starts inside the CharSet."""
    return ((index % 4) * SPRITE_W * 3 + (pose % 3) * SPRITE_W,
            (index // 4) * SPRITE_H * 4 + (pose // 3) * SPRITE_H)


ALL_POSES = frozenset(range(SPRITE_POSES))


def sprite_colors(image, index, poses=None):
    """The character's colors, with how many pixels each one uses.

    `poses` are the ones the event can end up showing. **Counting all twelve
    when one is seen gives away CGRAM entries**: the save point in Lashe City
    animates facing up and nothing else, and its twelve poses together have
    41 colors against the 13 of those three frames. The 26 of difference were
    all merged, and the first to go were the blue and white of the glow —few
    pixels each— against the grays that cover the rest of the block.

    Who can show what is decided by `map_poses`, which is the same pass
    that already chose who gets all twelve poses in the cartridge: the
    optimization existed in tiles and in VRAM since 2026-09-05 and had never
    reached the color count. `None` is "all twelve", which is what fits
    whoever walks, animates standing still, turns toward the hero or changes
    graphic with command 34.
    """
    base_x = (index % 4) * SPRITE_W * 3
    base_y = (index // 4) * SPRITE_H * 4
    # With numpy and not pixel by pixel: the character's block to an array,
    # the poses by slicing, and each 15-bit color as a single integer to
    # count them with `unique`. Millions of pixels are read per ROM.
    block = numpy.asarray(image.crop((base_x, base_y,
                                      base_x + SPRITE_W * 3,
                                      base_y + SPRITE_H * 4)))
    seen = numpy.concatenate([
        block[(pose // 3) * SPRITE_H:(pose // 3 + 1) * SPRITE_H,
              (pose % 3) * SPRITE_W:(pose % 3 + 1) * SPRITE_W].reshape(-1, 4)
        for pose in (sorted(ALL_POSES) if poses is None
                     else sorted(poses))])
    return _count_colors(seen)


def _count_colors(pixels):
    """A Counter of the 15-bit colors of the opaque RGBA pixels.

    **The keys come in the order in which they appear**, which is the one the
    `Counter` built pixel by pixel had: whoever walks it
    —`merge_least_visible` breaks ties by that order— has to see the same.
    """
    opaque = pixels[pixels[:, 3] != 0, :3] >> 3
    codes = ((opaque[:, 0].astype(numpy.int32) << 10)
             | (opaque[:, 1].astype(numpy.int32) << 5) | opaque[:, 2])
    unique, first, count = numpy.unique(codes, return_index=True,
                                        return_counts=True)
    counts = collections.Counter()
    for k in numpy.argsort(first, kind="stable").tolist():
        c = int(unique[k])
        counts[(c >> 10, (c >> 5) & 31, c & 31)] = int(count[k])
    return counts


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


def character_palette(image, index, cap=None, poses=None):
    """A character's palette, and how to map each color to its index.

    It is the same computation for the image that goes to VRAM and for the
    cartridge's pose bank, and it has to be: a pose uploaded on the fly is
    drawn with the palette already in CGRAM.

    `cap` lowers the number of colors below fifteen, and exists to make room
    for the timer: its digits are two colors and black is usually already
    there, so one entry is enough. **Who pays for it and how much is decided
    by `drawable_npcs`**, which is the only one that sees all the palettes
    of the map; here it is only obeyed. If the converter chose it here, two
    calls for the same character could give different palettes and the
    cartridge's poses wouldn't match the CGRAM.

    `poses` are the ones the event can show: **the fifteen colors are chosen
    looking only at those**, which is where almost all of the save point's
    color gain comes from. Same as `cap`, `drawable_npcs` decides it and
    here it is only obeyed.

    The returned `mapping` still covers **all** the colors of the twelve-pose
    block, not only those of `poses`: the ones left out of the count go to
    the nearest of the survivors. It is not defensive decoration —it is what
    keeps `pose_tiles` from dying with a KeyError if someone asks for one pose
    too many—, and it costs one computation per color.
    """
    cap = OBJ_COLORS if cap is None else cap
    counts = sprite_colors(image, index, poses)
    if len(counts) <= cap:
        mapping = {c: c for c in counts}
    else:
        mapping, _ = adeleine.merge_least_visible(counts, cap)
    palette = sorted(set(mapping.values()))
    if poses is not None and palette:
        for color in sprite_colors(image, index):
            if color not in mapping:
                mapping[color] = min(
                    palette, key=lambda p, c=color: (adeleine.luma_distance(p, c), p))
    lookup = {color: i + 1 for i, color in enumerate(palette)}
    return palette, lookup, mapping


def pose_tiles(image, index, pose, lookup, mapping):
    """The sixteen tiles of a pose, by rows: four rows of four.

    It is the order in which the PPU reads a 32x32 object —each row is four
    consecutive tiles of the name grid, and rows go sixteen apart— and that is
    why a pose is uploaded with four DMAs of 128 bytes.
    """
    ox, oy = pose_origin(index, pose)
    # With numpy, like `sprite_colors`: the pose to an array, each distinct
    # color translated only once, and the bit planes of the sixteen tiles
    # together.
    pixels = numpy.asarray(image.crop((ox, oy, ox + SPRITE_W,
                                       oy + SPRITE_H)))
    rgb = pixels[:, :, :3] >> 3
    codes = ((rgb[:, :, 0].astype(numpy.int32) << 10)
             | (rgb[:, :, 1].astype(numpy.int32) << 5) | rgb[:, :, 2])
    opaque = pixels[:, :, 3] != 0
    unique, which = numpy.unique(codes[opaque], return_inverse=True)
    indices = numpy.array(
        [lookup[mapping[(c >> 10, (c >> 5) & 31, c & 31)]]
         for c in unique.tolist()], dtype=numpy.uint8)
    whole_pose = numpy.zeros((OBJ_H, OBJ_W), dtype=numpy.uint8)
    margin = (OBJ_W - SPRITE_W) // 2
    center = numpy.zeros((SPRITE_H, SPRITE_W), dtype=numpy.uint8)
    center[opaque] = indices[which]
    whole_pose[:SPRITE_H, margin:margin + SPRITE_W] = center
    tiles = whole_pose.reshape(4, CELL, 4, CELL).swapaxes(1, 2).reshape(
        16, CELL, CELL)
    return pack_tiles(tiles, planes=4)


def changes_graphic(event):
    """Whether some page of the event draws something different from another.

    It is what separates an annoying discard from one that breaks the game. A
    decorative single-page event that isn't drawn is just lost —the
    `CoreBlood` of map 3, the four `Link`s—. One that **changes graphic** is a
    mechanism: a door that opens, a machine that turns on. If it isn't drawn,
    the change is never seen, and since the event still blocks the way, what is
    left is an invisible wall the player expected to open.
    """
    graphics = {((getattr(p, "character_name", "") or "").strip(),
                 p.character_index) for p in event.pages}
    return len(graphics) > 1


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


# --- the weight of a graphic ------------------------------------------------
#
def graphic_weight(charset):
    """How much a CharSet weighs when splitting the sprite palettes: the one
    that weighs is served first, and the one that doesn't arrives in map order
    and may end up with someone else's palette. The game decides it, in
    `[graphics.palette_weight]` of the project file, with its reasons. The
    `~trama` suffix of translucent ones doesn't count: the weight belongs to
    the drawing."""
    weights = settings.value("graphics", "palette_weight", kind=dict)
    return weights.get((charset or "").split(rm2k.DITHER_SUFFIX)[0], 0)


def pose_row(pose):
    """The three frames of the walking cycle for the direction of `pose`.

    An event that animates standing still changes column and **never row**: the
    ROM builds its pose as `facing_of_row * 3 + columna` in `animate_still`,
    so of the twelve it can only show these three.
    """
    return frozenset(range(pose // 3 * 3, pose // 3 * 3 + 3))


def map_poses(renderer, game_map, leaders, movable=(), turning=(),
              route_graphics=(), animates_still=()):
    """Which poses each (CharSet, index) can end up showing in this map.

    Each character's palette comes from here: fifteen colors chosen over what
    is seen and not over the twelve poses of the block. The list of who needs
    all twelve is **the same** that already decided which poses go to the
    cartridge and to VRAM —see `movable_events` and how `slots` is built in
    `convert_map`—, and it has to be: a pose the ROM uploads and the palette
    didn't count is drawn with colors that aren't its own.

    These take all twelve:

    * the leader candidates, because the hero walks;
    * the events in `movable` that **walk**;
    * the graphics in `turning`, because one that turns toward the hero can end
      up in any of the four directions;
    * the graphics of command 34, which keep walking after the change.

    One that **animates standing still** keeps the three frames of its
    direction, which is all `animate_still` can put on screen: it changes
    column and not row. That is where the save point in Lashe City is, the one
    taro saw gray: its twelve poses have 41 colors and the three frames it
    shows, 13. `savept` is an **edited** CharSet —the original RPG Maker
    drawing in almost all of the block and a new drawing, with its own colors,
    in a corner—, and in those the twelve poses don't share a palette. In a
    normal one counting twelve or counting three gives almost the same.

    The rest keep the pose their page declares, plus each page's if the
    graphic follows them: exactly the VRAM slots the map reserves for it, not
    one more.

    The same (CharSet, index) can belong to a still one and to a walking one
    at once —and across maps of the same ROM, too—: the union accumulates,
    which is what makes the count independent of the order they are walked in.
    """
    poses = {}

    def add(key, which_ones):
        previous = poses.get(key)
        poses[key] = ALL_POSES if (previous is ALL_POSES
                                   or which_ones is ALL_POSES) \
            else frozenset(previous or ()) | frozenset(which_ones)

    for actor in leaders:
        a = renderer.database.actors[actor]
        add((a.charset, a.charset_index), ALL_POSES)
    for pairs in (turning.values() if hasattr(turning, "values") else turning):
        for pair in pairs:
            add(tuple(pair), ALL_POSES)
    for pair in route_graphics:
        add(tuple(pair), ALL_POSES)
    for npc in collect_npcs(game_map):
        key = (npc["charset"], npc["index"])
        # Animates standing still and doesn't walk: the three frames of its
        # row. If it is also in `turning` it already took all twelve above, so
        # the turn doesn't run out of colors.
        still_animated = (npc["event"] in animates_still
                          and npc["event"] in movable)
        if still_animated:
            own = pose_row(npc["pose"])
        elif npc["event"] in movable:
            own = ALL_POSES
        else:
            own = frozenset((npc["pose"],))
        add(key, own)
        if npc["changes"]:
            for graphic in npc["graphics"]:
                if graphic is not None:
                    # An event that walks and also changes graphic loses the
                    # change —walking wins, see `convert_map`—, but the page's
                    # graphic still asks for a palette here, so the pose it
                    # declares is counted.
                    add(graphic[:2],
                        pose_row(graphic[2]) if still_animated
                        else ALL_POSES if npc["event"] in movable
                        else (graphic[2],))
    return poses


def drawable_npcs(renderer, game_map, leaders, cap, route_graphics=(),
                  timer_colors=(), only_here=None, poses=None):
    """The map's NPCs that are drawn: all the ones with a CharSet, and the ones
    drawn with a chipset tile **that fit** in the sprite palettes.

    An event with a tile graphic is one more character for the console, with
    its palette, and there are eight sprite palettes. The game's CharSets use
    fifteen colors each and share none, so in a map with seven CharSet
    characters there is a single palette left for all the tiles, and two tiles
    that don't share colors don't fit. It happened in map 8: nine characters in
    nine palettes. Before this, tile events weren't drawn at all in any map
    —the door of map 2 was a black portal—, so drawing the ones that fit and
    warning about the ones that don't is strictly better.

    There is a single rule: first the possible leaders are placed, the NPCs
    with a CharSet and the graphics that routes change to with command 34
    —which are one more character, with its palette—, in map order and with the
    same first-place-that-fits as `build_characters`; then the tiles, in map
    order, each one while it fits. Returns the list of NPCs that are drawn and
    that of the (event, tile) left out.
    A tile left out isn't drawn, but its event is still there: it blocks the
    way and triggers all the same.
    """
    palettes = []
    palette_of = {}
    # Who had to be lent someone else's palette. They show up in the
    # converter's report: they don't break anything, but they are seen with
    # colors that aren't their own.
    lent = set()
    # The palettes of the possible leaders. **Nobody else goes in there**, and
    # not for tidiness: an event's flash —`FlashSprite`— on the console is a
    # CGRAM tint, so it tints the whole palette and with it everything sharing
    # it. RM2k, instead, applies it on the sprite image; that is, sharing the
    # hero's palette is a real difference from RM2k and not a packing detail.
    #
    # taro saw it on 2026-09-07 in the Emitter Room: when Talan absorbs Core's
    # anger and flashes red, two black tiles above some chests —invisible,
    # because they are all black— turned red with him. They shared palette 0
    # with `Future1:0`.
    #
    # The leader is protected and not "the one that flashes" because the target
    # of a flash can be any event and is decided at run time; the hero is the
    # one that flashes in this game and is the only one that can be known here.
    # If a flash on another event shows up, it will leak all the same.
    leader_owned = set()
    # Which poses each graphic can show, which is what its fifteen colors are
    # chosen over. Without it they are the usual twelve.
    poses = dict(poses or {})

    def fits(charset, index, force, leader=False):
        palette, _, _ = character_palette(renderer.charsets.get(charset),
                                          index,
                                          poses=poses.get((charset, index)))
        for number, existing in enumerate(palettes):
            if number in leader_owned and not leader:
                continue
            union = existing + [c for c in palette if c not in existing]
            if len(union) <= OBJ_COLORS:
                palettes[number] = union
                palette_of[(charset, index)] = number
                return True
        if force or len(palettes) < cap:
            if leader:
                leader_owned.add(len(palettes))
            palette_of[(charset, index)] = len(palettes)
            palettes.append(list(palette))
            return True
        # There is no palette for it, so **one is lent to it**: each color goes
        # to the nearest of the ones there are. It looks bad, but it shows.
        #
        # It used to be discarded, and taro cut that discussion short with the
        # argument that settles it: if we can't include all the events, the
        # whole project falls apart. And a sprite with odd colors is a
        # **visible** error; an invisible one is a trap, and it already cost us
        # an afternoon with the door Core breaks.
        #
        # How much it shows depends on the color jump, not on how many pixels
        # change: the pad's door changes 42% of its own with a jump of 1 out
        # of 31 and stays almost the same, while `Future3:1` changes 49% with
        # jumps of 17 and it does show.
        counts = sprite_colors(renderer.charsets.get(charset), index)
        best = None
        for number, existing in enumerate(palettes):
            if number in leader_owned:
                continue        # the ROM overwrites those with the leader's colors
            cost = sum(v for c, v in counts.items() if c not in existing)
            if best is None or cost < best[0]:
                best = (cost, number)
        if best is None:
            return False        # there isn't a single non-leader palette
        palette_of[(charset, index)] = best[1]
        lent.add((charset, index))
        return True

    npcs = collect_npcs(game_map)

    def keys(npc):
        """The (CharSet, index) pairs the NPC can end up drawing: its row's
        and, if the graphic follows the page, those of all its pages."""
        out = [(npc["charset"], npc["index"])]
        if npc["changes"]:
            out += [g[:2] for g in npc["graphics"] if g is not None]
        return out

    # The possible leaders, which are the ones the hero can end up drawing.
    #
    # **They share a single CGRAM slot**, because one leads at a time: the ROM
    # uploads the fifteen colors of whoever is leading when the party changes
    # and when loading the map. A palette used to be reserved for each, and
    # that is a palette taken by someone who isn't on screen: map 8 —the street
    # Talan's pad opens onto— asked for nine out of eight because of that, with
    # Talan and Kersh reserved on a street where neither appears.
    #
    # **Except the one that is also an NPC in this map.** That one gets its own
    # palette, because its row uses it at the same time as the hero: sharing
    # the slot, with Talan leading, the Kersh standing on the map would be
    # drawn with Talan's colors. It happens in maps 1 and 6 with Kersh and in 3
    # with Talan; in the other six of the PoC it doesn't, and that is where the
    # gain is.
    npc_keys = {c for npc in npcs for c in keys(npc)}
    seen, slot_leader, own = set(), None, set()
    for actor in leaders:
        a = renderer.database.actors[actor]
        key = (a.charset, a.charset_index)
        if key in seen or not sprite_colors(
                renderer.charsets.get(a.charset), a.charset_index):
            continue
        seen.add(key)
        if key in npc_keys or slot_leader is None:
            fits(a.charset, a.charset_index, True, leader=True)
            if key not in npc_keys:
                slot_leader = palette_of[key]
        else:
            # To the shared slot, and with **its own** colors: its poses are
            # packed with its sorted palette, which is the one the ROM uploads
            # when its turn to lead comes.
            palette_of[key] = slot_leader
            own.add(key)

    # The CharSets of the pages **are no longer forced**. They were forced so
    # that a character never ran out of palette, and the price was that a map
    # with more characters than palettes didn't convert: map 8 asked for nine
    # out of eight and the Hover-Tram asks for eleven. With the lending in
    # `fits` that is no longer needed —whoever doesn't fit is drawn with
    # someone else's— and no map fails because of this.
    #
    # The only one still forced is the leader: the hero is on screen all the
    # time and is the one where it would show the most.
    #
    # The order is the map's, **except the ones with weight**: see `graphic_weight`.
    for npc in sorted(npcs, key=lambda n: -graphic_weight(n["charset"])):
        for key in keys(npc):
            if key not in seen and not key[0].startswith(rm2k.TILE_PREFIX):
                seen.add(key)
                fits(key[0], key[1], False)
    # And the ones from command 34, after the NPCs and before the tiles.
    # **While they fit**, like the tiles and not like a page's CharSets: forcing
    # them broke three maps of the game —108, 114 and 207 asked for nine
    # palettes out of eight— and breaking a map that converts today is worse
    # than not drawing a graphic change. The one that doesn't fit isn't drawn,
    # which is the same that already happens with a page whose graphic didn't
    # fit. Transparent ones don't even ask for a palette.
    for key in route_graphics:
        if key not in seen and sprite_colors(
                renderer.charsets.get(key[0]), key[1]):
            seen.add(key)
            fits(key[0], key[1], False)
    # The timer **before the events drawn with a chipset tile**. Its two colors
    # go to the first palette with room and are reserved there;
    # `timer_digits` later finds them in place and adds nothing.
    #
    # The order matters and until now it was reversed by accident. A tile event
    # goes in "while it fits" —that is how it is written a few lines below, and
    # the one that doesn't fit isn't drawn—, while the timer is HUD and is on
    # screen always. In map 8 chipset tile 118, which is two colors, went into
    # the save point's palette and left it at fourteen: the timer no longer fit
    # anywhere and a whole character had to lose a color to make room for it.
    # Serving it first, nothing is merged and the tile settles in another
    # palette.
    if timer_colors:
        for number, existing in enumerate(palettes):
            if number in leader_owned:
                continue        # the ROM overwrites those with the leader's colors
            union = existing + [c for c in timer_colors if c not in existing]
            if len(union) <= OBJ_COLORS:
                palettes[number] = union
                break

    fit, outside, out, discarded = set(), set(), [], []
    for npc in npcs:
        for key in keys(npc):
            if key in seen or key in fit or key in outside:
                continue
            if fits(key[0], key[1], False):
                fit.add(key)
            else:
                outside.add(key)
        # The ones left out aren't drawn, from anywhere: the row is hidden if
        # it is its own, and the page that asks for it comes out with no
        # graphic.
        npc["afuera"] = {c for c in keys(npc) if c in outside}
        discarded += [(npc["event"], c[0]) for c in sorted(npc["afuera"])]
        if (npc["charset"], npc["index"]) in outside:
            npc["visible"] = False
            npc["tile_pass"] = None
            if not npc["changes"]:
                continue
            # The row stays for the other pages, hidden, and its fields move to
            # the first of them that fits: it is the slot it starts with. If
            # none fits, the event is never drawn.
            other = next((g for g in npc["graphics"]
                          if g is not None and g[:2] not in outside), None)
            if other is None:
                continue
            npc["charset"], npc["index"], npc["pose"] = other
        out.append(npc)
    # And last, the timer. Its digits are two colors and black is usually
    # already in almost all of them, so **one free entry** is enough; the
    # problem shows up in a map that fills the eight palettes to fifteen, which
    # is 8 —Lashe City, the street Talan's pad opens onto—.
    #
    # There room is made by lowering a fifteen-color character to fourteen,
    # and **the one that moves the fewest pixels** is chosen. Only palettes of
    # a single character are looked at: lowering one shared by two would force
    # requantizing both against the new palette, and that is a lot more code
    # for a case that doesn't come up. Leader ones aren't looked at either: the
    # ROM overwrites them.
    #
    # Measured in map 8: `BLVehicles:5` moves 105 pixels of 4648, 2.26%, with a
    # jump of 4 out of 31. The next candidate costs 11.84%.
    caps = {}
    # Only if it really has nowhere to go: not a palette with room **nor a free
    # slot**. Without looking at the free slots, this took two colors off
    # `People4:5` in map 5 —16.85% of its pixels— when the map uses four
    # palettes of the eight and the timer had a whole one to spare.
    if timer_colors and len(palettes) >= OBJ_PALETTES and not any(
            n not in leader_owned
            and len(set(p) | set(timer_colors)) <= OBJ_COLORS
            for n, p in enumerate(palettes)):
        singles = collections.Counter()
        for key, n in palette_of.items():
            singles[n] += 1
        best = None
        for key, n in palette_of.items():
            if n in leader_owned or singles[n] != 1 or key[0].startswith(
                    rm2k.TILE_PREFIX):
                continue
            # The ones in another map of the ROM go **last**, not out: the pose
            # bank is global, so quantizing it differently here than there
            # costs the cartridge one more bank, 6 KB. Until 2026-09-12 they
            # were excluded and that was enough, because in map 8 there was
            # always a single-map candidate; when the weighted graphics —the
            # save point— started being served first the split rearranged
            # itself, none was left, and the ROM with the timer stopped
            # building. Six kilobytes is worse than nothing and better than not
            # having a timer.
            foreign = only_here is not None and key not in only_here
            counts = sprite_colors(renderer.charsets.get(key[0]), key[1],
                                   poses.get(key))
            if not counts:
                continue
            missing = len([c for c in timer_colors if c not in palettes[n]])
            new_cap = OBJ_COLORS - missing
            m, _ = adeleine.merge_least_visible(counts, new_cap)
            moved = sum(v for c, v in counts.items() if m[c] != c)
            cost = (foreign, moved / float(sum(counts.values())), key)
            if best is None or cost < best[0]:
                best = (cost, key, n, new_cap, sorted(set(m.values())))
        if best is not None:
            _cost, key, n, new_cap, new_palette = best
            print("  to make room for the timer, %s:%d drops to %d colors "
                  "(%.2f%% of its pixels)%s"
                  % (key[0], key[1], new_cap, 100 * _cost[1],
                     ", and with a pose bank of its own" if _cost[0] else ""))
            palettes[n] = new_palette
            caps[key] = new_cap

    # The split is returned so `build_characters` uses it as is: a second
    # first-place-that-fits in another order can give a different count, and
    # it did: map 8 fit here in eight palettes and there asked for nine.
    return out, discarded, (palettes, palette_of, own, leader_owned,
                            caps, lent, poses)


def build_characters(images, characters, slots, split):
    """The sprite bank that goes to VRAM: one pose per slot.

    `characters` is the list of (charset, index) that need a palette, in the
    order they are handed out; `slots` that of (key, charset, index, pose), a
    block of 16 tiles for each one and in that order. Since 2026-09-05 what
    goes here is **one pose per slot** and nothing else: the twelve of the
    walkers live in the cartridge —see `pose_bank`— and are uploaded on
    the fly. They all used to go here, and the opening scene asked for 768
    tiles of the 512 the PPU addresses.

    **Palettes are not decided here**: they arrive in `split`, which is what
    `drawable_npcs` decided for the whole map. Here only the index of each
    color inside its own is built. Until 2026-09-17 there was also a split of
    its own, first-that-fits, for when none arrived; nobody used it, and a
    second split in another order had already given a different count —map 8
    fit there in eight palettes and here asked for nine—.

    Returns (tiles, palettes, location, paleta_de): location maps the slot's
    key to (block, palette), and paleta_de each (charset, index) to its
    palette.
    """
    tiles = bytearray()
    colors = {}
    palettes = [list(p) for p in split[0]]
    palette_of = dict(split[1])
    # The ones that share the leader's slot: their `lookup` comes from **their**
    # palette and not from the slot's, because the ROM will upload their colors
    # there when their turn to lead comes. See `drawable_npcs`.
    own = set(split[2])
    # And who had their number of colors lowered so the timer would fit. It has
    # to be the same number `drawable_npcs` used: if here it were quantized
    # with fifteen, the cartridge's poses wouldn't match the palette the ROM
    # uploads to CGRAM.
    caps = dict(split[4])
    # And which poses each one can show, which is what their fifteen colors
    # were chosen over there. It has to be the same set: with another one, the
    # palette the ROM uploads to CGRAM and the tiles packed here would come
    # from two different computations.
    poses_of = dict(split[6])
    for charset, index in characters:
        if (charset, index) in colors:
            continue
        palette, lookup, mapping = character_palette(
            images[charset], index, caps.get((charset, index)),
            poses=poses_of.get((charset, index)))
        if (charset, index) not in palette_of:
            sys.exit("%s:%d is not in the palette split" % (charset, index))
        if (charset, index) in own:
            colors[(charset, index)] = (lookup, mapping)
            continue
        union = palettes[palette_of[(charset, index)]]
        # The colors that aren't in the palette it got go to the nearest of the
        # ones there are. It happens when the map ran out of palettes and
        # `drawable_npcs` lent it someone else's: it looks bad, but it shows.
        lookup = {}
        for color in palette:
            if color in union:
                lookup[color] = union.index(color) + 1
            else:
                near = min(union,
                           key=lambda p, c=color: adeleine.luma_distance(p, c))
                lookup[color] = union.index(near) + 1
        colors[(charset, index)] = (lookup, mapping)

    where = {}
    for block, (key, charset, index, pose) in enumerate(slots):
        lookup, mapping = colors[(charset, index)]
        where[key] = (block, palette_of[(charset, index)])
        first = block_tile(block)
        # The block doesn't take 16 consecutive tiles: it is a 4x4 square inside
        # a grid 16 wide, so the gap has to be left.
        needed = (first + 3 * OBJ_ROW + 4) * 32
        if len(tiles) < needed:
            tiles += bytes(needed - len(tiles))
        for i, tile in enumerate(pose_tiles(images[charset], index, pose,
                                            lookup, mapping)):
            number = first + (i // 4) * OBJ_ROW + (i % 4)
            tiles[number * 32:(number + 1) * 32] = tile
    return bytes(tiles), palettes, where, palette_of, colors


# A pose in the cartridge: the 16 tiles in a row, by rows.
POSE_BYTES = 16 * 32


def pose_bank(images, characters, colors):
    """The twelve poses of each character that changes pose, for the cartridge.

    One block per character —twelve poses of 512 bytes, 6 KB— and not one for
    all: each goes with `.block`, so no DMA of a pose crosses a bank. And
    **from the whole ROM, not from the map**: maps 1 and 2 share Core, Manta
    and Kersh, and with one copy per map the boot-with-window ROM went over the
    cartridge by 19 KB. `emit` splits them into poses and emits each distinct
    pose only once; the map carries its animated characters in order and
    `emit` translates.
    """
    banks = {}
    for charset, index in characters:
        # With the lookup from `build_characters`, which is that of the palette
        # it ended up packed in: a pose uploaded on the fly is drawn with the
        # palette already in CGRAM.
        lookup, mapping = colors[(charset, index)]
        data = bytearray()
        for pose in range(SPRITE_POSES):
            for tile in pose_tiles(images[charset], index, pose, lookup,
                                   mapping):
                data += tile
        banks[(charset, index)] = bytes(data)
    return banks


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

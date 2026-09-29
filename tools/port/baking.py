"""The events baked into the map: the opaque ones that never move or change
are painted into the upper layer instead of being drawn as sprites, and only
if that doesn't move anyone else's colors in CGRAM.
"""

from port import events
from rpgmaker import rm2k
from rpgmaker.rm2k import collect_npcs
from render import render_map
from port.map_layers import converted_layers


# --- the events baked into the map ------------------------------------------
# An event drawn with **an opaque ChipSet tile**, always the same and always in
# the same cell, doesn't need to be drawn as an event: its tile goes into the
# map's upper layer and its NPC row starts hidden. The event stays whole for
# its logic —it triggers, blocks the way, is the target of a page—; what is
# saved is its OAM object and its pass through `place_npc`, which is what
# costs frames in the most loaded map of the game.
#
# **Passability doesn't change, and that is what allows hiding the row.** For
# an upper-layer tile without the "above the hero" bit,
# `rm2k.passability_map` resolves the cell with that tile's bits, which are
# exactly the ones `rm2k.event_tile_passability` made the event's row
# impose; and `pass_with_event`, in tools/runtime/hero.s, skips hidden
# rows. That is, the baking hands the same table answer over to the map. It
# is guarded by `rom/pruebas/herramientas/test_horneados.py`.
#
# What is **not** saved yet: its sprite palette and its VRAM slot. The event
# still enters the `drawable_npcs` split as if it were drawn, on purpose:
# taking it out of there frees a palette for the map and that changes what is
# seen —the tiles that today are drawn with someone else's palette would get
# their own, and map 11 has one—, and that is a separate decision from this
# one.

# The commands that move an event to another cell or touch its drawing: an
# event that some page can move, change drawing or flash is not fixed, so it
# isn't baked. The **raw** commands are looked at and not the compiled pages:
# it is more conservative —it also counts the pages this port doesn't
# compile— and nothing needs compiling to ask, which is what lets the decision
# be made before drawing the layers.
MOVING_COMMANDS = (events.MOVE_EVENT, events.CHANGE_EVENT_LOCATION,
                   events.TRADE_EVENT_LOCATIONS, events.FLASH_SPRITE)


def _tile_alphas(chipset, index):
    """The alpha of the 16x16 pixels of upper-layer tile `index`."""
    return render_map.upper_tile(chipset, index).getchannel("A").tobytes()


def bakeable_events(renderer, game_map):
    """The map's events that can be baked, as {event: map tile}.

    The rule is deliberately small, because what holds it up is that **it
    looks the same**; when in doubt the event keeps being drawn. All five
    things are required:

    * **it is drawn with a tile of the ChipSet's upper layer** —not with a
      CharSet—, with tile 0 left out because in RM2k it is "no graphic";
    * **the drawing is fixed**: the first page without a condition and **all**
      pages drawing the same tile on the same layer. A door that opens with a
      switch changes tile, so it doesn't qualify; one that only changes
      script does. Until 2026-09-20 **a single page** was required, and that
      left out four light tiles of map 11 whose two or three pages draw the
      same thing;
    * **the event doesn't move or change**: no `move_type`, no own route on any
      page, no continuous animation on any, and no page of the map moves it or
      makes it flash (see `MOVING_COMMANDS`);
    * **the tile covers the whole cell**: opaque in all 16x16, and without the
      "above the hero" bit —with it, placed in the upper layer it would be
      drawn above the hero and not below, which is where the sprite of a
      below-layer event is—;
    * **the cell has room and doesn't open**: the event is on the below layer,
      the map's upper layer is empty there, and the tile adds no passage bit
      the map's table didn't have. If a tile is already drawn, baking would
      cover it; if the event is on the hero's layer or the above one its
      sprite doesn't go in the map's upper layer without changing what covers
      what; and if the tile opened the cell, baking would leave a hole that
      until then only existed while the row was visible.

    The tile below being animated **doesn't rule it out**: the cell is baked
    into every drawing of the animation, because what is touched is the map
    layer and `animated_layers` renders all of them from there. What is lost is
    the animation the opaque tile already covered.
    """
    chipset = renderer.chipset_by_name(getattr(game_map, "chipset_filename",
                                               None))
    flags = getattr(game_map, "passability_table", None)
    if chipset is None or flags is None:
        return {}
    # That tile 0 of the upper layer —the one an empty cell carries— draws
    # nothing is checked, not assumed: it is what makes putting the event's
    # tile there cover nothing. The ChipSets of this game satisfy it; one that
    # doesn't leaves the map without baked events instead of changing what is
    # seen.
    if any(_tile_alphas(chipset, 0)):
        return {}
    # The events that some page moves, flashes or sends walking. It goes by
    # the RM2k id, which is what the commands carry, and it is translated by
    # the same `events.MapEvents` the compilation uses.
    map_events = events.MapEvents(game_map)
    touched = set()
    for event in game_map.events:
        for page in event.pages:
            for cmd in page.commands:
                if cmd.code in MOVING_COMMANDS and cmd.parameters:
                    target = map_events.route_target(cmd.parameters[0])
                    if target:
                        touched.add(target - 1)
    # And the ones that walk on their own: `move_type` set to anything other
    # than still, or an own route on some page.
    walking = {number for number, event in enumerate(game_map.events)
               if any(p.move_type or p.move_route.commands
                      for p in event.pages)}
    opaque = {}
    bakeable = {}
    for npc in collect_npcs(game_map):
        number = npc["event"]
        base = rm2k.unbaked(npc["charset"])
        if not base.startswith(rm2k.TILE_PREFIX) or not npc["visible"]:
            continue
        if npc["changes"] or number in walking or number in touched:
            continue
        pages = game_map.events[number].pages
        if pages[0].condition.active:
            continue
        # All its pages have to draw the same thing, on the same layer and
        # without continuous animation, and not only the active one: the row
        # is hidden for the whole playthrough, so what decides is what the
        # event **can end up** drawing. Half of
        # `test_hornear_no_cambia_la_pasabilidad_de_la_celda` comes for free
        # from this: with the same graphic and the same layer on all of them,
        # `rm2k.event_tile_passability` gives the same on all of them.
        if set(npc["graphics"]) != {npc["graphics"][0]} \
                or npc["graphics"][0] is None:
            continue
        if set(npc["layers"]) != {rm2k.LAYER_BELOW}:
            continue
        if any(p.animation_type in rm2k.CONTINUOUS_ANIMATION for p in pages):
            continue
        index = int(base.rsplit(":", 1)[1])
        if not index:
            continue                    # tile 0 is "no graphic"
        tile = rm2k.UPPER_BASE + index
        if flags[tile] & rm2k.PASS_ABOVE:
            continue                    # it would go above the hero
        cell = npc["y"] * game_map.width + npc["x"]
        if game_map.upper_layer[cell] != rm2k.UPPER_BASE:
            continue                    # the cell's upper layer is taken
        # **And baking cannot open the cell.** Baking puts the tile in the
        # upper layer, so the map's table starts declaring the tile's bits
        # where it used to declare its own. Closing too much doesn't happen
        # —a solid event on free floor is the normal case, and the row already
        # closed that cell for everyone—, but **opening** does: a walkable
        # tile over a cell the map has closed is a hole that until now only
        # existed while the row was visible.
        #
        # The case that brought it up is the `MovinDoor` of map 2, which the
        # relaxed rule reaches: it is in a corner of the map, out of any
        # camera, and baking it moved the golden `puerta-izq-950` —113 pixels,
        # on a door sixty cells from there, with the same switches set—. The
        # whole mechanism was never fully taken apart; what is measured is
        # that this baking is the only thing that changes between the two
        # ROMs.
        if npc["tile_pass"] & ~rm2k.cell_passability(
                flags, game_map.lower_layer[cell],
                game_map.upper_layer[cell]):
            continue
        if index not in opaque:
            opaque[index] = all(a == 255
                                for a in _tile_alphas(chipset, index))
        if not opaque[index]:
            continue
        bakeable[number] = (cell, tile)
    return bakeable


def _same_cgram_split(without_it, with_it):
    """Whether baking didn't move anyone else's colors they are drawn with.

    What baking adds to the map are the tile's colors, and the background's
    colors are a shared pool with a budget: a few extra make it merge —and
    then pixels change in cells that have nothing to do with it— or take a
    palette away from the upper layer, which packs per tile and merges much
    worse. Both things show here: the upper layer has to come out identical,
    and the background with the same budget and without merging more than
    before. The background palette having new colors, and therefore another
    order, is not a change: the tilemap comes out with the indices of that
    same palette.
    """
    if with_it is None:
        return False
    (_, _, _, before), above_before = without_it
    (_, _, _, now), above_now = with_it
    return (above_before == above_now
            and before["presupuesto"] == now["presupuesto"]
            and before["fusionados"] == now["fusionados"])


def _bake_unless_cgram_moves(renderer, game_map, map_id, without_baked,
                             baked):
    """Bakes `baked` and returns (layers, baked): the baked ones if the
    CGRAM split didn't move, and otherwise those of `without_baked`, with none.
    See `_same_cgram_split`."""
    bake_into_map(game_map, baked)
    with_baked = converted_layers(renderer, game_map)
    if _same_cgram_split(without_baked, with_baked):
        return with_baked, baked
    print("  map %d: baking %d event(s) moved its CGRAM split, "
          "so they are drawn" % (map_id, len(baked)))
    for cell, _tile in baked.values():
        game_map.upper_layer[cell] = rm2k.UPPER_BASE
    return without_baked, {}


def bake_into_map(game_map, bakeable):
    """Puts the tile of each baked event into the map's upper layer.

    It is done on the `game_map` and not on the drawn image, and that solves
    three things at once: the layers are drawn from here —so the drawings of
    the ChipSet animation come out baked too—, the layer cache key carries the
    upper layer, so it changes by itself, and the cell's passability is
    resolved by `passability_map` with the tile's bits, which are the same the
    event's row imposed.
    """
    for cell, tile in bakeable.values():
        game_map.upper_layer[cell] = tile

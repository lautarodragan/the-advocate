"""A whole map, converted: its layers, its sprites, its blocks and its VRAM
layout, gathered into the `map_info` that the emission reads; and the
conversion of the layers of all maps in parallel, before `convert_map` asks
for them.
"""

import contextlib
import multiprocessing
import os
import sys

from port import compiler, events
from rpgmaker import lcf
from rpgmaker import rm2k
from port import animation as animation_mod
from port import picture
from port.adeleine import CELL
from port.snes_format import BYTES_PER_TILE, cgram_word
from rpgmaker.rm2k import collect_npcs, passability_map
from render.render_map import build_passability
from port.map_layers import BG_PALETTES, _layers_in_memory, converted_layers
from port.sprites import (INITIAL_POSE, OBJ_PALETTES, block_tile,
                          build_characters, changes_graphic,
                          character_palette, discard_warning, drawable_npcs,
                          map_poses, movable_events, pose_bank,
                          separate_from_hero, sprite_colors)
from port.obj_extras import (map_animation, map_palette_cap,
                             map_shows_animation, picture_of_image,
                             rain_drops, timer_colors_of, timer_digits)
from port.baking import (_bake_unless_cgram_moves, bake_into_map,
                         bakeable_events)
from port.vram import WINDOW_H, WINDOW_W, vram_layout
from port.blocks import BLOCK_BYTES, build_blocks
from port.map_record import (NPC_MAX, ROUTE_GFX_MAX, TURN_NONE, anim_bytes,
                             ev_pos_bytes, npc_table)
from port.game_scan import images_of, map_start
from port.options import map_order
from port.cases import case_commands, test_graphics, test_maps


def precompute_layers(renderer, map_ids, args):
    """The layers of all maps, converted in parallel before `convert_map` asks
    for them.

    It is the most expensive part of a cold build —or of a warm one after
    touching a source of `map_layers._layers_version`, which invalidates the
    stored layers— and each map is
    independent, so there is one process per map. The processes fork with all
    the state already built, prepare the map like `convert_map` does and return
    what they computed with its key; `convert_map` then asks for the same key.
    **A map prepared differently here than there doesn't give a different
    ROM**: it gives another key, and `convert_map` computes it as always.
    """
    if len(map_ids) < 2:
        return
    global _to_precompute
    _to_precompute = (renderer, args)
    processes = min(len(map_ids), os.cpu_count() or 1)
    with multiprocessing.get_context("fork").Pool(processes) as pool:
        for done_ones in pool.map(_map_layers, map_ids, chunksize=1):
            _layers_in_memory.update(done_ones)
    _to_precompute = None


_to_precompute = None


def _map_layers(map_id):
    """What `precompute_layers` does in each process: the same steps as
    `convert_map` up to its two calls to `converted_layers`."""
    renderer, args = _to_precompute
    try:
        # Quiet: whatever it has to say, `convert_map` says it, in order.
        with open(os.devnull, "w") as null, contextlib.redirect_stdout(null):
            game_map = renderer.load_map(
                os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
            separate_from_hero(renderer, game_map, args,
                               case_commands(args, map_id))
            converted_layers(renderer, game_map)
            baked = bakeable_events(renderer, game_map)
            if baked:
                bake_into_map(game_map, baked)
                converted_layers(renderer, game_map)
    except BaseException:
        # If it fails, let it fail in `convert_map`, which can say why.
        pass
    return _layers_in_memory


def convert_map(renderer, map_id, args):
    """A whole map: tiles, colors, sprites, collision and blocks."""
    game_map = renderer.load_map(
        os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    if args.cases and map_id == map_order(args)[args.start_index]:
        # The test page's event goes **first**: the ROM walks the events from
        # lowest to highest, and the test page has to run before the game's.
        # It builds the party the test starts with, and a map whose page
        # touches the party on entering —21 adds Talan— found it already
        # changed. It is an event without pages: nothing is drawn or compiled,
        # it only takes index 0 so that everything that numbers events after
        # reading the map numbers the same.
        empty = lcf.Event.__new__(lcf.Event)
        empty.id, empty.name, empty.x, empty.y, empty.pages = (
            0, "prueba", 0, 0, [])
        game_map.events.insert(0, empty)
    separate_from_hero(renderer, game_map, args,
                       case_commands(args, map_id))
    name = renderer.tree.map_names.get(map_id, "?")

    layers = converted_layers(renderer, game_map)
    if layers is None:
        sys.exit("can't find the chipset of map %d" % map_id)

    # And the layers again, with the opaque events baked into the map. **Both**
    # are converted and compared because baking adds colors to the
    # background: if that made it merge colors, or shifted the upper layer's
    # CGRAM split, what is seen in cells that have nothing to do with the
    # baking would change. In that case the map goes unbaked, which is the
    # usual. The second conversion isn't paid twice in a warm build: both stay
    # in the disk cache, with their key.
    without_baked = layers
    baked = bakeable_events(renderer, game_map)
    if baked:
        layers, baked = _bake_unless_cgram_moves(
            renderer, game_map, map_id, without_baked, baked)

    # The characters: the hero with its 12 poses because it walks, and each
    # NPC with the one its page declares. If an NPC uses the same character as
    # the hero, they share palette and tiles without anything having to be
    # done.
    #
    # The timer digits take one of the eight sprite palettes, so the ceiling
    # drops to seven. The events drawn with a chipset tile go in while they
    # fit under that ceiling.
    # Who is going to walk and which graphics the routes change to. It goes
    # **before** the palette split because a graphic of command 34 is one
    # more character and asks for a palette like anyone: splitting without
    # counting it, it would come in later and there might be no room.
    movable, route_graphics, animates_still, turning = movable_events(
        game_map, compiler.map_entry(args.scan, map_id))
    # And the ones from `--test-graphic`, which go only in the maps where
    # some case runs, and for the same reason their pages are compiled with
    # that map's context. They are added **after** the game's, which is the
    # order the real compilation numbers them in.
    if args.test_graphic and map_id in test_maps(args):
        for charset, index in test_graphics(args.test_graphic):
            if (charset, index) not in route_graphics:
                route_graphics.append((charset, index))
    if case_commands(args, map_id):
        # And the ones the test pages send walking, which don't come from
        # the map's pages: they have to be added by hand or the NPC would
        # walk with a single pose. It goes **before** the palette split: since
        # the palette is chosen over the poses that are seen, knowing who walks
        # is part of choosing the colors and not only of splitting the VRAM.
        # The event goes by its RM2k id and the same `MapEvents` the compilation
        # uses translates it.
        map_events = events.MapEvents(game_map)
        for cmd in case_commands(args, map_id):
            if cmd.code == events.MOVE_EVENT and cmd.parameters \
                    and cmd.parameters[0] != events.ROUTE_HERO:
                target = map_events.route_target(cmd.parameters[0])
                if target:
                    movable = movable | {target - 1}
    # And with that, which poses each graphic can show: it is what decides
    # over which pixels its fifteen colors are chosen. See `map_poses`.
    poses_by_graphic = map_poses(renderer, game_map, args.leaders,
                                 movable, turning, route_graphics,
                                 animates_still)

    # All eight, with or without the timer: its two colors fit in some
    # character's palette. Reserving one for it here took events away from
    # the map, because this number is the one that decides which ones are
    # drawn.
    #
    # **One less in the maps that show battle animations**, since 2026-09-12:
    # the box needs a whole palette just for it —its fifteen colors belong to
    # the animation and are overwritten when another starts— and maps 2 and
    # 3, which are the intro's, filled all eight. Without this the Emitter
    # Room scene was left without its drawing, which is exactly what was
    # being done. What it costs —which characters merge more colors— is said
    # by each map's report.
    sample_animation = map_shows_animation(
        game_map, renderer,
        case_commands(args, map_id))
    # The timer's colors are passed to the split and not only to the packing:
    # in a map that fills the eight palettes someone has to be chosen to lose
    # a color to make room for it, and that changes how that character is
    # quantized.
    timer_colors = ()
    if map_id in args.timer_maps:
        from port import window as window_mod
        timer_colors = sorted(timer_colors_of(window_mod.skin(
            args.game_dir, renderer.database)))
    singles = {c for c, n in getattr(args, "maps_per_character", {}).items()
               if n == 1}
    palette_cap = map_palette_cap(
        renderer, game_map, args.leaders, route_graphics, timer_colors,
        singles, poses_by_graphic, sample_animation)

    npcs, discarded, split = drawable_npcs(renderer, game_map,
                                           args.leaders, palette_cap,
                                           route_graphics,
                                           timer_colors,
                                           singles,
                                           poses_by_graphic)
    lent = split[5]
    if lent:
        print("  map %d: %d graphic(s) without a palette of their own, drawn "
              "with someone else's: %s" % (map_id, len(lent),
                                          ", ".join(sorted("%s:%d" % k for k in lent))))
    # A baked event that was drawn with someone else's palette can't be
    # hidden: the sprite and the background tile would show different colors
    # —the lent ones and the real ones— and covering it with the second
    # changes what is seen. So that one is unbaked and goes back to being a
    # sprite, with the lent colors: it looks as it would without the baking.
    # It is asked here and not in `bakeable_events` because the lent ones
    # come from the split, which runs after drawing the layers. The first was
    # `PawnDoorTop`, event 11 of map 37: until 2026-09-26 this was a
    # `sys.exit`.
    lent_baked = sorted(
        event for event in baked
        for npc in npcs
        if npc["event"] == event and (npc["charset"], npc["index"]) in lent)
    if lent_baked:
        print("  map %d: event %s is drawn with someone else's palette, so "
              "it isn't baked" % (map_id, ", ".join(str(e + 1)
                                                    for e in lent_baked)))
        for event in lent_baked:
            cell_idx, _tile = baked.pop(event)
            game_map.upper_layer[cell_idx] = rm2k.UPPER_BASE
        layers = without_baked
        if baked:
            layers, baked = _bake_unless_cgram_moves(
                renderer, game_map, map_id, without_baked, baked)
    (tile_data, cram, tilemap, summary), above_data = layers
    if baked:
        print("  map %d: %d opaque event(s) baked into the map: %s"
              % (map_id, len(baked),
                 ", ".join(str(e + 1) for e in sorted(baked))))
    for event, tile in discarded:
        discard_warning(
            "map %d: event %d, drawn with tile %s, doesn't fit in "
            "the %d sprite palettes and isn't drawn"
            % (map_id, event + 1, tile[len(rm2k.TILE_PREFIX):],
               palette_cap),
            changes_graphic(game_map.events[event]))
    # Who changes pose and therefore carries their twelve to the cartridge:
    # the leader candidates with a graphic and the NPCs that walk. In that
    # order, with the initial leader first, which is the order the rest
    # expects.
    actors_with_graphic = []
    for actor in args.leaders:
        a = renderer.database.actors[actor]
        if not sprite_colors(images_of(renderer, args, a.charset),
                             a.charset_index):
            continue            # not a single opaque pixel: it isn't drawn
        actors_with_graphic.append(actor)
    first = renderer.database.leader(args.leaders)   # (CharSet, index)
    animated = []
    for actor in actors_with_graphic:
        a = renderer.database.actors[actor]
        if (a.charset, a.charset_index) not in animated:
            animated.append((a.charset, a.charset_index))
    animated.sort(key=lambda pair: pair != first)   # the initial leader first
    for npc in npcs:
        if npc["event"] in movable \
                and (npc["charset"], npc["index"]) not in animated:
            animated.append((npc["charset"], npc["index"]))
    # And the graphics a command 34 changes to. They go to the bank for the
    # same reason as the ones that walk: after changing, the event keeps
    # walking, so it needs the twelve poses of the new graphic and not the one
    # its page declared.
    #
    # The ones without **a single opaque pixel** don't go in, and it isn't a
    # rare case: `nobodyhere` is 185 of the game's 437 commands 34. A
    # transparent CharSet has no colors, so it has no palette to ask of the
    # bank; and it isn't needed, because what the command does there is hide
    # the row. It is the same `sprite_colors` an actor without a graphic is
    # discarded with.
    graphic_visible = []
    for charset, index in route_graphics:
        # It is drawn if it has an opaque pixel **and** it made it into the
        # palette split. The second is almost always yes; when not, the
        # command hides it just like a transparent one, which is what the ROM
        # does with any graphic that didn't make it.
        graphic_visible.append(
            bool(sprite_colors(images_of(renderer, args, charset), index))
            and (charset, index) in split[1])
        if graphic_visible[-1] and (charset, index) not in animated:
            animated.append((charset, index))
    # And the ones that turn toward the hero: their twelve poses, to upload
    # the one facing it. They go at the end so as not to move anyone else's
    # index.
    for pairs in turning.values():
        for pair in sorted(pairs):
            if pair in split[1] and pair not in animated:
                animated.append(pair)
    off_route = [pair for pair, visible in zip(route_graphics, graphic_visible)
                 if not visible and sprite_colors(
                          images_of(renderer, args, pair[0]), pair[1])]
    for charset, index in off_route:
        discard_warning(
            "map %d: graphic %s:%d, which a route changes to, doesn't fit "
            "in the %d sprite palettes: that command hides the event instead "
            "of changing it" % (map_id, charset, index, palette_cap),
            # A command 34 **is** a graphic change, so it always counts.
            True)

    # The slots of the VRAM bank, one pose each: the hero in block 0 —if some
    # leader candidate has a graphic—, then each NPC that walks with its own,
    # and the still ones shared by (CharSet, index, pose), which never change.
    # An NPC that walks doesn't share even with an identical one: each changes
    # pose on its own.
    slots = []
    if actors_with_graphic:
        charset, index = animated[0]
        slots.append(("heroe", charset, index, INITIAL_POSE))
    for npc in npcs:
        if npc["event"] in movable:
            if npc["changes"]:
                # Two mechanisms on the same row: the cartridge's twelve poses
                # and the page's graphic. The ROM doesn't know both at once, so
                # **walking wins** and its graphic stops following the page. It
                # is the same it did before `collect_npcs` counted "nothing" as
                # a state —see `changes` there—, that is nothing that used to
                # work is lost.
                #
                # This was a `sys.exit`, and it was fine while no event asked
                # for it. Counting the "nothing" state, event 10 of map 8 asks
                # for it, and stopping because of that would be not building
                # the ROM over a detail of an NPC that walks.
                # What **does** follow the page is whether the row is visible:
                # that is bit 4 and it doesn't overwrite the tile. Without
                # separating them, an event that walks and appears with the
                # page never appeared, because the row starts hidden when on
                # loading the map no page qualifies. See `page_graphic` in
                # tools/runtime/event_pages.s.
                npc["aparece"] = True
                npc["changes"] = False
            slots.append((("ev", npc["event"]), npc["charset"],
                          npc["index"], npc["pose"]))
        else:
            # The pose of its row and, if the graphic follows the page, that of
            # each page: the ROM's refresh chooses between slots that are
            # already in VRAM.
            poses = [(npc["charset"], npc["index"], npc["pose"])]
            if npc["changes"]:
                poses += [g for g in npc["graphics"]
                          if g is not None and g[:2] not in npc["afuera"]]
            for key in poses:
                if key not in {r[0] for r in slots}:
                    slots.append((key,) + key)
    # The turn slot: one more pose, for the still one that turns toward the
    # hero. The still ones share a slot by (CharSet, index, pose), so turning
    # its own would also turn the others that use it; the one that turns
    # moves to this one while its page lasts. It is a single one because only
    # the event the hero triggered turns, and there is one at a time. The
    # ones that walk or animate don't need it: they have their own. See TURN
    # in events.py.
    still_turning = [npc for npc in npcs
                     if npc["event"] in turning
                     and npc["event"] not in movable
                     and any(pair in split[1]
                             for pair in turning[npc["event"]])]
    if still_turning:
        npc = still_turning[0]
        slots.append(("giro", npc["charset"], npc["index"], npc["pose"]))
    characters = list(animated)
    for _key, charset, index, _pose in slots:
        if (charset, index) not in characters:
            characters.append((charset, index))

    images = {}
    for charset, _index in characters:
        if charset not in images:
            # Through the renderer's loader, which also builds the CharSet of
            # an event drawn with a chipset tile.
            images[charset] = renderer.charsets.get(charset)
            if images[charset] is None:
                sys.exit("can't find CharSet %r" % charset)

    tiles, palettes, where, palette_of, char_colors = build_characters(
        images, characters, slots, split)
    # It is counted here and not inside because the message has to name the
    # culprit, which is the map. With `drawable_npcs` above this shouldn't
    # fail because of a tile anymore; if it fails it is because of the
    # CharSets.
    if len(palettes) > palette_cap:
        sys.exit("the map uses %d characters in %d palettes and there are %d "
                 "sprite ones" % (len(characters), len(palettes), palette_cap))
    banks = pose_bank(images, animated, char_colors)
    animated_index = {p: k for k, p in enumerate(animated)}
    # The table of command 34: for each graphic a route asks for, which entry
    # of `npc_poses` it is in and with which palette. $FF in the entry is
    # "hide the row", which is what a transparent CharSet does.
    route_gfx = [
        (animated_index[pair], palette_of[pair]) if visible else (0xFF, 0)
        for pair, visible in zip(route_graphics, graphic_visible)]
    # The timer, if this ROM carries it: its glyphs go at the end of the bank
    # and share a palette with whoever has room, which there almost always is.
    timer_base, timer_pal = 0, None
    if map_id in args.timer_maps:
        from port import window as window_mod
        sys_img = window_mod.skin(args.game_dir, renderer.database)
        tiles, timer_base, timer_pal = timer_digits(
            sys_img, tiles, palettes, split[3],
            palette_cap)
    rain_base, rain_pal = 0, 0
    if args.with_rain:
        tiles, rain_base, rain_pal = rain_drops(
            tiles, palettes, split[3],
            timer_base, palette_cap, timer_pal)
        if not rain_base:
            print("  map %d: WARNING, the raindrops don't fit in the "
                  "sprite palettes and it doesn't rain here" % map_id)
    # The `ShowPicture` picture, if its own belongs to this map. The slot is
    # chosen by `Pictures.choose` **in the order of the map table**, which is
    # this same loop.
    image_base, image_pal = 0, 0
    record = getattr(args, "pictures", None)
    if record is not None:
        info = record.choose([game_map])
        if info is not None and record.map_id is None:
            record.map_id = map_id
        if info is not None and record.map_id == map_id:
            tiles, image_base, image_pal = picture_of_image(
                info, tiles, palettes, rain_base or timer_base)
            if not image_base:
                sys.exit("map %d: the picture %r doesn't fit: the map already uses "
                         "the %d sprite palettes and the fade needs a whole "
                         "one. See `cartel_de_imagen`."
                         % (map_id, record.name, OBJ_PALETTES))
            print("  map %d: the picture %r, %d objects in %d tiles from "
                  "%d, palette %d" % (map_id, record.name,
                                      info["objetos"],
                                      picture.reserved_tiles(info),
                                      image_base, image_pal))
    # And the battle animation box, if some page of this map can show one that
    # is drawn. It goes last because it takes the end of the bank and the
    # palette left free after the picture. The criterion for it to fit is a
    # computation and the converter emits it: if there is no palette or no
    # VRAM, **this map doesn't draw animations** and says so.
    anim_base, anim_pal = 0, 0
    if sample_animation:
        trial, trial_base, trial_pal = map_animation(
            tiles, palettes, 1 if image_base else 0)
        if not trial_base:
            # Without a palette this map doesn't draw animations. It is the
            # same that is done with the raindrops: it is declared and it goes
            # on.
            print("  map %d: WARNING, battle animations aren't drawn "
                  "here: the map already uses the %d sprite palettes and the "
                  "box needs a whole one" % (map_id, OBJ_PALETTES))
        else:
            # The VRAM, instead, **stops**: whether it fits depends on the
            # tile layout and not on the palettes. It stopped because the
            # Python reference couldn't recompute it without redoing the whole
            # bank; without it, it could warn and go on, as with the palettes.
            count = len(trial) // 32
            try:
                layout = vram_layout(len(tile_data) // BYTES_PER_TILE, count,
                                     len(above_data[0]) // 32)
            except SystemExit:
                layout = None
            if layout is None or count > layout["sprites"][1]:
                sys.exit(
                    "map %d: shows battle animations and the %d tiles of its "
                    "box don't fit in the sprite bank: it spends %d of %d. "
                    "See `animacion_de_mapa`."
                    % (map_id, animation_mod.TILES, count,
                       layout["sprites"][1] if layout else 0))
            tiles, anim_base, anim_pal = trial, trial_base, trial_pal
            print("  map %d: battle animations are drawn in %d "
                  "tiles from %d, palette %d"
                  % (map_id, animation_mod.TILES, anim_base, anim_pal))
    # And the rows of the baked events start hidden: their tile is already
    # drawn in the map. The row is still whole —the event triggers, blocks the
    # way and is the target of a route like any other—, and `build_oam` skips
    # it without building an object, which is what is being saved.
    # `tile_pass` is left set on purpose: the cell is already resolved by the
    # map's table with the same bits, and if a page ever showed this row
    # again, the data it needs is there.
    for npc in npcs:
        if npc["event"] in baked:
            npc["visible"] = False
    table = npc_table(npcs, where, movable, animated_index, animates_still)
    # For each leader candidate, its palette and which pose bank its twelve
    # are in. The ROM computes nothing from the pose: it looks up the pointer
    # here and queues it.
    actors = []
    for actor in args.leaders:
        a = renderer.database.actors[actor]
        if actor not in actors_with_graphic:
            # An actor with an empty graphic. `DummyHero`, 10, is like that:
            # its eight poses don't have an opaque pixel, and RM2k draws
            # nothing. It goes with the sentinel pointer and the ROM skips the
            # object.
            actors.append((actor, 0, None, []))
            continue
        # Its colors, in the same order as the `lookup` its poses were packed
        # with: `character_palette` returns the sorted palette and
        # `build_characters` indexes 1..15 over it. If the two orders drifted
        # apart, the hero would come out with its colors swapped around.
        own, _, _ = character_palette(
            images[a.charset], a.charset_index)
        actors.append((actor, palette_of[(a.charset, a.charset_index)],
                       animated_index[(a.charset, a.charset_index)],
                       [cgram_word(c) for c in own]))
    turn_tile = (block_tile(where["giro"][0]) if "giro" in where
                 else TURN_NONE)
    sprite = (tiles, palettes, where, table, actors, timer_base, timer_pal,
              animated, banks, route_gfx, rain_base, rain_pal,
              turn_tile, image_base, image_pal, anim_base, anim_pal)

    # The collision: one byte per 16x16 cell with the four direction bits
    # already resolved. All of RM2k's logic —that the upper layer rules unless
    # it is decoration, that wall faces are always crossed— is decided here,
    # not on the console.
    chipset = renderer.database.chipsets[game_map.chipset_id]
    flags = build_passability(chipset)
    passable = passability_map(game_map, flags)
    # The cells with an NPC are left out: if the hero started on one, both
    # would have the same sort key and which one stays on top would depend on
    # a tie-breaker that has no reason to match between the console and the
    # render. With **all** the ones drawn on some page: a tile left out of the
    # palettes still takes space.
    used = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
    start_x, start_y = map_start(
        renderer, map_id, passable, game_map.width, game_map.height, used)
    collision = (passable, start_x, start_y, game_map.width, game_map.height)

    if len(table) > NPC_MAX:
        sys.exit("map %d has %d NPCs and %d fit in OAM"
                 % (map_id, len(table), NPC_MAX))
    if len(route_gfx) > ROUTE_GFX_MAX:
        sys.exit("map %d has %d graphics of command 34 and %d fit: see "
                 "ROUTE_GFX_MAX" % (map_id, len(route_gfx), ROUTE_GFX_MAX))

    print("Map %d %r: %dx%d cells of %dx%d px"
          % (map_id, name, len(tilemap[0]), len(tilemap),
             CELL, CELL))
    print("  %d distinct colors, %d in CGRAM of %d available, %d merged"
          % (summary["colores"], summary["usados"], summary["presupuesto"],
             summary["fusionados"]))
    print("  %d unique tiles of %d cells (%.0f%% reuse)"
          % (summary["tiles"], summary["celdas"],
             100.0 * (1 - summary["tiles"] / summary["celdas"])))

    print("  sprites: %d characters, %d slots, %d tiles in VRAM, %d palettes; "
          "%d with their twelve poses in the cartridge"
          % (len(characters), len(where), len(tiles) // 32, len(palettes),
             len(animated)))
    print("  %d NPCs with a CharSet out of %d events" % (len(table), len(game_map.events)))

    open_ones = sum(1 for b in passable if b == 0x0F)
    print("  collision: %d cells, %d open on all four sides (%.0f%%), "
          "the hero starts at (%d,%d)"
          % (len(passable), open_ones, 100.0 * open_ones / len(passable),
             start_x, start_y))

    print("  layer above the hero: %d tiles, %d colors in %d palette(s) "
          "from %d, %d merged"
          % (len(above_data[0]) // 32, len(above_data[1]) // 2,
             BG_PALETTES - above_data[3], above_data[3], above_data[4]))

    cells, blocks, block_pass, block_terrain, combos = build_blocks(
        game_map, tilemap, above_data[2], passable,
        game_map.width, game_map.height, chipset)
    print("  the map fits in %d 16x16 blocks for %d cells: %d B of "
          "grid plus %d B of table, against the %d B of the expanded tilemap"
          % (len(blocks) // BLOCK_BYTES, len(cells), 2 * len(cells),
             len(blocks), 2 * summary["celdas"]))
    windows_x = (len(tilemap[0]) + WINDOW_W - 1) // WINDOW_W
    windows_y = (len(tilemap) + WINDOW_H - 1) // WINDOW_H
    if windows_x > 1 or windows_y > 1:
        print("  it doesn't fit in the %dx%d window: the ROM is going to redraw"
              % (WINDOW_W, WINDOW_H))

    words = bytearray()
    for cell in cells:
        words += cell.to_bytes(2, "little")
    colors = bytearray()
    for word in cram:
        colors += word.to_bytes(2, "little")

    return {
        "id": map_id, "nombre": name,
        "tiles": tile_data, "cram": bytes(colors), "cram_words": cram,
        "tilemap": tilemap, "above": above_data, "sprite": sprite,
        # The graphics of command 34 as the pass that builds the bank numbered
        # them. `main()` compares against the ones it gathers compiling for
        # real: if the two passes drifted apart, the bytecode would carry
        # indices of a table that says something else.
        "graficos_de_ruta": route_graphics,
        "collision": collision, "celdas": bytes(words),
        "ev_pos": ev_pos_bytes(game_map),
        # Both grow while the pages are compiled, if some substitutes tiles:
        # see `Substitutions`. That is why they are mutable and are frozen
        # only when emitted.
        "bloques": blocks, "pass": block_pass, "terreno": block_terrain,
        "combos": combos,
        # The terrain of a cell **outside the map**: `GetTerrainTag` uses the
        # ChipSet's index 0, that is the first autotile, and not that of any
        # cell. See `op_terrain`.
        "terreno_fuera": rm2k.terrain_of(chipset, 0),
        "layout": vram_layout(
            len(tile_data) // BYTES_PER_TILE,
            len(sprite[0]) // 32 if sprite else 0,
            len(above_data[0]) // 32),
        "resumen": summary,
        "anim": anim_bytes(summary["animacion"]),
        "imagenes_fondo": summary["imagenes"],
        # The whole map is stored because the events' pages can't be compiled
        # until all the maps are there: a `Teleport` translates map ids to
        # table indices.
        "game_map": game_map,
        # For the page table: where each (CharSet, index, pose) ended up in
        # the sprite bank, which events change graphic with the page and which
        # of their graphics were left out of the palettes.
        "where": where,
        # For the turn toward the hero: which entry of `npc_poses` the twelve
        # poses of each graphic are in, which is the page's +30.
        "giro_k": {pair: animated_index[pair] for pair in animated},
        "giran": set(turning),
        "cambian": {npc["event"] for npc in npcs if npc["changes"]},
        # And the ones that only appear and disappear with it: the ones that
        # walk, whose graphic was pinned further up.
        "aparecen": {npc["event"] for npc in npcs if npc.get("aparece")},
        "afuera": {npc["event"]: npc["afuera"] for npc in npcs},
    }

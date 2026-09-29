#!/usr/bin/env python3
"""Converts an A Blurred Line map into data the SNES PPU consumes.

Splitting colors into palettes, and merging the least used ones when they
don't fit, lives in `allocator.py`, and reusing mirrored tiles in Voodoo.
What is left here is what depends on the hardware:

  * **Color is 15 bits, five per channel.** Of the 72 colors in the render of
    Map0007, 60 survive.
  * **The background goes in mode 3, at 8 bits per pixel.** There each pixel is
    a direct index into CGRAM and there is no per-tile palette, so the problem
    of splitting the colors into groups simply does not exist. With 4 bits and
    8 palettes, Map0007 lost 32 of its 60 colors; with 8 bits it loses none.

    It costs twice the VRAM per tile, 64 bytes instead of 32. With 92 tiles
    that is 5.8 KB of the 64 available, so it is not a real constraint.
  * **The tile format is planar**, not packed in nibbles: each bit of a pixel
    lives in a different bitmap, in pairs and 16 bytes at a time. That is why
    a 4-bit tile is exactly the first half of an 8-bit one.

Indices are kept to the lower half of CGRAM. Sprites always use palettes 8 to
15, that is indices 128 to 255, and at 8 bits the background reaches up to
255: staying low avoids stepping on them.

Usage:
    rm2k-snes-convert --map-id 7 -o rom/build/inc/mapdata.inc

With a test page, which is the list of RM2k commands from a file in
`rom/pruebas/casos/`; several in one cartridge, each one after a `--case`, and
the cartridge flags before the first. The harness picks which one runs with
`Partida(case=k)`:
    rm2k-snes-convert -o … --map-id 6 \
        --test-commands rom/pruebas/casos/pan.json \
        --case --test-commands rom/pruebas/casos/pan-vuelve.json
"""

import collections
import contextlib
import multiprocessing
import os
import sys


# Run as a script —which is how the recipes run it—, Python puts this file's
# folder in `sys.path`, not `tools/`, which is where the packages are imported
# from. It is replaced instead of adding `tools/` next to it: with both, a bare
# `import eventos` would work and load a second copy of the module, distinct
# from `port.events`.
# `realpath` and not `abspath`: `just install` installs it on the PATH as
# a symlink, and the folder that matters is the one of the real file.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from rpgmaker import event_codes
from port import events
from rpgmaker import lcf
from rpgmaker import rm2k

# Translucent events carry their own graphic: see `rm2k.decorate_translucent`
# —baked against the background, dithered, or opaque—.
lcf.DECORATE_TRANSLUCENT = rm2k.decorate_translucent
# And the text boxes, rebuilt for the SNES window: see
# `lcf.REFIT_TEXTS` and `port/texts.py`.
from port import texts
lcf.REFIT_TEXTS = texts.refit_commands
from port import animation as animation_mod
from port import picture
from port import patches as patches_mod
from port import title as title_mod
from port import menus as menus_mod
from port import fullscreen
from port import end_game as end_game_mod
from port import screens as screens_mod
from port import scene as scene_mod
from port import constants
from common import settings
from common import project
from port.allocator import CELL
from port.snes_format import BYTES_PER_TILE, cgram_word
from rpgmaker.rm2k import TILE, collect_npcs, passability_map
from render.render_map import Renderer, build_passability, load_image
from common import environment
from rpgmaker import resources
from rpgmaker.resources import find_resource
from port.map_layers import BG_PALETTES, _layers_in_memory, converted_layers
from port.sprites import (INITIAL_POSE, OBJ_PALETTES, OBJ_PRIORITY,
                          OBJ_PRIORITY_ABOVE, block_tile, build_characters,
                          changes_graphic, character_palette, discard_warning,
                          drawable_npcs, map_poses, maps_per_character,
                          movable_events, pose_bank, separate_from_hero,
                          sprite_colors)
from port.obj_extras import (map_animation, map_palette_cap,
                             map_shows_animation, picture_of_image,
                             rain_drops, timer_colors_of, timer_digits)
from port.baking import (_bake_unless_cgram_moves, bake_into_map,
                         bakeable_events)
from port.vram import (SLOTS, WINDOW_H, WINDOW_W, _check_items_border,
                       _check_shop, _check_slots, _check_splits,
                       _check_target, items_border_first, vram_layout)
from port.message_window import convert_window, font_bytes
from port.blocks import (BLOCK_BYTES, SUB_MAX, Substitutions, build_blocks,
                         substitution_triples)
from port.materials import compress_blocks, decompress_frames
from port.map_record import (NPC_MAX, PARALLEL_MAX, ROUTE_EV_MAX,
                             ROUTE_GFX_MAX, TURN_NONE, anim_bytes,
                             ev_pos_bytes, npc_table)
from port.battle_animations import rom_animations
from port.battle_scenes import fallback_bytes, patch_uses, rom_scene
from port.battle_tables import rom_encounters
from port.music import (boot_frames, compile_music, inherited_songs,
                        rom_songs, separate_songs, write_msu)
from port.game_scan import (args_game_dir, drop_items, has_rain, images_of,
                            map_start, possible_items, possible_leaders,
                            possible_members)
from port.options import flags_parser, map_order
from port.cases import (case_commands, case_map, case_page, page_party,
                        split_cases, test_cases, test_graphics, test_maps)
from port.mapdata import emit


def precompute_layers(renderer, map_ids, args):
    """The layers of all maps, converted in parallel before `convert_map` asks
    for them.

    It is the most expensive part of a cold build —or of a warm one after
    touching this file, which invalidates the stored layers— and each map is
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


# How much each opcode takes, to walk the bytecode without running it. The
# variable-length ones go with None and are measured separately.
# The bytecode walk lives in events.py, with the length table: there was a
# copy here and the one there went stale without anyone seeing it.
walk_code = events.walk_code


def main():
    project.from_command_line()
    parser = flags_parser()
    argv, stretches = split_cases(sys.argv[1:])
    args = parser.parse_args(argv)
    if args.map_id is None:
        parser.error("--map-id is missing, the boot map")
    environment.from_arguments(args, "game_dir", "rtp_dir", "soundfont",
                               "cache")
    args.game_dir = environment.game()
    args.cases = test_cases(parser, args, stretches)
    order = map_order(args)
    if not 0 <= args.start_index < len(order):
        sys.exit("--start-index %d but there are %d maps" % (args.start_index, len(order)))
    for case in args.cases:
        case.run_map = case_map(case, order, args.start_index)
    file_commands = case_commands(args)
    # Which maps carry the timer digits, which cost a sprite palette.
    # Normally, all: it is what the game asks for, where the countdown starts
    # in one map and is seen in the following ones. With `--no-timer`, the
    # maps where a case that touches it runs: until step 9e one was enough for
    # every map of the cartridge to carry them, and in the single cartridge of
    # 9f that took the palette away from every map —measured, fifteen goldens
    # moved—. A map without digits doesn't draw them: `TIMER_BASE` at zero,
    # see `timer_oam`.
    args.timer_maps = set(order) if not args.no_timer else {
        case.run_map for case in args.cases
        if any(cmd.code == events.TIMER_OPERATION for cmd in case.commands)}

    renderer = Renderer(args.game_dir)

    # The hero's graphic comes from the party, not from here. In RM2k the
    # first of the list gives it, and this game starts with actor 10
    # —'DummyHero', which is Chubby2[2]—. Until now there was a hand-set
    # default that gave Future1[0], that is another character's sprite.
    # --charset stays to force it by hand when needed.
    party = args.party if args.party else renderer.database.party
    if args.charset is None:
        args.charset, table_index = renderer.database.leader(party)
        if args.charset_index is None:
            args.charset_index = table_index
    if args.charset_index is None:
        args.charset_index = 0

    # The leader candidates are computed with all the ROM's maps together,
    # because the party is global state: a page of map A can add someone who
    # then walks around map B.
    args_game_dir[0] = args.game_dir
    every = map_order(args)
    # **The indices go before anything that compiles a page**, and
    # `possible_leaders` compiles pages. They were after, and the price was
    # concrete: without `index_variables`, no `ControlVars` compiles, so
    # `RaceController1` of map 49 —which starts with a `PlayBGM` and goes on
    # with two `ControlVars`— didn't compile **in that pass** and did in the
    # real one. The actors it adds to the party were lost: `CarRED` didn't go
    # into the map's actor table and the chase's hero was drawn **with no
    # graphic**, that is the car wasn't visible. It is the same hole that was
    # already noted for the page counts, in another place.
    #
    # The variables of the whole game, with their slot.
    extra = events.command_variables(file_commands)
    if len(args.cases) > 1:
        # The one that picks the case: see `events.CASE_VARIABLE`. With a
        # single one it isn't needed, and that way that cartridge comes out
        # the same as before `--case`.
        extra.add(events.CASE_VARIABLE)
    events.index_variables(args.game_dir, extra)
    # And the battle animations, which `ShowBattleAnimation` compiles with its
    # timeline inside: see OP_ANIMATION.
    events.index_animations(args.game_dir)
    # And the common events, which `CallEvent` compiles in place.
    events.index_common_events(args.game_dir)
    events.index_battle_audio(args.game_dir)
    # And the inn terms, which `ShowInn` builds its greeting with.
    events.index_terms(args.game_dir)
    # And the equipment and skills of each actor of the LDB: it is what the
    # two actor branches with two operands answer. **Before
    # `possible_leaders`**, which compiles pages: see its comment.
    events.index_actors(args.game_dir)
    # And the (actor, skill) pairs of the whole game, with those of the test
    # pages: it is the operand of `ChangeSkills` and of the branch that asks
    # whether it knows one, so it goes before compiling anything, same as the
    # variables.
    events.index_skills(
        args.game_dir, events.command_skill_pairs(file_commands))
    args.leaders = possible_leaders(renderer, every, party)
    # And those of the party each test page continues with, behind: the test
    # can start with it in any map of the cartridge.
    for case in args.cases:
        test_party = page_party(case, party)
        if test_party:
            for actor in possible_leaders(renderer, every, test_party):
                if actor not in args.leaders:
                    args.leaders.append(actor)
    # If some map sets rain, all of them carry the drops: see `has_rain`.
    args.with_rain = has_rain(every, file_commands)
    # How many maps of this ROM each character appears in. The palette split
    # uses it to choose who can lose a color without breaking anything: the
    # pose bank is **the whole ROM's**, so a character that is in two maps has
    # to be quantized the same in both. Quantizing it differently doesn't give
    # an ugly image but a `sys.exit` when emitting, which is what happened the
    # first time this was written: `Future1:4` dropped in one map and not in
    # the other.
    args.maps_per_character = maps_per_character(renderer, every,
                                                 args.game_dir)
    # The `ShowPicture` picture, one per ROM: see `events.Pictures`. The first
    # map of the table that shows it keeps it, which is the order `convert_map`
    # walks them in.
    args.pictures = events.Pictures(args.game_dir)
    args.pictures.map_id = None
    # And the slots `ChangeSpriteAssociation` reserves in the graphics table
    # of **all** maps, for the same reason as the picture: the graphic it gives
    # an actor crosses the teleport, so its index has to mean the same in both
    # maps. See `events.sprite_associations`.
    #
    # The test pages' ones come in through the same door: if they went by
    # `--test-graphic` they would have an index only in the maps where a
    # case runs, and what the command does —crossing the teleport— couldn't
    # be tested.
    args.associations = events.sprite_associations(
        [lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % m))
         for m in every], file_commands)

    precompute_layers(renderer, every, args)
    maps = [convert_map(renderer, map_id, args) for map_id in every]
    # The maps whose upper layer started higher than the window's palette used
    # to be reconverted here, to squeeze their background below it. With the
    # window in palette 0 there is nothing to squeeze: each map's background
    # starts at `CGRAM_RESERVED` and reaches up to its own upper layer,
    # without depending on what the other maps of the ROM need.
    # Teleports are resolved when all the maps are there: one can lead to any
    # other, so the destination index isn't known until the end.
    indices = {map_info["id"]: number for number, map_info in enumerate(maps)}

    # The blocks the map's `TileSubstitution`s are going to need, built
    # **before** compiling any page: see `Substitutions`. A map without that
    # command builds nothing and doesn't grow a byte, which is the case of the
    # game's 328 maps as of today.
    for map_info in maps:
        chipset = renderer.database.chipsets[map_info["game_map"].chipset_id]
        map_info["sustituciones"] = Substitutions(
            map_info, build_passability(chipset), chipset)
        # It hangs from the map so it reaches `events.MapEvents`, which is what
        # the compiler already passes around.
        map_info["game_map"].substitutions = map_info["sustituciones"]
        triples = substitution_triples(map_info["game_map"], args.cases,
                                       map_info["id"])
        for absent in map_info["sustituciones"].close(triples):
            # It doesn't stop the conversion: the page that asks for it
            # doesn't compile, which is what any command that can't be run
            # does. But it is said, because from outside it looks like an
            # event that does nothing.
            #
            # The two reasons a substitution can't be built, and both are
            # fixed on the data side: either the new tile isn't drawn in any
            # cell of the map —and then its 8x8s didn't go into VRAM—, or the
            # combination that would be needed carries an upper tile **without
            # the "Above" bit**, which isn't drawn on BG2 but baked into the
            # background, and then the block's two layers stop being
            # independent. See `Substitutions._bakes`.
            print("  map %d: TileSubstitution %d -> %d on the %s layer: the "
                  "block that would be needed can't be built. Either the new "
                  "tile isn't drawn in any cell of the map, or one of the two "
                  "is an upper tile without 'Above' and is baked into the "
                  "background. The page doesn't compile."
                  % (map_info["id"], absent[1], absent[2],
                     "upper" if absent[0] else "lower"))

    # The text block belongs to the whole ROM and is built while the pages
    # are compiled: each `ShowMessage` leaves its text here and takes an
    # offset, which is what goes in the bytecode.
    messages = events.Messages(step=events.MESSAGES_STEP)
    # The songs the pages' PlayBGMs ask for, numbered in the order they
    # appear. The ROM carries a single one —see `Songs`— and picks it further
    # down, when all are compiled and it is known which ones are asked for.
    songs = events.Songs()
    # And the troops the EnemyEncounters ask for. It doesn't number anything
    # —the bytecode carries the RM2k id— so it only says which enemy tables
    # have to be emitted. See `events.Troops`.
    troops = events.Troops()
    # The test pages' texts go **first**, before all the maps, and that isn't
    # aesthetic: that way their offset doesn't depend on how many texts the
    # map the ROM boots in brings nor on the order they are compiled in —the
    # first is 0—. They are stored here and the page's compilation, further
    # down, finds them stored, because the block deduplicates by content.
    for cmd, extra_lines in events.group_boxes(file_commands):
        if cmd.code == events.SHOW_MESSAGE:
            messages.add([cmd.string] + extra_lines)
    # The test pages already compiled, per case: see the second round.
    test_party = {}

    for map_info in maps:
        # The automatic events: their pages with the conditions, and the code
        # of the ones that can be run, all together in a single block.
        # One graphics registry per map: command 34 carries the index and the
        # map's `ruta_grafico` table resolves it. See `events.Graphics`.
        graphics = events.Graphics(args.associations)
        songs.current_map = maps.index(map_info)      # for its audio package
        pages = events.map_pages(map_info["game_map"], indices.get,
                                 messages, songs, graphics,
                                 args.pictures, troops)
        songs.current_map = None
        # One interpreter per event with some parallel page that compiles. The
        # ROM carries them in a fixed-cap list and **doesn't warn** if it goes
        # over —the extra ones wouldn't run and nothing would say so—, so the
        # stop goes here.
        with_parallel = {p["event"] for p in pages
                         if p["trigger"] == events.TRIGGER_PARALLEL
                         and p["codigo"]}
        if len(with_parallel) > PARALLEL_MAX:
            sys.exit("map %d has %d events with a parallel page and %d "
                     "fit: see PARALLEL_MAX"
                     % (map_info["id"], len(with_parallel), PARALLEL_MAX))
        if with_parallel:
            print("  map %d: %d event(s) with a parallel page"
                  % (map_info["id"], len(with_parallel)))
        if args.test_graphic and map_info["id"] in test_maps(args):
            for charset, index in test_graphics(args.test_graphic):
                graphics.index(charset, index)
        # **Only the map that took its tiles can show the picture.** The sprite
        # bank belongs to each map, so from another one the six objects would
        # read whatever was in those tiles. It doesn't happen today —the "1
        # year earlier" picture is shown by a single page— and that is why this
        # stops instead of choosing: the day two maps show the same one, it
        # has to be decided whether its tiles go in both, and the converter
        # can't make that decision alone.
        if (args.pictures.name is not None
                and map_info["id"] != args.pictures.map_id):
            for test_page in pages:
                code = test_page["codigo"]
                if code and any(code[i] == events.OP_PICTURE
                                for i, _c in events.walk_code(code)):
                    sys.exit(
                        "map %d: shows the picture %r and its tiles ended up in "
                        "map %d; the ROM carries it in a single one. See "
                        "`cartel_de_imagen`."
                        % (map_info["id"], args.pictures.name,
                           args.pictures.map_id))
        if graphics.pairs != map_info["graficos_de_ruta"]:
            # The two passes compiled different things. It can't happen —both
            # use `map_pages` with the same text block— and if it did,
            # the bytecode would end up pointing at the wrong table without
            # anything saying so.
            sys.exit("map %d: the two passes numbered the route graphics "
                     "differently: %s against %s"
                     % (map_info["id"], graphics.pairs, map_info["graficos_de_ruta"]))
        # The pages of the cases that run in this map, compiled with its
        # context even though they will live in the boot map: see
        # `case_map`. They are put there in the second round, when all
        # are done.
        for k, case in enumerate(args.cases):
            if case.run_map == map_info["id"]:
                test_party[k] = case_page(case, map_info, songs, graphics,
                                          messages, indices,
                                          args.pictures)
        map_info["pages"] = pages
        # And which maps outside the ROM the ones that don't compile point to.
        #
        # A `Teleport` to a map that didn't make it cuts the whole page, and a
        # page that doesn't compile does **nothing**: neither the teleport nor
        # what came before. `event` has always said so in its comment, but
        # the count above doesn't tell this reason apart from the others a
        # page falls out for, and it is the only one that is fixed from
        # outside —adding the map— and not by touching the compiler. That is
        # how the elevator page of map 2 was overlooked, which was seen
        # opening and led nowhere because it ends up jumping to map 3.
        outside_of, how_many = set(), 0
        for test_page in pages:
            if test_page["codigo"] or test_page["trigger"] not in events.TRIGGERS \
                    or test_page.get("prueba"):
                continue        # the test page doesn't come from the game
            event = map_info["game_map"].events[test_page["event"]]
            missing = {cmd.parameters[0]
                       for cmd in event.pages[test_page["pagina"]].commands
                       if cmd.code == events.TELEPORT and cmd.parameters
                       and indices.get(cmd.parameters[0]) is None}
            if missing:
                outside_of |= missing
                how_many += 1
        if outside_of:
            print("  map %d: %d of those %s because of a teleport to a map "
                  "that didn't make it into the ROM: %s"
                  % (map_info["id"], how_many,
                     "doesn't compile" if how_many == 1 else "don't compile",
                     ", ".join(str(m) for m in sorted(outside_of))))
        # Debts are warned about. A page that is accepted without doing
        # everything it asks for is a difference from the original game, and
        # keeping quiet about it is how it becomes invisible: here the command
        # and what is lost are named.
        debts = set()
        for event in map_info["game_map"].events:
            for page in event.pages:
                if page.trigger != events.TRIGGER_AUTOSTART:
                    continue
                # With the same text block as above: if it were None here, a
                # page with a text box wouldn't compile and its debt —a
                # PlayBGM, say— would go unwarned even though the ROM does run
                # it. Adding a text that is already there again doesn't grow
                # the block: the key is the content.
                if events.compile_page(page, indices.get,
                                       messages) is None:
                    continue
                debts |= set(events.page_debts(page,
                                               args.pictures))
        for cmd_code in sorted(debts):
            print("  map %d: WARNING, a page uses %s and the ROM doesn't do it; "
                  "see ACCEPTED_UNDONE in tools/port/events.py"
                  % (map_info["id"], event_codes.EVENT_CODES.get(cmd_code,
                                                                 cmd_code)))


    # The second round: with the pages of all the cases compiled, they are
    # put in the boot map and each map's block is built.
    for map_info in maps:
        pages = map_info["pages"]
        if args.cases and map_info is maps[args.start_index]:
            # The test pages, only in the map the ROM boots in. They don't come
            # from the game but from `rom/pruebas/casos/`: they exist because
            # there are interpreter paths no page of the game that compiles
            # exercises —the first was a wait—.
            #
            # It goes at **index 0**, that of the empty event `convert_map` put
            # at the start of the map: the ROM walks the events from lowest to
            # highest, and this page has to run before the game's. Until
            # 2026-09-17 it went at the first free index, at the end.
            #
            # **One page per case**, and page k asks for `CASE_VARIABLE` to
            # be at least k: see its comment. Page 0 asks for nothing, so a
            # single-case cartridge is the usual one.
            pages = pages + [{
                "event": 0, "pagina": k, "prueba": True,
                "trigger": events.TRIGGER_AUTOSTART,
                "switch_a": 0, "switch_b": 0, "actor": 0,
                "variable": ((events.variable_slot(
                    events.CASE_VARIABLE),
                    events.COMPARE_AT_LEAST, k) if k else None),
                "item": 0, "capa": 0,
                "frecuencia": events.ROUTE_FREQUENCY, "speed": 4,
                "codigo": test_party[k]} for k in range(len(args.cases))] + [{
                # And the one that turns it off: it asks for
                # `TEST_SWITCH` and has no code, so as soon as it wins,
                # the invented event no longer has an automatic page to run and
                # the first one doesn't repeat.
                "event": 0, "pagina": len(args.cases), "prueba": True,
                "trigger": events.TRIGGER_AUTOSTART,
                "switch_a": events.TEST_SWITCH, "switch_b": 0,
                "actor": 0, "variable": None, "item": 0, "capa": 0,
                "frecuencia": events.ROUTE_FREQUENCY, "speed": 4,
                "codigo": b""}]
        code = bytearray()
        for test_page in pages:
            test_page["offset"] = len(code)
            if test_page["codigo"]:
                code += test_page["codigo"]
            # And the commands of the own route, behind, one byte per command.
            own = test_page.get("ruta_propia")
            if own:
                test_page["ruta_offset"] = len(code)
                code += bytes(own["ordenes"])
        map_info["pages"] = pages
        # What each page of the events that change graphic draws, already as
        # OAM wants it: it is what the ROM copies to the NPC's row when the
        # active page changes. See `page_table`, +20.
        for test_page in pages:
            continues = test_page["event"] in map_info["cambian"]
            if not continues and test_page["event"] not in map_info["aparecen"]:
                continue
            graphic = test_page.get("grafico")
            if graphic is None \
                    or graphic[:2] in map_info["afuera"].get(test_page["event"], ()):
                continue
            if not continues:
                # The one that only appears carries no tile or attributes: its
                # own point to its slot of twelve poses and the ROM doesn't
                # touch them. The pose goes —with bit 7, which is "this page
                # draws something"— and what its tile imposes on the cell.
                test_page["oam"] = (0, 0, graphic[2] | 0x80,
                                 0xFF if test_page.get("tile_pass") is None
                                 else test_page["tile_pass"])
                continue
            block, slot = map_info["where"][graphic]
            tile = block_tile(block)
            priority = (OBJ_PRIORITY_ABOVE
                        if test_page["capa"] == rm2k.LAYER_ABOVE
                        else OBJ_PRIORITY)
            test_page["oam"] = (tile & 0xFF,
                             priority | ((slot & 0x07) << 1) | ((tile >> 8) & 1),
                             graphic[2] | 0x80,
                             0xFF if test_page.get("tile_pass") is None
                             else test_page["tile_pass"])
        map_info["evcode"] = bytes(code)
        # The ROM's substitution table has a fixed cap and **doesn't warn** if
        # it goes over: the pairs that don't fit wouldn't be applied and the
        # map would draw too much. How many entries it can end up having is
        # known here, and it is the number of distinct blocks some substitution
        # of the map uses as a key, because a key is never overwritten: the
        # second round changes its value. See `op_tile_sub` in
        # tools/runtime/interpreter_map.s.
        keys = len(map_info["sustituciones"].known_keys)
        if keys > SUB_MAX:
            sys.exit("map %d substitutes %d distinct blocks and the RAM "
                     "table carries %d: see SUB_MAX"
                     % (map_info["id"], keys, SUB_MAX))
        # How many distinct events this map can end up sending walking. The
        # ROM has ROUTE_EV_MAX slots and a route that finds no room is
        # discarded **without saying anything**: the NPC stays still and, if
        # the golden is taken like that, the test defends the error. With this
        # game's data the worst map uses two, so the check bothers nobody; it
        # is there so that a future change doesn't throw them away silently.
        #
        # The pages that **run** here: the map's and those of the cases that
        # jump to it, which live in the boot one. See `case_map`.
        run_here = [p["codigo"] for p in pages
                    if p["codigo"] and not p.get("prueba")]
        run_here += [test_party[k] for k, case in enumerate(args.cases)
                     if case.run_map == map_info["id"]]
        targets = {c[i + 1] for code in run_here
                   for i, c in walk_code(code)
                   if c[i] == events.OP_ROUTE and c[i + 1]}
        # And that nobody flashes someone who shares a graphic with another.
        # On the console the flash is done on the character's palette, so two
        # that share a graphic would flash together. `events.py` already
        # rejects the case of two events; here the one it can't see there is
        # covered, which is the hero's: which graphic it has depends on the
        # party, and the converter knows that and the compiler doesn't.
        #
        # `separate_from_hero` already avoids this in the maps whose pages flash
        # the hero. This stays for what that one doesn't see: a `FlashSprite`
        # that arrives inside a common event, which is compiled in place from
        # any `CallEvent` and isn't in the map's pages.
        graphics = collections.Counter(
            (npc["charset"], npc["index"])
            for npc in rm2k.collect_npcs(map_info["game_map"]))
        for actor in args.leaders:
            a = renderer.database.actors[actor]
            graphics[(a.charset, a.charset_index)] += 1
        for code in run_here:
            for i, c in walk_code(code):
                if c[i] != events.OP_FLASH or c[i + 1] != 0:
                    continue
                for actor in args.leaders:
                    a = renderer.database.actors[actor]
                    if graphics[(a.charset, a.charset_index)] > 1:
                        raise SystemExit(
                            "map %d: a page makes the hero flash, and "
                            "actor %d is drawn with %s[%d], which an NPC of "
                            "the map also uses. On the console they share a "
                            "palette and both would flash"
                            % (map_info["id"], actor, a.charset, a.charset_index))

        if len(targets) > ROUTE_EV_MAX:
            raise SystemExit(
                "map %d: its pages send %d distinct events walking and "
                "the ROM has %d route slots"
                % (map_info["id"], len(targets), ROUTE_EV_MAX))
        runnable = sum(1 for p in pages if p["codigo"])
        if pages:
            print("  map %d: %d automatic event page(s), %d runnable"
                  % (map_info["id"], len(pages), runnable))

    if not 0 <= args.start_index < len(maps):
        sys.exit("--start-index %d but there are %d maps" % (args.start_index, len(maps)))
    from port import window as window_mod
    skin = window_mod.skin(args.game_dir, renderer.database.system_name)
    font_id = renderer.database.font_id
    window_data = convert_window(skin, font_id)
    window_data["fuente"] = font_bytes(font_id)
    window_data["mensajes"] = messages.bytes()
    print("  message window: %d fixed tiles + %d of text, %d colors; "
          "font %d B, %d text box(es) in %d B"
          % (len(window_data["tiles"]) // 32,
             len(window_data["fondo"]) // 32,
             sum(1 for w in window_data["cram"] if w),
             len(window_data["fuente"]), len(messages.texts),
             len(window_data["mensajes"])))
    # The slots screen goes in every ROM: the save point opens it from inside
    # the game, and "Resume the Story" from the title when there is one. It is
    # drawn with the same font and the same skin as the message window, and
    # lives in the title's VRAM, where there is no map.
    # The actors that can be in the party when saving, to have their face and
    # their name in the cartridge: the starting ones and all the ones some
    # `ChangePartyMembers` of these maps adds, whether their pages compile or
    # not. It is a superset on purpose: one face too many costs 36 tiles and
    # one too few leaves a hole in the menu.
    members = possible_members(every, party, file_commands)
    # And the items that can be in the inventory, to carry their name and
    # their description: see "la pantalla de ítems" in menus.py.
    items_rom = possible_items(every, members, renderer.database,
                               file_commands)
    # With the letters of the medicines, which the actor choice writes with
    # the bank's glyphs: see `TARGET_WINDOWS`.
    medicine_letters = "".join(
        renderer.database.items[n].name for n in items_rom
        if renderer.database.items[n].type == lcf.ITEM_TYPE_MEDICINE)
    (slot_tiles, slot_palettes, slot_headers, slot_rows, slot_faces,
     slot_menu) = menus_mod.slots_screen(
        skin, renderer.database, SLOTS, renderer.database.font_id,
        members, args.game_dir, medicine_letters)
    target = menus_mod.borders(
        skin, 0, menus_mod.target_layers(skin, renderer.database,
                                           renderer.database.font_id),
        menus_mod.TARGET_CGRAM,
        menus_mod.TARGET_CGRAM + menus_mod.TARGET_COLORS_MAX)
    _check_target(len(target[0]))
    items_tiles, items_palettes, items_glyphs = menus_mod.items_screen(
        skin, renderer.database.font_id)
    # The item and equipment windows share tiles and colors: see
    # `menus.borders`.
    items_border = menus_mod.borders(
        skin, items_border_first(len(items_tiles)),
        [menus_mod.item_layers(skin), screens_mod.equipment_layers(skin)])
    _check_items_border(len(items_tiles), len(items_border[0]))
    # The shop's, with their own tiles and colors: see
    # `screens.TI_WINDOWS`.
    shop_border = menus_mod.borders(
        skin, 0, screens_mod.shop_layers(skin),
        menus_mod.ITEM_BORDER_CGRAM, menus_mod.TARGET_CGRAM)
    _check_shop(len(shop_border[0]))
    # The End Game screen's tiles go where the slots' do, so what is checked
    # is the same.
    end = end_game_mod.convert(skin, renderer.database, renderer.database.font_id)
    _check_slots(len(end[0]))
    slots_data = {"tiles": slot_tiles, "paletas": slot_palettes,
                  "cabeceras": slot_headers, "filas": slot_rows,
                  "caras": slot_faces,
                  "menu": slot_menu, "items": items_rom,
                  "db": renderer.database, "actores": members,
                  "relleno_textos": args.text_padding,
                  "items_db": renderer.database.items,
                  "items_tiles": items_tiles,
                  "items_paletas": items_palettes,
                  "items_glifos": items_glyphs,
                  "items_marco": items_border, "fin": end,
                  "tienda_marco": shop_border,
                  "objetivo": target}
    _check_slots(len(slot_tiles))
    _check_splits()
    print("  slots screen: %d, %d 4bpp tiles (%d B) + %d palettes, "
          "%d B of cells; %d actors with a face: %s"
          % (SLOTS, len(slot_tiles), len(slot_tiles) * 32,
             len(slot_palettes),
             (len(slot_headers) * len(slot_headers[0])
              + SLOTS * 4 * len(slot_rows[0][0][0])) * 2,
             len(slot_faces),
             ", ".join("%d %s" % (a, renderer.database.actors[a].name)
                       for a in sorted(slot_faces)) or "none"))
    title_data = None
    if not args.no_title:
        from PIL import Image
        name = renderer.database.title_name
        picture = Image.open(os.path.join(args.game_dir, "Title",
                                          name + ".png"))
        texts = title_mod.options(renderer.database)
        menu_tiles, menu_palette, menu_maps = title_mod.menu(
            skin, texts, renderer.database.font_id)
        # The image, compressed like the Game Over one, and with the menu's
        # colors below its own in the same stream: the whole CGRAM at once,
        # the menu's palette at the bottom because a 4-bit BG only reaches
        # those. The tiles' indices already come shifted from
        # `palette.convert`.
        below = list(menu_palette)
        below += [(0, 0, 0)] * (constants.MENU_CGRAM - len(below))
        screen = fullscreen.compressed(
            picture, constants.MENU_CGRAM, constants.COLORS, below)
        title_data = {"pantalla": screen,
                      "menu_tiles": menu_tiles, "menu_paleta": menu_palette,
                      "menu_tilemaps": menu_maps}
        print("  title screen %r: %d 8bpp tiles + %d colors, "
              "%d B in an LZ2 stream of %d B"
              % (name, screen["tiles"],
                 screen["colores"] - len(below), screen["crudo"],
                 len(screen["flujo"])))
        print("    menu (%s): %d 4bpp tiles (%d B) + %d colors, %d tilemap(s)"
              % (", ".join(repr(t) for t in texts), len(menu_tiles),
                 len(menu_tiles) * 32, len(menu_palette), len(menu_maps)))
    # The Game Over screen: the image the LDB's `System` names, in the game's
    # or the RTP's `GameOver/` —as RM2k looks for it—, compressed. It goes in
    # every ROM that finds it: any cartridge can lose a battle or run a
    # `GameOver`. See tools/port/fullscreen.py.
    game_over_data = None
    path = find_resource([args.game_dir, resources.RTP_DIR], "GameOver",
                         renderer.database.gameover_name)
    if renderer.database.gameover_name and path:
        from PIL import Image
        game_over_data = fullscreen.compressed(Image.open(path))
        print("  Game Over screen %r: %d 8bpp tiles + %d colors, "
              "%d B in an LZ2 stream of %d B"
              % (os.path.basename(path), game_over_data["tiles"],
                 game_over_data["colores"], game_over_data["crudo"],
                 len(game_over_data["flujo"])))
    # The battle animations the already emitted bytecode shows: their
    # prerendered frames go to the cartridge and the ROM uploads them by DMA.
    animations = rom_animations(maps, renderer)
    for number in sorted(animations):
        data = animation_mod.report(number, animations[number])
        print("  animation %d: %d frames of %dx%d, shrunk from %dx%d to %d%%,"
              " %d colors, %d B"
              % (data["animacion"], data["cuadros"], data["caja"][0],
                 data["caja"][1], data["original"][0], data["original"][1],
                 data["porciento"], data["colores"], data["bytes"]))
    # The random encounters of each map, which ask for their troops. They go
    # **before** those of the test pages, which go at the end: that way the
    # cartridge's troops are numbered by the maps and the invented one goes
    # last, which is the same `rom_songs` does with the map's song.
    # Asking for it first always gave it index 0, and with that no case of the
    # suite exercised that `scene_troop_backdrop` and `troop_id` are really
    # indexed. That is why `case_page` compiles without `Troops`.
    encounters = rom_encounters(maps, renderer.tree,
                                args.test_encounters, troops)
    how_many = sum(z["troop_n"] for z in encounters["zonas"])
    if encounters["registros"]:
        print("  random encounters: %d map(s), %d zone(s), %d troop(s)"
              % (len(encounters["registros"]), len(encounters["zonas"]),
                 how_many))
    for cmd in file_commands:
        if cmd.code == events.ENEMY_ENCOUNTER:
            troops.request(events.encounter_troop(cmd),
                           events.encounter_backdrop(cmd))
    # The battle's audio, with the indices it already got from `songs` while
    # the pages compiled. It is asked for again only to read them: `Songs`
    # numbers once and returns the same, and what was noted goes to the
    # battle's package and not to any map's.
    battle_audio = events.battle_audio(songs) if troops.ids else None
    # The backdrops and the battlers the cartridge's battles ask for, each one
    # once: the ROM composes them when each battle starts. See
    # tools/port/scene.py, which is where the reason and the budget are.
    scenes = rom_scene(renderer.database, troops, maps, renderer.tree,
                       encounters, args.game_dir)
    # The `.msu` is written after the audio, because it also carries the
    # quality sound effects: see `msu_asm`.
    for info in scenes["fondos"]:
        rom_tiles, rom_colors = fallback_bytes(info)
        msu_tiles, msu_colors = scenes["calidad"][info["numero"]]
        print("  battle backdrop %d %r: %dx%d, %d tiles from CGRAM entry %d; "
              "in the ROM %dx%d at 4bpp and %d colors (%d B), in "
              "the .msu 8bpp and %d colors (%d B)"
              % (info["numero"], info["nombre"], scene_mod.WIDTH,
                 scene_mod.HEIGHT, scene_mod.TILES, scene_mod.CGRAM_BASE,
                 scene_mod.FALLBACK_WIDTH, scene_mod.FALLBACK_HEIGHT,
                 len(info["respaldo"]["paleta"]),
                 len(rom_tiles) + len(rom_colors), scene_mod.COLORS,
                 len(msu_tiles) + len(msu_colors)))
    # And the ones that aren't in the ROM, with which one replaces them
    # without MSU-1.
    in_rom = {info["numero"] for info in scenes["fondos"]}
    outside = [k for k in range(len(scenes["juego"])) if k not in in_rom]
    if outside and scenes["fondos"]:
        print("  battle backdrops only in the .msu, which without MSU-1 fall "
              "back to %r: %s" % (scenes["fondos"][scenes["respaldo_de"][outside[0]]]
                                  ["nombre"], ", ".join(
                                      "%d %s" % (k, scenes["juego"][k])
                                      for k in outside)))
    for info in scenes["battlers"]:
        d = scene_mod.battler_report(info)
        print("  battler %r: %dx%d, %d B, %d colors of %d"
              % (d["clave"], d["ancho"], d["alto"], d["bytes"], d["quedan"],
                 d["colores"]))
    # The event pages of the troops some battle of the cartridge asks for,
    # with **all** the troops already asked for: the maps', the random
    # encounters' and the test pages'. See `events.TroopPages`, which is
    # also why their messages go to a separate block. With `songs`, because a
    # page's `PlaySound` sounds in the battle's package, which isn't built
    # yet: it is built further down.
    troop_pages = events.TroopPages()
    for number in troops.ids:
        if number in renderer.database.troops:
            troop_pages.compile(number, renderer.database.troops[number],
                                songs)
    print("  troop pages: %d of %d in %d distinct body(ies), %d B of "
          "code and %d B in %d message(s)"
          % (troop_pages.pages - troop_pages.left_out,
             troop_pages.pages, len(troop_pages.where),
             len(troop_pages.bodies), len(troop_pages.messages.data),
             len(troop_pages.messages.texts)))
    # The items the enemies of those troops drop can also reach the
    # inventory: see `drop_items`.
    slots_data["items"] = sorted(
        set(items_rom) | drop_items(renderer.database, troops.ids))
    compressed = compress_blocks(maps)
    report = emit(args.output, maps, args.start_index, args.hero_above, party,
                  window_data, title_data, slots_data,
                  args.pictures.info, animations, troops.ids, battle_audio,
                  scenes, encounters, troop_pages, compressed,
                  enemy_hp=args.enemy_hp,
                  game_over=game_over_data)
    # Which entries of their palette the timer digits use, one bit per entry
    # and one word per map, in the order of `map_table`. `upload_timer_pal`
    # uploads **those** again untinted and not the whole palette, because the
    # palette belongs to a character that is tinted. It goes separately and
    # not as a record field because the record is at exactly its 128. The
    # index is the same `index + 1` `timer_digits` painted the glyphs
    # with: the first one that has that color.
    timer_color_list = sorted(timer_colors_of(skin))
    masks = []
    for map_info in maps:
        sprite, mask = map_info["sprite"], 0
        if sprite and sprite[5]:
            palette = sprite[1][sprite[6]]
            for color in timer_color_list:
                mask |= 1 << (palette.index(color) + 1)
        masks.append(mask)
    with open(args.output, "a") as handle:
        handle.write('\n.segment "RODATA"\n.block %d\ntimer_mask:\n'
                     '    .word %s\n'
                     % (2 * len(masks),
                        ", ".join("$%04X" % m for m in masks)))
    if len(args.cases) > 1:
        # Where the harness writes the case number: see `--case`.
        with open(args.output, "a") as handle:
            handle.write("\nCASE_SLOT = %d\n" % events.variable_slot(
                events.CASE_VARIABLE))
    print("%d map(s) -> %s, boots at %d (map %d)"
          % (len(maps), args.output, args.start_index, maps[args.start_index]["id"]))
    # What the allocator decided, as images: to look at which colors were lost
    # and which palette each cell ended up in without building or running the
    # ROM. They are indexed and their indices are CGRAM entries, so an editor
    # in indexed mode opens them just as `tiles` is going to see them.
    allocator = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                             "asignador")
    os.makedirs(allocator, exist_ok=True)
    for map_info in maps:
        pictures = list(map_info["imagenes_fondo"]) + [("encima", map_info["above"][5])]
        for name, png in pictures:
            with open(os.path.join(allocator, "%04d-%s.png"
                                   % (map_info["id"], name)), "wb") as handle:
                handle.write(png)
    # And **what it decided to lose**, written down: which color was merged
    # with which in each layer. It goes next to the images because it comes
    # from the same decision, but it is something else: the images are for
    # looking at and this is for reading back and for the diff to warn. What
    # is versioned is in `rom/parches/`, and `just parches --check` compares.
    # See tools/port/patches.py.
    patches_dest = os.path.dirname(os.path.abspath(args.output))
    count, weigh = patches_mod.write_maps(patches_dest, maps)
    print("patches of %d map(s) -> %s (%d B)"
          % (count, patches_mod.MAPS_IN_BUILD, weigh))
    # And the other decision that is already written down: **at what size
    # each battle animation is drawn**. It comes from the same round above;
    # here it is joined with the name and the sheet the animation has in the
    # LDB, which nobody looks at to draw and are there so that the diff says
    # which one it is about.
    count, weigh = patches_mod.write_animations(
        patches_dest,
        [dict(animation_mod.report(number, animations[number]),
              nombre=events.ANIMATIONS[number].get("nombre", ""),
              hoja=events.ANIMATIONS[number].get("imagen", ""),
              lado=animation_mod.BOX)
         for number in sorted(animations)])
    print("patches of %d animation(s) -> %s (%d B)"
          % (count, patches_mod.ANIMS_IN_BUILD, weigh))
    # And **which fifteen colors each battler is reduced to**, which is the
    # decision the scene composed on the console brought: see
    # tools/port/scene.py.
    count, weigh = patches_mod.write_battlers(patches_dest,
                                              scenes["battlers"])
    print("patches of %d battler(s) -> %s (%d B)"
          % (count, patches_mod.BATTLERS_IN_BUILD, weigh))
    # And who asked for each one, which isn't versioned: it is what separates,
    # in the ROM that is played, what belongs to the game from what only
    # exists because of the suite.
    patches_mod.write_uses(patches_dest, patch_uses(
        maps, renderer.database, renderer.tree))
    if report:
        print("material compressed and shared between maps:")
        for line in report:
            print(line)

    # The music comes from here and not from a separate recipe.
    # `musicdata.inc` was global state as `mapdata.inc` was, with the
    # aggravating factor that nobody regenerated it: a ROM built for maps 4, 7,
    # 19 and 1 —which have no music— played the song of map 348, which was the
    # last one somebody had generated by hand. Emitting them together is the
    # only thing that guarantees both describe the same ROM.
    #
    # **All the songs** go, sharing a single sample bank, and the one of the
    # map the ROM boots in plays; the others are started by a `PlayBGM`, or
    # by the map that is entered if it brings its own —see `map_song_mute`
    # in tools/runtime/enter_map.s—. What rate each sample ends up at is
    # decided by the ARAM, package by package: see `Bank` in the `bank.rs`
    # of `rm2k-snes-audio`.
    music = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                         "musicdata.inc")
    requested, boot, title_song, map_song, game_over_song = (
        rom_songs(
            maps[args.start_index]["id"], songs, args.game_dir,
            renderer.database.title_music if not args.no_title else None,
            [m["id"] for m in maps],
            renderer.database.gameover_music if game_over_data else None))
    # The sound effects, in the order the compiled pages ask for them: the
    # maps are compiled in ROM order, so those of the map where it boots go
    # first —in the demo, the rain and the thunder of the opening—. Only the
    # ones that are in some package: one that isn't in any doesn't sound
    # anywhere —its row of `sound_table` stays at $FF— and building it would
    # cost the music, because the copies of `rm2k-snes-audio` count the
    # cartridge's sound effects. It happens with the route ones of
    # `se_route_left_out`.
    packed = {n for palettes_needed in songs.per_map.values()
              for n in palettes_needed["sonidos"]}
    requested_se = []
    for name, _v, _t, _b in songs.sounds:
        if name not in requested_se and name in packed:
            requested_se.append(name)
    # Each map's audio package, in the order of the map table: the songs its
    # pages can start —plus, in the boot one, the one that plays from the
    # start, and in all the map's own— and its sound effects, in the order
    # they appear, which is the priority the ROM uploads them with if they
    # don't all fit. See `package_load` in tools/runtime/audio_package.s.
    # They are built **before** the bank, by name, because each sample's
    # budget comes from them: see `Bank` in `rm2k-snes-audio`.
    packages, separate_ones = [], []
    for i, _map in enumerate(maps):
        palettes_needed = songs.per_map.get(i, {"temas": [], "sonidos": []})
        owned = list(palettes_needed["temas"])
        if i == args.start_index and boot != 0xFF and boot not in owned:
            owned.insert(0, boot)
        # And the map's own song, **in front**: it is the only one on the list
        # that surely plays on entering, so if the ARAM isn't enough for
        # everything it is the last one that has to fall. Without it in the
        # package, its samples would have to be uploaded by `song_ensure`
        # when starting it, rebuilding the whole package a second time.
        if map_song[i] != 0xFF:
            if map_song[i] in owned:
                owned.remove(map_song[i])
            owned.insert(0, map_song[i])
        # And the exit ones, separate and after the sound effects: the ones
        # the map starts only to leave have no reason to go in with its sound
        # effects. See `Songs.exit_songs`. Not the map's own nor the boot one:
        # those play on entering.
        out = [t for t in songs.exit_songs(i)
               if t in owned and t != map_song[i]
               and not (i == args.start_index and t == boot)]
        owned = [t for t in owned if t not in out]
        # And the separate ones, which don't go with the other songs either:
        # their `PlayBGM` uploads them with the package's sound effects. See
        # `separate_songs`.
        separate = [t for t in owned if requested[t] in separate_songs().get(
                      _map["id"], ()) and t != map_song[i]
                    and not (i == args.start_index and t == boot)]
        owned = [t for t in owned if t not in separate]
        separate_ones.append(separate)
        packages.append((owned, list(palettes_needed["sonidos"]), out))
    # And the battle's package, after the maps: the battle song and its sound
    # effects, which the ROM uploads when opening the battle and unloads when
    # closing it. It goes separately and not inside the map's package because
    # the battle song alone fills the ARAM; see `events.BATTLE_PACKAGE`.
    palettes_needed = songs.per_map.get(events.BATTLE_PACKAGE)
    if palettes_needed:
        packages.append((list(palettes_needed["temas"]), list(palettes_needed["sonidos"]), []))
        separate_ones.append([])
    package_names = ([str(m["id"]) for m in maps]
                     + (["pelea"] if palettes_needed else []))
    # And the Game Over screen's, last: its song alone and no sound effects.
    # The ROM uploads it with the screen black, before the fade in —see
    # `game_over_black` in tools/runtime/game_over.s—, and with a package of
    # its own it uploads only that: arriving with `song_ensure` would
    # rebuild the whole map package behind it, which is one more second of
    # black. For the allocation it is a one-song package, which doesn't lower
    # anyone's rate: its samples fit alone in the ARAM.
    game_over_package = 0xFFFF
    if game_over_song != 0xFF:
        game_over_package = len(packages)
        packages.append(([game_over_song], [], []))
        separate_ones.append([])
        package_names.append("gameover")
    per_name = [(name, owned, theirs, out, separate)
                for name, (owned, theirs, out), separate
                in zip(package_names, packages, separate_ones)]
    # And the title screen's, which isn't in the table: `song_ensure`
    # uploads its song with the boot map's package behind.
    if title_song != 0xFF:
        owned, theirs, _out = packages[args.start_index]
        per_name.append(("titulo", [title_song] + owned, theirs))
    inheritance = inherited_songs(songs, map_song, args.start_index,
                                  title_song, package_names,
                                  [owned for owned, _e, _s in packages],
                                  separate_ones, not_given=settings.value(
                                   "music", "jumps_that_never_happen",
                                   kind=list))
    # The music itself is `rm2k-snes-audio`'s: it gets what was decided
    # here —the songs, the sound effects, the packages—, and writes
    # `musicdata.inc`, `musica.json` —what `tools/audio/msu.py` and the
    # volume ceilings read of each song— and `audio.json`, what the rest of
    # this function needs from the music. The job stays next to them, so
    # the music of a cartridge can be rebuilt alone.
    # Each package's sound effects go by number and not by SRCN: several
    # share the directory's place, which is its business.
    job = {
        "songs": requested,
        "effects": requested_se,
        "packages": [{"name": name, "songs": list(owned),
                      "effects": list(theirs), "exits": list(out),
                      "separate": list(separate)}
                     for name, owned, theirs, out, separate
                     in per_name[:len(packages)]]
                    + [{"name": p[0], "songs": list(p[1]),
                        "effects": list(p[2])}
                       for p in per_name[len(packages):]],
        "inheritance": [[name, t] for name, t in inheritance],
        "measuring_headroom": args.measure_headroom,
        "system_songs": lcf.system_songs(
            os.path.join(args.game_dir, "RPG_RT.ldb")),
        "emit": {
            "packages": len(packages),
            "boot": boot,
            "title": title_song,
            "game_over": [game_over_song, game_over_package],
            "map_song": list(map_song),
            "sounds": [list(sound) for sound in songs.sounds],
            "start": args.start_index,
            "decompress_frames": decompress_frames(maps[args.start_index],
                                                   compressed),
        },
    }
    audio = compile_music(job, os.path.dirname(music))
    done_ones = audio["songs"]
    effects = {e["name"]: e for e in audio["effects"]}
    packages = [(owned, theirs, out)
                for owned, theirs, out, _separate in audio["packages"]]
    if palettes_needed:
        assert package_names[len(maps)] == "pelea", (
            "the battle's package has to end up at the index `emit` emitted "
            "as PAQUETE_BATALLA")
        print("  battle audio package: %d song(s), %d sound effect(s)"
              % (len(palettes_needed["temas"]), len(packages[-1][1])))
    # **And that the boot fits in `BOOT_FRAMES`**: the ROM waits until that
    # frame so that the loop always starts on the same one, and if uploading
    # the boot map's package took longer, it would come out later and the
    # tests —which count from there— would count wrong. See the comment on
    # `BOOT_FRAMES` in tools/runtime/far_ram.s.
    frames, in_package = audio["boot"]["frames"], audio["boot"]["bytes"]
    cap = boot_frames()
    if frames > cap:
        raise SystemExit(
            "the boot doesn't fit in BOOT_FRAMES: the boot map's package is "
            "%d B and with the map, the driver and the directory the "
            "computation gives %.0f frames, against %d. Raise BOOT_FRAMES in "
            "tools/runtime/far_ram.s, or shrink that package"
            % (in_package, frames, cap))
    print("  boot: the boot map's package is %d B, %.0f of "
          "the %d frames of BOOT_FRAMES" % (in_package, frames, cap))
    # The `.msu`: the quality backdrops and the quality sound effects, to read
    # them through the MSU-1 when it is there. It is always written, even if
    # the cartridge carries neither backdrops nor sound effects, because it is
    # also the file that turns on the MSU-1 for the tracks.
    write_msu(args.msu or os.path.join(os.path.dirname(os.path.abspath(
        args.output)), "datos.msu"), music, scenes["calidad"],
        audio, songs.sounds)
    for i, (owned, theirs, out) in enumerate(packages[:len(maps)]):
        if owned or theirs or out or separate_ones[i]:
            print("  audio package of map %d: %d song(s), %d sound effect(s)%s%s"
                  % (maps[i]["id"], len(owned), len(theirs),
                     ", and for exit %s" % ", ".join(done_ones[t]["name"]
                                                     for t in out)
                     if out else "",
                     ", and separate %s" % ", ".join(done_ones[t]["name"]
                                                     for t in separate_ones[i])
                     if separate_ones[i] else ""))
    if requested_se:
        print("  sound effects: %d, %d B in the cartridge"
              % (len(effects), sum(e["bytes"] for e in effects.values())))
    print("music -> %s: %s"
          % (music, ", ".join(t["name"] for t in done_ones)
             or "none, it comes out silent"))
    # The bank packing is not decided here: both files send everything to
    # RODATA, with a `.block` or a `.crossbank` in front of each piece, and
    # `rm2k-snes-assemble` spreads it into banks and writes the memory map
    # before running `ca65`.


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
    order = map_order(args)
    movable, route_graphics, animates_still, turning = movable_events(
        game_map, {m: i for i, m in enumerate(order)}.get,
        associations=args.associations)
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
        # `map_pages`: they have to be added by hand or the NPC would
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
            args.game_dir, renderer.database.system_name)))
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
        sys_img = window_mod.skin(args.game_dir, renderer.database.system_name)
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


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Converts an A Blurred Line map into data the SNES PPU consumes.

This is `main`: it reads the command line, asks the game what it needs to
know, converts each map and hands everything to the emission. Each part lives
in its own module of `port/`, one per piece that can be replaced alone:

    options             the flags, and the ROM's maps in table order
    cases               the test cases, split at each `--case`
    game_scan           what is deduced from the whole game: leaders, items
    map_convert         a whole map: what goes into `rm2k-snes-maps map`
                        and its `map_info`, from what comes back
      map_layers        the layers' answer, and the CGRAM constants
      sprites           who walks, the hero's flash, the object constants
      obj_extras        the timer's colors, and whether a map animates
      vram              the VRAM layouts
      blocks            `TileSubstitution` translated to 16x16 blocks
    message_window      the message window and the font
    battle_scenes       backdrops and battlers
    battle_animations   the battle animations
    stage               runs a part that is a program of its own:
                        `rm2k-snes-battle`, experience and encounters
    compiler            the event compiler, `rm2k-snes-events`: what goes
                        into its two calls and what comes back
    music               the job for `rm2k-snes-audio`, and the `.msu`
    mapdata             `emit`: the whole `mapdata.inc`
      map_record        the tables of each map
      materials         the data blocks and their LZ2 streams
      asm               `block` and `pointer`

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
import json
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
from rpgmaker.rm2k import TILE
from render.render_map import Renderer, build_passability
from common import environment
from rpgmaker import resources
from rpgmaker.resources import find_resource
from port.sprites import (OBJ_PRIORITY, OBJ_PRIORITY_ABOVE, block_tile,
                          maps_per_character)
from port.obj_extras import timer_colors_of
from port.vram import (SLOTS, _check_items_border, _check_shop, _check_slots,
                       _check_splits, _check_target, items_border_first)
from port.message_window import convert_window, font_bytes
from port.blocks import SUB_MAX, Substitutions, substitution_triples
from port.materials import compress_blocks, decompress_frames
from port.map_record import PARALLEL_MAX, ROUTE_EV_MAX
from port.battle_animations import rom_animations
from port.battle_scenes import fallback_bytes, patch_uses, rom_scene
from port import stage
from port import compiler
from port.music import (boot_frames, compile_music, inherited_songs,
                        rom_songs, separate_songs, write_msu)
from port.game_scan import (args_game_dir, drop_items, has_rain,
                            possible_items, possible_leaders,
                            possible_members)
from port.options import flags_parser, map_order
from port.cases import (case_commands, case_map, page_party,
                        split_cases, test_cases, test_graphics, test_maps)
from port.mapdata import emit
from port.map_convert import convert_maps


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
    # `possible_leaders` looks at which pages compile. They were after, and
    # the price was concrete: without the variables' slots no `ControlVars`
    # compiled **in that pass** —`RaceController1` of map 49 starts with a
    # `PlayBGM` and goes on with two `ControlVars`— and did in the real one.
    # The actors it adds to the party were lost: `CarRED` didn't go into the
    # map's actor table and the chase's hero was drawn **with no graphic**.
    #
    # Since 2026-09-29 the compiler is `rm2k-snes-events`, which answers
    # both in its first call: the whole game's indices —each variable's slot
    # and each (actor, skill) pair's bit, with those of the test pages—,
    # which pages of each map compile, and each map's pages as `convert_map`
    # needs them to know who walks. See `port/compiler.py`.
    extra = set()
    if len(args.cases) > 1:
        # The one that picks the case: see `events.CASE_VARIABLE`. With a
        # single one it isn't needed, and that way that cartridge comes out
        # the same as before `--case`.
        extra.add(events.CASE_VARIABLE)
    args.dump = compiler.dump_of(args.game_dir)
    # The boot map carries an event without pages at index 0 when there are
    # cases: see `convert_map`.
    args.test_event_map = every[args.start_index] if args.cases else None
    args.extra_variables = extra
    args.scan = compiler.scan(args.dump, every, file_commands, extra,
                              args.test_event_map)
    # The slots and bits, where the rest of the converter reads them; and
    # the slots `ChangeSpriteAssociation` reserves in the graphics table of
    # **all** maps: the graphic it gives an actor crosses the teleport, so
    # its index has to mean the same in both maps. See `associations` in
    # the crate.
    args.associations = compiler.apply_indices(args.scan)
    # And the battle animations, which `animation.py` draws.
    events.index_animations(args.game_dir)
    args.leaders = possible_leaders(renderer, every, party, args.scan)
    # And those of the party each test page continues with, behind: the test
    # can start with it in any map of the cartridge.
    for case in args.cases:
        test_party = page_party(case, party)
        if test_party:
            for actor in possible_leaders(renderer, every, test_party,
                                          args.scan):
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
    maps = convert_maps(renderer, every, args)
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
        triples = substitution_triples(map_info["game_map"], args.cases,
                                       map_info["id"])
        # The compiler gets each one already translated: see
        # `compiler.substitution_table`.
        map_info["triples"] = triples
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

    # The actors that can be in the party when saving, to have their face and
    # their name in the cartridge: the starting ones and all the ones some
    # `ChangePartyMembers` of these maps adds, whether their pages compile or
    # not. It is a superset on purpose: one face too many costs 36 tiles and
    # one too few leaves a hole in the menu.
    members = possible_members(every, party, file_commands)
    # The random encounters of each map, which ask for their troops. They go
    # after the maps' battles and **before** those of the test pages, which
    # go at the end: that way the cartridge's troops are numbered by the maps
    # and the invented one goes last, which is the same `rom_songs` does with
    # the map's song. Asking for it first always gave it index 0, and with
    # that no case of the suite exercised that `scene_troop_backdrop` and
    # `troop_id` are really indexed. That is why a test page compiles without
    # `Troops`. The compiler numbers them all, below.
    #
    # They come from `rm2k-snes-battle`, with the experience tables: it
    # reads the game from the same dump as `renderer.tree`, plus the nodes
    # the project added on top. Which actors fight is the party's, and which
    # troops the cartridge carries is the compiler's, so the one goes in the
    # request and the other comes back as a list, in the order they are met,
    # which goes to the compiler.
    written = stage.run("rm2k-snes-battle", "battle", "tables", {
        "party": list(members),
        "maps": [{"id": m["id"], "width": m["game_map"].width,
                  "height": m["game_map"].height} for m in maps],
        "encounter_steps": args.test_encounters,
        "tree_nodes": list(renderer.tree.added_nodes.values()),
    }, "--data", renderer.tree.dump)
    answer = json.loads(written["battle.json"])
    encounters = answer["encounters"]
    battle_tables = {"experience": written["experience.inc"],
                     "slots": answer["experience"]["slots"],
                     "encounters": written["encounters.inc"]}
    if encounters["records"]:
        print("  random encounters: %d map(s), %d zone(s), %d troop(s)"
              % (encounters["records"], encounters["zones"],
                 len(encounters["troops"])))
    # Every page of the cartridge, compiled: `rm2k-snes-events`'s second
    # call. What it fills while it compiles comes back with it —see
    # `port/compiler.py`—:
    #
    # * the text block, which belongs to the whole ROM: each `ShowMessage`
    #   leaves its text there and takes an offset. The test pages' texts go
    #   **first**, so their offset depends on nothing else;
    # * the songs the pages' `PlayBGM`s ask for and the effects, numbered in
    #   the order they appear, with what each map's audio package asks for;
    # * the troops the `EnemyEncounter`s ask for —the maps', then the random
    #   encounters', then the test pages'—, which say which enemy tables
    #   have to be emitted: the bytecode carries the RM2k number;
    # * each test page, compiled with the context of the map it runs in
    #   —see `case_map`—, which the second round puts in the boot map.
    picture = None
    if args.pictures.name is not None:
        picture = {"name": args.pictures.name,
                   "number": args.pictures.number,
                   "x": args.pictures.where[0], "y": args.pictures.where[1]}
    compiled = compiler.compile_cartridge(
        args.dump, maps, [(case.run_map, case.commands) for case in args.cases],
        file_commands, args.extra_variables, args.test_event_map, picture,
        {m: test_graphics(args.test_graphic) for m in test_maps(args)}
        if args.test_graphic else {},
        encounters["troops"])
    messages = compiler.messages(compiled["messages"]["data"],
                                 compiled["messages"]["count"])
    songs = compiler.songs(compiled)
    troops = compiler.troops(compiled)
    test_party = {}
    for k, code in enumerate(compiled["cases"]):
        if code is None:
            sys.exit("%s: the test page doesn't compile"
                     % args.cases[k].test_commands)
        test_party[k] = bytes.fromhex(code)

    for map_info in maps:
        entry = compiler.map_entry(compiled, map_info["id"])
        # The pages of the map's events: their conditions, and the code of
        # the ones that can be run.
        pages = compiler.pages(entry["pages"], map_info["game_map"])
        # And which substitutions they asked for, which are the keys of the
        # ROM's table: see `SUB_MAX`.
        for upper, old, new in entry["substitutions"]:
            map_info["sustituciones"].pairs(upper, old, new)
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
        # The graphics command 34 and `ChangeSpriteAssociation` carry by
        # index, with those of `--test-graphic` after: the map's
        # `ruta_grafico` table resolves them.
        graphics = [tuple(g) for g in entry["graphics"]]
        if graphics != map_info["graficos_de_ruta"]:
            # The two passes compiled different things. It can't happen —both
            # are `map_pages` with the same rules— and if it did, the bytecode
            # would end up pointing at the wrong table without anything
            # saying so.
            sys.exit("map %d: the two passes numbered the route graphics "
                     "differently: %s against %s"
                     % (map_info["id"], graphics, map_info["graficos_de_ruta"]))
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
        # and what is lost are named. The compiler says which, of the
        # automatic pages that compile.
        for cmd_code in entry["debts"]:
            print("  map %d: WARNING, a page uses %s and the ROM doesn't do it; "
                  "see ACCEPTED_UNDONE in tools/rm2k-snes/events"
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
    skin = window_mod.skin(args.game_dir, renderer.database)
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
    # The battle's audio, with the indices it got from `songs` while the
    # pages compiled: what was noted goes to the battle's package and not to
    # any map's.
    battle_audio = compiled["battle_audio"]
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
    # with **all** the troops asked for: the maps', the random encounters'
    # and the test pages'. The compiler compiled them with the rest, with
    # their messages in a separate block.
    troop_pages = compiler.troop_pages(compiled)
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
                  scenes, battle_tables, troop_pages, compressed,
                  party_common=compiler.party_common_events(compiled),
                  enemy_hp=args.enemy_hp,
                  game_over=game_over_data)
    # Which entries of their palette the timer digits use, one bit per entry
    # and one word per map, in the order of `map_table`. `upload_timer_pal`
    # uploads **those** again untinted and not the whole palette, because the
    # palette belongs to a character that is tinted. It goes separately and
    # not as a record field because the record is at exactly its 128. The
    # index is the same `index + 1` the timer's glyphs were painted with
    # —`timer_digits`, in `rm2k-snes-map-sprites`—: the first one that has
    # that color.
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
    # What Adeleine decided, as images: to look at which colors were lost
    # and which palette each cell ended up in without building or running the
    # ROM. They are indexed and their indices are CGRAM entries, so an editor
    # in indexed mode opens them just as `tiles` is going to see them.
    adeleine_dir = os.path.join(os.path.dirname(os.path.abspath(args.output)),
                             "adeleine")
    os.makedirs(adeleine_dir, exist_ok=True)
    for map_info in maps:
        pictures = list(map_info["imagenes_fondo"]) + [("encima", map_info["above"][5])]
        for name, png in pictures:
            with open(os.path.join(adeleine_dir, "%04d-%s.png"
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
    # `[sound_effects] route_effects_left_out`.
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
    # `musicdata.inc`, `musica.json` —what `rm2k-snes-msu` and
    # `rm2k-snes-volume-ceilings` read of each song— and `audio.json`, what
    # the rest of this function needs from the music. The job stays next to
    # them, so the music of a cartridge can be rebuilt alone.
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


if __name__ == "__main__":
    main()

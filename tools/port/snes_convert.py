#!/usr/bin/env python3
"""Converts an A Blurred Line map into data the SNES PPU consumes.

This is `main`: it reads the command line, asks the game what it needs to
know, converts each map and hands everything to the emission. Each part lives
in its own module of `port/`, one per piece that can be replaced alone:

    options             the flags, and the ROM's maps in table order
    cases               the test cases, split at each `--case`
    game_scan           what is deduced from the whole game: leaders, items
    map_convert         a whole map: what goes into `wally map`
                        and its `map_info`, from what comes back
      map_layers        the layers' answer
      sprites           the hero's flash, the objects' priorities
      obj_extras        whether a map draws a battle animation
      vram              the VRAM layouts, as `rm2k-snes-mapdata`
                        publishes them
    screen_stage        the screens, `rm2k-snes-screens`: the message
                        window and its font, the title's menu, the menus,
                        and the message boxes reflowed for the window
    battle_scenes       backdrops and battlers
    battle_animations   the battle animations
    stage               runs a part that is a program of its own:
                        `rm2k-snes-battle`, experience and encounters
    battle_stage        the battle's model and its text screen, from
                        `rm2k-snes-battle`
    compiler            the event compiler, `rm2k-snes-events`: what goes
                        into its two calls and what comes back
    music               the job for `rm2k-snes-audio`, and the `.msu`
    mapdata             `emit`: what goes into `rm2k-snes-mapdata emit`,
                        which writes the whole `mapdata.inc`

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
# `lcf.REFIT_TEXTS` and `port/screen_stage.py`.
from port import screen_stage
lcf.REFIT_TEXTS = screen_stage.refit_commands
from port import animation as animation_mod
from port import fullscreen
from port import scene as scene_mod
from port import constants
from common import settings
from common import project
from rpgmaker.rm2k import TILE
from render.render_map import Renderer
from common import environment
from rpgmaker import resources
from rpgmaker.resources import find_resource
from port.sprites import (OBJ_PRIORITY, OBJ_PRIORITY_ABOVE, block_tile,
                          maps_per_character)
from port import vram
from port.battle_animations import animations_request, rom_animations
from port.battle_scenes import (fallback_bytes, patch_uses, rom_scene,
                                scene_request, write_patch_uses)
from port import stage
from port import battle_stage
from port import compiler
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


# How many block pairs the ROM's substitution table can hold at once. It is
# `SUB_MAX` in tools/runtime/low_ram.s and it is written on both sides on
# purpose —the converter has to be able to refuse **before** emitting a map
# that doesn't fit—; the test `test_substitutions.py` compares the two.
SUB_MAX = 8

# How many events with a parallel page there can be at once in a map, and
# how many forced routes can be running at once on events: the ROM's caps,
# which it does not warn about. The same numbers go into the `.inc` from
# `record.rs` in `rm2k-snes-mapdata`, where the reasons are; the checks are
# here because they look at the compiled pages.
PARALLEL_MAX = 48
ROUTE_EV_MAX = 12


def patch_of_map(map_info):
    """A map's decision, as `rm2k-snes-patches` takes it: its colors, the
    budget the upper layer left and each layer's merges, in order. The
    summary is the one `map_layers.layers_answer` leaves."""
    summary = map_info["resumen"]
    merges = summary.get("fusiones", {})
    return {"id": map_info["id"], "name": map_info["nombre"],
            "colors": summary["colores"], "budget": summary["presupuesto"],
            "background": merges.get("fondo", []),
            "above": merges.get("encima", [])}


def patch_of_animation(number, info):
    """An animation's decision: the rectangle it is drawn at, and what it
    came from, from `animation.report`."""
    report = animation_mod.report(number, info)
    return {"number": number,
            "name": events.ANIMATIONS[number].get("nombre", ""),
            "sheet": events.ANIMATIONS[number].get("imagen", ""),
            "side": animation_mod.BOX, "size": report["caja"],
            "original": report["original"], "frames": report["cuadros"]}


def patch_of_battler(info):
    """A battler's decision: the palette that remained. `info` is the one
    `scene.battler` returns; of its merges only how many travel, because
    that is all that is written —see `battler_text` in
    `rm2k-snes-patches`—."""
    return {"key": info["clave"], "image": info["imagen"],
            "hue": info["tono"], "width": info["ancho"],
            "height": info["alto"], "colors": info["colores"],
            "palette": info["paleta"], "merges": len(info["fusiones"])}


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

    # The blocks the map's `TileSubstitution`s are going to need were built
    # by `wally`, **before** compiling any page: see
    # `substitutions.rs` there. A map without that command builds nothing
    # and doesn't grow a byte, which is the case of the game's 328 maps as of
    # today. The compiler gets each one already translated: see
    # `compiler.substitution_table`.
    for map_info in maps:
        for absent in map_info["missing_substitutions"]:
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
            # independent. See `bakes` in `substitutions.rs`.
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
    # and the invented one goes last, which is the same `rm2k-snes-audio cartridge`
    # does with the map's song. Asking for it first always gave it index 0, and with
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
        # And which substitutions they asked for: the blocks their pairs
        # start from are the keys of the ROM's table. See `SUB_MAX`.
        translated = {(t["upper"], t["old"], t["new"]): t["pairs"]
                      for t in map_info["substitution_table"]}
        map_info["sub_keys"] = set()
        for upper, old, new in entry["substitutions"]:
            pairs = translated.get((bool(upper), old, new))
            map_info["sub_keys"].update(pair[0] for pair in pairs or ())
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
        keys = len(map_info["sub_keys"])
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
    # The screens, all at once: the message window and its font, the slots
    # screen and the pause menu, the text screens with their windows, End
    # Game and the title's menu. See `port/screen_stage.py`.
    #
    # The slots screen goes in every ROM: the save point opens it from inside
    # the game, and "Resume the Story" from the title when there is one. And
    # the items that can be in the inventory, to carry their name and their
    # description.
    items_rom = possible_items(every, members, renderer.database,
                               file_commands)
    # The items the enemies of the cartridge's troops drop can also reach
    # the inventory: see `drop_items`. The menu bank's letters are those of
    # the medicines of `items_rom` alone.
    items_all = sorted(set(items_rom)
                       | drop_items(renderer.database, troops.ids))
    window_data, slots_data, title_menu, screen_texts, says, screens = \
        screen_stage.convert(args.game_dir, members, items_all, items_rom,
                             not args.no_title)
    window_data["mensajes"] = messages.bytes()
    print("  message window: %d fixed tiles + %d of text, %d colors; "
          "font %d B, %d text box(es) in %d B"
          % (len(window_data["tiles"]) // 32,
             len(window_data["fondo"]) // 32,
             sum(1 for w in window_data["cram"] if w),
             len(window_data["fuente"]), len(messages.texts),
             len(window_data["mensajes"])))
    for line in says:
        print(line)
    slots_data.update({"items": items_rom, "db": renderer.database,
                       "actores": members,
                       "relleno_textos": args.text_padding,
                       "items_db": renderer.database.items,
                       "textos": screen_texts})
    vram._check_splits()
    slot_tiles, slot_headers = slots_data["tiles"], slots_data["cabeceras"]
    print("  slots screen: %d, %d 4bpp tiles (%d B) + %d palettes, "
          "%d B of cells; %d actors with a face: %s"
          % (vram.SLOTS, len(slot_tiles), len(slot_tiles) * 32,
             len(slots_data["paletas"]),
             (len(slot_headers) * len(slot_headers[0])
              + vram.SLOTS * 4 * len(slots_data["filas"][0][0][0])) * 2,
             len(slots_data["caras"]),
             ", ".join("%d %s" % (a, renderer.database.actors[a].name)
                       for a in sorted(slots_data["caras"])) or "none"))
    title_data = None
    if title_menu is not None:
        name = renderer.database.title_name
        picture = os.path.join(args.game_dir, "Title", name + ".png")
        texts = title_menu["texts"]
        menu_tiles = title_menu["tiles"]
        menu_palette = title_menu["palette"]
        menu_maps = title_menu["tilemaps"]
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
        game_over_data = fullscreen.compressed(path)
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
    slots_data["items"] = items_all
    # The battle's model, `rm2k-snes-battle`'s second call: now that the
    # pages compiled it knows every troop and every (actor, skill) pair. See
    # `port/battle_stage.py`.
    battle_model = battle_stage.model(
        renderer.tree.dump, members, troops.ids, items_all,
        [pair for pair, _slot in sorted(events.SKILL_SLOT.items(),
                                        key=lambda x: x[1])],
        screen_stage.layout().ITEM_NAME_WIDTH)
    report, decompress_frames = emit(
        args.output, maps, args.dump, args.start_index, args.hero_above,
        party, screens, window_data["mensajes"], title_data and
        title_data["pantalla"], game_over_data, args.pictures.info,
        animations_request(animations), troops.ids, battle_audio,
        scene_request(scenes, troops.ids, renderer.database), battle_tables,
        compiled["troop_pages"], compiler.party_common_events(compiled),
        battle_model, items_all, members, args.text_padding,
        # Where the harness writes the case number: see `--case`.
        events.variable_slot(events.CASE_VARIABLE)
        if len(args.cases) > 1 else None,
        enemy_hp=args.enemy_hp, speed_keys=not args.no_speed_keys)
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
    # with which in each layer, at what size each battle animation is drawn,
    # and which fifteen colors each battler is reduced to. It goes next to the
    # images because it comes from the same decisions, but it is something
    # else: the images are for looking at and this is for reading back and
    # for the diff to warn. What is versioned is in the project's patches,
    # and `just parches --check` compares. **What travels is the decision**,
    # in a request: the text each one is written as, and what is done with
    # it afterwards, are `rm2k-snes-patches`'s.
    patches_dest = os.path.dirname(os.path.abspath(args.output))
    stage.hand_over("rm2k-snes-patches", "patches", {
        "maps": [patch_of_map(m) for m in maps],
        # The animations' come from the same round above; here they are
        # joined with the name and the sheet the animation has in the LDB,
        # which nobody looks at to draw and are there so that the diff says
        # which one it is about.
        "animations": [patch_of_animation(number, animations[number])
                       for number in sorted(animations)],
        # The battlers', from the scene composed on the console: see
        # tools/port/scene.py.
        "battlers": [patch_of_battler(info) for info in scenes["battlers"]],
    }, patches_dest)
    # And who asked for each one, which isn't versioned: it is what separates,
    # in the ROM that is played, what belongs to the game from what only
    # exists because of the suite. The converter is the one that knows, and
    # `rm2k-snes-patches` reads it.
    write_patch_uses(patches_dest, patch_uses(
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
    # What each map's package carries, which song may already be playing
    # when it loads, whether the boot fits and the `.msu` with the quality
    # backdrops and sound effects are `rm2k-snes-audio cartridge`'s: it gets
    # the songs and sounds the pages numbered, and reads the rest from the
    # dump and the project. It writes next to the ROM `musicdata.inc`,
    # `musica.json` —what `rm2k-snes-msu` and `rm2k-snes-volume-ceilings`
    # read of each song—, `audio.json`, `efectos.json` and the job it built,
    # so the music of a cartridge can be rebuilt alone. The `.msu` is always
    # written, even if the cartridge carries neither backdrops nor sound
    # effects, because it is also the file that turns on the MSU-1 for the
    # tracks.
    directory = os.path.dirname(os.path.abspath(args.output))
    stage.hand_over("rm2k-snes-audio", "rm2k-snes-audio", {
        "songs": compiled["songs"],
        "maps": [m["id"] for m in maps],
        "start": args.start_index,
        "title": not args.no_title,
        "game_over": bool(game_over_data),
        "decompress_frames": decompress_frames[args.start_index],
        "measuring_headroom": args.measure_headroom,
        # The quality backdrops are the emission's bytes: the stage only
        # puts them in their place in the `.msu`.
        "backdrops": [[tiles.hex(), colors.hex()]
                      for tiles, colors in scenes["calidad"]],
        "tree_nodes": list(renderer.tree.added_nodes.values()),
    }, "--out", directory,
        "--msu", args.msu or os.path.join(directory, "datos.msu"),
        "--data", renderer.tree.dump, "--project", project.directory(),
        *environment.as_flags("game_dir", "rtp_dir", "soundfont"),
        command="cartridge")
    # The bank packing is not decided here: both files send everything to
    # RODATA, with a `.block` or a `.crossbank` in front of each piece, and
    # `rm2k-snes-assemble` spreads it into banks and writes the memory map
    # before running `ca65`.


if __name__ == "__main__":
    main()

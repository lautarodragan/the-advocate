"""A whole map, converted: its layers, its sprites, its blocks and its VRAM
layout, gathered into the `map_info` that the emission reads.

**The conversion is `rm2k-snes-maps map`'s**, a Rust stage on the PATH
—`tools/rm2k-snes/maps/`—, one call per map: it reads the map from the
dump, draws and converts its layers, bakes the opaque events into them,
splits the object palettes and builds the sprite bank. What stays here is
what the stage gets from other domains —the event compiler's scan of the
map's pages, from which the stage says who walks, and which graphics the
routes change to; the test cases; the
timer's System, the picture and whether a battle animation is drawn— and
what the rest of the converter reads back: the `map_info`, with the NPC
table (`map_record`'s), the VRAM layout (`vram`'s) and the messages.
"""

import concurrent.futures
import json
import os
import sys

from port import compiler, events, stage
from rpgmaker import lcf
from rpgmaker import rm2k
from port import animation as animation_mod
from port import picture
from port.constants import CELL
from port.snes_format import BYTES_PER_TILE
from port.map_layers import BG_PALETTES, layers_answer
from port.sprites import block_tile, discard_warning, separate_from_hero
from port.obj_extras import map_shows_animation
from port import vram
from port.map_record import TURN_NONE
from port.options import map_order
from port.cases import case_commands, test_graphics, test_maps
from common import settings

STAGE = "rm2k-snes-maps"


def convert_maps(renderer, map_ids, args):
    """Every map of the cartridge, in table order.

    What each map asks the stage is built in order —the `ShowPicture`
    picture goes to the first map of the table that shows it—, the calls go
    in parallel, since each map is independent and they are the most
    expensive part of a build, and what each one answered is read back in
    order, which is the order its messages are printed in.
    """
    prepared = [_prepare(renderer, map_id, args) for map_id in map_ids]
    workers = min(len(prepared), os.cpu_count() or 1) or 1
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        answers = list(pool.map(lambda p: _run(renderer, p), prepared))
    return [_map_info(renderer, p, written, args)
            for p, written in zip(prepared, answers)]


def convert_map(renderer, map_id, args):
    """A whole map: tiles, colors, sprites, collision and blocks."""
    prepared = _prepare(renderer, map_id, args)
    return _map_info(renderer, prepared, _run(renderer, prepared), args)


class _Prepared:
    """A map as it goes to the stage: the map as the converter keeps it, and
    the request."""


def _prepare(renderer, map_id, args):
    game_map = renderer.load_map(
        os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
    test_event = bool(args.cases) and map_id == map_order(args)[args.start_index]
    if test_event:
        # The test page's event goes **first**: the ROM walks the events from
        # lowest to highest, and the test page has to run before the game's.
        # It builds the party the test starts with, and a map whose page
        # touches the party on entering —21 adds Talan— found it already
        # changed. It is an event without pages: nothing is drawn or compiled,
        # it only takes index 0 so that everything that numbers events after
        # reading the map numbers the same. The stage puts its own.
        empty = lcf.Event.__new__(lcf.Event)
        empty.id, empty.name, empty.x, empty.y, empty.pages = (
            0, "prueba", 0, 0, [])
        game_map.events.insert(0, empty)
    separate_from_hero(renderer, game_map, args,
                       case_commands(args, map_id))

    # Who is going to walk and which graphics the routes change to: it
    # comes from the compiler's first call, which walked the bytecode. Its
    # page records go to the stage as they came, and the stage answers who
    # walks, who animates still and who turns —`moves.rs`—.
    #
    # The graphics of command 34 come from the same pass and for the same
    # reason: an event that changes graphic needs the twelve poses of the new
    # graphic put in the cartridge, and that is decided before building the
    # bank. **The order has to be the same as the real compilation's**,
    # because the bytecode carries the index: what guarantees it is that both
    # passes compile the same pages, with the same text block.
    scanned = compiler.map_entry(args.scan, map_id)
    route_graphics = [tuple(g) for g in scanned["graphics"]]
    # And the ones from `--test-graphic`, which go only in the maps where
    # some case runs, and for the same reason their pages are compiled with
    # that map's context. They are added **after** the game's, which is the
    # order the real compilation numbers them in.
    if args.test_graphic and map_id in test_maps(args):
        for charset, index in test_graphics(args.test_graphic):
            if (charset, index) not in route_graphics:
                route_graphics.append((charset, index))
    also_walk = set()
    if case_commands(args, map_id):
        # And the ones the test pages send walking, which don't come from
        # the map's pages: they have to be added by hand or the NPC would
        # walk with a single pose. The event goes by its RM2k id and the
        # same `MapEvents` the compilation uses translates it.
        map_events = events.MapEvents(game_map)
        for cmd in case_commands(args, map_id):
            if cmd.code == events.MOVE_EVENT and cmd.parameters \
                    and cmd.parameters[0] != events.ROUTE_HERO:
                target = map_events.route_target(cmd.parameters[0])
                if target:
                    also_walk.add(target - 1)

    timer = None
    if map_id in args.timer_maps:
        from port import window as window_mod
        timer = window_mod.skin(args.game_dir, renderer.database).path
    # The `ShowPicture` picture, if its own belongs to this map. The slot is
    # chosen by `Pictures.choose` **in the order of the map table**, which is
    # the order maps are prepared in.
    shown = None
    record = getattr(args, "pictures", None)
    if record is not None:
        info = record.choose([game_map])
        if info is not None and record.map_id is None:
            record.map_id = map_id
        if info is not None and record.map_id == map_id:
            shown = {"name": record.name, "objects": info["objetos"],
                     "tiles": picture.reserved_tiles(info),
                     "cells": [[number, [v for line in cell for v in line]]
                               for number, cell
                               in sorted(picture.cells(info).items())]}
    singles = sorted(c for c, n in getattr(args, "maps_per_character",
                                             {}).items() if n == 1)
    dump = compiler.dump_of(args.game_dir)
    p = _Prepared()
    p.map_id, p.game_map, p.dump = map_id, game_map, dump
    p.route_graphics = route_graphics
    p.request = {
        "map": map_id,
        "map_files": compiler.map_files(dump),
        "chipset_files": compiler.chipset_files(dump),
        "names": [entry[1:] for entry in compiler.names([game_map])],
        "test_event": test_event,
        "leaders": list(args.leaders),
        "pages": scanned["pages"],
        "route_graphics": [list(g) for g in route_graphics],
        "also_walk": sorted(also_walk),
        "timer": timer,
        "rain": bool(args.with_rain),
        "picture": shown,
        "battle_animation": bool(map_shows_animation(
            game_map, renderer, case_commands(args, map_id))),
        "singles": [list(c) for c in singles],
        "palette_weight": settings.value("graphics", "palette_weight",
                                         kind=dict),
        "dither": rm2k.DITHER_PATTERN,
        # The `TileSubstitution`s that can run here, whose blocks the stage
        # builds before any page compiles —see `substitutions.rs` there—,
        # and the common events', which it only translates.
        "substitutions": [list(t) for t in substitution_triples(
            game_map, args.cases, map_id)],
        "common_substitutions": [list(t) for t in _common_substitutions(dump)],
    }
    return p


_COMMON = {}


def _common_substitutions(dump):
    """`compiler.common_substitutions`, read once per dump."""
    if dump not in _COMMON:
        _COMMON[dump] = compiler.common_substitutions(dump)
    return _COMMON[dump]


def substitution_triples(game_map, cases, map_id):
    """The `(upper layer, old, new)` of all the `TileSubstitution`s that can
    end up running in this map: those of its events and those of the test
    cases that start here —which live in the boot map but are compiled with
    this one's context, see `case_map`—."""
    triples = []
    lists = [page.commands
             for event in game_map.events for page in event.pages]
    lists += [case.commands for case in cases if case.run_map == map_id]
    for commands in lists:
        for cmd in commands:
            if cmd.code != events.TILE_SUBSTITUTION or len(cmd.parameters) < 3:
                continue
            triple = (bool(cmd.parameters[0]),
                      cmd.parameters[1], cmd.parameters[2])
            if triple not in triples:
                triples.append(triple)
    return triples


def _run(renderer, prepared):
    flags = ["--data", prepared.dump]
    for directory in renderer.search_dirs:
        flags += ["--search-dir", os.path.abspath(directory)]
    return stage.run(STAGE, "maps", "map", prepared.request, *flags,
                     raw=True)


def _key(slot):
    """A slot of the sprite bank by the key the rest of the converter knows
    it by."""
    if slot.get("hero"):
        return "heroe"
    if slot.get("turn"):
        return "giro"
    if "event" in slot:
        return ("ev", slot["event"])
    return (slot["charset"], slot["index"], slot["pose"])


def _npc(n):
    return {
        "event": n["event"], "x": n["x"], "y": n["y"],
        "charset": n["charset"], "index": n["index"], "pose": n["pose"],
        "layer": n["layer"], "blocks": n["blocks"], "speed": n["speed"],
        "animates": n["animates"], "visible": n["visible"],
        "changes": n["changes"],
        "graphics": [tuple(g) if g is not None else None
                     for g in n["graphics"]],
        "layers": n["layers"], "tile_pass": n["tile_pass"],
        "afuera": {tuple(k) for k in n["outside"]},
        "aparece": n["appears"],
    }


def _map_info(renderer, prepared, written, args):
    """What the stage answered, as the rest of the converter reads it, with
    its messages printed in the order the conversion said them."""
    map_id, game_map = prepared.map_id, prepared.game_map
    answer = json.loads(written["map.json"])
    for note in answer["notes"]:
        if note["kind"] == "discard":
            discard_warning(note["text"], note["stop"])
        elif note["stop"]:
            sys.exit(note["text"])
        else:
            print(note["text"])
    # The events baked into the map go into its upper layer here too: the
    # stage decided them, and the pages are compiled with this map.
    for _event, cell, tile in answer["baked"]:
        game_map.upper_layer[cell] = tile
    (tile_data, cram, tilemap, summary), above_data = layers_answer(written)
    s = answer["sprite"]
    animation = s["animation"]
    anim_base, anim_pal = 0, 0
    if animation is not None:
        # The VRAM **stops**: whether the box fits depends on the tile
        # layout and not on the palettes.
        count = animation["count"]
        try:
            layout = vram.vram_layout(len(tile_data) // BYTES_PER_TILE, count,
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
        anim_base, anim_pal = animation["base"], animation["palette"]
        print("  map %d: battle animations are drawn in %d "
              "tiles from %d, palette %d"
              % (map_id, animation_mod.TILES, anim_base, anim_pal))

    npcs = [_npc(n) for n in answer["npcs"]]
    where = {_key(slot): (block, palette)
             for slot, block, palette in s["place"]}
    animated = [tuple(k) for k in s["animated"]]
    animated_index = {p: k for k, p in enumerate(animated)}
    tiles = written[s["tiles"]]
    palettes = [[tuple(c) for c in p] for p in s["palettes"]]
    banks = {(charset, index): written[name]
             for charset, index, name in s["banks"]}
    timer_base, timer_pal = s["timer"] if s["timer"] else (0, None)
    rain_base, rain_pal = s["rain"]
    image_base, image_pal = s["image"]
    turn_tile = (block_tile(s["turn_block"]) if s["turn_block"] is not None
                 else TURN_NONE)
    actors = [(actor, palette, k, list(words))
              for actor, palette, k, words in s["actors"]]
    route_gfx = [tuple(r) for r in s["route_gfx"]]
    # The fourth is the NPC table, which is the emission's: see
    # `npc_table` in `rm2k-snes-mapdata`, which builds it from `objects`
    # and `npcs`, below.
    sprite = (tiles, palettes, where, None, actors, timer_base, timer_pal,
              animated, banks, route_gfx, rain_base, rain_pal,
              turn_tile, image_base, image_pal, anim_base, anim_pal)

    passable = summary["pasabilidad"]
    start_x, start_y = answer["start"]
    collision = (passable, start_x, start_y, game_map.width, game_map.height)
    route_graphics = prepared.route_graphics

    name = renderer.tree.map_names.get(map_id, "?")
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
          % (s["characters"], len(where), len(tiles) // 32, len(palettes),
             len(animated)))
    print("  %d NPCs with a CharSet out of %d events" % (len(npcs), len(game_map.events)))

    open_ones = sum(1 for b in passable if b == 0x0F)
    print("  collision: %d cells, %d open on all four sides (%.0f%%), "
          "the hero starts at (%d,%d)"
          % (len(passable), open_ones, 100.0 * open_ones / len(passable),
             start_x, start_y))

    print("  layer above the hero: %d tiles, %d colors in %d palette(s) "
          "from %d, %d merged"
          % (len(above_data[0]) // 32, len(above_data[1]) // 2,
             BG_PALETTES - above_data[3], above_data[3], above_data[4]))

    # The map in 16x16 blocks, which `rm2k-snes-maps` made with the layers.
    # Copies, because `Substitutions` grows them while the pages compile.
    made = summary["bloques"]
    cells = list(made["celdas"])
    blocks = bytearray(made["tabla"])
    block_pass = bytearray(made["pass"])
    block_terrain = bytearray(made["terreno"])
    combos = {(low, high): block for low, high, block in made["combos"]}
    print("  the map fits in %d 16x16 blocks for %d cells: %d B of "
          "grid plus %d B of table, against the %d B of the expanded tilemap"
          % (len(block_pass), len(cells), 2 * len(cells),
             len(blocks), 2 * summary["celdas"]))
    windows_x = (len(tilemap[0]) + vram.WINDOW_W - 1) // vram.WINDOW_W
    windows_y = (len(tilemap) + vram.WINDOW_H - 1) // vram.WINDOW_H
    if windows_x > 1 or windows_y > 1:
        print("  it doesn't fit in the %dx%d window: the ROM is going to redraw"
              % (vram.WINDOW_W, vram.WINDOW_H))

    words = bytearray()
    for cell in cells:
        words += cell.to_bytes(2, "little")
    colors = bytearray()
    for word in cram:
        colors += word.to_bytes(2, "little")

    chipset = renderer.database.chipsets[game_map.chipset_id]
    layout_name, layout = vram.choose(len(tile_data) // BYTES_PER_TILE,
                                      len(tiles) // 32,
                                      len(above_data[0]) // 32)
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
        # Both grow while the pages are compiled, if some substitutes tiles:
        # see `Substitutions`. That is why they are mutable and are frozen
        # only when emitted.
        "bloques": blocks, "pass": block_pass, "terreno": block_terrain,
        "combos": combos,
        # The terrain of a cell **outside the map**: `GetTerrainTag` uses the
        # ChipSet's index 0, that is the first autotile, and not that of any
        # cell. See `op_terrain`.
        "terreno_fuera": rm2k.terrain_of(chipset, 0),
        "layout": layout, "layout_name": layout_name,
        "resumen": summary,
        # Which entries of its palette the timer's digits take, one bit each:
        # `timer_mask` in `rm2k-snes-map-sprites`. 0 without a timer.
        "timer_mask": s["timer_mask"],
        # The objects and the drawn events as the stage answered them, with
        # the bytes of its files: what the emission builds the NPC table,
        # the leaders' and the pose tables from.
        "objects": dict(s, tiles=tiles.hex(),
                        banks=[[charset, index, written[name].hex()]
                               for charset, index, name in s["banks"]]),
        "npcs": answer["npcs"], "movable": answer["movable"],
        "animates_still": answer["animates_still"],
        "imagenes_fondo": summary["imagenes"],
        # The whole map is stored because the events' pages can't be compiled
        # until all the maps are there: a `Teleport` translates map ids to
        # table indices.
        "game_map": game_map,
        # For the page table: where each (CharSet, index, pose) ended up in
        # the sprite bank, which events change graphic with the page and which
        # of their graphics were left out of the palettes.
        "where": where,
        # Each `TileSubstitution` the map can run, translated to its blocks
        # —which already include the ones the stage built for them—, as the
        # compiler takes it; and the ones that couldn't be built, which the
        # orchestrator says.
        "substitution_table": [
            {"upper": upper, "old": old, "new": new, "pairs": pairs}
            for upper, old, new, pairs in answer["substitutions"]["table"]],
        "missing_substitutions": [
            tuple(t) for t in answer["substitutions"]["missing"]],
        # For the turn toward the hero: which entry of `npc_poses` the twelve
        # poses of each graphic are in, which is the page's +30.
        "giro_k": {pair: animated_index[pair] for pair in animated},
        "giran": {event for event, _pairs in answer["turning"]},
        "cambian": {npc["event"] for npc in npcs if npc["changes"]},
        # And the ones that only appear and disappear with it: the ones that
        # walk, whose graphic was pinned further up.
        "aparecen": {npc["event"] for npc in npcs if npc.get("aparece")},
        "afuera": {npc["event"]: npc["afuera"] for npc in npcs},
    }

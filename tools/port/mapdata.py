"""`mapdata.inc`, the `.inc` that is assembled together with main.s: what
every domain of the conversion answered, written for ca65.

**The emission is `rm2k-snes-mapdata emit`'s** —`tools/rm2k-snes/mapdata/`,
a Rust stage on the PATH—: the header of constants, the tables of every map,
the window and the font, the screens, the menus, the battle, and what the
save game is signed with. It reads the database's items, skills, enemies,
actors and troops from the dump itself. What stays here is the request:
each map as the conversion left it, and what the other domains answered,
in the shape the stage takes it. Until 2026-10-01 all of it was here.
"""

import json
import os

from port import events, stage
from common import settings


# The header title of a SNES ROM: 21 bytes, at `$FFC0`.
TITLE_HEADER = 21


_FAMILIES = {"agua": "water", "animado": "animated"}


def _page_record(page):
    """A page as `rm2k-snes-mapdata` takes it, from the converter's."""
    own = page.get("ruta_propia")
    graphic = page.get("grafico")
    return {
        "event": page["event"], "page": page["pagina"],
        "trigger": page["trigger"], "switch_a": page["switch_a"],
        "switch_b": page["switch_b"], "actor": page["actor"],
        "layer": page["capa"], "item": page["item"],
        "has_code": bool(page["codigo"]), "offset": page.get("offset", 0),
        "route_offset": page.get("ruta_offset", 0),
        "frequency": page["frecuencia"], "speed": page["speed"],
        "fixed_direction": bool(page.get("dir_fija")),
        "own_route": None if not own else {
            "repeats": bool(own["repite"]),
            "skippable": bool(own["saltable"]),
            "fixed_direction": bool(own["dir_fija"]),
            "animation_continues": bool(own["anim_continues"]),
            "frequency": own["frecuencia"], "speed": own["speed"],
            "orders": len(own["ordenes"])},
        "oam": list(page["oam"]) if page.get("oam") is not None else None,
        "variable": (list(page["variable"])
                     if page.get("variable") is not None else None),
        "graphic": list(graphic) if graphic else None,
        "turns": bool(page.get("gira")),
    }


def _map_record(map_info):
    """A map as `rm2k-snes-mapdata maps` takes it: see `Map` in its
    `request.rs`."""
    _passable, start_x, start_y, width, height = map_info["collision"]
    above = map_info["above"]
    return {
        "id": map_info["id"], "name": map_info["nombre"],
        "tilemap": [len(map_info["tilemap"][0]), len(map_info["tilemap"])],
        "size": [width, height], "start": [start_x, start_y],
        "layout": map_info["layout_name"],
        "tiles": bytes(map_info["tiles"]).hex(),
        "cgram": bytes(map_info["cram"]).hex(),
        "above_tiles": bytes(above[0]).hex(),
        "above_cgram": bytes(above[1]).hex(), "above_first": above[3],
        "runs": [{"family": _FAMILIES[family], "base": run["base"],
                  "tiles": run["tiles"],
                  "drawings": [bytes(d).hex() for d in run["dibujos"]]}
                 for family, run in map_info["resumen"]["animacion"].items()],
        "cells": bytes(map_info["celdas"]).hex(),
        "blocks": bytes(map_info["bloques"]).hex(),
        "block_pass": bytes(map_info["pass"]).hex(),
        "block_terrain": bytes(map_info["terreno"]).hex(),
        "terrain_outside": map_info["terreno_fuera"],
        "sprite": map_info["objects"],
        "npcs": map_info["npcs"], "movable": map_info["movable"],
        "animates_still": map_info["animates_still"],
        "events": [[e.x, e.y] for e in map_info["game_map"].events],
        "pages": [_page_record(p) for p in map_info["pages"]],
        "evcode": bytes(map_info["evcode"]).hex(),
        "changing": sorted(map_info.get("cambian", ())),
        "appearing": sorted(map_info.get("aparecen", ())),
        "turning": sorted(map_info.get("giran", ())),
    }




def _full_screen(data):
    """A full screen, as `fullscreen.compressed` returns it."""
    if data is None:
        return None
    return {"tiles": data["tiles"], "colors": data["colores"],
            "first_color": data["primer_color"],
            "stream": bytes(data["flujo"]).hex()}


def emit(path, maps, dump, initial, hero_above, initial_party, screens,
         messages, message_pairs, title, game_over, picture_info,
         animations, troops,
         battle_audio, scene, battle_tables, troop_pages, party_common,
         battle_model, items, actors, text_padding, case_slot, enemy_hp,
         speed_keys):
    """Writes the `.inc` at `path`, with what the console decompresses of
    each map, uncompressed, in `crudos/` next to it; and returns `(what was
    shared and compressed, per map how many frames decompressing it
    takes)`.

    `screens` is what `rm2k-snes-screens convert` answered, as it came;
    `messages`, the text block of the pages, and `message_pairs` the pair
    table its letters are written with, `{"first", "table"}` as the event
    compiler answered them; `title` and `game_over`, what
    `fullscreen.compressed` returns, or None; `animations` and `scene`, what
    `battle_animations.animations_request` and
    `battle_scenes.scene_request` build; `troop_pages`, the compiler's
    answer of them; `party_common`, `{common event: its code}` of the ones
    the menu runs on closing; `battle_model`, what `rm2k-snes-battle model`
    answered. `case_slot` is where the harness writes the case number, if
    there is more than one.
    """
    request = {
        "maps": [_map_record(m) for m in maps],
        "start": initial,
        "hero_above": bool(hero_above),
        "speed_keys": bool(speed_keys),
        "enemy_hp": bool(enemy_hp),
        "party": list(initial_party),
        # What the ROM says about itself, from the `[rom]` of the project
        # file: the header title and the save signature in SRAM.
        "rom": {"title": settings.ascii("rom", "title",
                                        max_length=TITLE_HEADER),
                "sram_signature": settings.ascii("rom", "sram_signature",
                                                 length=4)},
        "screens": screens,
        "messages": bytes(messages).hex(),
        "message_pairs": message_pairs,
        "title": _full_screen(title),
        "game_over": _full_screen(game_over),
        "picture": None if not picture_info else {
            "x": picture_info["x"], "y": picture_info["y"],
            "objects": picture_info["objetos"],
            "palette": [list(c) for c in picture_info["paleta"]]},
        "animations": animations,
        "troops": list(troops),
        "battle_audio": battle_audio,
        "scene": scene,
        "battle_tables": battle_tables,
        "troop_pages": troop_pages,
        # The common events the menu runs on closing, by the switch that
        # turns them on: see `events.PARTY_COMMON_EVENTS`.
        "party_common": [[switch, number, party_common[number].hex()]
                         for switch, number
                         in sorted(events.PARTY_COMMON_EVENTS.items())],
        "battle_model": dict(battle_model,
                             layout=vars(battle_model["layout"])),
        # The compiler's indices: each variable's slot and each (actor,
        # skill) pair's bit.
        "variables": [[v, s] for v, s in events.VARIABLE_SLOT.items()],
        "skill_pairs": [[a, h, s]
                        for (a, h), s in events.SKILL_SLOT.items()],
        "items": list(items),
        "actors": list(actors),
        "text_padding": text_padding or 0,
        "case_slot": case_slot,
    }
    written = stage.run(
        "rm2k-snes-mapdata", "mapdata", "emit", request, "--data", dump,
        "--raw", os.path.join(os.path.dirname(os.path.abspath(path)),
                              "crudos"))
    with open(path, "w") as handle:
        handle.write(written["mapdata.inc"])
    answer = json.loads(written["mapdata.json"])
    for note in answer["notes"]:
        print(note)
    return answer["report"], answer["frames"]

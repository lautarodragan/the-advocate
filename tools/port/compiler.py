"""The event compiler, which is `rm2k-snes-events`: what goes into its two
requests and what comes back.

It reads the game from the dump itself. What it is told is what the dump
does not say: the cartridge's maps and test pages, and what the project
changed on top of the dump —the forks' files, the text boxes rebuilt for
the console's window (`texts.py`), the names the port gives some graphics
(`rm2k.decorate_translucent` and `sprites.separate_from_hero`), how a
`TileSubstitution` translates to the map's blocks, which picture took the
cartridge's place, the sound effects decided by ear—. See the crate's
README, `tools/rm2k-snes/events/`.

Two calls, because the converter needs the first answer to build the maps
and the maps to ask for the second: `scan` before converting any map, and
`compile_cartridge` after.
"""

import json
import os

from common import project, settings
from port import constants, events, stage, texts
from rpgmaker import fork, lcf, rm2k

BINARY = "rm2k-snes-events"
PROJECT = "events"


def dump_of(game_dir):
    """The dump the game is read from: `lcf`'s rule."""
    return lcf.dump_dir(os.path.join(game_dir, "RPG_RT.ldb"))


def command(cmd):
    """A command as the request carries it."""
    return {"code": cmd.code, "indent": cmd.indent, "string": cmd.string,
            "parameters": list(cmd.parameters)}


def _this_game(dump):
    """Whether the dump is this project's, the only one its forks apply to:
    `lcf.Map`'s rule."""
    return os.path.abspath(dump) == os.path.abspath(project.data())


def map_files(dump):
    """The maps read from the project's files and not from the dump: the
    forks of the game's, and the ones the game does not have."""
    if not _this_game(dump):
        return {}
    out = {m: pair[0] for m, pair in fork.maps().items()}
    out.update({m: entry[0] for m, entry in fork.new_maps().items()})
    return {str(m): os.path.abspath(p) for m, p in sorted(out.items())}


_BOXES = {}


def boxes(dump):
    """Every text box of the game the port rebuilds for the console's
    window, with the boxes that go in its place: `lcf.REFIT_TEXTS`, which
    is `texts.refit_commands`, applied to one box. Empty if nobody set it.

    All the boxes of all the maps and of the common events, whether or not
    the cartridge carries them: it is cheaper than knowing which it reads.
    """
    if not lcf.REFIT_TEXTS:
        return []
    key = (os.path.abspath(dump), constants.COLUMNS, constants.LINES)
    if key in _BOXES:
        return _BOXES[key]
    lists = []
    paths = [os.path.join(dump, "maps", name)
             for name in sorted(os.listdir(os.path.join(dump, "maps")))
             if name.endswith(".json")]
    paths += list(map_files(dump).values())
    for path in paths:
        # A fork's file overrides the dump's: both are read, which only
        # adds boxes that nobody asks for.
        for event in lcf.read_json(path)["events"]:
            for page in event["pages"]:
                lists.append(page["event_commands"])
    for common in lcf.read_json(dump, "db", "commonevents.json"):
        lists.append(common["event_commands"])
    table = {}
    for raw in lists:
        i = 0
        while i < len(raw):
            if raw[i]["code"] != events.SHOW_MESSAGE:
                i += 1
                continue
            j = i + 1
            while j < len(raw) and raw[j]["code"] == events.SHOW_MESSAGE_2:
                j += 1
            lines = [c["string"] for c in raw[i:j]]
            if tuple(lines) not in table:
                frames = texts.refit(lines)
                table[tuple(lines)] = frames
            i = j
    out = [{"from": list(k), "to": v} for k, v in table.items()
           if v != [list(k)]]
    _BOXES[key] = out
    return out


def names(game_maps):
    """The graphics the port calls by another name than the dump's, in
    these maps: `[map, event, page, name]`."""
    out = []
    for game_map in game_maps:
        for event in game_map.events:
            for page in event.pages:
                if page.character_name != getattr(page, "dump_name",
                                                  page.character_name):
                    out.append([game_map.map_id, event.id, page.id,
                                page.character_name])
    return out


def request(dump, map_ids, test_commands=(), extra_variables=(),
            test_event_map=None):
    """What both calls carry."""
    return {
        "map_files": map_files(dump),
        "boxes": boxes(dump),
        "names": [],
        "window": {"columns": constants.COLUMNS, "lines": constants.LINES},
        "maps": list(map_ids),
        "test_commands": [command(c) for c in test_commands],
        "extra_variables": sorted(extra_variables),
        "test_event_map": test_event_map,
    }


def run(command_name, dump, req):
    written = stage.run(BINARY, PROJECT, command_name, req, "--data", dump)
    return json.loads(written["events.json"])


# --- scan ---------------------------------------------------------------------

_SCANS = {}


def scan(dump, map_ids, test_commands=(), extra_variables=(),
         test_event_map=None):
    """The first call, remembered: the indices, which pages of each map
    compile, and each map's pages compiled without songs."""
    req = request(dump, map_ids, test_commands, extra_variables,
                  test_event_map)
    key = json.dumps(req, sort_keys=True)
    if key not in _SCANS:
        _SCANS[key] = run("scan", dump, req)
    return _SCANS[key]


def apply_indices(answer):
    """Leaves the whole game's indices where the rest of the converter reads
    them —`events.VARIABLE_SLOT`, `events.SKILL_SLOT`,
    `events.PARTY_COMMON_EVENTS`— and returns the graphics actors can be
    given, which every map's table starts with."""
    events.VARIABLE_SLOT.clear()
    events.VARIABLE_SLOT.update({v: s for v, s in answer["variables"]})
    events.SKILL_SLOT.clear()
    events.SKILL_SLOT.update({(a, h): s for a, h, s in answer["skills"]})
    events.PARTY_COMMON_EVENTS.clear()
    events.PARTY_COMMON_EVENTS.update(
        {entry[0]: entry[1] for entry in answer["party_common_events"]})
    return [tuple(p) for p in answer["associations"]]


def compiling_pages(answer, map_id):
    """`(event, page)` of the pages of that map that compile, by index."""
    for entry in answer["maps"]:
        if entry["id"] == map_id:
            return {tuple(p) for p in entry["leaders"]}
    raise KeyError("map %d is not in the scan" % map_id)


def map_entry(answer, map_id):
    for entry in answer["maps"]:
        if entry["id"] == map_id:
            return entry
    raise KeyError("map %d is not in the answer" % map_id)


def pages(records, game_map):
    """The records the compiler answered, as the converter keeps them, with
    what each page draws: that is the port's, and `rm2k`'s rules."""
    chipset = getattr(game_map, "chipset_filename", None)
    out = []
    for r in records:
        page = game_map.events[r["event"]].pages[r["page"]]
        graphic = rm2k.page_graphic(page, chipset)
        own = r["own_route"]
        out.append({
            "event": r["event"],
            "pagina": r["page"],
            "trigger": r["trigger"],
            "switch_a": r["switch_a"],
            "switch_b": r["switch_b"],
            "actor": r["actor"],
            "variable": (tuple(r["variable"])
                         if r["variable"] is not None else None),
            "item": r["item"],
            "capa": r["layer"],
            "frecuencia": r["frequency"],
            "speed": r["speed"],
            "codigo": (bytes.fromhex(r["code"])
                       if r["code"] is not None else None),
            "ruta_propia": None if own is None else {
                "ordenes": own["commands"],
                "frecuencia": own["frequency"],
                "speed": own["speed"],
                "repite": own["repeats"],
                "saltable": own["skippable"],
                "dir_fija": own["fixed_direction"],
                "anim_continues": own["animation_continues"],
            },
            "grafico": graphic,
            "tile_pass": (rm2k.event_tile_passability(game_map, graphic[0],
                                                      page.layer)
                          if graphic is not None else None),
            "gira": r["turns"],
        })
    return out


# --- compile ------------------------------------------------------------------

def compile_cartridge(dump, maps, cases, test_commands, extra_variables,
                      test_event_map, picture, test_graphics,
                      encounter_troops):
    """The second call: every page of the cartridge. `maps` are the
    converter's `map_info`s, in the cartridge's order, with their
    `game_map` and their `sustituciones`; `cases` are `(map, commands)`."""
    req = request(dump, [m["id"] for m in maps], test_commands,
                  extra_variables, test_event_map)
    req["names"] = names([m["game_map"] for m in maps])
    common = common_substitutions(dump)
    req["substitutions"] = {
        str(m["id"]): substitution_table(m, common) for m in maps}
    req["picture"] = picture
    req["sound_effects"] = {
        name: settings.value("sound_effects", name, kind=list)
        for name in ("per_map", "route_effects_left_out",
                     "troop_effects_in_package")}
    req["cases"] = [{"map": run_map, "commands": [command(c) for c in cmds]}
                    for run_map, cmds in cases]
    req["test_graphics"] = {str(m): [list(g) for g in graphics]
                            for m, graphics in test_graphics.items()}
    req["messages_step"] = events.MESSAGES_STEP
    req["encounter_troops"] = list(encounter_troops)
    return run("compile", dump, req)


def common_substitutions(dump):
    """The `(upper layer, old, new)` of the common events'
    `TileSubstitution`s, which a `CallEvent` can bring into any map."""
    triples = []
    for common in lcf.read_json(dump, "db", "commonevents.json"):
        for cmd in common["event_commands"]:
            p = cmd["parameters"]
            if cmd["code"] != events.TILE_SUBSTITUTION or len(p) < 3:
                continue
            triple = (bool(p[0]), p[1], p[2])
            if triple not in triples:
                triples.append(triple)
    return triples


def substitution_table(map_info, common=()):
    """Each `TileSubstitution` the map can end up running —its events', the
    test pages' that run there, and the common events'— with the blocks it
    translates to. `pure_pairs` and not `pairs`: which ones a page asked for
    comes back in the answer, and those are the ones counted."""
    subs = map_info["sustituciones"]
    triples = list(map_info.get("triples", ()))
    triples += [t for t in common if t not in triples]
    out = []
    for upper, old, new in triples:
        pairs = subs.pure_pairs(upper, old, new)
        out.append({"upper": upper, "old": old, "new": new,
                    "pairs": None if pairs is None
                    else [list(p) for p in pairs]})
    return out


class Registry:
    """What a registry filled by the compiler is to the rest of the
    converter: its fields."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def songs(answer):
    """The `Songs` the compiler filled, as `events.Songs`: the music
    numbers what it adds after these."""
    s = events.Songs()
    data = answer["songs"]

    def key(k):
        return events.BATTLE_PACKAGE if k == "battle" else k
    s.names = list(data["names"])
    s.sounds = [tuple(x) for x in data["sounds"]]
    s.per_map = {key(k): {"temas": list(w["songs"]),
                          "sonidos": list(w["sounds"]),
                          "destinos": list(w["destinations"])}
                 for k, w in data["per_package"]}
    s.exits = {key(k): {song: is_exit for song, is_exit in e}
               for k, e in data["exits"]}
    s.jumps = {key(k): {dest: set(songs) for dest, songs in j}
               for k, j in data["jumps"]}
    s.requested = data["requested"]
    return s


def troops(answer):
    t = events.Troops()
    t.ids = list(answer["troops"]["ids"])
    t.backdrops = {n: (name if name is not None else events.PLACE_BACKDROP)
                   for n, name in answer["troops"]["backdrops"]}
    return t


def messages(data, count):
    """A text block, as much as the converter reads of one."""
    block = bytes.fromhex(data)
    return Registry(data=bytearray(block), texts=range(count),
                    bytes=lambda: block)


def troop_pages(answer):
    data = answer["troop_pages"]
    per_troop = {}
    for number, theirs in data["per_troop"]:
        per_troop[number] = [(events.Trigger(*t), at) for t, at in theirs]
    return Registry(
        messages=messages(data["messages"], data["message_count"]),
        bodies=bytearray(bytes.fromhex(data["code"])),
        where=range(data["distinct"]),
        per_troop=per_troop, pages=data["pages"],
        left_out=data["left_out"])


def party_common_events(answer):
    """{common event: its code}: what the ROM runs when the menu closes."""
    return {number: bytes.fromhex(code)
            for _switch, number, code in answer["party_common_events"]}

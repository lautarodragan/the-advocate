"""The battle backdrops and battlers the cartridge carries: which ones, who
asks for each, and their bytes —the full backdrop for the `.msu` and the
light fallback the ROM carries— as the emission takes them
(`scene_request`): `scene.rs` in `rm2k-snes-mapdata` writes them. What a
scene looks like is `scene.py`'s.
"""

import collections
import json
import os

from port import events
from port import scene as scene_mod
from port import constants
from port.snes_format import cgram_word, pack_tile


# What goes in the backdrop tables instead of a backdrop number: the plain one
# —no backdrop, which is zeros— and "the one of the place", which the ROM
# resolves when the battle starts with the map and the terrain. See
# `rom_scene`.
FLAT_BACKDROP = 0xFF
PLACE_BACKDROP = 0xFE


def rom_scene(db, troops, maps, tree, encounters, game_dir):
    """Which backdrops and which battlers the cartridge carries, and who uses
    each one.

    It is the other half of tools/port/scene.py: there is how a backdrop or
    a battler is converted, here **which ones**. Backdrops are named by their
    number in the game —see "Which backdrops there are" there—, and a battle asks for its
    own in three ways:

    * **an `EnemyEncounter` that names it**, and then it belongs to the troop
      —that is how the baked scene worked—. If two asked for it differently
      for the same troop the first one wins, as in `Troops.request`;
    * **a random encounter in a map that inherits it**, which is
      `TreeMap.map_background`: the Back Alleys areas bring no backdrop and
      take it from their map;
    * **the one of the terrain the hero is standing on**, if the map names
      none: the world, 66. The ROM resolves that one when the battle starts,
      with `backdrop_terrain`. And an `EnemyEncounter` with the backdrop "of the
      place" does the same as a random encounter: `PLACE_BACKDROP`.

    A backdrop goes **into the ROM**, light, if some battle of the cartridge
    asks for it; if some can land on one that isn't there —a troop of the
    place in a map without encounters—, `scene.replacement()` goes in too, and
    `respaldo_de` says which one of the ROM each backdrop of the game uses.
    **All of them go in the `.msu`**: `calidad` is their bytes, by number.

    A battler goes in if some troop of the cartridge uses it, **once** even if
    four use it, and it is the image with its hue: the GiantRat and the
    HairyVermin are the same `BLmouse` and two battlers.
    """
    E = scene_mod
    names_in_game = E.game_backdrops(events.named_backdrops(game_dir), tree,
                                     db.terrain_backdrops, game_dir)
    number_of = {name.lower(): k for k, name in enumerate(names_in_game)}
    if len(names_in_game) >= PLACE_BACKDROP:
        raise SystemExit("the game has %d battle backdrops and the number of "
                         "one is a byte, with $%02X and $FF reserved"
                         % (len(names_in_game), PLACE_BACKDROP))
    data = {"juego": names_in_game, "fondos": [], "battlers": [], "battler_de": {},
            "tropa_fondo": {}, "mapa_fondo": [], "respaldo_de": [],
            "terreno_fondo": [], "calidad": []}

    def number(name):
        if name is None or name is events.PLACE_BACKDROP:
            return PLACE_BACKDROP
        return number_of.get(name.lower(), FLAT_BACKDROP) if name \
            else FLAT_BACKDROP

    for n in troops.ids:
        background = troops.backdrops.get(n)
        data["tropa_fondo"][n] = number(background) if background else FLAT_BACKDROP
    # The map's, for random encounters and for the troops that fight with the
    # one of the place. Only in the maps where some battle can look at it:
    # without that, any cartridge would ask for the replacement.
    per_map = (encounters or {}).get("per_map") or [0xFF] * len(maps)
    place_ones = PLACE_BACKDROP in data["tropa_fondo"].values()
    for map_info, record in zip(maps, per_map):
        if record != 0xFF or place_ones:
            data["mapa_fondo"].append(
                number(tree.map_background(map_info["id"])))
        else:
            data["mapa_fondo"].append(FLAT_BACKDROP)
    terrains = db.terrain_backdrops
    data["terreno_fondo"] = [number(terrains.get(t, "")) if terrains.get(t)
                             else FLAT_BACKDROP
                             for t in range(max(terrains, default=0) + 1)]

    # The ROM's: all the ones asked for, in the order they are asked for —see
    # "Which backdrops there are" in scene.py—. A map with encounters that asks for the
    # one of the place asks for those of all the terrains of its blocks, which
    # are the ones the hero can stand on, substitutions included. A map
    # without encounters that asks for it anyway —because some troop fights
    # with the one of the place, and it isn't known where— doesn't: if its
    # terrain isn't there, the replacement goes.
    def of_terrains(map_info):
        return [data["terreno_fondo"][t]
                if t < len(data["terreno_fondo"]) else FLAT_BACKDROP
                for t in sorted(set(map_info["terreno"]))]
    requested = list(data["tropa_fondo"].values()) + data["mapa_fondo"]
    possible = []
    for map_info, record, k in zip(maps, per_map, data["mapa_fondo"]):
        if k != PLACE_BACKDROP:
            continue
        if record != 0xFF:
            requested += of_terrains(map_info)
        else:
            possible += of_terrains(map_info)
    theirs = []
    for k in requested:
        if k < PLACE_BACKDROP and k not in theirs:
            theirs.append(k)
    if any(k < PLACE_BACKDROP and k not in theirs for k in possible):
        replacement = number_of[E.replacement().lower()]
        if replacement not in theirs:
            theirs.append(replacement)
    lights = E.backdrops([names_in_game[k] for k in theirs], game_dir,
                         quality=False)
    for k, (_quality, info) in zip(theirs, lights):
        data["fondos"].append({"nombre": names_in_game[k], "numero": k,
                               "respaldo": info})
    place = {k: i for i, k in enumerate(theirs)}
    replacement = place.get(number_of[E.replacement().lower()], 0)
    data["respaldo_de"] = [place.get(k, replacement) for k in range(len(names_in_game))]
    # The quality ones, for the `.msu`: all of them, whether in the ROM or not.
    data["calidad"] = [backdrop_bytes(quality) for quality, _light
                       in E.backdrops(names_in_game, game_dir, light=False)]
    # Which enemies ask for which battler, in the order they are asked for;
    # then the battlers, with a single call to the stage.
    asked, first_asked = [], {}
    for number in troops.ids:
        if number not in db.troops:
            continue
        for enemy in db.troops[number].members[:constants.ENEMIES_MAX]:
            if enemy in first_asked or enemy not in db.enemies:
                continue
            e = db.enemies[enemy]
            name = e.battler_name or ""
            hue = getattr(e, "battler_hue", 0) or 0
            first_asked[enemy] = (name, hue)
            if name and (name, hue) not in asked:
                asked.append((name, hue))
    drawn = dict(zip(asked, E.battlers(asked, game_dir)))
    battler_k = {}
    for enemy, (name, hue) in first_asked.items():
        k = E.key(name, hue)
        if k not in battler_k:
            info = drawn[(name, hue)] if name else None
            battler_k[k] = 0xFF if info is None else len(data["battlers"])
            if info is not None:
                data["battlers"].append(info)
        data["battler_de"][enemy] = battler_k[k]
    return data


def patch_uses(maps, db, tree):
    """Who asks for each animation and each battler of the cartridge: per
    patch class, `{key: [origin, ...]}`, where the origin is the id of the map
    whose page or random encounter asks for it, or `"caso"` if a test page
    asks for it.

    It is what lets `rm2k-snes-patches --check` know what isn't the game's
    in the ROM that is played, which also carries the suite's maps and
    pages: an
    animation only a case asks for, or a battler that only shows up in a test
    map, isn't versioned. The bytecode is walked, as in
    `rom_animations`, so it counts what ended up emitted. A troop
    someone asked for and no emitted page names —a page that fell out after
    asking for it— has no origin, and the check treats it as the game's: the
    doubt leans toward asking for the patch.
    """
    E = scene_mod
    animations = collections.defaultdict(set)
    troops = collections.defaultdict(set)
    for map_info in maps:
        for page in map_info.get("pages", ()):
            origin = "caso" if page.get("prueba") else map_info["id"]
            code = page.get("codigo") or b""
            for i, c in events.walk_code(code):
                if (c[i] == events.OP_ANIMATION
                        and c[i + 1] != events.ANIM_NO_DRAWING):
                    animations[c[i + 1]].add(origin)
                elif c[i] == events.OP_BATTLE:
                    troops[c[i + 1] | (c[i + 2] << 8)].add(origin)
        game_map = map_info["game_map"]
        for *_rect, which_ones in events.encounter_zones(
                tree, map_info["id"], game_map.width, game_map.height):
            for number in which_ones:
                troops[number].add(map_info["id"])
    battlers = collections.defaultdict(set)
    for number, origins in troops.items():
        if number not in db.troops:
            continue
        for enemy in db.troops[number].members[:constants.ENEMIES_MAX]:
            if enemy not in db.enemies:
                continue
            e = db.enemies[enemy]
            if e.battler_name:
                battlers[E.key(e.battler_name,
                               getattr(e, "battler_hue", 0) or 0)] |= origins
    return {"animacion": animations, "battler": battlers}


# Where `write_patch_uses` leaves them, next to the cartridge's patches and
# **not versioned**: `rm2k-snes-patches` reads it from there. It is the shape
# of the build, which imitates the project's patches: not where those are in
# the repo, and it does not move with them.
USES_FILE = os.path.join("parches", "usos.json")


def write_patch_uses(dest, uses):
    """`uses` is what `patch_uses` returns, into the build at `dest`. The
    origins go sorted as text, so a map id and `"caso"` can share a list;
    and the keys by the text of their `(key, origins)` pair, which is what
    `key=str` sorts an item by: it is the order the file always had, and
    nobody reads it in order."""
    with open(os.path.join(dest, USES_FILE), "w") as f:
        json.dump({kind: {str(k): sorted(v, key=str)
                          for k, v in sorted(which_ones.items(), key=str)}
                   for kind, which_ones in uses.items()}, f, indent=1)


def backdrop_bytes(info):
    """A battle backdrop as the console reads it: `(tiles, colors)`, its 512
    8bpp tiles in tilemap order and its `COLORS` 15-bit colors, padded with
    black."""
    E = scene_mod
    tiles_ = bytearray()
    for cell in E.tiles(info["indices"]):
        tiles_ += pack_tile(cell, planes=8)
    colors = list(info["paleta"])
    colors += [(0, 0, 0)] * (E.COLORS - len(colors))
    cgram = bytearray()
    for color in colors:
        cgram += cgram_word(color).to_bytes(2, "little")
    return bytes(tiles_), bytes(cgram)


def fallback_bytes(info):
    """The light fallback of a backdrop, as the ROM carries it: `(bytes,
    colors)`, its 4 KB of 128x64 at 4bpp and its `FALLBACK_COLORS` colors.
    They store the index **within their palette**: the ROM adds the planes of
    `CGRAM_BASE` separately, see `fallback_height` in the emission's
    `scene.rs`.

    **The bytes don't go in tile order**, but in the one `scn_double` enlarges
    them in without doing any arithmetic. Each small tile becomes four large
    ones, and the ROM fills them two neighbors of the same row at a time —the
    pair that comes from the same row of eight small pixels—, pair by pair in
    the scene's order. Of each pair, large row by large row two at a time (both
    come from the same small row) and planes 0/1 before 2/3.

    And within that, **each byte carries half a byte of two planes**: of the
    small row that gives planes `p` and `p+1`, the first carries the high
    nibble of both —the four leftmost pixels, which go to the left large
    tile— and the second the two low nibbles. That way each byte, duplicated
    bit by bit with `fallback_double` —also there—, is already the two-plane word of a row
    of a large tile, and the ROM writes it whole without separating the planes.
    """
    E = scene_mod
    light = info["respaldo"]
    smalls = [pack_tile([[v - E.CGRAM_BASE for v in row] for row in cell],
                        planes=E.FALLBACK_PLANES)
              for cell in E.tiles(light["chico"])]
    columns = E.FALLBACK_WIDTH // E.CELL
    tiles_ = bytearray()
    for big_row in range(E.TILES_Y):
        half = big_row % E.FALLBACK_SCALE     # above or below the small one
        for column in range(columns):
            small = smalls[(big_row // E.FALLBACK_SCALE) * columns
                           + column]
            for pair in (0, 16):                     # planes 0/1 and 2/3
                for k in range(4):                  # the large rows 2k, 2k+1
                    row = half * 4 + k            # the small row
                    p0, p1 = small[pair + 2 * row], small[pair + 2 * row + 1]
                    tiles_.append((p0 & 0xF0) | (p1 >> 4))
                    tiles_.append(((p0 & 0x0F) << 4) | (p1 & 0x0F))
    colors = list(light["paleta"])
    colors += [(0, 0, 0)] * (E.FALLBACK_COLORS - len(colors))
    cgram = bytearray()
    for color in colors:
        cgram += cgram_word(color).to_bytes(2, "little")
    return bytes(tiles_), bytes(cgram)


def scene_request(data, troops, db):
    """The cartridge's battle scene as `rm2k-snes-mapdata emit` takes it:
    what `rom_scene` decided, with what a backdrop and a battler look like,
    where each member stands and in which order the troop is drawn already
    as bytes and numbers —those are the scene's, `scene.py`—. The emission
    only writes them: see `scene.rs` there."""
    E = scene_mod
    geometry = {name: getattr(E, name) for name in (
        "WIDTH", "HEIGHT", "TILES", "TILES_X", "TILES_Y", "COLORS",
        "CGRAM_BASE", "VRAM_TILES", "VRAM_MAP", "FALLBACK_COLORS",
        "FALLBACK_PLANES", "FALLBACK_WIDTH", "FALLBACK_HEIGHT",
        "FALLBACK_SCALE", "BATTLER_PALETTE")}
    backdrops = []
    for info in data["fondos"]:
        tiles_, colors = fallback_bytes(info)
        backdrops.append({"tiles": tiles_.hex(), "colors": colors.hex()})
    battlers = data["battlers"]
    placed = []
    for number in troops:
        if number not in db.troops:
            continue
        troop = db.troops[number]
        theirs = list(zip(troop.members,
                          troop.positions))[:constants.ENEMIES_MAX]
        members, infos = [], []
        for enemy, center in theirs:
            k = data["battler_de"].get(enemy, 0xFF)
            infos.append(battlers[k] if k != 0xFF else None)
            x, y = (E.position(center, battlers[k]) if k != 0xFF else (0, 0))
            members.append([k, x, y])
        placed.append([number, members,
                       E.drawing_order([c for _e, c in theirs], infos)])
    return {
        "geometry": geometry,
        "game": len(data.get("juego", ())),
        "troop_backdrop": [[n, k] for n, k in data["tropa_fondo"].items()],
        "map_backdrop": list(data["mapa_fondo"]),
        "terrains": list(data.get("terreno_fondo") or []),
        "fallback_of": list(data.get("respaldo_de") or []),
        "backdrops": backdrops,
        "battlers": [{"columns": E.columns(b), "height": b["alto"],
                      "palette": [list(c) for c in b["paleta"]],
                      "bytes": E.battler_bytes(b).hex()} for b in battlers],
        "troops": placed,
    }

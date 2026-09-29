"""`rom/parches/manual/`: what is ours, which overrides the dump in `rom/data/`.

`rom/data/` is the game as its author wrote it —Ditto's dump, which is
derived and fully regenerated with `just datos`—. A **fork** is a file of
ours that the pipeline uses **instead of** the one in `rom/data/`: it does
not describe changes, it is the whole file. Today map 11 asks for one, whose
stones minigame we redesigned; the why is in
`workflow/done/el-mapa-11-se-rediseno.md` and the what, in
`rom/parches/manual/README.md`.

Three things this module enforces, and all three are the same fear:

* **a forked map is all or nothing.** The tile layers live outside the JSON,
  so a `Map0011.json` without its `Map0011.tiles` would leave the build with
  the old layers and the new events, and that **looks fine until it doesn't**;
* **the id inside is the one in the name.** A misnamed fork —or one copied
  from another map— does not fail: it overwrites the wrong map, and the
  teleports land inside a wall;
* **a map fork replaces one that exists.** A misspelled name does nothing,
  silently, and that is worse than an error.

And one it does **not** do: the fork touches neither the original game nor
`rom/data/`. `unpack` writes to `rom/data/` and never here, so the diff
against the original is computed whenever needed and is never lost.

Maps the game does not have go separately, in `nuevos/`, with the rule
reversed —they cannot overwrite one that exists— and their tree node inside:
see `new_maps`.

ChipSets go separately and **are added**, they do not replace: map 11
introduces one of its own so it can duplicate tiles without touching a pixel
of the other six maps that share number 10. An id already in
`rom/data/db/chipsets.json` is an error, because a fork that overwrites a
database entry goes stale without warning the day `just datos` changes it.

The image of those ChipSets is built by `render/chipset_recipe.py`.
"""

import json
import os

from common import project

# Where each part is. They are functions and not constants because they come
# from the project, which is found when used and not when this module is
# imported; the tests override them with a temporary directory.

def maps_folder():
    return os.path.join(project.manual_patches(), "mapas")


def chipsets_folder():
    return os.path.join(project.manual_patches(), "chipsets")


def new_maps_folder():
    """The maps the game does not have: see `new_maps`."""
    return os.path.join(project.manual_patches(), "nuevos")


def game_maps_folder():
    """The game's maps, against which it is checked that a fork overwrites one
    and a new map does not."""
    return os.path.join(project.data(), "maps")


class BrokenFork(Exception):
    """The fork is incomplete or contradicts itself: the build stops."""


def _name(map_id):
    return "Map%04d" % map_id


def maps():
    """{map_id: (json, tiles)} of the forked maps, already validated.

    The whole thing is validated on every call and not only the requested
    map: an incomplete fork has to break the build whoever builds it, and not
    only when that particular map happens to be loaded.

    What was validated is remembered as long as the directory does not
    change —the names, dates and sizes of its files, and whether the
    originals are there—: every `lcf.Map` goes through here, and reading the
    forks' whole JSON files to look at their id took ~2 ms per map, some nine
    hundred times per conversion. A broken fork is not remembered: it keeps
    breaking on every call.
    """
    fingerprint = _fingerprint()
    if fingerprint in _validated:
        return dict(_validated[fingerprint])
    found = _validate()
    _validated[fingerprint] = dict(found)
    return found


_validated = {}


def _fingerprint():
    """What has to change for the validated fork to stop being valid."""
    folder = maps_folder()
    game_maps = game_maps_folder()
    if not os.path.isdir(folder):
        return None
    parts = [folder, game_maps]
    for entry in sorted(os.listdir(folder)):
        try:
            stat = os.stat(os.path.join(folder, entry))
            parts.append((entry, stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append((entry, None, None))
        base = os.path.splitext(entry)[0]
        parts.append(os.path.isfile(os.path.join(game_maps, base + ".json")))
    return tuple(parts)


def _validate():
    folder = maps_folder()
    game_maps = game_maps_folder()
    found = {}
    if not os.path.isdir(folder):
        return found
    for entry in sorted(os.listdir(folder)):
        base, extension = os.path.splitext(entry)
        if extension not in (".json", ".tiles"):
            raise BrokenFork("%s: only .json and .tiles go in "
                             "rom/parches/manual/mapas/" % entry)
        if not (base.startswith("Map") and base[3:].isdigit()):
            raise BrokenFork("%s: the name has to be MapNNNN" % entry)
        map_id = int(base[3:])
        if map_id in found:
            continue
        pair = (os.path.join(folder, base + ".json"),
                os.path.join(folder, base + ".tiles"))
        missing = [p for p in pair if not os.path.isfile(p)]
        if missing:
            raise BrokenFork(
                "the fork of map %d is incomplete: %s is missing. The layers "
                "live outside the JSON, so half a piece leaves the build with "
                "the layers of one map and the events of another"
                % (map_id, ", ".join(os.path.basename(p) for p in missing)))
        original = os.path.join(game_maps, base + ".json")
        if not os.path.isfile(original):
            raise BrokenFork(
                "the fork names map %d and rom/data/ has none: a fork "
                "replaces a map of the game, it does not add one" % map_id)
        with open(pair[0], encoding="utf-8") as handle:
            inside = json.load(handle).get("id")
        if inside != map_id:
            raise BrokenFork(
                "%s says inside that it is map %r: the id and the file name "
                "have to be the same, because the pipeline picks the map by "
                "the name and the teleports by the id"
                % (entry, inside))
        found[map_id] = pair
    return found


def map_fork(map_id):
    """(json, tiles) of that map's fork, or None if there is none."""
    return maps().get(map_id)


def new_maps():
    """{map_id: (json, tiles, node)} of the maps the game **does not have**.

    It is `maps`'s rule reversed, and that is why they live in another
    folder: a fork replaces a map that exists and a new map **cannot**
    overwrite one that exists. Mixing them in `mapas/` would take away both
    their safety nets: a fork with a misspelled name would pass as a new map,
    and a new map with the id of one of the game's would hide it without
    warning.

    A map that does not exist has no node in the tree either
    —`rom/data/maps.json`—, which is where its name, its parent, its music
    and its encounters come from. So it brings its own: the JSON's `arbol`
    field is the whole node, in the same resolved view as the dump, and
    `lcf.TreeMap` adds it. Today there is only one, the debug map: see
    `debug_map_id` in `tools/assembly/cartridges.py`.

    What was validated is remembered as in `maps`, and for the same reason:
    every `lcf.Map` asks here.
    """
    fingerprint = _new_maps_fingerprint()
    if fingerprint not in _validated_new_maps:
        _validated_new_maps[fingerprint] = _validate_new_maps()
    return dict(_validated_new_maps[fingerprint])


_validated_new_maps = {}


def _new_maps_fingerprint():
    folder = new_maps_folder()
    game_maps = game_maps_folder()
    if not os.path.isdir(folder):
        return (folder, None)
    parts = [folder, game_maps]
    for entry in sorted(os.listdir(folder)):
        stat = os.stat(os.path.join(folder, entry))
        base = os.path.splitext(entry)[0]
        parts.append((entry, stat.st_mtime_ns, stat.st_size,
                      os.path.isfile(os.path.join(game_maps, base + ".json"))))
    return tuple(parts)


def _validate_new_maps():
    folder = new_maps_folder()
    game_maps = game_maps_folder()
    found = {}
    if not os.path.isdir(folder):
        return found
    for entry in sorted(os.listdir(folder)):
        base, extension = os.path.splitext(entry)
        if extension not in (".json", ".tiles"):
            raise BrokenFork("%s: only .json and .tiles go in "
                             "rom/parches/manual/nuevos/" % entry)
        if not (base.startswith("Map") and base[3:].isdigit()):
            raise BrokenFork("%s: the name has to be MapNNNN" % entry)
        map_id = int(base[3:])
        if map_id in found:
            continue
        pair = (os.path.join(folder, base + ".json"),
                os.path.join(folder, base + ".tiles"))
        missing = [p for p in pair if not os.path.isfile(p)]
        if missing:
            raise BrokenFork("the new map %d is incomplete: %s is missing"
                             % (map_id, ", ".join(os.path.basename(p)
                                                  for p in missing)))
        if os.path.isfile(os.path.join(game_maps, base + ".json")):
            raise BrokenFork(
                "the new map %d already exists in rom/data/: a new map does "
                "not overwrite one of the game's; if it is meant to change it, "
                "it is a fork and goes in rom/parches/manual/mapas/" % map_id)
        with open(pair[0], encoding="utf-8") as handle:
            data = json.load(handle)
        node = data.get("arbol")
        if data.get("id") != map_id or not node or node.get("id") != map_id:
            raise BrokenFork(
                "%s: the id inside, the one in the `arbol` node and the one in "
                "the file name have to be the same" % entry)
        found[map_id] = pair + (node,)
    return found


def new_map(map_id):
    """(json, tiles) of the new map with that id, or None if there is none."""
    hit = new_maps().get(map_id)
    return hit[:2] if hit else None


def chipsets():
    """{id: entry} of the ChipSets the fork adds to the database."""
    folder = chipsets_folder()
    added = {}
    if not os.path.isdir(folder):
        return added
    for entry in sorted(os.listdir(folder)):
        base, extension = os.path.splitext(entry)
        if extension != ".json" or not base.isdigit():
            raise BrokenFork("%s: rom/parches/manual/chipsets/ takes NNNN.json"
                             % entry)
        with open(os.path.join(folder, entry), encoding="utf-8") as handle:
            data = json.load(handle)
        if data["chipset"]["id"] != int(base):
            raise BrokenFork(
                "%s says inside that it is ChipSet %d: the id and the file "
                "name have to be the same"
                % (entry, data["chipset"]["id"]))
        added[int(base)] = data
    return added

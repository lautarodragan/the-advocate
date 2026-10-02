"""`rom/parches/manual/`: what is ours, which overrides the dump in `rom/data/`.

`rom/data/` is the game as its author wrote it —Ditto's dump, which is
derived and fully regenerated with `just datos`—. A **fork** is a file of
ours that the pipeline uses **instead of** the one in `rom/data/`: it does
not describe changes, it is the whole file. Today maps 11, 18, 32 and 108
have one; the why is in `rom/parches/manual/README.md`.

This only says **where** each file is, for the tests that read the game the
way the converter reads it. Whether the patches are whole —a map's JSON
with its layers, the id inside the one in the name, a fork that replaces a
map that exists, a new map that does not— the converter checks on every
build, `fork.rs` in `rm2k-snes-convert`, and its tests are there: a broken
fork stops the cartridges before any test runs. Until 2026-10-02 this was
`rpgmaker/fork.py`, and checked it too.

Maps the game does not have go separately, in `nuevos/`, with their tree
node inside; ChipSets go in `chipsets/`, and **are added** to the database.
"""

import json
import os

from common import project


def maps_folder():
    return os.path.join(project.manual_patches(), "mapas")


def chipsets_folder():
    return os.path.join(project.manual_patches(), "chipsets")


def new_maps_folder():
    """The maps the game does not have: see `new_maps`."""
    return os.path.join(project.manual_patches(), "nuevos")


def _pairs(folder):
    """{map_id: (json, tiles)} of the `MapNNNN.json` in `folder`."""
    found = {}
    if not os.path.isdir(folder):
        return found
    for entry in sorted(os.listdir(folder)):
        base, extension = os.path.splitext(entry)
        if extension != ".json":
            continue
        found[int(base[3:])] = (os.path.join(folder, base + ".json"),
                                os.path.join(folder, base + ".tiles"))
    return found


def maps():
    """{map_id: (json, tiles)} of the forked maps."""
    return _pairs(maps_folder())


def map_fork(map_id):
    """(json, tiles) of that map's fork, or None if there is none."""
    return maps().get(map_id)


def new_maps():
    """{map_id: (json, tiles, node)} of the maps the game **does not have**,
    each with its node of the tree, the JSON's `arbol` field."""
    found = {}
    for map_id, pair in _pairs(new_maps_folder()).items():
        with open(pair[0], encoding="utf-8") as handle:
            found[map_id] = pair + (json.load(handle)["arbol"],)
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
        if extension != ".json":
            continue
        with open(os.path.join(folder, entry), encoding="utf-8") as handle:
            added[int(base)] = json.load(handle)
    return added

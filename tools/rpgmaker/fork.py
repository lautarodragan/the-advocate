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
see `nuevos`.

ChipSets go separately and **are added**, they do not replace: map 11
introduces one of its own so it can duplicate tiles without touching a pixel
of the other six maps that share number 10. An id already in
`rom/data/db/chipsets.json` is an error, because a fork that overwrites a
database entry goes stale without warning the day `just datos` changes it.

The image of those ChipSets is built by `render/chipset_del_fork.py`.
"""

import json
import os

from common import proyecto

# Where each part is. They are functions and not constants because they come
# from the project, which is found when used and not when this module is
# imported; the tests override them with a temporary directory.

def carpeta_mapas():
    return os.path.join(proyecto.parches_manual(), "mapas")


def carpeta_chipsets():
    return os.path.join(proyecto.parches_manual(), "chipsets")


def carpeta_nuevos():
    """The maps the game does not have: see `nuevos`."""
    return os.path.join(proyecto.parches_manual(), "nuevos")


def carpeta_del_juego():
    """The game's maps, against which it is checked that a fork overwrites one
    and a new map does not."""
    return os.path.join(proyecto.data(), "maps")


class ForkRoto(Exception):
    """The fork is incomplete or contradicts itself: the build stops."""


def _nombre(map_id):
    return "Map%04d" % map_id


def mapas():
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
    huella = _huella()
    if huella in _validados:
        return dict(_validados[huella])
    encontrados = _validar()
    _validados[huella] = dict(encontrados)
    return encontrados


_validados = {}


def _huella():
    """What has to change for the validated fork to stop being valid."""
    carpeta = carpeta_mapas()
    del_juego = carpeta_del_juego()
    if not os.path.isdir(carpeta):
        return None
    partes = [carpeta, del_juego]
    for entrada in sorted(os.listdir(carpeta)):
        try:
            estado = os.stat(os.path.join(carpeta, entrada))
            partes.append((entrada, estado.st_mtime_ns, estado.st_size))
        except OSError:
            partes.append((entrada, None, None))
        base = os.path.splitext(entrada)[0]
        partes.append(os.path.isfile(os.path.join(del_juego, base + ".json")))
    return tuple(partes)


def _validar():
    carpeta = carpeta_mapas()
    del_juego = carpeta_del_juego()
    encontrados = {}
    if not os.path.isdir(carpeta):
        return encontrados
    for entrada in sorted(os.listdir(carpeta)):
        base, extension = os.path.splitext(entrada)
        if extension not in (".json", ".tiles"):
            raise ForkRoto("%s: only .json and .tiles go in "
                           "rom/parches/manual/mapas/" % entrada)
        if not (base.startswith("Map") and base[3:].isdigit()):
            raise ForkRoto("%s: the name has to be MapNNNN" % entrada)
        map_id = int(base[3:])
        if map_id in encontrados:
            continue
        pareja = (os.path.join(carpeta, base + ".json"),
                  os.path.join(carpeta, base + ".tiles"))
        falta = [p for p in pareja if not os.path.isfile(p)]
        if falta:
            raise ForkRoto(
                "the fork of map %d is incomplete: %s is missing. The layers "
                "live outside the JSON, so half a piece leaves the build with "
                "the layers of one map and the events of another"
                % (map_id, ", ".join(os.path.basename(p) for p in falta)))
        original = os.path.join(del_juego, base + ".json")
        if not os.path.isfile(original):
            raise ForkRoto(
                "the fork names map %d and rom/data/ has none: a fork "
                "replaces a map of the game, it does not add one" % map_id)
        with open(pareja[0], encoding="utf-8") as handle:
            adentro = json.load(handle).get("id")
        if adentro != map_id:
            raise ForkRoto(
                "%s says inside that it is map %r: the id and the file name "
                "have to be the same, because the pipeline picks the map by "
                "the name and the teleports by the id"
                % (entrada, adentro))
        encontrados[map_id] = pareja
    return encontrados


def mapa(map_id):
    """(json, tiles) of that map's fork, or None if there is none."""
    return mapas().get(map_id)


def nuevos():
    """{map_id: (json, tiles, nodo)} of the maps the game **does not have**.

    It is `mapas`'s rule reversed, and that is why they live in another
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
    `el_mapa_de_debug` in `tools/ensamblado/cartuchos.py`.

    What was validated is remembered as in `mapas`, and for the same reason:
    every `lcf.Map` asks here.
    """
    huella = _huella_de_nuevos()
    if huella not in _nuevos_validados:
        _nuevos_validados[huella] = _validar_nuevos()
    return dict(_nuevos_validados[huella])


_nuevos_validados = {}


def _huella_de_nuevos():
    carpeta = carpeta_nuevos()
    del_juego = carpeta_del_juego()
    if not os.path.isdir(carpeta):
        return (carpeta, None)
    partes = [carpeta, del_juego]
    for entrada in sorted(os.listdir(carpeta)):
        estado = os.stat(os.path.join(carpeta, entrada))
        base = os.path.splitext(entrada)[0]
        partes.append((entrada, estado.st_mtime_ns, estado.st_size,
                       os.path.isfile(os.path.join(del_juego, base + ".json"))))
    return tuple(partes)


def _validar_nuevos():
    carpeta = carpeta_nuevos()
    del_juego = carpeta_del_juego()
    encontrados = {}
    if not os.path.isdir(carpeta):
        return encontrados
    for entrada in sorted(os.listdir(carpeta)):
        base, extension = os.path.splitext(entrada)
        if extension not in (".json", ".tiles"):
            raise ForkRoto("%s: only .json and .tiles go in "
                           "rom/parches/manual/nuevos/" % entrada)
        if not (base.startswith("Map") and base[3:].isdigit()):
            raise ForkRoto("%s: the name has to be MapNNNN" % entrada)
        map_id = int(base[3:])
        if map_id in encontrados:
            continue
        pareja = (os.path.join(carpeta, base + ".json"),
                  os.path.join(carpeta, base + ".tiles"))
        falta = [p for p in pareja if not os.path.isfile(p)]
        if falta:
            raise ForkRoto("the new map %d is incomplete: %s is missing"
                           % (map_id, ", ".join(os.path.basename(p)
                                                for p in falta)))
        if os.path.isfile(os.path.join(del_juego, base + ".json")):
            raise ForkRoto(
                "the new map %d already exists in rom/data/: a new map does "
                "not overwrite one of the game's; if it is meant to change it, "
                "it is a fork and goes in rom/parches/manual/mapas/" % map_id)
        with open(pareja[0], encoding="utf-8") as handle:
            datos = json.load(handle)
        nodo = datos.get("arbol")
        if datos.get("id") != map_id or not nodo or nodo.get("id") != map_id:
            raise ForkRoto(
                "%s: the id inside, the one in the `arbol` node and the one in "
                "the file name have to be the same" % entrada)
        encontrados[map_id] = pareja + (nodo,)
    return encontrados


def nuevo(map_id):
    """(json, tiles) of the new map with that id, or None if there is none."""
    hallado = nuevos().get(map_id)
    return hallado[:2] if hallado else None


def chipsets():
    """{id: entry} of the ChipSets the fork adds to the database."""
    carpeta = carpeta_chipsets()
    nuevos = {}
    if not os.path.isdir(carpeta):
        return nuevos
    for entrada in sorted(os.listdir(carpeta)):
        base, extension = os.path.splitext(entrada)
        if extension != ".json" or not base.isdigit():
            raise ForkRoto("%s: rom/parches/manual/chipsets/ takes NNNN.json"
                           % entrada)
        with open(os.path.join(carpeta, entrada), encoding="utf-8") as handle:
            datos = json.load(handle)
        if datos["chipset"]["id"] != int(base):
            raise ForkRoto(
                "%s says inside that it is ChipSet %d: the id and the file "
                "name have to be the same"
                % (entrada, datos["chipset"]["id"]))
        nuevos[int(base)] = datos
    return nuevos

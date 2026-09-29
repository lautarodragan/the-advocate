#!/usr/bin/env python3
"""The patches: what the converter **decides to lose** when taking the game to the SNES.

Going from RPG Maker to the console there are two kinds of transformation
and only one is a patch. Baking opaque events, reusing mirrored tiles or
`separar_del_heroe` require no judgment and do not change what is seen: they
are optimizations and are not here. Merging two colors because CGRAM does
not have room for both, on the other hand, **loses something and someone
chose what**, and that is a patch.

Until now those decisions were made silently and left no trace: if a change
made a map lose two more colors, the only way to find out was to look at the
ROM. Here they come out written, they are versioned, and the suite fails if
what is committed does not match —the same as `just protocol --check` does
with the opcodes—. The point is that **the diff warns**: it is what the
goldens do with the pixels, for the decisions.

What is written is **the desired state and not a report**, because phase 2
—already decided— is for the converter to read these files instead of
deciding again. That is why each merge is written as "this color goes to
this other one" and in the order they were applied: replaying the list
rebuilds the whole mapping, which is exactly what
`allocator.merge_least_visible` returns. And that is why an animation writes
the rectangle it is drawn at and not how much it was shrunk: the percentage
is for reading and the rectangle is for applying.

Two examples of how it would be read back, which is what guided the format.
The color mapping of a layer::

    mapping = {}
    for f in patches.read_map(project.auto_patches(), 7)["capas"]["fondo"]["fusiones"]:
        de, a = tuple(f["de"]), tuple(f["a"])
        for viejo, actual in mapping.items():
            if actual == de:
                mapping[viejo] = a
        mapping[de] = a

And the size a battle animation is drawn at, which is a single line because
the decision is a rectangle::

    ta, tal = patches.read_animation(project.auto_patches(), 82)["tamano"]

The key
-------

One file per game situation: ``rom/parches/auto/mapas/<id>.toml`` for the
layers of a map, with one section per layer, and
``rom/parches/auto/animaciones/<n>.toml`` for the battle animations. **The
map id is the game's and not the cartridge's**: it does not move when the
ROM's list of maps changes, nor when the converter's internal order changes,
nor when the allocator's algorithm changes. Colors are written by their
value —15-bit RGB, which is the console's real depth— and not by their index
in any palette, for the same reason: the index shifts with anything and the
value identifies the color forever.

And the cartridge **is not part of the key**: the rule is taro's, from
2026-09-21, and it says that *the versioned decision is always the playable
ROM's*, today `release`. What is versioned is what **the game** lost, which
is the only thing that matters to someone looking at the repo; a test
cartridge reuses it when it applies, and when it does not apply it decides
on its own and that is not versioned. That is why the 29 maps of `abl` are
here and not the 40 the test cartridges build: the eleven extra are
situations that only exist in the suite.

What happens **when `abl`'s decision cannot be applied** in a test cartridge
is, then, an expected path and not an exception: that cartridge decides on
its own, writes what it decided next to its ROM —in
`rom/build/<cartucho>/parches/`, which is not versioned— and `--check` asks
nothing of it. In this kind of decision, moreover, the question never even
comes up: the layer merges depend on the map and its ChipSet and nothing
else —it is the same reason `capas_convertidas` can cache them with a key
that does not know which cartridge is being built—. That this is true **is
not assumed**: `--check` compares against what is versioned **every**
cartridge that carries a versioned map, so if any decided differently, the
suite says so with its name on it. Measured on 2026-09-21: the three test
cartridges of the time and `abl` emit the same 29 files byte for byte.

And one thing the format leaves open on purpose. The direction is for which
maps go in, where the ROM starts and with which party to stop being loose
arguments of a recipe and become **a description** that whoever hands out
palettes can read. A key that names the game situation —the map, and
tomorrow the graphic or the song— does not get in its way: the day it
exists, what changes is where the list of situations comes from, not how
each one is identified.

The battle animations
---------------------

The second kind that stopped being decided silently, and the cheapest of the
ones left: **the size each animation is drawn at**. One that does not fit in
the console's box is shrunk whole, keeping its proportions, and that shows
—number 82 of the intro measures 536x416 in RM2k and is drawn at 64x49,
11%—.

Its key is **the RM2k animation number**, and it is enough alone because the
size comes from `animation.fit_size`, which looks at the box the animation
takes in RM2k and the console's box, which is **a single one for the whole
ROM** —the reason is in `animation.py`: that it does not depend on the map is
what lets the `ShowBattleAnimation`s of every map share the frames already
converted—. Neither the cartridge nor the map is part of it, and it is not
assumed: as with the layers, `--check` compares every cartridge that shows
a versioned animation, and
`test_el_tamano_de_cada_animacion_versionada_sale_de_su_caja_y_de_nada_mas`
redoes the math from what is written.

What **does** depend on the map is something else and is not here: whether
the animation is drawn, which is what `animacion_de_mapa` decides when the
map already took the eight sprite palettes. It is another decision —and
another kind—, and putting it in this file would mix the cartridge with the
game again.

The battlers
------------

The third, from 2026-09-21: since the battle scene is composited on the
console, each battler has **fifteen colors and the transparent one**, and
which ones are lost is a new decision. What is written is the palette that
remained and how many merges were needed —see `battler_text`—, with the
battler's key: its image and its hue, which is what `scene.key` builds.
It looks at neither the troop nor the cartridge: the reduction is of the
already shrunk drawing and nothing else.

What **is not here yet**, and is left for later: the character palettes
—which do depend on the cartridge, because who pays the timer's entry is
decided by `npcs_dibujables` looking at the whole map—, the voices dropped
from a MIDI, the trimmed samples, the fifteen colors each animation is
reduced to, and `DECORATE_TRANSLUCENT`.
"""

import argparse
import collections
import os
import sys
import tomllib

# Run as a script, Python puts this file's folder in `sys.path` and not
# `tools/`: see the same startup in `port/snes_convert.py`.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from common import environment                                  # noqa: E402
from common import project                                  # noqa: E402

# Where the versioned ones live, relative to what the converter decided and
# is versioned: the functions receive that directory —`project.auto_patches()`,
# or a temporary one in the tests— and this is what is appended. Until
# 2026-09-29 they received the repo root and appended `rom/parches/auto/`,
# which is knowing where the game lives.
MAPS_DIR = "mapas"

# Where each cartridge leaves them when it is built, relative to the build
# directory. It is the shape of the build, not where `rom/parches/` is in the
# repo: that is why it does not come from `project`, and does not move with
# it.
MAPS_IN_BUILD = os.path.join("parches", "auto", "mapas")


def map_path(auto, map_id):
    return os.path.join(auto, MAPS_DIR, "%04d.toml" % map_id)


def _color(c):
    return "[%d, %d, %d]" % tuple(c)


def map_text(map_id, name, summary):
    """A map's file, exactly as it goes to disk.

    `summary` is the one `_convert_layers` leaves in `mapa["resumen"]`.
    """
    merges = summary.get("fusiones", {"fondo": [], "encima": []})
    lines = [
        "# Las decisiones artísticas del mapa %d: qué se pierde al pasarlo a la"
        % map_id,
        "# SNES. Lo escribe el conversor y lo regenera `just parches`, que es lo",
        "# que hay que correr cuando un cambio lo mueve; `just parches --check`",
        "# —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
        "",
        "mapa = %d" % map_id,
        "nombre = %s" % _toml_string(name),
    ]
    for layer, count in (("fondo", summary.get("presupuesto")),
                         ("encima", None)):
        lines += ["", "[capas.%s]" % layer]
        if layer == "fondo":
            lines += [
                "# Cuántos colores distintos traía el dibujo y cuántas entradas",
                "# de CGRAM le dejó la capa de encima.",
                "colores = %d" % summary["colores"],
                "presupuesto = %d" % count,
            ]
        lines += [
            "# Cada fusión manda el color `de` al color `a`, en RGB de 15 bits,",
            "# y `pixeles` es cuántos movía cuando se decidió. Van **en orden**:",
            "# aplicarlas de arriba a abajo reconstruye el mapeo entero.",
        ]
        own = merges.get(layer, [])
        if not own:
            lines.append("fusiones = []")
            continue
        lines.append("fusiones = [")
        for victim, dest, pixels in own:
            lines.append("  { de = %s, a = %s, pixeles = %d },"
                         % (_color(victim), _color(dest), pixels))
        lines.append("]")
    return "\n".join(lines) + "\n"


def _toml_string(value):
    return '"%s"' % str(value).replace("\\", "\\\\").replace('"', '\\"')


def _clear(folder):
    """A kind's folder in the build, created and without the previous run's
    `.toml`s. Without this, a cartridge that stops carrying a map or an
    animation still had its old patch next to the ROM, and `check` counted
    it as converted: when the test maps were taken out of `release`, the
    `0052.toml` left behind made `test_parches` fail."""
    os.makedirs(folder, exist_ok=True)
    for old in os.listdir(folder):
        if old.endswith(".toml"):
            os.remove(os.path.join(folder, old))
    return folder


def write_maps(dest, maps):
    """The patches of a cartridge's maps, in
    `<destino>/parches/auto/mapas/`.

    `maps` are the ones the converter's `main()` returns. Returns how many
    files it wrote and how many bytes they take.
    """
    folder = _clear(os.path.join(dest, MAPS_IN_BUILD))
    bytes_ = 0
    for game_map in maps:
        content = map_text(game_map["id"], game_map["nombre"], game_map["resumen"])
        with open(os.path.join(folder, "%04d.toml" % game_map["id"]), "w") as f:
            f.write(content)
        bytes_ += len(content.encode("utf-8"))
    return len(maps), bytes_


# --- the battle animations, which are drawn at another size -----------------

# Like the maps: versioned here, and each cartridge leaves its own next to its
# ROM. The key is **the RM2k animation number**, which is the game's: the same
# 82 in any cartridge that shows it.
ANIMS_DIR = "animaciones"
ANIMS_IN_BUILD = os.path.join("parches", "auto", "animaciones")


def animation_path(auto, number):
    return os.path.join(auto, ANIMS_DIR, "%04d.toml" % number)


def animation_text(data):
    """An animation's file, exactly as it goes to disk.

    `data` is what `snes_convert` builds with `animation.report` and the
    name the animation has in the LDB.
    """
    width, height = data["original"]
    box_w, box_h = data["caja"]
    return "\n".join([
        "# La decisión artística de la animación %d: **a qué tamaño se dibuja**"
        % data["animacion"],
        "# en la consola. Lo escribe el conversor y lo regenera `just parches`,",
        "# que es lo que hay que correr cuando un cambio lo mueve; `just parches",
        "# --check` —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
        "",
        "animacion = %d" % data["animacion"],
        "nombre = %s" % _toml_string(data["nombre"]),
        "hoja = %s" % _toml_string(data["hoja"]),
        "",
        "# Lo decidido: el rectángulo, en pixeles de la consola, al que se",
        "# achica la animación entera para entrar en la caja de %d x %d. Es lo"
        % (data["lado"], data["lado"]),
        "# que la fase 2 va a leer en vez de volver a calcularlo.",
        "tamano = [%d, %d]" % (box_w, box_h),
        "",
        "# De qué venía: la unión de todas las celdas de todos sus cuadros en",
        "# pixeles de RM2k, y cuántos cuadros son. No se decide, se mide, y",
        "# está para que el diff diga por qué cambió el tamaño.",
        "original = [%d, %d]" % (width, height),
        "cuadros = %d" % data["cuadros"],
        "",
    ])


def write_animations(dest, animations):
    """The patches of a cartridge's animations, in
    `<destino>/parches/auto/animaciones/`.

    Returns how many files it wrote and how many bytes they take.
    """
    folder = _clear(os.path.join(dest, ANIMS_IN_BUILD))
    bytes_ = 0
    for data in animations:
        content = animation_text(data)
        with open(os.path.join(folder, "%04d.toml" % data["animacion"]),
                  "w") as f:
            f.write(content)
        bytes_ += len(content.encode("utf-8"))
    return len(animations), bytes_


# --- the battlers, which are reduced to fifteen colors ----------------------

# The third kind, since 2026-09-21: with the battle scene composited on the
# console each battler carries **fifteen colors and the transparent one**, and
# which ones are lost is a decision that did not exist before —the baked scene
# split 96 among the backdrop and all the battlers together—. See
# tools/port/scene.py.
#
# The key is **the battler**: the RM2k image and its hue, `scene.key`. It
# is the game's and does not depend on the cartridge nor on the troop,
# because the reduction looks at the already shrunk drawing and nothing else.
BATTLERS_DIR = "battlers"
BATTLERS_IN_BUILD = os.path.join("parches", "auto", "battlers")


def _file_name(key):
    """The file name of a key: RM2k battlers can have spaces —`sentry
    drone`—, and a file with spaces in the repo is a nuisance in every
    command that names it."""
    return "%s.toml" % str(key).replace(" ", "_")


def battler_path(auto, key):
    return os.path.join(auto, BATTLERS_DIR, _file_name(key))


def battler_text(info):
    """A battler's file, exactly as it goes to disk. `info` is the one
    `scene.battler` returns."""
    lines = [
        "# La decisión artística del battler %s: **qué colores se pierden** al"
        % info["clave"],
        "# llevarlo a quince, que es lo que la escena de la pelea le deja a cada",
        "# uno. Lo escribe el conversor y lo regenera `just parches`, que es lo",
        "# que hay que correr cuando un cambio lo mueve; `just parches --check`",
        "# —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
        "",
        "battler = %s" % _toml_string(info["clave"]),
        "imagen = %s" % _toml_string(info["imagen"]),
        "tono = %d" % info["tono"],
        "",
        "# De qué venía, ya achicado al 80%: el tamaño en pixeles de la escena y",
        "# cuántos colores distintos de 15 bits traía. No se decide, se mide.",
        "tamano = [%d, %d]" % (info["ancho"], info["alto"]),
        "colores = %d" % info["colores"],
        "",
        "# Lo que quedó, en el orden de la paleta: el índice 1 es el primero.",
        "paleta = [",
    ]
    for color in info["paleta"]:
        lines.append("  %s," % _color(color))
    # **The minimal form, on purpose**: the palette that remained and not the
    # list of merges that led to it. An already shrunk battler carries
    # hundreds of colors —the intermediate grays LANCZOS leaves on every
    # edge— and the list measured 179 KB for `abl`'s eleven; what is seen is
    # which fifteen remain, and that is what the diff has to show. The day
    # phase 2 wants to read this instead of deciding, the list comes back: it
    # is `info["fusiones"]`.
    lines += [
        "]",
        "",
        "# Cuántas fusiones hicieron falta para llegar ahí, con",
        "# `asignador.merge_least_visible`: cada una manda al color que menos",
        "# se nota a su vecino más cercano.",
        "fusiones = %d" % len(info["fusiones"]),
    ]
    return "\n".join(lines) + "\n"


def write_battlers(dest, battlers):
    """The patches of a cartridge's battlers, in
    `<destino>/parches/auto/battlers/`. Returns how many and how many
    bytes."""
    folder = _clear(os.path.join(dest, BATTLERS_IN_BUILD))
    bytes_ = 0
    for info in battlers:
        content = battler_text(info)
        with open(os.path.join(folder, _file_name(info["clave"])), "w") as f:
            f.write(content)
        bytes_ += len(content.encode("utf-8"))
    return len(battlers), bytes_


def read_battler(auto, key):
    return _read_toml(battler_path(auto, key))


def battler_diff(old, new):
    """What changed between two battler patches, in plain words: first
    whether another color is lost, then why."""
    out = []
    before = [tuple(c) for c in old.get("paleta", [])]
    after = [tuple(c) for c in new.get("paleta", [])]
    for c in after:
        if c not in before:
            out.append("keeps %s, which used to be merged"
                       % _color(c))
    for c in before:
        if c not in after:
            out.append("loses %s, which used to stay" % _color(c))
    if not out and before != after:
        out.append("the same colors in another palette order")
    for field in ("tamano", "colores", "imagen", "tono"):
        if old.get(field) != new.get(field):
            out.append("%s went from %s to %s"
                       % (field, old.get(field), new.get(field)))
    if old.get("fusiones") != new.get("fusiones"):
        out.append("%s merges were needed and now %s"
                   % (old.get("fusiones"), new.get("fusiones")))
    return out


# --- what is not the game's -------------------------------------------------

# Who asked for each of the cartridge's patches, next to its patches and **not
# versioned**: the converter writes it —see `usos_de_los_parches` in
# snes_convert.py— and `only_for_tests` reads it. It is needed since the ROM that
# is played also carries the suite's maps and pages.
USES_FILE = os.path.join("parches", "usos.json")


def write_uses(dest, uses):
    """`uses` is `{kind key: {key: [origin, ...]}}`; the origin is a map id
    or `"caso"`."""
    import json
    with open(os.path.join(dest, USES_FILE), "w") as f:
        json.dump({kind: {str(k): sorted(v, key=str)
                          for k, v in sorted(which_ones.items(), key=str)}
                   for kind, which_ones in uses.items()}, f, indent=1)


def test_maps():
    """The maps that only exist for the suite. The project file declares
    them, `[maps] test`, and `cartridges.py` reads them; they are not written
    again here."""
    from assembly import cartridges
    return set(cartridges.TEST_MAPS)


def only_for_tests(build, kind, which, tests):
    """Whether `which` is in cartridge `build` only for the suite: a test
    map, or an animation or a battler that only the test maps and the cases'
    pages ask for. `tests` is `test_maps()`.

    Without `usos.json`, or without a known origin, **no**: doubt goes to the
    side of asking for the patch, which is the complaint that shows.
    """
    if kind.key == "mapa":
        return which in tests
    import json
    try:
        with open(os.path.join(build, USES_FILE)) as f:
            origins = json.load(f).get(kind.key, {}).get(str(which))
    except OSError:
        return False
    return bool(origins) and all(o == "caso" or o in tests
                                 for o in origins)


# --- the check -------------------------------------------------------------

def _read_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def read_map(auto, map_id):
    """What was decided and versioned for a map, parsed.

    It is phase 2's entry point and the check uses it, which is what keeps it
    alive while phase 2 does not exist.
    """
    return _read_toml(map_path(auto, map_id))


def read_animation(auto, number):
    """What was decided and versioned for a battle animation, parsed."""
    return _read_toml(animation_path(auto, number))


def _merges(doc, layer):
    return [(tuple(f["de"]), tuple(f["a"]), f["pixeles"])
            for f in doc.get("capas", {}).get(layer, {}).get("fusiones", [])]


def map_diff(old, new):
    """Which decision changed between two already parsed patches, in plain
    words.

    It is not a text diff: a file that differs only in a comment says
    nothing, and one where a merge changed has to say **which**. It is the
    only thing that makes the check useful: "the file differs" sends you to
    run `diff` and guess whether the change matters.
    """
    out = []
    for layer in ("fondo", "encima"):
        before, after = _merges(old, layer), _merges(new, layer)
        for field in ("colores", "presupuesto"):
            a = old.get("capas", {}).get(layer, {}).get(field)
            b = new.get("capas", {}).get(layer, {}).get(field)
            if a != b:
                out.append("layer %s: %s went from %s to %s"
                           % (layer, field, a, b))
        if len(before) != len(after):
            out.append("layer %s: it merged %d color(s) and now merges %d"
                       % (layer, len(before), len(after)))
        for i, (a, b) in enumerate(zip(before, after)):
            if a[:2] != b[:2]:
                out.append(
                    "layer %s: merge %d sent %s to %s and now sends %s to %s"
                    % (layer, i, _color(a[0]), _color(a[1]),
                       _color(b[0]), _color(b[1])))
            elif a[2] != b[2]:
                out.append(
                    "layer %s: merge %d of %s moved %d pixel(s) and now "
                    "moves %d" % (layer, i, _color(a[0]), a[2], b[2]))
        extra = after[len(before):] if len(after) > len(before) else []
        missing = before[len(after):] if len(before) > len(after) else []
        for v, d, _p in extra:
            out.append("layer %s: extra merge %s -> %s"
                       % (layer, _color(v), _color(d)))
        for v, d, _p in missing:
            out.append("layer %s: no longer merges %s -> %s"
                       % (layer, _color(v), _color(d)))
    return out


def animation_diff(old, new):
    """What changed between two animation patches, in plain words.

    What matters is the first line: **the size it is drawn at**. The other
    two say why it changed —the animation measures something else in RM2k,
    or has other frames—, and they can come out alone: the box not moving
    does not mean the animation is the same.
    """
    out = []
    if old.get("tamano") != new.get("tamano"):
        out.append("it was drawn at %s and now it is drawn at %s"
                   % (_sides(old.get("tamano")),
                      _sides(new.get("tamano"))))
    if old.get("original") != new.get("original"):
        out.append("it came from %s in RM2k and now comes from %s"
                   % (_sides(old.get("original")),
                      _sides(new.get("original"))))
    if old.get("cuadros") != new.get("cuadros"):
        out.append("it had %s frame(s) and now has %s"
                   % (old.get("cuadros"), new.get("cuadros")))
    if old.get("hoja") != new.get("hoja"):
        out.append("it came from sheet %r and now comes from %r"
                   % (old.get("hoja"), new.get("hoja")))
    return out


def _sides(pair):
    return "%dx%d" % tuple(pair) if pair else "nothing"


# The kinds of decision that are written, each with its directory, the key
# that identifies it —which is always something **of the game**— and how
# what changed is told. Adding a kind is adding a row here and its `map_text`:
# the check, the copy to `rom/parches/` and the messages come from this one.
Kind = collections.namedtuple(
    "Kind", "name article directory in_build key read diff")

KINDS = (
    Kind("map(s)", "map", MAPS_DIR, MAPS_IN_BUILD, "mapa", read_map,
         map_diff),
    Kind("animation(s)", "animation", ANIMS_DIR, ANIMS_IN_BUILD,
         "animacion", read_animation, animation_diff),
    Kind("battler(s)", "battler", BATTLERS_DIR, BATTLERS_IN_BUILD, "battler",
         read_battler, battler_diff),
)


def versioned(auto, kind=None):
    """The ones with a versioned patch, that is the playable ROM's.

    Without `kind`, the maps: it is what the callers asked for when this was
    the only kind there was.
    """
    kind = kind or KINDS[0]
    folder = os.path.join(auto, kind.directory)
    if not os.path.isdir(folder):
        return []
    # The key is read from inside the file and not from the name: a battler's
    # is a text, and its file name does not carry the spaces. See `_file_name`.
    return sorted(_read_toml(os.path.join(folder, n))[kind.key]
                  for n in os.listdir(folder) if n.endswith(".toml"))


def check(auto, builds, playable="release"):
    """The builds' patches against the versioned ones: (quejas, propios).

    `builds` are directories of built cartridges, and **all** of them are
    looked at. What is not versioned is not a complaint: it is a situation
    `abl` does not have —a map it does not carry, an animation it does not
    show—, so the test cartridge decided on its own and that is not
    versioned; it comes out in `own`, which is information about how
    much the cartridges resemble the game and not an error. For the playable
    ROM, on the other hand, everything has to be versioned **except what it
    carries only for the suite** —see `only_for_tests`—, which also comes out in
    `own`.

    What **is** versioned is compared against what is committed in every
    cartridge that carries it. For today's two kinds that cannot differ
    —neither the layer merges nor the size of an animation look at the
    cartridge— and that is why it complains: if it did differ, what broke is
    that independence, and it is better to find out there and not in
    phase 2.

    `own` goes per kind: `{"mapa": {7: ["test-special"]}, ...}`, with
    each one's key.
    """
    complaints, own = [], {}
    for kind in KINDS:
        theirs, mine = _check_kind(kind, auto, builds, playable)
        complaints += theirs
        if mine:
            own[kind.key] = mine
    return complaints, own


def _check_kind(kind, auto, builds, playable):
    complaints, own = [], {}
    tests = test_maps()
    have = set(versioned(auto, kind))
    seen = set()
    # One complaint per situation **and per set of differences**: four
    # cartridges that carry the same map all say the same thing, and
    # repeating it four times buries the others'. If one decided differently
    # from the rest, its differences are different and its complaint comes
    # out anyway, with its name.
    said = set()
    for build in builds:
        folder = os.path.join(build, kind.in_build)
        if not os.path.isdir(folder):
            continue
        cartridge = os.path.basename(os.path.normpath(build))
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".toml"):
                continue
            doc = _read_toml(os.path.join(folder, name))
            which = doc[kind.key]
            if which not in have:
                if cartridge == playable and not only_for_tests(build, kind, which,
                                                          tests):
                    # What the playable ROM converts **has** to be versioned:
                    # otherwise the game loses something somewhere and it is
                    # not written down. In a test cartridge, on the other
                    # hand, it is normal and nothing is said.
                    complaints.append(
                        "%s %s went into «%s», the playable ROM, and has no "
                        "versioned patch: run `just parches`."
                        % (kind.article, which, cartridge))
                else:
                    own.setdefault(which, []).append(cartridge)
                continue
            seen.add(which)
            versioned_path = os.path.join(auto, kind.directory, name)
            changes = kind.diff(kind.read(auto, which), doc)
            if changes and (which, tuple(changes)) not in said:
                said.add((which, tuple(changes)))
                complaints.append(
                    "%s is stale (cartridge «%s» says so), and what "
                    "changed in %s %s is this:\n    %s\n"
                    "  If the change is the one intended, `just parches` and "
                    "commit; if not, something moved what is seen."
                    % (os.path.relpath(versioned_path), cartridge,
                       kind.article, which, "\n    ".join(changes)))
    for which in sorted(have - seen):
        complaints.append(
            "%s %s has a versioned patch and none of the built cartridges "
            "converts it: either the game stopped carrying it —and then the "
            "file is left over— or the cartridge that has it is not built."
            % (kind.article, which))
    return complaints, own


def main(argv=None):
    project.from_command_line(argv)
    auto = project.auto_patches()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    project.add_argument(parser)
    environment.add_arguments(parser, "test_cartridges")
    parser.add_argument(
        "builds", nargs="*",
        help="the directories of the built cartridges. Without --check it has "
             "to be the playable ROM's and nothing else: what is versioned is "
             "what `abl` decides. With --check and none given, those of all "
             "the cartridges in `cartridges.py`")
    parser.add_argument("--check", action="store_true",
                        help="do not write: fail if what is versioned is stale")
    args = parser.parse_args(argv)
    environment.from_arguments(args, "test_cartridges")
    if not args.builds and args.check:
        from assembly import cartridges
        args.builds = [cartridges.directory(n) for n in cartridges.CARTRIDGES]
    builds = []
    for build in args.builds:
        if _has_patches(build):
            builds.append(build)
        else:
            builds += [os.path.join(build, n) for n in sorted(os.listdir(build))
                       if _has_patches(os.path.join(build, n))]
    if not builds:
        sys.exit("found no built cartridge with patches inside: %s"
                 % ", ".join(args.builds))
    if args.check:
        complaints, own = check(auto, builds)
        for complaint in complaints:
            print("  " + complaint, file=sys.stderr)
        if complaints:
            sys.exit("%d patch(es) do not match what the converter decides"
                     % len(complaints))
        for kind in KINDS:
            print("the game's %d patch(es) of %s match what %d "
                  "cartridge(s) decided"
                  % (len(versioned(auto, kind)), kind.name, len(builds)))
            mine = own.get(kind.key)
            if mine:
                # It is not a complaint: they are situations `abl` does not
                # have, so the test cartridge decided on its own and that is
                # not versioned. It is printed because it says how much the
                # suite resembles the game.
                print("  and %d that only exist for the suite, "
                      "which decide on their own: %s"
                      % (len(mine), ", ".join(str(m) for m in sorted(mine))))
        return
    if len(builds) != 1:
        sys.exit("what is versioned is what **one** ROM decides, the playable "
                 "one: pass `rom/build/release` and not %d cartridges"
                 % len(builds))
    for kind in KINDS:
        _copy(auto, builds[0], kind)


def _has_patches(build):
    return any(os.path.isdir(os.path.join(build, c.in_build))
               for c in KINDS)


def _copy(auto, build, kind):
    """What the playable ROM decided, to `rom/parches/`, and out with what is
    no longer there."""
    dest = os.path.join(auto, kind.directory)
    os.makedirs(dest, exist_ok=True)
    folder = os.path.join(build, kind.in_build)
    seen, bytes_ = set(), 0
    tests = test_maps()
    for name in sorted(os.listdir(folder) if os.path.isdir(folder) else []):
        if not name.endswith(".toml"):
            continue
        # What the playable ROM carries only for the suite is not versioned:
        # see `only_for_tests`.
        if only_for_tests(build, kind, _read_toml(os.path.join(folder, name))[
                kind.key], tests):
            continue
        with open(os.path.join(folder, name)) as f:
            content = f.read()
        with open(os.path.join(dest, name), "w") as f:
            f.write(content)
        seen.add(name)
        bytes_ += len(content.encode("utf-8"))
    for name in sorted(os.listdir(dest)):
        if name.endswith(".toml") and name not in seen:
            os.remove(os.path.join(dest, name))
            print("  %s: the game no longer carries it, removing it"
                  % os.path.relpath(os.path.join(dest, name)))
    print("%d patch(es) in %s, %d B" % (len(seen), os.path.relpath(dest),
                                         bytes_))


if __name__ == "__main__":
    main()

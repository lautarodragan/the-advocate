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
    for f in parches.leer(project.auto_patches(), 7)["capas"]["fondo"]["fusiones"]:
        de, a = tuple(f["de"]), tuple(f["a"])
        for viejo, actual in mapping.items():
            if actual == de:
                mapping[viejo] = a
        mapping[de] = a

And the size a battle animation is drawn at, which is a single line because
the decision is a rectangle::

    ta, tal = parches.leer_animacion(project.auto_patches(), 82)["tamano"]

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
size comes from `animacion.tamano`, which looks at the box the animation
takes in RM2k and the console's box, which is **a single one for the whole
ROM** —the reason is in `animacion.py`: that it does not depend on the map is
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
remained and how many merges were needed —see `texto_battler`—, with the
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
DIRECTORIO = "mapas"

# Where each cartridge leaves them when it is built, relative to the build
# directory. It is the shape of the build, not where `rom/parches/` is in the
# repo: that is why it does not come from `project`, and does not move with
# it.
EN_BUILD = os.path.join("parches", "auto", "mapas")


def ruta(auto, map_id):
    return os.path.join(auto, DIRECTORIO, "%04d.toml" % map_id)


def _color(c):
    return "[%d, %d, %d]" % tuple(c)


def texto(map_id, nombre, resumen):
    """A map's file, exactly as it goes to disk.

    `resumen` is the one `_convert_layers` leaves in `mapa["resumen"]`.
    """
    fusiones = resumen.get("fusiones", {"fondo": [], "encima": []})
    lineas = [
        "# Las decisiones artísticas del mapa %d: qué se pierde al pasarlo a la"
        % map_id,
        "# SNES. Lo escribe el conversor y lo regenera `just parches`, que es lo",
        "# que hay que correr cuando un cambio lo mueve; `just parches --check`",
        "# —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
        "",
        "mapa = %d" % map_id,
        "nombre = %s" % _cadena(nombre),
    ]
    for capa, cuantos in (("fondo", resumen.get("presupuesto")),
                          ("encima", None)):
        lineas += ["", "[capas.%s]" % capa]
        if capa == "fondo":
            lineas += [
                "# Cuántos colores distintos traía el dibujo y cuántas entradas",
                "# de CGRAM le dejó la capa de encima.",
                "colores = %d" % resumen["colores"],
                "presupuesto = %d" % cuantos,
            ]
        lineas += [
            "# Cada fusión manda el color `de` al color `a`, en RGB de 15 bits,",
            "# y `pixeles` es cuántos movía cuando se decidió. Van **en orden**:",
            "# aplicarlas de arriba a abajo reconstruye el mapeo entero.",
        ]
        propias = fusiones.get(capa, [])
        if not propias:
            lineas.append("fusiones = []")
            continue
        lineas.append("fusiones = [")
        for victima, destino, pixeles in propias:
            lineas.append("  { de = %s, a = %s, pixeles = %d },"
                          % (_color(victima), _color(destino), pixeles))
        lineas.append("]")
    return "\n".join(lineas) + "\n"


def _cadena(valor):
    return '"%s"' % str(valor).replace("\\", "\\\\").replace('"', '\\"')


def _vaciar(carpeta):
    """A kind's folder in the build, created and without the previous run's
    `.toml`s. Without this, a cartridge that stops carrying a map or an
    animation still had its old patch next to the ROM, and `revisar` counted
    it as converted: when the test maps were taken out of `release`, the
    `0052.toml` left behind made `test_parches` fail."""
    os.makedirs(carpeta, exist_ok=True)
    for viejo in os.listdir(carpeta):
        if viejo.endswith(".toml"):
            os.remove(os.path.join(carpeta, viejo))
    return carpeta


def escribir(destino, mapas):
    """The patches of a cartridge's maps, in
    `<destino>/parches/auto/mapas/`.

    `mapas` are the ones the converter's `main()` returns. Returns how many
    files it wrote and how many bytes they take.
    """
    carpeta = _vaciar(os.path.join(destino, EN_BUILD))
    bytes_ = 0
    for mapa in mapas:
        contenido = texto(mapa["id"], mapa["nombre"], mapa["resumen"])
        with open(os.path.join(carpeta, "%04d.toml" % mapa["id"]), "w") as f:
            f.write(contenido)
        bytes_ += len(contenido.encode("utf-8"))
    return len(mapas), bytes_


# --- the battle animations, which are drawn at another size -----------------

# Like the maps: versioned here, and each cartridge leaves its own next to its
# ROM. The key is **the RM2k animation number**, which is the game's: the same
# 82 in any cartridge that shows it.
DIRECTORIO_ANIM = "animaciones"
EN_BUILD_ANIM = os.path.join("parches", "auto", "animaciones")


def ruta_animacion(auto, numero):
    return os.path.join(auto, DIRECTORIO_ANIM, "%04d.toml" % numero)


def texto_animacion(datos):
    """An animation's file, exactly as it goes to disk.

    `datos` is what `snes_convert` builds with `animacion.informe` and the
    name the animation has in the LDB.
    """
    ancho, alto = datos["original"]
    ta, tal = datos["caja"]
    return "\n".join([
        "# La decisión artística de la animación %d: **a qué tamaño se dibuja**"
        % datos["animacion"],
        "# en la consola. Lo escribe el conversor y lo regenera `just parches`,",
        "# que es lo que hay que correr cuando un cambio lo mueve; `just parches",
        "# --check` —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
        "",
        "animacion = %d" % datos["animacion"],
        "nombre = %s" % _cadena(datos["nombre"]),
        "hoja = %s" % _cadena(datos["hoja"]),
        "",
        "# Lo decidido: el rectángulo, en pixeles de la consola, al que se",
        "# achica la animación entera para entrar en la caja de %d x %d. Es lo"
        % (datos["lado"], datos["lado"]),
        "# que la fase 2 va a leer en vez de volver a calcularlo.",
        "tamano = [%d, %d]" % (ta, tal),
        "",
        "# De qué venía: la unión de todas las celdas de todos sus cuadros en",
        "# pixeles de RM2k, y cuántos cuadros son. No se decide, se mide, y",
        "# está para que el diff diga por qué cambió el tamaño.",
        "original = [%d, %d]" % (ancho, alto),
        "cuadros = %d" % datos["cuadros"],
        "",
    ])


def escribir_animaciones(destino, animaciones):
    """The patches of a cartridge's animations, in
    `<destino>/parches/auto/animaciones/`.

    Returns how many files it wrote and how many bytes they take.
    """
    carpeta = _vaciar(os.path.join(destino, EN_BUILD_ANIM))
    bytes_ = 0
    for datos in animaciones:
        contenido = texto_animacion(datos)
        with open(os.path.join(carpeta, "%04d.toml" % datos["animacion"]),
                  "w") as f:
            f.write(contenido)
        bytes_ += len(contenido.encode("utf-8"))
    return len(animaciones), bytes_


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
DIRECTORIO_BAT = "battlers"
EN_BUILD_BAT = os.path.join("parches", "auto", "battlers")


def _archivo(clave):
    """The file name of a key: RM2k battlers can have spaces —`sentry
    drone`—, and a file with spaces in the repo is a nuisance in every
    command that names it."""
    return "%s.toml" % str(clave).replace(" ", "_")


def ruta_battler(auto, clave):
    return os.path.join(auto, DIRECTORIO_BAT, _archivo(clave))


def texto_battler(info):
    """A battler's file, exactly as it goes to disk. `info` is the one
    `scene.battler` returns."""
    lineas = [
        "# La decisión artística del battler %s: **qué colores se pierden** al"
        % info["clave"],
        "# llevarlo a quince, que es lo que la escena de la pelea le deja a cada",
        "# uno. Lo escribe el conversor y lo regenera `just parches`, que es lo",
        "# que hay que correr cuando un cambio lo mueve; `just parches --check`",
        "# —y la tanda— fallan si quedó viejo. Ver `rm2k-snes-patches`.",
        "",
        "battler = %s" % _cadena(info["clave"]),
        "imagen = %s" % _cadena(info["imagen"]),
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
        lineas.append("  %s," % _color(color))
    # **The minimal form, on purpose**: the palette that remained and not the
    # list of merges that led to it. An already shrunk battler carries
    # hundreds of colors —the intermediate grays LANCZOS leaves on every
    # edge— and the list measured 179 KB for `abl`'s eleven; what is seen is
    # which fifteen remain, and that is what the diff has to show. The day
    # phase 2 wants to read this instead of deciding, the list comes back: it
    # is `info["fusiones"]`.
    lineas += [
        "]",
        "",
        "# Cuántas fusiones hicieron falta para llegar ahí, con",
        "# `asignador.merge_least_visible`: cada una manda al color que menos",
        "# se nota a su vecino más cercano.",
        "fusiones = %d" % len(info["fusiones"]),
    ]
    return "\n".join(lineas) + "\n"


def escribir_battlers(destino, battlers):
    """The patches of a cartridge's battlers, in
    `<destino>/parches/auto/battlers/`. Returns how many and how many
    bytes."""
    carpeta = _vaciar(os.path.join(destino, EN_BUILD_BAT))
    bytes_ = 0
    for info in battlers:
        contenido = texto_battler(info)
        with open(os.path.join(carpeta, _archivo(info["clave"])), "w") as f:
            f.write(contenido)
        bytes_ += len(contenido.encode("utf-8"))
    return len(battlers), bytes_


def leer_battler(auto, clave):
    return _leer(ruta_battler(auto, clave))


def diferencias_battler(viejo, nuevo):
    """What changed between two battler patches, in plain words: first
    whether another color is lost, then why."""
    salida = []
    antes = [tuple(c) for c in viejo.get("paleta", [])]
    ahora = [tuple(c) for c in nuevo.get("paleta", [])]
    for c in ahora:
        if c not in antes:
            salida.append("keeps %s, which used to be merged"
                          % _color(c))
    for c in antes:
        if c not in ahora:
            salida.append("loses %s, which used to stay" % _color(c))
    if not salida and antes != ahora:
        salida.append("the same colors in another palette order")
    for campo in ("tamano", "colores", "imagen", "tono"):
        if viejo.get(campo) != nuevo.get(campo):
            salida.append("%s went from %s to %s"
                          % (campo, viejo.get(campo), nuevo.get(campo)))
    if viejo.get("fusiones") != nuevo.get("fusiones"):
        salida.append("%s merges were needed and now %s"
                      % (viejo.get("fusiones"), nuevo.get("fusiones")))
    return salida


# --- what is not the game's -------------------------------------------------

# Who asked for each of the cartridge's patches, next to its patches and **not
# versioned**: the converter writes it —see `usos_de_los_parches` in
# snes_convert.py— and `de_prueba` reads it. It is needed since the ROM that
# is played also carries the suite's maps and pages.
USOS = os.path.join("parches", "usos.json")


def escribir_usos(destino, usos):
    """`usos` is `{kind key: {key: [origin, ...]}}`; the origin is a map id
    or `"caso"`."""
    import json
    with open(os.path.join(destino, USOS), "w") as f:
        json.dump({clase: {str(k): sorted(v, key=str)
                           for k, v in sorted(cuales.items(), key=str)}
                   for clase, cuales in usos.items()}, f, indent=1)


def mapas_de_prueba():
    """The maps that only exist for the suite. The project file declares
    them, `[maps] test`, and `cartridges.py` reads them; they are not written
    again here."""
    from assembly import cartridges
    return set(cartridges.TEST_MAPS)


def de_prueba(build, clase, cual, prueba):
    """Whether `cual` is in cartridge `build` only for the suite: a test
    map, or an animation or a battler that only the test maps and the cases'
    pages ask for. `prueba` is `mapas_de_prueba()`.

    Without `usos.json`, or without a known origin, **no**: doubt goes to the
    side of asking for the patch, which is the complaint that shows.
    """
    if clase.clave == "mapa":
        return cual in prueba
    import json
    try:
        with open(os.path.join(build, USOS)) as f:
            origenes = json.load(f).get(clase.clave, {}).get(str(cual))
    except OSError:
        return False
    return bool(origenes) and all(o == "caso" or o in prueba
                                  for o in origenes)


# --- the check -------------------------------------------------------------

def _leer(ruta_):
    with open(ruta_, "rb") as f:
        return tomllib.load(f)


def leer(auto, map_id):
    """What was decided and versioned for a map, parsed.

    It is phase 2's entry point and the check uses it, which is what keeps it
    alive while phase 2 does not exist.
    """
    return _leer(ruta(auto, map_id))


def leer_animacion(auto, numero):
    """What was decided and versioned for a battle animation, parsed."""
    return _leer(ruta_animacion(auto, numero))


def _fusiones(doc, capa):
    return [(tuple(f["de"]), tuple(f["a"]), f["pixeles"])
            for f in doc.get("capas", {}).get(capa, {}).get("fusiones", [])]


def diferencias(viejo, nuevo):
    """Which decision changed between two already parsed patches, in plain
    words.

    It is not a text diff: a file that differs only in a comment says
    nothing, and one where a merge changed has to say **which**. It is the
    only thing that makes the check useful: "the file differs" sends you to
    run `diff` and guess whether the change matters.
    """
    salida = []
    for capa in ("fondo", "encima"):
        antes, ahora = _fusiones(viejo, capa), _fusiones(nuevo, capa)
        for campo in ("colores", "presupuesto"):
            a = viejo.get("capas", {}).get(capa, {}).get(campo)
            b = nuevo.get("capas", {}).get(capa, {}).get(campo)
            if a != b:
                salida.append("layer %s: %s went from %s to %s"
                              % (capa, campo, a, b))
        if len(antes) != len(ahora):
            salida.append("layer %s: it merged %d color(s) and now merges %d"
                          % (capa, len(antes), len(ahora)))
        for i, (a, b) in enumerate(zip(antes, ahora)):
            if a[:2] != b[:2]:
                salida.append(
                    "layer %s: merge %d sent %s to %s and now sends %s to %s"
                    % (capa, i, _color(a[0]), _color(a[1]),
                       _color(b[0]), _color(b[1])))
            elif a[2] != b[2]:
                salida.append(
                    "layer %s: merge %d of %s moved %d pixel(s) and now "
                    "moves %d" % (capa, i, _color(a[0]), a[2], b[2]))
        sobran = ahora[len(antes):] if len(ahora) > len(antes) else []
        faltan = antes[len(ahora):] if len(antes) > len(ahora) else []
        for v, d, _p in sobran:
            salida.append("layer %s: extra merge %s -> %s"
                          % (capa, _color(v), _color(d)))
        for v, d, _p in faltan:
            salida.append("layer %s: no longer merges %s -> %s"
                          % (capa, _color(v), _color(d)))
    return salida


def diferencias_animacion(viejo, nuevo):
    """What changed between two animation patches, in plain words.

    What matters is the first line: **the size it is drawn at**. The other
    two say why it changed —the animation measures something else in RM2k,
    or has other frames—, and they can come out alone: the box not moving
    does not mean the animation is the same.
    """
    salida = []
    if viejo.get("tamano") != nuevo.get("tamano"):
        salida.append("it was drawn at %s and now it is drawn at %s"
                      % (_lados(viejo.get("tamano")),
                         _lados(nuevo.get("tamano"))))
    if viejo.get("original") != nuevo.get("original"):
        salida.append("it came from %s in RM2k and now comes from %s"
                      % (_lados(viejo.get("original")),
                         _lados(nuevo.get("original"))))
    if viejo.get("cuadros") != nuevo.get("cuadros"):
        salida.append("it had %s frame(s) and now has %s"
                      % (viejo.get("cuadros"), nuevo.get("cuadros")))
    if viejo.get("hoja") != nuevo.get("hoja"):
        salida.append("it came from sheet %r and now comes from %r"
                      % (viejo.get("hoja"), nuevo.get("hoja")))
    return salida


def _lados(par):
    return "%dx%d" % tuple(par) if par else "nothing"


# The kinds of decision that are written, each with its directory, the key
# that identifies it —which is always something **of the game**— and how
# what changed is told. Adding a kind is adding a row here and its `texto`:
# the check, the copy to `rom/parches/` and the messages come from this one.
Clase = collections.namedtuple(
    "Clase", "nombre articulo directorio en_build clave leer diferencias")

CLASES = (
    Clase("map(s)", "map", DIRECTORIO, EN_BUILD, "mapa", leer,
          diferencias),
    Clase("animation(s)", "animation", DIRECTORIO_ANIM, EN_BUILD_ANIM,
          "animacion", leer_animacion, diferencias_animacion),
    Clase("battler(s)", "battler", DIRECTORIO_BAT, EN_BUILD_BAT, "battler",
          leer_battler, diferencias_battler),
)


def versionados(auto, clase=None):
    """The ones with a versioned patch, that is the playable ROM's.

    Without `clase`, the maps: it is what the callers asked for when this was
    the only kind there was.
    """
    clase = clase or CLASES[0]
    carpeta = os.path.join(auto, clase.directorio)
    if not os.path.isdir(carpeta):
        return []
    # The key is read from inside the file and not from the name: a battler's
    # is a text, and its file name does not carry the spaces. See `_archivo`.
    return sorted(_leer(os.path.join(carpeta, n))[clase.clave]
                  for n in os.listdir(carpeta) if n.endswith(".toml"))


def revisar(auto, builds, jugable="release"):
    """The builds' patches against the versioned ones: (quejas, propios).

    `builds` are directories of built cartridges, and **all** of them are
    looked at. What is not versioned is not a complaint: it is a situation
    `abl` does not have —a map it does not carry, an animation it does not
    show—, so the test cartridge decided on its own and that is not
    versioned; it comes out in `propios`, which is information about how
    much the cartridges resemble the game and not an error. For the playable
    ROM, on the other hand, everything has to be versioned **except what it
    carries only for the suite** —see `de_prueba`—, which also comes out in
    `propios`.

    What **is** versioned is compared against what is committed in every
    cartridge that carries it. For today's two kinds that cannot differ
    —neither the layer merges nor the size of an animation look at the
    cartridge— and that is why it complains: if it did differ, what broke is
    that independence, and it is better to find out there and not in
    phase 2.

    `propios` goes per kind: `{"mapa": {7: ["test-special"]}, ...}`, with
    each one's key.
    """
    quejas, propios = [], {}
    for clase in CLASES:
        suyas, mios = _revisar_clase(clase, auto, builds, jugable)
        quejas += suyas
        if mios:
            propios[clase.clave] = mios
    return quejas, propios


def _revisar_clase(clase, auto, builds, jugable):
    quejas, propios = [], {}
    prueba = mapas_de_prueba()
    tengo = set(versionados(auto, clase))
    vistos = set()
    # One complaint per situation **and per set of differences**: four
    # cartridges that carry the same map all say the same thing, and
    # repeating it four times buries the others'. If one decided differently
    # from the rest, its differences are different and its complaint comes
    # out anyway, with its name.
    dichas = set()
    for build in builds:
        carpeta = os.path.join(build, clase.en_build)
        if not os.path.isdir(carpeta):
            continue
        cartucho = os.path.basename(os.path.normpath(build))
        for nombre in sorted(os.listdir(carpeta)):
            if not nombre.endswith(".toml"):
                continue
            doc = _leer(os.path.join(carpeta, nombre))
            cual = doc[clase.clave]
            if cual not in tengo:
                if cartucho == jugable and not de_prueba(build, clase, cual,
                                                          prueba):
                    # What the playable ROM converts **has** to be versioned:
                    # otherwise the game loses something somewhere and it is
                    # not written down. In a test cartridge, on the other
                    # hand, it is normal and nothing is said.
                    quejas.append(
                        "%s %s went into «%s», the playable ROM, and has no "
                        "versioned patch: run `just parches`."
                        % (clase.articulo, cual, cartucho))
                else:
                    propios.setdefault(cual, []).append(cartucho)
                continue
            vistos.add(cual)
            versionado = os.path.join(auto, clase.directorio, nombre)
            cambios = clase.diferencias(clase.leer(auto, cual), doc)
            if cambios and (cual, tuple(cambios)) not in dichas:
                dichas.add((cual, tuple(cambios)))
                quejas.append(
                    "%s is stale (cartridge «%s» says so), and what "
                    "changed in %s %s is this:\n    %s\n"
                    "  If the change is the one intended, `just parches` and "
                    "commit; if not, something moved what is seen."
                    % (os.path.relpath(versionado), cartucho,
                       clase.articulo, cual, "\n    ".join(cambios)))
    for cual in sorted(tengo - vistos):
        quejas.append(
            "%s %s has a versioned patch and none of the built cartridges "
            "converts it: either the game stopped carrying it —and then the "
            "file is left over— or the cartridge that has it is not built."
            % (clase.articulo, cual))
    return quejas, propios


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
        if _tiene_parches(build):
            builds.append(build)
        else:
            builds += [os.path.join(build, n) for n in sorted(os.listdir(build))
                       if _tiene_parches(os.path.join(build, n))]
    if not builds:
        sys.exit("found no built cartridge with patches inside: %s"
                 % ", ".join(args.builds))
    if args.check:
        quejas, propios = revisar(auto, builds)
        for queja in quejas:
            print("  " + queja, file=sys.stderr)
        if quejas:
            sys.exit("%d patch(es) do not match what the converter decides"
                     % len(quejas))
        for clase in CLASES:
            print("the game's %d patch(es) of %s match what %d "
                  "cartridge(s) decided"
                  % (len(versionados(auto, clase)), clase.nombre, len(builds)))
            mios = propios.get(clase.clave)
            if mios:
                # It is not a complaint: they are situations `abl` does not
                # have, so the test cartridge decided on its own and that is
                # not versioned. It is printed because it says how much the
                # suite resembles the game.
                print("  and %d that only exist for the suite, "
                      "which decide on their own: %s"
                      % (len(mios), ", ".join(str(m) for m in sorted(mios))))
        return
    if len(builds) != 1:
        sys.exit("what is versioned is what **one** ROM decides, the playable "
                 "one: pass `rom/build/release` and not %d cartridges"
                 % len(builds))
    for clase in CLASES:
        _copiar(auto, builds[0], clase)


def _tiene_parches(build):
    return any(os.path.isdir(os.path.join(build, c.en_build))
               for c in CLASES)


def _copiar(auto, build, clase):
    """What the playable ROM decided, to `rom/parches/`, and out with what is
    no longer there."""
    destino = os.path.join(auto, clase.directorio)
    os.makedirs(destino, exist_ok=True)
    carpeta = os.path.join(build, clase.en_build)
    vistos, bytes_ = set(), 0
    prueba = mapas_de_prueba()
    for nombre in sorted(os.listdir(carpeta) if os.path.isdir(carpeta) else []):
        if not nombre.endswith(".toml"):
            continue
        # What the playable ROM carries only for the suite is not versioned:
        # see `de_prueba`.
        if de_prueba(build, clase, _leer(os.path.join(carpeta, nombre))[
                clase.clave], prueba):
            continue
        with open(os.path.join(carpeta, nombre)) as f:
            contenido = f.read()
        with open(os.path.join(destino, nombre), "w") as f:
            f.write(contenido)
        vistos.add(nombre)
        bytes_ += len(contenido.encode("utf-8"))
    for nombre in sorted(os.listdir(destino)):
        if nombre.endswith(".toml") and nombre not in vistos:
            os.remove(os.path.join(destino, nombre))
            print("  %s: the game no longer carries it, removing it"
                  % os.path.relpath(os.path.join(destino, nombre)))
    print("%d patch(es) in %s, %d B" % (len(vistos), os.path.relpath(destino),
                                         bytes_))


if __name__ == "__main__":
    main()

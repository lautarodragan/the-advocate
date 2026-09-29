#!/usr/bin/env python3
"""The game's cartridges, the ones its project file declares in
`[cartridges]`: `release`, the ROM that is played and that runs almost the
whole suite, and the others, with what does not fit in it.
No test builds anything: they run against what this leaves —see `tanda.rom`—.

    rm2k-snes-cartridges            builds whatever is needed
    rm2k-snes-cartridges release    only that one, with its MSU-1 tracks:
                                    `just build`
    rm2k-snes-cartridges --lista    which case goes in which cartridge

A new case is a file in `rom/pruebas/casos/` and nothing else: it goes into
`release` on its own and is run with `tanda.partida("<name>")`. It starts
with a `Teleport` to the map where it has to run: the starting one
—`start_map`— is map 4, the game's router, whose cutscene waits for nobody.

A new cartridge is one more table in `[cartridges]`, and nothing here.
"""

import argparse
import concurrent.futures
import glob
import hashlib
import json
import os
import subprocess
import sys

# `realpath` and not `abspath`: `just herramientas` installs this script on
# the PATH as a symlink, and what matters is where the real file is.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from audio import muestras_brr                          # noqa: E402
from common import ambiente                              # noqa: E402
from common import perillas                              # noqa: E402
from common import proyecto                              # noqa: E402
from ensamblado import ensamblar                        # noqa: E402
from port import tiles_bin                              # noqa: E402
from port import comprimir                              # noqa: E402

# `--proyecto` is read before anything else: this module reads the project
# file when imported, and `main`'s `parse_args` comes too late.
if __name__ == "__main__":
    proyecto.desde_la_linea_de_comandos()

RAIZ = proyecto.raiz()
CASOS = proyecto.casos()
FUENTE = proyecto.runtime()

# **What each cartridge carries belongs to the game, and is in its project
# file** —`proyecto.archivo_de_proyecto()`, with the reasons for each value as
# comments—: which maps go in, which are excluded, which cartridges exist and
# which cases each one carries. Until 2026-09-29 it was written here. What
# remains in this file is the mechanism that reads it and builds; the module
# names —`MENOR_A`, `CARTUCHOS`, `FUERA`…— are the old ones, because the
# suite reads them.
#
# **The maps are values in the file and not converter flags**, on purpose:
# the converter still receives the whole list in `--mapas`. This is the only
# one that calls it; `test_horneados` and `test_parches` need the list
# without running it; and since the stamp carries the flags and not
# `rom/data/`, a tree that changes which maps go in makes the cartridge stale
# only if the list travels expanded.
MENOR_A = perillas.valor("maps", "below", tipo=int)
EXCLUIDOS = frozenset(perillas.valor("maps", "excluded", tipo=list))
AGREGADOS = tuple(perillas.valor("maps", "added", tipo=list))


def el_mapa_de_debug():
    """The debug map's id: the only new map in
    `rom/parches/manual/nuevos/` —see `fork.nuevos`—. It comes from there and
    not from the project file so as not to write the number twice."""
    from rpgmaker import fork
    nuevos = sorted(fork.nuevos())
    if len(nuevos) != 1:
        sys.exit("the debug map is the only new map in %s, and there are %d: %s"
                 % (fork.carpeta_nuevos(), len(nuevos), nuevos))
    return nuevos[0]


# The debug map, which the game does not have, goes after the added ones.
CON_MAPA_DE_DEBUG = perillas.valor("debug", "debug_map", tipo=bool)
MAPA_DE_DEBUG = el_mapa_de_debug()
if CON_MAPA_DE_DEBUG:
    AGREGADOS += (MAPA_DE_DEBUG,)

# The enemies' HP in battle: passes `--hp-de-enemigos` to the converter in
# every cartridge.
CON_HP_DE_ENEMIGOS = perillas.valor("debug", "enemy_hp", tipo=bool)
_DE_TODOS = ["--hp-de-enemigos"] if CON_HP_DE_ENEMIGOS else []


def mapas_de_la_regla(menor_a=MENOR_A, excluidos=EXCLUIDOS,
                      agregados=AGREGADOS):
    """The game's maps in the order they go to `--mapas`: the ones from the
    rule in ascending order, and then the added ones. **The order is that of
    the ROM's table**, so changing it moves the table: see `orden_de_mapas`
    in snes_convert.py.

    The tree is the one in the `rom/data/` dump, which is what the converter
    reads: that is why the path falls inside `rom/data/` and not inside the
    game —see `lcf.volcado`—."""
    from rpgmaker import lcf
    arbol = lcf.TreeMap(os.path.join(proyecto.data(), "RPG_RT.lmt"))
    de_la_regla = [m for m in range(1, menor_a)
                   if arbol.map_types.get(m) == 1 and m not in excluidos]
    return tuple(de_la_regla + [m for m in agregados if m not in de_la_regla])


MAPAS_DEL_JUEGO = mapas_de_la_regla()

# And the ones that only exist for the suite. `parches.revisar` reads them
# from here so as not to require a versioned patch for them.
MAPAS_DE_PRUEBA = tuple(perillas.valor("maps", "test", tipo=list))

MAPAS = MAPAS_DEL_JUEGO + MAPAS_DE_PRUEBA

# The cartridge that is played: the one that carries the ROM with the game's
# name, its MSU-1 tracks, and all the cases. The file has to declare it.
RELEASE = "release"

# What its files are called: `<name>.sfc`, and next to it the `.msu` and the
# `<name>-N.pcm` tracks. The other cartridges' files are called `prueba`.
NOMBRE_DE_LA_ROM = perillas.valor("rom", "name", tipo=str)


def _cartucho(nombre):
    """(the converter flags, the cases or None if it is all of them) of a
    cartridge in the file. The flags come out in the usual order —the party,
    the starting map, the maps, the graphics, the rest—, because they go into
    the stamp as is."""
    def clave(k, tipo):
        return perillas.valor("cartridges", nombre, k, tipo=tipo)
    arranque = clave("start_map", int)
    grupo = clave("party", list)
    mapas = clave("maps", (str, list))
    if isinstance(mapas, str):
        if mapas != "game":
            sys.exit("%s: maps of %s is a list or \"game\", and it is %r"
                     % (proyecto.archivo_de_proyecto(), nombre, mapas))
        mapas = MAPAS
    casos = clave("cases", (str, list))
    if isinstance(casos, str):
        if casos != "all":
            sys.exit("%s: cases of %s is a list or \"all\", and it is %r"
                     % (proyecto.archivo_de_proyecto(), nombre, casos))
        casos = None
    flags = ((["--grupo"] + [str(a) for a in grupo] if grupo else [])
             + ["--map-id", str(arranque), "--mapas"]
             + [str(m) for m in mapas if m != arranque]
             + [f for charset, indice in clave("test_graphics", list)
                for f in ("--grafico-de-prueba", charset, indice)]
             + clave("flags", list) + _DE_TODOS)
    return flags, casos


CARTUCHOS = {nombre: _cartucho(nombre)
             for nombre in perillas.valor("cartridges", tipo=dict)}
if RELEASE not in CARTUCHOS or CARTUCHOS[RELEASE][1] is not None:
    sys.exit("%s: missing [cartridges.%s], with cases = \"all\""
             % (proyecto.archivo_de_proyecto(), RELEASE))

# The cases `release` does not carry, because there they would change the
# others' images.
FUERA = set(perillas.valor("cartridges", RELEASE, "excluded_cases",
                           tipo=list))

# Page 0 is the real game's, except with the debug map, whose entry is what
# goes there: see `[cases]` in the file.
LA_PARTIDA_DE_VERDAD = perillas.valor("cases", "real_game", tipo=str)
ENTRADA_AL_MAPA_DE_DEBUG = perillas.valor("cases", "debug_map_entry",
                                          tipo=str)


def primero(con_mapa_de_debug=CON_MAPA_DE_DEBUG):
    """The case on page 0: what "Begin the Story" runs."""
    return (ENTRADA_AL_MAPA_DE_DEBUG if con_mapa_de_debug
            else LA_PARTIDA_DE_VERDAD)


def fuera(con_mapa_de_debug=CON_MAPA_DE_DEBUG):
    """The cases `release` does not carry. Without the map, not its entry
    either: its `Teleport` leads to a map that is not there, and the converter
    balks."""
    return FUERA | (set() if con_mapa_de_debug
                    else {ENTRADA_AL_MAPA_DE_DEBUG})


PRIMERO = primero()


def huella():
    """What a cartridge depends on, besides its flags and its cases.

    Whatever changes the ROM and is not here leaves it silently stale: that
    is why the binaries and `rom/parches/manual/` go in, since they change it
    without touching any source.
    `rom/data/` does not, since `just datos` regenerates it. The content is
    looked at and not the date, which `git checkout` changes.
    """
    h = hashlib.sha256()
    for ruta in archivos_de_la_huella():
        with open(ruta, "rb") as archivo:
            h.update(archivo.read())
    # And each song's volume ceiling, which changes the streams: by its values
    # and not by the file, because `just techos` rewrites it with what it
    # measured —the peak, the mix fingerprint— after building, and that does
    # not change the ROM.
    from audio import snes_music
    h.update(repr(sorted(snes_music.leer_techos().items())).encode())
    return h.hexdigest()[:16]


def archivos_de_la_huella(fuente=FUENTE):
    """The files `huella` reads, in order. `fuente` is a parameter only so
    that a test can pass it a tree built by hand."""
    # All of `tools/runtime/`, and not only what `main.s` includes today: a file
    # that is added and included in the same change has to make the cartridge
    # stale.
    partes = (sorted(r for r in glob.glob(os.path.join(fuente, "**"),
                                          recursive=True) if os.path.isfile(r))
              + ensamblar.binarios()
              + [tiles_bin.binario(), muestras_brr.binario(),
                 comprimir.binario()])
    # Except the tools' tests, which build nothing: with them inside, editing
    # a test made every cartridge stale.
    pruebas = os.path.join(proyecto.herramientas(), "pruebas", "")
    partes += sorted(r for r in glob.glob(os.path.join(proyecto.herramientas(),
                                                       "*", "*.py"))
                     if not r.startswith(pruebas))
    partes += sorted(glob.glob(os.path.join(proyecto.parches_manual(), "*",
                                            "*")))
    # And the project file, whole: the converter and the music read it, and
    # not only what reaches the stamp's flags.
    partes.append(proyecto.archivo_de_proyecto())
    return partes


def todos_los_casos():
    return sorted(os.path.splitext(os.path.basename(r))[0]
                  for r in glob.glob(os.path.join(CASOS, "*.json")))


def casos_de(nombre, con_mapa_de_debug=CON_MAPA_DE_DEBUG):
    """The cartridge's cases, in the order of its pages. `con_mapa_de_debug`
    is a parameter only so that a test can look at the clean delivery without
    building it."""
    casos = CARTUCHOS[nombre][1]
    if casos is None:
        cero = primero(con_mapa_de_debug)
        return [cero] + [n for n in todos_los_casos()
                         if n not in fuera(con_mapa_de_debug) and n != cero]
    return list(casos)


def sin_titulo(nombre):
    """Whether the cartridge starts without a title screen, straight on the
    map."""
    return "--sin-titulo" in CARTUCHOS[nombre][0]


def donde_esta(caso):
    """The cartridges that carry the case: first the one that carries all of
    them, then the rest by name.

    **It does not come from the order of `CARTUCHOS`**, on purpose: a case
    that is in two —`parado-tapado`— runs in the first, and with the
    dictionary in another order it ran in the small one and moved its golden
    without anyone touching the case.
    """
    return sorted((n for n in CARTUCHOS if caso in casos_de(n)),
                  key=lambda n: (CARTUCHOS[n][1] is not None, n))


def _contenido(casos):
    contenido = []
    for caso in casos:
        with open(os.path.join(CASOS, caso + ".json"), encoding="utf-8") as a:
            contenido.append((caso, a.read()))
    return contenido


def sello(nombre, fuentes=None):
    """What the cartridge's stamp has to say for it to be up to date."""
    flags, _casos = CARTUCHOS[nombre]
    return "%s\n%r" % (fuentes or huella(),
                       (flags, _contenido(casos_de(nombre))))


def directorio(nombre):
    """What the tests write does not go here but to `rom/pruebas/snapshots/`."""
    if nombre == RELEASE:
        return os.path.join(proyecto.build(), RELEASE)
    return os.path.join(ambiente.cartuchos_de_prueba(),
                        nombre.replace("test-", "", 1))


def rom_de(nombre):
    # The MSU-1 looks for its tracks by the `.sfc`'s name.
    return os.path.join(directorio(nombre),
                        NOMBRE_DE_LA_ROM + ".sfc" if nombre == RELEASE
                        else "prueba.sfc")


def msu_de(nombre):
    """The cartridge's `.msu`: the converter writes it, with the battle
    backgrounds the MSU-1 serves to the ROM —see tools/port/msu_datos.py—,
    and it is also what turns on the MSU-1 for the tracks. Next to the `.sfc`
    and with its name, which is where the emulator and the FX Pak look for
    it."""
    return os.path.splitext(rom_de(nombre))[0] + ".msu"


def _archivo(nombre, que):
    return os.path.join(directorio(nombre), que)


def viejo(nombre, fuentes=None):
    """Why the cartridge is no good, or None if it is up to date."""
    if nombre not in CARTUCHOS:
        return "does not exist"
    try:
        with open(_archivo(nombre, "sello.txt")) as archivo:
            sellado = archivo.read()
    except OSError:
        return "is not built"
    if sellado != sello(nombre, fuentes):
        return "was built with other sources, other flags or other cases"
    # The converter writes it along with the ROM and it does not go into the
    # stamp: without it the cartridge would work, but the MSU-1 test would
    # have nothing to read.
    if not os.path.isfile(msu_de(nombre)):
        return "does not have its .msu"
    return None


def manifiesto(nombre):
    """(the cases, whether each one starts with a `Teleport`), per page."""
    casos = casos_de(nombre)
    return casos, [_salta(texto) for _n, texto in _contenido(casos)]


def _salta(texto):
    """Whether the case starts with a `Teleport`: the harness waits for the
    arrival, and looking at whether the ROM is fading is not enough, because
    there are maps that fade on their own when entered."""
    comandos = json.loads(texto).get("event_commands") or [{}]
    return comandos[0].get("code") == "Teleport"


def armar(nombre, fuentes):
    """Converts and assembles the cartridge, if it is not up to date. Says
    whether it built it."""
    if not viejo(nombre, fuentes):
        return False
    convertir(nombre, directorio(nombre), rom_de(nombre))
    with open(_archivo(nombre, "sello.txt"), "w") as archivo:
        archivo.write(sello(nombre, fuentes))
    return True


def convertir(nombre, destino, sfc, extra=()):
    """Converts and assembles the cartridge in `destino`, without a stamp and
    even if it is up to date. `extra` are extra flags for the converter:
    that is how `tools/audio/techos.py` builds a copy of `release` with
    another volume, without touching the real one."""
    flags, _casos = CARTUCHOS[nombre]
    os.makedirs(destino, exist_ok=True)
    log = os.path.join(destino, "conversor.log")
    # The cases go at the end: after a `--caso`, any cartridge flag would
    # belong to that case, and the converter rejects it.
    de_casos = []
    for k, caso in enumerate(casos_de(nombre)):
        de_casos += (["--caso"] if k else []) + [
            "--comandos-de-prueba",
            os.path.relpath(os.path.join(CASOS, caso + ".json"), RAIZ)]
    # With `--proyecto`, because it runs standing in the repo root —see
    # `ensamblar.RAIZ`— and from there it would not find the file by
    # searching.
    orden = ([sys.executable, os.path.join(proyecto.herramientas(), "port",
                                           "snes_convert.py"),
              "--proyecto", proyecto.directorio(),
              *ambiente.como_flags(*AL_CONVERSOR),
              "-o", os.path.join(destino, "mapdata.inc"),
              "--msu", os.path.splitext(sfc)[0] + ".msu"]
             + flags + list(extra) + de_casos)
    hecho = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True)
    with open(log, "w") as archivo:
        archivo.write(hecho.stdout + hecho.stderr)
    if hecho.returncode:
        sys.stderr.write(hecho.stdout[-3000:] + hecho.stderr)
        sys.exit("%s: the converter failed; everything is in %s" % (nombre, log))
    ensamblar.ensamblar(os.path.join(FUENTE, "main.s"),
                        destino, sfc, sfc + ".sym")


# What the converter needs from the machine, since it runs in another
# process and receives it by flags; and what this one adds: where the test
# cartridges go, and the replacements for the MSU-1 tracks.
AL_CONVERSOR = ("game_dir", "rtp_dir", "soundfont", "cache")
DEL_AMBIENTE = AL_CONVERSOR + ("test_cartridges", "reemplazos")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    proyecto.argumento(parser)
    ambiente.argumentos(parser, *DEL_AMBIENTE)
    parser.add_argument("--lista", action="store_true",
                        help="which case goes in which cartridge, without building anything")
    parser.add_argument("nombres", nargs="*", metavar="CARTRIDGE",
                        help="only these; without names, all of them. It is what "
                             "`just build release` uses")
    args = parser.parse_args()
    ambiente.desde_argumentos(args, *DEL_AMBIENTE)
    for nombre in args.nombres:
        if nombre not in CARTUCHOS:
            sys.exit("there is no cartridge %r: the ones there are %s"
                     % (nombre, ", ".join(CARTUCHOS)))
    if args.lista:
        for nombre in CARTUCHOS:
            casos = casos_de(nombre)
            print("%s (%d): %s" % (nombre, len(casos), " ".join(casos)))
        return
    fuentes = huella()
    nombres = args.nombres or list(CARTUCHOS)
    # The cartridges and the tracks are built at the same time, in threads:
    # each one writes in its own directory, and the heavy work runs in
    # subprocesses —the converter, `ca65`, fluidsynth—. What they share is the
    # disk cache, which writes aside and renames. What is printed stays in the
    # usual order.
    #
    # The tracks, **after `release`** and not alongside it: they are its
    # songs', which the converter leaves in its `musica.json`. Meanwhile the
    # other cartridges get built.
    with concurrent.futures.ThreadPoolExecutor(len(nombres) + 1) as hilos:
        armados = {nombre: hilos.submit(armar, nombre, fuentes)
                   for nombre in nombres}
        hechas = (hilos.submit(pistas, armados[RELEASE])
                  if RELEASE in nombres else None)
        for nombre in nombres:
            print("%s: %s" % (nombre, "built" if armados[nombre].result()
                              else "up to date"))
            if nombre == RELEASE:
                print(hechas.result())


def pistas(armado=None):
    """The MSU-1 tracks next to the ROM that is played: `release` always
    carries them, so there is no other way to have the ROM with tracks.

    They go outside the stamp and are checked even if the ROM is up to date:
    which ones they are is said by the cartridge —its `musica.json`—, but how
    each one sounds depends on the MIDI, the soundfont and the synthesizer,
    and `msu.armar` already knows which ones are there —see
    `clave_de_la_pista`—. Having them next to it does not change the suite:
    the harness hides the tracks from the core, see `retro.Consola`.
    Returns the line that reports it, which `main` prints in its place.
    """
    if armado is not None:
        armado.result()         # the `musica.json` that says which ones
    from audio import msu       # fluidsynth and ffmpeg, only for `release`
    hechas, estaban = msu.armar(rom_de(RELEASE), charlar=False)
    return ("%s: MSU-1 tracks, %d made and %d that were already there"
            % (RELEASE, hechas, estaban))


if __name__ == "__main__":
    main()

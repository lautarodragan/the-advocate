"""Where everything is: the only place that knows.

One function per place, and the environment's default values, which eleven
modules used to compute on their own and as many again built by hand. See
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`.

**The tools do not know where the game lives: they find it.** They look for
`rm2k-snes.toml` from the current directory upwards, the way cargo looks for
its `Cargo.toml`, or receive it through `--proyecto`. What belongs to the
repo —the tools, the runtime, the root— comes from where this file is.

They are functions and not constants so that one place can depend on another
regardless of the order they are written in, and so that nothing is computed
at import: the project is looked up the first time someone asks for it, so
importing the tools does not require a game.

It imports nothing from `tools/`: it is in the lowest layer, and all of them
use it.
"""

import os

# `realpath` and not `abspath`: the scripts that get executed are installed
# on the PATH as symlinks, and what matters is where the real file is.
_HERRAMIENTAS = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


# What belongs to the repo.

def herramientas():
    """`tools/`: the Python packages, which is where this file lives."""
    return _HERRAMIENTAS


def raiz():
    """The repo root: where `ca65` and `ld65` run, and what the relative
    paths that end up inside a `.dbg` or a `.inc` are written against. It is
    for what belongs to the repo, like `.git`: the game is not looked up from
    here."""
    return os.path.dirname(_HERRAMIENTAS)


def runtime():
    """The runtime in assembly: it travels with the tools, and is assembled
    together with each game's `.inc` files."""
    return os.path.join(herramientas(), "runtime")


# The project: the game being built. The tools do not know where it lives;
# they find it.

ARCHIVO = "rm2k-snes.toml"


class NoHayProyecto(SystemExit):
    """The project file was not found. It is a `SystemExit` and not just any
    error because what fixes it is how the tool was run, not its code: an
    executable stops with the message and no traceback."""


_directorio = None


def buscar(desde):
    """The nearest directory, `desde` or one above it, that has a
    `rm2k-snes.toml`; or None. It is how cargo finds its `Cargo.toml`."""
    actual = os.path.abspath(desde)
    while True:
        if os.path.isfile(os.path.join(actual, ARCHIVO)):
            return actual
        padre = os.path.dirname(actual)
        if padre == actual:
            return None
        actual = padre


def fijar(directorio):
    """Uses the project in `directorio`, without searching: it is
    `--proyecto`, and what a game's tests do, since they know where they
    are."""
    global _directorio
    directorio = os.path.abspath(directorio)
    if not os.path.isfile(os.path.join(directorio, ARCHIVO)):
        raise NoHayProyecto("%s has no %s: --proyecto is the directory "
                            "where that file is" % (directorio, ARCHIVO))
    _directorio = directorio


def directorio():
    """The project root: where `rm2k-snes.toml` is. If nobody set it, it is
    looked up from the current directory upwards, the first time it is asked
    for and not at import: importing the tools does not require a game."""
    global _directorio
    if _directorio is None:
        desde = os.getcwd()
        encontrado = buscar(desde)
        if encontrado is None:
            raise NoHayProyecto(
                "found no %s in %s nor in any folder above it: run this "
                "from inside the project, or pass it "
                "--proyecto <directory>" % (ARCHIVO, desde))
        _directorio = encontrado
    return _directorio


def argumento(parser):
    """Adds `--proyecto` to an executable's parser, so that it shows up in
    its `--help` and is not rejected. What uses it is
    `desde_la_linea_de_comandos`."""
    parser.add_argument(
        "--proyecto", metavar="DIRECTORY",
        help="the directory where %s is. Without this, it is looked up from "
             "the current directory upwards" % ARCHIVO)


def desde_la_linea_de_comandos(argv=None):
    """Takes `--proyecto` from the command line, if it is there.

    It goes at the start of each executable, before importing anything that
    reads the project file —`cartuchos` reads it when imported—, so it cannot
    wait for its `main`'s `parse_args`: it reads only this flag and leaves
    the rest to it."""
    import argparse
    previo = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    previo.add_argument("--proyecto")
    leidos, _resto = previo.parse_known_args(argv)
    if leidos.proyecto:
        fijar(leidos.proyecto)


def archivo_de_proyecto():
    """`rm2k-snes.toml`: the game's settings. `common/perillas.py` reads it."""
    return os.path.join(directorio(), ARCHIVO)


def _ruta(clave):
    """A path from `[paths]`: the file declares it, relative to itself. How
    the game is laid out inside belongs to the game, not to the tools."""
    from common import perillas      # inside: `perillas` imports this one
    return os.path.normpath(os.path.join(
        directorio(), perillas.valor("paths", clave, tipo=str)))


def build():
    """`[paths] build`: everything that gets built, and nothing versioned."""
    return _ruta("build")


def data():
    """`[paths] data`: the game dumped to JSON."""
    return _ruta("data")


def parches():
    """`[paths] patches`: what was decided about the game, `manual/` and
    `auto/`. What goes inside has the shape the tools give it."""
    return _ruta("patches")


def parches_manual():
    """What was redesigned by hand: the forks, the new maps, the ChipSets."""
    return os.path.join(parches(), "manual")


def parches_auto():
    """What the converter decided and is versioned."""
    return os.path.join(parches(), "auto")


def casos():
    """`[paths] cases`: the suite's cases, one JSON per case. `cartuchos.py`
    reads them and puts them into the test pages."""
    return _ruta("cases")

"""Where everything is: the only place that knows.

One function per place, and the environment's default values, which eleven
modules used to compute on their own and as many again built by hand. See
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`.

**The tools do not know where the game lives: they find it.** They look for
`rm2k-snes.toml` from the current directory upwards, the way cargo looks for
its `Cargo.toml`, or receive it through `--project`. What belongs to the
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
_TOOLS = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


# What belongs to the repo.

def tools():
    """`tools/`: the Python packages, which is where this file lives."""
    return _TOOLS


def root():
    """The repo root: where `ca65` and `ld65` run, and what the relative
    paths that end up inside a `.dbg` or a `.inc` are written against. It is
    for what belongs to the repo, like `.git`: the game is not looked up from
    here."""
    return os.path.dirname(_TOOLS)


def runtime():
    """The runtime in assembly: it travels with the tools, and is assembled
    together with each game's `.inc` files."""
    return os.path.join(tools(), "runtime")


# The project: the game being built. The tools do not know where it lives;
# they find it.

FILENAME = "rm2k-snes.toml"


class NoProject(SystemExit):
    """The project file was not found. It is a `SystemExit` and not just any
    error because what fixes it is how the tool was run, not its code: an
    executable stops with the message and no traceback."""


_directory = None


def find(start):
    """The nearest directory, `start` or one above it, that has a
    `rm2k-snes.toml`; or None. It is how cargo finds its `Cargo.toml`."""
    current = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(current, FILENAME)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def use(directory):
    """Uses the project in `directory`, without searching: it is
    `--project`, and what a game's tests do, since they know where they
    are."""
    global _directory
    directory = os.path.abspath(directory)
    if not os.path.isfile(os.path.join(directory, FILENAME)):
        raise NoProject("%s has no %s: --project is the directory "
                        "where that file is" % (directory, FILENAME))
    _directory = directory


def directory():
    """The project root: where `rm2k-snes.toml` is. If nobody set it, it is
    looked up from the current directory upwards, the first time it is asked
    for and not at import: importing the tools does not require a game."""
    global _directory
    if _directory is None:
        start = os.getcwd()
        found = find(start)
        if found is None:
            raise NoProject(
                "found no %s in %s nor in any folder above it: run this "
                "from inside the project, or pass it "
                "--project <directory>" % (FILENAME, start))
        _directory = found
    return _directory


def add_argument(parser):
    """Adds `--project` to an executable's parser, so that it shows up in
    its `--help` and is not rejected. What uses it is
    `from_command_line`."""
    parser.add_argument(
        "--project", metavar="DIRECTORY",
        help="the directory where %s is. Without this, it is looked up from "
             "the current directory upwards" % FILENAME)


def from_command_line(argv=None):
    """Takes `--project` from the command line, if it is there.

    It goes at the start of each executable, before importing anything that
    reads the project file —`cartridges` reads it when imported—, so it cannot
    wait for its `main`'s `parse_args`: it reads only this flag and leaves
    the rest to it."""
    import argparse
    early = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    early.add_argument("--project")
    known, _rest = early.parse_known_args(argv)
    if known.project:
        use(known.project)


def project_file():
    """`rm2k-snes.toml`: the game's settings. `common/settings.py` reads it."""
    return os.path.join(directory(), FILENAME)


def _path(key):
    """A path from `[paths]`: the file declares it, relative to itself. How
    the game is laid out inside belongs to the game, not to the tools."""
    from common import settings      # inside: `settings` imports this one
    return os.path.normpath(os.path.join(
        directory(), settings.value("paths", key, kind=str)))


def build():
    """`[paths] build`: everything that gets built, and nothing versioned."""
    return _path("build")


def data():
    """`[paths] data`: the game dumped to JSON."""
    return _path("data")


def patches():
    """`[paths] patches`: what was decided about the game, `manual/` and
    `auto/`. What goes inside has the shape the tools give it."""
    return _path("patches")


def manual_patches():
    """What was redesigned by hand: the forks, the new maps, the ChipSets."""
    return os.path.join(patches(), "manual")


def auto_patches():
    """What the converter decided and is versioned."""
    return os.path.join(patches(), "auto")


def cases():
    """`[paths] cases`: the suite's cases, one JSON per case. `cartridges.py`
    reads them and puts them into the test pages."""
    return _path("cases")

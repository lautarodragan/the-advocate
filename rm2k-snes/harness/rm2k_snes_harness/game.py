"""A game, as its tests see it: where it is, and each cartridge as its last
build left it.

A game says it once, before its first test, with `use(Game(...))`: its root
and where its goldens and its red captures go. From then on `cartridge()`
is its `release`, built, read through the symbols and the map table it
leaves.

**What the build left is read, not asked**: every `advocate build` writes
`build/advocate.json` beside the project's `advocate.toml`, with its
cartridges, whether each one was up to date when it ended, and the
project as the tools resolve it. Until 2026-11-25 this ran
`rm2k-snes-cartridges --list --json` and `rm2k-snes-project`, and had to be
given the machine's flags the game was built with for the first to answer
the same.
"""

import functools
import json
import os
import re
import tempfile

# The cartridge the tests run unless they ask for another: the one the tools
# demand of every project.
RELEASE = "release"


class Game:
    """A game's project, for its tests.

    `root` is the directory with its `advocate.toml`; `goldens` the folder
    of its frozen captures, and `snapshots` the one where the red ones are
    left to look at, which is not versioned."""

    def __init__(self, root, goldens, snapshots):
        self.root = root
        self.goldens = goldens
        self.snapshots = snapshots

    @functools.cached_property
    def built(self):
        """What the last `advocate build` left in `build/advocate.json`."""
        path = os.path.join(self.root, "build", "advocate.json")
        assert os.path.exists(path), (
            "%s is not there: build the game first, with `just cartridges` "
            "in %s" % (path, self.root))
        with open(path) as file:
            return json.load(file)

    @property
    def listing(self):
        """Its cartridges, and where `ca65` ran and the runtime is."""
        return self.built["listing"]

    @property
    def project(self):
        """What the tools resolve of its project —`project`, `suite`,
        `settings`—."""
        return self.built

    @functools.lru_cache(maxsize=None)
    def cartridge(self, name=RELEASE):
        """The built `release`, or the cartridge `name` of `advocate.toml`.
        **It does not build**: a stale cartridge is a red, because a test
        that ran against an old ROM says nothing. The game's `just` recipe
        that runs its tests builds them before."""
        data = next((c for c in self.listing["cartridges"]
                     if c["name"] == name), None)
        assert data, "the project does not declare a cartridge %r" % name
        assert not data["stale"], (
            "the cartridge is stale (%s): build it with `just cartridges` in "
            "%s" % (data["stale"], self.root))
        return Cartridge(data, self.project["project"]["data"])


class Cartridge:
    """A cartridge, built: the ROM, its symbols and its maps. `dump` is the
    game's dump it was converted from, for what is asked of the stages."""

    def __init__(self, data, dump=None):
        self.dump = dump
        self.rom = data["rom"]
        # Where the converter left what it built: `degradations.json`, the
        # `.inc`s.
        self.directory = data["directory"]
        # The cases it carries, in the order of their test pages: page k
        # runs when the case variable is at least k, and 0 asks for nothing.
        self.cases = data["cases"]
        with open(self.rom + ".sym") as file:
            self.symbols = {name: int(value) for name, value
                            in (line.split() for line in file if line.strip())}
        # The order of the map table, which is what `map_current` indexes:
        # from the comment the converter leaves on each entry.
        with open(os.path.join(self.directory, "mapdata.inc")) as file:
            inc = file.read()
        index = dict((int(i), int(m)) for i, m in re.findall(
            r"^; --- (\d+): map (\d+) ", inc, re.MULTILINE))
        self.maps = [index[i] for i in range(len(index))]

    @functools.cached_property
    def variable_slots(self):
        """{RM2k variable: its slot in `FAR_VARIABLES`}: the ROM keeps only
        the variables the game names, packed, so the number is not the
        place. Asked of the events compiler with the request the converter
        left beside the ROM, so it is the answer the ROM was built with."""
        assert self.dump, "this cartridge was not given its game's dump"
        with tempfile.TemporaryDirectory() as out:
            subprocess.run(
                ["rm2k-snes-events", "scan", "--data", self.dump,
                 "--request", os.path.join(self.directory,
                                           "events-request.json"),
                 "--out", out], check=True, capture_output=True)
            with open(os.path.join(out, "events.json")) as file:
                return dict(json.load(file)["variables"])


_current = None


def use(game):
    """The game the tests of this process are about."""
    global _current
    _current = game


def current():
    assert _current is not None, (
        "no game: the tests' conftest hands one to `rm2k_snes_harness.use` "
        "before the first test")
    return _current


def listing():
    """The builder's answer about the current game's project."""
    return current().listing


def cartridge(name=RELEASE):
    """The current game's cartridge `name`, built: see `Game.cartridge`."""
    return current().cartridge(name)

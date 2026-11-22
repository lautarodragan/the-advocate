"""A game, as its tests see it: where it is, how its cartridges are built,
and each cartridge as the builder answers for it.

A game says it once, before its first test, with `use(Game(...))`: its root,
the flags `rm2k-snes-cartridges` builds it with —the builder's answer depends
on them, so they are the ones its `just cartridges` passes—, and where its
goldens and its red captures go. From then on `cartridge()` is its
`release`, built, read through the symbols and the map table it leaves.
"""

import functools
import json
import os
import re
import subprocess

# The cartridge the tests run unless they ask for another: the one the tools
# demand of every project.
RELEASE = "release"


class Game:
    """A game's project, for its tests.

    `root` is the directory with its `advocate.toml`; `flags` what
    `rm2k-snes-cartridges` is given besides `--list --json`, or a function
    that returns it —so a variable the machine has to set is asked for only
    when a test needs a cartridge, and not on import—; `goldens` the folder
    of its frozen captures, and `snapshots` the one where the red ones are
    left to look at, which is not versioned."""

    def __init__(self, root, flags, goldens, snapshots):
        self.root = root
        self._flags = flags
        self.goldens = goldens
        self.snapshots = snapshots

    def flags(self):
        return list(self._flags() if callable(self._flags) else self._flags)

    @functools.cached_property
    def listing(self):
        """What the builder answers about the project: its cartridges, and
        where `ca65` ran and the runtime is."""
        done = subprocess.run(
            ["rm2k-snes-cartridges", *self.flags(), "--list", "--json"],
            cwd=self.root, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

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
        return Cartridge(data)


class Cartridge:
    """A cartridge, built: the ROM, its symbols and its maps."""

    def __init__(self, data):
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

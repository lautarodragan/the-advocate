"""The test game's cartridge, running, for its tests: the smallest harness
that boots it, plays it and compares what it draws.

It is small on purpose, and it is a stopgap. A Blurred Line's harness, in
the ports' repo, is the one that knows how to play a game —cases, routes,
battles, menus—, and phase 2 of the test game's research, in the book,
brings its generic part here as one package; until then, what the test game
asks for is written here, and the ports' `tests/games.py` is where it comes
from: the tick clock, the control, the goldens at 15 bits. The libretro
driver, `emulator/retro.py`, is a copy of that game's.

Nothing here is written by hand about the cartridge: which symbols there
are in RAM is said by its `.sym`, which map each index is by its
`mapdata.inc`, and where the cartridge is and whether it is up to date by
`rm2k-snes-cartridges`.
"""

import functools
import json
import os
import re
import subprocess

from PIL import Image

from emulator import retro

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
GOLDENS = os.path.join(TESTS, "golden")
# The captures that came out red, to look at them: not versioned.
SNAPSHOTS = os.path.join(TESTS, "snapshots")

# The two cores, as in the ports: snes9x is the one the goldens are taken
# with, and bsnes the one that powers on with WRAM full of garbage, like the
# console, so a difference between the two is uninitialised memory. bsnes
# needs the patch that exposes its WRAM (`tests/harness/emulator/` in A
# Blurred Line's repo), and without it the clock cannot read the ROM's tick.
# Where they are belongs to the machine: these are the libretro packages'
# paths, and a variable moves them.
SNES9X = os.environ.get("SNES9X_CORE", "/usr/lib/libretro/snes9x_libretro.so")
BSNES = os.environ.get("BSNES_CORE", "/usr/lib/libretro/bsnes_libretro.so")

# The cartridge the tests run: the one the tools demand of every project.
RELEASE = "release"

# How many hardware frames a tick can last before giving the ROM up as hung.
# Not a tuned number: a hung ROM never advances, so the margin costs nothing
# while it works. The ports' `FRAMES_PER_TICK`.
FRAMES_PER_TICK = 3000

# `msg_state` back at idle: with `msg_open` set, the message is whole on
# screen and waits for a button. It is 1 while composing and 2 only between
# the last letter and the vblank that shows it —`vblank.s` clears it—, so
# waiting for 2 can miss it: see `runtime/low_ram.s`.
MESSAGE_SHOWN = 0


def _builder(*args):
    """`rm2k-snes-cartridges` with the flags of `just cartridges`, which is
    what built it: the builder's answer depends on them."""
    soundfont = os.environ.get("SOUNDFONT")
    assert soundfont, ("SOUNDFONT is not set: run the tests with `just test` in "
                       "test-game/, which builds the cartridge first")
    return subprocess.run(
        ["rm2k-snes-cartridges", "--game-dir", "build/game",
         "--rtp-dir", "build/no-rtp", "--soundfont", soundfont,
         "--without-tracks", *args],
        cwd=ROOT, capture_output=True, text=True)


class Cartridge:
    """The `release` cartridge, built: the ROM, its symbols and its maps."""

    def __init__(self, data):
        self.rom = data["rom"]
        with open(self.rom + ".sym") as file:
            self.symbols = {name: int(value) for name, value
                            in (line.split() for line in file if line.strip())}
        # The order of the map table, which is what `map_current` indexes:
        # from the comment the converter leaves on each entry.
        with open(os.path.join(data["directory"], "mapdata.inc")) as file:
            inc = file.read()
        index = dict((int(i), int(m)) for i, m in re.findall(
            r"^; --- (\d+): map (\d+) ", inc, re.MULTILINE))
        self.maps = [index[i] for i in range(len(index))]


@functools.lru_cache(maxsize=None)
def cartridge():
    """The built `release`. **It does not build**: a stale cartridge is a
    red, because a test that ran against an old ROM says nothing. `just
    test` builds it before."""
    listing = _builder("--list", "--json")
    assert listing.returncode == 0, listing.stderr
    data = next((c for c in json.loads(listing.stdout)["cartridges"]
                 if c["name"] == RELEASE), None)
    assert data, "the project does not declare a cartridge %r" % RELEASE
    assert not data["stale"], ("the cartridge is stale (%s): build it with "
                               "`just cartridges` in test-game/" % data["stale"])
    return Cartridge(data)


class Session:
    """The cartridge running on a core, with the boot already past."""

    def __init__(self, core):
        self.cartridge = cartridge()
        self.core = core
        self.console = retro.Console(self.cartridge.rom, core)
        self.console.run(self.symbol("BOOT_FRAMES"))
        # How many ticks the test took.
        self.tick = 0

    def symbol(self, name):
        try:
            return self.cartridge.symbols[name]
        except KeyError:
            raise AssertionError("the cartridge has no symbol %r: if it was "
                                 "renamed in runtime/, rename it here"
                                 % name) from None

    def _ram(self, name):
        # Far RAM ones come with their bank in front: the WRAM is 128 KB.
        return self.symbol(name) & 0x1FFFF

    def byte(self, name):
        return self.console.ram(self._ram(name), 1)[0]

    def word(self, name):
        low, high = self.console.ram(self._ram(name), 2)
        return low | (high << 8)

    def map_(self):
        """Which RM2k map the game is on."""
        return self.cartridge.maps[self.word("map_current")]

    def cell(self):
        """The hero's cell, once they stand on one."""
        return self.word("hero_x") // 16, self.word("hero_y") // 16

    def advance(self, *buttons):
        """One tick —one round of the main loop— with `buttons` held.

        The ports' clock, and for the same reason: the ROM reads the pad once
        per round, and a round can last more than a frame, so counting ticks
        and not frames both cores see the same presses on the same rounds."""
        before = self.word("ticks")
        self.console.hold(*buttons)
        for _ in range(FRAMES_PER_TICK):
            self.console.run(1)
            if self.word("ticks") != before:
                self.tick += 1
                return
        raise AssertionError("no tick in %d frames, on map %d: the ROM hung"
                             % (FRAMES_PER_TICK, self.map_()))

    def has_control(self):
        """No page running, nor fade, nor message, nor menu: what the player
        sees as "I can walk"."""
        return not (self.byte("ev_active") or self.byte("fade")
                    or self.byte("msg_open") or self.byte("menu_open"))

    def until(self, what, condition, limit):
        """Ticks with nothing pressed until `condition()` holds."""
        for _ in range(limit):
            if condition():
                return
            self.advance()
        raise AssertionError("%d ticks and still not %s; on map %d, cell %s"
                             % (limit, what, self.map_(), self.cell()))

    def walk_until_blocked(self, direction, limit=200):
        """Holds `direction` until the hero stops moving: in front of what
        blocks them, facing it."""
        still, before = 0, self.cell()
        for _ in range(limit):
            self.advance(direction)
            here = self.cell()
            still = still + 1 if here == before else 0
            before = here
            # A one-cell step takes a few ticks: a dozen without moving is
            # being stopped.
            if still >= 12:
                self.advance()
                return here
        raise AssertionError("%d ticks walking %s and the hero never stopped"
                             % (limit, direction))

    def press(self, button):
        """A one-tick press and a release: the edge the ROM looks for."""
        self.advance(button)
        self.advance()

    def image(self):
        return self.console.image()


def core_name(core):
    return os.path.basename(core).split("_")[0]


def _save(image, *parts):
    os.makedirs(os.path.join(SNAPSHOTS, *parts[:-1]), exist_ok=True)
    path = os.path.join(SNAPSHOTS, *parts)
    image.save(path)
    return path


def golden(name, image, core):
    """The capture against its frozen one, identical **at 15 bits**, the
    console's depth: the golden is snes9x's, and bsnes's is compared against
    it too. A capture with no golden is left in `snapshots/golden/` and is a
    red: it is looked at and, if it is right, copied to `golden/` in its own
    commit. A golden is never overwritten from here."""
    path = os.path.join(GOLDENS, "%s.png" % name)
    if not os.path.exists(path):
        # snes9x's under the golden's name, since it is the one taken; the
        # other core's beside it, so it does not overwrite it.
        suffix = "" if core_name(core) == "snes9x" else "-" + core_name(core)
        where = _save(image, "golden", "%s%s.png" % (name, suffix))
        raise AssertionError("%r has no golden: the capture was left in %s"
                             % (name, where))
    expected = retro.fifteen_bits(Image.open(path))
    actual = retro.fifteen_bits(image)
    if expected == actual:
        return
    distinct = sum(1 for a, b in zip(expected, actual) if a != b)
    where = _save(image, "golden", "%s-%s.png" % (name, core_name(core)))
    raise AssertionError(
        "%r on %s differs from its golden in %d of %d pixels, at 15 bits. The "
        "capture was left in %s and the golden is %s."
        % (name, core_name(core), distinct, len(expected), where, path))

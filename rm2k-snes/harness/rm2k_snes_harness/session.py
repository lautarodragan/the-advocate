"""A cartridge running on a core, past its boot: the tick clock, and what
any game's tests ask it —which map, which cell, which switch, whether the
player has control—, read through the symbols the cartridge leaves.

It is what a game with no title screen in the way needs: one with a title,
or that asks its own questions, puts its own on top. A Blurred Line's
`Session`, in the ports, is where this came from —the tick clock, the
control, the reset—, and it still keeps its own, with its title screen,
its menus and its battles.
"""

from . import retro
from .game import RELEASE, cartridge

# How many hardware frames a tick can last before giving the ROM up as hung.
# Not a tuned number: a hung ROM never advances, so the margin costs nothing
# while it works. A Blurred Line's `FRAMES_PER_TICK`.
FRAMES_PER_TICK = 3000

# `msg_state` back at idle: with `msg_open` set, the message is whole on
# screen and waits for a button. It is 1 while composing and 2 only between
# the last letter and the vblank that shows it —`vblank.s` clears it—, so
# waiting for 2 can miss it: see `runtime/low_ram.s`.
MESSAGE_SHOWN = 0

# The WRAM's size, which `Session.reset` powers on again.
WRAM = 0x20000

# The frames a screen with no ticks —the slot screen— is given to upload and
# draw itself before a press, and after one: A Blurred Line's
# `TITLE_HEADROOM`.
SCREEN_HEADROOM = 30


class Session:
    """The cartridge running on a core, with the boot already past and, with
    `case`, that test page chosen: one of `cases/`, by its name. Without one
    it is page 0, `[cases] real_game`: the game as it boots. `on` is
    another cartridge than `release`, and `options` the core's, as
    `retro.Console` takes them."""

    def __init__(self, core, case=None, on=RELEASE, options=None):
        self.cartridge = cartridge(on)
        self.core = core
        self.console = retro.Console(self.cartridge.rom, core, options)
        self.console.run(self.symbol("BOOT_FRAMES"))
        if case is not None:
            self.choose_case(case)
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

    def choose_case(self, case):
        """Chooses test page `case`, by its name in `cases/`: at boot, and
        after a `reset`, which loads a saved game with the case page that
        already ran. Each test page turns `TEST_SWITCH` on first, and the
        page that asks for it, last, has no code: a saved game brings it on,
        so it is turned off here."""
        assert case in self.cartridge.cases, (
            "the cartridge does not carry the case %r: is it in cases/?"
            % case)
        # A cartridge with a single case has no variable to choose it with:
        # that one is the page that asks for nothing, and runs on its own
        # —see `--case` in `rm2k-snes-convert`—.
        if self.cartridge.cases == [case]:
            return
        # The cartridge says which: 1023, or the first above it the game
        # does not name —see `test_switch` in rm2k-snes-events—.
        switch = self.symbol("TEST_SWITCH")
        address = self._ram("switches") + switch // 8
        octet = self.console.ram(address, 1)[0]
        self.console.write_ram(address, [octet & ~(1 << (switch % 8)) & 0xFF])
        self._choose(self.cartridge.cases.index(case))

    def _choose(self, page):
        """Writes the case variable, by its slot in far RAM, and the refresh
        that makes the ROM look at the pages again. Before the first game
        frame: the test pages are automatic and chosen on it. A Blurred
        Line's `_choose_the_case`."""
        address = self._ram("FAR_VARIABLES") + 2 * self.symbol("CASE_SLOT")
        self.console.write_ram(address, [page & 0xFF, page >> 8])
        self.console.write_ram(self._ram("refresh"), [1])

    def switch(self, number):
        """Whether the switch is on, read from the table the ROM reads:
        `switches`, in far RAM, `SWITCH_BYTES` long."""
        assert number // 8 < self.symbol("SWITCH_BYTES"), (
            "switch %d is past the table, which holds %d bytes"
            % (number, self.symbol("SWITCH_BYTES")))
        octet = self.console.ram(self._ram("switches") + number // 8, 1)[0]
        return bool(octet & (1 << (number % 8)))

    def map_(self):
        """Which RM2k map the game is on."""
        return self.cartridge.maps[self.word("map_current")]

    def cell(self):
        """The hero's cell, once they stand on one."""
        return self.word("hero_x") // 16, self.word("hero_y") // 16

    def advance(self, *buttons):
        """One tick —one round of the main loop— with `buttons` held.

        A Blurred Line's clock, and for the same reason: the ROM reads the pad
        once per round, and a round can last more than a frame, so counting ticks
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

    def reset(self):
        """The console's reset button: the cartridge's SRAM survives and the
        WRAM does not. The WRAM is written with the $55 snes9x powers on
        with first, since the core's reset leaves it as it was —like the
        console's— and a value the load did not bring back would still be
        there. A cartridge without a title loads the saved game on boot, so
        this is how a test loads one. A Blurred Line's `_reset`."""
        self.console.write_ram(0, bytes([0x55]) * WRAM)
        self.console.reset()
        self.console.run(self.symbol("BOOT_FRAMES"))
        self.tick = 0

    def screen_up(self, limit=300):
        """Hardware frames until a screen with no ticks inside —the slot
        screen, the menu— is up, and a few more for it to be drawn whole."""
        for _ in range(limit):
            if self.byte("menu_open"):
                self.console.run(SCREEN_HEADROOM)
                return
            self.console.run(1)
        raise AssertionError("no screen opened in %d frames" % limit)

    def choose(self, button="a"):
        """A press on a screen with no ticks —or one that opens one—: two
        frames held, and released."""
        self.console.hold(button)
        self.console.run(2)
        self.console.hold()
        self.console.run(SCREEN_HEADROOM)

    def press(self, button):
        """A one-tick press and a release: the edge the ROM looks for."""
        self.advance(button)
        self.advance()

    def image(self):
        return self.console.image()

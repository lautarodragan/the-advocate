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

    def __init__(self, core, case=None, on=RELEASE, options=None,
                 switches=()):
        self.cartridge = cartridge(on)
        self.core = core
        self.console = retro.Console(self.cartridge.rom, core, options)
        self.console.run(self.symbol("BOOT_FRAMES"))
        if case is not None:
            self.choose_case(case)
        # Before the first game frame, like the case: a switch that decides
        # which page of a map runs arrives in time for it.
        if switches:
            self.turn_on(*switches)
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

    def put_byte(self, name, value):
        """Writes a byte of the ROM's RAM, by symbol: a state that would take
        long to reach by playing —a spent budget, a speed a route left—, and
        then the ROM is asked what it does with it."""
        self.console.write_ram(self._ram(name), [value & 0xFF])

    def put_word(self, name, value):
        self.console.write_ram(self._ram(name), [value & 0xFF,
                                                 (value >> 8) & 0xFF])

    def variable(self, number):
        """RM2k variable `number`, signed, read from far RAM. The ROM keeps
        only the variables the game names, packed, so its slot is asked of
        the event compiler: see `Cartridge.variable_slots`."""
        slots = self.cartridge.variable_slots
        assert number in slots, (
            "the cartridge does not keep variable %d: no page names it"
            % number)
        low, high = self.console.ram(
            self._ram("FAR_VARIABLES") + 2 * slots[number], 2)
        value = low | (high << 8)
        return value - 0x10000 if value & 0x8000 else value

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

    def turn_on(self, *numbers):
        """Turns switches on by writing the table, as if the game had: the
        refresh is what `OP_SWITCH` does after touching it, so the ROM looks
        again at which page is active, and `compar_owed` tells the pure
        parallel common events a switch changed. A Blurred Line's
        `turn_on`."""
        base = self._ram("switches")
        for number in numbers:
            octet = self.console.ram(base + number // 8, 1)[0]
            self.console.write_ram(base + number // 8,
                                   [octet | (1 << (number % 8))])
        self.console.write_ram(self._ram("refresh"), [1])
        self.console.write_ram(self._ram("compar_owed"), [1])

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
        """The hero's cell, once they stand on one. Midway through a step it
        is the pixels' one, that is, the one they left until they arrive."""
        return self.word("hero_x") // 16, self.word("hero_y") // 16

    def event(self, index):
        """The cell where the ROM has event `index` of its table now: from
        zero, in the order of the map's ids."""
        base = self._ram("ev_pos_buf") + index * self.symbol("EV_STRIDE")
        b = self.console.ram(base, 4)
        return (b[0] | (b[1] << 8), b[2] | (b[3] << 8))

    def party(self):
        """The party's actors, by their RM2k number, in order."""
        return list(self.console.ram(self._ram("party"), self.byte("party_n")))

    def running_a_page(self):
        return bool(self.byte("ev_active"))

    def box_up(self):
        """The message window up with its box typed whole: what waits for
        the player. `msg_open` is on while the box is typed, so it alone is
        not "the box is there"."""
        return bool(self.byte("msg_open")) and not self.byte("MSG_TYPE")

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

    def run(self, ticks, holding=()):
        """`ticks` ticks with `holding` held on every one of them, and
        nothing else."""
        for _ in range(ticks):
            self.advance(*holding)

    def until(self, what, condition, limit):
        """Ticks with nothing pressed until `condition()` holds."""
        for _ in range(limit):
            if condition():
                return
            self.advance()
        raise AssertionError("%d ticks and still not %s; on map %d, cell %s"
                             % (limit, what, self.map_(), self.cell()))

    def until_control(self, limit=600):
        """Ticks until the player has control again: at least one, since
        before the first one a case's page has not started yet."""
        self.advance()
        self.until("control", self.has_control, limit)

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

    def go_to_map(self, map_id, x, y, ticks=90):
        """Teleports the game as a door of the game would: the ROM is asked
        for a door's fade —where to, which cell, and the flag— and it loads
        the map by its own path. The screen's tint is cleared, which is the
        only thing a real door does not do: appearing on a map nobody walked
        to would keep whatever tint the map before left. A Blurred Line's
        `go_to_map`."""
        assert map_id in self.cartridge.maps, (
            "map %d is not in this cartridge; it carries %s"
            % (map_id, self.cartridge.maps))
        self.put_word("fade_map", self.cartridge.maps.index(map_id))
        self.put_word("entry_x", x)
        self.put_word("entry_y", y)
        # `start_fade`, from outside: which fade, that there is one, and the
        # clock, in ticks.
        self.put_byte("fade_kind", self.symbol("FADE_DOOR"))
        self.put_byte("fade", 1)
        self.put_byte("fade_base", self.word("ticks"))
        for name in ("tint_r", "tint_g", "tint_b", "tint_s"):
            self.put_byte(name, self.symbol("TINT_NEUTRAL"))
        self.run(ticks)

    def window(self):
        """Which map cell is drawn at each place of the screen, as the VRAM
        has it: `{(mx, my): (below, above)}`, the two tilemap entries, for
        the cells the screen touches inside the map.

        The tilemap's window is a torus —map cell `(mx, my)` always lives in
        slot `(mx mod 64, my mod 32)`—, so two shifted rows look like a
        plausible map on screen: one has to ask each slot. The two 32x32
        screens are not contiguous, the right one lives 1024 words further
        on, which is how `push_strips` writes them; where the background's
        is depends on the map's layout, and the ROM leaves it in
        `FAR_VRAM_MAP`. A Blurred Line's `window`."""
        win_col, win_row = self.word("win_col"), self.word("win_row")
        width, height = self.word("map_cw"), self.word("map_ch")
        cols, rows = self.symbol("WINDOW_COLS"), self.symbol("WINDOW_ROWS")
        below = self.console.vram(self.word("FAR_VRAM_MAP"), 32 * 32 * 2)
        above = self.console.vram(self.symbol("VRAM_ABOVE_MAP"), 32 * 32 * 2)
        seen = {}
        for my in range(win_row, min(win_row + self.symbol("VIEW_ROWS"), height)):
            for mx in range(win_col, min(win_col + self.symbol("VIEW_COLS"), width)):
                slot = (my % rows) * 32 + (mx % 32)
                if (mx % cols) >= 32:
                    slot += 1024
                seen[(mx, my)] = (below[slot], above[slot])
        return seen

    def wrongly_drawn_cells(self):
        """The window's cells that do not match what the ROM draws when it
        fills the window from scratch, and the window from before.

        It teleports the game to the cell where it already is, which makes
        the ROM rebuild the whole window by its own path —and so it
        **repairs** whatever it finds—. It only holds with the camera still
        and the pan back at zero, which is checked."""
        before = self.window()
        camera = (self.word("camera_x"), self.word("camera_y"))
        self.go_to_map(self.map_(), self.word("tile_x"), self.word("tile_y"))
        self.run(10)
        assert (self.word("camera_x"), self.word("camera_y")) == camera, (
            "the teleport left the camera at %s and before it was at %s: the "
            "reference is no good" % ((self.word("camera_x"),
                                       self.word("camera_y")), camera))
        after = self.window()
        return [c for c in before if before[c] != after[c]], before

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

"""A game's cartridge, running, for its tests: the generic part of the harness.

What every game's tests need and no game decides: the libretro driver
(`retro`), the cartridge as the builder answers for it and read through the
symbols and the map table it leaves (`game`), the tick clock and the
questions any game is asked —which map, which switch, whether the player
has control— (`session`), the goldens compared at 15 bits (`golden`), and
RPG Maker 2000's own rules the tests compute what to expect with (`rm2k`).
It knows no game: each one says, once, where it is and how its cartridges
are built —a `Game`, handed to `use` before the first test—, and its own
harness adds what only it knows on top.

Nothing here is written by hand about a cartridge: which symbols there are
in RAM is said by its `.sym`, which map each index is by its `mapdata.inc`,
and where the cartridge is and whether it is up to date by
`rm2k-snes-cartridges`.

**How a game's tests find it**: `rm2k-snes-project --harness` prints the
directory to put on the import path, the one of the checkout the tools were
installed from —the same that gives the runtime—, so the harness and the
runtime it reads the symbols of are always the same checkout's. The test
game, which lives beside it, puts it on its path in its `pytest.ini`.
"""

from .cores import ACCURATE, AUDIT, BSNES, SNES9X, core_name
from .game import RELEASE, Cartridge, Game, cartridge, current, listing, use
from .golden import golden
from .session import (FRAMES_PER_TICK, MESSAGE_SHOWN, SCREEN_HEADROOM, WRAM,
                      Session)

__all__ = [
    "ACCURATE", "AUDIT", "BSNES", "SNES9X", "core_name",
    "RELEASE", "Cartridge", "Game", "cartridge", "current", "listing", "use",
    "golden",
    "FRAMES_PER_TICK", "MESSAGE_SHOWN", "SCREEN_HEADROOM", "WRAM", "Session",
]

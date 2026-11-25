"""The engine's numbers, as the cartridge's build left them: the equates of
its `.inc`, which `ld65` writes into the `.dbg` and the `.sym` beside the
ROM whether the runtime references them or not.

**They live in `engine.rs` of `rm2k-snes-mapdata`, and only there**; the
emission hands them to the runtime by name, and this module reads them
back by that name: `engine.PAUSE_FRAMES`. One the runtime does not name a
test reads only if the emission writes it for it —see `for_readers` in
`rm2k-snes-mapdata`'s `emit.rs`—. Until 2026-11-25 this module asked
`rm2k-snes-mapdata engine`, which answered every number of `engine.rs`
whether the ROM had it or not; now it reads what the ROM was built with.

**A name is looked up in the whole table**, labels and equates alike: the
`.sym` does not tell them apart. A number is asked by the name the `.inc`
gives it, and a name the ROM does not have is an `AttributeError` that
says where to add it.

Which `.sym`: the current game's `release` —see `game`—, unless the
game's harness says another with `use_symbols`, as one that does not go
through `game` does.
"""

import functools

from . import game

_SOURCE = []


def use_symbols(path):
    """Read the numbers from the `.sym` `path` returns —a function, called
    the first time a number is asked, so that importing reads nothing—."""
    _SOURCE[:] = [path]
    table.cache_clear()


def symbols_of(path):
    """{name: value} of a `.sym`."""
    with open(path) as file:
        return {name: int(value) for name, value
                in (line.split() for line in file if line.strip())}


@functools.lru_cache(maxsize=None)
def table():
    """The `.sym`'s table, read once per process."""
    if _SOURCE:
        return symbols_of(_SOURCE[0]())
    return dict(game.cartridge().symbols)


def number(name):
    """The equate `name` of the cartridge."""
    symbols = table()
    if name not in symbols:
        raise AttributeError(
            "the cartridge's .sym has no %s: a number the runtime does not "
            "name reaches it only if the emission writes it —see "
            "`for_readers` in rm2k-snes-mapdata's emit.rs—" % name)
    return symbols[name]


def __getattr__(name):
    if name.isupper():
        return number(name)
    raise AttributeError(name)

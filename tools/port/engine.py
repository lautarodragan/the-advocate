"""The engine's numbers, as `rm2k-snes-mapdata engine` publishes them: the
ones the `.inc` hands the runtime —the box's header, the keys, the rain, the
fade, the troops' triggers— and the caps the compiled pages are checked
against.

**They live in `engine.rs` of `rm2k-snes-mapdata`, and only there.** Until
2026-10-02 `events.py` had a copy of each one, because the converter and the
game's tests read them; now both ask for them here, by the same names:
`engine.PAUSE_FRAMES`. The whys of most of them are still in `events.py`,
next to their names, where the runtime and the `.inc` cite them.

A list comes back as a tuple, which is what those names always were.
"""

import json

from port import stage

BINARY = "rm2k-snes-mapdata"
PROJECT = "mapdata"

_NUMBERS = {}


def numbers():
    """Every number by its name, asked once per process."""
    if not _NUMBERS:
        written = stage.run(BINARY, PROJECT, "engine", {})
        _NUMBERS.update(
            (name, tuple(value) if isinstance(value, list) else value)
            for name, value in json.loads(written["engine.json"]).items())
    return _NUMBERS


def __getattr__(name):
    if name.isupper() and name in numbers():
        return numbers()[name]
    raise AttributeError(name)

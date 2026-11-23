"""The libretro driver's two shortcuts change nothing a test sees.

`retro.Console.run` draws only the frames somebody is going to look at, and
a console of the same ROM as the previous one starts from the power-on
kept as a savestate instead of loading it again —see `POWER_ON_STATES`
there—. Both save a suite's CPU, and both are only worth it if the console
goes exactly the same way: the same screens where they are looked at, the
same WRAM and the same audio. Here the same play, with input and a write
to the WRAM halfway, goes four ways —drawing every frame or only the
looked-at ones, from a fresh load or from the kept power-on— and the four
have to agree byte for byte.

snes9x, because it is the core that skips: bsnes draws every frame and
starts each console with different garbage, on purpose, so it has nothing
to compare here.

What it does not cover: a savestate **in the middle** of a play. snes9x's
round trip —serialize and unserialize right away— is not exact: four bytes
of WRAM differ some hundred frames later, the stack where an interrupt
landed. That is why the frames are not drawn later by replaying them from
a state, which was measured and dropped, and why the kept power-on is only
taken before the first frame, where it is exact.
"""

import hashlib
import os

import pytest

from rm2k_snes_harness import SNES9X, cartridge
from rm2k_snes_harness import retro

FRAMES = 1500
LOOKED_AT = {1, 2, 40, 41, 233, 400, 401, 777, 1000, 1499, 1500}
WRITE_AT = 900


def _buttons(n):
    if n % 97 == 0:
        return ("start",)
    if n % 31 == 0:
        return ("a",)
    if 300 < n < 600:
        return ("right",)
    if 600 <= n < 800:
        return ("down",)
    return ()


def _play(every_frame, fresh):
    """The play, drawing every frame or only the looked-at ones —in runs
    of several frames where the buttons do not change—, and what it
    leaves: the hashes of the looked-at screens, of the WRAM and of the
    audio, and how many frames it counted."""
    if fresh:
        retro._power_on.clear()
    console = retro.Console(cartridge().rom, SNES9X)
    screens = {}
    n = 0
    while n < FRAMES:
        n += 1
        console.hold(*_buttons(n))
        span = 1
        if not every_frame and n % 50 == 1:
            span = 7
            while span > 1 and (
                    any(m in LOOKED_AT or m == WRITE_AT
                        for m in range(n, n + span - 1))
                    or len({_buttons(m) for m in range(n, n + span)}) > 1):
                span -= 1
        last = n + span - 1
        console.run(span, draw=every_frame or last in LOOKED_AT)
        n = last
        if n in LOOKED_AT:
            screens[n] = hashlib.sha1(console.image().tobytes()).hexdigest()
        if n == WRITE_AT:
            console.write_ram(0x1F00, b"\x01")
    return (screens, hashlib.sha1(console.ram()).hexdigest(),
            hashlib.sha1(bytes(console.audio)).hexdigest(),
            console.frame_count)


@pytest.fixture(scope="module")
def reference():
    """Every frame drawn, from a fresh load: what the driver did before
    either shortcut."""
    if not os.path.exists(SNES9X):
        pytest.skip("no libretro core at %s" % SNES9X)
    return _play(every_frame=True, fresh=True)


@pytest.mark.parametrize("every_frame,fresh", [
    (False, True), (True, False), (False, False)],
    ids=["only-looked-at", "kept-power-on", "both"])
def test_the_shortcuts_leave_the_same_console(reference, every_frame, fresh):
    screens, wram, audio, frames = _play(every_frame, fresh)
    assert frames == reference[3]
    assert screens == reference[0], "a looked-at screen changed"
    assert wram == reference[1], "the WRAM went another way"
    assert audio == reference[2], "the audio went another way"


def test_a_frame_run_without_drawing_is_not_shown(reference):
    """Whoever runs a frame with `draw=False` and then looks at it gets a
    refusal, not the previous frame passed off as this one."""
    console = retro.Console(cartridge().rom, SNES9X)
    console.run(10)
    console.image()
    console.run(1, draw=False)
    with pytest.raises(RuntimeError, match="without drawing"):
        console.image()
    console.run(3)
    console.image()

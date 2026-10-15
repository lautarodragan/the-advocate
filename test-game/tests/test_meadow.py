"""The meadow, map 1: the game boots on it, and the elder talks.

The skeleton's one test, and the whole path of a game through the tools:
the text in `src/` made into RM2k files, those dumped and converted, the
cartridge booted, a map drawn with its ChipSet, the hero and an NPC with
their CharSet, the hero walked by the pad, an action page started with A and
its message composed in the System's window. Two goldens: the map as it is
reached, and the message.

In snes9x, which the goldens are taken with, and in bsnes, which starts
with WRAM full of garbage: both have to draw the same at 15 bits, so a red
only in bsnes is memory nobody initialised.
"""

import os

import pytest

from game import BSNES, MESSAGE_SHOWN, SNES9X, Session, golden

# Where `src/maps.json` starts the party, and where `src/maps/Map0001.json`
# puts the elder, straight up from it: walking up, the hero stops in the
# cell below him.
START = (10, 10)
ELDER = (10, 6)


@pytest.fixture(params=[SNES9X, BSNES], ids=["snes9x", "bsnes"])
def core(request):
    if not os.path.exists(request.param):
        pytest.skip("no libretro core at %s" % request.param)
    return request.param


def test_the_elder_talks_to_whoever_talks_to_him(core):
    sess = Session(core)
    sess.until("on map 1 with control",
               lambda: sess.map_() == 1 and sess.has_control(), 600)
    # A few ticks more, so the map is drawn whole and the sprites are up.
    for _ in range(30):
        sess.advance()
    assert sess.cell() == START, "the hero starts at %s" % (sess.cell(),)
    golden("meadow", sess.image(), core)

    stop = sess.walk_until_blocked("up")
    assert stop == (ELDER[0], ELDER[1] + 1), (
        "walking up the hero stopped at %s, and not in front of the elder"
        % (stop,))
    sess.press("a")
    sess.until("the elder's message composed",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN
               and not sess.byte("msg_upload"), 300)
    # The window waits for a button; a second without one leaves it whole.
    for _ in range(60):
        sess.advance()
    assert sess.byte("msg_open"), "the message closed on its own"
    golden("elder", sess.image(), core)

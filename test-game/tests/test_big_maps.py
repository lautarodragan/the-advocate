"""The grid of a big map: one that goes one byte a cell, past the first
32 KB, and one that does not fit at all.

The grid lives in WRAM, the upper halves of banks $7E and $7F, 64 KB. Until
2026-10-17 a cell was two bytes, so a map past 32,768 cells did not fit and
stopped the build: Zounds' dream, map 30, is 200x200, and the game had it
left out by hand —see `tasks/a-200x200-map-does-not-fit-the-cell-stream.md`
in the-advocate-work—. Now a map with at most 256 blocks goes one byte a
cell, and one that fits neither way is left out with a warning.

The plain, map 6, is 200x200 and has three blocks: its grid is 40,000
bytes, and cell 32,768, (168, 163), is the first in $7F's half. Case
`big-narrow-map` leaves the hero at (100, 158); the test walks down across
rows 163 and 164 to the bush at (100, 170), and then right along row 163
across x 168 to the bush at (175, 163). Each walk ends on a golden.

The vast, map 7, is 330x200: 66,000 cells, past even one byte a cell. Case
`map-left-out` jumps to it and then turns 1403 on —its first command, which
turns it off, is there so the case runs on the meadow and not on the vast—:
the jump is the box that says the map is missing, and the page goes on.

Seen red with the tools before the change: the build stopped at the plain,
"a stream of map_cells is 47232 bytes and 32768 fit in WRAM".
"""

import json
import os

from game import MESSAGE_SHOWN, Session, golden

MEADOW, PLAIN, VAST = 1, 6, 7
AFTER_JUMP = 1403   # the left-out case's last command, after its Teleport


def test_a_200x200_map_walks_across_the_two_halves_of_its_grid(core):
    sess = Session(core, case="big-narrow-map")
    sess.until("on map %d with control" % PLAIN,
               lambda: sess.map_() == PLAIN and sess.has_control(), 600)
    assert sess.word("cell_bytes") == 1, "the plain's grid is not one byte a cell"
    assert sess.cell() == (100, 158), "the hero is at %s" % (sess.cell(),)
    # Down, across the rows where the grid changes bank, to the bush.
    assert sess.walk_until_blocked("down", 300) == (100, 169)
    golden("plain-down", sess.image(), core)
    # Up to row 163, and right across (168, 163) to the other bush.
    for _ in range(200):
        if sess.cell()[1] <= 163:
            break
        sess.advance("up")
    sess.until("standing on row 163",
               lambda: sess.word("hero_y") == 163 * 16, 60)
    assert sess.walk_until_blocked("right", 1500) == (174, 163)
    golden("plain-right", sess.image(), core)


def test_a_map_too_big_for_wram_is_left_out(core):
    sess = Session(core, case="map-left-out")
    with open(os.path.join(sess.cartridge.directory, "degradations.json")) as f:
        losses = json.load(f)["losses"]
    left = [loss for loss in losses
            if loss.get("map") == VAST and loss["kind"] == "map-left-out"]
    assert left, "degradations.json does not say the vast was left out"
    assert VAST not in sess.cartridge.maps, "the vast is in the cartridge"
    # Typed whole: a key pressed while a box is typed does nothing, as in RM2k.
    sess.until("the box of the missing map",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN, 600)
    sess.press("a")
    sess.until("with control", sess.has_control, 300)
    assert sess.switch(AFTER_JUMP), "the page did not go on past its Teleport"
    assert sess.map_() == MEADOW, "the game left the meadow"

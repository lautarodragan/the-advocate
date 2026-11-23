"""`ChangeMapTileset` on a map whose own pages ask for it: the frost, map 16.

The converter converts the map once more with each ChipSet its pages swap
in, over the same grid, and the ROM swaps the variant in —its block table,
and if it draws otherwise its tiles, colours and animation—: see
`variants.rs` in rm2k-snes-convert and `runtime/tileset.s`.

The frost is a field with a hedge down the middle, drawn with ChipSet 1,
Exterior. Its three events swap, each on its switch:

* **to Winter**, ChipSet 3: Exterior's picture with its colours turned to a
  winter's —`ChipSet/Winter.png`— and Exterior's passability. It draws
  otherwise: the screen changes, and the hedge still stops the hero.
* **to "Exterior above"**, ChipSet 2: Exterior's picture, with every upper
  tile passable. It draws the map as its own ChipSet does, so the ROM swaps
  its blocks alone; coming from Winter, it uploads the map's drawing again.
  The screen is the map's own, and the hedge lets the hero through —up to
  the map's edge, the border's bushes too—.
* **back to the map's own**, 0: the hedge stops him again, and the screen
  is the one he arrived to.

Every screen is taken with the hero in front of the hedge, facing it. The
switches are written from outside: what is looked at is the swap, not a way
to it.

Seen red with the global tools, which drop the command: the screen did not
change with Winter.
"""

from rm2k_snes_harness import golden

from play import boot, go_to

FROST = 16
# Each swap's switch, and the one its page turns on when it is done.
WINTER, AFTER_WINTER = 1800, 1801
OPEN, AFTER_OPEN = 1802, 1803
OWN, AFTER_OWN = 1804, 1805
# Where the guide leaves the hero, facing the hedge at column 11, and where
# it stops him; with every upper tile passable, the map's right edge does.
ARRIVAL = (9, 7)
BEFORE_THE_HEDGE = (10, 7)
THE_EDGE = (19, 7)


def swap(sess, switch, done):
    """Turns `switch` on and waits for its page to say it is done, and the
    screen to be drawn again."""
    sess.turn_on(switch)
    sess.until("the swap's page done", lambda: sess.switch(done), 120)
    for _ in range(4):
        sess.advance()


def back_left(sess):
    """Back left on his row, past the hedge's column."""
    for _ in range(200):
        if sess.cell()[0] < BEFORE_THE_HEDGE[0]:
            for _ in range(8):
                sess.advance()
            return
        sess.advance("left")
    raise AssertionError("the hero did not walk back left: he is at %s"
                         % (sess.cell(),))


def test_a_swap_draws_and_lets_through_with_the_chipset_asked(core):
    sess = boot(core)
    go_to(sess, "Frost")
    sess.until("control on the frost",
               lambda: sess.map_() == FROST and sess.has_control(), 600)
    assert sess.cell() == ARRIVAL, sess.cell()
    assert sess.walk_until_blocked("right") == BEFORE_THE_HEDGE
    own = sess.image()
    golden("frost-own", own, core)

    swap(sess, WINTER, AFTER_WINTER)
    winter = sess.image()
    assert winter.tobytes() != own.tobytes(), (
        "the screen did not change with the winter's ChipSet")
    golden("frost-winter", winter, core)
    assert sess.walk_until_blocked("right") == BEFORE_THE_HEDGE, (
        "the winter's ChipSet has Exterior's passability: the hedge blocks")

    swap(sess, OPEN, AFTER_OPEN)
    assert sess.image().tobytes() == own.tobytes(), (
        "\"Exterior above\" draws the map as its own ChipSet does")
    assert sess.walk_until_blocked("right") == THE_EDGE, (
        "with every upper tile passable the hero crosses the hedge")
    back_left(sess)

    swap(sess, OWN, AFTER_OWN)
    assert sess.walk_until_blocked("right") == BEFORE_THE_HEDGE, (
        "back on the map's own ChipSet, the hedge blocks again")
    assert sess.image().tobytes() == own.tobytes(), (
        "back on its own ChipSet, the map is drawn as it was on arriving")
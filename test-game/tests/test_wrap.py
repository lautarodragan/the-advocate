"""A map that loops: the ring, map 8, 24x16, `scroll_type` both. In RM2k
it is a torus —the hero, the events and the camera go across its edges to
the other side— and since 2026-10-19 the console does the same: see
`runtime/wrap.s`, and `tasks/maps-that-wrap-around.md` in
the-advocate-work. Until then every edge was a wall.

Case `ring` leaves the hero at (12, 10). The hero walks left along row 10
across column 0 to column 23, and, in the other test, up column 12 across
row 0 to row 15; each seam has its golden, with the hero on its first cell
across and the camera past the edge, showing the other side of the map
—the bush at (2, 12) and the tree at (2, 1) say which side is which—.

And the two walkers, each with a repeating page route: the leftward one,
event 1, from (12, 4) along row 4, stepping through `cell_allowed` with its
faces and who stands there; the upward one, event 2, from (20, 8) up
column 20, walking through everything. Both come back in from the other
side and go on, instead of piling up at the edge.

Seen red with the tools before the change: the hero stopped at (0, 10) and
at (12, 0), and the walkers at column 0 and row 0.
"""

from game import Session, golden

RING = 8
ARRIVAL = (12, 10)
WIDTH, HEIGHT = 24, 16


def tile(sess):
    return sess.word("tile_x"), sess.word("tile_y")


def on_the_ring(core):
    sess = Session(core, case="ring")
    sess.until("on map %d with control" % RING,
               lambda: sess.map_() == RING and sess.has_control(), 600)
    for _ in range(10):
        sess.advance()
    assert tile(sess) == ARRIVAL, "the hero is at %s" % (tile(sess),)
    return sess


def step(sess, direction):
    """One cell: holds the direction until the hero's cell changes, and
    waits for the step to end. A walker in the way only delays it."""
    before = tile(sess)
    for _ in range(60):
        sess.advance(direction)
        if tile(sess) != before:
            break
    for _ in range(40):
        if not sess.byte("step_left"):
            break
        sess.advance()
    return tile(sess)


def walker(sess, k):
    """Where event k of the map —in id order, from 0— stands."""
    at = sess._ram("ev_pos_buf") + 4 * k
    b = sess.console.ram(at, 4)
    return b[0] | b[1] << 8, b[2] | b[3] << 8


def test_the_hero_goes_left_across_column_0(core):
    sess = on_the_ring(core)
    walked = [step(sess, "left") for _ in range(14)]
    assert walked == [(x % WIDTH, 10) for x in range(11, -3, -1)], (
        "the hero walked %s along row 10" % walked)
    golden("ring-across-the-left-edge", sess.image(), core)


def test_the_hero_goes_up_across_row_0(core):
    sess = on_the_ring(core)
    walked = [step(sess, "up") for _ in range(12)]
    assert walked == [(12, y % HEIGHT) for y in range(9, -3, -1)], (
        "the hero walked %s up column 12" % walked)
    golden("ring-across-the-top-edge", sess.image(), core)


def test_the_walkers_come_back_in_from_the_other_side(core):
    sess = on_the_ring(core)
    left, up = [walker(sess, 0)], [walker(sess, 1)]
    for _ in range(1500):
        sess.advance()
        for trail, k in ((left, 0), (up, 1)):
            here = walker(sess, k)
            if here != trail[-1]:
                trail.append(here)
    # Each one went more than a lap: every column of row 4, every row of
    # column 20, and across the seam in the right order.
    assert {x for x, _ in left} == set(range(WIDTH)), (
        "the leftward walker went %s" % left)
    assert all(y == 4 for _, y in left), "the leftward walker left row 4: %s" % left
    assert ((0, 4), (WIDTH - 1, 4)) in zip(left, left[1:]), (
        "the leftward walker did not cross from column 0 to %d: %s"
        % (WIDTH - 1, left))
    assert {y for _, y in up} == set(range(HEIGHT)), (
        "the upward walker went %s" % up)
    assert ((20, 0), (20, HEIGHT - 1)) in zip(up, up[1:]), (
        "the upward walker did not cross from row 0 to %d: %s"
        % (HEIGHT - 1, up))

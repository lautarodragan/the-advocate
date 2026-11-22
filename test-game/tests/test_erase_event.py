"""`EraseEvent` takes out the event that runs it, and what is seen of that.

`CommandEraseEvent` with 0 erases "this event" until the map is loaded
again: it is not drawn, it does not block, none of its pages starts, and a
parallel page that runs it stops right there —easyrpg-player's
`CommandEraseEvent` with `main_flag` false—. In the runtime it is a bit,
`FLAG_ERASED`, and three paths that exist only for it:

* `apply_pages`, in `event_pages.s`, hides the erased event's row and lets
  its move route go. An event with nothing but a still graphic is one the
  page pick skips, so this is the only place that hides it;
* `conditions_ok`, in the same file, says no page of an erased event is
  met: what the hero's layer, the action key and the list of parallels ask;
* `op_erase_event`, in `interpreter_movement.s`, ends the page there when
  `pair_ev` says a parallel is the one running it.

The erasure, map 14, has two events that erase themselves:

* the statue, event 1 at (14, 5): People1, on the hero's layer, and an
  action page that erases it and then sets variable 201 to 1. The hero
  walks up to it, is stopped by it, presses A, and then walks through its
  cell. Its second page, automatic on switch 1452, sets 202 to 1 and turns
  1452 off: it must not start while the statue is erased, and must when
  the map is loaded again;
* the pacer, event 2 at (6, 7): People1, on the hero's layer, walking up
  and down, and a parallel page on switch 1450 that adds 1 to variable 200,
  waits a second, erases itself and turns 1451 on. 1451 must stay off and
  200 at 1: the page was cut, and never ran again.

And the loop, event 3 at (1, 3), below the hero and touched: a `Teleport`
to this same map, in front of the statue. RM2k loads nothing on a jump to
the map it is on, so what was erased stays erased; the harness's
`go_to_map` is not that, it loads the map.

What is drawn is asked of the screen, not of a golden: the field is one
grass tile, so a region where nothing is drawn is equal, pixel for pixel,
to the same region three cells to the right, where nothing ever stands.
The region is the event's cell and the one above it, which is where a
CharSet's figure goes, and a few pixels to each side. A golden would say
the same and would also freeze the hero's pose and the pacer's step, which
are not what this is about.

Before 2026-11-22 only the compiler's tests and A Blurred Line's
`test_erase_event_for_real.py` —an event with no graphic, in the
foreground— looked at `EraseEvent`: these paths were checked playing
Desert Nightmare, which erases events on 157 parallel pages.

Each path was seen red, broken in the runtime for one run: `apply_pages`'s
hiding, the statue and the pacer still drawn; its route, the pacer still
walking; `conditions_ok`, the statue still blocking and its other page
starting; `pair_ev`, 1451 on; the foreground cut too, 201 at 0; the map
load keeping the statue's erasure, its other page not starting after it.
The pacer's page not starting again is guarded twice —`apply_pages` leaves
the erased event out of the list of parallels it rebuilds, and
`conditions_ok` gives it no page to be one— so it is red only with both
broken. The task is `eraseevent-no-test-looks-at-what-is-seen`, in
the-advocate-work.
"""

from rm2k_snes_harness import Session

ERASURE = 14
STATUE, PACER = 0, 1                # their rows in the ROM's table
STATUE_CELL = (14, 5)
PACER_COLUMN = 6
PACER_ON = 1450                     # the pacer's page asks for it
AFTER_ERASE = 1451                  # the pacer's command after EraseEvent
PACER_RUNS = 200                    # +1 each time the pacer's page starts
STATUE_WENT_ON = 201                # the statue's command after EraseEvent
OTHER_PAGE = 1452                   # the statue's second page asks for it
OTHER_PAGE_RAN = 202                # and sets this
CLEARING = 4
LOOP = (1, 3)
LOOP_LANDING = (14, 9)              # where the loop's Teleport puts the hero

# How far to the right the region it is compared against is: three cells
# of the same grass, where no event stands and the hero is never put.
SHIFT = 3


def _region(sess, x, rows):
    """The pixels of map column `x` over map rows `rows`, a few pixels wider
    than the cell on each side and one cell taller on top: where a CharSet's
    figure standing on any of those cells is drawn."""
    cam_x, cam_y = sess.word("camera_x"), sess.word("camera_y")
    left = x * 16 - 4 - cam_x
    top = (rows[0] - 1) * 16 - cam_y
    bottom = (rows[-1] + 1) * 16 - cam_y
    return sess.image().convert("RGB").crop((left, top, left + 24, bottom))


def drawn(sess, x, rows):
    """Whether something is drawn over map column `x`, rows `rows`: its
    region against the same one `SHIFT` cells to the right."""
    here = _region(sess, x, rows)
    there = _region(sess, x + SHIFT, rows)
    return here.tobytes() != there.tobytes()


def test_an_erased_event_is_not_drawn_and_does_not_block(core):
    sess = Session(core)
    sess.go_to_map(ERASURE, STATUE_CELL[0], 9)
    assert drawn(sess, STATUE_CELL[0], [STATUE_CELL[1]]), (
        "the statue is not drawn before anything happened: the region "
        "check sees nothing")
    assert sess.walk_until_blocked("up") == (STATUE_CELL[0], STATUE_CELL[1] + 1), (
        "the statue, on the hero's layer, did not stop the hero")
    sess.press("a")
    sess.run(10)
    # Walked through first, so the hero, who stood below it and overlaps the
    # cell with their head, is out of the region when it is looked at.
    assert sess.walk_until_blocked("up") == (STATUE_CELL[0], 1), (
        "the hero cannot walk through the cell of an erased event")
    assert not drawn(sess, STATUE_CELL[0], [STATUE_CELL[1]]), (
        "the erased statue is still drawn")


def erase_the_statue(sess):
    """Walks up to the statue and presses A: it erases itself."""
    sess.go_to_map(ERASURE, STATUE_CELL[0], 9)
    sess.walk_until_blocked("up")
    sess.press("a")
    sess.run(10)


def take_the_loop(sess):
    """From in front of the statue's cell, walks to the loop and steps on
    it: its `Teleport` to this map puts the hero back below the statue."""
    sess.walk_until_blocked("left")
    assert sess.cell()[0] == LOOP[0], "the hero did not reach the loop's column"
    for _ in range(200):
        if sess.cell() == LOOP:
            break
        sess.advance("up")
    sess.until("back from the loop",
               lambda: sess.cell() == LOOP_LANDING and sess.has_control(), 300)
    assert sess.map_() == ERASURE


def test_the_erasure_lasts_until_the_map_is_loaded_again(core):
    """A foreground page goes on past its `EraseEvent`, as in RM2k; the
    erased event's other pages do not start; a jump to the same map loads
    nothing, so it stays erased; going to another map and back brings it
    back. A Blurred Line's `test_erase_event_for_real.py` asks the same of
    an event with no graphic."""
    sess = Session(core)
    erase_the_statue(sess)
    assert sess.variable(STATUE_WENT_ON) == 1, (
        "a foreground page has to go on after erasing its event")
    sess.turn_on(OTHER_PAGE)
    sess.run(30)
    assert sess.variable(OTHER_PAGE_RAN) == 0, (
        "a page of an erased event started: it is still standing")
    take_the_loop(sess)
    assert sess.variable(OTHER_PAGE_RAN) == 0, (
        "a jump to the same map brought the erased statue back")
    assert not drawn(sess, STATUE_CELL[0], [STATUE_CELL[1]]), (
        "a jump to the same map draws the erased statue again")
    sess.go_to_map(CLEARING, 10, 10)
    sess.go_to_map(ERASURE, STATUE_CELL[0], 9)
    assert sess.variable(OTHER_PAGE_RAN) == 1, (
        "after loading the map again the statue's other page did not start")
    assert not sess.switch(OTHER_PAGE), "the statue's other page did not end"
    assert drawn(sess, STATUE_CELL[0], [STATUE_CELL[1]]), (
        "after loading the map again the statue is not drawn")
    assert sess.walk_until_blocked("up") == (STATUE_CELL[0], STATUE_CELL[1] + 1), (
        "after loading the map again the statue does not block")


def test_a_parallel_page_that_erases_its_event_stops_there(core):
    sess = Session(core)
    sess.go_to_map(ERASURE, 16, 12)
    rows = list(range(1, 14))
    assert not drawn(sess, PACER_COLUMN, rows), (
        "the pacer is drawn with its page's switch off")
    sess.turn_on(PACER_ON)
    sess.run(5)
    assert sess.variable(PACER_RUNS) == 1, "the pacer's page did not start"
    assert drawn(sess, PACER_COLUMN, rows), (
        "the pacer is not drawn with its page on: the region check sees "
        "nothing")
    # Its Wait is a second; two are well past it.
    sess.run(120)
    assert not sess.switch(AFTER_ERASE), (
        "a parallel page went on past the EraseEvent of its own event")
    assert sess.variable(PACER_RUNS) == 1, (
        "the erased pacer's parallel page started again")
    assert not drawn(sess, PACER_COLUMN, rows), "the erased pacer is still drawn"
    where = sess.event(PACER)
    sess.run(60)
    assert sess.event(PACER) == where, (
        "the erased pacer is still walking: its move route was not let go")

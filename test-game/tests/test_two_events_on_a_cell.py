"""Two events on one cell: every one whose trigger matches fires.

RPG_RT walks the whole list of the map's events for the cell it looks at
—`Game_Player::CheckEventTriggerThere` and `CheckEventTriggerHere` in
easyrpg-player— and schedules each one whose active page has the trigger
asked for and the layer that side asks for; they then run one after the
other, by event number. Until 2026-11-20 the console stopped at the first
event standing on the cell, and if its page was not the one asked for, the
one behind it was never looked at: Desert Nightmare's box, pushed onto the
ladder that climbs to the next map, hid the ladder, and an invisible dog
sent into the middle of a gate hid the teleport under it. See
`action_in_cell` in `runtime/action_key.s` and
tasks/a-second-event-on-a-cell-is-never-asked.md in the-advocate-work.

The crossing, map 11, has four cells with two events each, in a row; a case
per cell leaves the hero two cells below it, facing up:

* (5, 4), the box and the ladder: an action page on the layer below, with
  no commands, and a touch page on the hero's, which turns 1330 on. A bump
  from below.
* (8, 4), the dog and the doorway: an action page below, empty, and a touch
  page below, 1331. The hero steps onto it.
* (11, 4), both: two touch pages below; the first turns 1332 on and the
  second turns 1333 on only if 1332 already is, so 1333 says both ran and
  in their order.
* (14, 4), the crate and the sign: two action pages on the hero's layer,
  the first empty and the second 1334. The button from below.

Seen red with the tools before the change: none of the four switches comes
on, and 1332 without 1333.
"""

from play import playing

LADDER, DOORWAY, FIRST, SECOND, SIGN = 1330, 1331, 1332, 1333, 1334
CROSSING = 11


def arrive(core, case, column):
    sess = playing(core, case)
    sess.until("on the crossing with control",
               lambda: sess.map_() == CROSSING and sess.has_control(), 600)
    assert sess.cell() == (column, 6), "the hero is at %s" % (sess.cell(),)
    return sess


def step_up(sess, column, row):
    """Up until the hero stands on (column, row)."""
    for _ in range(60):
        if sess.cell() == (column, row) and not sess.byte("step_left"):
            return
        sess.advance("up")
    raise AssertionError("the hero did not reach (%d, %d); he is at %s"
                         % (column, row, sess.cell()))


def settle(sess, ticks=30):
    for _ in range(ticks):
        sess.advance()


def test_a_bump_finds_the_ladder_under_the_box(core):
    sess = arrive(core, "crossing-ladder", 5)
    step_up(sess, 5, 5)
    for _ in range(4):
        sess.advance("up")
    settle(sess)
    assert sess.cell() == (5, 5), "the ladder let the hero through"
    assert sess.switch(LADDER), (
        "the bump asked only the box: the ladder's touch page behind it, on "
        "the hero's layer, never fired")


def test_a_step_finds_the_doorway_under_the_dog(core):
    sess = arrive(core, "crossing-doorway", 8)
    step_up(sess, 8, 4)
    settle(sess)
    assert sess.switch(DOORWAY), (
        "the step asked only the dog: the doorway's touch page under it "
        "never fired")


def test_both_touch_pages_run_in_their_order(core):
    sess = arrive(core, "crossing-both", 11)
    step_up(sess, 11, 4)
    settle(sess)
    assert sess.switch(FIRST), "the first touch page did not run"
    assert sess.switch(SECOND), (
        "the second touch page did not run after the first: only one event "
        "on the cell was asked, or they ran out of order")


def test_the_button_finds_the_sign_behind_the_crate(core):
    sess = arrive(core, "crossing-sign", 14)
    step_up(sess, 14, 5)
    sess.press("a")
    settle(sess)
    assert sess.switch(SIGN), (
        "the button asked only the crate: the sign's action page behind it "
        "never fired")

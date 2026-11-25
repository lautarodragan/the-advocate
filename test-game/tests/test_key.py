"""`KeyInputProc`: the page stops until the player presses the key.

What is looked at is what a pixel does not say: **which number was left in
the variable**, which is what a game's pages read afterwards with a
`ConditionalBranch`, and that the variable stays at zero while waiting. The
numbers are RM2k's —`CheckInput`: 1 down, 2 left, 3 right, 4 up, 5 the
action key, 6 cancel—, and the engine publishes them; both are checked.

The cases `key-wait-for-*` go to the clearing, wait half a second and wait
for the key into variable 88: `-a` the action key, `-dir` the d-pad, and `-all`
the three. The form that **does not wait** is `test_key_long_form.py`'s.

It came from A Blurred Line's suite, in the ports, on 2026-11-22.
"""

from rm2k_snes_harness import engine

from play import playing

VARIABLE = 88
CLEARING = 4
# What the cases take to reach the command once on the clearing: their
# `Wait`, five tenths of a second —thirty frames, measured: a press before
# them is not read—, with as much again of headroom.
REACHED = 60


def on_the_clearing(sess):
    sess.until("on the clearing", lambda: sess.map_() == CLEARING
               and not sess.byte("fade"), 300)


def waiting(core, case):
    sess = playing(core, case)
    on_the_clearing(sess)
    sess.run(REACHED)
    assert sess.running_a_page(), "the page is not waiting for anything"
    assert sess.variable(VARIABLE) == 0, (
        "it jumped ahead: the variable already had %d" % sess.variable(VARIABLE))
    return sess


def test_while_nobody_presses_the_variable_stays_at_zero(core):
    """And the page does not go on: without this, a command that waited for
    nothing would give the same green at the end."""
    sess = waiting(core, "key-wait-for-a")
    sess.run(60)
    assert sess.running_a_page(), "the page went on without anybody pressing"
    assert sess.variable(VARIABLE) == 0


def test_pressing_stores_the_action_key_number(core):
    sess = waiting(core, "key-wait-for-a")
    sess.press("a")
    sess.run(5)
    assert engine.KEY_VALUE_DECISION == 5
    assert sess.variable(VARIABLE) == 5, (
        "with A pressed the variable was left at %d" % sess.variable(VARIABLE))


def test_holding_the_key_does_not_answer(core):
    """What the command looks at is the **edge**, not that the button is
    down: `Input::IsTriggered`, the same thing a message is closed with, so
    the command does not eat the A that has just closed a box."""
    sess = playing(core, "key-wait-for-a")
    on_the_clearing(sess)
    sess.run(REACHED + 20, holding=("a",))
    assert sess.variable(VARIABLE) == 0, (
        "the command answered with A held since before starting: the "
        "variable was left at %d" % sess.variable(VARIABLE))


def test_the_d_pad_stores_each_directions_number(core):
    """The four, each on a console of its own: the command answers once and
    the page goes on, so nobody looks at a second press."""
    assert (engine.KEY_VALUE_UP, engine.KEY_VALUE_RIGHT, engine.KEY_VALUE_DOWN,
            engine.KEY_VALUE_LEFT) == (4, 3, 1, 2)
    for button, expected in (("up", 4), ("right", 3), ("down", 1), ("left", 2)):
        sess = waiting(core, "key-wait-for-dir")
        sess.press(button)
        sess.run(5)
        assert sess.variable(VARIABLE) == expected, (
            "with %s the variable was left at %d and RM2k gives %d"
            % (button, sess.variable(VARIABLE), expected))


def test_cancel_stores_six(core):
    """B, which is worth 6. **The same B also opens the pause menu, and it is
    right that it does**: the command eats nothing, and the page ends on
    this very tick. That is why the press is a single tick: with the menu
    open `ticks` does not advance and a second one would never come."""
    sess = waiting(core, "key-wait-for-all")
    sess.advance("b")
    assert engine.KEY_VALUE_CANCEL == 6
    assert sess.variable(VARIABLE) == 6, (
        "with B the variable was left at %d" % sess.variable(VARIABLE))


def test_with_all_three_asked_cancel_wins(core):
    """`CheckInput` goes from the highest value to the lowest, so B beats A
    and A beats the d-pad."""
    sess = waiting(core, "key-wait-for-all")
    sess.advance("b", "a", "up")
    assert sess.variable(VARIABLE) == 6, (
        "with B, A and up at once the variable was left at %d and it should "
        "say cancel" % sess.variable(VARIABLE))


def test_holding_a_direction_does_not_answer(core):
    """The same as with A: the **edge**."""
    sess = playing(core, "key-wait-for-dir")
    on_the_clearing(sess)
    sess.run(REACHED + 20, holding=("left",))
    assert sess.variable(VARIABLE) == 0, (
        "the command answered with left held since before starting: the "
        "variable was left at %d" % sess.variable(VARIABLE))

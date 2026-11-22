"""Playing the test game the way a person does: from the meadow, to the
guide's signpost or the tester's board, and down their menus.

The tests used to reach a case by writing the case variable before the
first frame, and a map by asking the ROM for a door's fade from outside.
Since 2026-11-22 the cases are the game's own —the tester's menus, written
by `hub.py`— and the maps are the guide's teleports, so a test starts the
way the player does, and what it tests is reached by the same path. Where
a test still pokes the RAM it says why on that line.

Choosing in a `ShowChoice` is A Blurred Line's `mark` and `confirm`, from
its playthrough in the ports, with its three traps: the window does not
look at the pad while it is typed, a press can be lost, and an extra A
chooses.
"""

from rm2k_snes_harness import Session

import hub

MEADOW = 1
# Where the game starts, and where the Way Home brings the hero back.
START = (10, 10)
# A press lost to the round the ROM did not read the pad on is repeated;
# this many per option is generous.
INSIST = 6
# How long A is held, and then let go, in frames: a tick is a frame or a
# few, and the ROM reads the pad once a tick.
FRAMES_HELD = 4


def boot(core, **options):
    """The game as it boots, once the player can move."""
    sess = Session(core, **options)
    sess.until("control on the meadow",
               lambda: sess.map_() == MEADOW and sess.has_control(), 600)
    return sess


def choice_ready(sess):
    """A `ShowChoice` on screen, whole, looking at the pad."""
    return bool(sess.byte("pick_active") and sess.box_up())


def choose(sess, option, limit=600):
    """Waits for the next `ShowChoice` and picks option `option`, from zero:
    down a press at a time, looking at the cursor between presses, and A
    until the window lets it go."""
    sess.until("a choice", lambda: choice_ready(sess), limit)
    n = sess.byte("pick_n")
    assert 0 <= option < n, "the choice has %d options and %d was asked for" % (n, option)
    for _ in range(n * INSIST):
        if sess.byte("pick_sel") == option:
            break
        sess.press("down")
    assert sess.byte("pick_sel") == option, (
        "the cursor did not reach option %d: it is on %d"
        % (option, sess.byte("pick_sel")))
    # A, in frames and not ticks, looking at the window after each: the
    # option taken may open a screen with no ticks inside —`OpenSaveMenu`—,
    # and a press that waited for a tick would wait for ever.
    for _ in range(INSIST * 2):
        sess.console.hold("a")
        for _ in range(FRAMES_HELD):
            sess.console.run(1)
            if not choice_ready(sess):
                sess.console.hold()
                return
        sess.console.hold()
        for _ in range(FRAMES_HELD):
            sess.console.run(1)
            if not choice_ready(sess):
                return
    raise AssertionError("the choice did not take A")


def talk_to(sess, direction):
    """From the start cell, walks `direction` until the signpost or the
    board stops the hero, and presses A on it: the board is right below
    the start, which the hero faces when the game boots and when the Way
    Home brings them back, so for it there is nothing to walk."""
    assert sess.map_() == MEADOW and sess.cell() == START, (
        "the hub is walked to from the meadow's start, and the hero is on "
        "map %d, at %s" % (sess.map_(), sess.cell()))
    if direction == "down":
        assert sess.byte("hero_dir") == sess.symbol("DIR_DOWN"), (
            "the hero is on the start cell but not facing the board")
    else:
        sess.walk_until_blocked(direction)
    # A press can be lost —the first one after the boot is—: repeated until
    # the page starts, and never once it has.
    for _ in range(INSIST):
        sess.press("a")
        if sess.running_a_page():
            return
    raise AssertionError("pressing A in front of the %s started nothing"
                         % ("board" if direction == "down" else "signpost"))


def go_to(sess, label):
    """The guide's teleport `label`, from the meadow's start; returns as
    soon as the hero is on another map, which may start a page of its own
    on arriving."""
    talk_to(sess, "left")
    for option in hub.guide_paths()[label]:
        choose(sess, option)
    sess.until("on another map", lambda: sess.map_() != MEADOW, 600)


def run_case(sess, name):
    """The tester's case `name`, chosen from the meadow's start. It returns
    as soon as the last choice is taken: the case's commands are what runs
    next, as they did when the harness chose it at boot."""
    talk_to(sess, "down")
    for option in hub.tester_paths()[name]:
        choose(sess, option)


def playing(core, name, **options):
    """A game booted and the tester's case `name` chosen: what
    `Session(core, case=name)` was before the cases were the game's."""
    sess = boot(core, **options)
    run_case(sess, name)
    return sess


def go_home(sess):
    """The Way Home, from the pause menu: its first option is the items,
    and the Way Home the first of them when the hero carries nothing
    else."""
    sess.choose("b")
    sess.screen_up()
    sess.choose("a")
    sess.choose("a")
    sess.until("back on the meadow",
               lambda: sess.map_() == MEADOW and sess.has_control(), 600)

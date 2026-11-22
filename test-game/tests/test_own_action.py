"""The action key also looks at the hero's own cell.

`Game_Player::CheckActionEvent` tries two cells and **each one asks for the
opposite layer**:

    CheckEventTriggerHere   the hero's cell,      GetLayer() != Layers_same
    CheckEventTriggerThere  the one in front,     GetLayer() == Layers_same

It is not symmetry for decoration: an event on the hero's layer blocks the
way, so the hero could never stand on top of it; and one on another layer
does not stop the hero, so it can be walked over.

The doors, map 12, has a hatch, event 5, at (4, 11): action, above the
hero, and its page leads to the clearing. A Blurred Line's way out of
Talan's pad is a door like it, and without this there was no way out; it
came from that game's suite, in the ports, on 2026-11-22.
"""

from play import boot, go_to

DOORS, CLEARING = 12, 4
DOORS_LABEL = "Doors"
HATCH = (4, 11)


def walk(sess, button, target, limit=200):
    """Holds `button` until the hero stands on `target`."""
    for _ in range(limit):
        if sess.cell() == target and not sess.byte("fade"):
            sess.run(2)
            return
        sess.advance(button)
    raise AssertionError("walking %s the hero did not reach %s: at %s"
                         % (button, target, sess.cell()))


def at_the_doors(core):
    """The guide's doors: in front of the door, at (10, 8)."""
    sess = boot(core)
    go_to(sess, DOORS_LABEL)
    sess.until("control", sess.has_control, 300)
    assert sess.map_() == DOORS
    return sess


def test_standing_on_the_hatch_and_pressing_a_opens_it(core):
    sess = at_the_doors(core)
    walk(sess, "down", (10, HATCH[1]))
    walk(sess, "left", HATCH)
    # A press can be lost on the tick the hero stops: a few, until the
    # hatch's page starts.
    for _ in range(4):
        sess.press("a")
        if sess.running_a_page():
            break
    sess.until("the clearing", lambda: sess.map_() == CLEARING, 200)


def test_head_on_does_not_trigger_it(core):
    """And the one in front must **not** trigger it: that one asks for the
    hero's layer, and the hatch is above it. Without this half, the first
    one would also pass in a world where the action key looked at both cells
    without filtering by layer."""
    sess = at_the_doors(core)
    # Below the hatch and facing it: from the row under it, one step up.
    walk(sess, "down", (10, HATCH[1] + 2))
    walk(sess, "left", (HATCH[0], HATCH[1] + 2))
    walk(sess, "up", (HATCH[0], HATCH[1] + 1))
    assert sess.byte("hero_dir") == sess.symbol("DIR_UP")
    for _ in range(4):
        sess.press("a")
        sess.run(30)
    assert sess.map_() == DOORS, (
        "something triggered while facing an event that is not on the hero's layer")

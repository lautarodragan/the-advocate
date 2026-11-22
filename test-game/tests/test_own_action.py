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

from rm2k_snes_harness import Session

DOORS, CLEARING = 12, 4
HATCH = (4, 11)


def test_standing_on_the_hatch_and_pressing_a_opens_it(core):
    sess = Session(core)
    sess.go_to_map(DOORS, *HATCH)
    assert sess.cell() == HATCH
    sess.press("a")
    sess.until("the clearing", lambda: sess.map_() == CLEARING, 200)


def test_head_on_does_not_trigger_it(core):
    """And the one in front must **not** trigger it: that one asks for the
    hero's layer, and the hatch is above it. Without this half, the first
    one would also pass in a world where the action key looked at both cells
    without filtering by layer."""
    sess = Session(core)
    sess.go_to_map(DOORS, HATCH[0], HATCH[1] + 1)
    sess.put_byte("hero_dir", sess.symbol("DIR_UP"))
    for _ in range(4):
        sess.press("a")
        sess.run(30)
    assert sess.map_() == DOORS, (
        "something triggered while facing an event that is not on the hero's layer")

"""A teleport cuts the hero's step in progress short: he lands on the cell.

`Game_Character::MoveTo`, in easyrpg-player, sets the remaining step to
zero, so a hero halfway between two cells when a page teleports him
arrives standing on the destination cell, and the step he was taking is
lost —the route that gave it is not cancelled—. Until 2026-11-22 the
console kept the step: the hero landed on the cell and, on the first frame
after the fade-in, went on from half a cell back along that step's
direction, and the camera with him. Zounds showed it between its maps 26
and 27, where a parallel page walks the hidden hero diagonally while the
autostart page teleports, as a jump of the camera right after the fade-in:
see `tasks/zounds-a-camera-pan-on-map-27-starts-with-a-jump.md` in the
tasks repository, and the ports' `tests/test_zounds_map_27_arrival.py`.

The case `teleport-mid-step` walks the hero one cell right, waits a tenth
of a second —less than the eight frames a step takes at speed 4— and
teleports to the clearing, map 4, cell (10, 7).
"""

from play import playing

CLEARING = 4
CELL = (10, 7)


def test_a_teleport_cuts_the_step_short(core):
    sess = playing(core, "teleport-mid-step")
    sess.until("on the clearing", lambda: sess.map_() == CLEARING, 600)
    assert not sess.byte("step_left"), (
        "the hero arrived on the clearing with %d of his step still to go"
        % sess.byte("step_left"))
    seen = []
    for _ in range(120):
        sess.console.run(1)
        seen.append((sess.word("hero_x"), sess.word("hero_y")))
    landed = (CELL[0] * 16, CELL[1] * 16)
    assert all(at == landed for at in seen), (
        "the hero after the jump, frame by frame, and he should stand at %s: "
        "%s" % (landed, sorted(set(seen))))

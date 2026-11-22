"""The hero's speed: that the pad walks at the one the last route left.

What a golden does not say is where the hero ended up, so here the speed a
route would have left is written into the hero and they are made to walk
with the pad. The reckoning of where they have to be is RM2k's: 256 units
per cell —`engine.JUMP_STEP`— at `1 << (1 + speed)` per frame, the
`Game_Character::UpdateMovement` step, and the pixels left are the units
left over sixteen.

The case `speed` puts the hero on the clearing at (10, 3): two cells up
there is the bush on its edge, so no reckoning goes past it. It came from A
Blurred Line's suite, in the ports, on 2026-11-22.
"""

import pytest

from rm2k_snes_harness import core_name, engine

from play import playing


def step_per_speed(speed):
    return 1 << (1 + speed)


def where_it_ends(tile_y, speed, ticks):
    """hero_y after `ticks` ticks **going up** from cell `tile_y`, at one
    frame per tick."""
    units = ticks * step_per_speed(speed)
    cells, remainder = divmod(units, engine.JUMP_STEP)
    if remainder:
        cells += 1
        missing = (engine.JUMP_STEP - remainder) >> 4
    else:
        missing = 0
    return (tile_y - cells) * 16 + missing


def on_the_clearing(core, case="speed"):
    sess = playing(core, case)
    sess.until_control()
    assert sess.map_() == 4 and sess.cell() == (10, 3)
    return sess


def test_starts_at_normal_speed(core):
    sess = on_the_clearing(core)
    assert sess.byte("FAR_HERO_SPEED") == 4


@pytest.mark.parametrize("speed,ticks", [(1, 20), (2, 10), (2, 40), (5, 3), (6, 3)])
def test_the_pad_walks_at_the_speed_the_route_left(core, speed, ticks):
    """At speed 2 the hero moves half a pixel per frame and takes 32 frames
    per cell; at 5, four pixels and four frames; at 1, a quarter of a pixel
    and 64 frames."""
    sess = on_the_clearing(core)
    y0 = sess.word("tile_y")
    # Poked, not played: in the game only a route's speed commands change
    # it, and this sweeps five speeds over the same walk; what is asked is
    # the pad's step at each, not the route.
    sess.put_byte("FAR_HERO_SPEED", speed)
    before = sess.console.frame_count
    sess.run(ticks, holding=("up",))
    assert sess.console.frame_count - before == ticks, (
        "a tick took more than a frame, so the frames walked are not the "
        "ticks counted")
    assert sess.word("hero_y") == where_it_ends(y0, speed, ticks), (
        "at speed %d, after %d frames going up from cell %d the hero is at "
        "y=%d and RM2k has them at %d"
        % (speed, ticks, y0, sess.word("hero_y"), where_it_ends(y0, speed, ticks)))


def test_the_speed_travels_in_the_save(core):
    if core_name(core) == "bsnes":
        # As in `test_variables.py`: bsnes keeps the SRAM between consoles.
        pytest.skip("bsnes keeps the SRAM between tests and does not let it be cleared")
    sess = playing(core, "speed-saved")
    try:
        sess.screen_up()
        # Poked, as above: what is asked is that the save carries it.
        sess.put_byte("FAR_HERO_SPEED", 2)
        sess.choose()
        sess.reset()
        sess.run(10)
        assert sess.byte("FAR_HERO_SPEED") == 2, (
            "the hero's speed did not come back from the SRAM: the reset sets "
            "it to 4 and the saved game had 2")
    finally:
        sess.console.write_sram(0, bytes(len(sess.console.sram())))

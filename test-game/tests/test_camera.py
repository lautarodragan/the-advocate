"""The map window against the camera: that what is drawn is what belongs
there.

A golden cannot catch this. The tilemap window is a torus —cell `(mx, my)`
always lives in slot `(mx mod 64, my mod 32)`—, so a row left undrawn looks
like a perfectly plausible map **shifted by one or two cells**: the tiles
are the neighbour's and there is no garbage to give anything away.
Collision keeps coming out of the cartridge's grid, which did not move, and
so one walks over walls.

The check is direct: the VRAM is asked which cell it has at each place on
the screen —`Session.window`— and that is compared against the same thing
arrived at through a teleport, which fills the whole window from scratch.
If the streaming is right, the two are identical; if a row was skipped,
they are not. The map is the patchwork, 60x60 of diagonal stripes, so no
row or column draws the same as its neighbour.

It came from A Blurred Line's suite, in the ports, on 2026-11-22, where it
ran on that game's map 5.
"""

import pytest

from rm2k_snes_harness import Session, core_name


def test_the_camera_reaches_two_rows_per_tick(core):
    """The worst case is **two** rows or columns per tick: the hero at speed
    6 walks 8 px per frame and a `PanScreen` at speed 6 moves the camera
    another 8, which is two 8-pixel cells. It is here so that the two cases
    below keep reproducing the bug: if someone lowers their speed, this
    fails instead of the other two passing without testing anything."""
    for case, axis in (("camera-fast", "camera_y"), ("camera-fast-x", "camera_x")):
        sess = Session(core, case=case)
        sess.until("on the patchwork", lambda: sess.map_() == 13
                   and not sess.byte("fade"), 300)
        worst, previous = 0, None
        for _ in range(60):
            sess.advance()
            now = sess.word(axis)
            if previous is not None:
                worst = max(worst, abs(now - previous))
            previous = now
        assert worst >= 16, (
            "%s moves the camera %d px per tick at most, and skipping a row "
            "takes more than 8: the case stopped reproducing" % (case, worst))


def window_after(core, case):
    if core_name(core) == "bsnes":
        # Its libretro core exposes no VRAM, which is what this reads; the
        # suite this came from ran it on snes9x alone too.
        pytest.skip("bsnes's core does not expose the VRAM")
    sess = Session(core, case=case)
    sess.until("on the patchwork", lambda: sess.map_() == 13
               and not sess.byte("fade"), 300)
    sess.until_control()
    return sess.wrongly_drawn_cells()


def test_the_window_follows_the_camera_going_down_fast(core):
    """An 8 px row that the camera uncovers and nobody redraws stays wrong
    forever: the torus slot is not touched again until 32 rows later."""
    wrong, cells = window_after(core, "camera-fast")
    assert not wrong, (
        "%d of the %d visible cells have another map cell drawn on them; the "
        "first ones: %s" % (len(wrong), len(cells), wrong[:6]))


def test_the_window_follows_the_camera_going_right_fast(core):
    """The same along the other axis: `MARGIN_COLS` covers four columns of
    lag, but a sustained pan uses them up in four frames."""
    wrong, cells = window_after(core, "camera-fast-x")
    assert not wrong, (
        "%d of the %d visible cells have another map cell drawn on them; the "
        "first ones: %s" % (len(wrong), len(cells), wrong[:6]))


def test_no_row_or_column_draws_like_its_neighbours(core):
    """Without this, the two above could pass with a window a row or two
    behind: on a map whose neighbouring rows draw the same, a shifted window
    is the right one."""
    if core_name(core) == "bsnes":
        pytest.skip("bsnes's core does not expose the VRAM")
    sess = Session(core, case="camera-fast")
    sess.until("on the patchwork", lambda: sess.map_() == 13
               and not sess.byte("fade"), 300)
    seen = sess.window()
    # The window's cells are the tilemap's, eight pixels: two to a tile.
    xs = sorted({x for x, _ in seen})
    ys = sorted({y for _, y in seen})
    assert len(xs) > 20 and len(ys) > 20, "the window is %dx%d" % (len(xs), len(ys))
    rows = {y: tuple(seen[(x, y)] for x in xs) for y in ys}
    columns = {x: tuple(seen[(x, y)] for y in ys) for x in xs}
    for lines, what in ((rows, "rows"), (columns, "columns")):
        for k, line in lines.items():
            for d in (1, 2):
                assert lines.get(k + d) != line, (
                    "%s %d and %d draw the same: a window that far behind "
                    "would not be seen" % (what, k, k + d))

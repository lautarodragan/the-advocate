"""An event whose page lifts its graphic above the hero covers him.

RPG_RT draws an event "above the hero" over him whatever its Y —
`Priority_EventsAbove` against `Priority_Player`, EasyRPG's
`Game_Character::GetScreenZ`—, and the layer is the active page's: a page
that becomes active with the same graphic on another layer moves it there.

The doors, map 12, has an awning, event 6, at (15, 11): upper tile 39 of
the ChipSet on the hero's layer, which blocks the way and, with A, turns
1441 on; and a second page, with 1441, with the same tile above the hero.
So once it is opened the hero walks onto its cell and it covers him.

It is Zounds' door to Kazar's room, on its map 19, which taro saw on
2026-11-22: the converter took an event whose pages all draw the same
graphic as one whose look never changes, its row did not follow the page,
kept the first one's layer, and the hero, on its row, was drawn over it.
See `collect_npcs` in `rm2k-snes/wally/src/events.rs`.

The tile is opaque in all its 16x16, so what is looked at is its cell on
screen: with the hero on it, the same as with the hero two cells to the
left, where his sprite does not reach it. In that corner the camera is
against the map's bottom right edge and does not move between the two.
"""

from play import boot, go_to

DOORS = 12
AWNING = (15, 11)
BESIDE = (14, 11)                   # where it stops the hero, facing it
AWAY = (13, 11)                     # where his sprite does not reach it
GRASS = (16, 11)                    # a cell with nothing, for the sanity check
OPEN = 1441


def walk(sess, button, target, limit=200):
    """Holds `button` until the hero stands on `target`."""
    for _ in range(limit):
        if sess.cell() == target and not sess.byte("fade"):
            sess.run(2)
            return
        sess.advance(button)
    raise AssertionError("walking %s the hero did not reach %s: at %s"
                         % (button, target, sess.cell()))


def box(sess, image, cell):
    """The 16x16 pixels of `cell` on screen, with the camera there is."""
    x = cell[0] * 16 - sess.word("screen_x")
    y = cell[1] * 16 - sess.word("camera_y")
    return image.convert("RGB").crop((x, y, x + 16, y + 16)).tobytes()


def test_the_opened_awning_covers_the_hero(core):
    sess = boot(core)
    go_to(sess, "Doors")
    sess.until("control", sess.has_control, 300)
    assert sess.map_() == DOORS
    walk(sess, "down", (10, AWNING[1]))
    walk(sess, "right", BESIDE)
    for _ in range(20):
        sess.advance("right")
    assert sess.cell() == BESIDE, (
        "the closed awning, on the hero's layer, did not stop the hero: at %s"
        % (sess.cell(),))
    for _ in range(4):
        sess.press("a")
        if sess.switch(OPEN):
            break
    sess.until("the awning's page", lambda: sess.switch(OPEN) and sess.has_control(), 120)
    walk(sess, "left", AWAY)
    camera = (sess.word("screen_x"), sess.word("camera_y"))
    alone = sess.image()
    assert box(sess, alone, AWNING) != box(sess, alone, GRASS), (
        "the awning's cell looks like the grass: the box is not the awning's")
    walk(sess, "right", AWNING)
    assert (sess.word("screen_x"), sess.word("camera_y")) == camera, (
        "the camera moved from %s: the two boxes are not the same place" % (camera,))
    assert box(sess, sess.image(), AWNING) == box(sess, alone, AWNING), (
        "with the hero on the opened awning's cell, the awning, above the "
        "hero, does not cover him: its row kept the closed page's layer")

"""A `Teleport` to a map the cartridge does not carry shows the screen.

The converter compiles such a jump as a box, "Teleport to missing map N",
and the page goes on where it is. A game often erases the screen before
the jump and leaves the showing to the destination's autostart; an erased
screen is black over the windows too, as in RPG_RT, so until 2026-10-17
the box waited for A in the black, and after it nothing showed the screen
again: the player walked a black map. Zounds' bed is that: its dream, map
30, is left out of the cartridge —see
`tasks/zounds-sleeping-in-unames-bed-leaves-the-screen-black.md` in
the-advocate-work—. Now the box comes after a `ShowScreen` with the cut.

The case `missing-teleport` erases the screen with the teleport's
transition, jumps to map 99, which the game does not have —for the
compiler the same as a map left out—, and turns 1402 on.

Seen red with the tools before the change: the box opens with the screen
erased and black.
"""

from game import MESSAGE_SHOWN, Session

AFTER_JUMP = 1402   # the page's last command, after its Teleport


def lit(sess):
    pixels = sess.image().convert("RGB").get_flattened_data()
    return max(max(p) for p in pixels) > 64


def test_the_box_of_a_missing_map_is_seen(core):
    sess = Session(core, case="missing-teleport")
    sess.until("a message composed",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN
               and not sess.byte("msg_upload"), 600)
    for _ in range(30):
        sess.advance()
    assert not sess.byte("SCREEN_ERASED"), "the box is up over an erased screen"
    assert lit(sess), "the box is up and the screen is black"
    sess.press("a")
    sess.until("with control", sess.has_control, 300)
    assert sess.switch(AFTER_JUMP), "the page did not go on past its Teleport"
    assert sess.map_() == 1, "the game left the meadow"
    assert lit(sess), "the meadow is black after the box"

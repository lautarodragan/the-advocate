"""`ChangeFaceGraphic`: the face a box draws, where RM2k draws it.

Until 2026-10-15 the command was accepted and did nothing: the box came out
without its face. Now the face's tiles go in the window's own text cells
—six by six, where RM2k puts it, with the text starting past it— and its
colours in palette 1 on the window's lines only, by HDMA: see
`runtime/message_face.s`, and the task `draw-the-faces` in
the-advocate-work.

The case `faces` sets Actor1's first face and shows a box —left—, then its
second face on the right and mirrored, and a box, then another box with no
command between —the face stays, as RM2k's `Game_System` keeps it—, then
its third face on the left again, and last clears it: the box after has no
face and the whole line back. Five goldens, one per box, in snes9x and in
bsnes.

Seen red with the tools before the change: `ChangeFaceGraphic` compiled to
nothing, and the boxes had no face and the text at the border.
"""

from game import MESSAGE_SHOWN, Session, golden


def shown(sess):
    """Waits for the next box, whole and waiting for a button."""
    sess.until("a message composed",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN
               and not sess.byte("msg_upload"), 300)
    # A few ticks more, so the window has finished opening.
    for _ in range(30):
        sess.advance()


def test_the_face_left_right_mirrored_changed_and_cleared(core):
    sess = Session(core, case="faces")
    for name in ("face-left", "face-right-mirrored", "face-stays",
                 "face-changed", "face-cleared"):
        shown(sess)
        golden(name, sess.image(), core)
        sess.press("a")
    sess.until("the case over", sess.has_control, 300)

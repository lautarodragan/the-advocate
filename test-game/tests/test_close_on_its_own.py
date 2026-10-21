"""A box whose tail is `\\^` and no `\\|`: typed whole, then gone without a
key, as RPG_RT's `kill_page` closes it at the end of the message.

Until 2026-10-20 the console closed it the frame after the page asked for
it, before the composer had finished it, and its text was never on screen:
the draft `a-box-that-closes-on-its-own-without-a-pause-is-never-seen` in
the-advocate-work. Now the page holds while the box is typed —see
`runtime/message_pace.s`— and its tail counts from there.

The case `close-on-its-own` shows the box and turns switch 1320 on after
it. Seen red with the tools before the change: the window never came up.
"""

from game import MESSAGE_SHOWN, Session

AFTER = 1320
TYPING = 2


def test_the_box_is_typed_whole_and_then_closes(core):
    sess = Session(core, case="close-on-its-own")
    sess.until("the box being typed",
               lambda: sess.byte("msg_open")
               and sess.byte("MSG_TYPE") == TYPING, 300)
    assert not sess.switch(AFTER), "the page went on while the box types"
    letters = 0
    for _ in range(300):
        if not sess.byte("msg_open"):
            break
        if sess.byte("msg_line") == 0:
            letters = sess.byte("msg_col")
        else:
            letters = len("Typed whole, and gone without a key.")
        sess.advance()
    else:
        raise AssertionError("the box did not close on its own")
    # The line ends —`msg_line` past it— only once its last letter is typed.
    assert letters == len("Typed whole, and gone without a key."), (
        "the box closed with %d letters typed" % letters)
    assert sess.byte("msg_state") == MESSAGE_SHOWN
    sess.until("the page past the box", lambda: sess.switch(AFTER), 60)

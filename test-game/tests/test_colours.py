"""`\\c[n]` and `\\s[n]`: a box's colours, and the pace it is typed at.

RM2k types a box letter by letter —easyrpg's `Window_Message::
UpdateMessage`—: at speed 1, the one a page starts at, two letters a frame;
at speed `n` past 1, one every `n / 2 + 1` frames; `\\.` waits 16 frames
and one more per speed past 16; `\\>` and `\\<` type at once what is between
them. And `\\c[n]` draws what follows in the System's text colour `n`. The
console does the same —see `runtime/message_pace.s` in the-advocate—, with
two losses the book's "What message escapes do not model" tells: a colour
takes **one** palette entry, the box's ink, so its gradient is one shade,
and a second colour in the same box is drawn with the window's nearest;
and the instant text goes at the composer's five letters a frame, not a
whole line in one.

The case `colours` shows four boxes: one with three colours —orange takes
the ink, gold and blue the window's nearest— and a whole line in orange;
one at speed 1; one at speed 10; and one at speed 20 with a `\\.` and an
instant stretch.

Seen red with the tools before the change: the colours were dropped and
the box came out white, and the window appeared with its box whole.
"""

from game import MESSAGE_SHOWN, Session, golden

TYPING = 2


def shown(sess):
    """Waits for the next box, typed whole and waiting for a button."""
    sess.until("a message typed",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN
               and not sess.byte("msg_upload"), 600)
    # A few ticks more, so the window has finished opening.
    for _ in range(30):
        sess.advance()


def typing(sess):
    """Waits for the next box to start being typed: its lines blanked and
    its window up."""
    sess.until("a box being typed",
               lambda: sess.byte("MSG_TYPE") == TYPING, 300)


def ticks_of_each_letter(sess, limit=600):
    """The tick each letter of a one-line box is typed on, counted from when
    its typing starts: from `msg_col`, which the line's end leaves as it
    is."""
    typing(sess)
    ticks, seen = [], 0
    for tick in range(limit):
        now = sess.byte("msg_col")
        ticks.extend([tick] * (now - seen))
        seen = now
        if sess.byte("msg_line") > 0:
            return ticks
        sess.advance()
    raise AssertionError("%d ticks and the line is not over" % limit)


def gaps(ticks):
    return [b - a for a, b in zip(ticks, ticks[1:])]


def test_the_colours_are_the_systems(core):
    sess = Session(core, case="colours")
    shown(sess)
    golden("colours", sess.image(), core)


def test_a_box_half_typed(core):
    """What was typed is on screen and the rest is not: the window up, and
    half of the line."""
    sess = Session(core, case="colours")
    shown(sess)
    sess.press("a")
    typing(sess)
    for _ in range(10):
        sess.advance()
    golden("colours-half-typed", sess.image(), core)


def test_speed_1_types_two_letters_a_tick(core):
    sess = Session(core, case="colours")
    shown(sess)
    sess.press("a")
    ticks = ticks_of_each_letter(sess)
    text = "Typed at speed one, two a frame."
    assert len(ticks) == len(text), ticks
    # RPG_RT waits a frame every second letter: two a frame.
    assert gaps(ticks) == [0, 1] * (len(text) // 2 - 1) + [0], ticks


def test_speed_10_types_a_letter_every_six_ticks(core):
    sess = Session(core, case="colours")
    for _ in range(2):
        shown(sess)
        sess.press("a")
    ticks = ticks_of_each_letter(sess)
    text = "Typed at speed ten."
    assert len(ticks) == len(text), ticks
    # 10 / 2 + 1.
    assert gaps(ticks) == [6] * (len(text) - 1), ticks


def test_speed_20_a_quarter_second_and_the_instant_text(core):
    sess = Session(core, case="colours")
    for _ in range(3):
        shown(sess)
        sess.press("a")
    ticks = ticks_of_each_letter(sess)
    text = "ab, and all this at once then."
    assert len(ticks) == len(text), ticks
    instant = text.index("all")
    want = (
        # `a`, eleven frames —20 / 2 + 1—, and the `\.`: sixteen and four
        # more, one per speed past 16.
        [11 + 20]
        # ", and " at eleven each.
        + [11] * (instant - 1)
        # "all this at once", five letters a tick: RM2k types it in one.
        + [0, 0, 0, 0, 1] * 3
        # The `\<` waits the speed's twenty, and " then." goes on at eleven.
        + [20]
        + [11] * (len(" then.") - 1)
    )
    assert gaps(ticks) == want, (gaps(ticks), want)

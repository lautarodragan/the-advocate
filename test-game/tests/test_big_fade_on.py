"""A big picture faded out without waiting: the case `big-fade-on`, on the
meadow.

`Picture/Curtain` is RM2k's whole screen of one dark plum, so the console
shows it as a big picture, on BG1 with the map hidden. The case shows it,
waits a second, fades it to transparency 100 in another **without
waiting** —the `MovePicture`'s last parameter off— and waits that second
too. In RM2k the meadow comes up through it while the page waits. On the
console the faded picture is black, since what is under it is the black
backdrop and not the map, so the converter takes it down where the page
has waited the fade's time: see `big_fade_outs` in rm2k-snes-events'
`compile.rs`. It is Desert Nightmare's motel at night, map 32, whose scene
after the bar played on black.

Seen red with the tools before the change: the curtain was taken down only
after a fade that waits, and the meadow stayed black once the case was
over.
"""

from play import playing

# The curtain's colour, on the console's 15 bits: 72, 24, 64 rounded down
# to a multiple of 8.
CURTAIN = (72, 24, 64)
# How much of the screen has to be the curtain while it is up, and how
# little once it is down.
UP = 0.9
DOWN = 0.01


def share(sess, colour):
    pixels = sess.image().convert("RGB").get_flattened_data()
    near = sum(1 for p in pixels
               if all(abs(a - b) <= 8 for a, b in zip(p, colour)))
    return near / len(pixels)


def lit(sess):
    pixels = sess.image().convert("RGB").get_flattened_data()
    return sum(1 for p in pixels if max(p) > 24) / len(pixels)


def test_the_meadow_comes_up_through_a_fade_that_does_not_wait(core):
    sess = playing(core, "big-fade-on")
    sess.until("the curtain up", lambda: share(sess, CURTAIN) >= UP, 600)
    sess.until("the case over", sess.has_control, 600)
    for _ in range(30):
        sess.advance()
    assert share(sess, CURTAIN) <= DOWN, "the curtain is still up"
    assert lit(sess) >= UP, (
        "with the case over, only %.1f %% of the screen is lit: the meadow "
        "is not seen" % (100 * lit(sess)))

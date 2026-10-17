"""Six small pictures at once, two sliding at the same time: the case
`pictures`, on the meadow.

Until 2026-10-16 the console kept two pictures at a time, one sprite
palette each, every one cut in 32x32 objects, and a `MovePicture` changed
only the tone: a third number was not drawn, and a move elsewhere was not
done. Now a map keeps up to sixteen, the converter puts the ones whose
colours fit together in one palette, a block with few cells drawn goes as
8x8 objects, the same pixels take their tiles once, and each slot has its
own ramp, which walks the corner too: see `runtime/picture_far.s` and
`rm2k-snes/convert/src/pictures.rs`.

The case shows the digits 1, 2 and 3 —8x10 in RM2k, three colours, one
palette and one 8x8 tile each—, a 64x48 panel of fifteen, a second 2 over
the panel —a higher number, so in front of it— and a bar as wide as RM2k's
screen, above it. Then the bar slides down into the screen and the 1 to
the bottom right corner, both in sixty frames, at once; then the 3 is
tinted blue in thirty.

Three goldens, in snes9x and in bsnes: halfway through the two slides,
when they have arrived, and with the 3 tinted. None with a picture half
transparent: the console's blend of it rounds a step apart in the two
cores.

Seen red with the tools before the change: the converter left four of the
six numbers out, and the moves were not done.
"""

from game import Session, golden

# The slots the converter gives the numbers: the highest number first,
# which OAM draws in front.
BAR, ONE, THREE = 0, 5, 3


def ramp(sess, slot):
    """Where slot `slot`'s ramp is: its step and its steps, zero if none."""
    step = sess.console.ram(sess._ram("PIC_R_STEP") + slot, 1)[0]
    steps = sess.console.ram(sess._ram("PIC_R_STEPS") + slot, 1)[0]
    return step, steps


def test_six_pictures_and_two_slides_at_once(core):
    sess = Session(core, case="pictures")
    sess.until("the bar sliding", lambda: ramp(sess, BAR)[1] == 60, 600)
    sess.until("the bar halfway", lambda: ramp(sess, BAR)[0] >= 30, 60)
    assert ramp(sess, BAR) == (30, 60), "the bar's ramp is at %s" % (ramp(sess, BAR),)
    assert ramp(sess, ONE) == (30, 60), "the 1's ramp walks with the bar's: %s" % (ramp(sess, ONE),)
    golden("pictures-sliding", sess.image(), core)
    sess.until("both arrived", lambda: ramp(sess, BAR)[1] == 0 and ramp(sess, ONE)[1] == 0, 200)
    golden("pictures-arrived", sess.image(), core)
    sess.until("the case over", sess.has_control, 300)
    assert ramp(sess, THREE)[1] == 0
    for _ in range(4):
        sess.advance()
    golden("pictures-tinted", sess.image(), core)

"""A shop's screens switch whole, from one frame to the next as seen: every
frame between the press and the new screen is the old screen or the new
one, never the new one's windows over the old one's text.

From taro, on 2026-11-22, playing A Blurred Line: going from the shop's
choice to its buy list showed, for up to twelve frames, the buy list's
windows, bar and party with the choice's text; and opening the shop, a
frame black down to line 166 and the shop below it. The text is typeset
some frames after the press —`text_layer.s`— and the windows went up in
the next vblank; the screen came on wherever its uploads ended. See
`runtime/shop.s`'s loop and `screen_ppu_on`.

The tester's `screen-letters-shop`: Zoë alone, a shop that sells the
potion and the Sword. The buy list shows the party walking, so "the
screen" is each picture it shows while it stands: every frame of one
screen is gathered while nothing is pressed, and a frame between is
compared against those.
"""

from play import playing

# How many frames a screen is watched standing —the party's walk is four
# steps of twelve frames, and its arrows' too—, and how many after a press.
STANDING = 60
WATCH = 40
STAYS = 4


def standing(sess):
    """Every picture the screen shows while nothing is pressed."""
    sess.console.hold()
    shown = set()
    for _ in range(STANDING):
        sess.console.run(1)
        shown.add(sess.image().convert("RGB").tobytes())
    return shown


def watch(sess, button):
    """Each frame from the press of `button` —two frames held—, as
    bytes."""
    frames = []
    for frame in range(WATCH):
        sess.console.hold(*((button,) if frame < 2 else ()))
        sess.console.run(1)
        frames.append(sess.image().convert("RGB").tobytes())
    return frames


def switch(sess, button):
    """What each frame after the press showed: "before", "after" or
    "neither"."""
    before = standing(sess)
    frames = watch(sess, button)
    after = standing(sess)
    return ["after" if f in after else "before" if f in before
            else "neither" for f in frames]


def whole(seen):
    first = seen.index("after") if "after" in seen else len(seen)
    return (all(v == "before" for v in seen[:first])
            and seen[first:] == ["after"] * (len(seen) - first)
            and len(seen) - first >= STAYS)


def test_the_shop_switches_whole(core):
    sess = playing(core, "screen-letters-shop")
    sess.screen_up()
    wrong = []
    for name, button in (("to the buy list", "a"), ("down the list", "down"),
                         ("back to the choice", "b")):
        seen = switch(sess, button)
        if not whole(seen):
            wrong.append("%s: %s" % (name, seen))
    assert not wrong, ("frame by frame —the screen before, after, or "
                       "neither—: %s" % "; ".join(wrong))

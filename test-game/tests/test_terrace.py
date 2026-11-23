"""A transparent box in the middle of the screen over a panorama that
scrolls on its own: the terrace, map 9, with characters walking under the
letters; and then the same in the rain.

It keeps a stress case of A Blurred Line's: its map 1 —a flattened map in
mode 3, whose panorama scrolls on its own— with the message of `EV0002`
made transparent and put in the middle, measured by hand on 2026-11-16
and not kept in that game's suite, because there it would have moved the
cartridge's text block and its goldens. See the task
`the-test-game-a-transparent-box-over-a-scrolling-panorama` in
the-advocate-work, and `a-window-line-cannot-wait-forever`, where it was
measured. Here it costs that game nothing.

**The scene**: a slab of grass in a night sky, `Panorama/Stars.png`,
scrolling three pixels a step on its own; the hero still at its bottom,
three walkers going round with repeating routes, and two trees whose
crowns go above the hero, which makes the map flattened, as that one is.
The guide's "Terrace" leaves the hero there —and the probe cartridge's
case `terrace`, the same teleport—, and a parallel page of the map
—a parallel one so the walkers go on walking, which under an automatic
page they would not, as in RM2k— shows four boxes, transparent and in
the middle: four lines, four, three and one. The sky is left where the
lines start and in a hole in the slab, so the letters go over it.

**Then the rain**, since A Blurred Line's map 1 has it on while its boxes
are up —weak there, `EV0001` sets it before `EV0002` talks—: the hero
turns to the event at their right, `Rain`, and talks to it; it sets the
rain strong —`RAIN_DROPS_2` drops, two objects each, after every
character in the OAM: see `runtime/rain.s`— and turns switch 1500 on,
whose parallel page of the same event shows four boxes more, the same
shape, and turns it off. The rain stays. Everything below is asked over
both halves of the scene.

**What it asks**:

* on the `test-vblank` cartridge, built with `--vblank-probe`, every call
  of `upload_line` while the boxes are typed: the vblank line it read and
  its margin to the limit it had —`LINE_LATEST_BARE` on a line's first
  try, `LINE_LATEST` on the next—. That no line waited two vblanks, that
  the ceiling (`WAIT_CEILING` in `runtime/vblank.s`) never put the screen
  in forced blank, and that the window's writes ended with `MARGIN` lines
  of the vblank to spare, on snes9x and bsnes. A line that misses its
  first vblank and goes up on the next is the window's design —the second
  chance, see `upload_line`—, so it is counted, not failed;
* on bsnes's accurate PPU with the display-access audit, `release`: no
  VRAM, CGRAM or OAM access lands while the screen is drawn, over the
  whole scene. Without that core it skips, saying how to get it;
* and what it looks like: the first box whole, and the third, with a
  walker on its lines; and the same two in the rain, with drops over the
  letters.

**Measured** when it was written, on 2026-11-16: 34 calls on snes9x,
bsnes and the audit core; 22 read line 235 or 236 and went up on their
first try, margin 3 or 2; 6 read 239 or 240, missed it by 1 or 2, and
went up on the next vblank at 235 to 237, margin 11 to 9. No forced blank;
the window's writes ended at worst on line 256; 0 display accesses. A
Blurred Line's map 1, measured the same way, read 235 to 240, with nine
misses by one or two and no ceiling. And with the probe's `VBLANK_STALL`
at 251 —the vblank full before the window's work— the first test goes
red, the ceiling firing on every line.

**In the rain**, measured on 2026-11-16 too: 29 calls on snes9x and
bsnes; 27 read line 235 and went up on their first try, margin 3; one read
240, missed it, and went up on the next vblank at 236 or 237, margin 10 or
9. No forced blank; the window's writes ended at worst on line 257, one
later than dry; 0 display accesses. The rain costs the window nothing it
can see: its drops are moved and put in the OAM outside the vblank, and
the OAM's upload is the same 544 bytes with them or without.

**What the goldens show that RM2k does not**: on the box's lines the
panorama is black, since in mode 3 it is BG2, which the window takes on
its lines —the known divergence "The window without a background does not
cover the characters", in the book—; and the walkers and the rain's
drops go over the letters, the same divergence: they are objects, which
in mode 3 go in front of BG2, and in RM2k the window is above the weather
too. The striped columns at the screen's edges that A Blurred Line's map
1 showed —the draft
`a-transparent-window-over-a-flattened-panorama-shows-striped-edges`— do
not show here, dry or in the rain: and they are not the rain's, since
that map shows them the same with its rain taken out. The draft says
what is left.

What it does not cover: the console's timing and an FX Pak's hooks, only
the emulators'; a map with the layer above for the text, which a
flattened map has not; and a camera that moves while a box is up.
"""

import os

import pytest

from rm2k_snes_harness import ACCURATE, AUDIT, MESSAGE_SHOWN, Session, golden

from play import boot, go_to

TERRACE = 9
BOXES = 4                   # dry, and as many again in the rain
PROBE = "test-vblank"

VBLANK_LAST = 261           # NTSC's last line
MARGIN = 3                  # `VBLANK_WRITES_END`'s, in runtime/far_ram.s
# What `vblank_line` answers past the vblank: see `upload_line`.
ON_THE_SCREEN = 0xFFFF


def boxes(sess, first, count, at_each_box):
    """`count` boxes, from the `first`-th of the scene: each one waited
    for whole on screen, given a few ticks, `at_each_box(k)` and an A."""
    for k in range(first, first + count):
        sess.until("box %d whole on screen" % k,
                   lambda: sess.byte("msg_open")
                   and sess.byte("msg_state") == MESSAGE_SHOWN
                   and not sess.byte("msg_upload"), 600)
        # A few ticks more, so the window has finished opening.
        for _ in range(30):
            sess.advance()
        at_each_box(k)
        sess.press("a")
    sess.until("the boxes over", sess.has_control, 600)


def raining(sess):
    """The weather's type, `WEATHER_RAIN`, and how many drops are alive:
    `far_weather` and `far_rain` in runtime/rain.s."""
    kind = sess.byte("far_weather")
    room = sess.symbol("RAIN_DROPS_MAX")
    drops = sess.console.ram(sess._ram("far_rain"), 3 * room)
    return kind == sess.symbol("WEATHER_RAIN"), sum(
        1 for d in range(room) if drops[3 * d + 2])


def play(sess, at_each_box=lambda k: None):
    """From the case to the end of the scene: its four boxes, then a talk
    with the rain's event, at the hero's right, and its four boxes in the
    rain. `at_each_box(k)` sees the boxes as 0 to 7."""
    sess.until("on the terrace", lambda: sess.map_() == TERRACE, 600)
    boxes(sess, 0, BOXES, at_each_box)
    assert not raining(sess)[0], "it rains before the rain's event"
    sess.walk_until_blocked("right")
    sess.press("a")
    sess.until("raining", lambda: raining(sess)[0], 60)
    boxes(sess, BOXES, BOXES, at_each_box)
    on, alive = raining(sess)
    assert on and alive, "the rain stopped, or has no drops: %d" % alive


def test_each_line_goes_up_inside_the_vblank(core):
    # The probe's cartridge, which carries the terrace and the clearing and
    # no hub: the case is the harness's, the guide's same teleport.
    sess = Session(core, case="terrace", on=PROBE)
    bare = sess.symbol("LINE_LATEST_BARE")
    latest = sess.symbol("LINE_LATEST")
    # The probe's counters live in far RAM that the boot does not clear: a
    # difference, not a value.
    forced = sess.word("VBLANK_FORCED_N")
    calls, late = [], []
    run = sess.console.run

    def put(name, value):
        sess.console.write_ram(sess._ram(name), [value & 0xFF, value >> 8])

    def probed(frames=1, draw=True):
        for _ in range(frames):
            put("VBLANK_UPLOAD_LINE", 0)
            put("VBLANK_WRITES_LINE", 0)
            waited = sess.byte("msg_waited")
            run(1, draw=draw)
            if sess.map_() != TERRACE:
                continue
            seen = sess.word("VBLANK_UPLOAD_LINE")
            if seen:
                calls.append((seen, waited, sess.byte("msg_waited"),
                              raining(sess)[0]))
            wrote = sess.word("VBLANK_WRITES_LINE")
            if wrote > VBLANK_LAST - MARGIN:
                late.append(wrote)

    sess.console.run = probed
    play(sess)

    def table():
        return "; ".join(
            "%sline %s, %s try, %s" % (
                "in the rain, " if wet else "",
                "past the vblank" if seen == ON_THE_SCREEN else seen,
                "second" if before else "first",
                "missed" if after else "margin %d"
                % ((latest if before else bare) - seen))
            for seen, before, after, wet in calls)

    assert calls, "no line went up: is the probe on?"
    assert any(wet for *_, wet in calls), (
        "no line went up in the rain: the rain's boxes were not measured")
    assert (sess.word("VBLANK_FORCED_N") - forced) & 0xFFFF == 0, (
        "the ceiling put the screen in forced blank: a line waited %d "
        "vblanks. The calls: %s" % (sess.symbol("WAIT_CEILING"), table()))
    twice = [c for c in calls if c[1] and c[2]]
    assert not twice, ("%d lines missed their second vblank too. The "
                       "calls: %s" % (len(twice), table()))
    assert not late, (
        "the window's writes ended on line %d, past %d: fewer than %d lines "
        "of the vblank to spare" % (max(late), VBLANK_LAST - MARGIN, MARGIN))


@pytest.mark.skipif(not os.path.exists(AUDIT),
                    reason="no bsnes with the display-access audit at %s: "
                    "build it as the CI workflow does —bsnes at its pin with "
                    "both patches of rm2k-snes/harness/cores/— and point AUDIT_CORE "
                    "at it" % AUDIT)
def test_nothing_reaches_the_screen_while_it_is_drawn():
    sess = boot(AUDIT, options=ACCURATE)
    sess.console.watch_the_display()
    go_to(sess, "Terrace")
    play(sess)
    seen = sess.console.display_accesses
    assert not seen, (
        "on %d frames the accurate PPU refused or misplaced an access "
        "because the screen was being drawn, which the console loses: the "
        "first, %r" % (len(seen), seen[0]))


def test_what_it_looks_like(core):
    sess = boot(core)
    go_to(sess, "Terrace")
    shots = {0: "terrace-first-box", 2: "terrace-three-lines",
             4: "terrace-rain-first-box", 6: "terrace-rain-three-lines"}
    play(sess, lambda k: k in shots and golden(shots[k], sess.image(), core))

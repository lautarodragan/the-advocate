"""A battle animation flashes the event it falls on, and nobody else.

`ShowBattleAnimation` on a map event plays the animation over it, and each
timing with a target flash tints **the target** toward its colour for a
few frames —easyrpg-player's `BattleAnimationMap::FlashTargets`, which is
`Game_Character::Flash` on the target—. On the console that flash is a
tint of the target object's sprite palette: `flash_start` and
`target_palette` in `runtime/character_flash.s`.

A still event drawn with a ChipSet tile may have no object: Wally draws one
that only changes pose into the background, a block per pose (`posed`),
and one that never changes into the layer above (`baking`). The row of
the first keeps in its palette bits which of its characters it shows, so
until 2026-11-22 a battle animation on it tinted that sprite palette —the
hero's, 0—: A Blurred Line's Lazer Teeth HQ flashed Talan when the rock
hit the computer. Now an event a battle animation falls on stays an
object, as one a `FlashSprite` names always did.

The anvil, map 15, has both kinds, drawn with the Exterior's opaque upper
tile 39:

* the crate, event 1 at (10, 5), on the hero's layer, with a second page
  on switch 1460 that shows tile 78 —which would make it a still drawn
  into the background—; its action page plays animation 1 on "this
  event";
* the slab, event 3 at (12, 6), below the hero, with one page: one that
  would be painted into the layer above; the lever, event 2 at (11, 6),
  with no graphic and on the hero's layer, plays animation 1 on it by id.

Animation 1, "Red flash", draws nothing —it has no sheet—, and flashes
its target red on its second frame, as "Hit A" does: so what changes on
screen is the flash alone. The guide's "Anvil" puts the hero at (10, 6),
below the crate and with the lever on their right.

The hero's own cell is compared, not their whole 24x32: the top half of
it is over the crate's cell, which does flash. Both were seen red with
Wally's `posed` and `baking` as they were: the hero's cell tinted, the
crate's and the slab's unchanged. The task is
`abl-the-rock-s-hit-flashes-talan-instead-of-the-computer`, in
the-advocate-work.
"""

from play import boot, go_to

ANVIL = 15
LANDING = (10, 6)
CRATE = (10, 5)
SLAB = (12, 6)
# Long enough for the animation's eight frames, two ticks each, and the
# ten frames of its flash.
TICKS = 40


def _cell(sess, x, y):
    """The pixels of map cell (x, y), and four to each side: where what
    stands on it is drawn at its feet."""
    cam_x, cam_y = sess.word("camera_x"), sess.word("camera_y")
    left, top = x * 16 - 4 - cam_x, y * 16 - cam_y
    return sess.image().convert("RGB").crop(
        (left, top, left + 24, top + 16)).tobytes()


def arrive(core):
    sess = boot(core)
    go_to(sess, "Anvil")
    sess.until("control", sess.has_control, 300)
    assert sess.map_() == ANVIL and sess.cell() == LANDING
    return sess


def flashes(sess, target):
    """Presses A and watches the target's cell and the hero's for `TICKS`:
    whether each changed on some tick."""
    target_before, hero_before = _cell(sess, *target), _cell(sess, *LANDING)
    sess.press("a")
    target_changed = hero_changed = False
    for _ in range(TICKS):
        sess.run(1)
        target_changed |= _cell(sess, *target) != target_before
        hero_changed |= _cell(sess, *LANDING) != hero_before
    assert sess.cell() == LANDING
    return target_changed, hero_changed


def test_an_animation_on_a_still_event_flashes_it_and_not_the_hero(core):
    """The crate, which plays it on itself."""
    sess = arrive(core)
    crate, hero = flashes(sess, CRATE)
    assert not hero, (
        "the hero flashed when the animation fell on the crate: its flash "
        "tinted the hero's palette")
    assert crate, "the crate did not flash under its own animation"


def test_an_animation_named_by_id_flashes_its_event_and_not_the_hero(core):
    """The slab, which the lever names."""
    sess = arrive(core)
    sess.advance("right")       # turns: the lever blocks the cell
    sess.run(4)
    assert sess.cell() == LANDING
    slab, hero = flashes(sess, SLAB)
    assert not hero, (
        "the hero flashed when the animation fell on the slab: its flash "
        "tinted the hero's palette")
    assert slab, "the slab did not flash under the lever's animation"

"""`\\N[0]`, the party's leader, and the `\\N[n]` of an actor a
`ChangeHeroName` renames, written by the ROM when the box opens.

Until 2026-10-15 the converter wrote a `\\N[n]` into the text with the
database's name, and only when no `ChangeHeroName` of the game touched that
actor; `\\N[0]` and a renamed actor's left the whole page out, and
`ChangeHeroName` did not compile. Now the text carries a mark —`NAME` in the
event compiler's `messages.rs`— and the composer hands out the name's
letters from the cartridge's text table: see `runtime/actor_names.s`.

The case `leader-name` shows "\\N[0] leads." with the database's party,
Hero; then brings Alda in and puts Hero behind her, and shows the same box,
which now names Alda; then renames Hero "Hiro" and shows
"\\N[1] follows \\N[0].". After it, the menu shows the new name too. The
case `no-leader` empties the party and shows "[\\N[0]] leads no one.": with
no one leading, RM2k writes nothing.

Seen red with the tools before the change: the cartridge did not build,
since a test page's box with `\\N[0]` does not compile.
"""

import pytest

from game import MESSAGE_SHOWN, Session, core_name, golden


def shown(sess):
    """Waits for the next box, whole and waiting for a button."""
    sess.until("a message composed",
               lambda: sess.byte("msg_open")
               and sess.byte("msg_state") == MESSAGE_SHOWN
               and not sess.byte("msg_upload"), 300)
    # A few ticks more, so the window has finished opening.
    for _ in range(30):
        sess.advance()


def test_the_leader_and_a_renamed_actor(core):
    sess = Session(core, case="leader-name")
    shown(sess)
    golden("leader-hero", sess.image(), core)
    sess.press("a")
    shown(sess)
    golden("leader-alda", sess.image(), core)
    sess.press("a")
    shown(sess)
    golden("renamed", sess.image(), core)
    sess.press("a")
    sess.until("the case over", sess.has_control, 300)
    # The menu draws Hero's name from his rename's row.
    sess.choose("b")
    sess.screen_up()
    golden("renamed-menu", sess.image(), core)


def test_no_leader_is_no_name(core):
    sess = Session(core, case="no-leader")
    shown(sess)
    golden("no-leader", sess.image(), core)


def test_a_rename_travels_in_the_save(core):
    """The case `rename-saved` renames Hero "Hiro", turns on 1300 and opens
    the slot screen, where slot 0 is chosen; after a reset the game loads
    with 1300 on and the case's other branch says "\\N[1] is back.", renames
    him "Hugo" and opens the slot screen again: slot 0 shows the leader's
    name as it was saved, Hiro, as RM2k's save screen does."""
    if core_name(core) == "bsnes":
        # bsnes exposes no SRAM to clear afterwards, and keeps it from one
        # console to the next in the same process: a cartridge without a
        # title loads a saved game on boot, so every test after this one
        # would start from it. The save is the ROM's, not the core's: one
        # core is enough.
        pytest.skip("bsnes keeps the SRAM between tests and does not let it be cleared")
    sess = Session(core, case="rename-saved")
    try:
        sess.screen_up()
        sess.choose()
        sess.reset()
        # The saved game is loaded, with 1300 on, and the case runs again:
        # now down its other branch.
        sess.choose_case("rename-saved")
        shown(sess)
        golden("rename-loaded", sess.image(), core)
        # In frames and not ticks: the slot screen opens right after, and
        # inside it there are none.
        sess.choose()
        sess.screen_up()
        golden("rename-slot", sess.image(), core)
    finally:
        # The core keeps its SRAM from one console to the next in the same
        # process, and a cartridge without a title loads a saved game on
        # boot: the tests after this one would start from it.
        sess.console.write_sram(0, bytes(len(sess.console.sram())))

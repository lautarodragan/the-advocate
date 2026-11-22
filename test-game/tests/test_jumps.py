"""The budget of chained teleports: that it is restored, and that it is not
spent silently.

`jumps_left` exists so that two maps that teleport to each other do not hang
the console. What counts are the **chained** jumps, the ones that happen
without the player getting control back; those of a game are as many as
they want to be.

It was wrong in both possible ways: only entering a map by a door restored
it, so a `Teleport` command spent it for the whole game; and when it ran
out, the jump was **discarded** without a word, so the game went on on the
wrong map. taro found it playing A Blurred Line on 2026-09-07: a dispatcher
map —empty on purpose, an automatic page per switch, each sending the hero
somewhere else— did not get them out, and its page, still on, started
again forever. The lookout carries one like it, "Dispatcher", on switch
1430. It came from that game's suite, in the ports, on 2026-11-22.
"""

from rm2k_snes_harness import Session

DISPATCHER = 1430
LOOKOUT, CLEARING = 10, 4


def test_the_budget_comes_back_when_the_player_has_control(core):
    """The chain ends when the player can move, and there it is restored."""
    sess = Session(core)
    sess.until("control", lambda: not sess.running_a_page()
               and not sess.byte("waiting_n"), 300)
    sess.put_byte("jumps_left", 0)
    sess.advance()
    assert sess.byte("jumps_left") == sess.symbol("JUMPS_MAX"), (
        "the budget was not restored with the player in control: a long game "
        "runs out of teleports")


def test_the_dispatcher_gets_you_out(core):
    """Entering the lookout with 1430 on, as a door would, and getting out.

    If that teleport is lost, the page ends, 1430 stays on and —being
    automatic— it starts again on its own: the player is locked in with no
    control. This does not fail on its own with the budget broken —a door
    restores it—: what it covers is that the path exists and ends where it
    has to end. The one that catches the budget is the one above."""
    sess = Session(core, switches=[DISPATCHER])
    sess.go_to_map(LOOKOUT, 10, 7)
    sess.until("out of the lookout", lambda: sess.map_() == CLEARING, 600)
    assert sess.cell() == (10, 7)


def test_nobody_panics(core):
    """The cap is not reached by playing. If this fails, the ROM stopped on
    its own."""
    sess = Session(core)
    sess.run(600)
    assert not sess.byte("panic"), "the ROM panicked with code %d" % sess.byte("panic")

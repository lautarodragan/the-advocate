"""A parallel page that teleports goes on to its next command.

RM2k and RM2k3 do not stop a parallel page at its `Teleport`: the jump is
reserved, and the page keeps running in the same frame until it waits or
ends —`Game_Interpreter_Map::CommandTeleport` in easyrpg-player, "parallel
events should keep on running in 2k and 2k3"—. The map changes at the end
of the frame and the parallel is gone with the old map, but what it did
until then stays done. Zounds' guard scene, on its map 7, is such a page:
it tints the screen black, jumps, and tints it back. Until 2026-10-16 the
console ended the frame at the `Teleport`, as it does for the foreground,
so the map load threw the parallel's cursor away with the tint back still
to run, and the next map stayed black with the player in control.

The meadow, `src/maps/Map0001.json`, has "Jump Away" (id 10), whose only
page is parallel on switch 1400: it tints the screen black waiting for it,
teleports to the clearing —map 4—, tints it back without waiting, turns
1401 on and 1400 off. The case `parallel-teleport` turns 1400 on. Zounds'
tint back waits, and that is fine there: the tint is already asked for
when the frame ends, and only what comes after the wait is lost with the
old map, in RM2k too; here the switch has to come in the same frame. 1400
goes off last, and
not first: turning off its own switch changes the event's page, which ends
the parallel at the refresh after its frame —see `parallel_tick` in the
runtime—, and the jump would never come.

Seen red with the tools before the change: the game arrives at the
clearing black, and 1401 stays off.
"""

from game import Session

CLEARING = 4
ASKED = 1400        # the page's condition, which the case turns on
AFTER_JUMP = 1401   # the page's last command, after its Teleport


def test_a_parallel_page_runs_past_its_teleport(core):
    sess = Session(core, case="parallel-teleport")
    sess.until("on map %d with control" % CLEARING,
               lambda: sess.map_() == CLEARING and sess.has_control(), 600)
    # The tint back is half a second: well done after 60 ticks.
    for _ in range(60):
        sess.advance()
    assert sess.map_() == CLEARING, "the game left the clearing"
    assert sess.switch(AFTER_JUMP), (
        "the parallel page stopped at its Teleport: what came after it "
        "never ran")
    assert not sess.switch(ASKED), "the parallel page did not reach its end"
    pixels = sess.image().convert("RGB").get_flattened_data()
    assert max(max(p) for p in pixels) > 64, (
        "the clearing is black: the tint back after the jump did not run")

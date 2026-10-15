"""A map with no events at all, the clearing —map 4—, reached by the
`Teleport` of case `empty-map`: it arrives and draws.

Every map of the other three has some event, and so does every map of the
ports, so a map with `ev_total` at zero ran nowhere until the test game's
garden was first drawn without its villager. Then the refresh that picks
each event's page cleared its table with a loop that stored before it
tested the limit, ran round the whole bank, and left every byte of WRAM
bank 0 at $FF fifteen frames after `map_current` changed: a black screen,
in snes9x and in bsnes. See `pick_with_filter`, in `runtime/event_pages.s`,
and tasks/a-map-with-no-events-wipes-wram-when-entered.md.
"""

from game import Session, golden

CLEARING = 4
# Where the case's Teleport leaves the hero.
ARRIVAL = (10, 7)


def test_a_map_with_no_events_arrives_and_draws(core):
    sess = Session(core, case="empty-map")
    sess.until("on map %d with control" % CLEARING,
               lambda: sess.map_() == CLEARING and sess.has_control(), 600)
    # A few ticks more, so the map is drawn whole and the hero is up.
    for _ in range(30):
        sess.advance()
    assert sess.map_() == CLEARING, "the game left the clearing"
    assert sess.cell() == ARRIVAL, "the hero is at %s" % (sess.cell(),)
    golden("clearing", sess.image(), core)

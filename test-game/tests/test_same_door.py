"""A door to the same map does not reload the map.

Reloading reads the events' positions from the cartridge again, and with
that everything that moved them is lost —a `ChangeEventLocation`, a
`TradeEventLocations`— even though the player never left the map. It is the
`map_changed` of `Game_Player::PerformTeleport`: without a change of map
there is no `Setup`.

The doors, map 12, has two rooms the bushes split, crossed only by
teleports to the same map. Its door, event 1, stands in the bushes' gap on
the hero's layer; A on it turns 1440 on, moves the door out of the way, to
(1, 1), and the marker, event 2, to the corner, (18, 13). Then the gap's
touch page, event 3, leads up into the top room, and event 4, by the top
room's wall, back down in front of the door.

taro reported it on A Blurred Line's map 2 on 2026-09-07: the way there was
a `Teleport` and kept what had moved, and the way back a **door** —a touch
page whose only command is the teleport—, which always reloaded, and the
opened door's stripes came back. It came from that game's suite, in the
ports, on 2026-11-22.
"""

from rm2k_snes_harness import Session

DOORS = 12
EV_DOOR, EV_MARKER = 0, 1           # indices, from zero
DOOR_AWAY, MARKER_AWAY = (1, 1), (18, 13)
IN_FRONT = (10, 8)                  # below the door, facing it
TOP_ROOM = (15, 3)                  # where the gap leads
BACK = (10, 9)                      # where the top room's wall leads


def walk(sess, button, target, limit=200):
    """Holds `button` until the hero stands on `target`."""
    for _ in range(limit):
        if sess.cell() == target and not sess.byte("fade"):
            sess.run(2)
            return True
        sess.advance(button)
    return sess.cell() == target


def opened(core):
    """A game with the door opened, standing in front of it."""
    sess = Session(core)
    sess.go_to_map(DOORS, *IN_FRONT)
    sess.put_byte("hero_dir", sess.symbol("DIR_UP"))
    sess.press("a")
    sess.until("the door's page", lambda: sess.switch(1440) and sess.has_control(), 120)
    return sess


def test_opening_it_moves_the_events(core):
    """First what has to happen when opening it, or the rest proves nothing."""
    sess = opened(core)
    assert sess.event(EV_DOOR) == DOOR_AWAY, "the door did not move out of the way"
    assert sess.event(EV_MARKER) == MARKER_AWAY, "the marker did not go to the corner"


def test_crossing_it_and_coming_back_leaves_it_open(core):
    sess = opened(core)
    assert walk(sess, "up", TOP_ROOM), "the door could not be crossed: at %s" % (sess.cell(),)
    assert sess.map_() == DOORS
    assert sess.event(EV_MARKER) == MARKER_AWAY, (
        "crossing already resets the events; the teleport there should keep them")
    assert walk(sess, "up", BACK), "could not come back: at %s" % (sess.cell(),)
    assert sess.event(EV_MARKER) == MARKER_AWAY, (
        "coming back through the door reloaded the map: the marker went back "
        "to %s" % (sess.event(EV_MARKER),))
    assert sess.event(EV_DOOR) == DOOR_AWAY, (
        "coming back through the door reloaded the map: the door is closed again")

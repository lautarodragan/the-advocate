"""Switches past 1023: set, branched on and asked for by a page.

Until 2026-10-15 the ROM's switch table was 128 bytes for every game
—switches 0 to 1023—: a `ControlSwitches` past it compiled and wrote into
whatever RAM followed the table, a page condition past it read that RAM,
and a branch on one did not compile. Vampires Dawn names up to 1643 and The
Frozen World up to 1077. Now the table is the game's, sized by the highest
switch it names —see `switch_top` in the event compiler—, in far RAM.

The meadow, `src/maps/Map0001.json`, has an invisible event at (1,1) whose
only page, parallel, asks for switch 1100 and turns on 1101. The case
`switches-past-1023` waits, checks that 1101 is still off —turning on 1103
if it is not—, turns on 1100 and branches on it to turn on 1102.

It lived in A Blurred Line until 2026-10-15, with a fork of that game's map
348 that brought the event: that game names none past 1008. There it was
seen red with the tools before the change: the branch on 1100 did not
compile, so neither did the case's page, and the cartridge did not build.
"""

from game import Session

CASE = "switches-past-1023"
ASKED = 1100        # the page condition's, set by the case
BY_THE_PAGE = 1101  # what the page on 1100 turns on
BRANCHED = 1102     # what the branch on 1100 turns on
TOO_EARLY = 1103    # the page ran before its switch was on


def test_switches_past_1023(core):
    sess = Session(core, case=CASE)
    # The case's `Wait` is a second —RM2k counts it in tenths—, and the case
    # ends around tick 60 and the page on 1100 runs a few later: twice that
    # leaves both done, and a page that never runs has had time to.
    for _ in range(120):
        sess.advance()
    assert sess.symbol("SWITCH_BYTES") > TOO_EARLY // 8, (
        "the table does not hold the case's switches: SWITCH_BYTES is %d"
        % sess.symbol("SWITCH_BYTES"))
    assert sess.switch(ASKED), "the ControlSwitches on 1100 did not turn it on: did the page compile?"
    assert sess.switch(BRANCHED), "the branch on 1100 did not see it on"
    assert not sess.switch(TOO_EARLY), "the page that asks for 1100 ran with 1100 off"
    assert sess.switch(BY_THE_PAGE), "the page that asks for 1100 did not run with it on"

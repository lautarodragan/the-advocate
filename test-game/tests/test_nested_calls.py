"""A chain of CallEvents, six deep, that returns to each caller and goes on.

Until 2026-10-15 a `CallEvent` to a map event's page was pasted into the
caller, four levels deep at most (`CALL_MAX` in the event compiler): the
calls past that were skipped without a word, and Frozen World's battle
screen, whose pages call the same pages dozens of times, came to four
megabytes of bytecode. Now it is `OP_CALL_PAGE`: the page's own bytes run
from where the map's page table points, the caller's place goes on the
interpreter's call stack, and the callee's `OP_DONE` comes back to it. The
stack has `CALL_LEVELS` entries, eight; see `common_events.s` in the
runtime.

The meadow, `src/maps/Map0001.json`, has six invisible events at column 18,
"Chain 1" to "Chain 6" (ids 3 to 8), each turning a switch on, calling the
next one's page and turning another on after the call; the third also
calls common event 1, `Deep Wait`, which waits a second between its two
switches; the sixth waits a second too, and notes if an outer caller's
"after" switch is already on. The case `nested-calls` is the first caller.
"Every Frame" (id 9) is a parallel page that turns a switch on every frame
while the chain waits: the stack is the foreground's, and its `OP_DONE`
must end its own page and not return into the chain.

Seen red with the tools before the change: the fourth call —Chain 4's to
Chain 5— was past `CALL_MAX`, so 1260 and 1270 stayed off.
"""

from game import Session

CASE = "nested-calls"
# Each frame's "before", in the order the frames are entered, and its
# "after", in the order they are left.
BEFORE = [1200, 1210, 1220, 1230, 1240, 1250, 1260]
AFTER = [1201, 1211, 1221, 1231, 1241, 1251, 1261]
DEEPEST = 1270      # Chain 6 ran to its end
TOO_EARLY = 1271    # an outer "after" was on when Chain 6 started
EVERY_FRAME = 1280  # the parallel page ran


def test_nested_calls_return_and_go_on(core):
    sess = Session(core, case=CASE)
    # Two `Wait`s of a second inside the chain, and a tick is a frame or
    # two: the chain is done well before 300.
    for _ in range(300):
        sess.advance()
    assert not sess.byte("ev_active"), "the case's page is still running after 300 ticks"
    for switch in BEFORE:
        assert sess.switch(switch), "switch %d is off: a frame of the chain did not start" % switch
    assert sess.switch(DEEPEST), "Chain 6 did not run to its end: a call was skipped"
    assert not sess.switch(TOO_EARLY), "an outer caller went on before its callee ended"
    for switch in AFTER:
        assert sess.switch(switch), "switch %d is off: a call did not return to its caller" % switch
    assert sess.switch(EVERY_FRAME), "the parallel page did not run while the chain waited"
    assert sess.byte("call_depth") == 0, "the call stack was not unwound: depth %d" % sess.byte("call_depth")

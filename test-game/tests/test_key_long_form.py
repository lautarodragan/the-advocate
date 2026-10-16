"""`KeyInputProc` in RM2k 1.50's long form: ten parameters, each direction
on its own, which is the same program as the short one when the four are
asked for alike.

Until 2026-10-16 the compiler took the five-parameter form only —the one
every game of the survey but Zounds writes— and a page with the long one
was left out. Zounds, an RPG Maker 2003 game, writes the fourteen of that
engine's 1.05, and its intro waited on map 106 for a key read by a common
event left out for it; the 2003 layout cannot be written in a 2000 game,
so it is covered by the compiler's unit tests and by Zounds' boot, and the
ROM side —the same bytes as the short form— by this.

The case `key-long-form` loops on a `KeyInputProc` that waits for any key,
with the ten parameters, and turns on 1310 for the action key, 1311 for
cancel and 1312 for down, which also ends the loop.

Before the change the case did not compile, and with it neither did the
cartridge: red by construction.
"""

from game import Session

CASE = "key-long-form"
DECISION = 1310
CANCEL = 1311
DOWN = 1312


def test_the_long_form_reads_the_same_keys(core):
    sess = Session(core, case=CASE)
    # The first turn of the waiting form eats the edge that is there and
    # looks from the next frame on: a few ticks with nothing pressed, then
    # one key at a time, with a release in between so each is an edge.
    for _ in range(6):
        sess.advance()
    assert not sess.switch(DECISION) and not sess.switch(CANCEL) and not sess.switch(DOWN), (
        "a switch came on before any key was pressed")
    sess.press("a")
    for _ in range(4):
        sess.advance()
    assert sess.switch(DECISION), "the action key was not read as 5"
    assert not sess.switch(CANCEL) and not sess.switch(DOWN)
    sess.press("b")
    for _ in range(4):
        sess.advance()
    assert sess.switch(CANCEL), "cancel was not read as 6"
    assert not sess.switch(DOWN)
    sess.press("down")
    for _ in range(4):
        sess.advance()
    assert sess.switch(DOWN), "down was not read as 1"

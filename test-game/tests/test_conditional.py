"""`ConditionalBranch`: the branch that runs and the one that is skipped.

**The branch that runs** needs the switch that decides it on before the
page: the case `branch` branches on 1420, and the tester offers it twice,
`branch` with 1420 off and `branch-switched` with it on —see `hub.toml`—.
Inside, 1421; after the `end`, always, 1422.

**The branch that is skipped** has two halves: that it does not run, and
that the page **goes on after the `end`** —an implementation that skips too
much leaves what follows undone—. The case `branch-skipped` has the shape
of A Blurred Line's map 52, event 1, page 1, the entrance to its chase,
which is where this was tested until 2026-11-22: two branches on switches
nobody turned on, each adding an actor to the party and walking the hero,
the first with an empty `else`; a walk after both; and 1425 last.
"""

from play import playing

INSIDE, AFTER = 1421, 1422
SKIPPED_END = 1425
# Who the skipped branches would have added: Alda and Bram.
WOULD_COME = (2, 3)


def test_the_branch_runs_with_the_switch_on(core):
    sess = playing(core, "branch-switched")
    sess.run(30)
    assert sess.switch(INSIDE), "the inner branch did not run"
    assert sess.switch(AFTER), "the page did not go on after the `end`"


def test_the_branch_does_not_run_with_the_switch_off(core):
    sess = playing(core, "branch")
    sess.run(30)
    assert not sess.switch(INSIDE), "the branch ran with the switch off"
    assert sess.switch(AFTER), "the page did not go on after the `end`"


def test_the_skipped_branches_leave_the_page_going_on(core):
    sess = playing(core, "branch-skipped")
    sess.until("the page's end", lambda: sess.switch(SKIPPED_END), 300)
    for actor in WOULD_COME:
        assert actor not in sess.party(), (
            "a branch ran with its switch off: %d came into the party" % actor)

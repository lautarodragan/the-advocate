"""`Label` and `JumpToLabel`: the jump is resolved at compile time and is an
`OP_GOTO`.

The case `labels` does, in order:

* a loop backwards: variable 40 goes up one at a time, and while it is less
  than 3 a branch jumps to label 1, from inside the branch to the outside;
* a jump forwards, to 2, over switch 1410;
* a jump to 9, which the page does not have: in RM2k it does nothing, and
  goes on;
* and a jump to 3, which is **inside the `else`** of a branch that would
  give true —it is what A Blurred Line's common event 39, the portable
  console, does—: it runs the body of the `else` and not the one above.

It came from that game's suite, in the ports, on 2026-11-22. Without the two
commands in the compiler, the whole page did not compile and turned
nothing on: seen red like that, there.
"""

from rm2k_snes_harness import Session

SKIPPED = 1410   # the one the jumps dodge
GOES_ON = 1411   # after the jump to a label that is not there
ELSE = 1412      # the body of the `else`, entered by jumping
END = 1413       # the last thing on the page


def test_the_jumps_to_labels(core):
    sess = Session(core, case="labels")
    sess.run(30)
    assert sess.switch(END), "the page did not reach the end: did it compile?"
    assert sess.variable(40) == 3, "the loop backwards did not give three passes"
    assert not sess.switch(SKIPPED), (
        "a jump did not dodge the switch: either the forward one landed before "
        "its label, or the else one ran the body above")
    assert sess.switch(GOES_ON), "the jump to a label that is not there cut the page"
    assert sess.switch(ELSE), "the jump inside the else did not run its body"

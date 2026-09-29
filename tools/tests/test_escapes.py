"""RM2k's two text escapes, `\\|` and `\\^`, on the Python side.

The box is compiled by `rm2k-snes-events`, which cuts the escape tail off and
puts it in the box's header. The converter keeps its own `escape_tail`, in
`port/events.py`, because `texts.py` rebuilds the game's boxes for the
window before the compiler sees them, and has to know which part of the
last line is the tail. Two copies of one rule: this and the crate's
`tests/escapes.rs` read the same cases, `rm2k-snes/events/tests/escapes.json`,
so one changed alone goes red on its side.

That the message pauses and closes by itself is enforced by `autocierre` and
`autocierre-3` in `test_comandos_golden.py`, which compare pixels; that two
boxes with the same text and another tail are two, by the crate.
"""

import json
import os

import pytest

from common import project
from port import events

FIXTURE = os.path.join(project.tools(), "rm2k-snes", "events", "tests",
                       "escapes.json")


def _cases():
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)["cases"]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: repr(c["lines"]))
def test_the_tail_is_the_compilers(case):
    try:
        lines, pauses, auto_close = events.escape_tail(case["lines"])
        got = [list(lines), pauses, auto_close]
    except events.CannotCompile:
        got = None
    assert got == case["answer"]

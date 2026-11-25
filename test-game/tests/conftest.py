"""What every test of the test game shares: the game, and the two cores.

The harness is the tools' generic one, `rm2k-snes/harness/`, which
`pytest.ini` puts on the path; what is the test game's is said here, once:
where it is, and where its goldens are. What its last build left, the
harness reads from `build/advocate.json`.
"""

import os

import pytest

from rm2k_snes_harness import BSNES, SNES9X, Game, use

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)


# The captures that came out red go to `snapshots/`, to look at them: not
# versioned.
use(Game(ROOT, goldens=os.path.join(TESTS, "golden"),
         snapshots=os.path.join(TESTS, "snapshots")))


@pytest.fixture(params=[SNES9X, BSNES], ids=["snes9x", "bsnes"])
def core(request):
    """snes9x, which the goldens are taken with, and bsnes, which starts
    with WRAM full of garbage: a red only in bsnes is memory nobody
    initialised."""
    if not os.path.exists(request.param):
        pytest.skip("no libretro core at %s" % request.param)
    return request.param

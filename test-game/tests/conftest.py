"""What every test of the test game shares: the two cores."""

import os

import pytest

from game import BSNES, SNES9X


@pytest.fixture(params=[SNES9X, BSNES], ids=["snes9x", "bsnes"])
def core(request):
    """snes9x, which the goldens are taken with, and bsnes, which starts
    with WRAM full of garbage: a red only in bsnes is memory nobody
    initialised."""
    if not os.path.exists(request.param):
        pytest.skip("no libretro core at %s" % request.param)
    return request.param

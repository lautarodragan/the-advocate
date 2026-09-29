"""The cap of the `TileSubstitution` table is written on both sides.

And it has to be: the ROM **cannot warn** that it was exceeded —the pairs
that do not fit would simply not be applied, and the map would draw extra
without anything saying so—, so the one that refuses to emit a map that does
not fit is the converter. That makes two numbers, and two numbers written in
two places is what this repo already got burned by with the opcodes; here one
cannot be generated from the other —the BSS `.res` and the converter's
cutoff share nothing— so what is left is comparing them.
"""

import os
import re

from port import snes_convert                            # noqa: E402
from common import project  # noqa: E402
from assembly import assemble  # noqa: E402

MAIN = os.path.join(project.runtime(), "main.s")


def from_main(nombre):
    fuente = assemble.source_text(MAIN)
    hallado = re.search(r"^%s\s*=\s*(\d+)\s*$" % nombre, fuente, re.M)
    assert hallado, "tools/runtime/ no longer declares %s" % nombre
    return int(hallado.group(1))


def reservation(nombre):
    fuente = assemble.source_text(MAIN)
    hallado = re.search(r"^%s:\s*\.res\s+([^;\n]+)" % nombre, fuente, re.M)
    assert hallado, "tools/runtime/ no longer reserves %s" % nombre
    return hallado.group(1).strip()


def test_the_table_cap_is_the_same_on_both_sides():
    assert from_main("SUB_MAX") == snes_convert.SUB_MAX


def test_the_rom_table_is_as_long_as_the_cap_says():
    """Two words per pair, keys and values in parallel arrays: that is how
    `cell_replaced` walks them with a single index."""
    assert reservation("sub_clave") == "SUB_MAX * 2"
    assert reservation("sub_valor") == "SUB_MAX * 2"

"""`StoreTerrainID`: a cell's terrain, stored in a variable.

The terrain is not seen, so no golden would charge it: the ROM is asked its
far RAM, as in `test_variables.py`.

**The map is the showcase, and not at random**: its ChipSet, 2, gives its
first lower tiles —5000 to 5003, at (0, 0) to (3, 0)— four different
terrains, and the first water, the ChipSet's entry 0, a fifth. Every other
ChipSet entry is terrain 1, which is also what a ChipSet **without** a
terrain table answers —the RPG_RT optimisation `GetTerrainTag` documents—,
so a case on a cell of terrain 1 would be green with the table read
backwards.

The expected values are not written down: they come from the game's dump
—the map's `.tiles` and the ChipSet's `terrain_data`— with
`rm2k.terrain_of`, the same rule the table the ROM carries came from. What
this compares is that the whole path —converter, bytecode, interpreter and
the bank 1 table— returns what the game says. It came from A Blurred Line's
suite, in the ports, on 2026-11-22, where it looked at that game's map 5.
"""

import json
import os
from types import SimpleNamespace

import pytest

from rm2k_snes_harness import cartridge, rm2k

from play import playing

SHOWCASE = 3
# Which cell the case asks about and in which variable it leaves the answer.
CELLS = (((0, 0), 17), ((1, 0), 19), ((2, 0), 20), ((3, 0), 21))
# The one that falls outside the map, which is another answer and not an
# error: RPG_RT answers the terrain of the **ChipSet's first tile**.
OUTSIDE = 39
# And the one the case asks for with the cell in two variables —the
# `ValueOrVariable` of `CommandStoreTerrainID`—: (1, 0) again, the same
# answer by the other path.
BY_VARIABLE = (1, 0), 40


@pytest.fixture(scope="module")
def of_the_game():
    """The showcase's lower layer and its ChipSet, from the dump the
    cartridge was converted from."""
    dump = cartridge().dump
    with open(os.path.join(dump, "maps", "Map%04d.json" % SHOWCASE)) as file:
        game_map = json.load(file)
    with open(os.path.join(dump, "maps", "Map%04d.tiles" % SHOWCASE)) as file:
        lines = [line for line in file.read().split("# upper")[0].splitlines()
                 if line.strip() and not line.startswith("#")]
    lower = [int(n) for line in lines for n in line.split()]
    assert len(lower) == game_map["width"] * game_map["height"]
    with open(os.path.join(dump, "db", "chipsets.json")) as file:
        chipset = next(c for c in json.load(file) if c["id"] == game_map["chipset_id"])
    return game_map["width"], lower, SimpleNamespace(terrain=chipset["terrain_data"])


def terrain_at(of_the_game, cell):
    width, lower, chipset = of_the_game
    x, y = cell
    return rm2k.terrain_of(chipset, lower[y * width + x])


@pytest.fixture(scope="module", params=["snes9x", "bsnes"])
def sequence(request):
    from rm2k_snes_harness import BSNES, SNES9X
    core = SNES9X if request.param == "snes9x" else BSNES
    if not os.path.exists(core):
        pytest.skip("no libretro core at %s" % core)
    sess = playing(core, "terrain")
    sess.until_control()
    return sess


@pytest.mark.parametrize("cell,variable", CELLS, ids=["%d-%d" % c for c, _v in CELLS])
def test_the_cells_terrain_is_the_games(sequence, of_the_game, cell, variable):
    expected = terrain_at(of_the_game, cell)
    assert sequence.variable(variable) == expected, (
        "cell %s of the showcase has terrain %d in the game" % (cell, expected))


def test_the_cells_four_terrains_are_not_the_same(of_the_game):
    """Without this, the cases above could pass reading anything: a whole
    table at 1 answers them right."""
    distinct = {terrain_at(of_the_game, cell) for cell, _v in CELLS}
    assert len(distinct) == len(CELLS), (
        "the case's cells no longer have four different terrains but %s"
        % sorted(distinct))


def test_outside_the_map_answers_the_first_tiles(sequence, of_the_game):
    """`GetTerrainTag` does not crash nor answer the nearest cell's: it uses
    the ChipSet's index 0, which here is not 1."""
    _width, _lower, chipset = of_the_game
    assert rm2k.terrain_of(chipset, 0) != 1
    assert sequence.variable(OUTSIDE) == rm2k.terrain_of(chipset, 0)


def test_the_cell_by_variable_gives_the_same_as_written(sequence, of_the_game):
    """Mode 1 reads x and y **at run time**, and it has to give the same as
    mode 0 on the same cell."""
    cell, variable = BY_VARIABLE
    assert sequence.variable(variable) == terrain_at(of_the_game, cell)

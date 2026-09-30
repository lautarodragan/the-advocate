"""The map as indices into a table of 16x16 blocks, each one with its four
BG1 cells, its four BG2 cells and its passability; and `TileSubstitution`
translated from RM2k tiles to those blocks.
"""

from port import events
from rpgmaker import rm2k


# What is stored in the ROM isn't the expanded tilemap: the ROM redraws the
# tilemap window of `vram.py` from something smaller. An RM2k 16x16
# cell is four SNES 8x8 cells, and it is the unit the game was drawn with: it
# repeats a lot. Storing an index into a table of blocks, the heaviest map
# goes from 175 KB —more than the whole ROM— to 40.
#
# The block carries both layers together and the passability. Passability
# going into the block isn't free: two cells that are drawn the same could
# have different permissions if they came from different ChipSet tiles, so it
# goes in the key and they separate by themselves.
BLOCK_BYTES = 16                # four BG1 cells and four BG2 cells


# The block table is read with `lda tabla, x`, that is it lives in bank 0
# together with the code.
MAX_BLOCKS = 1024


# How many block pairs the ROM's substitution table can hold at once. It is
# `SUB_MAX` in tools/runtime/low_ram.s and it is written on both sides on
# purpose —the converter has to be able to refuse **before** emitting a map
# that doesn't fit—; the test `test_sustitucion.py` compares the two.
SUB_MAX = 8


class Substitutions:
    """`TileSubstitution` translated from RM2k tiles to ROM blocks.

    RM2k substitutes by **tile number**: every cell of the map that draws the
    old tile starts drawing the new one. In the ROM there are no RM2k tiles,
    there are 16x16 blocks that carry both layers and the passability
    together, so an RM2k substitution is as many block pairs as (lower, upper)
    combinations of the map carry that tile. Which ones they are is known when
    converting, which is why this lives here and not in `events.py`.

    The destination block may not exist —nobody drew that combination
    anywhere in the map— and then it is built: the four 8x8 cells of the layer
    that changes come from another block that already draws the new tile,
    those of the other layer come from the source block, and the passability
    is recomputed with the same RM2k rules. That is where the only real limit
    of this comes from: **the new tile has to be drawn in some cell of the
    map**, on its layer. If it isn't, its 8x8s didn't go into VRAM and there
    is nothing to draw it with; the page doesn't compile and it says why.

    All the blocks are built **before** compiling any page, and not as the
    commands show up: substitutions chain —turning on is 80→80A and turning
    off is 80A→80— so the block one needs is created by another, and the
    order the pages are compiled in can't decide what compiles.
    """

    def __init__(self, map_info, flags, chipset):
        self.map_info = map_info
        self.flags = flags
        self.chipset = chipset
        self.combos = map_info["combos"]
        # The four 8x8 cells each RM2k tile is drawn with, per layer. They come
        # from the blocks that already exist: a tile the map doesn't draw
        # anywhere isn't here and can't be substituted into.
        self.cells = ({}, {})
        for (low, height), block in self.combos.items():
            # **The lower half is only usable if the upper tile of that block
            # isn't baked into it.** An upper-layer tile **without** the
            # "Above" bit isn't drawn on BG2 but over the background —that is
            # what `rm2k-render` decides, and that is why there are upper tiles
            # whose BG2 half comes out empty—, so the lower half of that block
            # is the composition of the two and not the lower tile alone.
            # Copying it to build another combination would draw the
            # neighbor's upper tile.
            if not self._bakes(height):
                self.cells[0].setdefault(low, self._half(block, 0))
            self.cells[1].setdefault(height, self._half(block, 1))
        # The blocks some substitution of the map uses as a key, which is what
        # is going to take room in the RAM table.
        self.known_keys = set()
        # And the blocks by content, to deduplicate the ones built the same way
        # `build_blocks` deduplicates the map's. It isn't to save room: two
        # combinations that already share a block —the two water autotiles of
        # map 6 draw the same thing— have to keep sharing it after
        # substituting, or the substitution would send a single block to two
        # places and couldn't be expressed.
        self.by_bytes = {}
        for block in range(len(map_info["pass"])):
            self.by_bytes.setdefault(self._fingerprint(block), block)

    def _bakes(self, height):
        """Whether that upper-layer tile is baked into the background instead
        of going to BG2.

        It is the computation `rm2k-render` draws with: an upper tile goes above the hero
        —that is, to BG2— only with the `Above` bit set, and without it it is
        drawn stuck to the background. The empty tile draws nothing and bakes
        nothing.
        """
        return (height != rm2k.UPPER_BASE
                and not self.flags[height] & rm2k.PASS_ABOVE)

    def _half(self, block, layer):
        first = block * BLOCK_BYTES + layer * 8
        return bytes(self.map_info["bloques"][first:first + 8])

    def _fingerprint(self, block):
        first = block * BLOCK_BYTES
        return (bytes(self.map_info["bloques"][first:first + BLOCK_BYTES]),
                self.map_info["pass"][block], self.map_info["terreno"][block])

    def _combo(self, high_layer, old, new):
        """The RM2k ids of the tile that goes out and the one that comes in."""
        base = rm2k.UPPER_BASE if high_layer else rm2k.LOWER_BASE
        return base + old, base + new

    def pure_pairs(self, high_layer, old, new):
        """The `(old block, new block)` pairs of a substitution, or None.

        None is "this page doesn't compile", which is what `events.py`
        expects from a command that can't be done.
        """
        if not (0 <= old < rm2k.TILES_PER_LAYER
                and 0 <= new < rm2k.TILES_PER_LAYER):
            return None
        layer = 1 if high_layer else 0
        old_id, new_id = self._combo(high_layer, old, new)
        out, seen = [], {}
        for combination, block in sorted(self.combos.items()):
            if combination[layer] != old_id:
                continue
            dest = list(combination)
            dest[layer] = new_id
            new_block = self.combos.get(tuple(dest))
            if new_block is None:
                return None     # `close` should have created it
            if seen.setdefault(block, new_block) != new_block:
                # Two distinct combinations that draw the same and have the
                # same permissions share a block, and there the substitution
                # can't be expressed: the block would have to go two ways. It
                # doesn't happen with any ChipSet of the game —drawing the
                # same means being the same tile— but if it did, substituting
                # would change cells RM2k doesn't touch.
                return None
            out.append((block, new_block))
        if len(out) > 0xFF:
            return None         # the count operand is one byte
        return out

    def pairs(self, high_layer, old, new):
        """`pure_pairs`, and the keys it uses are counted: a page asked
        for it. See `known_keys`."""
        out = self.pure_pairs(high_layer, old, new)
        if out is not None:
            self.known_keys.update(pair[0] for pair in out)
        return out

    def close(self, triples):
        """Builds the blocks that are going to be needed, and returns what
        couldn't be done.

        `triples` are the `(upper layer, old, new)` of all the map's
        `TileSubstitution`s. It repeats until none creates a new block,
        because the block one creates is the source of the next.
        """
        missing = []
        while True:
            before = len(self.combos)
            for high_layer, old, new in triples:
                if not (0 <= old < rm2k.TILES_PER_LAYER
                        and 0 <= new < rm2k.TILES_PER_LAYER):
                    continue
                layer = 1 if high_layer else 0
                old_id, new_id = self._combo(high_layer, old, new)
                if new_id not in self.cells[layer]:
                    if (high_layer, old, new) not in missing:
                        missing.append((high_layer, old, new))
                    continue
                for combination in sorted(self.combos):
                    if combination[layer] != old_id:
                        continue
                    dest = list(combination)
                    dest[layer] = new_id
                    if self._create(tuple(dest)) is None \
                            and (high_layer, old, new) not in missing:
                        missing.append((high_layer, old, new))
            if len(self.combos) == before:
                return missing

    def _create(self, combination):
        """The block of a combination the map doesn't draw anywhere.

        None is "this combination can't be built without drawing the map
        again". It happens when the upper tile is baked into the background:
        then the two halves of the block aren't independent and there is
        nowhere to take the lower one from. See `_bakes`.
        """
        if combination in self.combos:
            return self.combos[combination]
        low, height = combination
        if self._bakes(height) or low not in self.cells[0] \
                or height not in self.cells[1]:
            return None
        fingerprint = (self.cells[0][low] + self.cells[1][height],
                       rm2k.cell_passability(self.flags, low, height),
                       rm2k.terrain_of(self.chipset, low))
        number = self.by_bytes.get(fingerprint)
        if number is None:
            number = len(self.map_info["pass"])
            if number >= MAX_BLOCKS:
                raise SystemExit(
                    "map %d goes over %d blocks building the ones "
                    "`TileSubstitution` needs"
                    % (self.map_info["id"], MAX_BLOCKS))
            self.map_info["bloques"] += fingerprint[0]
            self.map_info["pass"].append(fingerprint[1])
            self.map_info["terreno"].append(fingerprint[2])
            self.by_bytes[fingerprint] = number
        self.combos[combination] = number
        return number


def substitution_triples(game_map, cases, map_id):
    """The `(upper layer, old, new)` of all the `TileSubstitution`s that can
    end up running in this map: those of its events and those of the test
    cases that start here —which live in the boot map but are compiled with
    this one's context, see `case_map`—."""
    triples = []
    lists = [page.commands
             for event in game_map.events for page in event.pages]
    lists += [case.commands for case in cases if case.run_map == map_id]
    for commands in lists:
        for cmd in commands:
            if cmd.code != events.TILE_SUBSTITUTION or len(cmd.parameters) < 3:
                continue
            triple = (bool(cmd.parameters[0]),
                      cmd.parameters[1], cmd.parameters[2])
            if triple not in triples:
                triples.append(triple)
    return triples

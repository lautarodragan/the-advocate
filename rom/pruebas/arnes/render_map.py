"""The game as the tests read it: its database, its map tree, a map with
its ChipSet's name and passability, and where the pictures are looked up.

It was the converter's `Renderer`, in `render/`, until the converter
moved to Rust on 2026-10-02. Nothing is drawn from here: the tests that
need a map's layers, its sprites or a screen ask the stages for them.
"""

import os

from common import project
import lcf
import resources


def build_passability(chipset):
    """Table of flags per tile ID, as lmu2png builds it (main.cpp): one
    entry per family for the autotiles, one per tile for the plain ones."""
    flags = bytearray(65536)
    lower, upper = chipset.passable_lower, chipset.passable_upper

    for i in range(3):          # water A/B/C
        flags[1000 * i:1000 * i + 1000] = bytes([lower[i]]) * 1000
    for i in range(3):          # animated tiles
        flags[3000 + i * 50:3050 + i * 50] = bytes([lower[3 + i]]) * 50
    for i in range(12):         # terrain autotiles
        flags[4000 + i * 50:4050 + i * 50] = bytes([lower[6 + i]]) * 50
    for i in range(144):        # common tile pages
        flags[5000 + i] = lower[18 + i]
        flags[10000 + i] = upper[i]
    return flags


class Renderer:
    """Everything shared between maps: the game, the RTP and where the
    pictures are."""

    def __init__(self, game_dir=None, rtp_dir=None):
        game_dir = game_dir or resources.GAME_DIR
        rtp_dir = rtp_dir or resources.RTP_DIR
        self.database = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
        self.tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
        self.game_dir = game_dir
        # The images of the ChipSets `rom/parches/manual/` adds go first:
        # the converter builds them into the build, from their recipe.
        self.search_dirs = [os.path.join(project.build(), "parches-manual"),
                            project.root(), game_dir, rtp_dir]

    def load_map(self, path):
        """The map, with its chipset's name set and the passability of its
        tiles, for the events drawn with one: see `rm2k.page_graphic` and
        `rm2k.event_tile_passability`."""
        game_map = lcf.Map(path)
        chipset = self.database.chipsets[game_map.chipset_id]
        game_map.chipset_filename = chipset.filename
        game_map.passability_table = build_passability(chipset)
        return game_map

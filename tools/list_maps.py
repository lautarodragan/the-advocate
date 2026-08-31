#!/usr/bin/env python3
"""Lista los mapas de A Blurred Line con su chipset y si podemos renderizarlo."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
from render_map import GAME_DIR, REPO, RTP_DIR, find_resource


def main():
    database = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    tree = lcf.TreeMap(os.path.join(GAME_DIR, "RPG_RT.lmt"))
    search_dirs = [REPO, GAME_DIR, RTP_DIR]

    missing = set()
    for map_id in sorted(tree.map_names):
        path = os.path.join(REPO, "Maps", "Map%04d.lmu" % map_id)
        if not os.path.exists(path):
            continue

        game_map = lcf.Map(path)
        chipset = database.chipsets[game_map.chipset_id]
        found = find_resource(search_dirs, "ChipSet", chipset.filename)
        if not found:
            missing.add(chipset.filename)

        print("%s %4d  %-34s %4dx%-4d %s" % (
            "ok" if found else "--", map_id, tree.map_names[map_id][:34],
            game_map.width, game_map.height, chipset.filename))

    if missing:
        print("\nChipsets que faltan (RTP oficial de RM2k): %s"
              % ", ".join(sorted(missing)))


if __name__ == "__main__":
    main()

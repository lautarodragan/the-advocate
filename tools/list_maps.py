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

    missing_chipsets = set()
    missing_charsets = set()
    for map_id in sorted(tree.map_names):
        path = os.path.join(REPO, "Maps", "Map%04d.lmu" % map_id)
        if not os.path.exists(path):
            continue

        game_map = lcf.Map(path)
        chipset = database.chipsets[game_map.chipset_id]
        found = find_resource(search_dirs, "ChipSet", chipset.filename)
        if not found:
            missing_chipsets.add(chipset.filename)

        drawn = 0
        for event in game_map.events:
            page = event.active_page()
            if page is None:
                continue
            drawn += 1
            if page.character_name and not find_resource(
                    search_dirs, "CharSet", page.character_name):
                missing_charsets.add(page.character_name)

        print("%s %4d  %-34s %4dx%-4d %-22s %3d/%-3d ev" % (
            "ok" if found else "--", map_id, tree.map_names[map_id][:34],
            game_map.width, game_map.height, chipset.filename,
            drawn, len(game_map.events)))

    print("\nDel RTP oficial de RM2k, que no tenemos:")
    print("  chipsets: %s" % ", ".join(sorted(missing_chipsets)))
    print("  charsets: %s" % ", ".join(sorted(missing_charsets)))


if __name__ == "__main__":
    main()

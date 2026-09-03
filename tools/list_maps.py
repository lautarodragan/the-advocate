#!/usr/bin/env python3
"""Inventario de los mapas de A Blurred Line.

Cada mapa con su tamaño, su chipset, cuántos eventos se dibujarían y si nos
falta algún asset. Con --render además renderiza todo (sin guardar), que es la
forma barata de encontrar mapas que rompen el pipeline.
"""

import argparse
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
from render_map import GAME_DIR, REPO, Renderer, find_resource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true",
                        help="renderizar cada mapa para verificar que no rompe")
    args = parser.parse_args()

    renderer = Renderer()
    failures = []

    for map_id in sorted(renderer.tree.map_names):
        path = os.path.join(GAME_DIR, "Map%04d.lmu" % map_id)
        if not os.path.exists(path):
            continue

        game_map = lcf.Map(path)
        chipset = renderer.database.chipsets[game_map.chipset_id]
        found = find_resource(renderer.search_dirs, "ChipSet", chipset.filename)
        if not found:
            renderer.missing_chipsets.add(chipset.filename)

        drawn = 0
        for event in game_map.events:
            page = event.active_page()
            if page is None:
                continue
            drawn += 1
            if page.character_name:
                renderer.charsets.get(page.character_name)

        if args.render and found:
            try:
                renderer.render(game_map)
            except Exception:
                failures.append(map_id)
                traceback.print_exc()

        print("%s %4d  %-34s %4dx%-4d %-22s %3d/%-3d ev" % (
            "ok" if found else "--", map_id, renderer.tree.map_names[map_id][:34],
            game_map.width, game_map.height, chipset.filename,
            drawn, len(game_map.events)))

    missing = sorted(renderer.missing_chipsets), sorted(renderer.charsets.missing)
    if any(missing):
        print("\nAssets que faltan (ver README):")
        print("  chipsets: %s" % (", ".join(missing[0]) or "-"))
        print("  charsets: %s" % (", ".join(missing[1]) or "-"))
    else:
        print("\nNo falta ningún asset.")

    if args.render:
        print("Mapas que rompen: %s" % (failures or "ninguno"))
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

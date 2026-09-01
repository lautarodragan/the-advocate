#!/usr/bin/env python3
"""Imprime la ruta del MIDI asociado a un mapa.

Existe para que las recetas del justfile no tengan que saber cómo se llega del
número de mapa al archivo: el nombre del tema está en el árbol de mapas, puede
venir heredado del mapa padre, y el archivo en disco no respeta mayúsculas.
Todo eso ya lo resuelven lcf.py y find_resource.

Uso:
    python3 tools/midi_path.py --map-id 67
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
from render_map import GAME_DIR, find_resource


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--game-dir", default=GAME_DIR)
    args = parser.parse_args()

    tree = lcf.TreeMap(os.path.join(args.game_dir, "RPG_RT.lmt"))
    music = tree.map_music(args.map_id)
    if not music or not music["name"]:
        sys.exit("el mapa %d no tiene música propia" % args.map_id)

    path = find_resource([args.game_dir], "Music", music["name"], (".mid",))
    if not path:
        sys.exit("no encuentro el MIDI %r" % music["name"])
    print(path)


if __name__ == "__main__":
    main()

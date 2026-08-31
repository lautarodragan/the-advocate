#!/usr/bin/env python3
"""Renderiza un mapa de A Blurred Line (RPG Maker 2000) a un PNG.

Sólo el mapa: las dos capas de tiles, sin eventos, sin sprites, sin panorama.
Es el paso cero del port a Mega Drive: confirmar que podemos leer los datos
originales y reconstruir lo que se ve en pantalla.

Uso:
    python3 tools/render_map.py                 # el mapa inicial del juego
    python3 tools/render_map.py --map-id 5
    python3 tools/render_map.py --map Maps/Map0001.lmu -o /tmp/mapa.png
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
from chipset import ChipsetAtlas, TILE

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME_DIR = "/home/taro/git/gaming/abl-rm"
RTP_DIR = "/home/taro/git/gaming/easyrpg/RTP"

# Los mapas 1 a 6 (intro y flashbacks) usan chipsets del RTP oficial de RM2k
# (ChipSet1/2/3, Basis) que no vienen con el juego ni están en el RTP libre de
# EasyRPG. El 7 es el primero que se dibuja sólo con assets propios de ABL.
DEFAULT_MAP_ID = 7


def find_resource(dirs, folder, name):
    """Busca <dir>/<folder>/<name>.<ext> sin distinguir mayúsculas.

    RM2k guarda los nombres sin extensión y el juego original corría en
    Windows, así que los .lmu no dicen nada del case real del archivo.
    """
    for directory in dirs:
        for entry in os.listdir(directory) if os.path.isdir(directory) else []:
            if entry.lower() != folder.lower():
                continue
            subdir = os.path.join(directory, entry)
            for filename in os.listdir(subdir):
                base, ext = os.path.splitext(filename)
                if base.lower() == name.lower() and ext.lower() in (".png", ".bmp"):
                    return os.path.join(subdir, filename)
    return None


def load_chipset_image(path):
    image = Image.open(path)
    if image.mode == "P":
        # En RM2k el color 0 de la paleta es el color key.
        image.info["transparency"] = 0
    return image.convert("RGBA")


def build_passability(chipset):
    """Tabla de flags por ID de tile, como la arma lmu2png (main.cpp).

    Sólo la usamos para decidir si un tile va antes o después del jugador; acá
    no hay jugador, pero define el orden de dibujado entre las dos capas.
    """
    flags = bytearray(65536)
    lower, upper = chipset.passable_lower, chipset.passable_upper

    for i in range(3):          # agua A/B/C
        flags[1000 * i:1000 * i + 1000] = bytes([lower[i]]) * 1000
    for i in range(3):          # tiles animados
        flags[3000 + i * 50:3050 + i * 50] = bytes([lower[3 + i]]) * 50
    for i in range(12):         # autotiles de terreno
        flags[4000 + i * 50:4050 + i * 50] = bytes([lower[6 + i]]) * 50
    for i in range(144):        # páginas de tiles comunes
        flags[5000 + i] = lower[18 + i]
        flags[10000 + i] = upper[i]
    return flags


def draw_layers(image, atlas, game_map, flags, pass_upper):
    """Dibuja los tiles de ambas capas que caen en la pasada pedida.

    Un tile de la capa baja con flags 0x30 y uno de la alta con 0x10 se dibujan
    por encima del jugador; el resto, por debajo. Sin jugador el efecto visible
    es el orden relativo entre capas.
    """
    for y in range(game_map.height):
        row = y * game_map.width
        for x in range(game_map.width):
            lower_tile = game_map.lower_layer[row + x]
            if bool(flags[lower_tile] & 0x30) == pass_upper:
                atlas.render_tile(image, x, y, lower_tile)

            upper_tile = game_map.upper_layer[row + x]
            if bool(flags[upper_tile] & 0x10) == pass_upper:
                atlas.render_tile(image, x, y, upper_tile)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", help="ruta a un .lmu concreto")
    parser.add_argument("--map-id", type=int, default=DEFAULT_MAP_ID,
                        help="número de mapa (default: %d)" % DEFAULT_MAP_ID)
    parser.add_argument("--maps-dir", default=os.path.join(REPO, "Maps"))
    parser.add_argument("--game-dir", default=GAME_DIR,
                        help="proyecto RM2k original, para RPG_RT.ldb/.lmt y chipsets")
    parser.add_argument("--rtp-dir", default=RTP_DIR,
                        help="RTP donde buscar los chipsets que no trae el juego")
    parser.add_argument("-o", "--output", help="PNG de salida (por defecto, junto al .lmu)")
    args = parser.parse_args()

    database = lcf.Database(os.path.join(args.game_dir, "RPG_RT.ldb"))
    tree = lcf.TreeMap(os.path.join(args.game_dir, "RPG_RT.lmt"))

    if args.map:
        map_path = args.map
        map_id = int(os.path.basename(map_path)[3:7])
    else:
        map_id = args.map_id
        map_path = os.path.join(args.maps_dir, "Map%04d.lmu" % map_id)

    # El mapa de arranque del juego es un cuarto vacío que sólo teletransporta,
    # así que no sirve como "primer mapa"; lo dejamos anotado igual.
    print("Mapa de arranque del juego: %d %r en (%d, %d)" % (
        tree.start_map_id, tree.map_names.get(tree.start_map_id, "?"),
        tree.start_x, tree.start_y))

    game_map = lcf.Map(map_path)
    chipset = database.chipsets[game_map.chipset_id]

    print("Mapa %d %r: %dx%d tiles, chipset %d %r (%s)" % (
        map_id, tree.map_names.get(map_id, "?"), game_map.width, game_map.height,
        game_map.chipset_id, chipset.name, chipset.filename))

    search_dirs = [REPO, args.game_dir, args.rtp_dir]
    chipset_path = find_resource(search_dirs, "ChipSet", chipset.filename)
    if not chipset_path:
        sys.exit("No encuentro el chipset %r en %s" % (chipset.filename, search_dirs))

    atlas = ChipsetAtlas(load_chipset_image(chipset_path))
    flags = build_passability(chipset)

    image = Image.new("RGBA", (game_map.width * TILE, game_map.height * TILE),
                      (0, 0, 0, 255))
    draw_layers(image, atlas, game_map, flags, pass_upper=False)
    draw_layers(image, atlas, game_map, flags, pass_upper=True)

    output = args.output or os.path.join(REPO, "render", "Map%04d.png" % map_id)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    image.save(output)
    print("-> %s (%dx%d px)" % (output, image.width, image.height))


if __name__ == "__main__":
    main()

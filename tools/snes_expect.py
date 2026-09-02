#!/usr/bin/env python3
"""Construye lo que la consola debería estar mostrando, para comparar contra ella.

No alcanza con el render del mapa: ahora hay un personaje encima, y hay que
saber dónde quedó. Eso no se estima mirando la captura — se calcula con las
mismas reglas que sigue la ROM, y si la ROM lo dejó en otro lado la comparación
falla. Es lo mismo que se hizo en la Mega Drive.

Dónde queda es predecible porque se camina hasta chocar: contra un borde del
mapa la posición es exactamente el tamaño del mapa menos una celda. Y como la
ROM sólo anima cuando la posición realmente cambia, contra el borde el
personaje queda en su pose parada, que también es predecible.

Los colores del personaje son los ya fusionados a 15: el sprite de la consola
tiene 4 bits por pixel y no entran los 36 que trae el CharSet.

Uso:
    python3 tools/snes_expect.py --map-id 7 --walk right -o esperado.png
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
import md_convert
import snes_convert
from md_convert import hero_start, passability_map, walk
from render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, build_passability,
                        find_resource, load_image)

SCREEN_W, SCREEN_H = 256, 224
TILE = 16                       # la celda de RM2k sobre la que se para
STAND = 1                       # el frame del medio del ciclo de caminata

# Las direcciones de RM2k, en el orden en que están en el CharSet.
DIRECTIONS = {"up": 0, "right": 1, "down": 2, "left": 3}
WALK = {"none": None, "up": (0, -1), "down": (0, 1),
        "left": (-1, 0), "right": (1, 0)}


def hero_position(direction_name, passable, width, height):
    """Dónde termina el héroe, en pixeles, y hacia dónde mira.

    No se estima: se camina con las mismas reglas que la ROM. Arranca en el tile
    abierto más cercano al centro —el mismo que eligió el conversor— y avanza
    hasta que la pasabilidad lo frena o se acaba el mapa. Si la ROM lo dejara en
    otra celda, la comparación falla.
    """
    start = hero_start(passable, width, height)
    step = WALK[direction_name]
    direction = DIRECTIONS.get(direction_name, DIRECTIONS["down"])
    if step is None:
        return start[0] * TILE, start[1] * TILE, DIRECTIONS["down"]

    x, y = walk(passable, width, height, start, step[0], step[1])
    return x * TILE, y * TILE, direction


def camera_for(x, y, map_w, map_h):
    """Dónde mira la cámara: centrada en el héroe y pegada a los bordes."""
    cam_x = max(0, min(map_w * 8 - SCREEN_W, x + 8 - SCREEN_W // 2))
    cam_y = max(0, min(map_h * 8 - SCREEN_H, y + 8 - SCREEN_H // 2))
    return cam_x, cam_y


def hero_image(charset, index, direction, frame):
    """La pose pedida, con los colores ya fusionados a los 15 del sprite."""
    counts = snes_convert.sprite_colors(charset, index)
    if len(counts) <= snes_convert.OBJ_COLORS:
        mapping = {c: c for c in counts}
    else:
        mapping, _ = md_convert.merge_least_used(counts,
                                                 snes_convert.OBJ_COLORS)

    pose = direction * 3 + frame
    ox, oy = snes_convert.pose_origin(index, pose)
    out = Image.new("RGBA", (snes_convert.SPRITE_W, snes_convert.SPRITE_H),
                    (0, 0, 0, 0))
    for y in range(snes_convert.SPRITE_H):
        for x in range(snes_convert.SPRITE_W):
            r, g, b, a = charset.getpixel((ox + x, oy + y))
            if not a:
                continue
            # Se guarda el color de 15 bits corrido a 8, que es la misma escala
            # en la que después se compara.
            cr, cg, cb = mapping[(r >> 3, g >> 3, b >> 3)]
            out.putpixel((x, y), (cr << 3, cg << 3, cb << 3, 255))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=7)
    parser.add_argument("--walk", default="none", choices=sorted(WALK))
    parser.add_argument("--charset", default="Future1")
    parser.add_argument("--charset-index", type=int, default=0)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()

    renderer = Renderer(args.game_dir)
    game_map = lcf.Map(os.path.join(args.game_dir,
                                    "Map%04d.lmu" % args.map_id))
    base, _above = renderer.render_layers(game_map)
    if base is None:
        sys.exit("no encuentro el chipset del mapa %d" % args.map_id)

    chipset = renderer.database.chipsets[game_map.chipset_id]
    passable = passability_map(game_map, build_passability(chipset))
    x, y, direction = hero_position(args.walk, passable,
                                    game_map.width, game_map.height)
    cam_x, cam_y = camera_for(x, y, game_map.width * 2, game_map.height * 2)

    view = base.convert("RGBA").crop((cam_x, cam_y,
                                      cam_x + SCREEN_W, cam_y + SCREEN_H))

    charset = load_image(find_resource([REPO, args.game_dir, RTP_DIR],
                                       "CharSet", args.charset))
    # El sprite se centra sobre su celda y se apoya por los pies.
    pose = hero_image(charset, args.charset_index, direction, STAND)
    view.alpha_composite(pose, (x - 4 - cam_x, y - 16 - cam_y))

    view.convert("RGB").save(args.output)
    print("esperado -> %s: héroe en (%d,%d) mirando %s, cámara en (%d,%d)"
          % (args.output, x, y, args.walk if args.walk != "none" else "abajo",
             cam_x, cam_y))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Cuánto llega a caminar el héroe en cada dirección, mapa por mapa.

La ventana del tilemap da la vuelta cada 64 celdas a lo ancho y cada 32 a lo
alto. Para que una prueba diga algo sobre el redibujado hay que elegir un mapa
donde la caminata cruce esos límites de verdad, y eso no se adivina mirando el
tamaño: un mapa enorme lleno de paredes frena en la tercera celda.

Se camina con las mismas reglas que la ROM —las de rm2k.py, que son las que
usa también la referencia— así que lo que dice es lo que va a pasar.

Uso:
    python3 tools/snes_recorrido.py --desde 66
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
from rm2k import collect_npcs, hero_start, passability_map, walk
from render_map import GAME_DIR, Renderer, build_passability

PASOS = {"derecha": (1, 0), "izquierda": (-1, 0),
         "abajo": (0, 1), "arriba": (0, -1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--desde", type=int, default=0,
                        help="sólo mapas de al menos esta cantidad de celdas "
                             "de 8x8 de lado")
    args = parser.parse_args()

    renderer = Renderer(args.game_dir)
    ids = sorted(int(n[3:7]) for n in os.listdir(args.game_dir)
                 if n.startswith("Map") and n.endswith(".lmu"))

    filas = []
    for map_id in ids:
        game_map = lcf.Map(os.path.join(args.game_dir, "Map%04d.lmu" % map_id))
        if max(game_map.width, game_map.height) * 2 < args.desde:
            continue
        chipset = renderer.database.chipsets.get(game_map.chipset_id)
        if chipset is None:
            continue
        passable = passability_map(game_map, build_passability(chipset))
        ocupadas = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
        start = hero_start(passable, game_map.width, game_map.height, ocupadas)

        # En celdas de 8x8, que es la unidad de la ventana: la de RM2k son dos.
        recorrido = {}
        for nombre, (dx, dy) in PASOS.items():
            x, y = walk(passable, game_map.width, game_map.height, start, dx, dy)
            recorrido[nombre] = (abs(x - start[0]) + abs(y - start[1])) * 2

        filas.append((min(recorrido["arriba"] + recorrido["abajo"],
                          recorrido["izquierda"] + recorrido["derecha"]),
                      map_id, renderer.tree.map_names.get(map_id, ""),
                      recorrido))

    print("Los mapas donde más se camina por los dos ejes, en celdas de 8x8.")
    print("La ventana da la vuelta a las 64 a lo ancho y a las 32 a lo alto.\n")
    print("  id  nombre                    izq  der  arr  aba")
    for _peor, map_id, name, r in sorted(filas, reverse=True)[:12]:
        print("  %3d  %-24s %4d %4d %4d %4d"
              % (map_id, name[:24], r["izquierda"], r["derecha"],
                 r["arriba"], r["abajo"]))


if __name__ == "__main__":
    main()

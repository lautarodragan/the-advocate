#!/usr/bin/env python3
"""Pasa todos los mapas por los límites del hardware y dice cuáles no entran.

Nació para decidir cómo encarar los mapas grandes —cuál de los límites se toca
primero no se adivinaba, había que medirlo— y quedó como control: cada vez que
se toca el conversor o el reparto de la VRAM, esto dice sobre qué mapas se
rompió algo, sin tener que armar la ROM de cada uno.

Para cada mapa reporta las celdas de 8x8 que ocupa, los tiles distintos que le
quedan al fondo después del reuso, los colores, los bloques de 16x16 en que se
resume, y cuánto pesan sus datos contra lo que pesaría el tilemap expandido.

Uso:
    python3 tools/snes_survey.py                 # todos
    python3 tools/snes_survey.py --desde 66      # sólo los que piden redibujado
"""

import argparse
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
import snes_convert
from render_map import GAME_DIR, Renderer

ROM = 256 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--desde", type=int, default=0,
                        help="sólo los mapas de al menos esta cantidad de "
                             "celdas de 8x8 de lado")
    args = parser.parse_args()

    renderer = Renderer(args.game_dir)
    ids = sorted(int(n[3:7]) for n in os.listdir(args.game_dir)
                 if n.startswith("Map") and n.endswith(".lmu"))

    # "colores" es lo que el fondo usa contra lo que tiene disponible, y ese
    # disponible depende de "arr", las paletas que se llevó la capa de encima.
    # Cuando los dos números son iguales el mapa está fusionando colores.
    print("  id  nombre                    celdas    tiles   colores arr"
          " bloques     hoy  bloques  qué lo frena")
    for map_id in ids:
        path = os.path.join(args.game_dir, "Map%04d.lmu" % map_id)
        game_map = lcf.Map(path)
        width, height = game_map.width * 2, game_map.height * 2
        if max(width, height) < args.desde:
            continue

        name = renderer.tree.map_names.get(map_id, "")
        try:
            base, above_img, variantes = renderer.capas_animadas(game_map)
            if base is None:
                print("  %3d  %-24s  sin chipset" % (map_id, name[:24]))
                continue
            (tile_data, cram, tilemap, resumen), above = \
                snes_convert.convert_layers(base, above_img,
                                            variantes=variantes)
        except SystemExit as error:
            print("  %3d  %-24s  %4dx%-4d  %s" % (map_id, name[:24], width,
                                                  height, error))
            continue
        except Exception:
            traceback.print_exc()
            continue

        tiles = resumen["tiles"]
        # Lo que pesaría emitido como hoy: los tiles del fondo más una palabra
        # por celda del tilemap.
        datos = tiles * snes_convert.BYTES_PER_TILE + width * height * 2

        # Y lo que pesaría guardando la celda de 16x16 de RM2k en vez de las
        # cuatro de 8x8 en que se parte: la celda se repite muchísimo dentro de
        # un mapa, así que alcanza con un índice a una tabla de bloques.
        # El bloque lleva las dos capas juntas: una celda de RM2k es un par
        # (abajo, encima) y guardarlas en un solo índice ahorra la mitad de la
        # grilla, que es lo que domina en los mapas grandes.
        arriba = above[2]
        bloques = {}
        for by in range(len(tilemap) // 2):
            for bx in range(len(tilemap[0]) // 2):
                bloque = (tilemap[by * 2][bx * 2], tilemap[by * 2][bx * 2 + 1],
                          tilemap[by * 2 + 1][bx * 2],
                          tilemap[by * 2 + 1][bx * 2 + 1],
                          arriba[by * 2][bx * 2], arriba[by * 2][bx * 2 + 1],
                          arriba[by * 2 + 1][bx * 2],
                          arriba[by * 2 + 1][bx * 2 + 1])
                bloques.setdefault(bloque, len(bloques))
        con_bloques = (tiles * snes_convert.BYTES_PER_TILE
                       + len(above[0])
                       + len(bloques) * snes_convert.BLOCK_BYTES
                       + (width // 2) * (height // 2) * 2)

        # Contra los límites de verdad, los mismos que hace valer el conversor.
        layout = snes_convert.vram_layout(tiles)
        frena = []
        if tiles > layout["tiles"][1]:
            frena.append("tiles de fondo")
        if len(above[0]) // 32 > layout["encima"][1]:
            frena.append("tiles de la capa de encima")
        if len(bloques) > snes_convert.MAX_BLOCKS:
            frena.append("bloques")
        if con_bloques > ROM:
            frena.append("ROM")

        print("  %3d  %-24s  %4dx%-4d  %5d  %4d/%-4d  %d  %5d  %6.1f KB"
              "  %6.1f KB  %s"
              % (map_id, name[:24], width, height, tiles,
                 resumen["usados"], resumen["presupuesto"],
                 snes_convert.BG_PALETTES - above[3],
                 len(bloques), datos / 1024, con_bloques / 1024,
                 ", ".join(frena) or "-"))


if __name__ == "__main__":
    main()

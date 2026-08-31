#!/usr/bin/env python3
"""Compara el screenshot del emulador contra el render de Python.

Tres comparaciones distintas, porque hay tres fuentes de diferencia:

  1. Screenshot vs referencia del conversor. Tienen que ser iguales salvo por
     los niveles exactos del DAC, que dependen del emulador. Se chequea que
     coincidan "salvo renombre de colores": misma forma, mismos píxeles.
  2. Referencia vs render original. Acá sí hay diferencia real y esperable: los
     colores pasaron de 24 a 9 bits y algunos se fusionaron para entrar en las
     paletas.
  3. Sale un PNG lado a lado para mirar.

Uso:
    python3 tools/md_compare.py md/shots/map0007.png /tmp/ref.png render/Map0007.png
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

from render_map import REPO

BACKDROP = (255, 0, 255)   # el color de fondo que pone la ROM, fuera del área activa


def crop_active(image):
    """Recorta el área activa buscando las bandas de overscan.

    El framebuffer que guarda blastem incluye el overscan y, más afuera, zonas
    negras del blanking. Como la ROM pinta el fondo de magenta y ningún tile
    usa ese color, el área activa es el hueco que dejan las bandas magenta:
    primero las filas enteras de fondo acotan arriba y abajo, y después, ya
    dentro de esas filas, las columnas enteras acotan a los costados.
    """
    pixels = image.convert("RGB")
    width, height = pixels.size

    def bounds(is_backdrop, length):
        """Entre qué índices queda el hueco, mirando desde el centro hacia afuera."""
        centre = length // 2
        low = centre
        while low > 0 and not is_backdrop(low - 1):
            low -= 1
        high = centre
        while high < length and not is_backdrop(high):
            high += 1
        return low, high

    def row_is_backdrop(y):
        return all(pixels.getpixel((x, y)) == BACKDROP for x in range(width))

    y0, y1 = bounds(row_is_backdrop, height)

    def column_is_backdrop(x):
        return all(pixels.getpixel((x, y)) == BACKDROP for y in range(y0, y1))

    x0, x1 = bounds(column_is_backdrop, width)

    if x1 <= x0 or y1 <= y0:
        sys.exit("No encontré el área activa dentro del marco de fondo.")
    return pixels.crop((x0, y0, x1, y1)), (x0, y0, x1, y1)


def relabel(image, mask=None):
    """La imagen como índices de color, en orden de aparición.

    Sirve para comparar dos imágenes que tienen la misma forma pero paletas con
    valores RGB distintos, que es justo el caso entre el emulador y nosotros:
    los dos sabemos qué color de 9 bits va en cada píxel, pero cada uno lo
    convierte a RGB con su propia tabla.
    """
    ids = {}
    labels = []
    width = image.width
    mx, my, mw, mh = mask if mask else (0, 0, 0, 0)

    for i, pixel in enumerate(image.get_flattened_data()):
        # Los píxeles tapados no entran en la numeración: si entraran, los
        # colores del sprite correrían los ids de todo lo que viene después.
        if mask and mx <= i % width < mx + mw and my <= i // width < my + mh:
            labels.append(-1)
        else:
            labels.append(ids.setdefault(pixel, len(ids)))
    return labels


TILE = 16
SPRITE_W = 24
SPRITE_H = 32


DIRECTIONS = {"none": (0, 0), "right": (1, 0), "left": (-1, 0),
              "up": (0, -1), "down": (0, 1)}


def simulate(map_id, direction):
    """Dónde termina el personaje, con las mismas reglas que la ROM.

    Si la simulación y la ROM no coinciden en la colisión, el personaje va a
    quedar en otro tile y la comparación falla. O sea que esto no sólo ubica al
    sprite: verifica la colisión.
    """
    import lcf
    from render_map import Renderer, build_passability
    from md_convert import hero_start, passability_map, walk

    renderer = Renderer()
    game_map = lcf.Map(os.path.join(REPO, "Maps", "Map%04d.lmu" % map_id))
    flags = build_passability(renderer.database.chipsets[game_map.chipset_id])
    passable = passability_map(game_map, flags)
    start = hero_start(passable, game_map.width, game_map.height)

    dx, dy = DIRECTIONS[direction]
    if (dx, dy) == (0, 0):
        return start
    return walk(passable, game_map.width, game_map.height, start, dx, dy)


def hero_view(tile, map_size, screen_size):
    """Dónde queda la cámara y el sprite, dado el tile donde está el personaje.

    Reproduce lo que hace la ROM: la cámara lo sigue centrada y topa contra los
    bordes del mapa. Como el render de Python no dibuja al personaje, su
    rectángulo se excluye de la comparación — pero justamente por eso, que todo
    lo de alrededor coincida prueba que el sprite está donde tiene que estar.
    """
    map_w, map_h = map_size
    screen_w, screen_h = screen_size

    def resolve(value, tiles):
        if value == "mid":
            return tiles // 2
        if value == "max":
            return tiles - 1
        return int(value)

    tx = resolve(tile[0], map_w // TILE)
    ty = resolve(tile[1], map_h // TILE)
    hero_x, hero_y = tx * TILE, ty * TILE

    cam_x = min(max(hero_x + TILE // 2 - screen_w // 2, 0), map_w - screen_w)
    cam_y = min(max(hero_y + TILE // 2 - screen_h // 2, 0), map_h - screen_h)

    # El sprite de 24x32 va centrado a lo ancho del tile y apoyado por los pies.
    mask = (hero_x - (SPRITE_W - TILE) // 2 - cam_x,
            hero_y - (SPRITE_H - TILE) - cam_y,
            SPRITE_W, SPRITE_H)
    return cam_x, cam_y, mask


def channel_error(a, b):
    """Diferencia de color entre dos imágenes: máxima, promedio y por píxel."""
    pa, pb = list(a.get_flattened_data()), list(b.get_flattened_data())
    deltas = [max(abs(x - y) for x, y in zip(p, q)) for p, q in zip(pa, pb)]
    return max(deltas), sum(deltas) / len(deltas), deltas


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("screenshot")
    parser.add_argument("reference")
    parser.add_argument("original")
    parser.add_argument("-o", "--output", help="PNG lado a lado")
    parser.add_argument("--map-id", type=int,
                        help="mapa, para poder calcular la colisión")
    parser.add_argument("--walk", default="none",
                        choices=("none", "right", "left", "up", "down"),
                        help="hacia dónde se caminó sin soltar la cruceta. Se "
                             "simula con las mismas reglas que la ROM para "
                             "saber en qué tile tuvo que frenar")
    parser.add_argument("--hero-tile", nargs=2, metavar=("TX", "TY"),
                        help="tile donde está el personaje, si se sabe de "
                             "antemano. Alternativa a --map-id/--walk")
    parser.add_argument("--camera", nargs=2, default=("0", "0"),
                        metavar=("X", "Y"),
                        help="dónde debería estar la cámara, en píxeles. "
                             "'max' = contra el tope del mapa, que es donde la "
                             "deja el clamp si se mantiene la cruceta apretada")
    args = parser.parse_args()

    shot, box = crop_active(Image.open(args.screenshot))
    reference = Image.open(args.reference).convert("RGB")
    original = Image.open(args.original).convert("RGB")
    print("Área activa del screenshot: %dx%d en %s" % (shot.width, shot.height, box))

    # Los dos tienen que ser el mismo mapa. Si no, alguno quedó de una corrida
    # anterior y la comparación no significa nada.
    if reference.size != original.size:
        print("La referencia mide %s y el render de Python %s: son de mapas "
              "distintos. Corré `just md-convert` de nuevo."
              % (reference.size, original.size))
        return 1

    # La pantalla es una ventana del mapa: se recorta donde debería estar la
    # cámara y se compara contra eso.
    mask = None
    if args.map_id is not None:
        tile = simulate(args.map_id, args.walk)
        cam_x, cam_y, mask = hero_view(tile, reference.size, shot.size)
        print("Caminando hacia %s: frena en el tile %s, cámara en (%d, %d), "
              "sprite en %s" % (args.walk, tile, cam_x, cam_y, mask))
    elif args.hero_tile:
        cam_x, cam_y, mask = hero_view(args.hero_tile, reference.size, shot.size)
        print("Personaje en el tile %s: cámara en (%d, %d), sprite en %s"
              % (tuple(args.hero_tile), cam_x, cam_y, mask))
    else:
        # 'max' es la posición contra la que topa la cámara: el mapa menos la
        # pantalla. Depende de la región, porque en NTSC se ven 16 renglones
        # menos.
        cam_x = (reference.width - shot.width if args.camera[0] == "max"
                 else int(args.camera[0]))
        cam_y = (reference.height - shot.height if args.camera[1] == "max"
                 else int(args.camera[1]))
    if (cam_x, cam_y) != (0, 0) or reference.size != shot.size:
        window = (cam_x, cam_y, cam_x + shot.width, cam_y + shot.height)
        if window[2] > reference.width or window[3] > reference.height:
            print("La ventana %s se sale del mapa de %dx%d"
                  % (window, reference.width, reference.height))
            return 1
        print("Cámara en (%d, %d): se compara la ventana %s del mapa"
              % (cam_x, cam_y, window))
        reference = reference.crop(window)
        original = original.crop(window)

    if shot.width != reference.width:
        print("El ancho del área activa no coincide: %d vs %d"
              % (shot.width, reference.width))
        return 1

    # En una consola NTSC sólo hay 224 renglones, así que se ven los primeros
    # 224 del mapa. Se comparan los que sí están.
    if shot.height < reference.height:
        print("La consola muestra %d de los %d renglones del mapa; se comparan "
              "los que se ven." % (shot.height, reference.height))
        reference = reference.crop((0, 0, reference.width, shot.height))
        original = original.crop((0, 0, original.width, shot.height))
    elif shot.height != reference.height:
        print("El alto del área activa no coincide: %d vs %d"
              % (shot.height, reference.height))
        return 1

    # La prueba de que la ROM está bien: dos píxeles tienen el mismo color en
    # el emulador si y sólo si lo tienen en la referencia. No se comparan
    # valores RGB porque cada uno convierte los 9 bits del VDP a RGB con su
    # propia tabla de niveles.
    ok = relabel(shot, mask) == relabel(reference, mask)
    print("emulador vs referencia (forma):   %s"
          % ("IDÉNTICOS, píxel por píxel" if ok else "DIFIEREN"))
    worst, mean, _ = channel_error(shot, reference)
    print("emulador vs referencia (niveles): máx %d/255, prom %.1f"
          % (worst, mean))
    print("  (sólo la tabla con que cada uno convierte los 9 bits del VDP a RGB)")

    worst, mean, deltas = channel_error(reference, original)
    heavy = sum(1 for d in deltas if d > 32)
    print("referencia vs render original:    máx %d/255, prom %.1f, %d px con "
          "más de 32 (%.3f%%)" % (worst, mean, heavy, 100.0 * heavy / len(deltas)))
    print("  (esperable: el color pasa de 24 a 9 bits y unos pocos se fusionan"
          " para entrar en las paletas)")

    if args.output:
        gap = 8
        canvas = Image.new("RGB", (shot.width * 2 + gap, shot.height))
        canvas.paste(original, (0, 0))
        canvas.paste(shot, (shot.width + gap, 0))
        canvas.save(args.output)
        print("lado a lado -> %s" % args.output)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

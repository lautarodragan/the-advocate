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
import sys

from PIL import Image

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


def relabel(image):
    """La imagen como índices de color, en orden de aparición.

    Sirve para comparar dos imágenes que tienen la misma forma pero paletas con
    valores RGB distintos, que es justo el caso entre el emulador y nosotros:
    los dos sabemos qué color de 9 bits va en cada píxel, pero cada uno lo
    convierte a RGB con su propia tabla.
    """
    ids = {}
    return [ids.setdefault(p, len(ids)) for p in image.get_flattened_data()]


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
    args = parser.parse_args()

    shot, box = crop_active(Image.open(args.screenshot))
    reference = Image.open(args.reference).convert("RGB")
    original = Image.open(args.original).convert("RGB")
    print("Área activa del screenshot: %dx%d en %s" % (shot.width, shot.height, box))

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
    ok = relabel(shot) == relabel(reference)
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

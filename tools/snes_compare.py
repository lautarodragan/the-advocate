#!/usr/bin/env python3
"""Compara la captura del emulador contra el render de Python, pixel por pixel.

La comparación se hace a 15 bits, que es la profundidad real de la consola. El
emulador expande cada canal de 5 bits a 8 al mostrarlo, así que volver a
recortar los tres bits bajos deshace exactamente esa expansión y deja los dos
lados en la misma escala. Cualquier diferencia que quede es nuestra.

No se compara "parecido": se cuenta cuántos pixeles difieren y cuánto. Si el
conversor eligió mal un color, o el tilemap apuntó al tile equivocado, o el
formato de bits está invertido, acá salta.

Uso:
    python3 tools/snes_compare.py snes/shots/mapa.png /tmp/ref7.png
"""

import argparse
import os
import sys

from PIL import Image


def quantize(image):
    """La imagen a 15 bits, que es lo que la consola puede mostrar."""
    return [(r >> 3, g >> 3, b >> 3)
            for r, g, b in image.convert("RGB").get_flattened_data()]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("captura")
    parser.add_argument("referencia")
    parser.add_argument("--camara", nargs=2, type=int, metavar=("X", "Y"),
                        default=(0, 0),
                        help="dónde tendría que estar mirando la cámara")
    parser.add_argument("--saltar", help="archivo con las líneas a excluir")
    parser.add_argument("-o", "--output", help="PNG con las dos y la diferencia")
    args = parser.parse_args()

    shot = Image.open(args.captura).convert("RGB")
    full = Image.open(args.referencia).convert("RGB")
    # La referencia es el mapa entero; la consola muestra sólo la ventana que la
    # cámara esté mirando. Dónde debería estar no se mide: se calcula, y si la
    # ROM la dejó en otro lado la comparación falla.
    x, y = args.camara
    reference = full.crop((x, y, x + shot.width, y + shot.height))

    ours, theirs = quantize(shot), quantize(reference)
    if len(ours) != len(theirs):
        sys.exit("las imágenes no tienen el mismo tamaño")

    # Hay líneas donde la consola no puede dibujar todos los sprites; el
    # esperado las declara y acá se excluyen, en vez de contar como error algo
    # que el hardware no puede hacer.
    saltar = set()
    if args.saltar and os.path.exists(args.saltar):
        saltar = {int(line) for line in open(args.saltar) if line.strip()}

    diffs = [i for i, (a, b) in enumerate(zip(ours, theirs))
             if a != b and (i // shot.width) not in saltar]
    total = len(ours) - len(saltar) * shot.width
    print("%s contra %s: %dx%d, cámara en (%d,%d)"
          % (args.captura, args.referencia, shot.width, shot.height, x, y))
    if saltar:
        print("  %d líneas excluidas: la consola no puede dibujar tantos "
              "sprites juntos" % len(saltar))
    print("  pixeles distintos: %d de %d (%.2f%%)"
          % (len(diffs), total, 100.0 * len(diffs) / total))

    if diffs:
        worst = max(diffs, key=lambda i: sum(abs(a - b) for a, b
                                             in zip(ours[i], theirs[i])))
        x, y = worst % shot.width, worst // shot.width
        print("  la peor en (%d,%d): %s contra %s"
              % (x, y, ours[worst], theirs[worst]))

        rows = {}
        for i in diffs:
            rows.setdefault(i // shot.width, 0)
            rows[i // shot.width] += 1
        peor = sorted(rows.items(), key=lambda kv: -kv[1])[:3]
        print("  filas con más diferencias: %s"
              % ", ".join("y=%d (%d px)" % kv for kv in peor))

    if args.output:
        canvas = Image.new("RGB", (shot.width * 2 + 8, shot.height), (32, 32, 32))
        canvas.paste(shot, (0, 0))
        canvas.paste(reference, (shot.width + 8, 0))
        canvas.save(args.output)
        print("  lado a lado -> %s" % args.output)

    if not diffs:
        print("IDÉNTICAS a 15 bits.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Corre la ROM en un core de libretro y guarda lo que dibuja.

El reemplazo de `snes/screenshot.sh`. Aquél levanta un servidor X, arranca
mednafen, duerme unos segundos de reloj, le manda teclas con xdotool, le saca
una foto a la pantalla entera y después la recorta. Acá no hay nada de eso:
`retro_run()` avanza un cuadro exacto, la cruceta se contesta cuadro por cuadro
y el framebuffer sale del callback ya en 256x224.

La diferencia que importa no es la velocidad sino que **la prueba deja de
depender del reloj**. Cuántos cuadros llegaba a emular mednafen en N segundos
dependía de la carga de la máquina; acá N cuadros son N cuadros. Eso es lo que
hacía que la tanda repartida en procesos pudiera dar rojos falsos.

Las teclas se mantienen apretadas desde que termina el arranque hasta el final,
que es lo que hacía screenshot.sh y lo que la referencia modela: camina hasta
chocar contra la pared.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from retro import Consola, CORE

# El core con el que están verificadas las 46 comparaciones bit-exactas contra
# el harness de mednafen. bsnes devuelve una pantalla negra con este frontend y
# todavía no sabemos por qué: ver `tools/retro.py` y ESTADO.md.
CORE_POR_DEFECTO = "/usr/lib/libretro/snes9x_libretro.so"

# Cuántos cuadros se le dan a la ROM antes de apretar nada. screenshot.sh
# dormía tres segundos de reloj por la misma razón: que arranque y dibuje el
# mapa antes de que empiece la caminata.
ARRANQUE = 180


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rom")
    parser.add_argument("-o", "--output", required=True,
                        help="dónde va el PNG. Con varias direcciones tiene "
                             "que llevar un {} donde va la dirección")
    parser.add_argument("--walk", nargs="+", default=["none"],
                        help="las direcciones a correr; `none` es sin apretar "
                             "nada")
    parser.add_argument("--cuadros", type=int, default=480,
                        help="cuántos cuadros con la cruceta apretada")
    parser.add_argument("--arranque", type=int, default=ARRANQUE,
                        help="cuántos cuadros antes de apretar nada")
    parser.add_argument("--teclas", nargs="*", default=None, metavar="BOTON",
                        help="una sola corrida manteniendo estos botones. Es "
                             "la forma de pedir dos a la vez —`right down`— "
                             "que --walk no cubre. Sin botones, no aprieta "
                             "nada")
    parser.add_argument("--core", default=CORE_POR_DEFECTO)
    args = parser.parse_args()

    if args.teclas is not None:
        consola = Consola(args.rom, core=args.core)
        consola.correr(args.arranque)
        if args.teclas:
            consola.apretar(*args.teclas)
        consola.correr(args.cuadros)
        consola.imagen().save(args.output)
        print("captura -> %s: %s, %d cuadros (%d de arranque)"
              % (args.output, " ".join(args.teclas) or "sin apretar nada",
                 args.arranque + args.cuadros, args.arranque))
        return

    for walk in args.walk:
        destino = args.output.format(walk) if "{}" in args.output else args.output
        # Una consola nueva por dirección: arrancar de cero es parte de lo que
        # se está comparando, y reusar una traería el estado de la caminata
        # anterior.
        consola = Consola(args.rom, core=args.core)
        consola.correr(args.arranque)
        if walk != "none":
            consola.apretar(walk)
        consola.correr(args.cuadros)
        consola.imagen().save(destino)
        print("captura -> %s: %s, %d cuadros (%d de arranque)"
              % (destino, walk, args.arranque + args.cuadros, args.arranque))


if __name__ == "__main__":
    main()

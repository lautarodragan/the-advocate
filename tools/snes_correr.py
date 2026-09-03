#!/usr/bin/env python3
"""Corre la ROM en un core de libretro y guarda lo que dibuja.

El reemplazo de `rom/screenshot.sh`. Aquél levanta un servidor X, arranca
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

# Cuánto se corre de más después de los cuadros que dice el plan. La ROM llega
# uno o dos cuadros después de `pasos x 8` —el pad se lee una vez por cuadro y
# el primero se pierde, y según la dirección la cámara termina de acomodarse un
# cuadro más tarde—, así que el plan solo se queda corto. Ocho es una celda
# entera: alcanza de sobra y sigue siendo un número exacto de cuadros, no una
# holgura de reloj. Medido en el mapa 73: right y up llegan en +1, left y down
# en +2.
MARGEN = 8

# Cuántos cuadros seguidos idénticos cuentan como "la pantalla se quedó quieta".
QUIETO = 4

# El cuadro que se ve en pantalla muestra el estado de la vuelta ANTERIOR del
# lazo principal: `flush_video` sube el OAM que armó `build_oam` la vuelta
# pasada, y por eso está al principio del lazo y no al final. De ahí sale este
# +1, que no es un ajuste sino una consecuencia del orden de main.s.
#
# Con eso, para ver al héroe con N pixeles de avance hay que correr N/2 + 1
# cuadros desde que se aprieta: se mueve WALK_SPEED = 2 por cuadro. Medido en el
# mapa 73 a 40, 60 y 80 px: exacto da 0, y errarle por un cuadro para cualquier
# lado da unos 25000 pixeles de diferencia.
RETRASO_DE_PANTALLA = 1


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
    parser.add_argument("--avance", type=int, default=None, metavar="PX",
                        help="capturar a mitad de camino, cuando el héroe lleva "
                             "andados estos pixeles. Los cuadros salen de la "
                             "cuenta, no de un número suelto")
    parser.add_argument("--plan", help="el archivo que escribe snes_expect.py "
                        "con --plan: por dirección, cuántas celdas camina el "
                        "héroe y cuántos cuadros le lleva. Con esto los "
                        "cuadros salen de la referencia y no de un número "
                        "elegido a ojo, y --cuadros pasa a ser sólo el tope")
    parser.add_argument("--margen", type=int, default=MARGEN,
                        help="cuadros de más sobre lo que dice el plan")
    parser.add_argument("--quieto", type=int, default=QUIETO,
                        help="cuántos cuadros idénticos seguidos cuentan como "
                             "pantalla quieta")
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

    # El plan dice, por dirección, cuántos cuadros dura la caminata. Sale de la
    # misma referencia contra la que se compara, así que la prueba pasa de
    # "dormí 45 segundos, seguro alcanza" a "corré exactamente los cuadros que
    # esta caminata dura". El de arranque no sale de ahí y sigue siendo fijo,
    # pero eso no es una holgura del reloj: 180 cuadros son 180 cuadros en
    # cualquier máquina, y cuestan un milisegundo de CPU.
    plan = {}
    if args.plan:
        for linea in open(args.plan):
            if linea.split():
                direccion, _pasos, cuadros = linea.split()
                plan[direccion] = int(cuadros)

    for walk in args.walk:
        destino = args.output.format(walk) if "{}" in args.output else args.output
        # Una consola nueva por dirección: arrancar de cero es parte de lo que
        # se está comparando, y reusar una traería el estado de la caminata
        # anterior.
        consola = Consola(args.rom, core=args.core)
        del_plan = walk in plan
        if args.avance is not None:
            del_plan = False
            cuadros = args.avance // 2 + RETRASO_DE_PANTALLA
        elif del_plan:
            cuadros = plan[walk] + args.margen
        else:
            cuadros = args.cuadros
        consola.correr(args.arranque)
        if walk != "none":
            consola.apretar(walk)

        # Se corren los cuadros de a uno para poder mirar desde qué cuadro la
        # pantalla ya no cambia más. El que se compara es siempre el último, o
        # sea un número exacto y fijo: esto no elige el cuadro, sólo informa.
        # Si eligiera, la prueba dependería de una heurística.
        #
        # Y se busca el último tramo quieto, no el primero: caminando el mapa 52
        # hacia arriba hay tres tramos de cinco cuadros o más sin que cambie
        # nada —en el 97, en el 103 y en el 161— y sólo el último es el héroe
        # que llegó. Los otros dos son la ROM que se queda un momento a mitad de
        # camino; ese mapa es de 1000x80 y no entra en la ventana del PPU, así
        # que va redibujando mientras se scrollea. Quedarse con el primer tramo
        # informaba "quieta en el 97" cuando la caminata dura 160.
        quieto_desde = None
        anterior = None
        for n in range(1, cuadros + 1):
            consola.correr(1)
            actual = consola.cuadro[0]
            if actual != anterior:
                quieto_desde = n
            anterior = actual

        consola.imagen().save(destino)
        aviso = ""
        if del_plan and quieto_desde is not None and plan[walk]:
            # El plan dice cuántos cuadros tendría que durar la caminata, y la
            # pantalla deja de cambiar cuando el héroe llegó. Los dos números
            # tienen que dar casi lo mismo. Es lo más cerca que estamos hoy de
            # medir la *velocidad* del héroe: las comparaciones sólo miran dónde
            # termina, nunca cuánto tardó en llegar. Es un dato, no una
            # aserción; para que lo fuera habría que comparar contra la
            # referencia a mitad de camino, que todavía no se hace.
            aviso = ", quieta desde el %d (el plan dice %d)" % (quieto_desde,
                                                                plan[walk])
        print("captura -> %s: %s, %d cuadros%s (%d de arranque)%s"
              % (destino, walk, cuadros,
                 " = plan %d + margen %d" % (plan[walk], args.margen)
                 if del_plan else "", args.arranque, aviso))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Dibuja una página de mensaje del juego como la dibujaría RM2k.

Existe para tener con qué comparar. La ventana y la fuente son nuestras —salen
de `ventana.py` y `fuente.py`, que siguen las reglas de easyrpg-player— y hasta
que la ROM sepa dibujar un mensaje no hay nada contra qué contrastarlas. Esto
saca el texto de verdad del juego y lo dibuja, así se puede poner al lado de una
captura de EasyRPG de esa misma página.

Es la única forma de salir del agujero de siempre: si la referencia y la ROM se
equivocan igual, la comparación da cero. Una captura del juego original es el
tercero en discordia.

    just snes-mensaje 1          la primera página de mensaje del mapa 1
    just snes-mensaje 1 4        la quinta
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
import ventana

GAME_DIR = os.environ.get("GAME_DIR", "/extras/abl-rm")
MENSAJE, MENSAJE_SIGUE = 10110, 20110


def paginas_del_mapa(game_map):
    """Las páginas de mensaje del mapa, cada una con sus líneas.

    En RM2k un `ShowMessage` abre la página y cada `ShowMessage_2` le agrega una
    línea; cualquier otro comando la cierra. Son hasta cuatro líneas.
    """
    paginas, actual = [], None
    for evento in game_map.events:
        for pagina in evento.pages:
            for cmd in pagina.commands:
                if cmd.code == MENSAJE:
                    if actual:
                        paginas.append(actual)
                    actual = [(cmd.string or "").rstrip()]
                elif cmd.code == MENSAJE_SIGUE and actual is not None:
                    actual.append((cmd.string or "").rstrip())
                elif actual:
                    paginas.append(actual)
                    actual = None
            if actual:
                paginas.append(actual)
                actual = None
    return paginas


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=1)
    parser.add_argument("--indice", type=int, default=0,
                        help="qué página de mensaje del mapa dibujar")
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--escala", type=int, default=1,
                        help="agrandar el PNG por este factor, para mirarlo")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()

    game_map = lcf.Map(os.path.join(args.game_dir,
                                    "Map%04d.lmu" % args.map_id))
    paginas = paginas_del_mapa(game_map)
    if not paginas:
        sys.exit("el mapa %d no tiene ninguna página de mensaje" % args.map_id)
    if not 0 <= args.indice < len(paginas):
        sys.exit("el mapa %d tiene %d páginas de mensaje, no hay una %d"
                 % (args.map_id, len(paginas), args.indice))

    base = lcf.Database(os.path.join(args.game_dir, "RPG_RT.ldb"))
    lineas = paginas[args.indice]
    skin = ventana.skin(args.game_dir, base.system_name)
    vista = ventana.pagina(skin, lineas)
    if args.escala > 1:
        vista = vista.resize((vista.width * args.escala,
                              vista.height * args.escala), 0)
    vista.save(args.output)
    print("mensaje -> %s: mapa %d, página %d de %d, skin %r"
          % (args.output, args.map_id, args.indice, len(paginas),
             base.system_name))
    for n, linea in enumerate(lineas):
        cabe = len(linea) * 6 <= ventana.ANCHO - 2 * ventana.BORDE
        print("   %d %-42r %s" % (n, linea, "" if cabe else "SE TRUNCA"))


if __name__ == "__main__":
    main()

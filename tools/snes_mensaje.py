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


def comparar(vista, captura):
    """Nuestra ventana contra una captura de EasyRPG, a 15 bits.

    La captura es de 320x240 y la ventana de mensaje ocupa las 80 filas de
    abajo. Devuelve 0 si sólo difiere en la flecha, que es lo esperado.
    """
    from PIL import Image
    llana = Image.alpha_composite(
        Image.new("RGBA", vista.size, (0, 0, 0, 255)), vista).convert("RGB")
    entera = Image.open(captura).convert("RGB")
    caja = entera.crop((0, entera.height - vista.height,
                        vista.width, entera.height))
    a = [tuple(v >> 3 for v in p) for p in caja.get_flattened_data()]
    b = [tuple(v >> 3 for v in p) for p in llana.get_flattened_data()]
    distintos = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    print("contra %s: %d pixeles distintos de %d (%.2f%%)"
          % (captura, len(distintos), len(a), 100.0 * len(distintos) / len(a)))
    if not distintos:
        return 0
    xs = [i % vista.width for i in distintos]
    ys = [i // vista.width for i in distintos]
    print("   zona: x %d..%d  y %d..%d" % (min(xs), max(xs), min(ys), max(ys)))
    # La flecha roja de "seguir" que EasyRPG anima mientras espera al jugador
    # sale del System y nosotros no la dibujamos. Es lo único que puede
    # diferir sin que sea un error, y por eso se acota por dónde cae y no por
    # cuántos pixeles son.
    solo_flecha = all(vista.width // 2 - 12 <= x <= vista.width // 2 + 12
                      and y >= vista.height - 12 for x, y in zip(xs, ys))
    if solo_flecha:
        print("   sólo la flecha de seguir, que no dibujamos: lo demás coincide")
        return 0
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=1)
    parser.add_argument("--indice", type=int, default=0,
                        help="qué página de mensaje del mapa dibujar")
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--escala", type=int, default=1,
                        help="agrandar el PNG por este factor, para mirarlo")
    parser.add_argument("--contra", metavar="CAPTURA",
                        help="una captura de EasyRPG de 320x240 de esta misma "
                             "página. Compara nuestra ventana contra ella a 15 "
                             "bits, que es el único oráculo externo que tiene "
                             "este repo: si la referencia y la ROM se "
                             "equivocan igual, comparar entre ellas da cero")
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
    # Contra una captura se dibuja a 320, que es el ancho de RM2k; el de la
    # consola son 256 y ahí el texto se trunca, que es otra cosa.
    ancho = 320 if args.contra else ventana.ANCHO
    vista = ventana.pagina(skin, lineas, ancho=ancho, font_id=base.font_id)
    if args.contra:
        salir = comparar(vista, args.contra)
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
    if args.contra:
        sys.exit(salir)


if __name__ == "__main__":
    main()

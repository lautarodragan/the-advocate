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
from md_convert import (collect_npcs, hero_start, passability_map, walk)
from render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, build_passability,
                        find_resource, load_image)

SCREEN_W, SCREEN_H = 256, 224

# En una misma línea de pantalla la consola no dibuja más de 34 tiles de 8x8 de
# sprite, ni más de 32 objetos. Un objeto de 32x32 aporta cuatro tiles a cada
# línea que cruza, así que a partir de nueve personajes juntos empieza a perder
# los últimos. Se recorren en el orden de OAM y se corta donde se acaba el
# presupuesto.
OBJ_TILES_PER_LINE = 34
OBJ_PER_LINE = 32
OBJ_TILES = OBJ_W // 8 if False else 4
TILE = 16                       # la celda de RM2k sobre la que se para
STAND = 1                       # el frame del medio del ciclo de caminata

# Las direcciones de RM2k, en el orden en que están en el CharSet.
DIRECTIONS = {"up": 0, "right": 1, "down": 2, "left": 3}
WALK = {"none": None, "up": (0, -1), "down": (0, 1),
        "left": (-1, 0), "right": (1, 0)}


def hero_position(direction_name, passable, width, height, ocupadas=()):
    """Dónde termina el héroe, en pixeles, y hacia dónde mira.

    No se estima: se camina con las mismas reglas que la ROM. Arranca en el tile
    abierto más cercano al centro —el mismo que eligió el conversor— y avanza
    hasta que la pasabilidad lo frena o se acaba el mapa. Si la ROM lo dejara en
    otra celda, la comparación falla.
    """
    start = hero_start(passable, width, height, ocupadas)
    step = WALK[direction_name]
    direction = DIRECTIONS.get(direction_name, DIRECTIONS["down"])
    if step is None:
        return start[0] * TILE, start[1] * TILE, DIRECTIONS["down"]

    # Las celdas ocupadas sólo sirven para elegir dónde arranca. No se le pasan
    # a la caminata: en RM2k un NPC bloquea el paso, pero la ROM todavía no lo
    # implementa, y modelar acá algo que la consola no hace es inventar una
    # diferencia.
    x, y = walk(passable, width, height, start, step[0], step[1])
    return x * TILE, y * TILE, direction


def camera_for(x, y, map_w, map_h):
    """Dónde mira la cámara: centrada en el héroe y pegada a los bordes."""
    cam_x = max(0, min(map_w * 8 - SCREEN_W, x + 8 - SCREEN_W // 2))
    cam_y = max(0, min(map_h * 8 - SCREEN_H, y + 8 - SCREEN_H // 2))
    return cam_x, cam_y


def pose_image(charset, index, pose):
    """Una pose, con los colores ya fusionados a los 15 que entran en un sprite.

    La fusión es la misma que hace el conversor —mismo criterio, mismos datos—
    así que si difiere algo no es esto.
    """
    counts = snes_convert.sprite_colors(charset, index)
    if len(counts) <= snes_convert.OBJ_COLORS:
        mapping = {c: c for c in counts}
    else:
        mapping, _ = md_convert.merge_least_used(counts,
                                                 snes_convert.OBJ_COLORS)

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


def draw_actors(view, sprites, encima=None):
    """Pinta los sprites y avisa en qué líneas la consola no va a poder.

    No se intenta reproducir *cuáles* se pierden. La consola arma la lista de
    los que caen en cada línea recorriendo OAM y después busca sus tiles en un
    orden que depende del modelo y que acá sería una conjetura; probar dos
    reglas plausibles dio peor que no modelar nada. Lo que sí se puede afirmar
    con certeza es en qué líneas el presupuesto no alcanza, y ésas se declaran
    para excluirlas de la comparación en vez de fingir que se saben.

    Devuelve la lista de líneas donde el límite se pasa.
    """
    excedidas = []
    for y in range(SCREEN_H):
        presentes = sum(1 for _img, _sx, sy, _a in sprites
                        if sy <= y < sy + snes_convert.OBJ_H)
        if (presentes * OBJ_TILES > OBJ_TILES_PER_LINE
                or presentes > OBJ_PER_LINE):
            excedidas.append(y)

    # Se pintan de atrás hacia adelante, o sea al revés del orden de OAM.
    for image, sx, sy, arriba in reversed(sprites):
        if arriba:
            continue                # esos van después de la capa de encima
        view.alpha_composite(image, (sx, sy))

    if encima is not None:
        view.alpha_composite(encima, (0, 0))

    for image, sx, sy, arriba in reversed(sprites):
        if arriba:
            view.alpha_composite(image, (sx, sy))
    return excedidas


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=7)
    parser.add_argument("--walk", default="none", choices=sorted(WALK))
    parser.add_argument("--charset", default="Future1")
    parser.add_argument("--charset-index", type=int, default=0)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--saltar", help="archivo donde anotar las líneas que "
                        "pasan el límite de sprites")
    parser.add_argument("--hero-tile", nargs=2, type=int, metavar=("TX", "TY"),
                        help="poner al héroe en esta celda en vez de calcularla; "
                             "sirve para averiguar dónde lo dejó la ROM")
    parser.add_argument("--dir", default=None, choices=sorted(DIRECTIONS),
                        help="hacia dónde mira, si se fija la celda a mano")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()

    renderer = Renderer(args.game_dir)
    game_map = lcf.Map(os.path.join(args.game_dir,
                                    "Map%04d.lmu" % args.map_id))
    base, above_img = renderer.render_layers(game_map)
    if base is None:
        sys.exit("no encuentro el chipset del mapa %d" % args.map_id)

    # La referencia se arma desde los datos convertidos, no desde el render:
    # entre uno y otro están la fusión de colores, el reparto en paletas, el
    # reuso de tiles y los espejados, y todo eso aparecería como diferencia
    # aunque la consola hiciera exactamente lo que se le pidió.
    # Las dos capas juntas, con la misma función que usa el conversor: el
    # reparto de CGRAM depende de las dos, y si la referencia lo calculara por
    # su cuenta compararía contra una ROM que no existe.
    (tile_data, cram, tilemap, _resumen), above_data = \
        snes_convert.convert_layers(base, above_img)
    mapa = snes_convert.render_converted(tile_data, cram, tilemap)
    encima_todo = snes_convert.render_above(cram, above_data)

    chipset = renderer.database.chipsets[game_map.chipset_id]
    passable = passability_map(game_map, build_passability(chipset))
    if args.hero_tile:
        x, y = args.hero_tile[0] * TILE, args.hero_tile[1] * TILE
        direction = DIRECTIONS[args.dir or "down"]
    else:
        ocupadas = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
        x, y, direction = hero_position(args.walk, passable, game_map.width,
                                        game_map.height, ocupadas)
    cam_x, cam_y = camera_for(x, y, game_map.width * 2, game_map.height * 2)

    view = mapa.crop((cam_x, cam_y, cam_x + SCREEN_W, cam_y + SCREEN_H))

    images = {}

    def charset_image(name):
        if name not in images:
            path = find_resource([REPO, args.game_dir, RTP_DIR], "CharSet", name)
            if not path:
                sys.exit("no encuentro el CharSet %r" % name)
            images[name] = load_image(path)
        return images[name]

    # Todo lo que se dibuja encima del mapa, con la clave con la que RM2k lo
    # ordena: primero por capa y recién después por Y. Se pinta de atrás hacia
    # adelante, que es al revés del orden en que van a OAM.
    actors = [(snes_convert.sort_key(npc["layer"], npc["y"] * TILE),
               npc["charset"], npc["index"], npc["pose"],
               npc["x"] * TILE, npc["y"] * TILE,
               npc["layer"] == md_convert.LAYER_ABOVE)
              for npc in collect_npcs(game_map)]
    actors.append((snes_convert.sort_key(md_convert.LAYER_SAME, y),
                   args.charset, args.charset_index,
                   direction * 3 + STAND, x, y, False))

    # En OAM van del frente hacia el fondo, que es al revés del orden en que se
    # pintan. La consola recorre ese mismo orden para decidir qué entra en cada
    # línea, así que hay que respetarlo para reproducir lo que se pierde.
    order = sorted(actors, key=lambda a: a[0], reverse=True)
    sprites = []
    for _key, name, index, pose, px, py, arriba in order:
        sprites.append((pose_image(charset_image(name), index, pose),
                        px - 4 - cam_x, py - 16 - cam_y, arriba))

    # La capa que va por encima del héroe se compone entre los sprites comunes y
    # los eventos marcados "above", que es el orden de RM2k y el que el hardware
    # reproduce con las prioridades del modo 3.
    encima = encima_todo.crop((cam_x, cam_y,
                               cam_x + SCREEN_W, cam_y + SCREEN_H))
    excedidas = draw_actors(view, sprites, encima)
    if excedidas:
        print("  %d líneas pasan el límite de sprites de la consola: ahí se"
              " pierden objetos y no se comparan" % len(excedidas))
    # El archivo se escribe siempre, aunque no haya nada que excluir. Si sólo se
    # escribiera cuando sobran sprites, al cambiar de mapa quedaría el del
    # anterior y la comparación seguiría salteando líneas que ya no
    # corresponden: aflojaría la prueba justo donde nadie está mirando.
    if args.saltar:
        with open(args.saltar, "w") as handle:
            handle.write("".join("%d\n" % y for y in excedidas))

    view.convert("RGB").save(args.output)
    print("esperado -> %s: héroe en (%d,%d) mirando %s, cámara en (%d,%d)"
          % (args.output, x, y, args.walk if args.walk != "none" else "abajo",
             cam_x, cam_y))


if __name__ == "__main__":
    main()

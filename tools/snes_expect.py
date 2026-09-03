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

Y tampoco alcanza con dibujar el mapa que se pidió. Al entrar a uno, la ROM le
corre sus eventos automáticos, y ésos prenden switches, tiñen la pantalla y
teletransportan: acá se corre el mismo bytecode, con el mismo estado, para
terminar dibujando el mapa donde la consola realmente terminó.

Uso:
    python3 tools/snes_expect.py --map-id 7 --walk right -o esperado.png
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eventos
import lcf
import md_convert
import snes_convert
from md_convert import (collect_doors, collect_npcs, passability_map,
                        puede_pasar)
from render_map import (GAME_DIR, REPO, RTP_DIR, Renderer, build_passability,
                        find_resource, load_image)

# El paso del héroe son dieciséis pixeles y la ROM avanza WALK_SPEED = 2 por
# cuadro, así que cada celda cuesta ocho cuadros. Este número es el puente entre
# la referencia —que sabe cuántas celdas se camina— y el emulador, que ahora
# corre cuadros exactos en vez de segundos de reloj. Si alguna vez cambia
# WALK_SPEED en main.s, cambia acá: son los dos lados de la misma cuenta y
# separarlos es el error que este repo ya cometió cinco veces.
CUADROS_POR_CELDA = 8

# El ciclo de caminata de la ROM, de `animate_hero` en main.s: cuatro pasos
# sobre tres columnas del CharSet —0, 1, 2, 1—, uno cada ANIM_FRAMES cuadros, y
# quieto vuelve al del medio. Se arranca en el 1 con el contador lleno.
#
# Esto no lo modelaba nadie de este lado, y por eso las poses de caminata no las
# verificaba ninguna prueba: cuando el héroe choca contra la pared `moving` es
# cero, así que la única pose que llegaba a compararse era la parada.
ANIM_FRAMES = 6
ANIM_INICIAL = 1


def columna_de_caminata(cuadros_moviendose):
    """En qué columna del CharSet está el héroe tras N cuadros caminando."""
    paso = (ANIM_INICIAL + cuadros_moviendose // ANIM_FRAMES) % 4
    return 1 if paso == 3 else paso

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


class Mundo:
    """Los mapas que entraron en la ROM, cargados a medida que se los pisa.

    `ids` es la tabla de la ROM en su orden, porque el orden es dato: un
    teletransporte compilado no guarda el número de mapa de RM2k sino el índice
    en esta tabla. Si acá estuviera en otro orden, el mismo bytecode llevaría a
    otro mapa y la comparación mediría dos ROMs distintas.
    """

    def __init__(self, renderer, game_dir, ids):
        self.renderer = renderer
        self.game_dir = game_dir
        self.ids = list(ids)
        self.indices = {map_id: i for i, map_id in enumerate(self.ids)}
        self.cache = {}
        self.paginas_cache = {}

    def paginas(self, map_id):
        """Las páginas de evento del mapa, compiladas como las compiló la ROM."""
        if map_id not in self.paginas_cache:
            self.paginas_cache[map_id] = eventos.paginas_del_mapa(
                self.mapa(map_id)[0], self.indices.get)
        return self.paginas_cache[map_id]

    def mapa(self, map_id):
        if map_id not in self.cache:
            game_map = lcf.Map(os.path.join(self.game_dir,
                                            "Map%04d.lmu" % map_id))
            chipset = self.renderer.database.chipsets[game_map.chipset_id]
            passable = passability_map(game_map, build_passability(chipset))
            ocupadas = {(n["x"], n["y"]) for n in collect_npcs(game_map)}
            puertas = {(p["x"], p["y"]): p for p in collect_doors(game_map)
                       if p["mapa"] in self.ids}
            self.cache[map_id] = (game_map, passable, ocupadas, puertas)
        return self.cache[map_id]


# El mismo tope que `saltos_restantes` en la ROM: dos mapas que se
# teletransporten entre sí colgarían a los dos lados, y una prueba colgada no
# le dice nada a nadie.
SALTOS_MAX = 8


def entrar_al_mapa(mundo, estado, map_id, entrada=None):
    """Entra a un mapa y le corre los eventos automáticos, como `cargar_mapa`.

    Primero se para al héroe —donde diga la puerta o el teletransporte que nos
    trajo, y si no, donde el mapa lo pone— y recién después corren los eventos,
    que es el orden de la ROM: una página que teletransporta pisa esa posición,
    pero una que sólo tiñe la deja donde estaba.

    Si un evento pide mudarse, el ciclo se repite acá y no adentro del
    intérprete, con el mismo tope de vueltas que la consola.

    `estado` sobrevive a los mapas: los switches que prende una página son los
    que deciden qué página está activa en el siguiente, y el tinte se queda
    puesto hasta que otro lo cambie.
    """
    saltos = SALTOS_MAX
    while True:
        game_map, passable, ocupadas, _puertas = mundo.mapa(map_id)
        if entrada is None:
            x, y = snes_convert.inicio_del_mapa(mundo.renderer, map_id,
                                                passable, game_map.width,
                                                game_map.height, ocupadas)
        else:
            x, y = entrada
            entrada = None
        salto = eventos.correr_automaticos(mundo.paginas(map_id), estado)
        if salto is None:
            return map_id, x, y
        saltos -= 1
        if not saltos:
            return map_id, x, y     # demasiadas vueltas: se queda en este mapa
        map_id = mundo.ids[salto[0]]
        entrada = (salto[1], salto[2])


def hero_position(mundo, estado, map_id, direction_name, inicio=None,
                  avance=None):
    """En qué mapa y en qué celda termina el héroe, y hacia dónde mira.

    No se estima: se entra al mapa como entra la ROM —corriéndole los eventos—
    y después se camina con sus mismas reglas, de a un paso, mirando entre paso
    y paso si la celda tiene una puerta, que es cuando la consola la mira. Si la
    tiene, se cambia de mapa —y al mapa nuevo también le corren sus eventos— y
    se sigue caminando desde donde deja, con la cruceta todavía apretada.

    Devuelve (mapa, x, y, dirección) con x e y en pixeles.
    """
    map_id, x, y = entrar_al_mapa(mundo, estado, map_id, inicio)
    step = WALK[direction_name]
    direction = DIRECTIONS.get(direction_name, DIRECTIONS["down"])
    if step is None:
        return map_id, x * TILE, y * TILE, DIRECTIONS["down"], 0
    desde = (x, y)

    # Cuántas celdas camina. Hasta ahora este número se calculaba y se tiraba;
    # es el que dice cuántos cuadros tarda la ROM en llegar, porque el paso son
    # dieciséis pixeles a WALK_SPEED = 2 por cuadro, o sea ocho cuadros por
    # celda. Antes la prueba pedía "45 segundos, seguro alcanza"; con esto pide
    # un número que sale de la misma referencia contra la que se compara.
    pasos = 0

    # El tope es por si dos puertas se apuntan entre sí: la ROM se quedaría
    # rebotando y la referencia también, y colgar una prueba no ayuda a nadie.
    for _ in range(10000):
        game_map, passable, _ocupadas, puertas = mundo.mapa(map_id)
        # Las celdas ocupadas sólo sirven para elegir dónde arranca. No se le
        # pasan a la caminata: en RM2k un NPC bloquea el paso, pero la ROM
        # todavía no lo mira, y modelar acá algo que la consola no hace es
        # inventar una diferencia.
        if not puede_pasar(passable, game_map.width, game_map.height,
                           x, y, step[0], step[1]):
            break
        x, y = x + step[0], y + step[1]
        pasos += 1
        puerta = puertas.get((x, y))
        if puerta is None:
            continue
        if avance is not None:
            # Un avance a mitad de camino no cruza puertas: del otro lado el
            # mapa es otro y la cuenta de pixeles desde el arranque no
            # significa nada. Se corta acá en vez de dibujar cualquier cosa.
            sys.exit("el avance pedido cruza una puerta en el paso %d; este "
                     "caso no sirve para comparar a mitad de camino" % pasos)
        map_id, x, y = entrar_al_mapa(mundo, estado, puerta["mapa"],
                                      (puerta["destino_x"], puerta["destino_y"]))
    if avance is not None:
        if avance > pasos * TILE:
            sys.exit("se pidió un avance de %d px pero la caminata son %d "
                     "celdas = %d px" % (avance, pasos, pasos * TILE))
        return (map_id,
                desde[0] * TILE + step[0] * avance,
                desde[1] * TILE + step[1] * avance,
                direction, pasos)
    return map_id, x * TILE, y * TILE, direction, pasos


def tenir_imagen(view, tinte):
    """El tinte del evento, aplicado color por color.

    La consola no tiñe la pantalla sino CGRAM, y como cada pixel del fondo, de
    la capa de encima y de los sprites sale de una entrada de CGRAM, teñir cada
    color de la imagen ya compuesta da exactamente lo mismo.

    La cuenta es la de `eventos.tenir`, con enteros y sobre los 15 bits. Hacerla
    sobre los 24 del PNG redondearía distinto y la comparación fallaría por el
    redondeo en vez de por la consola.
    """
    pixels = view.load()
    memo = {}
    for y in range(view.height):
        for x in range(view.width):
            color = pixels[x, y]
            nuevo = memo.get(color)
            if nuevo is None:
                r, g, b = color[:3]
                palabra = eventos.tenir(
                    (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10), tinte)
                nuevo = ((palabra & 0x1F) << 3,
                         ((palabra >> 5) & 0x1F) << 3,
                         ((palabra >> 10) & 0x1F) << 3) + color[3:]
                memo[color] = nuevo
            pixels[x, y] = nuevo
    return view


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
    parser.add_argument("--walk", nargs="+", default=["none"],
                        choices=sorted(WALK),
                        help="una o varias direcciones. Con varias, -o y --saltar\n"
                             "tienen que llevar un {} donde va la dirección: se\n"
                             "convierte el mapa una sola vez para todas")
    parser.add_argument("--grupo", nargs="+", type=int, default=None,
                        metavar="ACTOR",
                        help="el grupo con el que arranca, por ids de actor. El gráfico "
                             "del héroe es el del primero, que es como lo decide "
                             "RM2k. Por defecto, el de la base: este juego "
                             "arranca con el actor 10, DummyHero, cuyo sprite es "
                             "una celda vacía a propósito")
    parser.add_argument("--charset", default=None,
                        help="forzar el CharSet del héroe; por defecto sale\n"
                             "del primero del grupo, que es como lo decide RM2k")
    parser.add_argument("--heroe-encima", action="store_true",
                        help="el héroe en prioridad 2, por encima de "
                             "la capa que debería taparlo. El otro "
                             "lado del mismo flag de snes_convert.py")
    parser.add_argument("--charset-index", type=int, default=None)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--saltar", help="archivo donde anotar las líneas que "
                        "pasan el límite de sprites")
    parser.add_argument("--avance", type=int, nargs="+", default=None,
                        metavar="PX",
                        help="dibujar al héroe a mitad de camino, con este "
                             "avance en pixeles desde donde arrancó la "
                             "caminata, y en la pose de caminata que le toca. "
                             "Sin esto se dibuja donde termina, que es la "
                             "única pose que las pruebas miraban hasta ahora. "
                             "Con varios avances el mapa se convierte una sola "
                             "vez y el {} de -o lleva el avance en vez de la "
                             "dirección")
    parser.add_argument("--plan", help="archivo donde anotar, por dirección, "
                        "cuántas celdas camina el héroe y cuántos cuadros le "
                        "lleva. Es lo que le dice al emulador cuánto correr, "
                        "en vez de un número de segundos elegido a ojo")
    parser.add_argument("--mapas", nargs="*", type=int, default=[], metavar="ID",
                        help="los otros mapas que entraron en la ROM, en el "
                             "mismo orden que le pasaste al conversor. Sin esto "
                             "una puerta no lleva a ningún lado, que es lo que "
                             "pasa en la consola")
    parser.add_argument("--inicial", type=int, default=0, metavar="N",
                        help="en qué índice de la tabla arranca la ROM, igual "
                             "que en el conversor")
    parser.add_argument("--hero-tile", nargs=2, type=int, metavar=("TX", "TY"),
                        help="poner al héroe en esta celda en vez de calcularla; "
                             "sirve para averiguar dónde lo dejó la ROM")
    parser.add_argument("--dir", default=None, choices=sorted(DIRECTIONS),
                        help="hacia dónde mira, si se fija la celda a mano")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args()

    renderer = Renderer(args.game_dir)

    # El gráfico del héroe sale del grupo, no de acá. En RM2k lo da el primero
    # de la lista, y este juego arranca con el actor 10 —'DummyHero', que es
    # Chubby2[2]—. Hasta ahora había un default puesto a mano que daba
    # Future1[0], o sea el sprite de otro personaje; los dos lados de la
    # comparación lo tenían igual de mal, así que el cero no lo delataba.
    # --charset queda para forzarlo a mano cuando hace falta.
    grupo = args.grupo if args.grupo else renderer.database.party

    # El mundo son los mapas que entraron en la ROM, en el mismo orden y armado
    # con la misma regla que usa el conversor, incluido que un mapa repetido en
    # --mapas no entra dos veces. Sin --mapas es uno solo y no hay puerta que
    # lleve a ningún lado, que es como se comportaba esto antes de que hubiera
    # varios.
    tabla = [args.map_id] + [m for m in args.mapas if m != args.map_id]
    if not 0 <= args.inicial < len(tabla):
        sys.exit("--inicial %d pero la tabla tiene %d mapas"
                 % (args.inicial, len(tabla)))
    mundo = Mundo(renderer, args.game_dir, tabla)

    # Los CharSets y los mapas ya convertidos se comparten entre las
    # direcciones. Convertir un mapa es lo más caro de todo esto —el 52 son
    # 14 segundos— y las cinco direcciones de un mapa comparten absolutamente
    # todo lo caro: los tiles, el reparto de paletas, el reuso y los
    # espejados. Lo único que cambia entre ellas es dónde termina el héroe y
    # dónde queda la cámara. Antes cada dirección era un proceso aparte y
    # rehacía la conversión entera; ahora se hace una vez por mapa.
    images = {}
    convertidos = {}

    def charset_image(name):
        if name not in images:
            path = find_resource([REPO, args.game_dir, RTP_DIR], "CharSet", name)
            if not path:
                sys.exit("no encuentro el CharSet %r" % name)
            images[name] = load_image(path)
        return images[name]

    def convertir(map_id):
        if map_id not in convertidos:
            game_map = mundo.mapa(map_id)[0]
            base, above_img = renderer.render_layers(game_map)
            if base is None:
                sys.exit("no encuentro el chipset del mapa %d" % map_id)
            # La referencia se arma desde los datos convertidos, no desde el
            # render: entre uno y otro están la fusión de colores, el reparto en
            # paletas, el reuso de tiles y los espejados, y todo eso aparecería
            # como diferencia aunque la consola hiciera exactamente lo que se le
            # pidió. Las dos capas van juntas con la misma función que usa el
            # conversor, porque el reparto de CGRAM depende de las dos.
            (tile_data, cram, tilemap, _resumen), above_data = \
                snes_convert.convert_layers(base, above_img)
            convertidos[map_id] = (
                game_map,
                snes_convert.render_converted(tile_data, cram, tilemap),
                snes_convert.render_above(cram, above_data))
        return convertidos[map_id]

    def salida(patron, etiqueta):
        """El nombre de archivo de esta vuelta.

        La etiqueta es la dirección, o el avance cuando se piden varios. Con una
        sola vuelta y sin `{}` el nombre queda igual que siempre, que es lo que
        mantiene andando a las recetas que pasan una dirección sola.
        """
        return patron.format(etiqueta) if "{}" in patron else patron

    # Qué se recorre: o varias direcciones, o varios avances de una misma
    # dirección. Los dos casos comparten la conversión del mapa, que es lo caro,
    # y en los dos el {} de -o lleva lo que está variando.
    if args.avance and len(args.avance) > 1:
        if len(args.walk) != 1:
            sys.exit("con varios avances hay que pedir una sola dirección")
        vueltas = [(args.walk[0], px, str(px)) for px in args.avance]
    else:
        px = args.avance[0] if args.avance else None
        vueltas = [(w, px, w) for w in args.walk]

    plan = []
    for walk, avance, etiqueta in vueltas:
        # Los switches arrancan apagados y la pantalla sin teñir, como una
        # partida nueva de RM2k, y cada dirección arranca de cero: el estado lo
        # mueven los eventos y no puede filtrarse de una caminata a la otra.
        estado = eventos.Estado(grupo)

        # Adónde se llega es lo primero: entre los eventos del arranque y las
        # puertas que cruce la caminata, el mapa que hay que dibujar bien puede
        # no ser el que se pidió.
        inicio = tuple(args.hero_tile) if args.hero_tile else None
        map_id, x, y, direction, pasos = hero_position(mundo, estado,
                                                       tabla[args.inicial],
                                                       walk, inicio,
                                                       avance)
        if args.hero_tile and args.dir:
            direction = DIRECTIONS[args.dir]

        # Con qué se dibuja al héroe se decide *después* de correr los eventos,
        # no antes: `ChangePartyMembers` puede cambiar el líder del grupo, y en
        # RM2k el gráfico del héroe es el del líder —`AddActor` y `RemoveActor`
        # llaman los dos a `ResetGraphic`—. La página del mapa 121 hace
        # exactamente eso: saca al 10 y mete al 14, así que el héroe pasa de
        # `DummyHero`, que es una celda vacía, a Talan.
        if args.charset is not None:
            charset, charset_index = args.charset, args.charset_index or 0
        else:
            charset, charset_index = renderer.database.lider(estado.grupo)

        game_map, mapa, encima_todo = convertir(map_id)
        cam_x, cam_y = camera_for(x, y, game_map.width * 2, game_map.height * 2)
        view = mapa.crop((cam_x, cam_y, cam_x + SCREEN_W, cam_y + SCREEN_H))

        # Todo lo que se dibuja encima del mapa, con la clave con la que RM2k lo
        # ordena: primero por capa y recién después por Y. Se pinta de atrás
        # hacia adelante, que es al revés del orden en que van a OAM.
        actors = [(snes_convert.sort_key(npc["layer"], npc["y"] * TILE),
                   npc["charset"], npc["index"], npc["pose"],
                   npc["x"] * TILE, npc["y"] * TILE,
                   npc["layer"] == md_convert.LAYER_ABOVE)
                  for npc in collect_npcs(game_map)]
        # El último campo es si va por encima de la capa de encima. Para el
        # héroe es falso salvo en la ROM de `snes-encima`, donde su prioridad
        # de objeto sube a 2 —el mismo bit que llevan los eventos "above"— y
        # el hardware lo pone adelante de BG2. Su capa para ordenarlo contra
        # los NPCs no cambia: la prioridad es de la PPU y la capa es de RM2k.
        # La pose: parado al final de la caminata, y la del ciclo cuando se
        # pide un avance. El héroe se mueve WALK_SPEED = 2 pixeles por cuadro,
        # así que los cuadros que lleva moviéndose son el avance sobre dos.
        if avance is None:
            columna = STAND
        else:
            columna = columna_de_caminata(avance // 2)
        actors.append((snes_convert.sort_key(md_convert.LAYER_SAME, y),
                       charset, charset_index,
                       direction * 3 + columna, x, y, args.heroe_encima))

        # En OAM van del frente hacia el fondo, que es al revés del orden en que
        # se pintan. La consola recorre ese mismo orden para decidir qué entra
        # en cada línea, así que hay que respetarlo para reproducir lo que se
        # pierde.
        order = sorted(actors, key=lambda a: a[0], reverse=True)
        sprites = []
        for _key, name, index, pose, px, py, arriba in order:
            sprites.append((pose_image(charset_image(name), index, pose),
                            px - 4 - cam_x, py - 16 - cam_y, arriba))

        # La capa que va por encima del héroe se compone entre los sprites
        # comunes y los eventos marcados "above", que es el orden de RM2k y el
        # que el hardware reproduce con las prioridades del modo 3.
        encima = encima_todo.crop((cam_x, cam_y,
                                   cam_x + SCREEN_W, cam_y + SCREEN_H))
        excedidas = draw_actors(view, sprites, encima)
        if excedidas:
            print("  %d líneas pasan el límite de sprites de la consola: ahí se"
                  " pierden objetos y no se comparan" % len(excedidas))
        # El archivo se escribe siempre, aunque no haya nada que excluir. Si
        # sólo se escribiera cuando sobran sprites, al cambiar de mapa quedaría
        # el del anterior y la comparación seguiría salteando líneas que ya no
        # corresponden: aflojaría la prueba justo donde nadie está mirando.
        if args.saltar:
            with open(salida(args.saltar, etiqueta), "w") as handle:
                handle.write("".join("%d\n" % y for y in excedidas))

        # El tinte va al final, sobre todo lo que se dibujó: en la consola es
        # una transformación de CGRAM, y CGRAM la comparten el fondo, la capa de
        # encima y los sprites.
        view = tenir_imagen(view, estado.tinte)

        plan.append((walk, pasos, pasos * CUADROS_POR_CELDA))
        destino = salida(args.output, etiqueta)
        view.convert("RGB").save(destino)
        print("esperado -> %s: mapa %d, héroe en (%d,%d) mirando %s, cámara en"
              " (%d,%d)%s"
              % (destino, map_id, x, y,
                 walk if walk != "none" else "abajo", cam_x, cam_y,
                 "" if estado.tinte == (eventos.TINTE_NEUTRO,) * 3
                 else ", tinte %d/%d/%d" % estado.tinte))
        if pasos:
            print("  camina %d celdas = %d cuadros a %d por celda"
                  % (pasos, pasos * CUADROS_POR_CELDA, CUADROS_POR_CELDA))

    if args.plan:
        with open(args.plan, "w") as handle:
            for walk, pasos, cuadros in plan:
                handle.write("%s %d %d\n" % (walk, pasos, cuadros))


if __name__ == "__main__":
    main()

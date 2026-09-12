#!/usr/bin/env python3
"""Renderiza un mapa de A Blurred Line (RPG Maker 2000) a un PNG.

Las dos capas de tiles más los eventos en su posición inicial, tal como se
verían al empezar una partida nueva. Sin panorama y sin el héroe.
Es el paso cero del port a Mega Drive: confirmar que podemos leer los datos
originales y reconstruir lo que se ve en pantalla.

Uso:
    python3 tools/render_map.py                 # el mapa por defecto
    python3 tools/render_map.py --map-id 8
    python3 tools/render_map.py --map Maps/Map0001.lmu -o /tmp/mapa.png
"""

import argparse
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import charset
import lcf
import rm2k
from chipset import ANIMATED, ChipsetAtlas, TERRAIN, TILE, UPPER

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# El proyecto RM2k original. Es una copia dentro del contenedor, no un montaje
# del host: así el directorio original ni siquiera es alcanzable desde acá, que
# protege más que un montaje de sólo lectura. Todas las herramientas aceptan
# --game-dir para apuntar a otro lado.
GAME_DIR = os.environ.get("ABL_GAME_DIR", "/extras/abl-rm")
# El RTP de Don Miguel (junio de 2000), extraído de RTPE.EXE. No es el RTP
# "oficial": el RPG Maker 2000 que se usaba fuera de Japón era su traducción, y
# de paso le agregó archivos propios (Future1-3, entre otros) que ABL usa. El
# RTP libre de EasyRPG no sirve acá: es un reemplazo con arte distinto.
# El RTP de Don Miguel vive en /extras, del mismo lado que el juego original y
# por la misma razón: no es nuestro para redistribuir y no tiene por qué estar
# en el árbol. Antes era `RTP/` adentro del repo, excluido por .gitignore, que
# es la peor combinación —ocupaba lugar, no se versionaba, y parecía del
# proyecto—. Con ABL_RTP_DIR se apunta a otra copia.
RTP_DIR = os.environ.get("ABL_RTP_DIR", "/extras/rtp")

DEFAULT_MAP_ID = 1


def find_resource(dirs, folder, name, extensions=(".png", ".bmp")):
    """Busca <dir>/<folder>/<name>.<ext> sin distinguir mayúsculas.

    RM2k guarda los nombres sin extensión y el juego original corría en
    Windows, así que los .lmu no dicen nada del case real del archivo.
    """
    for directory in dirs:
        for entry in os.listdir(directory) if os.path.isdir(directory) else []:
            if entry.lower() != folder.lower():
                continue
            subdir = os.path.join(directory, entry)
            for filename in os.listdir(subdir):
                base, ext = os.path.splitext(filename)
                if base.lower() == name.lower() and ext.lower() in extensions:
                    return os.path.join(subdir, filename)
    return None


def load_image(path):
    image = Image.open(path)
    if image.mode == "P":
        # En RM2k el color 0 de la paleta es el color key.
        image.info["transparency"] = 0
    return image.convert("RGBA")


def build_passability(chipset):
    """Tabla de flags por ID de tile, como la arma lmu2png (main.cpp).

    Sólo la usamos para decidir si un tile va antes o después del jugador; acá
    no hay jugador, pero define el orden de dibujado entre las dos capas.
    """
    flags = bytearray(65536)
    lower, upper = chipset.passable_lower, chipset.passable_upper

    for i in range(3):          # agua A/B/C
        flags[1000 * i:1000 * i + 1000] = bytes([lower[i]]) * 1000
    for i in range(3):          # tiles animados
        flags[3000 + i * 50:3050 + i * 50] = bytes([lower[3 + i]]) * 50
    for i in range(12):         # autotiles de terreno
        flags[4000 + i * 50:4050 + i * 50] = bytes([lower[6 + i]]) * 50
    for i in range(144):        # páginas de tiles comunes
        flags[5000 + i] = lower[18 + i]
        flags[10000 + i] = upper[i]
    return flags


def draw_tiles(image, atlas, game_map, flags, pass_upper, pasos=(0, 0)):
    """Dibuja los tiles de ambas capas que caen en la pasada pedida.

    Un tile de la capa baja con flags 0x30 y uno de la alta con 0x10 se dibujan
    por encima del jugador; el resto, por debajo. Es lo que decide si un evento
    queda tapado por el techo o parado sobre él.

    `pasos` son los dos de la animación del ChipSet —agua y tiles animados—,
    que eligen qué dibujo de cada familia se pinta. Ver `render_tile`.
    """
    for y in range(game_map.height):
        row = y * game_map.width
        for x in range(game_map.width):
            lower_tile = game_map.lower_layer[row + x]
            if bool(flags[lower_tile] & 0x30) == pass_upper:
                atlas.render_tile(image, x, y, lower_tile, *pasos)

            upper_tile = game_map.upper_layer[row + x]
            if bool(flags[upper_tile] & 0x10) == pass_upper:
                atlas.render_tile(image, x, y, upper_tile, *pasos)


# Las tramas con las que se dibuja un evento translúcido, y qué pixel se cae.
# RM2k dibuja al 160 de 255, o sea al 63%: `cinco_de_ocho` es el que más se le
# acerca. El resto están para poder comparar en un televisor de verdad, que es
# donde esto se decide: el barrido de un CRT difumina **a lo largo de la línea**,
# así que las columnas alternadas se funden y el damero no.
TRAMAS = {
    "damero":        lambda x, y: (x + y) % 2 == 1,
    "columnas":      lambda x, y: x % 2 == 1,
    "filas":         lambda x, y: y % 2 == 1,
    "cinco_de_ocho": lambda x, y: ((y % 2) * 4 + (x % 4)) in (1, 4, 7),
    "tres_de_cuatro": lambda x, y: x % 2 == 1 and y % 2 == 1,
}


class Charsets:
    """Cache de CharSets, que se repiten mucho entre los eventos de un mapa."""

    def __init__(self, search_dirs, atlas_por_nombre=None, fondo_de_mapa=None):
        self.search_dirs = search_dirs
        self.images = {}
        self.missing = set()
        self.atlas_por_nombre = atlas_por_nombre
        self.fondo_de_mapa = fondo_de_mapa

    def get(self, name):
        if name not in self.images:
            base, donde = rm2k.parte_horneada(name)
            if donde is not None:
                self.images[name] = self._horneado(base, *donde)
            elif name.endswith(rm2k.TRAMA_SUFIJO):
                self.images[name] = self._tramado(
                    name[:-len(rm2k.TRAMA_SUFIJO)])
            elif name.startswith(rm2k.TILE_PREFIX):
                self.images[name] = self._de_tile(name)
            else:
                path = find_resource(self.search_dirs, "CharSet", name)
                if not path:
                    self.missing.add(name)
                self.images[name] = load_image(path) if path else None
        return self.images[name]

    def _tramado(self, name):
        """El CharSet de un evento translúcido: el mismo, con parte de sus
        pixeles transparentes. Ver `rm2k.TRAMA_SUFIJO` y `TRAMAS`."""
        base = self.get(name)
        if base is None:
            return None
        image = base.convert("RGBA")
        pix = image.load()
        cae = TRAMAS[rm2k.TRAMA_PATRON]
        for y in range(image.height):
            for x in range(image.width):
                if cae(x, y):
                    pix[x, y] = (0, 0, 0, 0)
        return image

    def _horneado(self, base, map_id, tile_x, tile_y):
        """El CharSet de un evento translúcido, con la mezcla ya calculada.

        RM2k lo dibuja al 160 de 255 sobre lo que haya detrás. Como el evento
        es estático —lo son los 70 del juego— y el fondo también, la mezcla se
        calcula una vez acá, contra el fondo real de la celda donde está
        parado, y queda horneada en el gráfico: el sprite sale opaco y con los
        colores exactos, sin trama.

        El fondo es la **capa de abajo** del mapa, que es lo único que queda
        detrás del sprite: la de encima se dibuja después y lo tapa, así que en
        los pixeles donde el sprite se ve el fondo es éste. Y se toma en
        `(x*16 - 4, y*16 - 16)`, que es donde `charset.draw` apoya el cuadro de
        24x32 sobre la celda; como todas las poses del CharSet caen en el mismo
        lugar de la pantalla, cada una se mezcla contra el mismo pedazo y
        alcanza con mirar la posición del pixel adentro de su cuadro.
        """
        sheet = self.get(base)
        fondo = self.fondo_de_mapa(map_id) if self.fondo_de_mapa else None
        if sheet is None or fondo is None:
            return sheet
        image = sheet.convert("RGBA")
        pix = image.load()
        atras = fondo.load()
        ox = tile_x * TILE + charset.OFFSET_X
        oy = tile_y * TILE + charset.OFFSET_Y
        alfa = rm2k.OPACIDAD_TRANSLUCIDO
        for y in range(image.height):
            fy = oy + y % charset.SPRITE_HEIGHT
            for x in range(image.width):
                r, g, b, a = pix[x, y]
                if not a:
                    continue
                fx = ox + x % charset.SPRITE_WIDTH
                if 0 <= fx < fondo.width and 0 <= fy < fondo.height:
                    br, bg, bb = atras[fx, fy][:3]
                else:
                    br = bg = bb = 0        # fuera del mapa la consola ve negro
                pix[x, y] = ((r * alfa + br * (255 - alfa)) // 255,
                             (g * alfa + bg * (255 - alfa)) // 255,
                             (b * alfa + bb * (255 - alfa)) // 255, 255)
        return image

    def _de_tile(self, name):
        """Un CharSet inventado con un tile de la página alta del chipset en
        las doce poses del personaje 0, apoyado en la celda: el cuadro de un
        personaje mide 24x32 y se dibuja en (x - 4, y - 16), así que el tile
        de 16x16 va en (4, 16) de cada cuadro. Es lo que hace `draw_events`
        con un evento sin CharSet, sólo que como sprite, para que se mueva y
        se cambie de lugar como cualquier otro."""
        _, chipset, indice = name.split(":", 2)
        atlas = self.atlas_por_nombre(chipset) if self.atlas_por_nombre else None
        if atlas is None:
            self.missing.add(name)
            return None
        tile = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        atlas.render_tile(tile, 0, 0, UPPER + int(indice))
        image = Image.new("RGBA", (288, 256), (0, 0, 0, 0))
        for pose in range(12):
            image.paste(tile, ((pose % 3) * 24 + 4, (pose // 3) * 32 + 16))
        return image


def draw_events(image, atlas, charsets, events, layer, ignore_conditions):
    """Dibuja los eventos de una capa, ordenados por Y.

    Un evento sin CharSet se dibuja como un tile de la página alta del chipset:
    así están hechas las puertas, los cofres y buena parte del decorado.
    """
    for event in sorted(events, key=lambda e: e.y):
        page = event.active_page(ignore_conditions)
        if page is None or page.layer != layer:
            continue

        if not page.character_name:
            atlas.render_tile(image, event.x, event.y, UPPER + page.character_index)
            continue

        sheet = charsets.get(page.character_name)
        if sheet is not None:
            charset.draw(image, sheet, event.x, event.y, page.character_index,
                         page.character_direction, page.character_pattern)


class Renderer:
    """Todo lo que se comparte entre mapas: el juego, el RTP y los cachés."""

    def __init__(self, game_dir=GAME_DIR, rtp_dir=RTP_DIR):
        self.database = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
        self.tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
        self.game_dir = game_dir
        self.search_dirs = [REPO, game_dir, rtp_dir]
        self.charsets = Charsets(self.search_dirs, self.atlas_por_nombre,
                                 self.fondo_de_mapa)
        self.atlases = {}
        self.fondos = {}
        self.missing_chipsets = set()

    def fondo_de_mapa(self, map_id):
        """La capa de abajo de un mapa, para hornear los translúcidos.

        Se cachea porque un mapa con varios translúcidos la pediría una vez por
        evento, y renderizar las capas de un mapa grande no es gratis.
        """
        if map_id not in self.fondos:
            game_map = self.cargar_mapa(
                os.path.join(self.game_dir, "Map%04d.lmu" % map_id))
            self.fondos[map_id] = self.render_layers(game_map)[0]
        return self.fondos[map_id]

    def atlas(self, chipset):
        """Los ChipSets se repiten entre mapas y expandirlos no es gratis."""
        return self.atlas_por_nombre(chipset.filename)

    def atlas_por_nombre(self, filename):
        if filename not in self.atlases:
            path = find_resource(self.search_dirs, "ChipSet", filename)
            if not path:
                self.missing_chipsets.add(filename)
            self.atlases[filename] = ChipsetAtlas(load_image(path)) if path else None
        return self.atlases[filename]

    def cargar_mapa(self, path):
        """El mapa, con el nombre de su chipset puesto: `collect_npcs` lo
        necesita para los eventos que se dibujan con un tile."""
        game_map = lcf.Map(path)
        chipset = self.database.chipsets[game_map.chipset_id]
        game_map.chipset_nombre = chipset.filename
        # Y la pasabilidad de sus tiles, para los eventos que se dibujan con
        # uno en la capa de abajo: ver `rm2k.pasabilidad_del_tile`.
        game_map.pasabilidad_tiles = build_passability(chipset)
        return game_map

    def render_layers(self, game_map, pasos=(0, 0)):
        """El mapa en dos capas separadas, como las ordena RM2k.

        La de abajo es opaca y va detrás del héroe; la de arriba lleva sólo los
        tiles marcados como "por encima del héroe" y es transparente en todo lo
        demás. En el VDP van a planos distintos: la de abajo al B sin prioridad
        y la de arriba al A con prioridad, que es justo el orden del hardware.
        """
        chipset = self.database.chipsets[game_map.chipset_id]
        atlas = self.atlas(chipset)
        if atlas is None:
            return None, None

        flags = build_passability(chipset)
        size = (game_map.width * TILE, game_map.height * TILE)

        base = Image.new("RGBA", size, (0, 0, 0, 255))
        draw_tiles(base, atlas, game_map, flags, pass_upper=False, pasos=pasos)
        above = Image.new("RGBA", size, (0, 0, 0, 0))
        draw_tiles(above, atlas, game_map, flags, pass_upper=True, pasos=pasos)
        return base, above

    def capas_animadas(self, game_map):
        """Las capas del mapa y los otros dibujos de la animación del ChipSet.

        Devuelve `(base, encima, variantes)`, con `variantes` en la forma que
        pide `snes_convert.convert_layers`: por familia, los dibujos que **no**
        son el 0, que es `base`.

        Es el único lugar donde se decide qué dibujos hay, y lo usan las dos
        puntas —el conversor y la referencia—: si cada una los armara por su
        cuenta, la ROM y la referencia podrían estar animando cosas distintas.

        Sólo se renderiza lo que el mapa puede llegar a mover: un mapa sin agua
        ni tiles animados no paga nada. Que los dibujos de una familia salgan
        todos iguales —el agua del mapa 3 lo hace, porque el ChipSet la tiene
        dibujada tres veces igual— no hace falta detectarlo acá: `convert` no
        va a encontrar ninguna celda que cambie y la corrida sale vacía.
        """
        base, above = self.render_layers(game_map)
        if base is None:
            return None, None, {}
        tiene = {"agua": False, "animado": False}
        for tile in list(game_map.lower_layer) + list(game_map.upper_layer):
            if tile < ANIMATED:
                tiene["agua"] = True
            elif tile < TERRAIN:
                tiene["animado"] = True
        variantes = {}
        for familia, dibujos in rm2k.FAMILIAS_ANIMADAS:
            if not tiene[familia]:
                continue
            variantes[familia] = [
                self.render_layers(
                    game_map,
                    (d, 0) if familia == "agua" else (0, d))[0]
                for d in range(1, dibujos)]
        return base, above, variantes

    def render(self, game_map, draw_events_too=True, first_page=False):
        """El orden del motor: tiles bajos, los eventos que van debajo del héroe
        y a su altura, los tiles altos que tapan, y por último los eventos que
        van por encima de todo.
        """
        chipset = self.database.chipsets[game_map.chipset_id]
        atlas = self.atlas(chipset)
        if atlas is None:
            return None, 0

        flags = build_passability(chipset)
        events = game_map.events if draw_events_too else []

        image = Image.new("RGBA", (game_map.width * TILE, game_map.height * TILE),
                          (0, 0, 0, 255))
        draw_tiles(image, atlas, game_map, flags, pass_upper=False)
        for layer in (0, 1):
            draw_events(image, atlas, self.charsets, events, layer, first_page)
        draw_tiles(image, atlas, game_map, flags, pass_upper=True)
        draw_events(image, atlas, self.charsets, events, 2, first_page)

        drawn = sum(1 for e in events if e.active_page(first_page) is not None)
        return image, drawn


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", help="ruta a un .lmu concreto")
    parser.add_argument("--map-id", type=int, default=DEFAULT_MAP_ID,
                        help="número de mapa (default: %d)" % DEFAULT_MAP_ID)
    parser.add_argument("--maps-dir", default=GAME_DIR)
    parser.add_argument("--game-dir", default=GAME_DIR,
                        help="proyecto RM2k original, para RPG_RT.ldb/.lmt y chipsets")
    parser.add_argument("--rtp-dir", default=RTP_DIR,
                        help="RTP donde buscar los chipsets que no trae el juego")
    parser.add_argument("-o", "--output", help="PNG de salida (default: render/MapXXXX.png)")
    parser.add_argument("--no-events", action="store_true",
                        help="sólo los tiles, sin eventos")
    parser.add_argument("--first-page", action="store_true",
                        help="usar siempre la página 1 de cada evento en vez de la "
                             "última sin condiciones (el estado 'de autor')")
    args = parser.parse_args()

    renderer = Renderer(args.game_dir, args.rtp_dir)

    if args.map:
        map_path = args.map
        map_id = int(os.path.basename(map_path)[3:7])
    else:
        map_id = args.map_id
        map_path = os.path.join(args.maps_dir, "Map%04d.lmu" % map_id)

    game_map = lcf.Map(map_path)
    chipset = renderer.database.chipsets[game_map.chipset_id]

    print("Mapa %d %r: %dx%d tiles, chipset %d %r (%s)" % (
        map_id, renderer.tree.map_names.get(map_id, "?"),
        game_map.width, game_map.height,
        game_map.chipset_id, chipset.name, chipset.filename))

    image, drawn = renderer.render(game_map, not args.no_events, args.first_page)
    if image is None:
        sys.exit("No encuentro el chipset %r en %s"
                 % (chipset.filename, renderer.search_dirs))

    print("Eventos: %d dibujados de %d" % (drawn, len(game_map.events)))
    if renderer.charsets.missing:
        print("CharSets que faltan: %s"
              % ", ".join(sorted(renderer.charsets.missing)))

    output = args.output or os.path.join(REPO, "render", "Map%04d.png" % map_id)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    image.save(output)
    print("-> %s (%dx%d px)" % (output, image.width, image.height))


if __name__ == "__main__":
    main()

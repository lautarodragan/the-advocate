"""Las capas de un mapa de A Blurred Line (RPG Maker 2000) como imágenes.

Las dos capas de tiles resueltas contra su ChipSet, con los dibujos de la
animación del agua y de los tiles animados, y los CharSets que se les ponen
encima. Es lo que el conversor corta en tiles: ver `Renderer.capas_animadas`.
Sin panorama y sin eventos: de los eventos se ocupa el conversor.
"""

import array
import hashlib
import os

from PIL import Image

from rpgmaker import lcf
from rpgmaker import rm2k
from rpgmaker.recursos import GAME_DIR, RTP_DIR, find_resource
from rpgmaker.rm2k import TILE
from render import chipset_del_fork
from render.chipset import ANIMATED, ChipsetAtlas, TERRAIN, UPPER

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_image(path):
    image = Image.open(path)
    if image.mode == "P":
        # En RM2k el color 0 de la paleta es el color key.
        image.info["transparency"] = 0
    return image.convert("RGBA")


def _capa(tiles):
    """Una capa de tiles como bytes, para meterla en una clave de caché.

    Cuatro bytes por tile y no uno: un ID de tile llega a 10143, así que
    `bytes()` no sirve.
    """
    return array.array("i", tiles).tobytes()


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
        self.atlas_por_nombre = atlas_por_nombre
        self.fondo_de_mapa = fondo_de_mapa

    def get(self, name):
        if name not in self.images:
            base, donde = rm2k.parte_horneada(name)
            if name.endswith(rm2k.COPIA_SUFIJO):
                self.images[name] = self.get(name[:-len(rm2k.COPIA_SUFIJO)])
            elif donde is not None:
                self.images[name] = self._horneado(base, *donde)
            elif name.endswith(rm2k.TRAMA_SUFIJO):
                self.images[name] = self._tramado(
                    name[:-len(rm2k.TRAMA_SUFIJO)])
            elif name.startswith(rm2k.TILE_PREFIX):
                self.images[name] = self._de_tile(name)
            else:
                path = find_resource(self.search_dirs, "CharSet", name)
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
        ox = tile_x * TILE + rm2k.OFFSET_X
        oy = tile_y * TILE + rm2k.OFFSET_Y
        alfa = rm2k.OPACIDAD_TRANSLUCIDO
        for y in range(image.height):
            fy = oy + y % rm2k.SPRITE_HEIGHT
            for x in range(image.width):
                r, g, b, a = pix[x, y]
                if not a:
                    continue
                fx = ox + x % rm2k.SPRITE_WIDTH
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
        de 16x16 va en (4, 16) de cada cuadro. Es como RM2k dibuja un evento
        sin CharSet, sólo que como sprite, para que se mueva y
        se cambie de lugar como cualquier otro."""
        _, chipset, indice = name.split(":", 2)
        atlas = self.atlas_por_nombre(chipset) if self.atlas_por_nombre else None
        if atlas is None:
            return None
        tile = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        atlas.render_tile(tile, 0, 0, UPPER + int(indice))
        image = Image.new("RGBA", (288, 256), (0, 0, 0, 0))
        for pose in range(12):
            image.paste(tile, ((pose % 3) * 24 + 4, (pose // 3) * 32 + 16))
        return image


class Renderer:
    """Todo lo que se comparte entre mapas: el juego, el RTP y los cachés."""

    def __init__(self, game_dir=GAME_DIR, rtp_dir=RTP_DIR):
        self.database = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
        self.tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
        self.game_dir = game_dir
        self.search_dirs = [REPO, game_dir, rtp_dir]
        # Las imágenes de los ChipSets que agrega `parches/manual/` se
        # **arman** —el arte del juego no es nuestro para versionar, ver
        # `chipset_del_fork.py`— y van primero en la búsqueda: son las que
        # mandan cuando existen.
        self.search_dirs.insert(0, chipset_del_fork.imagenes(
            lambda carpeta, nombre: find_resource(self.search_dirs, carpeta,
                                                  nombre)))
        self.charsets = Charsets(self.search_dirs, self.atlas_por_nombre,
                                 self.fondo_de_mapa)
        self.atlases = {}
        self.fondos = {}
        self.huellas = {}
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

    def insumos_de_capas(self, game_map):
        """Todo lo que entra en las capas dibujadas de un mapa, sin dibujarlas.

        Es una lista de partes para una clave de caché, y existe para que quien
        cachea lo que sale de `capas_animadas` pueda preguntar **antes** de
        pagar el dibujo. Devuelve `None` cuando el ChipSet no está: ahí no hay
        insumo que valga y el que llama tiene que ir por el camino de siempre,
        que es el que sabe fallar.

        Vive acá y no en el conversor porque es este archivo el que sabe qué
        lee `render_layers`: las dos capas del mapa, su tamaño, y del ChipSet
        la pasabilidad —que decide qué tile va en cuál capa— y la imagen. Nada
        más del `.lmu` llega al dibujo. Si algún día `render_layers` mira algo
        que no está en esta lista, el caché se queda viejo sin avisar, y el
        único lugar donde eso se puede ver es acá al lado.

        Lo que **no** está, a propósito: el código que dibuja y la versión de
        Pillow. No son del mapa sino de la corrida, y los pone quien arma la
        clave.
        """
        chipset = self.database.chipsets[game_map.chipset_id]
        imagen = self.huella_de_chipset(chipset.filename)
        if imagen is None:
            return None
        return [b"mapa %dx%d" % (game_map.width, game_map.height),
                _capa(game_map.lower_layer), _capa(game_map.upper_layer),
                bytes(chipset.passable_lower), bytes(chipset.passable_upper),
                imagen]

    def huella_de_chipset(self, filename):
        """El sha256 del archivo de ChipSet que gana la búsqueda, o `None`.

        Los bytes y no la ruta: que el archivo salga del juego o del RTP no
        cambia un pixel si es el mismo archivo, y que salga del mismo lado no
        garantiza que no lo hayan tocado.

        Se recuerda por nombre porque los mapas comparten ChipSet: un cartucho
        tiene bastantes menos ChipSets que mapas, y leer el archivo una vez por
        mapa no aportaría nada.
        """
        if filename not in self.huellas:
            path = find_resource(self.search_dirs, "ChipSet", filename)
            if path is None:
                self.huellas[filename] = None
            else:
                with open(path, "rb") as f:
                    self.huellas[filename] = hashlib.sha256(f.read()).digest()
        return self.huellas[filename]

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
        demás.
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
        pide `snes_convert._convert_layers`: por familia, los dibujos que **no**
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

"""The layers of an A Blurred Line (RPG Maker 2000) map as images.

The two tile layers resolved against their ChipSet, with the drawings of the
water animation and of the animated tiles, and the CharSets placed on top of
them. It is what the converter cuts into tiles: see
`Renderer.animated_layers`. No panorama and no events: the converter takes
care of the events.
"""

import array
import hashlib
import os

from PIL import Image

from common import project
from rpgmaker import lcf
from rpgmaker import rm2k
from rpgmaker import resources
from rpgmaker.resources import find_resource
from rpgmaker.rm2k import TILE
from render import chipset_recipe
from render.chipset import ANIMATED, ChipsetAtlas, TERRAIN, UPPER


def load_image(path):
    image = Image.open(path)
    if image.mode == "P":
        # In RM2k palette color 0 is the color key.
        image.info["transparency"] = 0
    return image.convert("RGBA")


def _layer_bytes(tiles):
    """A tile layer as bytes, to put it in a cache key.

    Four bytes per tile and not one: a tile ID goes up to 10143, so `bytes()`
    does not work.
    """
    return array.array("i", tiles).tobytes()


def build_passability(chipset):
    """Table of flags per tile ID, as lmu2png builds it (main.cpp).

    We only use it to decide whether a tile goes before or after the player;
    there is no player here, but it defines the drawing order between the two
    layers.
    """
    flags = bytearray(65536)
    lower, upper = chipset.passable_lower, chipset.passable_upper

    for i in range(3):          # water A/B/C
        flags[1000 * i:1000 * i + 1000] = bytes([lower[i]]) * 1000
    for i in range(3):          # animated tiles
        flags[3000 + i * 50:3050 + i * 50] = bytes([lower[3 + i]]) * 50
    for i in range(12):         # terrain autotiles
        flags[4000 + i * 50:4050 + i * 50] = bytes([lower[6 + i]]) * 50
    for i in range(144):        # common tile pages
        flags[5000 + i] = lower[18 + i]
        flags[10000 + i] = upper[i]
    return flags


def draw_tiles(image, atlas, game_map, flags, pass_upper, steps=(0, 0)):
    """Draws the tiles of both layers that fall in the requested pass.

    A lower-layer tile with flags 0x30 and an upper-layer one with 0x10 are
    drawn above the player; the rest, below. It is what decides whether an
    event is covered by the roof or stands on top of it.

    `steps` are the two of the ChipSet's animation —water and animated
    tiles—, which pick which drawing of each family is painted. See
    `render_tile`.
    """
    for y in range(game_map.height):
        row = y * game_map.width
        for x in range(game_map.width):
            lower_tile = game_map.lower_layer[row + x]
            if bool(flags[lower_tile] & 0x30) == pass_upper:
                atlas.render_tile(image, x, y, lower_tile, *steps)

            upper_tile = game_map.upper_layer[row + x]
            if bool(flags[upper_tile] & 0x10) == pass_upper:
                atlas.render_tile(image, x, y, upper_tile, *steps)


# The dithers a translucent event is drawn with, and which pixel drops out.
# RM2k draws at 160 out of 255, that is, at 63%: `cinco_de_ocho` is the one
# that comes closest. The rest are here to be able to compare on a real TV,
# which is where this is decided: a CRT's scan blurs **along the line**, so
# alternating columns blend and the checkerboard does not.
DITHERS = {
    "damero":        lambda x, y: (x + y) % 2 == 1,
    "columnas":      lambda x, y: x % 2 == 1,
    "filas":         lambda x, y: y % 2 == 1,
    "cinco_de_ocho": lambda x, y: ((y % 2) * 4 + (x % 4)) in (1, 4, 7),
    "tres_de_cuatro": lambda x, y: x % 2 == 1 and y % 2 == 1,
}


class Charsets:
    """Cache of CharSets, which repeat a lot among a map's events."""

    def __init__(self, search_dirs, atlas_by_name=None,
                 lower_layer_image=None):
        self.search_dirs = search_dirs
        self.images = {}
        self.atlas_by_name = atlas_by_name
        self.lower_layer_image = lower_layer_image

    def get(self, name):
        if name not in self.images:
            base, where = rm2k.baked_parts(name)
            if name.endswith(rm2k.COPY_SUFFIX):
                self.images[name] = self.get(name[:-len(rm2k.COPY_SUFFIX)])
            elif where is not None:
                self.images[name] = self._baked(base, *where)
            elif name.endswith(rm2k.DITHER_SUFFIX):
                self.images[name] = self._dithered(
                    name[:-len(rm2k.DITHER_SUFFIX)])
            elif name.startswith(rm2k.TILE_PREFIX):
                self.images[name] = self._from_tile(name)
            else:
                path = find_resource(self.search_dirs, "CharSet", name)
                self.images[name] = load_image(path) if path else None
        return self.images[name]

    def _dithered(self, name):
        """The CharSet of a translucent event: the same one, with part of its
        pixels transparent. See `rm2k.DITHER_SUFFIX` and `DITHERS`."""
        base = self.get(name)
        if base is None:
            return None
        image = base.convert("RGBA")
        pix = image.load()
        drops = DITHERS[rm2k.DITHER_PATTERN]
        for y in range(image.height):
            for x in range(image.width):
                if drops(x, y):
                    pix[x, y] = (0, 0, 0, 0)
        return image

    def _baked(self, base, map_id, tile_x, tile_y):
        """The CharSet of a translucent event, with the blend already computed.

        RM2k draws it at 160 out of 255 over whatever is behind. Since the
        event is static —all 70 in the game are— and so is the background,
        the blend is computed once here, against the real background of the
        cell where it stands, and stays baked into the graphic: the sprite
        comes out opaque and with the exact colors, no dither.

        The background is the map's **lower layer**, which is the only thing
        left behind the sprite: the upper one is drawn afterwards and covers
        it, so on the pixels where the sprite shows the background is this
        one. And it is taken at `(x*16 - 4, y*16 - 16)`, which is where
        `charset.draw` rests the 24x32 frame on the cell; since all the
        CharSet's poses land on the same place on the screen, each one is
        blended against the same piece and it is enough to look at the
        pixel's position inside its frame.
        """
        sheet = self.get(base)
        background = (self.lower_layer_image(map_id)
                      if self.lower_layer_image else None)
        if sheet is None or background is None:
            return sheet
        image = sheet.convert("RGBA")
        pix = image.load()
        behind = background.load()
        ox = tile_x * TILE + rm2k.OFFSET_X
        oy = tile_y * TILE + rm2k.OFFSET_Y
        alpha = rm2k.TRANSLUCENT_OPACITY
        for y in range(image.height):
            fy = oy + y % rm2k.SPRITE_HEIGHT
            for x in range(image.width):
                r, g, b, a = pix[x, y]
                if not a:
                    continue
                fx = ox + x % rm2k.SPRITE_WIDTH
                if 0 <= fx < background.width and 0 <= fy < background.height:
                    br, bg, bb = behind[fx, fy][:3]
                else:
                    br = bg = bb = 0        # outside the map the console sees black
                pix[x, y] = ((r * alpha + br * (255 - alpha)) // 255,
                             (g * alpha + bg * (255 - alpha)) // 255,
                             (b * alpha + bb * (255 - alpha)) // 255, 255)
        return image

    def _from_tile(self, name):
        """A made-up CharSet with a tile from the chipset's upper page in the
        twelve poses of character 0, resting on the cell: a character's frame
        is 24x32 and is drawn at (x - 4, y - 16), so the 16x16 tile goes at
        (4, 16) of each frame. It is how RM2k draws an event without a
        CharSet, only as a sprite, so that it moves and
        changes place like any other."""
        _, chipset, index = name.split(":", 2)
        atlas = self.atlas_by_name(chipset) if self.atlas_by_name else None
        if atlas is None:
            return None
        tile = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        atlas.render_tile(tile, 0, 0, UPPER + int(index))
        image = Image.new("RGBA", (288, 256), (0, 0, 0, 0))
        for pose in range(12):
            image.paste(tile, ((pose % 3) * 24 + 4, (pose // 3) * 32 + 16))
        return image


class Renderer:
    """Everything shared between maps: the game, the RTP and the caches."""

    def __init__(self, game_dir=None, rtp_dir=None):
        game_dir = game_dir or resources.GAME_DIR
        rtp_dir = rtp_dir or resources.RTP_DIR
        self.database = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
        self.tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
        self.game_dir = game_dir
        self.search_dirs = [project.root(), game_dir, rtp_dir]
        # The images of the ChipSets `rom/parches/manual/` adds are **built**
        # —the game's art is not ours to version, see `chipset_recipe.py`—
        # and go first in the search: they are the ones that win when they
        # exist.
        self.search_dirs.insert(0, chipset_recipe.build_images(
            lambda folder, name: find_resource(self.search_dirs, folder,
                                               name)))
        self.charsets = Charsets(self.search_dirs, self.atlas_by_name,
                                 self.lower_layer_image)
        self.atlases = {}
        self.lower_layers = {}
        self.fingerprints = {}
        self.missing_chipsets = set()

    def lower_layer_image(self, map_id):
        """A map's lower layer, to bake the translucent ones.

        It is cached because a map with several translucent events would ask
        for it once per event, and rendering the layers of a big map is not
        free.
        """
        if map_id not in self.lower_layers:
            game_map = self.load_map(
                os.path.join(self.game_dir, "Map%04d.lmu" % map_id))
            self.lower_layers[map_id] = self.render_layers(game_map)[0]
        return self.lower_layers[map_id]

    def atlas(self, chipset):
        """ChipSets repeat between maps and expanding them is not free."""
        return self.atlas_by_name(chipset.filename)

    def atlas_by_name(self, filename):
        if filename not in self.atlases:
            path = find_resource(self.search_dirs, "ChipSet", filename)
            if not path:
                self.missing_chipsets.add(filename)
            self.atlases[filename] = ChipsetAtlas(load_image(path)) if path else None
        return self.atlases[filename]

    def layer_inputs(self, game_map):
        """Everything that goes into a map's drawn layers, without drawing them.

        It is a list of parts for a cache key, and it exists so that whoever
        caches what comes out of `animated_layers` can ask **before** paying
        for the drawing. It returns `None` when the ChipSet is missing: then
        there is no input that counts and the caller has to take the usual
        path, which is the one that knows how to fail.

        It lives here and not in the converter because this file is the one
        that knows what `render_layers` reads: the map's two layers, its
        size, and from the ChipSet the passability —which decides which tile
        goes on which layer— and the image. Nothing else from the `.lmu`
        reaches the drawing. If some day `render_layers` looks at something
        not on this list, the cache goes stale without warning, and the only
        place where that can be seen is right next to it here.

        What is **not** here, on purpose: the drawing code and the Pillow
        version. They do not belong to the map but to the run, and whoever
        builds the key adds them.
        """
        chipset = self.database.chipsets[game_map.chipset_id]
        image = self.chipset_fingerprint(chipset.filename)
        if image is None:
            return None
        return [b"mapa %dx%d" % (game_map.width, game_map.height),
                _layer_bytes(game_map.lower_layer),
                _layer_bytes(game_map.upper_layer),
                bytes(chipset.passable_lower), bytes(chipset.passable_upper),
                image]

    def chipset_fingerprint(self, filename):
        """The sha256 of the ChipSet file that wins the search, or `None`.

        The bytes and not the path: whether the file comes from the game or
        from the RTP does not change a pixel if it is the same file, and
        coming from the same side does not guarantee nobody touched it.

        It is remembered by name because maps share ChipSets: a cartridge has
        quite a few fewer ChipSets than maps, and reading the file once per
        map would add nothing.
        """
        if filename not in self.fingerprints:
            path = find_resource(self.search_dirs, "ChipSet", filename)
            if path is None:
                self.fingerprints[filename] = None
            else:
                with open(path, "rb") as f:
                    self.fingerprints[filename] = hashlib.sha256(
                        f.read()).digest()
        return self.fingerprints[filename]

    def load_map(self, path):
        """The map, with its chipset's name set: `collect_npcs` needs it for
        the events that are drawn with a tile."""
        game_map = lcf.Map(path)
        chipset = self.database.chipsets[game_map.chipset_id]
        game_map.chipset_filename = chipset.filename
        # And the passability of its tiles, for the events drawn with one on
        # the lower layer: see `rm2k.event_tile_passability`.
        game_map.passability_table = build_passability(chipset)
        return game_map

    def render_layers(self, game_map, steps=(0, 0)):
        """The map in two separate layers, as RM2k orders them.

        The lower one is opaque and goes behind the hero; the upper one
        carries only the tiles marked "above the hero" and is transparent
        everywhere else.
        """
        chipset = self.database.chipsets[game_map.chipset_id]
        atlas = self.atlas(chipset)
        if atlas is None:
            return None, None

        flags = build_passability(chipset)
        size = (game_map.width * TILE, game_map.height * TILE)

        base = Image.new("RGBA", size, (0, 0, 0, 255))
        draw_tiles(base, atlas, game_map, flags, pass_upper=False, steps=steps)
        above = Image.new("RGBA", size, (0, 0, 0, 0))
        draw_tiles(above, atlas, game_map, flags, pass_upper=True, steps=steps)
        return base, above

    def animated_layers(self, game_map):
        """The map's layers and the other drawings of the ChipSet's animation.

        Returns `(base, above, variants)`, with `variants` in the shape
        `snes_convert._convert_layers` asks for: per family, the drawings
        that are **not** 0, which is `base`.

        It is the only place where it is decided which drawings there are,
        and both ends use it —the converter and the reference—: if each built
        them on its own, the ROM and the reference could be animating
        different things.

        Only what the map can end up moving is rendered: a map without water
        or animated tiles pays nothing. That all the drawings of a family
        come out the same —map 3's water does, because the ChipSet has it
        drawn three times the same— does not need detecting here: `convert`
        will not find any cell that changes and the run comes out empty.
        """
        base, above = self.render_layers(game_map)
        if base is None:
            return None, None, {}
        has = {"agua": False, "animado": False}
        for tile in list(game_map.lower_layer) + list(game_map.upper_layer):
            if tile < ANIMATED:
                has["agua"] = True
            elif tile < TERRAIN:
                has["animado"] = True
        variants = {}
        for family, drawings in rm2k.ANIMATED_FAMILIES:
            if not has[family]:
                continue
            variants[family] = [
                self.render_layers(
                    game_map,
                    (d, 0) if family == "agua" else (0, d))[0]
                for d in range(1, drawings)]
        return base, above, variants

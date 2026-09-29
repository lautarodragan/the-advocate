"""The image of a ChipSet from `rom/parches/manual/`: the recipe applied to the PNG.

**The ChipSet's image is not versioned: it is built.** The game's art is not
ours to redistribute —it lives in `/extras`, see `docs/rpgmaker/rtp.md`—, so
the fork keeps the *recipe* —which block is copied where— and
`build_chipset_image`
applies it on the original PNG, leaving the result in
`rom/build/parches-manual/`.

The recipe has five operations. Two copy from inside the ChipSet itself
—`bloques_bajos` and `tiles_altos`— and two **bring pixels from outside**:
`desde_charset` puts a CharSet pose into two upper tiles, which is how an NPC
that does nothing but stand there stops being a sprite and becomes map —the
Auditorium audience, map 18—, and `desde_imagen` puts in a PNG that is
neither a ChipSet nor a CharSet, scaled and cut into 16x16 cells.

The fifth, `podar`, does not draw: **it erases what the map does not use**.
A fork's ChipSet is private to its map, and what is gained is not pixels but
**palette indices**: the PNG is indexed and has 256, which is the ceiling
`desde_imagen` runs into.
"""

import os

from PIL import Image

from common import project
from rpgmaker import lcf
from rpgmaker.fork import BrokenFork, chipsets
from rpgmaker.rm2k import (OFFSET_X, SPRITE_HEIGHT, SPRITE_WIDTH, TILE,
                           common_box, terrain_box)

def output_dir():
    """Where the built images land. It is a build directory like any other:
    it can be deleted, and it rebuilds itself."""
    return os.path.join(project.build(), "parches-manual")


def _palette(image):
    """The colors of an indexed PNG, as RGB tuples and by index."""
    raw = image.getpalette() or []
    return [tuple(raw[i * 3:i * 3 + 3]) for i in range(len(raw) // 3)]


# The water and the animated tiles share this rectangle of the ChipSet; the
# rest of the left half is the twelve terrain autotiles, and the right half,
# the common tiles. See `rm2k-render`'s `src/chipset.rs`, which is where the
# offsets come from.
WATER_BOX = (0, 0, 96, 128)


# The commands that pick a tile **at run time**: with one of these inside,
# the map's layers no longer say what is drawn and the pruning cannot know
# what to keep. Neither of today's two forked maps uses them, so `prune`
# stops instead of guessing: silently losing art is exactly what this file
# exists to avoid.
TILE_PICKING_COMMANDS = {
    11710: "ChangeMapTileset",
    11750: "TileSubstitution",
}


def _what_it_draws(map_id):
    """Which parts of the ChipSet that map uses: water, autotiles and common
    slots.

    It comes from the **already forked** map, which is what makes it
    self-checking: if the fork starts drawing a new slot, this count sees it
    by itself and the pruning respects it without anyone having to remember
    to note it down anywhere.

    And the two layers are not enough. **An event without a CharSet is drawn
    with a tile from the upper page** —see `rm2k.tile_name`: that is how
    doors and a good part of the decoration are made— and that tile does not
    appear on any layer. Pruning without counting them, map 32 lost slot 13
    and the ROM came out with 78 different bytes: the byte-for-byte
    comparison caught it, not a test.
    """
    game_map = lcf.Map(os.path.join(project.data(), "maps",
                                    "Map%04d.json" % map_id))
    water = False
    terrains, commons = set(), set()
    for layer in (game_map.lower_layer, game_map.upper_layer):
        for tile in layer:
            if tile < 4000:
                water = True            # water (0..2999) and animated (3000..)
            elif tile < 5000:
                terrains.add((tile - 4000) // 50)
            elif tile < 10000:
                commons.add(tile - 5000)
            else:
                commons.add(144 + tile - 10000)
    for event in game_map.events:
        for page in event.pages:
            if not page.character_name:
                commons.add(144 + page.character_index)
            for command in page.commands:
                name = TILE_PICKING_COMMANDS.get(command.code)
                if name:
                    raise BrokenFork(
                        "map %d uses %s, which picks a tile at run time: "
                        "with that the layers do not say what is drawn and "
                        "pruning the ChipSet would erase art the map does use"
                        % (map_id, name))
    return water, terrains, commons


def prune(image, map_id):
    """Erases from the ChipSet everything that map does not draw.

    A fork's ChipSet is **private to its map** —see
    `rom/parches/manual/README.md`—, so no other map can ask it for a tile this
    one does not use: what is not drawn is dead weight. And the weight that
    matters is not the pixels but the **palette indices**: the PNG is indexed
    and has 256, which is the ceiling `desde_imagen` runs into when bringing
    a drawing from outside. Pruning ChipSet 1 goes from 122 free indices to
    174, and that is the difference between the Hover Tram fitting and not
    fitting.

    It cannot change what is seen —it erases tiles the map does not name— and
    here that is proven, not assumed: the ROM comes out byte for byte the
    same with the pruned ChipSet as long as the map keeps drawing the same.
    """
    water, terrains, commons = _what_it_draws(map_id)
    if not water:
        image.paste(Image.new("P", (WATER_BOX[2], WATER_BOX[3])),
                    WATER_BOX[:2])
    for n in range(12):
        if n not in terrains:
            image.paste(Image.new("P", (48, 64)), terrain_box(n)[:2])
    for i in range(288):
        if i not in commons:
            image.paste(Image.new("P", (16, 16)), common_box(i)[:2])


class _Palette:
    """The ChipSet's palette while colors from a CharSet are added to it.

    Both PNGs are indexed and **their indices do not mean the same thing**:
    copying the bytes of one into the other gives a sprite with the ChipSet's
    colors, which is visible garbage. So it is copied by color, and a color
    that is not there is added at an index the ChipSet does not use.

    Index 0 is left out of the search **at both ends**: it is the color key,
    and a sprite color that happens to equal the ChipSet's index 0 has to
    take an index of its own or the sprite would come out with a hole.
    """

    def __init__(self, image):
        self.colors = _palette(image)
        while len(self.colors) < 256:
            self.colors.append((0, 0, 0))
        used = set(image.tobytes())
        self.where = {}
        for index in sorted(used):
            if index:
                self.where.setdefault(self.colors[index], index)
        self.free = [i for i in range(1, 256) if i not in used]

    def index(self, color):
        if color not in self.where:
            if not self.free:
                raise BrokenFork(
                    "the ChipSet ran out of palette indices: all 256 are "
                    "already used and the incoming drawing brings colors it "
                    "does not have. If the ChipSet is not being pruned, "
                    "`podar` is what frees the indices the map does not use")
            self.where[color] = self.free.pop(0)
            self.colors[self.where[color]] = color
        return self.where[color]

    def apply(self, image):
        image.putpalette([channel for color in self.colors
                          for channel in color])


def _to_15_bits(color):
    """The color rounded to the 15 bits the console really shows.

    It loses nothing the cartridge could draw —the allocator quantizes with
    `>>3` anyway— and **it is what makes the drawing fit**: the Hover Tram's
    206 colors are 148 at 15 bits, against the 174 indices the pruned ChipSet
    leaves free. Without this it does not fit.

    That the ChipSet's PNG ends up with colors the original art does not have
    is not a problem: that image **is not versioned, it is built** —see
    `rom/parches/manual/README.md`—, so it is a build intermediate and not the
    game's art, which remains intact in its `Picture/`.
    """
    return tuple((channel >> 3) << 3 for channel in color)


def _pose(image, recipe):
    """A pose's 24x32 frame, cropped from the CharSet.

    A CharSet is 8 characters in 4x2, each with its 12 poses: 3 walking
    patterns by 4 directions. See `rm2k.SPRITE_WIDTH`.
    """
    x = (recipe["personaje"] % 4) * 72 + recipe["patron"] * SPRITE_WIDTH
    y = (recipe["personaje"] // 4) * 128 + recipe["direccion"] * SPRITE_HEIGHT
    return image.crop((x, y, x + SPRITE_WIDTH, y + SPRITE_HEIGHT))


def build_chipset_image(data, find):
    """Builds the PNG of a forked ChipSet and returns its path.

    `find(folder, name)` is what finds the originals —the ChipSet it
    comes from, and the CharSets that are baked—; the result lands in
    `rom/build/parches-manual/ChipSet/` with the name the database entry asks
    for.
    It is always rewritten —building it is copying rectangles— and moved into
    place in one go, so two builds at once do not leave each other a
    half-written PNG.
    """
    recipe = data["imagen"]
    source_path = find("ChipSet", recipe["base"])
    if source_path is None:
        raise BrokenFork("ChipSet %r, which %d comes from, is missing"
                         % (recipe["base"], data["chipset"]["id"]))
    # Without converting to RGBA: the ChipSets are indexed PNGs and color 0
    # is the color key. Converting them here threw away the palette, and the
    # resulting PNG had the empty tiles **opaque**: it shows, and it looks
    # bad.
    image = Image.open(source_path)
    image.load()
    # The pruning first, because it frees palette indices the operations
    # below will need, and because it reads the **forked** map: the slots the
    # fork introduces are already in its layers, so it respects them.
    if "podar" in recipe:
        prune(image, recipe["podar"])
    for src, dst in recipe.get("bloques_bajos", []):
        image.paste(image.crop(terrain_box(src)),
                    terrain_box(dst)[:2])
    for src, dst in recipe.get("tiles_altos", []):
        # Upper tile `u` is common tile 144 + u: the first 144 are the lower
        # layer. See `common_box`.
        image.paste(image.crop(common_box(144 + src)),
                    common_box(144 + dst)[:2])

    # The slots `desde_imagen` is going to overwrite are emptied **before**
    # looking at the palette. Otherwise their current colors still count as
    # used and keep the indices the new drawing needs: the pruning keeps
    # them because the forked map names them, but what the map draws there
    # is the drawing about to come in, not the one that was there. Without
    # this the Hover Tram runs out of indices and the build stops.
    for entry in (recipe.get("desde_imagen") or {}).get("celdas", []):
        if len(entry) <= 3:      # not the ones that compose over another slot
            image.paste(Image.new("P", (TILE, TILE)),
                        common_box(144 + entry[2])[:2])

    # The two operations that bring pixels from outside share **a single**
    # palette: each `_Palette` hands out the free indices from scratch, so two
    # would overwrite each other's indices and the second `apply` would
    # erase the first one's colors.
    palette = (_Palette(image)
               if recipe.get("desde_charset") or recipe.get("desde_imagen")
               else None)

    if recipe.get("desde_charset"):
        for item in recipe["desde_charset"]:
            sheet = find("CharSet", item["charset"])
            if sheet is None:
                raise BrokenFork("CharSet %r, which ChipSet %d bakes, "
                                 "is missing" % (item["charset"],
                                                 data["chipset"]["id"]))
            source = Image.open(sheet)
            source.load()
            source_colors = _palette(source)
            pose = list(_pose(source, item).tobytes())
            # The sprite is drawn at `(x*16 - 4, y*16 - 16)`, so its columns
            # 4 to 19 land exactly on the cell and its upper half lands on the
            # cell above: that is where the two tiles come from.
            column = -OFFSET_X
            for half, slot in (("cabeza", item["cabeza"]),
                               ("cuerpo", item["cuerpo"])):
                top = 0 if half == "cabeza" else TILE
                pixels = []
                for row in range(top, top + TILE):
                    for x in range(column, column + TILE):
                        index = pose[row * SPRITE_WIDTH + x]
                        pixels.append(0 if not index
                                      else palette.index(source_colors[index]))
                tile = Image.new("P", (TILE, TILE))
                tile.putdata(pixels)
                image.paste(tile, common_box(144 + slot)[:2])

    if recipe.get("desde_imagen"):
        item = recipe["desde_imagen"]
        path = find(item["carpeta"], item["imagen"])
        if path is None:
            raise BrokenFork("%s/%s, which ChipSet %d bakes, is missing"
                             % (item["carpeta"], item["imagen"],
                                data["chipset"]["id"]))
        source = Image.open(path)
        source.load()
        source_colors = _palette(source)
        # RM2k scales images with **nearest neighbor**, and the Hover Tram's
        # 65% matches that way at 97.3% against the original game's capture:
        # that checked the scaling, the anchoring and the position in one go.
        scale = item.get("escala", 100)
        width = source.width * scale // 100
        height = source.height * scale // 100
        small = source.resize((width, height), Image.NEAREST).load()
        # Where the drawing's pixel (0,0) lands inside its first cell: the
        # image has no reason to be aligned to the 16 grid, and the tram's is
        # not.
        dx, dy = item.get("desfase", (0, 0))
        # Colors of the drawing treated as transparent besides index 0. It
        # exists for defects in the original art: a pixel painted **almost**
        # the key color but not quite, which RM2k draws and shows as a stray
        # dot. It is a declared divergence, so it is written in the recipe
        # and not hidden here.
        transparent = {tuple(c) for c in item.get("transparentes", [])}
        for entry in item["celdas"]:
            column, row, slot = entry[:3]
            # The fourth element, if present, is the slot the background
            # comes from: the drawing is composed **on top** of it instead of
            # overwriting it. The terrace wall of map 32 asks for it, where
            # nine pixels of the tip of the tram land on a cell that already
            # draws something.
            tile = (image.crop(common_box(144 + entry[3]))
                    if len(entry) > 3 else Image.new("P", (TILE, TILE)))
            pixels = tile.load()
            for y in range(TILE):
                for x in range(TILE):
                    px, py = column * TILE + x - dx, row * TILE + y - dy
                    if not (0 <= px < width and 0 <= py < height):
                        continue
                    index = small[px, py]
                    if index and source_colors[index] not in transparent:
                        pixels[x, y] = palette.index(
                            _to_15_bits(source_colors[index]))
            image.paste(tile, common_box(144 + slot)[:2])

    if palette is not None:
        palette.apply(image)

    target = os.path.join(output_dir(), "ChipSet",
                          data["chipset"]["chipset_name"] + ".png")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    temp = "%s.%d.png" % (target, os.getpid())
    image.save(temp)
    os.replace(temp, target)
    return target


def build_images(find):
    """Builds the images of all the fork's ChipSets. Returns the directory
    where they ended up, to put it in the resource search."""
    for data in chipsets().values():
        build_chipset_image(data, find)
    return output_dir()

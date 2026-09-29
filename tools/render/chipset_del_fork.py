"""The image of a ChipSet from `rom/parches/manual/`: the recipe applied to the PNG.

**The ChipSet's image is not versioned: it is built.** The game's art is not
ours to redistribute —it lives in `/extras`, see `docs/rpgmaker/rtp.md`—, so
the fork keeps the *recipe* —which block is copied where— and
`imagen_del_chipset`
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

from common import proyecto
from rpgmaker import lcf
from rpgmaker.fork import ForkRoto, chipsets
from rpgmaker.rm2k import (OFFSET_X, SPRITE_HEIGHT, SPRITE_WIDTH, TILE,
                           caja_de_comun, caja_de_terreno)

def generado():
    """Where the built images land. It is a build directory like any other:
    it can be deleted, and it rebuilds itself."""
    return os.path.join(proyecto.build(), "parches-manual")


def _paleta(imagen):
    """The colors of an indexed PNG, as RGB tuples and by index."""
    crudo = imagen.getpalette() or []
    return [tuple(crudo[i * 3:i * 3 + 3]) for i in range(len(crudo) // 3)]


# The water and the animated tiles share this rectangle of the ChipSet; the
# rest of the left half is the twelve terrain autotiles, and the right half,
# the common tiles. See `render/chipset.py`, which is where the offsets come
# from.
CAJA_AGUA = (0, 0, 96, 128)


# The commands that pick a tile **at run time**: with one of these inside,
# the map's layers no longer say what is drawn and the pruning cannot know
# what to keep. Neither of today's two forked maps uses them, so `podar`
# stops instead of guessing: silently losing art is exactly what this file
# exists to avoid.
COMANDOS_QUE_ELIGEN_TILES = {
    11710: "ChangeMapTileset",
    11750: "TileSubstitution",
}


def _lo_que_dibuja(map_id):
    """Which parts of the ChipSet that map uses: water, autotiles and common
    slots.

    It comes from the **already forked** map, which is what makes it
    self-checking: if the fork starts drawing a new slot, this count sees it
    by itself and the pruning respects it without anyone having to remember
    to note it down anywhere.

    And the two layers are not enough. **An event without a CharSet is drawn
    with a tile from the upper page** —see `rm2k.nombre_de_tile`: that is how
    doors and a good part of the decoration are made— and that tile does not
    appear on any layer. Pruning without counting them, map 32 lost slot 13
    and the ROM came out with 78 different bytes: the byte-for-byte
    comparison caught it, not a test.
    """
    mapa = lcf.Map(os.path.join(proyecto.data(), "maps", "Map%04d.json" % map_id))
    agua = False
    terrenos, comunes = set(), set()
    for capa in (mapa.lower_layer, mapa.upper_layer):
        for tile in capa:
            if tile < 4000:
                agua = True              # water (0..2999) and animated (3000..)
            elif tile < 5000:
                terrenos.add((tile - 4000) // 50)
            elif tile < 10000:
                comunes.add(tile - 5000)
            else:
                comunes.add(144 + tile - 10000)
    for evento in mapa.events:
        for pagina in evento.pages:
            if not pagina.character_name:
                comunes.add(144 + pagina.character_index)
            for comando in pagina.commands:
                nombre = COMANDOS_QUE_ELIGEN_TILES.get(comando.code)
                if nombre:
                    raise ForkRoto(
                        "map %d uses %s, which picks a tile at run time: "
                        "with that the layers do not say what is drawn and "
                        "pruning the ChipSet would erase art the map does use"
                        % (map_id, nombre))
    return agua, terrenos, comunes


def podar(imagen, map_id):
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
    agua, terrenos, comunes = _lo_que_dibuja(map_id)
    if not agua:
        imagen.paste(Image.new("P", (CAJA_AGUA[2], CAJA_AGUA[3])),
                     CAJA_AGUA[:2])
    for n in range(12):
        if n not in terrenos:
            imagen.paste(Image.new("P", (48, 64)), caja_de_terreno(n)[:2])
    for i in range(288):
        if i not in comunes:
            imagen.paste(Image.new("P", (16, 16)), caja_de_comun(i)[:2])


class _Paleta:
    """The ChipSet's palette while colors from a CharSet are added to it.

    Both PNGs are indexed and **their indices do not mean the same thing**:
    copying the bytes of one into the other gives a sprite with the ChipSet's
    colors, which is visible garbage. So it is copied by color, and a color
    that is not there is added at an index the ChipSet does not use.

    Index 0 is left out of the search **at both ends**: it is the color key,
    and a sprite color that happens to equal the ChipSet's index 0 has to
    take an index of its own or the sprite would come out with a hole.
    """

    def __init__(self, imagen):
        self.colores = _paleta(imagen)
        while len(self.colores) < 256:
            self.colores.append((0, 0, 0))
        usados = set(imagen.tobytes())
        self.donde = {}
        for indice in sorted(usados):
            if indice:
                self.donde.setdefault(self.colores[indice], indice)
        self.libres = [i for i in range(1, 256) if i not in usados]

    def indice(self, color):
        if color not in self.donde:
            if not self.libres:
                raise ForkRoto(
                    "the ChipSet ran out of palette indices: all 256 are "
                    "already used and the incoming drawing brings colors it "
                    "does not have. If the ChipSet is not being pruned, "
                    "`podar` is what frees the indices the map does not use")
            self.donde[color] = self.libres.pop(0)
            self.colores[self.donde[color]] = color
        return self.donde[color]

    def aplicar(self, imagen):
        imagen.putpalette([canal for color in self.colores for canal in color])


def _a_quince(color):
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
    return tuple((canal >> 3) << 3 for canal in color)


def _pose(imagen, receta):
    """A pose's 24x32 frame, cropped from the CharSet.

    A CharSet is 8 characters in 4x2, each with its 12 poses: 3 walking
    patterns by 4 directions. See `rm2k.SPRITE_WIDTH`.
    """
    x = (receta["personaje"] % 4) * 72 + receta["patron"] * SPRITE_WIDTH
    y = (receta["personaje"] // 4) * 128 + receta["direccion"] * SPRITE_HEIGHT
    return imagen.crop((x, y, x + SPRITE_WIDTH, y + SPRITE_HEIGHT))


def imagen_del_chipset(datos, buscar):
    """Builds the PNG of a forked ChipSet and returns its path.

    `buscar(carpeta, nombre)` is what finds the originals —the ChipSet it
    comes from, and the CharSets that are baked—; the result lands in
    `rom/build/parches-manual/ChipSet/` with the name the database entry asks
    for.
    It is always rewritten —building it is copying rectangles— and moved into
    place in one go, so two builds at once do not leave each other a
    half-written PNG.
    """
    receta = datos["imagen"]
    origen = buscar("ChipSet", receta["base"])
    if origen is None:
        raise ForkRoto("ChipSet %r, which %d comes from, is missing"
                       % (receta["base"], datos["chipset"]["id"]))
    # Without converting to RGBA: the ChipSets are indexed PNGs and color 0
    # is the color key. Converting them here threw away the palette, and the
    # resulting PNG had the empty tiles **opaque**: it shows, and it looks
    # bad.
    imagen = Image.open(origen)
    imagen.load()
    # The pruning first, because it frees palette indices the operations
    # below will need, and because it reads the **forked** map: the slots the
    # fork introduces are already in its layers, so it respects them.
    if "podar" in receta:
        podar(imagen, receta["podar"])
    for desde, hasta in receta.get("bloques_bajos", []):
        imagen.paste(imagen.crop(caja_de_terreno(desde)),
                     caja_de_terreno(hasta)[:2])
    for desde, hasta in receta.get("tiles_altos", []):
        # Upper tile `u` is common tile 144 + u: the first 144 are the lower
        # layer. See `caja_de_comun`.
        imagen.paste(imagen.crop(caja_de_comun(144 + desde)),
                     caja_de_comun(144 + hasta)[:2])

    # The slots `desde_imagen` is going to overwrite are emptied **before**
    # looking at the palette. Otherwise their current colors still count as
    # used and keep the indices the new drawing needs: the pruning keeps
    # them because the forked map names them, but what the map draws there
    # is the drawing about to come in, not the one that was there. Without
    # this the Hover Tram runs out of indices and the build stops.
    for entrada in (receta.get("desde_imagen") or {}).get("celdas", []):
        if len(entrada) <= 3:      # not the ones that compose over another slot
            imagen.paste(Image.new("P", (TILE, TILE)),
                         caja_de_comun(144 + entrada[2])[:2])

    # The two operations that bring pixels from outside share **a single**
    # palette: each `_Paleta` hands out the free indices from scratch, so two
    # would overwrite each other's indices and the second `aplicar` would
    # erase the first one's colors.
    paleta = (_Paleta(imagen)
              if receta.get("desde_charset") or receta.get("desde_imagen")
              else None)

    if receta.get("desde_charset"):
        for una in receta["desde_charset"]:
            hoja = buscar("CharSet", una["charset"])
            if hoja is None:
                raise ForkRoto("CharSet %r, which ChipSet %d bakes, "
                               "is missing" % (una["charset"],
                                               datos["chipset"]["id"]))
            fuente = Image.open(hoja)
            fuente.load()
            desde = _paleta(fuente)
            pose = list(_pose(fuente, una).tobytes())
            # The sprite is drawn at `(x*16 - 4, y*16 - 16)`, so its columns
            # 4 to 19 land exactly on the cell and its upper half lands on the
            # cell above: that is where the two tiles come from.
            columna = -OFFSET_X
            for mitad, ranura in (("cabeza", una["cabeza"]),
                                  ("cuerpo", una["cuerpo"])):
                alto = 0 if mitad == "cabeza" else TILE
                pixeles = []
                for fila in range(alto, alto + TILE):
                    for x in range(columna, columna + TILE):
                        indice = pose[fila * SPRITE_WIDTH + x]
                        pixeles.append(0 if not indice
                                       else paleta.indice(desde[indice]))
                tile = Image.new("P", (TILE, TILE))
                tile.putdata(pixeles)
                imagen.paste(tile, caja_de_comun(144 + ranura)[:2])

    if receta.get("desde_imagen"):
        una = receta["desde_imagen"]
        ruta = buscar(una["carpeta"], una["imagen"])
        if ruta is None:
            raise ForkRoto("%s/%s, which ChipSet %d bakes, is missing"
                           % (una["carpeta"], una["imagen"],
                              datos["chipset"]["id"]))
        fuente = Image.open(ruta)
        fuente.load()
        desde = _paleta(fuente)
        # RM2k scales images with **nearest neighbor**, and the Hover Tram's
        # 65% matches that way at 97.3% against the original game's capture:
        # that checked the scaling, the anchoring and the position in one go.
        escala = una.get("escala", 100)
        ancho = fuente.width * escala // 100
        alto = fuente.height * escala // 100
        chica = fuente.resize((ancho, alto), Image.NEAREST).load()
        # Where the drawing's pixel (0,0) lands inside its first cell: the
        # image has no reason to be aligned to the 16 grid, and the tram's is
        # not.
        dx, dy = una.get("desfase", (0, 0))
        # Colors of the drawing treated as transparent besides index 0. It
        # exists for defects in the original art: a pixel painted **almost**
        # the key color but not quite, which RM2k draws and shows as a stray
        # dot. It is a declared divergence, so it is written in the recipe
        # and not hidden here.
        transparentes = {tuple(c) for c in una.get("transparentes", [])}
        for entrada in una["celdas"]:
            columna, fila, ranura = entrada[:3]
            # The fourth element, if present, is the slot the background
            # comes from: the drawing is composed **on top** of it instead of
            # overwriting it. The terrace wall of map 32 asks for it, where
            # nine pixels of the tip of the tram land on a cell that already
            # draws something.
            tile = (imagen.crop(caja_de_comun(144 + entrada[3]))
                    if len(entrada) > 3 else Image.new("P", (TILE, TILE)))
            pixeles = tile.load()
            for y in range(TILE):
                for x in range(TILE):
                    px, py = columna * TILE + x - dx, fila * TILE + y - dy
                    if not (0 <= px < ancho and 0 <= py < alto):
                        continue
                    indice = chica[px, py]
                    if indice and desde[indice] not in transparentes:
                        pixeles[x, y] = paleta.indice(_a_quince(desde[indice]))
            imagen.paste(tile, caja_de_comun(144 + ranura)[:2])

    if paleta is not None:
        paleta.aplicar(imagen)

    destino = os.path.join(generado(), "ChipSet",
                           datos["chipset"]["chipset_name"] + ".png")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    provisorio = "%s.%d.png" % (destino, os.getpid())
    imagen.save(provisorio)
    os.replace(provisorio, destino)
    return destino


def imagenes(buscar):
    """Builds the images of all the fork's ChipSets. Returns the directory
    where they ended up, to put it in the resource search."""
    for datos in chipsets().values():
        imagen_del_chipset(datos, buscar)
    return generado()

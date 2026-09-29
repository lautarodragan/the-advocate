#!/usr/bin/env python3
"""The battle scene: the backdrop and the monsters, **composited on the console**.

It lives apart from `snes_convert.py` for the same reason as `imagen.py` and
`animacion.py`: it is not a map, it is a loose drawing. What the converter
and the ROM have to share is exactly where each pixel lands and what color
it is.

taro asked for both things on 2026-09-13 —*"The battle has neither a
background image nor a monster image"*— and until 2026-09-21 they were baked
together: a 32 KB image **per troop**, with the backdrop and the battlers
already on top. That multiplied images per combination —six in `abl`, over
four backdrops— and a dead enemy was still visible. Since that day, taro's
idea, the cartridge carries **each backdrop once and each battler once**,
and the console composites them when the battle starts. See `escena_subir`
in tools/runtime/batalla_escena.s.

It is still a single 8bpp layer on BG1, and that is what buys the same as
before:

* **The screen does not have to be redone.** The 32x28 text grid is full
  —eight enemies, four actors and two message lines— and a monster drawn
  with objects would require taking something out. On the backdrop, the
  text is still visible on top.
* **There are no objects**: no OAM to build and no 34-tiles-per-line limit,
  which with four 64-pixel-wide battlers was at 32 with no margin.

## How a battler is overlaid

The SNES 8bpp is **planar**: each row of a tile is eight bytes, one per
bitplane, and planes 0/1, 2/3, 4/5 and 6/7 are interleaved in pairs. So
putting a battler over the backdrop is, per byte of each plane,
`backdrop AND NOT mask OR battler`, without touching pixel by pixel.

Each battler has **15 colors plus transparent**. Its low 4 bits come from
its drawing —index 0 is the transparent one, which is the mask— and its high
4 bits are **the palette it gets in this battle**: the ROM picks it at the
start, the troop's first distinct battler on palette 8, the second on 9, and
so on. Planes 4 to 7 are not stored: they are the mask or zero, depending on
the palette's bits. That is why the same battler serves any troop without
preparing anything per combination.

That they are fifteen colors **is an artistic decision**: color is lost
compared with the baked scene, where the battlers shared the 96 entries with
the backdrop. What was merged with what is written per battler in
`rom/parches/auto/battlers/`, like the map layers. See
`tools/port/parches.py`.

The edge changes too: before, the battler blended with the backdrop when
shrunk —`alpha_composite`— and now each pixel is either the battler's or the
backdrop's, with the cut at half the alpha. It is the cost of not preparing
anything per troop.

## The geometry

RM2k's battle backdrop is 320x160 and is drawn at the very top of a 320x240
screen. Here the screen is 256x224, so the backdrop goes in scaled to
**80%**: 256x128, which are the top seven text lines. The battlers go at the
same 80%, so the troop positions —which in the LDB are the center of each
battler, in 320x240 coordinates— map by multiplying by the same and no other
math.

The only thing that is not RM2k's is **the clipping**: a tall battler goes
past the scene's 128 pixels, so its corner is clamped inside. In RM2k it
does not go past because it has another eighty pixels of screen below.

## The budget

* **512 tiles at 8bpp, 32,768 B of VRAM**, which is exactly the 32x16 grid
  without deduplicating. A photo does not repeat, and compositing on top
  would make it repeat even less.
* **The colors**: the backdrop carries 96, CGRAM entries 32 to 127 —0 to 31
  are the two text palettes—, and the battlers **the top eight palettes**,
  128 to 255. Those are the map objects' ones, and the battle draws no
  objects; returning to the map did not restore them whole —the picture and
  the battle animation are uploaded only when they change—, so now
  `volver_de_batalla` uploads the 128 from `cgram_sombra` before anything
  else.
* **WRAM**: the clean backdrop at `$7F0000` and the composited scene at
  `$7F8000`, 32 KB each. The clean one is what allows recompositing the
  cells of a dead enemy without reading anything from the cartridge again:
  see `escena_tick`.
* In the battle's VRAM everything fits without fighting anything: the battle
  screen **does not share VRAM with the map**, because `volver_de_batalla`
  redoes it entirely on the way out. The text tiles live at $2000, their
  tilemap at $3C00, the scene's at $3800 and the scene's tiles at $4000.

## Which backdrops there are, and which ones the cartridge carries

**The game's backdrops** are all the ones a battle can ask for: those named
by the `EnemyEncounter`s and the `ChangeBattleBG`s, those of the map tree and
those of the terrains —see `fondos_del_juego`—. Each one has a **number**,
its place in that list sorted by name, and the number does not depend on
which maps the cartridge carries: it is what gives each backdrop a fixed
place in the `.msu`, which carries **all** of them, in quality
(tools/port/msu_datos.py).

**The ROM carries, in the light fallback, all the ones the cartridge's
battles can ask for**: those a troop names, those of the maps with random
encounters and, if the map names none, those of the terrains its cells
stand on. taro asked for it on 2026-09-27, with the quality as low as needed
for them to fit: see "The light fallback". Until that day it carried three,
and the other battles used the replacement.

**The replacement**, `reemplazo()`, is left for what the ROM cannot know at
conversion time: a troop that fights with the "local" backdrop on a map
without random encounters, where the backdrop comes from the terrain under
the hero and any terrain of the map is possible. In `release` only test
pages do that. Not black, because "black is confusing", taro's words. With
MSU-1, each battle reads its own from the `.msu`, whether or not it is in
the ROM.

The flat backdrop —zeros, which is black— is left for the battle that has no
backdrop: an `EnemyEncounter` with an empty name, or a terrain without a
backdrop. It is the same as RM2k does, and it is the same code with the
backdrop at zero.

## The light fallback

And since that same day **they are not the same**: the `.msu` carries the
quality backdrop —8bpp, 96 colors, 32 KB— and the ROM one of **16 colors at
half resolution, 128x64 at 4bpp: 4 KB**, which the ROM doubles in size. It
is what someone playing without MSU-1 sees, and it can be told apart by eye
from the quality one, which is what taro asked for to know which side it
came from.

Until 2026-09-27 it was 256x128, 16 KB, and the ROM carried three. That day
taro asked that all the ones `release`'s maps ask for fit "with the quality
as low as it takes", and every option was measured —the figures and the
images, in `workflow/tasks/*/todos-los-fondos-en-la-rom.md`—: at 256x128,
not even with LZ2 do they fit without eating the banks the main path of the
world needs; with four colors at 2bpp the shades are lost; and deduplicating
tiles saves almost nothing, because a photo does not repeat. At 128x64 each
backdrop weighs a quarter, and the sixteen colors stay.

The layer is still **a single one at 8bpp**: the only thing that changes is
how the fallback travels. Its sixteen colors go in the `CGRAM_BASE` palette
—entries 32 to 47—, so at 8bpp its indices are `CGRAM_BASE + i` and planes
4 to 7 of all its pixels are the same: those of `CGRAM_BASE`. The ROM first
fills the two WRAM buffers with those fixed planes, by DMA, and then
doubles the small one with the CPU: each pixel twice across and each row
twice down. From there on everything is the same —compositing, erasing a
dead one, uploading to VRAM—, because what is left in WRAM is an 8bpp
backdrop like the `.msu` one. See `esc_llenar` and `esc_doblar` in
tools/runtime/batalla_escena.s, and `respaldo_bytes` in snes_convert.py for
the order the bytes travel in, which is the one that saves the ROM math.

The other way out was for the `.msu` to carry 4bpp too, "more quality within
the same format"; but sixteen colors are the ceiling of 4bpp, so the quality
would have nowhere to grow.

The sixteen come from `asignador.merge_least_visible`, the battlers' one,
and not from `paleta.reducir`, which is the one that builds the 96: reducir
keeps the most used, and in a backdrop the sixteen most used are all from
the floor and the walls —the green sign and the violet water turned gray—.
Merging by what shows the least keeps the accents. The 96 did not change
reducer because they are the bytes of the `.msu`, and with them its
signature.
"""

import collections
import os

from common import perillas

# The scene, in screen pixels: the top seven text lines.
ANCHO, ALTO = 256, 128
# RM2k's battle backdrop and the screen it lives on, where the 80% comes from.
FONDO_RM = (320, 160)
PANTALLA_RM = (320, 240)
ESCALA_NUM, ESCALA_DEN = ANCHO, FONDO_RM[0]     # 256/320

# The backdrop's colors, and from which CGRAM entry they go. See "The
# budget".
COLORES = 96
CGRAM_BASE = 32
# Those of the light fallback, which goes at 4bpp: see "The light fallback".
# They fit in a palette of sixteen, and `CGRAM_BASE` has to be the start of
# one so that planes 4 to 7 are the same on all its pixels.
RESPALDO_COLORES = 16
RESPALDO_PLANOS = 4
assert CGRAM_BASE % RESPALDO_COLORES == 0
# And it goes at half resolution: the ROM doubles each pixel across and down.
# `esc_doblar` is written for double and nothing else.
RESPALDO_ESCALA = 2
RESPALDO_ANCHO = ANCHO // RESPALDO_ESCALA
RESPALDO_ALTO = ALTO // RESPALDO_ESCALA
# The battlers' palettes: 8 to 15, that is entries 128 to 255. One per
# distinct battler of the troop, and a troop has at most eight enemies, so
# there are always enough.
BATTLER_PALETA = 8
BATTLER_PALETAS = 8
BATTLER_COLORES = 15

CELDA = 8
TILES_X, TILES_Y = ANCHO // CELDA, ALTO // CELDA
TILES = TILES_X * TILES_Y                       # 512, the whole grid

# Where it lives in VRAM, in words. The tilemap goes before the text's
# —$3C00— and the tiles after, which is the only 32 KB gap left.
VRAM_MAPA = 0x3800
VRAM_TILES = 0x4000

def reemplazo():
    """The backdrop of the battles whose backdrop is not in the ROM: see
    "Which backdrops there are". The game chooses it, in
    `[battle] fallback_backdrop` of the project file, with its reason."""
    return perillas.valor("battle", "fallback_backdrop", tipo=str)

# How many planes the cartridge stores per row of a battler: the mask and the
# four of its drawing. The ROM sets the other four according to the palette.
BATTLER_PLANOS = 5


def escalar(valor):
    """An RM2k length in scene pixels. The same math on both sides, with
    integers: `//` would round differently from the hardware divider only
    with negatives, and there are none here."""
    return max(1, (valor * ESCALA_NUM + ESCALA_DEN // 2) // ESCALA_DEN)


def _abrir(game_dir, carpeta, nombre, rtp=False):
    """A game PNG with color 0 as transparent, which is RM2k's rule. It comes
    from `render_map.load_image` so as not to have two ways of reading the
    same thing.

    With `rtp`, if the game does not have it, it is looked up in the RTP,
    like RM2k. Only the backdrops ask for it: thirteen of the game's are from
    the RTP —`Cave1`, `Castle`, the terrain ones—, and until 2026-09-27 it
    was not needed because the ROM's three are the game's. The battlers still
    do not look there, so as not to change which ones get in without looking
    at it."""
    from render import render_map
    from rpgmaker import recursos
    lugares = [game_dir] + ([recursos.RTP_DIR] if rtp else [])
    camino = recursos.find_resource(lugares, carpeta, nombre,
                                    (".png", ".bmp", ".xyz"))
    if camino is None:
        return None
    return render_map.load_image(camino)


# --- the battler's hue -------------------------------------------------------

def _div(a, b):
    """C's integer division, which truncates toward zero. `//` rounds down,
    and with negative numerators —the hue of a color where green is less
    than blue— it would give a hue off by one."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _a_hsl(r, g, b):
    """easyrpg-player's `RGB_to_HSL`, `bitmap_hslrgb.h`, with its integers."""
    if r > g:
        orden = ("rbg" if g < b else "rgb") if r > b else "brg"
    else:
        orden = ("gbr" if g > b else "bgr") if r < b else "grb"
    if orden == "rgb":
        c = r - b; h = 0 if c == 0 else _div(0x100 * (g - b), c); l2 = r + b
    elif orden == "rbg":
        c = r - g; h = 0 if c == 0 else _div(0x100 * (g - b), c) + 0x600
        l2 = r + g
    elif orden == "grb":
        c = g - b; h = 0 if c == 0 else _div(0x100 * (b - r), c) + 0x200
        l2 = g + b
    elif orden == "gbr":
        c = g - r; h = 0 if c == 0 else _div(0x100 * (b - r), c) + 0x200
        l2 = g + r
    elif orden == "brg":
        c = b - g; h = 0 if c == 0 else _div(0x100 * (r - g), c) + 0x400
        l2 = b + g
    else:
        c = b - r; h = 0 if c == 0 else _div(0x100 * (r - g), c) + 0x400
        l2 = b + r
    if l2 == 0:
        return h, 0, 0
    s = _div(0x100 * c, (0x1FF - l2) if l2 > 0xFF else l2)
    return h, s, l2 // 2


def _de_hsl(h, s, l):
    """easyrpg-player's `HSL_to_RGB`."""
    l2 = 2 * l
    c = _div(s * ((0x1FF - l2) if l2 > 0xFF else l2), 0x100)
    m = _div(l2 - c, 2)
    h0 = h & 0xFF
    h1 = 0xFF - h0
    sector = h >> 8
    if sector == 0:
        return m + c, m + _div(h0 * c, 0x100), m
    if sector == 1:
        return m + _div(h1 * c, 0x100), m + c, m
    if sector == 2:
        return m, m + c, m + _div(h0 * c, 0x100)
    if sector == 3:
        return m, m + _div(h1 * c, 0x100), m + c
    if sector == 4:
        return m + _div(h0 * c, 0x100), m, m + c
    return m + c, m, m + _div(h1 * c, 0x100)


def girar_tono(imagen, grados):
    """`Bitmap::HueChangeBlit`: the enemy's `battler_hue`, in degrees.

    It is what makes the same `BLmouse` be the GiantRat, the MutantMouse and
    the HairyVermin. The baked scene ignored it; now, with one battler per
    enemy and not per image, ignoring it would draw all three the same.
    """
    tono = int(grados / 60.0 * 0x100)
    if tono < 0:
        tono += ((-tono + 0x5FF) // 0x600) * 0x600
    elif tono > 0x600:
        tono -= (tono // 0x600) * 0x600
    salida = imagen.copy()
    datos = []
    for r, g, b, a in imagen.get_flattened_data():
        if a > 0:
            h, s, l = _a_hsl(r, g, b)
            h += tono
            if h >= 0x600:
                h -= 0x600
            s = min(s, 0xFF)
            l = max(0, min(l, 0xFF))
            r, g, b = (max(0, min(255, v)) for v in _de_hsl(h, s, l))
        datos.append((r, g, b, a))
    salida.putdata(datos)
    return salida


# --- the backdrop -------------------------------------------------------------

def fondos_del_juego(nombrados, tree, terrenos, game_dir):
    """The game's backdrops, in the order that gives them their number: see
    "Which backdrops there are".

    `nombrados` are the ones the commands name (`eventos.fondos_nombrados`),
    `tree` the map tree and `terrenos` each terrain's backdrop
    (`Database.terrain_backdrops`). They are sorted by name ignoring case,
    which is how RM2k looks them up, and a name that is neither in the game
    nor in the RTP is left out: in RM2k that battle has no backdrop. Returns
    the names as the game writes them the first time, in that order.
    """
    from rpgmaker import recursos
    todos = set(nombrados)
    todos |= {nombre for tipo, nombre in tree.background.values()
              if tipo == 2 and nombre}
    todos |= {nombre for nombre in terrenos.values() if nombre}
    por_clave = {}
    for nombre in sorted(todos):
        por_clave.setdefault(nombre.lower(), nombre)
    salida = []
    for clave in sorted(por_clave):
        nombre = por_clave[clave]
        if recursos.find_resource([game_dir, recursos.RTP_DIR],
                                  "Backdrop", nombre,
                                  (".png", ".bmp", ".xyz")) is None:
            print("  backdrop %r is neither in the game nor in the RTP" % nombre)
            continue
        salida.append(nombre)
    return salida


def fondo(nombre, game_dir):
    """A battle backdrop ready for the ROM, or None if it is not there.

      `indices`  256x128 CGRAM indices, row by row, already shifted by
                 `CGRAM_BASE`: it is what the console reads.
      `paleta`   its `COLORES` 15-bit colors, from `CGRAM_BASE`.
    """
    from PIL import Image
    from port.paleta import reducir
    imagen = _abrir(game_dir, "Backdrop", nombre, rtp=True)
    if imagen is None:
        return None
    imagen = imagen.convert("RGB").resize((ANCHO, ALTO), Image.LANCZOS)
    pixeles = [(r >> 3, g >> 3, b >> 3)
               for r, g, b in imagen.get_flattened_data()]
    paleta, mapa = reducir(pixeles, COLORES)
    donde = {color: i + CGRAM_BASE for i, color in enumerate(paleta)}
    indices = [[donde[mapa[pixeles[y * ANCHO + x]]] for x in range(ANCHO)]
               for y in range(ALTO)]
    return {"nombre": nombre, "indices": indices, "paleta": paleta}


def fondo_liviano(nombre, game_dir):
    """The backdrop's fallback: the one that goes in the ROM, with
    `RESPALDO_COLORES` and at half resolution.

    The same image as `fondo`, shrunk to `RESPALDO_ANCHO` x `RESPALDO_ALTO`
    and with sixteen colors merged by `asignador.merge_least_visible`: see
    "The light fallback". The palette goes from most used to least, and on
    equal counts by color, so it always comes out the same.

      `chico`    the fallback's CGRAM indices, at 128x64: what travels.
      `indices`  the same, doubled to 256x128 as the ROM leaves them in
                 WRAM: it is what the tests compare.
    """
    from PIL import Image
    from port import asignador
    imagen = _abrir(game_dir, "Backdrop", nombre, rtp=True)
    if imagen is None:
        return None
    imagen = imagen.convert("RGB").resize((RESPALDO_ANCHO, RESPALDO_ALTO),
                                          Image.LANCZOS)
    pixeles = [(r >> 3, g >> 3, b >> 3)
               for r, g, b in imagen.get_flattened_data()]
    cuenta = collections.Counter(pixeles)
    mapeo, _fusiones = asignador.merge_least_visible(cuenta, RESPALDO_COLORES)
    finales = collections.Counter()
    for color, n in cuenta.items():
        finales[mapeo[color]] += n
    paleta = sorted(finales, key=lambda c: (-finales[c], c))
    donde = {color: i + CGRAM_BASE for i, color in enumerate(paleta)}
    chico = [[donde[mapeo[pixeles[y * RESPALDO_ANCHO + x]]]
              for x in range(RESPALDO_ANCHO)] for y in range(RESPALDO_ALTO)]
    indices = [[chico[y // RESPALDO_ESCALA][x // RESPALDO_ESCALA]
                for x in range(ANCHO)] for y in range(ALTO)]
    return {"nombre": nombre, "chico": chico, "indices": indices,
            "paleta": paleta}


def tiles(indices):
    """The 8x8 tiles of a grid —the 512 of a 256x128 one—, in the order the
    tilemap reads them: row by row, without deduplicating. See "The
    budget"."""
    salida = []
    for ty in range(len(indices) // CELDA):
        for tx in range(len(indices[0]) // CELDA):
            salida.append([[indices[ty * CELDA + y][tx * CELDA + x]
                            for x in range(CELDA)] for y in range(CELDA)])
    return salida


# --- the battlers --------------------------------------------------------------

def clave(nombre, tono):
    """What a battler is called in the cartridge and in `rom/parches/`: the
    image and its hue, which is what makes it different from another with
    the same image."""
    return "%s-%d" % (nombre, tono) if tono else nombre


def battler(nombre, tono, game_dir):
    """A battler ready for the ROM, or None if the image is not there.

      `ancho`, `alto`  in scene pixels, already at 80%.
      `pixeles`        row by row, from 0 to 15: 0 is the transparent one and
                       the others the color in `paleta`, plus one.
      `paleta`         its up to fifteen 15-bit colors.
      `colores`        how many distinct ones the drawing had, already
                       shrunk.
      `fusiones`       what was merged with what to get to fifteen, as
                       `asignador.merge_least_visible` returns them.
    """
    from PIL import Image
    from port import asignador
    imagen = _abrir(game_dir, "Monster", nombre)
    if imagen is None:
        return None
    imagen = imagen.convert("RGBA")
    if tono:
        imagen = girar_tono(imagen, tono)
    ancho, alto = escalar(imagen.width), escalar(imagen.height)
    chica = imagen.resize((ancho, alto), Image.LANCZOS)
    # A pixel is either the battler's or the backdrop's: half the alpha
    # decides.
    datos = chica.get_flattened_data()
    opacos = [(r >> 3, g >> 3, b >> 3) if a >= 128 else None
              for r, g, b, a in datos]
    cuenta = collections.Counter(c for c in opacos if c is not None)
    mapeo, fusiones = asignador.merge_least_visible(cuenta, BATTLER_COLORES)
    finales = collections.Counter()
    for color, n in cuenta.items():
        finales[mapeo[color]] += n
    paleta = sorted(finales, key=lambda c: (-finales[c], c))
    lugar = {c: i + 1 for i, c in enumerate(paleta)}
    # What goes past the scene is not stored: a battler taller than it ends
    # up clamped at the top —see `posicion`— and its bottom rows are not
    # seen.
    ancho, alto = min(ancho, ANCHO), min(alto, ALTO)
    pixeles = [[0 if opacos[y * chica.width + x] is None
                else lugar[mapeo[opacos[y * chica.width + x]]]
                for x in range(ancho)] for y in range(alto)]
    return {"clave": clave(nombre, tono), "imagen": nombre, "tono": tono,
            "ancho": ancho, "alto": alto, "pixeles": pixeles,
            "alto_rm": imagen.height,
            "paleta": paleta, "colores": len(cuenta), "fusiones": fusiones}


def columnas(info):
    """How many bytes a row of a plane is: eight pixels per byte."""
    return (info["ancho"] + 7) // 8


def battler_bytes(info):
    """A battler in the format `escena_poner` reads.

    **Plane by plane**, and within each plane row by row: the mask first and
    then the four planes of the drawing. Each row of a plane is
    `columnas + 1` bytes and goes **backwards**, the rightmost column first,
    with a zero in front:

        [0] [col n-1] ... [col 1] [col 0]

    That way a sixteen-bit read at column `k` brings `k` in the low byte and
    `k - 1` in the high one, which is exactly the word that has to be shifted
    right to place a battler that does not fall on a tile boundary. Column
    `-1` is the leading zero of the next row —or of the next plane—, so the
    ROM does not have to check for the edge; the last plane carries an extra
    zero at the end for the same reason.
    """
    n = columnas(info)
    planos = []
    for plano in range(BATTLER_PLANOS):
        datos = bytearray()
        for fila in info["pixeles"]:
            bytes_fila = bytearray(n)
            for x, valor in enumerate(fila):
                prendido = (valor != 0) if plano == 0 else \
                    bool((valor >> (plano - 1)) & 1)
                if prendido:
                    bytes_fila[x // 8] |= 0x80 >> (x % 8)
            datos += bytes([0]) + bytes(reversed(bytes_fila))
        planos.append(bytes(datos))
    return b"".join(planos) + b"\x00"


def posicion(centro, info):
    """Where a battler's corner lands in the scene, already clamped inside.

    The LDB position is **the center** of the battler, on RM2k's 320x240
    screen. It is scaled like everything else and clamped inside the scene:
    see "The geometry".
    """
    x, y = centro
    px = min(max(escalar(x) - info["ancho"] // 2, 0),
             max(0, ANCHO - info["ancho"]))
    py = min(max(escalar(y) - info["alto"] // 2, 0),
             max(0, ALTO - info["alto"]))
    return px, py


def orden_de_dibujo(centros, infos):
    """The order a troop's enemies are placed in: the one that goes later
    covers.

    It is easyrpg's `Sprite_Battler::ResetZ`: the depth is the battler's
    bottom edge in RM2k —the LDB center plus half the PNG's height— and, on
    an equal edge, the one with the lower place in the troop ends up on top.
    `infos` may carry None for an enemy without a battler: it is not drawn,
    and it does not matter where it lands.
    """
    def z(k):
        alto = infos[k]["alto_rm"] if infos[k] else 0
        return (centros[k][1] + alto // 2, -k)
    return sorted(range(len(centros)), key=z)


def componer(fondo_indices, puestos):
    """The scene as the console composites it, in CGRAM indices.

    `fondo_indices` is a backdrop's grid, or None for the flat backdrop.
    `puestos` are `(info, paleta, x, y)` in the order the ROM places them,
    which is `orden_de_dibujo`: the one that goes later covers the one
    before. The converter does not use it —the ROM composites on its own—
    but the tests do, to know what has to be in each pixel.
    """
    escena = [list(fila) if fondo_indices else [0] * ANCHO
              for fila in (fondo_indices or [None] * ALTO)]
    for info, paleta, px, py in puestos:
        for y, fila in enumerate(info["pixeles"]):
            for x, valor in enumerate(fila):
                if valor and 0 <= py + y < ALTO and 0 <= px + x < ANCHO:
                    escena[py + y][px + x] = paleta * 16 + valor
    return escena


def informe_battler(info):
    """The battler's numbers, for the converter to print."""
    return {"clave": info["clave"], "ancho": info["ancho"],
            "alto": info["alto"], "bytes": len(battler_bytes(info)),
            "colores": info["colores"], "quedan": len(info["paleta"])}

#!/usr/bin/env python3
"""The **drawing** of a battle animation over the map.

It lives apart from `snes_convert.py` for the same reason as `imagen.py`: it
is not a map. It is a loose drawing that has to be put on the screen, and
the only thing to decide is **exactly where each pixel lands and what color
it is**. The sounds and flashes of the same animation are not here: those
are `OP_ANIMATION` in `eventos.py`, and they exist since 2026-09-11.

The budget, which is where everything else comes from:

* The sprite VRAM a map has left free is **101 tiles on map 2 and 162 on
  map 3**, which are the two worst of those that show animations. A 96x96
  box is 144 tiles and does not fit on map 2.
* A 32x32 object reads four tiles from four consecutive rows of the name
  grid, so **a row of blocks is 64 tiles and four objects**, not one more.
  Four objects in two by two are 64x64 pixels.
* One of those frames is 2 KB of DMA, and one goes up every two console
  frames, which is how long an animation frame lasts in RM2k.

From there comes **the 64x64 box, the same for the whole ROM**. It is not
for convenience: the box not depending on the map is what lets the game's
388 `ShowBattleAnimation` across 81 maps share the frames already converted
in the cartridge instead of emitting one copy per map.

And from there also comes what taro accepted on 2026-09-12 —*"we should be
able to pull it off if we shrink some of the effects"*—: **the animation is
shrunk whole until it fits in the box**, keeping its proportions, and how
much it was shrunk is reported by the converter animation by animation. The
small ones are barely touched —a 96x96 one ends up at 64x64, 67%— and the
big ones from the intro are: number 82 measures 536x416 and ends up at
64x49, 11%. Nothing is drawn wrong silently: the criterion is a computation,
`tamano`, and it is the one `test_parches.py` enforces.

What is lost, and it is declared in
`workflow/divergencias/la-animacion-de-batalla-achicada.md`:

* **A cell's transparency does not exist.** A console object is opaque or it
  is not there. What is done is to composite the cells with their alpha in
  the frame and then **round the alpha**: a pixel at 128 or more stays, the
  rest does not. A cell that fades out disappears when it passes the half,
  instead of going away gradually.
* **The animation is not tinted by the screen tint nor reached by the
  flash.** The first is faithful: `Spriteset_Map::Update` sets the tone on
  the tilemap, the characters, the panorama and the shadows, and not on the
  animations. The second is debt, the same the picture already has: its
  palette lands above `SPRITE_CGRAM`.
* **A target without an NPC row, or with the row hidden, gets no
  animation.** On the console there is nowhere to get its position from; in
  RM2k the animation is drawn anyway over an invisible event.
* **`global` —the one RM2k repeats three by three to cover the screen— is
  not drawn.** None of the eleven in the intro asks for it.
"""

# The box, and the 32x32 objects it is drawn with.
# Measured against A Blurred Line: an assumption of the engine, not a fact of
# the game. See `workflow/decisiones/las-herramientas-se-separan-de-abl.md`.
CAJA = 64
OBJ = 32
OBJ_LADO = OBJ // 8
GRILLA = 16                 # tiles per row of the OAM name grid
OBJETOS = (CAJA // OBJ) ** 2
TILES = 4 * GRILLA          # one row of blocks: the four objects
COLORES = 15

# The `Battle` sheet: five cells per row, of 96x96 —or 128x128 if the
# animation is `large`, which none is in ABL—. It is the `size` of
# `BattleAnimation::DrawAt`.
CELDA = 96
CELDA_GRANDE = 128
COLUMNAS = 5

# `character_height` of `BattleAnimationMap::DrawSingle`, and the center of
# RM2k's screen, which is where those with "screen" scope land.
ALTO_PERSONAJE = 24
PANTALLA_RM = (320, 240)
PANTALLA = (256, 224)

# The three values of `Animation::Position`, which is what shifts the
# animation up or down from the target.
POS_ARRIBA, POS_CENTRO, POS_ABAJO = 0, 1, 2
ALCANCE_PANTALLA = 1        # `Animation::Scope_screen`

# The alpha from which a pixel is drawn. Half, rounding up: a pixel that is
# half and half stays.
ALFA_MINIMO = 128

_CACHE = {}


def hoja_de(renderer, anim):
    """The `Battle` sheet of this animation, or None if it has none or it is
    not there."""
    from render import render_map
    from rpgmaker import recursos
    nombre = anim.get("imagen") or ""
    if not nombre:
        return None
    carpeta = "Battle2" if anim.get("grande") else "Battle"
    path = recursos.find_resource(renderer.search_dirs, carpeta, nombre)
    return render_map.load_image(path) if path else None


def _celdas_vivas(anim, i):
    """The valid cells of frame `i`, in the LDB's order.

    `valid` defaults to 1 —liblcf, `AnimationCellData`— so a cell without the
    field counts. The invalid ones are the holes the editor leaves when a
    cell in the middle is deleted.
    """
    return [c for _k, c in sorted((anim["cuadros"][i] or {}).items())
            if c.get("valid", 1)]


def _lado(anim, celda):
    """How big a cell is on screen with its zoom, in RM2k pixels."""
    lado = CELDA_GRANDE if anim.get("grande") else CELDA
    return max(1, lado * celda.get("zoom", 100) // 100)


def caja_rm(anim):
    """The rectangle the whole animation takes in RM2k pixels, relative to
    its anchor: (x0, y0, ancho, alto).

    It is the union of all the cells of all the frames, not that of the
    biggest frame: the console box is a single one for the whole animation,
    so a frame that shifts to one side has to fit all the same.
    """
    x0 = y0 = None
    x1 = y1 = None
    for i in range(len(anim["cuadros"])):
        for celda in _celdas_vivas(anim, i):
            lado = _lado(anim, celda)
            cx, cy = celda.get("x", 0), celda.get("y", 0)
            a, b = cx - lado // 2, cy - lado // 2
            x0 = a if x0 is None else min(x0, a)
            y0 = b if y0 is None else min(y0, b)
            x1 = a + lado if x1 is None else max(x1, a + lado)
            y1 = b + lado if y1 is None else max(y1, b + lado)
    if x0 is None:
        return None
    return x0, y0, x1 - x0, y1 - y0


def tamano(ancho, alto):
    """The size an animation of `ancho` x `alto` is shrunk to in order to
    fit in the box, keeping its proportions.

    The denominator is the side that overflows the most, and never less than
    the box: an animation that already fits is not enlarged. Done with
    integers.
    """
    den = max(ancho, alto, CAJA)
    return max(1, ancho * CAJA // den), max(1, alto * CAJA // den)


def _pintar_cuadro(anim, hoja, i, caja):
    """A frame in RM2k pixels, the size of `caja`, with alpha.

    It is `BattleAnimation::DrawAt` without the screen: each cell comes from
    the sheet, is scaled by its zoom, gets its tone and transparency applied,
    and is composited centered at its (x, y).
    """
    from PIL import Image
    from port import eventos
    x0, y0, ancho, alto = caja
    canvas = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    lado_hoja = CELDA_GRANDE if anim.get("grande") else CELDA
    for celda in _celdas_vivas(anim, i):
        cid = celda.get("cell_id", 0)
        sx, sy = (cid % COLUMNAS) * lado_hoja, (cid // COLUMNAS) * lado_hoja
        if sx + lado_hoja > hoja.width or sy + lado_hoja > hoja.height:
            continue            # a cell the sheet does not have: RM2k draws nothing
        trozo = hoja.crop((sx, sy, sx + lado_hoja, sy + lado_hoja))
        lado = _lado(anim, celda)
        if lado != lado_hoja:
            trozo = trozo.resize((lado, lado), Image.BILINEAR)
        tono = (celda.get("tone_red", 100), celda.get("tone_green", 100),
                celda.get("tone_blue", 100), celda.get("tone_gray", 100))
        if tono != (100, 100, 100, 100):
            trozo = _tenir(trozo, tono)
        opacidad = 100 - max(0, min(100, celda.get("transparency", 0)))
        if opacidad != 100:
            alfa = trozo.getchannel("A").point(
                lambda v: v * opacidad // 100)
            trozo.putalpha(alfa)
        canvas.alpha_composite(
            trozo, (celda.get("x", 0) - lado // 2 - x0,
                    celda.get("y", 0) - lado // 2 - y0))
    return canvas


def _tenir(trozo, tono):
    """The tone of a cell, with the same math as the screen tint.

    `color.tenir` works on the console's fifteen bits, which is where the
    comparison looks: tinting the PNG's eight and truncating afterwards would
    give a different number from the screen tint's on the same color.
    """
    from port.color import tenir
    from PIL import Image
    salida = Image.new("RGBA", trozo.size)
    memo = {}
    datos = []
    for r, g, b, a in trozo.convert("RGBA").get_flattened_data():
        clave = (r >> 3, g >> 3, b >> 3)
        if clave not in memo:
            p = tenir(clave[0] | (clave[1] << 5) | (clave[2] << 10),
                              tono)
            memo[clave] = ((p & 0x1F) << 3, ((p >> 5) & 0x1F) << 3,
                           ((p >> 10) & 0x1F) << 3)
        datos.append(memo[clave] + (a,))
    salida.putdata(datos)
    return salida


def convertir(anim, hoja):
    """The animation ready for both ends, or None if it cannot be drawn.

    Returns a dictionary with:

      `cuadros`  for each RM2k frame, the 64x64 box as palette indices
                 shifted by one: 0 is the console's transparent.
      `paleta`   its fifteen 15-bit colors, chosen **over all the frames at
                 once**: the palette is uploaded only once at the start.
      `ancla`    where inside the box the point that RM2k puts over the
                 target lands. The ROM subtracts this from the target's
                 position and gets the corner of the box.
      `tam`      what it was shrunk to, and `caja_rm` what it came from.
    """
    caja = caja_rm(anim)
    if caja is None or hoja is None:
        return None
    from PIL import Image
    from port.paleta import reducir
    x0, y0, ancho, alto = caja
    ta, tal = tamano(ancho, alto)
    ox, oy = (CAJA - ta) // 2, (CAJA - tal) // 2
    cuadros = []
    for i in range(len(anim["cuadros"])):
        chico = _pintar_cuadro(anim, hoja, i, caja).resize(
            (ta, tal), Image.LANCZOS)
        entero = Image.new("RGBA", (CAJA, CAJA), (0, 0, 0, 0))
        entero.paste(chico, (ox, oy))
        cuadros.append(entero)
    # The colors of all the frames together, down to fifteen.
    # `paleta.reducir` does not average, so it does not invent a color that
    # would have to be quantized again.
    pixeles = []
    for entero in cuadros:
        for r, g, b, a in entero.get_flattened_data():
            if a >= ALFA_MINIMO:
                pixeles.append((r >> 3, g >> 3, b >> 3))
    if not pixeles:
        return None
    paleta, mapa = reducir(pixeles, COLORES)
    donde = {color: i + 1 for i, color in enumerate(paleta)}
    indices = []
    for entero in cuadros:
        datos = entero.get_flattened_data()
        indices.append([
            [donde[mapa[(datos[y * CAJA + x][0] >> 3,
                         datos[y * CAJA + x][1] >> 3,
                         datos[y * CAJA + x][2] >> 3)]]
             if datos[y * CAJA + x][3] >= ALFA_MINIMO else 0
             for x in range(CAJA)]
            for y in range(CAJA)])
    return {
        "cuadros": indices,
        "paleta": paleta,
        "ancla": (ox + (-x0) * ta // ancho, oy + (-y0) * tal // alto),
        "tam": (ta, tal),
        "caja_rm": (ancho, alto),
        "alcance": anim.get("alcance", 0),
        "posicion": anim.get("posicion", POS_CENTRO),
    }


def de_numero(renderer, numero):
    """Animation `numero` converted, cached per process.

    Converting one is a handful of large `resize`s, and the converter asks
    for it once per map that shows it.
    """
    from port import eventos
    if numero in _CACHE:
        return _CACHE[numero]
    anim = eventos.ANIMACIONES.get(numero)
    salida = convertir(anim, hoja_de(renderer, anim)) if anim else None
    _CACHE[numero] = salida
    return salida


def ancla_rom(info):
    """The anchor as the ROM's table carries it: (ax, ay).

    The vertical shift of `Animation::Position` is baked into it, since it
    is fixed per animation, so the console only has to subtract. With
    "screen" scope there is no shift: `DrawSingle` draws at the center
    without asking the target anything.
    """
    ax, ay = info["ancla"]
    if info["alcance"] == ALCANCE_PANTALLA:
        return ax, ay
    corrida = {POS_ARRIBA: -(ALTO_PERSONAJE // 2), POS_CENTRO: 0,
               POS_ABAJO: ALTO_PERSONAJE // 2}[info["posicion"]]
    return ax, ay + ALTO_PERSONAJE // 2 - corrida


def celdas(cuadro):
    """A frame cut into 8x8 tiles, in the order OAM numbers them.

    The four objects fit in one row of blocks —64 tiles— and object `o`
    starts at `o * 4`; inside it, tile (tx, ty) is `ty` grid rows further
    on. It is the same arithmetic as `imagen.celdas`, which is where it came
    from.

    On screen the objects go two by two: `o` at `(o % 2 * 32, o // 2 * 32)`
    of the box.
    """
    salida = {}
    for o in range(OBJETOS):
        arranca = (o % 4) * OBJ_LADO
        base_x, base_y = (o % 2) * OBJ, (o // 2) * OBJ
        for ty in range(OBJ_LADO):
            for tx in range(OBJ_LADO):
                celda = tuple(
                    tuple(cuadro[base_y + ty * 8 + py][base_x + tx * 8 + px]
                          for px in range(8))
                    for py in range(8))
                salida[arranca + ty * GRILLA + tx] = celda
    return salida


def render(info, cuadro):
    """The frame as it looks on screen: a 64x64 RGBA image to paste wherever
    `ancla_en_pantalla` says."""
    from PIL import Image
    colores = [(0, 0, 0, 0)] + [(r << 3, g << 3, b << 3, 255)
                                for r, g, b in info["paleta"]]
    salida = Image.new("RGBA", (CAJA, CAJA))
    salida.putdata([colores[i] for fila in info["cuadros"][cuadro]
                    for i in fila])
    return salida


def informe(numero, info):
    """The numbers that justify the layout, for the recipe to print."""
    ancho, alto = info["caja_rm"]
    ta, tal = info["tam"]
    return {
        "animacion": numero,
        "cuadros": len(info["cuadros"]),
        "original": (ancho, alto),
        "caja": (ta, tal),
        "porciento": 100 * ta // ancho,
        "colores": len(info["paleta"]),
        "bytes": len(info["cuadros"]) * TILES * 32,
    }

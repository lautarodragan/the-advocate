"""La pantalla de End Game del menú de pausa: `Scene_End` de RM2k.

Son dos ventanas sobre negro: arriba la pregunta —el término
`exit_game_message` del LDB, "End game?" en el ABL— y abajo "Yes" y "No"
—`yes` y `no`—, con la barra del System sobre la que se elige. Las reglas
salen de `Scene_End::CreateCommandWindow` y `CreateHelpWindow` de
easyrpg-player, y las medidas se compararon contra el RPG_RT de 2015
corriendo con Wine: con estas mismas cuentas a 320x240, las ventanas, el
texto y la barra caen en los mismos pixeles que en la captura del original.
Lo que difiere son cosas de `ventana.py` y de la fuente, que valen para todas
las ventanas del port: la franja clara del fondo estirado cae unas filas
corrida, y un par de glifos —la "g"— no son idénticos.

**Va dibujada entera, como una imagen**, y no con la fuente de a una letra
por celda de la pantalla de ítems: es una pantalla fija de tres palabras, así
que la letra puede ir a los 6 pixeles de la fuente, como en RM2k, y las
ventanas medir lo que miden allá. Va en BG1 de 8bpp, que en modo 3 direcciona
CGRAM entera.

**El cursor no mueve tiles: cambia colores.** Las dos imágenes —con la barra
en "Yes" y con la barra en "No"— comparten los tiles y el tilemap, y lo que
las distingue son los pixeles de las dos barras. Cada par (color con el
cursor en Yes, color con el cursor en No) que aparece en la imagen es una
entrada de CGRAM propia: los pixeles que no cambian tienen el mismo color en
las dos, y los de las barras, uno distinto. Mover el cursor es escribir esas
pocas entradas con la paleta de la otra imagen, en el vblank. Así no hay un
segundo tilemap ni tiles de más.
"""

from port import constantes
from port import ventana as ventana_mod

ANCHO, ALTO = constantes.ANCHO, constantes.ALTO
CELL = constantes.CELL
NEGRO = (0, 0, 0)

# `menu_item_height` de Window_Selectable y los bordes de Window.
LINEA = 16
BORDE = 8
# Las dos ventanas en RM2k, que es de 320x240: la pregunta en y=72 y las
# órdenes 48 más abajo, centradas en x. Acá la pantalla mide 256x224, así que
# se centran en 256 y se suben 8, la mitad de las 16 filas que faltan.
Y_PREGUNTA = 72
Y_ORDENES = 72 + 48
SUBIR = (240 - ALTO) // 2

# Qué orden marca el cursor al entrar. El RPG_RT de 2015 entra con "Yes",
# medido con Wine; easyrpg-player entra con "No" (`SetIndex(1)`). Vale el
# original.
SI, NO = 0, 1
ENTRA = SI


def textos(db):
    """La pregunta y las dos órdenes, del LDB, con los mismos textos de
    repuesto que easyrpg si el término está vacío."""
    t = db.terminos
    def uno(nombre, repuesto):
        valor = t.get(nombre, b"").decode("cp1252")
        return valor or repuesto
    return (uno("exit_game_message", "Do you really want to quit?"),
            uno("yes", "Yes"), uno("no", "No"))


def _ancho_de(texto):
    from port import fuente
    return len(texto) * fuente.ANCHO


def dibujar(sys_img, db, elegida, font_id=None, ancho=ANCHO, alto=ALTO,
            subir=SUBIR):
    """La pantalla en RGB, con el cursor en `elegida`. `ancho`, `alto` y
    `subir` en 320, 240 y 0 dan la de RM2k, que es con la que se compara
    contra la captura del original."""
    from PIL import Image
    pregunta, si, no = textos(db)
    if _ancho_de(pregunta) + 2 * BORDE > ancho:
        # RM2k la dejaría salirse de la pantalla; acá se cortaría sin avisar.
        raise SystemExit("la pregunta de End Game, %r, no entra en %d "
                         "pixeles" % (pregunta, ancho))
    fuera = Image.new("RGBA", (ancho, alto), NEGRO + (255,))

    def pegar(una, x, y):
        fuera.paste(una, (x, y), una)

    # La pregunta: `Window_Help`, del ancho del texto más los bordes, con el
    # texto en (0, 2) de su contenido.
    w = _ancho_de(pregunta) + 2 * BORDE
    x, y = ancho // 2 - w // 2, Y_PREGUNTA - subir
    pegar(ventana_mod.ventana(sys_img, w, 2 * LINEA), x, y)
    ventana_mod.dibujar_linea(fuera, sys_img, x + BORDE, y + BORDE + 2,
                              pregunta, font_id=font_id)

    # Las órdenes: `Window_Command`, del ancho de la más larga más los bordes
    # y de dieciséis por orden más los bordes. La barra es la de
    # `UpdateCursorRect`: cuatro más a cada lado del contenido.
    ordenes = (si, no)
    w = max(_ancho_de(o) for o in ordenes) + 2 * BORDE
    x, y = ancho // 2 - w // 2, Y_ORDENES - subir
    pegar(ventana_mod.ventana(sys_img, w, len(ordenes) * LINEA + 2 * BORDE),
          x, y)
    pegar(ventana_mod.cursor(sys_img, w - 2 * BORDE + 8, LINEA),
          x + BORDE - 4, y + BORDE + elegida * LINEA)
    for n, orden in enumerate(ordenes):
        ventana_mod.dibujar_linea(fuera, sys_img, x + BORDE,
                                  y + BORDE + n * LINEA + LINEA // 8, orden,
                                  font_id=font_id)
    return fuera.convert("RGB")


# --- lo que va al cartucho ----------------------------------------------------
#
# BG2, a 4bpp y con la paleta 0: los tiles desde `RANURA_VRAM` y el tilemap en
# `RANURA_MAP`, que son los lugares de la VRAM que ya escriben el menú y la
# pantalla de ranuras —ver `volver_al_mapa`—, así que el mapa vuelve sin que
# haya que reponer nada más. La paleta es la de las entradas 0 a 15, que
# también repone el menú al volver.
COLORES_MAX = 16
# Cuántos cuadros dura el fundido a negro de "Yes", y cuánto el del tema: el
# de la pantalla medido en el RPG_RT de 2015 —unos 330 ms—, y el del tema el
# `BgmFade(400)` de `Scene_End`.
CUADROS_FUNDIDO = 20
MS_FUNDIDO_TEMA = 400


def rampa():
    """El brillo de INIDISP en cada cuadro del fundido a negro: una recta de
    15 a 0 en `CUADROS_FUNDIDO` pasos, el último en negro."""
    ultimo = CUADROS_FUNDIDO - 1
    return [15 * (ultimo - n) // ultimo for n in range(CUADROS_FUNDIDO)]


def convertir(sys_img, db, font_id=None):
    """La pantalla como la sube la ROM: `(tiles, filas, fila0, paletas)`.

    `tiles[i][y][x]` son índices de 0 a 15, y el 0 es el tile vacío;
    `filas` las palabras del tilemap de las filas de celdas que tienen algo,
    desde la `fila0`; el resto del tilemap va en cero. `paletas` son dos
    listas de 16 colores de 15 bits: la de la barra en "Yes" y la de la barra
    en "No". Ver el encabezado: un índice por par de colores.
    """
    quince = [[tuple(v >> 3 for v in p) for p in
               dibujar(sys_img, db, n, font_id).get_flattened_data()]
              for n in (SI, NO)]
    pares = sorted(set(zip(*quince)))
    pares.remove((NEGRO, NEGRO))
    pares.insert(0, (NEGRO, NEGRO))     # el 0: transparente, el fondo negro
    if len(pares) > COLORES_MAX:
        raise SystemExit("la pantalla de End Game usa %d pares de colores y "
                         "una paleta de 4bpp tiene %d" % (len(pares),
                                                           COLORES_MAX))
    indice = {par: i for i, par in enumerate(pares)}
    pixeles = [indice[par] for par in zip(*quince)]
    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde, mapa = [vacio], {vacio: 0}, []
    for fila in range(ALTO // CELL):
        for col in range(ANCHO // CELL):
            celda = tuple(tuple(pixeles[(fila * CELL + y) * ANCHO
                                        + col * CELL:(fila * CELL + y) * ANCHO
                                        + col * CELL + CELL])
                          for y in range(CELL))
            # Espejados también, con los bits de volteo del tilemap: el marco
            # de las ventanas es simétrico.
            h = tuple(tuple(reversed(r)) for r in celda)
            for volteo, forma in ((0, celda), (0x4000, h),
                                  (0x8000, tuple(reversed(celda))),
                                  (0xC000, tuple(reversed(h)))):
                if forma in donde:
                    mapa.append(donde[forma] | volteo)
                    break
            else:
                donde[celda] = len(tiles)
                tiles.append(celda)
                mapa.append(donde[celda])
    cols = ANCHO // CELL
    usadas = [f for f in range(ALTO // CELL) if any(mapa[f * cols:(f + 1) * cols])]
    fila0, fila1 = usadas[0], usadas[-1] + 1
    paletas = [[par[n] for par in pares] + [NEGRO] * (COLORES_MAX - len(pares))
               for n in (SI, NO)]
    return tiles, mapa[fila0 * cols:fila1 * cols], fila0, paletas


def render(sys_img, db, elegida, font_id=None):
    """Lo que la ROM tiene que mostrar, reconstruido desde `convertir` y no
    desde `dibujar`: los tiles, el tilemap y la paleta, a 15 bits. Así el
    dibujo contra el que se compara la ROM pasa por la misma cuenta de pares
    de colores que ella."""
    from PIL import Image
    tiles, filas, fila0, paletas = convertir(sys_img, db, font_id)
    paleta = paletas[elegida]
    fuera = Image.new("RGB", (ANCHO, ALTO), NEGRO)
    px = fuera.load()
    cols = ANCHO // CELL
    for n, palabra in enumerate(filas):
        celda = tiles[palabra & 0x3FF]
        if palabra & 0x4000:
            celda = tuple(tuple(reversed(r)) for r in celda)
        if palabra & 0x8000:
            celda = tuple(reversed(celda))
        fila, col = fila0 + n // cols, n % cols
        for y in range(CELL):
            for x in range(CELL):
                r, g, b = paleta[celda[y][x]]
                px[col * CELL + x, fila * CELL + y] = (r << 3, g << 3, b << 3)
    return fuera

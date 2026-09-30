#!/usr/bin/env python3
"""Arma `menu-modo-5.sfc`: la maqueta del menú de pausa como imagen fija.

No es el juego y no pasa por el conversor: es una prueba de hardware, para
que taro vea en su SNES si las columnas de un pixel del modo 5 se leen por
su salida de video. Lo corre `just menu-modo-5`, que después la verifica en
los emuladores con `verificar.py`.

    armar.py <salida.sfc>

Convierte las tres imágenes de `maqueta/` a lo que lee la PPU, escribe
`datos.inc` y los `.bin` al lado de la salida, y arma `menu.s` con `ca65` y
`ld65`.

**Por qué no usa Voodoo ni Adeleine.** Agrupar los colores de cada celda en
paletas es de Adeleine, y acá se hace a mano porque no hay nada que perder:
las maquetas ya traen los colores que van, entran sin tocar uno, y si no
entraran el script se niega. Y Voodoo no sabe de las celdas de 16x8 del
modo 5 —dos tiles de 8x8 consecutivos por entrada del tilemap—: numera los
tiles de a uno y los reusa espejados, así que el par se le parte. Para el
menú de verdad le haría falta ese modo.
"""
import os
import subprocess
import sys

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))

# Las tres pantallas, en el orden en que las muestra la ROM. `modo` es el
# BGMODE: 5 es la alta resolución, 3 el menú de hoy (BG1 de 8 bits, el modo
# del juego). La marca es el número que se dibuja en la esquina.
PANTALLAS = [
    ("04-modo5-x1.5.png", 5, 1),
    ("02-modo5-simple.png", 5, 2),
    ("01-hoy.png", 3, 3),
]

# **Dónde están las caras en las maquetas de 512**: la franja entre la
# ventana de las órdenes y el texto del grupo. Adentro no hay otra cosa —se
# midió—, y el script igual verifica que cada pixel salga doble, que es lo
# que pide un sprite, que en modo 5 sigue siendo de 256.
#
# Van como sprites porque en el fondo no entran: una celda de 16x8 que
# cruza una cara lleva hasta 19 colores, y una paleta de 4 bits, 15.
FRANJA_CARAS = (156, 236, 8, 200)  # x0, x1, y0, y1, en pixeles de alta

# La memoria de video, en palabras. Los tiles del fondo desde 0 —hasta 768
# de 8 bits caben antes de los sprites—, los de los sprites en $6000
# (OBSEL = 3) y el tilemap de 32x32 en $7000 (BG1SC = $70). Lo repite
# `menu.s`.
VRAM_FONDO = 0x0000
VRAM_SPRITES = 0x6000
VRAM_MAPA = 0x7000

# La paleta de sprites de la marca: la última, que las caras no usan.
PALETA_MARCA = 7
# Y dónde se dibuja, en pixeles de 256: sobre la ventana del oro en las de
# modo 5. Tapa lo que haya abajo; B la esconde para comparar entera.
MARCA_X, MARCA_Y = 8, 206
TILE_MARCA = 255

BANCOS = 4           # 128 KB: el banco 0 es el código, los otros tres datos
BANCO = 0x8000

# Los dígitos de la marca, 5x7: blanco con un borde negro, para que se lea
# sobre cualquier fondo.
DIGITOS = {
    1: ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    2: [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    3: [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
}


def a15(color):
    """El color como lo guarda la CGRAM: `0BBBBBGGGGGRRRRR`, truncado."""
    r, g, b = color[:3]
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def planar(filas, bits):
    """Un tile de 8x8 en planos: de a pares, 16 bytes por par."""
    salida = bytearray()
    for par in range(0, bits, 2):
        for fila in filas:
            for plano in (par, par + 1):
                byte = 0
                for x, indice in enumerate(fila):
                    byte |= ((indice >> plano) & 1) << (7 - x)
                salida.append(byte)
    return bytes(salida)


def empaquetar(conjuntos, capacidad, cuantas, que):
    """Reparte conjuntos de colores en paletas, el primero que entre, de
    los más grandes a los más chicos. Devuelve las paletas como listas."""
    paletas = []
    for conjunto in sorted(set(conjuntos), key=lambda c: (-len(c), sorted(c))):
        for paleta in paletas:
            if len(paleta | conjunto) <= capacidad:
                paleta |= conjunto
                break
        else:
            paletas.append(set(conjunto))
    if len(paletas) > cuantas:
        sys.exit("%s: hacen falta %d paletas de %d colores y hay %d"
                 % (que, len(paletas), capacidad, cuantas))
    return [sorted(p) for p in paletas]


def cual_paleta(paletas, conjunto):
    for i, paleta in enumerate(paletas):
        if conjunto <= set(paleta):
            return i
    raise AssertionError(conjunto)


def tile_marca(digito):
    """El dígito en un tile de 8x8 de sprite: 1 blanco, 2 el borde."""
    tinta = {(x + 1, y) for y, fila in enumerate(DIGITOS[digito])
             for x, c in enumerate(fila) if c == "#"}
    filas = []
    for y in range(8):
        fila = []
        for x in range(8):
            if (x, y) in tinta:
                fila.append(1)
            elif any((x + dx, y + dy) in tinta
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                fila.append(2)
            else:
                fila.append(0)
        filas.append(fila)
    return planar(filas, 4)


def caras(pix, ancho, alto):
    """Saca las caras de la imagen y las devuelve como bandas de sprites.

    Cada cara se corta en bandas de filas de hasta 15 colores, de arriba
    para abajo, y cada banda es una grilla de sprites de 8x8 que arranca en
    su primera fila: dos bandas se tocan pero no se pisan, porque cada una
    deja transparente lo que no es suyo. Deja el lugar de la cara en negro,
    que es lo que había abajo."""
    x0, x1, y0, y1 = FRANJA_CARAS
    filas = {}
    for y in range(y0, y1):
        for x in range(x0, x1):
            if pix[y][x] != 0:
                if pix[y][x] != pix[y][x ^ 1]:
                    sys.exit("la cara en (%d, %d) no sale doble: un sprite "
                             "de modo 5 no la puede dibujar" % (x, y))
                filas.setdefault(y, {})[x // 2] = pix[y][x]
    for y, fila in filas.items():
        for x in fila:
            pix[y][2 * x] = pix[y][2 * x + 1] = 0
    bandas = []
    banda = None
    for y in sorted(filas):
        colores = set(filas[y].values())
        if (banda is None or y != banda["y1"] + 1
                or len(banda["colores"] | colores) > 15):
            banda = {"y0": y, "y1": y, "colores": set(), "pixeles": {}}
            bandas.append(banda)
        banda["y1"] = y
        banda["colores"] |= colores
        for x, c in filas[y].items():
            banda["pixeles"][(x, y)] = c
    return bandas


def convertir(archivo, modo, marca):
    imagen = Image.open(os.path.join(AQUI, "maqueta", archivo)).convert("RGB")
    ancho, alto = imagen.size
    if (modo == 5) != (ancho == 512) or alto != 224:
        sys.exit("%s: %dx%d no es una pantalla de modo %d"
                 % (archivo, ancho, alto, modo))
    datos = imagen.load()
    # El negro es el 0: el fondo de la pantalla, y lo que muestra la
    # subpantalla donde no hay nada (COLDATA en negro).
    pix = [[a15(datos[x, y]) for x in range(ancho)] for y in range(alto)]

    cgram = [0] * 256
    tiles = bytearray()
    mapa = [0] * (32 * 32)
    oam = []
    sprites = bytearray(bytes(32) * 256)

    if modo == 5:
        bandas = caras(pix, ancho, alto)
        # El fondo: celdas de 16x8, cada una con una paleta de 15.
        celdas = {}
        for cy in range(28):
            for cx in range(32):
                celdas[cx, cy] = frozenset(
                    pix[y][x] for y in range(cy * 8, cy * 8 + 8)
                    for x in range(cx * 16, cx * 16 + 16)) - {0}
        paletas = empaquetar(celdas.values(), 15, 8, archivo + ", el fondo")
        for p, paleta in enumerate(paletas):
            for i, color in enumerate(paleta):
                cgram[p * 16 + 1 + i] = color
        pares = {}
        tiles += bytes(64)                    # el par 0, vacío
        pares[None] = 0
        for (cx, cy), conjunto in celdas.items():
            if not conjunto:
                continue
            p = cual_paleta(paletas, conjunto)
            indices = {c: i + 1 for i, c in enumerate(paletas[p])}
            indices[0] = 0
            mitades = []
            for mitad in range(2):
                filas = [[indices[pix[cy * 8 + y][cx * 16 + mitad * 8 + x]]
                          for x in range(8)] for y in range(8)]
                mitades.append(planar(filas, 4))
            clave = (p, mitades[0] + mitades[1])
            if clave not in pares:
                pares[clave] = len(tiles) // 32
                tiles += clave[1]
            mapa[cy * 32 + cx] = pares[clave] | (p << 10)
        # Las caras: paletas de sprites 0 a 6.
        paletas_obj = empaquetar([frozenset(b["colores"]) for b in bandas],
                                 15, PALETA_MARCA, archivo + ", las caras")
        for p, paleta in enumerate(paletas_obj):
            for i, color in enumerate(paleta):
                cgram[128 + p * 16 + 1 + i] = color
        siguiente = 0
        for banda in bandas:
            p = cual_paleta(paletas_obj, frozenset(banda["colores"]))
            indices = {c: i + 1 for i, c in enumerate(paletas_obj[p])}
            xs = [x for x, _ in banda["pixeles"]]
            bx0, bx1 = min(xs), max(xs)
            for ty in range(banda["y0"], banda["y1"] + 1, 8):
                for tx in range(bx0, bx1 + 1, 8):
                    filas = [[indices.get(banda["pixeles"].get((tx + x, ty + y)), 0)
                              for x in range(8)] for y in range(8)]
                    if not any(any(f) for f in filas):
                        continue
                    sprites[siguiente * 32:siguiente * 32 + 32] = planar(filas, 4)
                    oam.append((tx, ty, siguiente, p))
                    siguiente += 1
        if siguiente > TILE_MARCA:
            sys.exit("%s: las caras piden %d tiles de sprite" % (archivo, siguiente))
    else:
        # El menú de hoy, en BG1 de 8 bits: todos los colores en una paleta.
        colores = sorted({c for fila in pix for c in fila} - {0})
        if len(colores) > 127:
            sys.exit("%s: %d colores no entran debajo de los sprites"
                     % (archivo, len(colores)))
        indices = {c: i + 1 for i, c in enumerate(colores)}
        indices[0] = 0
        for i, color in enumerate(colores):
            cgram[1 + i] = color
        vistos = {bytes(64): 0}
        tiles += bytes(64)
        for cy in range(28):
            for cx in range(32):
                filas = [[indices[pix[cy * 8 + y][cx * 8 + x]] for x in range(8)]
                         for y in range(8)]
                tile = planar(filas, 8)
                if tile not in vistos:
                    vistos[tile] = len(tiles) // 64
                    tiles += tile
                mapa[cy * 32 + cx] = vistos[tile]

    if len(tiles) // 2 > VRAM_SPRITES - VRAM_FONDO:
        sys.exit("%s: los tiles del fondo (%d bytes) pisan los de los sprites"
                 % (archivo, len(tiles)))

    # La marca: blanco y negro en la paleta 7, y su sprite primero, que es
    # el de más prioridad. B lo esconde reescribiendo esa entrada.
    cgram[128 + PALETA_MARCA * 16 + 1] = 0x7FFF
    cgram[128 + PALETA_MARCA * 16 + 2] = 0x0000
    sprites[TILE_MARCA * 32:TILE_MARCA * 32 + 32] = tile_marca(marca)
    oam.insert(0, (MARCA_X, MARCA_Y, TILE_MARCA, PALETA_MARCA))
    if len(oam) > 128:
        sys.exit("%s: %d sprites" % (archivo, len(oam)))

    tabla_oam = bytearray()
    for x, y, tile, p in oam:
        # Prioridad 3, arriba del fondo. Con BG1VOFS en -1 (ver `menu.s`),
        # la fila y de la imagen y un sprite con Y = y caen en la misma
        # línea: las dos cosas corren una línea para abajo.
        tabla_oam += bytes([x, y, tile, 0x30 | (p << 1)])
    while len(tabla_oam) < 512:
        tabla_oam += bytes([0, 0xE0, 0, 0])   # abajo de la pantalla
    tabla_oam += bytes(32)                    # la tabla alta: X < 256, 8x8

    return {
        "cgram": b"".join(c.to_bytes(2, "little") for c in cgram),
        "tiles": bytes(tiles),
        "mapa": b"".join(e.to_bytes(2, "little") for e in mapa),
        "oam": bytes(tabla_oam),
        "sprites": bytes(sprites),
        "modo": modo,
    }


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    salida = os.path.abspath(sys.argv[1])
    directorio = os.path.dirname(salida)
    os.makedirs(directorio, exist_ok=True)

    # Cada bloque va a un banco de datos, el primero donde entre; uno de más
    # de 32 KB se parte, porque el DMA no cruza de banco en LoROM.
    libre = [BANCO] * BANCOS
    libre[0] = 0
    segmentos = {b: [] for b in range(1, BANCOS)}
    inc = ["; Generado por `armar.py`: no se edita.", ""]
    trabajos = []
    for n, (archivo, modo, marca) in enumerate(PANTALLAS):
        datos = convertir(archivo, modo, marca)
        lista = []
        for nombre, tipo, destino in (("cgram", 2, 0), ("oam", 3, 0),
                                      ("sprites", 1, VRAM_SPRITES),
                                      ("mapa", 1, VRAM_MAPA),
                                      ("tiles", 1, VRAM_FONDO)):
            contenido = datos[nombre]
            for parte in range(0, len(contenido), BANCO):
                trozo = contenido[parte:parte + BANCO]
                banco = next((b for b in range(1, BANCOS)
                              if libre[b] >= len(trozo)), None)
                if banco is None:
                    sys.exit("no entra: %s de %s" % (nombre, archivo))
                libre[banco] -= len(trozo)
                etiqueta = "p%d_%s_%d" % (n, nombre, parte // BANCO)
                with open(os.path.join(directorio, etiqueta + ".bin"), "wb") as f:
                    f.write(trozo)
                segmentos[banco].append(etiqueta)
                lista.append((tipo, destino + parte // 2, etiqueta, len(trozo)))
        trabajos.append((archivo, datos["modo"], lista))
        print("%s: modo %d, %d bytes de tiles de fondo"
              % (archivo, modo, len(datos["tiles"])))

    for banco, etiquetas in segmentos.items():
        if etiquetas:
            inc.append('.segment "BANCO%d"' % banco)
            for etiqueta in etiquetas:
                inc.append('%s: .incbin "%s.bin"' % (etiqueta, etiqueta))
            inc.append("")
    inc.append('.segment "RODATA"')
    inc.append("; Por pantalla: el BGMODE y la lista de copias por DMA. Cada")
    inc.append("; copia es el tipo (1 VRAM, 2 CGRAM, 3 OAM; 0 termina), el")
    inc.append("; destino, la fuente y el tamaño.")
    inc.append("PANTALLAS = %d" % len(trabajos))
    inc.append("modos: .byte %s" % ", ".join(str(m) for _, m, _ in trabajos))
    inc.append("copias: .word %s" % ", ".join(".loword(copias_%d)" % n for n in range(len(trabajos))))
    for n, (archivo, _, lista) in enumerate(trabajos):
        inc.append("copias_%d:  ; %s" % (n, archivo))
        for tipo, destino, etiqueta, tamano in lista:
            inc.append("    .byte %d\n    .word $%04X\n    .faraddr %s\n    .word %d"
                       % (tipo, destino, etiqueta, tamano))
        inc.append("    .byte 0")
    with open(os.path.join(directorio, "datos.inc"), "w") as f:
        f.write("\n".join(inc) + "\n")

    objeto = os.path.join(directorio, "menu.o")
    subprocess.run(["ca65", "-g", "--cpu", "65816", "-I", directorio,
                    os.path.join(AQUI, "menu.s"), "-o", objeto], check=True)
    subprocess.run(["ld65", "-C", os.path.join(AQUI, "memoria.cfg"), objeto,
                    "-o", salida, "--dbgfile", salida + ".dbg"],
                   check=True, cwd=directorio)

    # La suma del encabezado: los emuladores no la miran, pero los
    # cartuchos flash como el FX Pak sí la muestran. Con la suma en 0 y el
    # complemento en $FFFF, las cuatro suman lo mismo que suman al final.
    with open(salida, "rb") as f:
        rom = bytearray(f.read())
    rom[0x7FDC:0x7FE0] = b"\xff\xff\x00\x00"
    suma = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FDE] = (suma ^ 0xFFFF).to_bytes(2, "little")
    rom[0x7FDE:0x7FE0] = suma.to_bytes(2, "little")
    with open(salida, "wb") as f:
        f.write(rom)
    print("%s (%d bytes, suma $%04X)" % (salida, len(rom), suma))


if __name__ == "__main__":
    main()

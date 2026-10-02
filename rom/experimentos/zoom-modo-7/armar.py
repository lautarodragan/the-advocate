#!/usr/bin/env python3
"""Arma `zoom-modo-7.sfc`: el zoom de una foto *Diff* en modo 7, en loop,
con cuatro variantes que se cambian con el control.

No es el juego y no pasa por el conversor: es un piloto, para que taro vea
en la tele si el zoom del 100 al 0 % de las fotos de los recuerdos de
Memnosyne (mapas 212, 213, 214 y 216) se puede hacer con lo que el modo 7
admite. Lo corre `just zoom-modo-7`, que después lo verifica en los
emuladores con `verificar.py`.

    armar.py <salida.sfc> --game-dir <juego>

**El problema** es que el mapa del modo 7 nombra 256 tiles de 8x8 a 8 bits,
16.384 pixeles, y una foto de 256x224 tiene 57.344: entra una de cada 3,5.
Las variantes son las maneras de repartir eso; qué es cada una, en `zoom.s`
y en `VARIANTES`, abajo.

La foto es PhoneCallDiff, **recortada** a lo que muestra la ROM y no
escalada: ver `RECORTE`.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))

# **Las cuatro fotos**, en el orden de la historia, con el mapa de la escena
# y dónde está el héroe: el `Teleport` que lleva ahí. La primera es la del
# encargo; las otras tres tienen más ruido —896 tiles distintos de 896— y son
# el caso difícil para el modo 7.
FOTOS = [
    ("PhoneCallDiff", 212, (8, 10)),
    ("SurlBroDiff", 213, (6, 10)),
    ("SurlGravesDiff", 214, (8, 9)),
    ("ThreeRubbleDiff", 216, (7, 11)),
]
ANCHO, ALTO = 256, 224
# Los cuatro mapas miden 20x15, la pantalla de RM2k entera.
MAPA = (20 * 16, 15 * 16)


def recorte(heroe):
    """**El recorte**: la foto es una captura de la pantalla de RM2k, de
    320x240, y la ROM muestra 256x224 del mismo mapa. Con el mapa del tamaño
    de la pantalla, la cámara de RM2k está en (0, 0), y la de la ROM centra
    la celda del héroe y no se pasa del borde (`follow_camera`). Lo que la
    ROM mostraba un cuadro antes de la foto es la foto recortada ahí: el "en
    vivo a foto" del original. Supone que el héroe no se movió desde que
    entró, que en los cuatro es así: lo que se mueve son los eventos."""
    hx, hy = heroe
    x = min(max(hx * 16 + 8 - ANCHO // 2, 0), MAPA[0] - ANCHO)
    y = min(max(hy * 16 + 8 - ALTO // 2, 0), MAPA[1] - ALTO)
    return x, y

# La línea de tiempo, en cuadros; la repite `zoom.s`. Medida cuadro a
# cuadro en la grabación del original: la foto aparece debajo de un destello
# blanco que se apaga en 12 cuadros, se queda quieta 93 y se achica del
# 100 al 0 % en 120, en línea recta.
NEGRO_ANTES = 60
DESTELLO = 12
QUIETA = 93
ZOOM = 120
NEGRO_DESPUES = 90

# **La CGRAM en modo 7 es una sola paleta de 256**, y los sprites leen la
# mitad de arriba: la marca de la variante usa la última paleta de sprites,
# así que la foto se queda con 1 a 239. El 0 es transparente: muestra el
# fondo, que es negro.
COLORES_M7 = 239
PALETA_MARCA = 7
CGRAM_MARCA = 128 + PALETA_MARCA * 16

# La VRAM, en palabras. El modo 7 es dueño de `$0000`-`$3FFF` —el mapa de
# 128x128 en los bytes bajos y los 256 tiles en los altos— y no se puede
# mover. La foto del modo 1 va arriba: sus tiles desde `$4000` —los 896 de
# una foto con ruido llegan a `$77FF`— y su tilemap en `$7800`, como en el
# juego pero corridos (ver la tarea). Los cuatro dígitos de la marca son los
# tiles $1C0 a $1C3 de la tabla de sprites que
# empieza en `$7000` —la segunda de la que empieza en `$6000`—: de `$7C00`
# a `$7C3F`, arriba del tilemap de la foto.
VRAM_M1_TILES = 0x4000
VRAM_M1_MAPA = 0x7800
VRAM_SPRITES = 0x6000
TILE_MARCA = 0x1C0
M1_TILES_MAX = (VRAM_M1_MAPA - VRAM_M1_TILES) // 16

# Las paletas del modo 1: las siete de arriba de la 0, como `BIG_PALETTES`
# en el juego, que deja la 0 para la ventana de mensajes.
M1_PALETAS = 7

# Cuánto se sube por vblank cuando la foto ya está en pantalla. Un vblank
# NTSC son 37 líneas de 1.364 ciclos maestros, unos 50.000, y el DMA gasta 8
# por byte: entran ~6 KB. 4 KB deja lugar a lo demás del vblank.
POR_VBLANK = 4096

# **Las variantes**, en el orden en que las muestra la ROM: qué se ve
# mientras la foto está quieta y con qué textura se hace el zoom.
#
# * `quieta`: 7 es la misma textura del zoom, a escala 1; 1 es la foto
#   entera en modo 1, a 4 bits por pixel y siete paletas, como la muestra
#   hoy el juego, y el cambio a modo 7 es al empezar el zoom.
# * `textura`: "media" es la foto a 128x112, promediando de a 2x2, en 224
#   tiles; "vq" es la foto a resolución completa con sólo 255 tiles
#   distintos, elegidos por cuantización vectorial (k-medias sobre los 896
#   tiles de la foto): cada lugar de la foto muestra el más parecido.
VARIANTES = [
    {"nombre": "media", "quieta": 7, "textura": "media"},
    {"nombre": "hibrida-media", "quieta": 1, "textura": "media"},
    {"nombre": "vq", "quieta": 7, "textura": "vq"},
    {"nombre": "hibrida-vq", "quieta": 1, "textura": "vq"},
]

BANCO = 0x8000
BANCOS_MINIMO = 4

# Los dígitos de la marca, 5x7, como en `menu-modo-5/`.
DIGITOS = {
    1: ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    2: [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    3: [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
    4: ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
}
MARCA_X, MARCA_Y = 8, 206


def a15(rgb):
    """Un color [r, g, b] de 8 bits como lo guarda la CGRAM."""
    r, g, b = (int(c) >> 3 for c in rgb[:3])
    return r | (g << 5) | (b << 10)


def de15(c):
    return ((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3)


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


def la_foto(game_dir, nombre, heroe):
    ruta = os.path.join(game_dir, "Picture", nombre + ".png")
    imagen = Image.open(ruta).convert("RGB")
    if imagen.size != (320, 240):
        sys.exit("%s: %dx%d, y se esperaba una captura de 320x240" % ((ruta,) + imagen.size))
    x, y = recorte(heroe)
    foto = np.asarray(imagen.crop((x, y, x + ANCHO, y + ALTO))).astype(np.int64)
    # A 15 bits, que es lo que la consola puede mostrar.
    return (foto >> 3) << 3


# --- las texturas del modo 7 -------------------------------------------------

def cuantizar(pixeles, cuantos):
    """Los colores de una imagen RGB (alto, ancho, 3) a lo sumo `cuantos`, a
    15 bits. Devuelve los índices (desde 1) y la lista de colores."""
    plano = pixeles.reshape(-1, 3)
    colores, inversa = np.unique((plano >> 3) << 3, axis=0, return_inverse=True)
    if len(colores) > cuantos:
        imagen = Image.fromarray(pixeles.astype(np.uint8))
        reducida = imagen.quantize(cuantos, method=Image.Quantize.MEDIANCUT,
                                   dither=Image.Dither.NONE).convert("RGB")
        plano = (np.asarray(reducida).reshape(-1, 3).astype(np.int64) >> 3) << 3
        colores, inversa = np.unique(plano, axis=0, return_inverse=True)
    indices = inversa.reshape(pixeles.shape[:2]) + 1
    return indices, [tuple(int(v) for v in c) for c in colores]


def kmedias(x, k, vueltas=40, semilla=1):
    """k-medias con k-means++, determinístico. Devuelve los centros y a qué
    centro va cada fila de `x`."""
    rng = np.random.default_rng(semilla)
    unicos = np.unique(x, axis=0)
    if len(unicos) <= k:
        centros = unicos.astype(float)
    else:
        centros = [unicos[rng.integers(len(unicos))]]
        d = ((unicos - centros[0]) ** 2).sum(1).astype(float)
        for _ in range(k - 1):
            i = rng.choice(len(unicos), p=d / d.sum())
            centros.append(unicos[i])
            d = np.minimum(d, ((unicos - unicos[i]) ** 2).sum(1))
        centros = np.array(centros, dtype=float)
    x = x.astype(float)
    for _ in range(vueltas):
        dist = (x ** 2).sum(1)[:, None] - 2 * x @ centros.T + (centros ** 2).sum(1)[None]
        cual = dist.argmin(1)
        for j in range(len(centros)):
            miembros = x[cual == j]
            if len(miembros):
                centros[j] = miembros.mean(0)
    dist = (x ** 2).sum(1)[:, None] - 2 * x @ centros.T + (centros ** 2).sum(1)[None]
    return centros, dist.argmin(1)


def textura_media(foto):
    """La foto a 128x112, promediando de a 2x2: 16x14 tiles."""
    media = foto.reshape(ALTO // 2, 2, ANCHO // 2, 2, 3).mean((1, 3)).round().astype(np.int64)
    indices, colores = cuantizar(media, COLORES_M7)
    return indices, colores


def textura_vq(foto):
    """La foto entera, con 255 tiles distintos: los 896 se agrupan en 255 y
    cada lugar muestra el representante de su grupo.

    **Se agrupan por la forma, no por el pixel**: la distancia entre dos
    tiles se mide con cada uno promediado de a 2x2, porque en las fotos con
    ruido —el pasto, la tierra— la distancia pixel a pixel la decide el ruido
    y k-medias junta un pedazo de árbol con pasto. Y **el representante es
    un tile de la foto** —el más cercano a los demás del grupo—, no el
    promedio: el promedio de tiles con ruido es un tile liso y de colores que
    la foto no tiene, y se ve como manchas. Medido en las cuatro fotos: el
    promedio da 1 a 3 dB más contra la foto, y a la vista es peor."""
    indices, colores = cuantizar(foto, COLORES_M7)
    def en_tiles(a, canales):
        return a.reshape(ALTO // 8, 8, ANCHO // 8, 8, canales).transpose(0, 2, 1, 3, 4) \
            .reshape(-1, 64 * canales)
    tiles = en_tiles(indices[..., None], 1)
    forma = en_tiles(foto, 3).reshape(-1, 4, 2, 4, 2, 3).mean((2, 4)).reshape(-1, 48)
    _, cual = kmedias(forma, 255)
    representante = {}
    for grupo in np.unique(cual):
        miembros = np.nonzero(cual == grupo)[0]
        f = forma[miembros]
        lejos = ((f[:, None] - f[None]) ** 2).sum(2).sum(1)
        representante[grupo] = tiles[miembros[lejos.argmin()]]
    salida = np.array([representante[g] for g in cual])
    salida = salida.reshape(ALTO // 8, ANCHO // 8, 8, 8).transpose(0, 2, 1, 3)
    return salida.reshape(ALTO, ANCHO), colores


class TilesDeMas(Exception):
    pass


def modo7(indices, colores):
    """Los índices de una textura a lo que lee el modo 7: los tiles en
    bytes, uno por pixel, con el 0 vacío, y las filas del mapa de 128
    entradas que la foto ocupa. Tiles iguales se comparten."""
    alto, ancho = indices.shape
    vistos = {bytes(64): 0}
    tiles = bytearray(bytes(64))
    filas = bytearray()
    for ty in range(alto // 8):
        fila = bytearray(128)
        for tx in range(ancho // 8):
            tile = bytes(int(v) for v in indices[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8].ravel())
            if tile not in vistos:
                if len(vistos) == 256:
                    raise TilesDeMas("la textura pide más de los 256 tiles que nombra el modo 7")
                vistos[tile] = len(vistos)
                tiles += tile
            fila[tx] = vistos[tile]
        filas += fila
    cgram = [0] * 256
    for i, c in enumerate(colores):
        cgram[1 + i] = a15(c)
    marca(cgram)
    return {"tiles": bytes(tiles), "filas": bytes(filas), "cgram": cgram,
            "cuantos": len(vistos), "ancho": ancho, "alto": alto,
            "imagen": np.array([[de15(cgram[v]) for v in fila] for fila in indices])}


def marca(cgram):
    cgram[CGRAM_MARCA + 1] = 0x7FFF
    cgram[CGRAM_MARCA + 2] = 0x0000


# --- la foto en modo 1 ---------------------------------------------------------

def modo1(foto, temporal):
    """La foto entera a 4 bits: Adeleine decide qué colores se pierden y
    cómo se agrupan en siete paletas, y Voodoo corta los tiles. Es lo que
    hace el conversor con las imágenes grandes del juego."""
    colores, cuentas = np.unique(foto.reshape(-1, 3), axis=0, return_counts=True)
    por_tile = set()
    for y in range(0, ALTO, 8):
        for x in range(0, ANCHO, 8):
            por_tile.add(tuple(sorted({tuple(int(v) for v in p)
                                       for p in foto[y:y + 8, x:x + 8].reshape(-1, 3)})))
    pedido = {"counts": [[int(r), int(g), int(b), int(n)] for (r, g, b), n in zip(colores, cuentas)],
              "tiles": [[list(c) for c in t] for t in sorted(por_tile)],
              "palettes": M1_PALETAS}
    ruta_pedido = os.path.join(temporal, "pedido.json")
    with open(ruta_pedido, "w") as f:
        json.dump(pedido, f)
    subprocess.run(["adeleine", "reduce", "--request", ruta_pedido, "--out", temporal], check=True)
    with open(os.path.join(temporal, "reduce.json")) as f:
        respuesta = json.load(f)
    a_donde = {tuple(int(v) for v in c): tuple(m) for c, m in zip(colores, respuesta["mapping"])}
    paletas = [[tuple(c) for c in p] for p in respuesta["palettes"]]

    indices = np.zeros((ALTO, ANCHO), dtype=np.uint8)
    for y in range(0, ALTO, 8):
        for x in range(0, ANCHO, 8):
            celda = [[a_donde[tuple(int(v) for v in foto[y + j, x + i])] for i in range(8)]
                     for j in range(8)]
            usados = {c for fila in celda for c in fila}
            p = next(n for n, paleta in enumerate(paletas) if usados <= set(paleta))
            for j in range(8):
                for i in range(8):
                    indices[y + j, x + i] = (p + 1) * 16 + 1 + paletas[p].index(celda[j][i])
    paleta_png = [0] * 768
    for p, paleta in enumerate(paletas):
        for i, c in enumerate(paleta):
            n = (p + 1) * 16 + 1 + i
            paleta_png[n * 3:n * 3 + 3] = c
    png = Image.fromarray(indices, "P")
    png.putpalette(paleta_png)
    ruta_png = os.path.join(temporal, "modo1.png")
    png.save(ruta_png)
    salidas = {k: os.path.join(temporal, "modo1." + k) for k in ("tiles", "cgram", "mapa")}
    subprocess.run(["voodoo", "convert", ruta_png, "--bpp", "4",
                    "--max-tiles", str(M1_TILES_MAX), "--no-blank-tile",
                    "--output", salidas["tiles"],
                    "--palette", salidas["cgram"], "--tilemap", salidas["mapa"]],
                   check=True, stdout=subprocess.DEVNULL)
    leer = lambda k: open(salidas[k], "rb").read()  # noqa: E731
    cgram_bytes = leer("cgram")
    cgram = [int.from_bytes(cgram_bytes[i:i + 2], "little") for i in range(0, 512, 2)]
    marca(cgram)
    mapa = leer("mapa")
    mapa += bytes(2 * 32 * 32 - len(mapa))
    tiles = leer("tiles")
    rgb = np.array([[de15(a15(paleta_png[int(v) * 3:int(v) * 3 + 3])) for v in fila]
                    for fila in indices])
    return {"tiles": tiles, "mapa": mapa, "cgram": cgram, "cuantos": len(tiles) // 32,
            "imagen": rgb}


# --- la escala ---------------------------------------------------------------

def escala(t):
    """El tamaño de la foto en el cuadro t del zoom, de 1 a 0."""
    return 1 - t / ZOOM


def matriz(textura, t):
    """A y D del modo 7 en el cuadro t: cuántos texels por pixel de
    pantalla, en 8.8. En el último cuadro la foto no se ve y la capa se
    apaga: el valor no importa."""
    s = escala(t)
    if s <= 0:
        return 0, 0
    a = round(256 * textura["ancho"] / (ANCHO * s))
    d = round(256 * textura["alto"] / (ALTO * s))
    assert a <= 0x7FFF and d <= 0x7FFF, (t, a, d)
    return a, d


def tile_marca(digito):
    tinta = {(x + 1, y) for y, fila in enumerate(DIGITOS[digito])
             for x, c in enumerate(fila) if c == "#"}
    filas = []
    for y in range(8):
        fila = []
        for x in range(8):
            if (x, y) in tinta:
                fila.append(1)
            elif any((x + dx, y + dy) in tinta for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                fila.append(2)
            else:
                fila.append(0)
        filas.append(fila)
    return planar(filas, 4)


# --- el armado -----------------------------------------------------------------

class Bancos:
    """Reparte los bloques en bancos de datos, el primero donde entren."""

    def __init__(self, directorio):
        self.directorio = directorio
        self.libre = [0]
        self.segmentos = {}
        self.etiquetas = {}

    def poner(self, etiqueta, contenido):
        assert len(contenido) <= BANCO
        if etiqueta in self.etiquetas:
            return
        banco = next((b for b in range(1, len(self.libre)) if self.libre[b] >= len(contenido)), None)
        if banco is None:
            self.libre.append(BANCO)
            banco = len(self.libre) - 1
            self.segmentos[banco] = []
        self.libre[banco] -= len(contenido)
        with open(os.path.join(self.directorio, etiqueta + ".bin"), "wb") as f:
            f.write(contenido)
        self.segmentos[banco].append(etiqueta)
        self.etiquetas[etiqueta] = banco


# Los tipos de copia; los repite `zoom.s`.
COPIA_BAJOS = 1     # VRAM, sólo los bytes bajos: el mapa del modo 7
COPIA_ALTOS = 2     # VRAM, sólo los altos: los tiles del modo 7
COPIA_PALABRAS = 3  # VRAM de a palabras
COPIA_CGRAM = 4
COPIA_CEROS = 5     # VRAM, bytes bajos, todos en 0: el resto del mapa del modo 7


def copias_modo7(nombre, textura, bancos):
    """La lista de copias que pone una textura en la VRAM del modo 7, en
    trozos de a lo sumo `POR_VBLANK`: sus filas del mapa, el resto del mapa
    en cero —con la foto chica la pantalla ve el plano entero, y lo que no
    es foto tiene que ser el tile vacío— y los tiles."""
    copias = []
    filas = textura["filas"]
    bancos.poner(nombre + "_filas", filas)
    for parte in range(0, len(filas), POR_VBLANK):
        copias.append((COPIA_BAJOS, parte, nombre + "_filas", parte,
                       min(POR_VBLANK, len(filas) - parte)))
    for parte in range(len(filas), 128 * 128, POR_VBLANK):
        copias.append((COPIA_CEROS, parte, "cero", 0, min(POR_VBLANK, 128 * 128 - parte)))
    tiles = textura["tiles"]
    bancos.poner(nombre + "_tiles", tiles)
    for parte in range(0, len(tiles), POR_VBLANK):
        copias.append((COPIA_ALTOS, parte, nombre + "_tiles", parte,
                       min(POR_VBLANK, len(tiles) - parte)))
    return copias


def cgram_bytes(cgram):
    return b"".join(c.to_bytes(2, "little") for c in cgram)


def destello(foto):
    """Cuánto blanco se suma en cada cuadro del destello, de 0 a 31.

    RM2k **mezcla** hacia el blanco —el color más (blanco − color) por la
    fuerza, que baja en línea recta— y la consola sólo puede **sumar** un
    color fijo, que satura. Arrancan y terminan igual; en el medio, sumar lo
    mismo daría la foto más clara que la de RM2k. Así que se elige, cuadro a
    cuadro, lo que deja el brillo medio de esta foto donde lo deja RM2k."""
    c = foto.astype(float)
    tabla = []
    for k in range(DESTELLO):
        fuerza = (DESTELLO - k) / DESTELLO
        meta = (c + (248 - c) * fuerza).mean()
        tabla.append(min(range(32), key=lambda v: abs(np.minimum(c + 8 * v, 248).mean() - meta)))
    return tabla


def main():
    argumentos = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    argumentos.add_argument("salida")
    argumentos.add_argument("--game-dir", required=True)
    args = argumentos.parse_args()
    salida = os.path.abspath(args.salida)
    directorio = os.path.dirname(salida)
    os.makedirs(directorio, exist_ok=True)

    bancos = Bancos(directorio)
    bancos.poner("cero", bytes(1))
    # Con lo que se ensucia la VRAM del modo 7 antes de subir la textura en
    # las híbridas: si la subida no llegara entera, se vería.
    bancos.poner("basura", bytes([0x55]))
    bancos.poner("sprite_marcas", b"".join(tile_marca(n) for n in sorted(DIGITOS)))

    inc = ["; Generado por `armar.py`: no se edita.", ""]
    for nombre, valor in (("NEGRO_ANTES", NEGRO_ANTES), ("DESTELLO", DESTELLO),
                          ("QUIETA", QUIETA), ("ZOOM", ZOOM),
                          ("NEGRO_DESPUES", NEGRO_DESPUES),
                          ("VARIANTES", len(VARIANTES)), ("FOTOS", len(FOTOS)),
                          ("VRAM_M1_TILES", VRAM_M1_TILES), ("VRAM_M1_MAPA", VRAM_M1_MAPA),
                          ("VRAM_SPRITES", VRAM_SPRITES), ("TILE_MARCA", TILE_MARCA),
                          ("MARCA_X", MARCA_X), ("MARCA_Y", MARCA_Y),
                          ("PALETA_MARCA", PALETA_MARCA)):
        inc.append("%s = %d" % (nombre, valor))
    inc.append("")
    inc.append('.segment "RODATA"')

    def lista(etiqueta, copias):
        inc.append("%s:" % etiqueta)
        for tipo, destino, fuente, desde, tamano in copias:
            inc.append("    .byte %d\n    .word $%04X\n    .faraddr %s + %d\n    .word %d"
                       % (tipo, destino, fuente, desde, tamano))
        inc.append("    .byte 0")

    lista("comun", [(COPIA_PALABRAS, VRAM_SPRITES + TILE_MARCA * 16,
                     "sprite_marcas", 0, len(DIGITOS) * 32)])

    # Por foto y variante, en ese orden: la lista que sube la textura del
    # modo 7, su paleta, las tablas de la matriz, el centro de la textura,
    # si la foto quieta va en modo 1, y la foto del modo 1 con su paleta.
    tablas = {c: [] for c in ("copias", "cgram", "matriz_a", "matriz_d", "centro_x",
                              "centro_y", "hibrida", "modo1", "cgram_m1", "destello")}
    resumen = {"variantes": VARIANTES, "fotos": [],
               "linea": {"negro_antes": NEGRO_ANTES, "destello": DESTELLO,
                         "quieta": QUIETA, "zoom": ZOOM, "negro_despues": NEGRO_DESPUES}}
    for f, (nombre_foto, mapa, heroe) in enumerate(FOTOS):
        foto = la_foto(args.game_dir, nombre_foto, heroe)
        texturas = {"media": modo7(*textura_media(foto)), "vq": modo7(*textura_vq(foto))}
        with tempfile.TemporaryDirectory() as temporal:
            m1 = modo1(foto, temporal)
        p = "f%d_" % f
        bancos.poner(p + "m1_tiles", m1["tiles"])
        bancos.poner(p + "m1_mapa", m1["mapa"])
        bancos.poner(p + "m1_cgram", cgram_bytes(m1["cgram"]))
        lista(p + "modo1", [(COPIA_PALABRAS, VRAM_M1_TILES, p + "m1_tiles", 0, len(m1["tiles"])),
                            (COPIA_PALABRAS, VRAM_M1_MAPA, p + "m1_mapa", 0, len(m1["mapa"]))])
        lista(p + "cgram_m1", [(COPIA_CGRAM, 0, p + "m1_cgram", 0, 512)])
        inc.append("%sdestello: .byte %s" % (p, ", ".join(str(v) for v in destello(foto))))
        print("%s (mapa %d, recorte %s): modo 1 en %d tiles de 4 bits, %d bytes"
              % (nombre_foto, mapa, recorte(heroe), m1["cuantos"], len(m1["tiles"])))
        for n, textura in texturas.items():
            bancos.poner(p + n + "_cgram", cgram_bytes(textura["cgram"]))
            copias = copias_modo7(p + n, textura, bancos)
            lista(p + "m7_" + n, copias)
            lista(p + "cgram_" + n, [(COPIA_CGRAM, 0, p + n + "_cgram", 0, 512)])
            a, d = zip(*(matriz(textura, t) for t in range(ZOOM + 1)))
            inc.append("%smatriz_a_%s: .word %s" % (p, n, ", ".join("$%04X" % v for v in a)))
            inc.append("%smatriz_d_%s: .word %s" % (p, n, ", ".join("$%04X" % v for v in d)))
            print("    textura %s: %dx%d, %d tiles con el vacío, %d copias de hasta %d bytes"
                  % (n, textura["ancho"], textura["alto"], textura["cuantos"], len(copias),
                     POR_VBLANK))
        for v in VARIANTES:
            t = v["textura"]
            tablas["copias"].append(".loword(%sm7_%s)" % (p, t))
            tablas["cgram"].append(".loword(%scgram_%s)" % (p, t))
            tablas["matriz_a"].append(".loword(%smatriz_a_%s)" % (p, t))
            tablas["matriz_d"].append(".loword(%smatriz_d_%s)" % (p, t))
            tablas["centro_x"].append(str(texturas[t]["ancho"] // 2))
            tablas["centro_y"].append(str(texturas[t]["alto"] // 2))
            tablas["hibrida"].append("1" if v["quieta"] == 1 else "0")
            tablas["modo1"].append(".loword(%smodo1)" % p)
            tablas["cgram_m1"].append(".loword(%scgram_m1)" % p)
            tablas["destello"].append(".loword(%sdestello)" % p)
        # Lo que `verificar.py` compara: cómo se tiene que ver la foto quieta
        # en cada variante, a 15 bits.
        for n, cosa in list(texturas.items()) + [("modo1", m1)]:
            Image.fromarray(cosa["imagen"].astype(np.uint8)).save(
                os.path.join(directorio, "esperada-%d-%s.png" % (f, n)))
        Image.fromarray(foto.astype(np.uint8)).save(
            os.path.join(directorio, "esperada-%d-foto.png" % f))
        resumen["fotos"].append({
            "nombre": nombre_foto, "mapa": mapa, "recorte": recorte(heroe),
            "modo1_tiles": m1["cuantos"],
            "texturas": {n: {"ancho": t["ancho"], "alto": t["alto"], "tiles": t["cuantos"]}
                         for n, t in texturas.items()}})

    for campo, valores in tablas.items():
        inc.append("v_%s: .word %s" % (campo, ", ".join(valores)))
    for banco, etiquetas in bancos.segmentos.items():
        inc.append('.segment "BANCO%d"' % banco)
        for etiqueta in etiquetas:
            inc.append('%s: .incbin "%s.bin"' % (etiqueta, etiqueta))
    with open(os.path.join(directorio, "datos.inc"), "w") as f:
        f.write("\n".join(inc) + "\n")
    with open(salida + ".variantes", "w") as f:
        json.dump(resumen, f, indent=1)

    bancos_rom = BANCOS_MINIMO
    while bancos_rom < len(bancos.libre):
        bancos_rom *= 2
    with open(os.path.join(AQUI, "memoria.cfg")) as f:
        cfg = f.read()
    memoria = "".join(
        "    ROM%d:   start = $%02X8000, size = $8000, fill = yes, fillval = $FF;\n"
        % (b, 0x80 + b) for b in range(bancos_rom))
    segs = "".join("    BANCO%d:   load = ROM%d, type = ro, optional = yes;\n" % (b, b)
                   for b in range(1, bancos_rom))
    cfg = re.sub(r"(?m)^    ROM\d+:.*\n", "", cfg)
    cfg = re.sub(r"(?m)^    BANCO\d+:.*\n", "", cfg)
    cfg = re.sub(r"(    ZP: [^\n]*\n)", lambda m: m.group(1) + memoria, cfg, count=1)
    cfg = re.sub(r"(    VECTORS: [^\n]*\n)", lambda m: m.group(1) + segs, cfg, count=1)
    ruta_cfg = os.path.join(directorio, "memoria.cfg")
    with open(ruta_cfg, "w") as f:
        f.write(cfg)

    objeto = os.path.join(directorio, "zoom.o")
    tamano = (bancos_rom * 32).bit_length() - 1
    subprocess.run(["ca65", "-g", "--cpu", "65816", "-I", directorio,
                    "-D", "TAMANO_ROM=%d" % tamano,
                    os.path.join(AQUI, "zoom.s"), "-o", objeto], check=True)
    subprocess.run(["ld65", "-C", ruta_cfg, objeto, "-o", salida, "--dbgfile", salida + ".dbg"],
                   check=True, cwd=directorio)

    # La suma del encabezado, como en `menu-modo-5/armar.py`.
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

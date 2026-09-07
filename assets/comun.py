"""Lo que comparten las mediciones de arte: leer el material y contarlo bien.

Dos cosas que este módulo existe para no volver a equivocarse:

**La unidad es el tile de 8x8, no el archivo ni el pixel.** Los KB de un PNG no
dicen nada —son truecolor y comprimidos— y contar pixeles engaña al revés: a un
tile al que le falta un solo color no se le dibuja peor, se le dibuja **roto**.
Todo lo que se mide acá se mide en tiles de 8x8 a 4 bits, que es lo que ocupa
en el cartucho.

**Se cuenta lo que el juego usa, no lo que hay en la carpeta.** Los juegos de
RM2k arrastran material que nadie referencia: de los 456 personajes de los
CharSets, el juego usa 161. Medir sobre los archivos da números que no
significan nada.

Las dos maneras de deduplicar que la consola regala, y por eso se usan siempre:

* **espejado**: el bit de espejo horizontal está en el tilemap y en el OAM, así
  que un tile y su reflejo son el mismo tile.
* **forma**: el número de paleta también es un campo, así que dos gráficos con
  el mismo dibujo y distintos colores son los mismos tiles. Un recoloreado no
  cuesta un byte de gráfico.
"""

import collections
import glob
import hashlib
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

JUEGO = os.environ.get("GAME_DIR", "/extras/abl-rm")
RTP = os.environ.get("RTP_DIR", "/extras/rtp")

# Un tile de 8x8 a 4 bits: 32 bytes en el cartucho.
BYTES_POR_TILE = 32

# Un personaje de RM2k son 12 fotogramas de 24x32 —tres poses por cuatro
# direcciones— en una grilla de 4x2 personajes por archivo.
SPRITE_W, SPRITE_H = 24, 32


def ruta_de(carpeta, nombre):
    """El archivo del juego, o el del RTP si el juego no lo trae."""
    for base in (JUEGO, RTP):
        for ext in (".png", ".PNG", ".bmp", ".BMP"):
            camino = os.path.join(base, carpeta, nombre + ext)
            if os.path.exists(camino):
                return camino
    return None


def abrir(ruta):
    """La imagen en RGBA, con el índice 0 de RM2k ya en transparente.

    PIL no lo sabe: un PNG en modo P sin `transparency` se convierte con alfa
    255 en todas partes, y entonces el color de fondo entra en el dibujo. Eso
    rompe la deduplicación justo donde más rinde —dos personajes iguales sobre
    fondos de distinto color dejan de parecerse— y era lo que taro veía en
    `YoungAgents`.
    """
    from PIL import Image
    base = Image.open(ruta)
    if base.mode != "P":
        return base.convert("RGBA")
    paleta = base.getpalette() or []
    fondo = tuple(paleta[0:3]) if len(paleta) >= 3 else None
    salida = base.convert("RGBA")
    if fondo is None:
        return salida
    pixeles = salida.load()
    indices = base.load()
    for y in range(base.height):
        for x in range(base.width):
            if indices[x, y] == 0:
                pixeles[x, y] = (0, 0, 0, 0)
    return salida


def mapas():
    """Todos los mapas del juego, ya leídos. Los que no abren se saltean."""
    import lcf
    for archivo in sorted(glob.glob(os.path.join(JUEGO, "Map*.lmu"))):
        try:
            yield int(os.path.basename(archivo)[3:7]), lcf.Map(archivo)
        except Exception:
            continue


def canonico(pixeles):
    """La forma de un dibujo, sin depender de la paleta.

    Cada color se numera por el orden en que aparece, así que dos dibujos
    iguales con paletas distintas dan lo mismo. Es lo que hace que un
    recoloreado no cueste: el número de paleta es un campo aparte.

    Trabaja sobre **píxeles**, no sobre bytes. Renumerar bytes de un RGB no es
    lo mismo y además puede juntar dibujos distintos: fue un error de la
    primera versión de este módulo.
    """
    mapa, salida, siguiente = {}, bytearray(), 0
    for pixel in pixeles:
        if pixel not in mapa:
            mapa[pixel] = siguiente
            siguiente += 1
        salida.append(mapa[pixel])
    return bytes(salida)


def huella(filas):
    """La huella de un dibujo, la misma para él y para su reflejo horizontal.

    `filas` son las filas de píxeles, cada uno cualquier valor hasheable.
    """
    derecho = canonico(p for fila in filas for p in fila)
    espejo = canonico(p for fila in filas for p in reversed(fila))
    return min(hashlib.sha256(derecho).digest(),
               hashlib.sha256(espejo).digest())


def transparente(pixel):
    """En RGBA, alfa cero. En los CharSets de RM2k lo pone el índice 0."""
    return len(pixel) > 3 and not pixel[3]


def tiles_de_imagen(imagen, ox=0, oy=0, w=None, h=None):
    """Las huellas de los tiles de 8x8 de una región de una imagen."""
    px = imagen.convert("RGBA")
    w = w if w is not None else px.width
    h = h if h is not None else px.height
    for ty in range(h // 8):
        for tx in range(w // 8):
            filas = [[px.getpixel((ox + tx * 8 + x, oy + ty * 8 + y))
                      for x in range(8)] for y in range(8)]
            yield huella(filas)


def ids_por_chipset():
    """Qué ids de tile usa cada chipset, mirando todos los mapas.

    Se agrupa **por chipset y no por mapa**: un id que aparece en treinta mapas
    es un solo tile en el cartucho. Sumar por mapa daba 20.753 en vez de 6916.
    """
    usados = collections.defaultdict(set)
    cuantos_mapas = collections.Counter()
    for _, game_map in mapas():
        usados[game_map.chipset_id].update(game_map.lower_layer)
        usados[game_map.chipset_id].update(game_map.upper_layer)
        cuantos_mapas[game_map.chipset_id] += 1
    return usados, cuantos_mapas


def nombres_de_chipset():
    with open(os.path.join(RAIZ, "data", "db", "chipsets.json")) as archivo:
        return {c["id"]: (c.get("chipset_name") or "").strip()
                for c in json.load(archivo)}


def personajes_usados():
    """Los (CharSet, índice) que el juego usa, con cuántas poses hace falta.

    `animation_type` 4 y 5 son fijas —una sola imagen— y 2 y 3 giran sin animar
    —una por dirección—. El resto necesita las doce.
    """
    FIJAS, SIN_PASO = {4, 5}, {2, 3}
    necesita = {}
    for _, game_map in mapas():
        for evento in game_map.events:
            for pagina in evento.pages:
                nombre = (getattr(pagina, "character_name", "") or "").strip()
                if not nombre:
                    continue
                anim = getattr(pagina, "animation_type", 0)
                ruta = getattr(pagina, "move_route", None)
                camina = bool(ruta and getattr(ruta, "move_commands", None))
                cuantas = (1 if (anim in FIJAS
                                 and getattr(pagina, "move_type", 0) == 0
                                 and not camina)
                           else 4 if anim in SIN_PASO else 12)
                clave = (nombre.lower(), pagina.character_index)
                necesita[clave] = max(necesita.get(clave, 0), cuantas)
    return necesita


def kb(cosas, tiles_por_cosa=1):
    """KB en el cartucho. `tiles_por_cosa` es cuántos 8x8 ocupa cada una: un
    fotograma de 24x32 son doce."""
    return len(cosas) * tiles_por_cosa * BYTES_POR_TILE / 1024.0

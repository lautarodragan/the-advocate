#!/usr/bin/env python3
"""Cuánto ocuparía en el cartucho el arte del juego, por rubro.

    python3 assets/medir.py sprites     los CharSets, por fotograma
    python3 assets/medir.py fondos      los ChipSets, sólo lo que se usa
    python3 assets/medir.py colores     si alcanza una paleta por chipset
    python3 assets/medir.py resto       backdrops, imágenes, panoramas
    python3 assets/medir.py todo

Los números que salen de acá son los que están en `assets/README.md`, y son los
que dictan la estrategia. Si alguno cambia, ese README miente.

Cada medición tarda entre unos segundos y unos minutos: expandir los ChipSets a
su atlas no es barato.
"""

import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image                                       # noqa: E402

import comun                                                # noqa: E402


def sprites():
    """Los CharSets: cuántos fotogramas distintos necesita el juego."""
    necesita = comun.personajes_usados()
    archivos = {}
    for base in (comun.JUEGO, comun.RTP):
        for x in glob.glob(os.path.join(base, "CharSet", "*")):
            archivos.setdefault(
                os.path.splitext(os.path.basename(x))[0].lower(), x)

    formas, pedidos, vacios, faltan = set(), 0, 0, set()
    for (nombre, indice), cuantas in sorted(necesita.items()):
        ruta = archivos.get(nombre)
        if not ruta:
            faltan.add(nombre)
            continue
        imagen = comun.abrir(ruta)
        bx = (indice % 4) * comun.SPRITE_W * 3
        by = (indice // 4) * comun.SPRITE_H * 4
        for pose in range(12):
            if cuantas == 1 and pose != 1:
                continue
            if cuantas == 4 and pose % 3 != 1:
                continue
            ox = bx + (pose % 3) * comun.SPRITE_W
            oy = by + (pose // 3) * comun.SPRITE_H
            pedidos += 1
            filas = [[imagen.getpixel((ox + x, oy + y))
                      for x in range(comun.SPRITE_W)]
                     for y in range(comun.SPRITE_H)]
            if all(comun.transparente(p) for fila in filas for p in fila):
                vacios += 1
                continue
            formas.add(comun.huella(filas))

    total_archivos = sum(
        1 for base in (comun.JUEGO, comun.RTP)
        for _ in glob.glob(os.path.join(base, "CharSet", "*"))) * 96
    print("CharSets")
    print("  personajes que el juego usa:   %4d de 456" % len(necesita))
    print("  fotogramas en los archivos:    %4d" % total_archivos)
    print("  fotogramas que el juego pide:  %4d  (%d vacíos)" % (pedidos, vacios))
    print("  formas distintas:              %4d" % len(formas))
    # Un fotograma de 24x32 son 3x4 tiles de 8x8. No se deduplica más fino
    # porque el OBJ de la consola compone el sprite con tiles **contiguos**:
    # compartir un 8x8 suelto entre dos sprites distintos no se puede.
    print("  en la ROM:                   %6.0f KB" % comun.kb(formas, 12))
    if faltan:
        print("  CharSets que no se encontraron: %s" % sorted(faltan)[:5])
    return comun.kb(formas)


def _atlas_por_chipset():
    import chipset as chipmod
    nombres = comun.nombres_de_chipset()
    usados, cuantos = comun.ids_por_chipset()
    for cid, ids in sorted(usados.items()):
        ruta = comun.ruta_de("ChipSet", nombres.get(cid, ""))
        if not ruta:
            continue
        yield (cid, nombres[cid], cuantos[cid], sorted(ids),
               chipmod.ChipsetAtlas(Image.open(ruta)))


def fondos():
    """Los ChipSets, expandiendo sólo los ids que los mapas usan.

    Un id de autotile no es una celda de la imagen sino una **combinación** que
    el motor compone de un bloque chico; por eso las combinaciones comparten
    casi todo, y por eso los 6916 ids no son 27.664 tiles sino 10.251.
    """
    todos, suma_propios, por_clase = set(), 0, collections.Counter()
    ids_clase = collections.Counter()
    lienzo = Image.new("RGBA", (16, 16))
    tiles_clase = collections.defaultdict(set)
    for cid, nombre, mapas_, ids, atlas in _atlas_por_chipset():
        propios = set()
        for tid in ids:
            clase = ("autotile" if tid < 5000
                     else "capa baja" if tid < 10000 else "capa alta")
            ids_clase[clase] += 1
            lienzo.paste((0, 0, 0, 0), (0, 0, 16, 16))
            atlas.render_tile(lienzo, 0, 0, tid)
            for h in comun.tiles_de_imagen(lienzo):
                propios.add(h)
                todos.add(h)
                tiles_clase[clase].add(h)
        suma_propios += len(propios)
    print("ChipSets")
    print("  ids de tile que los mapas usan:      %5d" % sum(ids_clase.values()))
    for clase in ("autotile", "capa baja", "capa alta"):
        print("     %-12s %5d ids -> %5d tiles de 8x8  (%.2f por id)"
              % (clase, ids_clase[clase], len(tiles_clase[clase]),
                 len(tiles_clase[clase]) / float(ids_clase[clase] or 1)))
    print("  tiles distintos, cada chipset aparte: %5d = %.0f KB"
          % (suma_propios, suma_propios * comun.BYTES_POR_TILE / 1024.0))
    print("  compartiendo entre chipsets:          %5d = %.0f KB"
          % (len(todos), comun.kb(todos)))
    print("  (cuatro por id sería no compartir nada)")
    return comun.kb(todos)


def colores():
    """¿Alcanza una paleta por chipset?

    Los tiles sólo hace falta compartirlos entre mapas del **mismo** chipset, y
    la CGRAM se recarga al cambiar de mapa: la paleta no tiene que ser global.
    Se cuenta sobre los ids usados, que es lo que hace que la idea funcione.
    """
    CGRAM_FONDO = 111       # lo que le queda a la capa de fondo hoy
    filas = []
    lienzo = Image.new("RGBA", (16, 16))
    for cid, nombre, mapas_, ids, atlas in _atlas_por_chipset():
        entero, parte = set(), set()
        imagen = atlas.base.convert("RGBA")
        for y in range(imagen.height):
            for x in range(imagen.width):
                r, g, b, a = imagen.getpixel((x, y))
                if a:
                    entero.add((r >> 3, g >> 3, b >> 3))
        for tid in ids:
            lienzo.paste((0, 0, 0, 0), (0, 0, 16, 16))
            atlas.render_tile(lienzo, 0, 0, tid)
            px = lienzo.convert("RGBA")
            for y in range(16):
                for x in range(16):
                    r, g, b, a = px.getpixel((x, y))
                    if a:
                        parte.add((r >> 3, g >> 3, b >> 3))
        filas.append((len(parte), len(entero), nombre, mapas_, len(ids)))
    filas.sort()
    print("Paleta por chipset (contando sólo los ids que los mapas usan)")
    print("  el más chico %d, mediana %d, el más grande %d colores"
          % (filas[0][0], filas[len(filas) // 2][0], filas[-1][0]))
    print("  entran en los %d de la capa de fondo: %d de %d"
          % (CGRAM_FONDO, sum(1 for f in filas if f[0] <= CGRAM_FONDO), len(filas)))
    print("  entran en 256:                        %d de %d"
          % (sum(1 for f in filas if f[0] <= 256), len(filas)))
    print("  llevando el chipset entero en vez de lo usado: %d de %d"
          % (sum(1 for f in filas if f[1] <= CGRAM_FONDO), len(filas)))
    print("  los que más piden:")
    for parte, entero, nombre, mapas_, ids in filas[-5:]:
        print("     %-24s %3d colores de %3d en el archivo (%d mapas)"
              % (nombre[:24], parte, entero, mapas_))


def resto():
    """Backdrops, imágenes, panoramas y lo demás, filtrando por uso.

    Dónde buscar las referencias importa: los backdrops los eligen los
    **terrenos**, no los eventos, y las imágenes las piden sobre todo los
    **eventos comunes** —mirando sólo los mapas daban 20 de 111 usadas, y son
    97—.
    """
    import lcf

    def pesar(rutas):
        todos = set()
        for r in rutas:
            try:
                todos.update(comun.tiles_de_imagen(comun.abrir(r)))
            except Exception:
                continue
        return comun.kb(todos), len(todos)

    def archivos(carpeta):
        """El material del juego y el del RTP juntos, que es lo que hay.

        Mirando sólo la carpeta del juego los panoramas daban 571 KB en vez de
        991: ocho de los que los mapas piden viven en el RTP.
        """
        hay = {}
        for base in (comun.RTP, comun.JUEGO):     # el del juego pisa al del RTP
            for x in glob.glob(os.path.join(base, carpeta, "*")):
                hay[os.path.splitext(os.path.basename(x))[0].lower()] = x
        return hay

    pedidas = set()
    for _, game_map in comun.mapas():
        for evento in game_map.events:
            for pagina in evento.pages:
                for cmd in pagina.commands:
                    if cmd.code == 11110 and getattr(cmd, "string", ""):
                        pedidas.add(cmd.string.strip().lower())
    with open(os.path.join(comun.RAIZ, "data", "db",
                           "commonevents.json")) as archivo:
        for comun_ev in json.load(archivo):
            for cmd in comun_ev.get("event_commands") or ():
                if len(cmd) >= 3 and cmd[1] == "ShowPicture" and cmd[2]:
                    pedidas.add(cmd[2].strip().lower())

    with open(os.path.join(comun.RAIZ, "data", "db",
                           "terrains.json")) as archivo:
        fondos_ = {(t.get("background_name") or "").strip().lower()
                   for t in json.load(archivo)}
    fondos_.discard("")

    panoramas = set()
    for _, game_map in comun.mapas():
        nombre = (getattr(game_map, "parallax_name", "") or "").strip().lower()
        if nombre:
            panoramas.add(nombre)

    for carpeta, usados in (("Picture", pedidas), ("Backdrop", fondos_),
                            ("Panorama", panoramas), ("Monster", None),
                            ("Battle", None), ("FaceSet", None)):
        hay = archivos(carpeta)
        rutas = ([hay[n] for n in sorted(set(usados) & set(hay))]
                 if usados is not None else sorted(hay.values()))
        kb, _ = pesar(rutas)
        print("  %-9s %3d de %3d archivos -> %5.0f KB%s"
              % (carpeta, len(rutas), len(hay), kb,
                 "" if usados is not None else "   (sin filtrar por uso)"))


def todo():
    a = sprites(); print()
    b = fondos(); print()
    colores(); print()
    print("Lo demás")
    resto()
    print("\nsprites + fondos: %.0f KB" % (a + b))


if __name__ == "__main__":
    QUE = {"sprites": sprites, "fondos": fondos, "colores": colores,
           "resto": resto, "todo": todo}
    if len(sys.argv) != 2 or sys.argv[1] not in QUE:
        sys.exit(__doc__)
    QUE[sys.argv[1]]()

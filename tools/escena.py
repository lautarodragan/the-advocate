#!/usr/bin/env python3
"""La escena de la batalla: el fondo y los monstruos, horneados en una imagen.

Vive aparte de `snes_convert.py` por lo mismo que `imagen.py` y `animacion.py`:
no es un mapa, es un dibujo suelto, y lo único que el conversor y la referencia
tienen que compartir es **exactamente dónde cae y de qué color es cada pixel**.

taro pidió las dos cosas el 2026-09-13 —*"La batalla no tiene ni imagen de fondo
ni imagen del monstruo"*— y acá van juntas a propósito: **son el mismo dibujo**.
El fondo y los battlers se componen en el conversor y quedan como una sola
capa de fondo de 8bpp, así que la consola no dibuja battlers: sube una imagen.

Qué compra y qué cuesta esa decisión, que es lo que hay que saber para
cambiarla:

* **Compra no tener que rehacer la pantalla.** La grilla de texto de 32x28 está
  llena —ocho enemigos, cuatro actores y dos renglones de mensaje son los
  catorce renglones que entran— y un monstruo dibujado aparte pide sacar algo.
  Yendo al fondo, el texto se sigue viendo encima, como ya se veía sobre negro.
* **Compra los objetos.** Ninguno: no hay OAM que armar, ni tiles de sprite que
  subir, ni el límite de 34 tiles por línea, que con cuatro battlers de 64
  pixeles de ancho quedaba en 32 y sin margen.
* **Cuesta que un enemigo muerto se siga viendo.** En RM2k desaparece. Acá se
  ve igual, y lo que dice que murió es su renglón: el nombre en gris y los HP
  en cero. Es deuda declarada, y es la razón por la que la pantalla muestra los
  HP de los enemigos, que RM2k no hace.
* **Cuesta una imagen por tropa** y no una por fondo: si dos tropas usan el
  mismo fondo, el cartucho lleva las dos escenas. Son 32 KB cada una.

## La geometría

El fondo de batalla de RM2k mide 320x160 y se dibuja arriba de todo en una
pantalla de 320x240. Acá la pantalla es de 256x224, así que el fondo entra
escalado al **80%**: 256x128, que son los siete renglones de texto de arriba.
Los battlers van al mismo 80%, con lo cual las posiciones de la tropa —que en
el LDB son las del centro de cada battler, en coordenadas de 320x240— se
mapean multiplicando por lo mismo y sin ninguna otra cuenta.

Lo único que no es de RM2k es **el recorte**: un battler alto se sale de los
128 pixeles de la escena, así que su esquina se topa adentro. En RM2k no se
sale porque abajo tiene otros ochenta pixeles de pantalla. Los cuatro Lazer
Teeth miden 46x101 y uno de ellos se topa.

## El presupuesto

* **512 tiles de 8bpp, 32.768 B de VRAM**, que es exactamente la grilla de
  32x16 sin deduplicar. Deduplicar da 490 y 503 tiles en los dos fondos del
  juego —una foto no repite— así que no vale el código.
* **96 colores**, las entradas 32 a 127 de la CGRAM. Las 0 a 31 son las dos
  paletas del texto —blanco y gris, ver `titulo.pantalla_items`— y de 128 para
  arriba son las de los objetos, que esta pantalla no usa pero el mapa sí.
* En la VRAM de la pelea entra todo sin pelearle a nada: la pantalla de batalla
  **no comparte VRAM con el mapa**, porque `volver_al_mapa` la rehace entera al
  salir. Los tiles del texto viven en $2000, su tilemap en $3C00, el de la
  escena en $3800 y los tiles de la escena en $4000.
"""

import os

# La escena, en pixeles de pantalla: los siete renglones de texto de arriba.
ANCHO, ALTO = 256, 128
# El fondo de batalla de RM2k y la pantalla donde vive, de donde sale el 80%.
FONDO_RM = (320, 160)
PANTALLA_RM = (320, 240)
ESCALA_NUM, ESCALA_DEN = ANCHO, FONDO_RM[0]     # 256/320

# Los colores, y desde qué entrada de la CGRAM van. Ver "El presupuesto".
COLORES = 96
CGRAM_BASE = 32

CELDA = 8
TILES_X, TILES_Y = ANCHO // CELDA, ALTO // CELDA
TILES = TILES_X * TILES_Y                       # 512, la grilla entera

# Dónde vive en la VRAM, en palabras. El tilemap va antes del del texto
# —$3C00— y los tiles después, que es el único hueco de 32 KB que queda.
VRAM_MAPA = 0x3800
VRAM_TILES = 0x4000


def escalar(valor):
    """Un largo de RM2k en pixeles de la escena. La misma cuenta de los dos
    lados, con enteros: `//` redondearía distinto que el divisor del hardware
    sólo con negativos, y acá no los hay."""
    return max(1, (valor * ESCALA_NUM + ESCALA_DEN // 2) // ESCALA_DEN)


def _abrir(game_dir, carpeta, nombre):
    """Un PNG del juego con el color 0 como transparente, que es la regla de
    RM2k. Sale de `render_map.load_image` para no tener dos maneras de leer lo
    mismo."""
    import render_map
    camino = render_map.find_resource([game_dir], carpeta, nombre,
                                      (".png", ".bmp", ".xyz"))
    if camino is None:
        return None
    return render_map.load_image(camino)


def componer(db, tropa, fondo, game_dir):
    """El fondo con los battlers de la tropa encima, ya en 256x128.

    Devuelve None si falta el fondo: sin él no hay escena, y dibujar los
    monstruos flotando sobre negro sería inventar algo que RM2k no hace.
    """
    from PIL import Image
    imagen = _abrir(game_dir, "Backdrop", fondo)
    if imagen is None:
        return None
    imagen = imagen.resize((ANCHO, ALTO), Image.LANCZOS)
    for numero, (x, y) in zip(db.troops[tropa].members,
                              db.troops[tropa].posiciones):
        enemigo = db.enemies.get(numero)
        battler = _abrir(game_dir, "Monster",
                         getattr(enemigo, "battler_name", "") or "")
        if battler is None:
            continue
        chico = battler.resize((escalar(battler.width),
                                escalar(battler.height)), Image.LANCZOS)
        # La posición del LDB es **el centro** del battler, en la pantalla de
        # 320x240 de RM2k. Se escala igual que todo lo demás y se topa adentro
        # de la escena: ver "La geometría".
        px = min(max(escalar(x) - chico.width // 2, 0),
                 max(0, ANCHO - chico.width))
        py = min(max(escalar(y) - chico.height // 2, 0),
                 max(0, ALTO - chico.height))
        imagen.alpha_composite(chico, (px, py))
    return imagen


def convertir(db, tropa, fondo, game_dir):
    """La escena lista para las dos puntas, o None si no se puede dibujar.

    Devuelve un diccionario con:

      `indices`  la escena como índices de CGRAM, fila por fila. Ya vienen
                 corridos por `CGRAM_BASE`, que es lo que la consola lee.
      `paleta`   sus `COLORES` colores de 15 bits, en el orden en que van a la
                 CGRAM desde `CGRAM_BASE`.
      `fondo`    el nombre, para el informe.
    """
    import titulo
    imagen = componer(db, tropa, fondo, game_dir)
    if imagen is None:
        return None
    datos = imagen.convert("RGB").get_flattened_data()
    pixeles = [(r >> 3, g >> 3, b >> 3) for r, g, b in datos]
    paleta, mapa = titulo.reducir(pixeles, COLORES)
    donde = {color: i + CGRAM_BASE for i, color in enumerate(paleta)}
    indices = [[donde[mapa[pixeles[y * ANCHO + x]]] for x in range(ANCHO)]
               for y in range(ALTO)]
    return {"indices": indices, "paleta": paleta, "fondo": fondo,
            "tropa": tropa}


def tiles(info):
    """Los 512 tiles de 8x8, en el orden en que los lee el tilemap: fila por
    fila, sin deduplicar. Ver "El presupuesto"."""
    salida = []
    for ty in range(TILES_Y):
        for tx in range(TILES_X):
            salida.append([[info["indices"][ty * CELDA + y][tx * CELDA + x]
                            for x in range(CELDA)] for y in range(CELDA)])
    return salida


def informe(info):
    """Los números que justifican el reparto, para que el conversor los
    imprima."""
    return {"tropa": info["tropa"], "fondo": info["fondo"],
            "tiles": TILES, "bytes": TILES * 64,
            "colores": len(info["paleta"])}

#!/usr/bin/env python3
"""La escena de la batalla: el fondo y los monstruos, **compuestos en la consola**.

Vive aparte de `snes_convert.py` por lo mismo que `imagen.py` y `animacion.py`:
no es un mapa, es un dibujo suelto. Lo que el conversor y la ROM tienen que
compartir es exactamente dónde cae cada pixel y de qué color es.

taro pidió las dos cosas el 2026-09-13 —*"La batalla no tiene ni imagen de fondo
ni imagen del monstruo"*— y hasta el 2026-09-21 iban horneadas juntas: una
imagen de 32 KB **por tropa**, con el fondo y los battlers ya encima. Eso
multiplicaba imágenes por combinación —seis en `abl`, sobre cuatro fondos— y un
enemigo muerto se seguía viendo. Desde ese día, idea de taro, el cartucho lleva
**cada fondo una vez y cada battler una vez**, y la consola los compone al
empezar la pelea. Ver `escena_subir` en main.s.

Sigue siendo una sola capa de 8bpp en BG1, y eso es lo que compra lo mismo que
compraba antes:

* **No hay que rehacer la pantalla.** La grilla de texto de 32x28 está llena
  —ocho enemigos, cuatro actores y dos renglones de mensaje— y un monstruo
  dibujado con objetos pediría sacar algo. En el fondo, el texto se sigue
  viendo encima.
* **No hay objetos**: ni OAM que armar ni el límite de 34 tiles por línea, que
  con cuatro battlers de 64 pixeles de ancho quedaba en 32 y sin margen.

## Cómo se superpone un battler

El 8bpp de la SNES es **planar**: cada fila de un tile son ocho bytes, uno por
plano de bits, y los planos 0/1, 2/3, 4/5 y 6/7 van intercalados de a pares.
Así que poner un battler encima del fondo es, por byte de cada plano,
`fondo AND NOT máscara OR battler`, sin tocar pixel por pixel.

Cada battler tiene **15 colores más el transparente**. Sus 4 bits bajos salen de
su dibujo —el índice 0 es el transparente, que es la máscara— y sus 4 bits
altos son **la paleta que le toca en esta pelea**: la ROM la elige al empezar,
el primer battler distinto de la tropa en la paleta 8, el segundo en la 9, y
así. Los planos 4 a 7 no se guardan: son la máscara o cero, según los bits de
la paleta. Por eso el mismo battler sirve para cualquier tropa sin preparar
nada por combinación.

Que sean quince colores **es una decisión artística**: se pierde color respecto
de la escena horneada, donde los battlers compartían las 96 entradas con el
fondo. Qué se fusionó con qué queda escrito por battler en
`parches/auto/battlers/`, como las capas de los mapas. Ver `tools/port/parches.py`.

El borde también cambia: antes el battler se mezclaba con el fondo al
achicarlo —`alpha_composite`— y ahora cada pixel es del battler o del fondo,
con el corte en la mitad del alfa. Es lo que cuesta no preparar nada por tropa.

## La geometría

El fondo de batalla de RM2k mide 320x160 y se dibuja arriba de todo en una
pantalla de 320x240. Acá la pantalla es de 256x224, así que el fondo entra
escalado al **80%**: 256x128, que son los siete renglones de texto de arriba.
Los battlers van al mismo 80%, con lo cual las posiciones de la tropa —que en
el LDB son las del centro de cada battler, en coordenadas de 320x240— se
mapean multiplicando por lo mismo y sin ninguna otra cuenta.

Lo único que no es de RM2k es **el recorte**: un battler alto se sale de los
128 pixeles de la escena, así que su esquina se topa adentro. En RM2k no se
sale porque abajo tiene otros ochenta pixeles de pantalla.

## El presupuesto

* **512 tiles de 8bpp, 32.768 B de VRAM**, que es exactamente la grilla de
  32x16 sin deduplicar. Una foto no repite, y componer encima la haría repetir
  todavía menos.
* **Los colores**: el fondo lleva 96, las entradas 32 a 127 de la CGRAM —las 0
  a 31 son las dos paletas del texto—, y los battlers **las ocho paletas de
  arriba**, 128 a 255. Esas son las de los objetos del mapa, y la pelea no
  dibuja objetos; volver al mapa no las reponía enteras —el cartel y la
  animación de batalla se suben sólo cuando cambian—, así que ahora
  `volver_de_batalla` sube las 128 de `cgram_sombra` antes que nada.
* **La WRAM**: el fondo limpio en `$7F0000` y la escena compuesta en
  `$7F8000`, 32 KB cada uno. El limpio es lo que deja recomponer las celdas de
  un enemigo muerto sin volver a leer nada del cartucho: ver `escena_tick`.
* En la VRAM de la pelea entra todo sin pelearle a nada: la pantalla de batalla
  **no comparte VRAM con el mapa**, porque `volver_de_batalla` la rehace entera
  al salir. Los tiles del texto viven en $2000, su tilemap en $3C00, el de la
  escena en $3800 y los tiles de la escena en $4000.

## Qué fondos lleva el cartucho

Por ahora, **tres**. `FONDOS` dice cuáles; una pelea que pida otro
va sobre fondo liso, con los mismos battlers compuestos encima. Es el mismo
código con el fondo en cero, y no un parche: es también lo que pasa sin fondo
—un `EnemyEncounter` que no nombra ninguno, o un mapa que hereda el del
terreno— y lo que va a pasar sin MSU-1 el día que los fondos vengan de ahí.
"""

import collections
import os

# La escena, en pixeles de pantalla: los siete renglones de texto de arriba.
ANCHO, ALTO = 256, 128
# El fondo de batalla de RM2k y la pantalla donde vive, de donde sale el 80%.
FONDO_RM = (320, 160)
PANTALLA_RM = (320, 240)
ESCALA_NUM, ESCALA_DEN = ANCHO, FONDO_RM[0]     # 256/320

# Los colores del fondo, y desde qué entrada de la CGRAM van. Ver "El
# presupuesto".
COLORES = 96
CGRAM_BASE = 32
# Las paletas de los battlers: de la 8 a la 15, o sea las entradas 128 a 255.
# Una por battler distinto de la tropa, y una tropa tiene a lo sumo ocho
# enemigos, así que siempre alcanzan.
BATTLER_PALETA = 8
BATTLER_PALETAS = 8
BATTLER_COLORES = 15

CELDA = 8
TILES_X, TILES_Y = ANCHO // CELDA, ALTO // CELDA
TILES = TILES_X * TILES_Y                       # 512, la grilla entera

# Dónde vive en la VRAM, en palabras. El tilemap va antes del del texto
# —$3C00— y los tiles después, que es el único hueco de 32 KB que queda.
VRAM_MAPA = 0x3800
VRAM_TILES = 0x4000

# Los fondos que el cartucho lleva, **por nombre del juego**. Nacieron con el
# PoC del 2026-09-21 —el de la pelea del droide y el de los Back Alleys— y el
# mismo día taro sumó el de los Rat Tracks, que es donde siguen los encuentros
# al azar. Cualquier otro va sobre fondo liso.
FONDOS = ("SJBackdropABL04", "ABLBackdropSJ03", "ABLBackdropSJ08")

# Cuántos planos guarda el cartucho por fila de un battler: la máscara y los
# cuatro de su dibujo. Los otros cuatro los pone la ROM según la paleta.
BATTLER_PLANOS = 5


def escalar(valor):
    """Un largo de RM2k en pixeles de la escena. La misma cuenta de los dos
    lados, con enteros: `//` redondearía distinto que el divisor del hardware
    sólo con negativos, y acá no los hay."""
    return max(1, (valor * ESCALA_NUM + ESCALA_DEN // 2) // ESCALA_DEN)


def _abrir(game_dir, carpeta, nombre):
    """Un PNG del juego con el color 0 como transparente, que es la regla de
    RM2k. Sale de `render_map.load_image` para no tener dos maneras de leer lo
    mismo."""
    from render import render_map
    camino = render_map.find_resource([game_dir], carpeta, nombre,
                                      (".png", ".bmp", ".xyz"))
    if camino is None:
        return None
    return render_map.load_image(camino)


# --- el tono del battler ----------------------------------------------------

def _div(a, b):
    """La división entera de C, que trunca hacia cero. `//` redondea hacia
    abajo, y con numeradores negativos —el tono de un color donde el verde es
    menor que el azul— daría un tono corrido en uno."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _a_hsl(r, g, b):
    """`RGB_to_HSL` de easyrpg-player, `bitmap_hslrgb.h`, con sus enteros."""
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
    """`HSL_to_RGB` de easyrpg-player."""
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
    """`Bitmap::HueChangeBlit`: el `battler_hue` del enemigo, en grados.

    Es lo que hace que el mismo `BLmouse` sea la GiantRat, la MutantMouse y la
    HairyVermin. La escena horneada lo ignoraba; ahora, con un battler por
    enemigo y no por imagen, ignorarlo dibujaría a los tres iguales.
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


# --- el fondo -----------------------------------------------------------------

def fondo(nombre, game_dir):
    """Un fondo de batalla listo para la ROM, o None si no está.

      `indices`  256x128 índices de CGRAM, fila por fila, ya corridos por
                 `CGRAM_BASE`: es lo que la consola lee.
      `paleta`   sus `COLORES` colores de 15 bits, desde `CGRAM_BASE`.
    """
    from PIL import Image
    from port import titulo
    imagen = _abrir(game_dir, "Backdrop", nombre)
    if imagen is None:
        return None
    imagen = imagen.convert("RGB").resize((ANCHO, ALTO), Image.LANCZOS)
    pixeles = [(r >> 3, g >> 3, b >> 3)
               for r, g, b in imagen.get_flattened_data()]
    paleta, mapa = titulo.reducir(pixeles, COLORES)
    donde = {color: i + CGRAM_BASE for i, color in enumerate(paleta)}
    indices = [[donde[mapa[pixeles[y * ANCHO + x]]] for x in range(ANCHO)]
               for y in range(ALTO)]
    return {"nombre": nombre, "indices": indices, "paleta": paleta}


def tiles(indices):
    """Los 512 tiles de 8x8 de una grilla de 256x128, en el orden en que los
    lee el tilemap: fila por fila, sin deduplicar. Ver "El presupuesto"."""
    salida = []
    for ty in range(TILES_Y):
        for tx in range(TILES_X):
            salida.append([[indices[ty * CELDA + y][tx * CELDA + x]
                            for x in range(CELDA)] for y in range(CELDA)])
    return salida


# --- los battlers ---------------------------------------------------------------

def clave(nombre, tono):
    """Cómo se llama un battler en el cartucho y en `parches/`: la imagen y su
    tono, que es lo que lo hace distinto de otro con la misma imagen."""
    return "%s-%d" % (nombre, tono) if tono else nombre


def battler(nombre, tono, game_dir):
    """Un battler listo para la ROM, o None si no está la imagen.

      `ancho`, `alto`  en pixeles de la escena, ya al 80%.
      `pixeles`        fila por fila, de 0 a 15: 0 es el transparente y los
                       otros el color en `paleta`, más uno.
      `paleta`         sus hasta quince colores de 15 bits.
      `colores`        cuántos distintos traía el dibujo, ya achicado.
      `fusiones`       qué se fusionó con qué para llegar a quince, como las
                       devuelve `asignador.merge_least_visible`.
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
    # Un pixel es del battler o del fondo: la mitad del alfa decide.
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
    # Lo que se sale de la escena no se guarda: un battler más alto que ella
    # queda topado arriba —ver `posicion`— y sus filas de abajo no se ven.
    ancho, alto = min(ancho, ANCHO), min(alto, ALTO)
    pixeles = [[0 if opacos[y * chica.width + x] is None
                else lugar[mapeo[opacos[y * chica.width + x]]]
                for x in range(ancho)] for y in range(alto)]
    return {"clave": clave(nombre, tono), "imagen": nombre, "tono": tono,
            "ancho": ancho, "alto": alto, "pixeles": pixeles,
            "alto_rm": imagen.height,
            "paleta": paleta, "colores": len(cuenta), "fusiones": fusiones}


def columnas(info):
    """Cuántos bytes mide una fila de un plano: ocho pixeles por byte."""
    return (info["ancho"] + 7) // 8


def battler_bytes(info):
    """Un battler en el formato que lee `escena_poner`.

    **Plano por plano**, y dentro de cada plano fila por fila: la máscara
    primero y después los cuatro planos del dibujo. Cada fila de un plano mide
    `columnas + 1` bytes y va **al revés**, la columna de la derecha primero,
    con un cero adelante:

        [0] [col n-1] ... [col 1] [col 0]

    Así una lectura de dieciséis bits en la columna `k` trae la `k` en el byte
    bajo y la `k - 1` en el alto, que es exactamente la palabra que hay que
    correr a la derecha para acomodar un battler que no cae en el borde de un
    tile. La columna `-1` es el cero de adelante de la fila siguiente —o del
    plano siguiente—, así que la ROM no tiene que preguntar por el borde; el
    último plano lleva un cero de más al final por lo mismo.
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
    """Dónde cae la esquina de un battler en la escena, ya topada adentro.

    La posición del LDB es **el centro** del battler, en la pantalla de 320x240
    de RM2k. Se escala igual que todo lo demás y se topa adentro de la escena:
    ver "La geometría".
    """
    x, y = centro
    px = min(max(escalar(x) - info["ancho"] // 2, 0),
             max(0, ANCHO - info["ancho"]))
    py = min(max(escalar(y) - info["alto"] // 2, 0),
             max(0, ALTO - info["alto"]))
    return px, py


def orden_de_dibujo(centros, infos):
    """En qué orden se ponen los enemigos de una tropa: el que va después tapa.

    Es `Sprite_Battler::ResetZ` de easyrpg: la profundidad es el borde de abajo
    del battler en RM2k —el centro del LDB más la mitad del alto del PNG— y, a
    igual borde, queda arriba el de menor lugar en la tropa. `infos` puede
    traer None para un enemigo sin battler: no se dibuja, y da igual dónde
    caiga.
    """
    def z(k):
        alto = infos[k]["alto_rm"] if infos[k] else 0
        return (centros[k][1] + alto // 2, -k)
    return sorted(range(len(centros)), key=z)


def componer(fondo_indices, puestos):
    """La escena como la compone la consola, en índices de CGRAM.

    `fondo_indices` es la grilla de un fondo, o None para el fondo liso.
    `puestos` son `(info, paleta, x, y)` en el orden en que la ROM los pone,
    que es `orden_de_dibujo`: el que va después tapa al de antes. No lo usa el
    conversor —la ROM compone sola— sino las pruebas, para saber qué tiene que
    haber en cada pixel.
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
    """Los números del battler, para que el conversor los imprima."""
    return {"clave": info["clave"], "ancho": info["ancho"],
            "alto": info["alto"], "bytes": len(battler_bytes(info)),
            "colores": info["colores"], "quedan": len(info["paleta"])}

#!/usr/bin/env python3
"""La pantalla de título: de `Title/ABL20Title.png` a tiles, paleta y tilemap.

Vive aparte de `snes_convert.py` porque no es un mapa: no tiene chipset, ni
eventos, ni capa de encima. Es una imagen sola, y el único trabajo es meterla
en el modo 3 sin que pierda nada que se note.

**Va en BG1, que en modo 3 tiene ocho bits por pixel**, o sea que direcciona
CGRAM entera y no necesita repartir nada en paletas de dieciséis. Es el único
lugar del port donde eso vale la pena: un mapa gasta sus 256 colores en varias
paletas porque los sprites necesitan las suyas, y acá no hay sprites.

**Se escala y no se recorta**, y eso costó mirar la imagen: el original es de
320x240 y la pantalla de 256x224, así que el recorte centrado se come el "2.1"
del título por la derecha y los créditos de `Additional Graphics` por abajo. Lo
que se paga a cambio es que la imagen queda 20% más angosta —el aspecto del
original no es el de la consola— y que los colores suben de 133 a 369, porque
interpolar inventa tonos entre los que había.

De ahí sale el único paso que no es mecánico: de 369 colores a 256.
"""

import collections

CELL = 8
ANCHO = 256
ALTO = 224
COLS = ANCHO // CELL            # 32
FILAS = ALTO // CELL            # 28

# Cuántas entradas de CGRAM se lleva el menú, que va en BG2 a cuatro bits por
# pixel: una paleta de dieciséis, la 0. Son las **primeras** de CGRAM porque un
# BG de 4bpp sólo alcanza las de abajo, así que la imagen no puede quedarse con
# ellas y arranca corrida.
MENU_CGRAM = 16

# Cuántos colores le quedan a la imagen. Bajar de 256 a 240 no se ve: ya venía
# de 369, y los que se fusionan son los que aparecen en un puñado de pixeles.
COLORES = 256 - MENU_CGRAM
NEGRO = (0, 0, 0)


def _distancia(a, b):
    """Lo lejos que están dos colores de 15 bits, al cuadrado.

    Euclídea y sin pesos por canal: la alternativa —ponderar por luma, que es
    lo que hace `merge_least_used` para las paletas de dieciséis— acá no
    cambiaría nada visible y sí haría falta explicar por qué los pesos son esos.
    Los colores que se fusionan son los que casi no aparecen, y el vecino que
    les toca está a un paso de distancia.
    """
    return sum((x - y) ** 2 for x, y in zip(a, b))


def reducir(pixeles, tope=COLORES):
    """Los colores de la imagen llevados a `tope`, y el mapa de a dónde fue cada uno.

    Se queda con los más usados y manda cada uno de los que sobran a su vecino
    más cercano de los que quedaron. **No es mediancut**: no promedia colores,
    así que no puede inventar uno que no estuviera en la imagen y no hay que
    volver a cuantizar a 15 bits después. Y no depende de qué versión de PIL
    esté instalada, que es lo que hace que la referencia y el conversor puedan
    llamarlo y obtener lo mismo.

    El desempate es por el color, no por el orden en que aparecieron: dos
    colores con la misma cuenta tienen que caer siempre del mismo lado o la
    ROM y la referencia se separan sin que nadie haya tocado nada.
    """
    cuenta = collections.Counter(pixeles)
    # El negro se queda con el índice 0 aunque no fuera de los más usados: es
    # el color del fondo, y así lo que el PPU pinta donde no hay nada coincide
    # con lo que la imagen tiene ahí.
    orden = sorted(cuenta, key=lambda c: (-cuenta[c], c))
    if NEGRO in orden:
        orden.remove(NEGRO)
    paleta = [NEGRO] + orden[:tope - 1]
    quedan = set(paleta)
    mapa = {c: c for c in quedan}
    for color in orden[tope - 1:]:
        mapa[color] = min(paleta, key=lambda p: (_distancia(color, p), p))
    return paleta, mapa


def _quince(imagen):
    """La imagen escalada a la pantalla y con los colores a 15 bits.

    El escalado es LANCZOS, que es el que menos ensucia los bordes del texto
    del título; el original tiene mucho degradé y poco detalle fino, así que la
    diferencia contra bicúbico se ve en los créditos y en ningún otro lado.
    """
    from PIL import Image
    chica = imagen.convert("RGB").resize((ANCHO, ALTO), Image.LANCZOS)
    return [(r >> 3, g >> 3, b >> 3) for r, g, b in chica.get_flattened_data()]


def convertir(imagen):
    """La imagen de título como (tiles, paleta, tilemap).

    `tiles` son los tiles únicos de 8 bits por pixel; `paleta` sus colores, que
    van en CGRAM **a partir de `MENU_CGRAM`** porque las de abajo son del menú;
    `tilemap` las 32x28 entradas, en el tilemap de 32x32 que el PPU espera.

    Los índices que los tiles llevan ya vienen corridos, así que quien los emita
    no tiene que acordarse de sumar nada: el corrimiento se escribe una sola vez
    y acá.
    """
    pixeles = _quince(imagen)
    paleta, mapa = reducir(pixeles)
    indice = {color: i + MENU_CGRAM for i, color in enumerate(paleta)}
    # La imagen como índices de paleta, fila por fila.
    filas = []
    for y in range(ALTO):
        filas.append([indice[mapa[pixeles[y * ANCHO + x]]] for x in range(ANCHO)])

    tiles, donde, tilemap = [], {}, []
    for ty in range(FILAS):
        for tx in range(COLS):
            celda = tuple(tuple(filas[ty * CELL + y][tx * CELL:(tx + 1) * CELL])
                          for y in range(CELL))
            if celda not in donde:
                donde[celda] = len(tiles)
                tiles.append(celda)
            tilemap.append(donde[celda])
    return tiles, paleta, tilemap


def informe(imagen):
    """Los números que justifican el reparto, para que la receta los imprima."""
    tiles, paleta, tilemap = convertir(imagen)
    return {
        "tiles": len(tiles),
        "colores": len(paleta),
        "bytes_tiles": len(tiles) * 64,
        "bytes_tilemap": 32 * 32 * 2,
    }


def render(imagen, sys_img=None, textos=None, elegida=0, font_id=None):
    """La pantalla de título como la tiene que mostrar la consola.

    Es `convertir` deshecho: los tiles vueltos a poner en su lugar según el
    tilemap, con los colores de la paleta llevados de 15 bits a 24. Que salga de
    los mismos datos que la ROM sube no lo hace una comparación vacía: lo que se
    verifica es el otro tramo del camino —el DMA a la VRAM, las dos bases del
    PPU, el scroll de una línea que ya costó un rojo en los mapas— y ahí la ROM
    puede equivocarse sin que la referencia se entere.

    Lo que esta comparación **no** puede ver es que la imagen esté mal
    convertida: si `convertir` eligiera mal los 256 colores, los dos lados se
    equivocarían igual y el resultado seguiría dando cero. Eso se mira con los
    ojos, una vez, y no vuelve a cambiar.
    """
    from PIL import Image
    tiles, paleta, tilemap = convertir(imagen)
    fuera = Image.new("RGB", (ANCHO, ALTO))
    px = fuera.load()
    for i, indice in enumerate(tilemap):
        tx, ty = (i % COLS) * CELL, (i // COLS) * CELL
        celda = tiles[indice]
        for y in range(CELL):
            for x in range(CELL):
                color = paleta[celda[y][x] - MENU_CGRAM]
                px[tx + x, ty + y] = tuple(v << 3 for v in color)
    if sys_img is None:
        return fuera
    # El menú va encima, y **por el mismo camino que la ROM**: los tiles de
    # 4bpp que emite `menu`, no la capa de texto de la que salieron. Dibujar
    # acá el texto con la fuente y allá con los tiles dejaría afuera justo el
    # paso que puede salir mal —cuantizar el degradé del skin a quince colores—
    # y la comparación no lo vería.
    tiles_menu, paleta_menu, mapas = menu(sys_img, textos, font_id)
    for i, indice in enumerate(mapas[elegida]):
        tx, ty = (i % COLS) * CELL, (i // COLS) * CELL
        if ty >= ALTO:
            break
        celda = tiles_menu[indice]
        for y in range(CELL):
            for x in range(CELL):
                valor = celda[y][x]
                if valor:       # el índice 0 no se dibuja: deja ver la imagen
                    px[tx + x, ty + y] = tuple(
                        v << 3 for v in paleta_menu[valor])
    return fuera


def main():
    import argparse
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PIL import Image
    from render_map import GAME_DIR
    import lcf

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", required=True,
                        help="PNG con la pantalla como la tiene que mostrar "
                             "la consola: es la referencia contra la que se "
                             "compara la captura")
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--elegida", type=int, default=0,
                        help="qué opción del menú —o qué ranura— está marcada, "
                             "desde cero")
    parser.add_argument("--ranuras", type=int, default=None, metavar="N",
                        help="dibuja la pantalla de N ranuras en vez de la de "
                             "título")
    parser.add_argument("--llenas", default="", metavar="0,1,...",
                        help="qué ranuras tienen partida, separadas por comas. "
                             "Sin esto, ninguna")
    parser.add_argument("--grupo-ranura", action="append", default=[],
                        metavar="N:ACTOR,ACTOR,...",
                        help="el grupo guardado en la ranura N, por ids de "
                             "actor: pone el nombre del primero y las caras. "
                             "La ranura cuenta como llena. Se repite por "
                             "ranura")
    parser.add_argument("--modo", type=int, default=0,
                        help="0 para la pantalla de cargar y 1 para la de "
                             "guardar; cambia el texto de la cabecera")
    parser.add_argument("--sin-menu", action="store_true",
                        help="sólo la imagen, sin las opciones encima")
    parser.add_argument("--informe", action="store_true",
                        help="además, los números del reparto")
    args = parser.parse_args()

    # Qué imagen es lo dice el LDB y no la línea de comandos: `title_name`.
    db = lcf.Database(os.path.join(args.game_dir, "RPG_RT.ldb"))
    imagen = Image.open(os.path.join(args.game_dir, "Title",
                                     db.title_name + ".png"))
    if args.ranuras:
        import ventana as ventana_mod
        skin = ventana_mod.skin(args.game_dir, db.system_name)
        llenas = [n in {int(x) for x in args.llenas.split(",") if x != ""}
                  for n in range(args.ranuras)]
        grupos = {}
        for uno in args.grupo_ranura:
            ranura, _, actores = uno.partition(":")
            grupos[int(ranura)] = [int(a) for a in actores.split(",") if a]
            llenas[int(ranura)] = True
        render_ranuras(skin, db, args.ranuras, llenas, args.elegida,
                       args.modo, db.font_id, grupos,
                       args.game_dir).save(args.output)
        print("ranuras %s -> %s"
              % ("".join("X" if l else "." for l in llenas), args.output))
        return
    if args.sin_menu:
        render(imagen).save(args.output)
    else:
        import ventana as ventana_mod
        skin = ventana_mod.skin(args.game_dir, db.system_name)
        render(imagen, skin, opciones(db), args.elegida,
               db.font_id).save(args.output)
    if args.informe:
        datos = informe(imagen)
        print("%s: %d tiles de 8bpp (%d B) + %d colores, %d B de tilemap"
              % (db.title_name, datos["tiles"], datos["bytes_tiles"],
                 datos["colores"], datos["bytes_tilemap"]))
    print("%s -> %s" % (db.title_name, args.output))



# --- el menú -----------------------------------------------------------------
#
# Las dos opciones del título van en **BG2, que en modo 3 tiene cuatro bits por
# pixel**, y no en BG1 con la imagen. Dos razones, y las dos se miden: en BG1
# habría que mezclar el texto con la imagen al convertir, o sea un tile nuevo
# por cada celda donde el texto pisa el fondo, y el texto dejaría de poder
# moverse; y en 4bpp cada tile cuesta la mitad.
#
# El cursor **no se dibuja aparte**: se emite un tilemap por opción
# seleccionada, y mover el cursor es subir el otro. Son 2048 B por tilemap y un
# DMA que sólo corre cuando el jugador aprieta arriba o abajo. La alternativa
# —escribir a mano las dos palabras del tilemap que cambian— ahorra 2 KB de
# cartucho y pide saber en qué celda cae cada flecha, que es justo la clase de
# número que se escribe mal en un lado y no en el otro.
MENU_Y = 152                    # dónde arranca la primera opción, en pixeles
MENU_ALTO = 24                  # y cada cuánto va la siguiente
MENU_X = 72
CURSOR = "> "
SIN_CURSOR = "  "


def opciones(db):
    """Los textos del menú, como los dice el juego y no como los diríamos.

    En el ABL son 'Begin the Story' y 'Resume the Story'; el motor de fábrica
    diría 'New Game' y 'Load Game'. Salen de los términos del LDB.
    """
    return [db.term_new_game, db.term_load_game]


def _capa_de_texto(sys_img, textos, elegida, font_id=None):
    """Una pantalla transparente con las opciones dibujadas, y el cursor puesto.

    Se dibuja con `ventana.dibujar_linea`, que es la misma que compone los
    mensajes: misma fuente, mismo degradé de color, misma sombra corrida uno.
    Que el menú del título y un mensaje del juego se vean iguales no es un
    detalle estético: es lo que hace que no haya una segunda fuente que
    mantener.
    """
    from PIL import Image
    import ventana as ventana_mod
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    for n, texto in enumerate(textos):
        marca = CURSOR if n == elegida else SIN_CURSOR
        ventana_mod.dibujar_linea(capa, sys_img, MENU_X, MENU_Y + n * MENU_ALTO,
                                  marca + texto, font_id=font_id)
    return capa


def menu(sys_img, textos, font_id=None):
    """Los tiles de 4bpp del menú, su paleta, y un tilemap por opción.

    Los tiles se juntan de **todas** las variantes antes de deduplicar: el
    banco es uno solo y los tilemaps lo indexan, así que armar cada variante por
    separado daría índices que no coinciden.

    El índice 0 de la paleta es transparente y le toca a la celda vacía, que es
    casi toda la pantalla: por eso el banco termina siendo chico aunque el
    tilemap tenga 1024 entradas.
    """
    capas = [_capa_de_texto(sys_img, textos, n, font_id)
             for n in range(len(textos))]

    # Los colores de todas las capas juntos, a 15 bits. El transparente no
    # cuenta: es el índice 0 y no se dibuja.
    vistos = collections.Counter()
    for capa in capas:
        for r, g, b, a in capa.get_flattened_data():
            if a:
                vistos[(r >> 3, g >> 3, b >> 3)] += 1
    if len(vistos) > 15:
        raise SystemExit(
            "el menú del título usa %d colores y en 4bpp entran 15. El degradé "
            "del skin es el sospechoso: mirar `color_de_texto` en ventana.py"
            % len(vistos))
    paleta = [NEGRO] + sorted(vistos, key=lambda c: (-vistos[c], c))
    indice = {color: i for i, color in enumerate(paleta)}

    tiles, donde, tilemaps = [], {}, []
    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    donde[vacio] = 0
    tiles.append(vacio)
    for capa in capas:
        px = capa.load()
        mapa = []
        for ty in range(32):
            for tx in range(COLS):
                celda = []
                for y in range(CELL):
                    fila = []
                    for x in range(CELL):
                        sx, sy = tx * CELL + x, ty * CELL + y
                        if sy >= ALTO:
                            fila.append(0)
                            continue
                        r, g, b, a = px[sx, sy]
                        fila.append(indice[(r >> 3, g >> 3, b >> 3)] if a else 0)
                    celda.append(tuple(fila))
                celda = tuple(celda)
                if celda not in donde:
                    donde[celda] = len(tiles)
                    tiles.append(celda)
                mapa.append(donde[celda])
        tilemaps.append(mapa)
    return tiles, paleta, tilemaps

# --- la pantalla de ranuras --------------------------------------------------
#
# La usan las dos puntas: "Resume the Story" en el título, y el save point de
# Lashe City. Es una pantalla propia y no una capa encima del título, así que
# tiene la VRAM para ella sola y todo puede ir en 4bpp.
#
# **Todo el texto está pre-renderizado**, incluidas las dos variantes de cada
# ranura —vacía y ocupada—. Es lo que evita tener que componer texto en caliente
# como hace la ventana de mensaje: los datos que la pantalla muestra o son fijos
# (el número de ranura) o están mockeados (el nivel), así que no hay nada que
# armar mientras corre. El día que el nivel sea de verdad, esa línea pasa a
# componerse con glifos sueltos como los dígitos del cronómetro, y el resto
# queda igual.
#
# Lo que la ROM sí hace en caliente es **elegir qué bloque de celdas escribe en
# cada fila**: por ranura hay cuatro —vacía o llena, con cursor o sin él— y
# mover el cursor es reescribir dos filas de 96 celdas. No hay tilemap completo
# por combinación porque serían 64.
# La fila mide **48 pixeles, seis celdas**, que es lo que mide una cara del
# FaceSet: `Window_SaveFile::Refresh` en easyrpg dibuja, por archivo, el nombre
# del archivo, el del líder, el nivel y los puntos de vida, y las caras de
# hasta cuatro del grupo a 48x48. Acá van tres líneas de texto a la izquierda y
# hasta tres caras a la derecha: la cuarta no entra en 256 pixeles sin comerse
# el borde, que en un televisor de tubo no se ve. Cuatro filas de 48 más la
# cabecera terminan en la línea 216 de las 224.
RANURA_Y = 24                   # dónde arranca la primera fila, en pixeles
# Y cada cuánto va la siguiente. **Múltiplo de 8 a propósito**: cada fila se
# sube al tilemap como un bloque de celdas enteras, así que si el salto no
# cayera en una celda el texto de una fila se escribiría en el bloque de la
# siguiente y se cortaría.
RANURA_SALTO = 48
RANURA_FILAS = 6                # celdas de 8 px de alto que ocupa cada una
RANURA_X = 56                   # dónde arranca el texto
LINEA = 16                      # cada cuánto va una línea de texto en la fila
CABECERA_Y = 4
CABECERA_FILAS = 2
# Qué dice una ranura sin partida. RM2k no tiene un término para esto —su menú
# muestra el hueco vacío— así que el texto es nuestro y por eso se escribe acá
# y no se saca del LDB, para que se vea que lo inventamos.
VACIA = "- Empty -"
# Las caras: dónde va la primera, en celdas desde el borde izquierdo, y cada
# cuántas la siguiente. Seis de ancho por seis de alto, pegadas.
CARA = 48
CARA_CELDAS = CARA // CELL      # 6
CARA_COL = 14                   # o sea x = 112
CARA_PASO = CARA_CELDAS         # pegadas: 112, 160, 208
CARAS_MAX = 3
# El nombre del líder, en la segunda línea: un bloque de dos celdas de alto
# —la fuente mide 12 con la sombra— y siete de ancho, o sea nueve caracteres
# de 6 px, que es lo más largo que hay en el LDB.
NOMBRE_COL = RANURA_X // CELL   # 7
NOMBRE_COLS = 7
NOMBRE_FILA = LINEA // CELL     # 2: la segunda línea arranca en y+16
NOMBRE_FILAS = 2
# Y con qué paleta van las caras: la 0 es del texto, y cada cara lleva la suya
# desde la 1. Son las paletas de BG2 a 4bpp, que en la consola son ocho.
CARAS_PALETAS_MAX = 7
# Cuántos tiles entran en el banco de la pantalla: el conversor lo comprueba
# contra el reparto de VRAM, ver RANURA_MAP allá.
RANURA_TILES_MAX = 448


def _bloque_de_celdas(capa, fila0, filas, tiles, donde, indice, col0=0,
                      cols=COLS, paleta=0):
    """Las celdas de un rectángulo de `capa`, agregando tiles nuevos.

    Devuelve la lista de palabras del tilemap, de a `cols` por fila: el índice
    del tile con los tres bits de `paleta` encima. Los tiles se comparten con
    todo lo demás de la pantalla: el banco es uno solo y los bloques lo
    indexan, así que deduplicar por separado daría índices que no coinciden.
    Se deduplican por sus índices y no por sus colores, así que un tile con el
    mismo dibujo en dos paletas es uno solo.

    `indice` va de color de 15 bits a índice de paleta; lo que no esté ahí es
    un error y no un color parecido, para que un color de más se note.
    """
    px = capa.load()
    celdas = []
    for fila in range(filas):
        for col in range(col0, col0 + cols):
            celda = []
            for y in range(CELL):
                renglon = []
                for x in range(CELL):
                    sx = col * CELL + x
                    sy = (fila0 + fila) * CELL + y
                    if sy >= ALTO or sx >= ANCHO:
                        renglon.append(0)
                        continue
                    r, g, b, a = px[sx, sy]
                    renglon.append(indice[(r >> 3, g >> 3, b >> 3)] if a else 0)
                celda.append(tuple(renglon))
            celda = tuple(celda)
            if celda not in donde:
                donde[celda] = len(tiles)
                tiles.append(celda)
            celdas.append(donde[celda] | (paleta << 10))
    return celdas


def _texto_de_ranura(numero, db, llena):
    """Las líneas de una ranura, con los términos del juego: la primera y la
    tercera; la segunda es el nombre del líder, que va aparte porque depende
    de la partida.

    El nivel está **mockeado en 1**: la partida guarda la posición, el mapa, el
    grupo, los switches y el oro, pero todavía no hay actores con nivel. Es una
    decisión tomada con taro y no un olvido; el día que exista, sale de la
    partida.
    """
    if not llena:
        return ["%s %d" % (db.term_file, numero + 1), VACIA, ""]
    return ["%s %d" % (db.term_file, numero + 1), "",
            "%s 1" % db.term_level]


def cara_de(db, actor, game_dir):
    """La cara del actor, 48x48 en RGBA, o None si no tiene.

    Va por `render_map.load_image` y no por `Image.open`, como el skin: en
    RM2k el índice 0 de la paleta es transparente también en un FaceSet, y en
    `ABLFaces` es un rojo que ocupa casi toda la cara. Dibujado opaco, cada
    cara era un cuadrado rojo con un muñeco adentro.
    """
    import os
    import render_map
    a = db.actors[actor]
    if not a.face_name:
        return None
    hoja = render_map.load_image(os.path.join(game_dir, "FaceSet",
                                              a.face_name + ".png"))
    col, fila = a.face_index % 4, a.face_index // 4
    return hoja.crop((col * CARA, fila * CARA, (col + 1) * CARA,
                      (fila + 1) * CARA))


def _paleta_de_cara(cara):
    """Quince colores para una cara, y de cada color de la imagen a cuál va.

    Las caras del ABL usan entre 22 y 29 colores de 15 bits, y en una paleta de
    4bpp entran 15: se reduce como la imagen del título, con `reducir`, que
    manda cada color que sobra al más cercano de los que quedan. El índice 0 es
    el transparente, y el negro va ahí: sobre el fondo negro de la pantalla da
    lo mismo y no gasta una entrada.
    """
    pixeles = [(r >> 3, g >> 3, b >> 3) if a else NEGRO
               for r, g, b, a in cara.get_flattened_data()]
    usados = collections.Counter(p for p in pixeles if p != NEGRO)
    if len(usados) > 15:
        paleta, destino = reducir([p for p in pixeles if p != NEGRO], 15)
    else:
        paleta = sorted(usados, key=lambda c: (-usados[c], c))
        destino = {c: c for c in usados}
    colores = [NEGRO] + list(paleta)
    indice = {NEGRO: 0}
    for color, a_donde in destino.items():
        indice[color] = colores.index(a_donde)
    return colores, indice


def pantalla_ranuras(sys_img, db, ranuras, font_id=None, actores=(),
                     game_dir=None):
    """Los tiles de la pantalla de ranuras, sus paletas y sus bloques de celdas.

    Devuelve `(tiles, paletas, cabeceras, filas, caras, nombres)`:

    * `paletas[0]` es la del texto y las que siguen, una por cara.
    * `cabeceras[modo]` son las celdas del título de la pantalla, con `modo` 0
      para cargar y 1 para guardar. Los dos textos salen del LDB
      —`load_game_message` y `save_game_message`, que en el ABL dicen "Load
      which slot?" y "Save in which slot?"—.
    * `filas[ranura][llena][cursor]` son las celdas de una fila entera, con
      las celdas de las caras y del nombre en blanco.
    * `caras[actor]` son las 36 celdas de la cara, con su paleta puesta, para
      los `actores` que tienen una; `nombres[actor]` las 14 del nombre. La ROM
      los escribe encima de la fila según el grupo que la partida guardó, y
      `render_ranuras` hace lo mismo.

    Todas las variantes se dibujan antes de deduplicar, por lo mismo de siempre:
    el banco de tiles es uno solo.
    """
    from PIL import Image
    import ventana as ventana_mod

    def capa():
        return Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))

    def escribir(destino, x, y, texto):
        if texto:
            ventana_mod.dibujar_linea(destino, sys_img, x, y, texto,
                                      font_id=font_id)

    # Primero todas las capas de texto, para poder juntar los colores de una vez.
    capas = []
    for modo, texto in enumerate((db.term_load_message, db.term_save_message)):
        una = capa()
        escribir(una, RANURA_X, CABECERA_Y, texto)
        capas.append(("cabecera", modo, una))
    for numero in range(ranuras):
        for llena in (0, 1):
            for cursor in (0, 1):
                una = capa()
                y = RANURA_Y + numero * RANURA_SALTO
                if cursor:
                    escribir(una, RANURA_X - 16, y + 2, ">")
                for n, linea in enumerate(_texto_de_ranura(numero, db, llena)):
                    escribir(una, RANURA_X, y + 2 + n * LINEA, linea)
                capas.append(("fila", (numero, llena, cursor), una))
    for actor in actores:
        una = capa()
        escribir(una, RANURA_X, RANURA_Y + 2 + LINEA, db.actors[actor].name)
        capas.append(("nombre", actor, una))

    vistos = collections.Counter()
    for _, _, una in capas:
        for r, g, b, a in una.get_flattened_data():
            if a:
                vistos[(r >> 3, g >> 3, b >> 3)] += 1
    if len(vistos) > 15:
        raise SystemExit(
            "la pantalla de ranuras usa %d colores y en 4bpp entran 15"
            % len(vistos))
    paleta = [NEGRO] + sorted(vistos, key=lambda c: (-vistos[c], c))
    indice = {color: i for i, color in enumerate(paleta)}

    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde = [vacio], {vacio: 0}
    cabeceras = [None, None]
    filas = [[[None, None], [None, None]] for _ in range(ranuras)]
    nombres = {}
    for clase, clave, una in capas:
        if clase == "cabecera":
            cabeceras[clave] = _bloque_de_celdas(
                una, CABECERA_Y // CELL, CABECERA_FILAS, tiles, donde, indice)
        elif clase == "fila":
            numero, llena, cursor = clave
            fila0 = (RANURA_Y + numero * RANURA_SALTO) // CELL
            filas[numero][llena][cursor] = _bloque_de_celdas(
                una, fila0, RANURA_FILAS, tiles, donde, indice)
        else:
            nombres[clave] = _bloque_de_celdas(
                una, RANURA_Y // CELL + NOMBRE_FILA, NOMBRE_FILAS, tiles,
                donde, indice, NOMBRE_COL, NOMBRE_COLS)

    # Y las caras, cada una con su paleta, pegadas arriba a la izquierda de la
    # primera fila para cortarlas en celdas con la misma función.
    paletas, caras = [paleta], {}
    for actor in actores:
        cara = cara_de(db, actor, game_dir)
        if cara is None:
            continue
        if len(paletas) > CARAS_PALETAS_MAX:
            raise SystemExit(
                "más de %d actores con cara pueden entrar al grupo y BG2 "
                "tiene ocho paletas, una de ellas del texto"
                % CARAS_PALETAS_MAX)
        colores, indice_cara = _paleta_de_cara(cara)
        una = capa()
        una.paste(cara, (CARA_COL * CELL, RANURA_Y))
        caras[actor] = _bloque_de_celdas(
            una, RANURA_Y // CELL, CARA_CELDAS, tiles, donde, indice_cara,
            CARA_COL, CARA_CELDAS, len(paletas))
        paletas.append(colores)
    if len(tiles) > RANURA_TILES_MAX:
        raise SystemExit(
            "la pantalla de ranuras junta %d tiles y en su banco entran %d"
            % (len(tiles), RANURA_TILES_MAX))
    return tiles, paletas, cabeceras, filas, caras, nombres


def render_ranuras(sys_img, db, ranuras, llenas, elegida, modo=0, font_id=None,
                   grupos=None, game_dir=None):
    """La pantalla de ranuras como la tiene que mostrar la consola.

    `llenas` es una secuencia de booleanos, una por ranura; `elegida`, dónde
    está el cursor; `modo`, 0 para cargar y 1 para guardar; `grupos`, por
    ranura llena, los actores del grupo guardado, que ponen el nombre del
    primero y las caras de hasta CARAS_MAX.

    Se arma con **los mismos bloques de celdas que la ROM sube**, no volviendo a
    dibujar el texto ni pegando la cara: si se dibujara acá con la fuente y
    allá con los tiles, quedaría afuera justo el paso que puede salir mal.
    """
    from PIL import Image
    grupos = grupos or {}
    actores = sorted({a for g in grupos.values() for a in g})
    tiles, paletas, cabeceras, filas, caras, nombres = pantalla_ranuras(
        sys_img, db, ranuras, font_id, actores, game_dir)
    fuera = Image.new("RGB", (ANCHO, ALTO), (0, 0, 0))
    px = fuera.load()

    def pegar(celdas, fila0, col0=0, cols=COLS):
        for i, palabra in enumerate(celdas):
            tx = (col0 + i % cols) * CELL
            ty = (fila0 + i // cols) * CELL
            celda = tiles[palabra & 0x3FF]
            paleta = paletas[(palabra >> 10) & 7]
            for y in range(CELL):
                if ty + y >= ALTO:
                    break
                for x in range(CELL):
                    valor = celda[y][x]
                    if valor:
                        px[tx + x, ty + y] = tuple(v << 3 for v in paleta[valor])

    pegar(cabeceras[modo], CABECERA_Y // CELL)
    for numero in range(ranuras):
        fila0 = (RANURA_Y + numero * RANURA_SALTO) // CELL
        llena = bool(llenas[numero]) or numero in grupos
        pegar(filas[numero][1 if llena else 0][
            1 if numero == elegida else 0], fila0)
        if not llena:
            continue
        grupo = list(grupos.get(numero, ()))
        # El nombre del líder y las caras, como la ROM: los bloques del actor
        # encima de la fila. Un actor sin cara no dibuja nada, que es lo que
        # hace `DrawFace` con un nombre vacío.
        if grupo and grupo[0] in nombres:
            pegar(nombres[grupo[0]], fila0 + NOMBRE_FILA, NOMBRE_COL,
                  NOMBRE_COLS)
        for lugar, actor in enumerate(grupo[:CARAS_MAX]):
            if actor in caras:
                pegar(caras[actor], fila0, CARA_COL + lugar * CARA_PASO,
                      CARA_CELDAS)
    return fuera


if __name__ == "__main__":
    main()

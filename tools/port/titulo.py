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

import numpy

from port import asignador
from port import experiencia
from port import fuente
from port.constantes import ALTO, ANCHO, CELL, COLS, FILAS, MENU_CGRAM
from port.paleta import NEGRO, convertir
from port.reglas import nivel_de, parametro_de


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
    from port import ventana as ventana_mod
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
# **El texto que no depende de la partida está pre-renderizado**, incluidas
# las dos variantes de cada ranura —vacía y ocupada— y el término del nivel.
# Lo que sí depende de ella —el nombre del líder y su nivel— se compone de a
# una letra por celda con glifos sueltos, como los dígitos del cronómetro; ver
# "lo que depende del actor" acá abajo. Hasta el 2026-09-20 se horneaba
# también, con un bloque por actor, y eso hacía que el banco creciera con cada
# actor que pudiera estar en el grupo.
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
# El nombre del líder, en la segunda línea: siete celdas de ancho, desde el
# borde del texto hasta donde arranca la primera cara.
NOMBRE_COL = RANURA_X // CELL   # 7
NOMBRE_COLS = CARA_COL - NOMBRE_COL     # 7
NOMBRE_FILA = LINEA // CELL     # 2: la segunda línea arranca en y+16
# Y la tercera línea, el nivel: las dos cifras que van detrás del término
# "L ", que sí se hornea porque es el mismo para todos.
NIVEL_FILA = 2 * LINEA // CELL  # 4
NIVEL_CIFRAS = 2                # "%2d", que es lo que muestra RM2k
# En qué celda arranca el número: la que sigue al término, que mide dos
# caracteres de la fuente. No es `RANURA_X + 12` redondeado a mano porque el
# término sale del LDB y su ancho es el de la fuente.
NIVEL_COL = (RANURA_X + 2 * fuente.ANCHO) // CELL       # 8
# Y con qué paleta van las caras: la 0 es del texto, y cada cara lleva la suya
# desde la 1. Son las paletas de BG2 a 4bpp, que en la consola son ocho.
CARAS_PALETAS_MAX = 7
# Cuántos tiles entran en el banco de la pantalla: el conversor lo comprueba
# contra el reparto de VRAM, ver RANURA_MAP allá.
RANURA_TILES_MAX = 448

# --- lo que depende del actor, compuesto con glifos ---------------------------
#
# El nombre, el nivel y los HP máximos **se componen de a una letra por celda**
# y no se hornean en un bloque por actor. El porqué es que el banco es uno
# solo y está deduplicado: horneados, el texto de cada actor sumaba unos siete
# tiles que no comparte con nadie, así que el banco crecía con cada actor que
# pudiera estar en el grupo y el juego entero no entraba. Con glifos el texto
# cuesta una vez —las letras que los nombres usan— y lo único que sigue
# creciendo por actor son las caras.
#
# Es lo mismo que ya hacen los dígitos del oro, los HP de ahora y la pantalla
# de ítems. El precio es el mismo que pagan ellos y está declarado: las letras
# van a 8 pixeles de paso y no a los 6 de la fuente, así que el texto que
# depende del actor sale un poco más ancho que antes. Lo que no depende de él
# —"File 1", "- Empty -", el término del nivel, "Normal", "HP"— se sigue
# horneando con la fuente, o sea que sale igual que siempre.
#
# Los glifos se dibujan **en la misma celda y con el mismo corrimiento que los
# dígitos del oro** —uno en x, dos en y—, así que las diez cifras salen de acá
# y la pantalla no lleva dos juegos de dígitos.
GLIFO_COL = 3                   # la columna donde se dibuja el glifo suelto
GLIFO_FILA = 25                 # y su fila; las dos son cualesquiera
GLIFO_DX = 1                    # centrado en la celda: 6 px de fuente en 8
GLIFO_DY = 2


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
    """Las dos primeras líneas de una ranura, con los términos del juego. La
    segunda de una ranura llena es el nombre del líder, que va aparte porque
    depende de la partida; la tercera es el nivel, que se escribe en dos
    colores y también va aparte."""
    if not llena:
        return ["%s %d" % (db.term_file, numero + 1), VACIA]
    return ["%s %d" % (db.term_file, numero + 1), ""]


def _escribir_termino_nivel(destino, sys_img, x, y, db, font_id):
    """El término del nivel, como `Window_SaveFile::Refresh`: `lvl_short`
    completado a dos caracteres y en el color 1 del sistema. En el ABL es "L ".
    Los puntos de vida que RM2k pone al lado no van: este port no los tiene.

    Está copiado de la captura de EasyRPG del 2026-09-10, no del código solo.

    **El número no va acá**: lo compone la ROM con glifos, porque es lo único
    de esta línea que depende del actor —con Kersh de líder dice 20 y con Core
    15—. El término sí se hornea, que es el mismo para todos.
    """
    from port import ventana as ventana_mod
    ventana_mod.dibujar_linea(destino, sys_img, x, y,
                              (db.term_lvl_short or "")[:2].ljust(2), color=1,
                              font_id=font_id)


def texto_de_nombre(db, actor, cols=None):
    """El nombre del actor como la ROM lo compone: una letra por celda, con
    las que la fuente no tiene vueltas '?' y rellenado con espacios.

    El relleno no es adorno: la ROM escribe siempre las mismas celdas, así
    que lo que sobra a la derecha tiene que borrar lo que hubiera."""
    cols = MENU_NOMBRE_COLS if cols is None else cols
    nombre = db.actors[actor].name if actor in db.actors else ""
    return texto_de_item(nombre, cols).ljust(cols)


def texto_de_nivel(db, actor, nivel=None):
    """Las dos cifras del nivel, como las dice RM2k: alineadas a la derecha.
    Sin `nivel`, el de arranque; la ROM compone el de ahora con lo mismo,
    `texto_nivel`."""
    if nivel is None:
        nivel = nivel_de(db.actors[actor]) if actor in db.actors else 0
    return ("%*d" % (NIVEL_CIFRAS, nivel))[-NIVEL_CIFRAS:]


def texto_de_maximo(db, actor, nivel=None):
    """Los HP máximos del actor detrás de su barra: "/168". Van al lado de los
    HP de ahora, que la ROM escribe con los mismos glifos. Sin `nivel`, los
    del de arranque; la ROM compone los del de ahora, `texto_maximo`."""
    maximo = (parametro_de(db.actors[actor], "maxhp", nivel)
              if actor in db.actors else 0)
    return ("/%d" % maximo).ljust(MENU_MAX_CIFRAS)[:MENU_MAX_CIFRAS]


def texto_de_exp(db, actor, nivel=None, exp=None):
    """La experiencia como la escribe `DrawActorExp`: `"%6d/%6d"`, la de ahora
    y la que pide el nivel que sigue —`GetNextExp`—, o guiones en el tope.
    Sin `nivel` ni `exp`, los de arranque, como `texto_de_nivel`."""
    a = db.actors[actor]
    if nivel is None:
        nivel = experiencia.nivel_inicial(a)
    if exp is None:
        exp = experiencia.exp_inicial(a)
    siguiente = experiencia.siguiente(a, nivel)
    if siguiente == -1:
        return "-" * MENU_EXP_CIFRAS + "/" + "-" * MENU_EXP_CIFRAS
    return "%*d/%*d" % (MENU_EXP_CIFRAS, exp, MENU_EXP_CIFRAS, siguiente)


def glifos_de(db, actores, otras=""):
    """Qué letras necesita el banco: las de lo que se compone, más las diez
    cifras, que van siempre porque el oro y los HP de ahora las usan, y las
    de `otras` —los nombres de las medicinas, que escribe la elección de
    actor: ver `OBJETIVO_VENTANAS`—.

    Sale de los textos mismos y no de un alfabeto escrito a mano: un cartucho
    con tres actores no paga las letras de los otros."""
    letras = set("0123456789 ") | set(otras)
    letras |= set("/-")         # los de la experiencia, que los tiene siempre
    for actor in actores:
        letras |= set(texto_de_nombre(db, actor) + texto_de_nivel(db, actor)
                      + texto_de_maximo(db, actor))
    return sorted(letras)


def cara_de(db, actor, game_dir):
    """La cara del actor, 48x48 en RGBA, o None si no tiene.

    Va por `render_map.load_image` y no por `Image.open`, como el skin: en
    RM2k el índice 0 de la paleta es transparente también en un FaceSet, y en
    `ABLFaces` es un rojo que ocupa casi toda la cara. Dibujado opaco, cada
    cara era un cuadrado rojo con un muñeco adentro.
    """
    import os
    from render import render_map
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
    4bpp entran 15. El índice 0 es el transparente, y el negro va ahí: sobre el
    fondo negro de la pantalla da lo mismo y no gasta una entrada.

    La reducción es `asignador.merge_least_visible` y **no** `reducir`, que es lo
    que usa la imagen del título. `reducir` se queda con los quince colores más
    usados y manda el resto al más cercano, y en 48x48 píxeles eso arrasa: en
    una cara hay un puñado de tonos de piel que cubren casi todo y una docena de
    detalles de dos o tres píxeles cada uno —el brillo de un ojo, el filo de un
    mechón—, así que los quince ganadores eran quince variantes del mismo tono y
    la cara quedaba plana. taro lo reportó como "Talan y Core se ven grises".

    En el título la diferencia no existe —son 240 colores de 369, y los que se
    fusionan casi no aparecen— y cuesta el cuadrático, así que allá sigue
    `reducir`.
    """
    pixeles_de_cara = [(r >> 3, g >> 3, b >> 3) if a else NEGRO
                       for r, g, b, a in cara.get_flattened_data()]
    usados = collections.Counter(p for p in pixeles_de_cara if p != NEGRO)
    if len(usados) > 15:
        mapa = asignador.merge_least_visible(usados, 15)[0]
        paleta = sorted(set(mapa.values()))
        destino = mapa
    else:
        paleta = sorted(usados, key=lambda c: (-usados[c], c))
        destino = {c: c for c in usados}
    colores = [NEGRO] + list(paleta)
    indice = {NEGRO: 0}
    for color, a_donde in destino.items():
        indice[color] = colores.index(a_donde)
    return colores, indice


def _cara_prestada(colores, indice_cara, paletas):
    """A qué paleta de las que ya hay se cuelga una cara que no consiguió la
    suya, y de cada color de la cara a qué índice de esa paleta va.

    Se elige la paleta a la que menos colores le faltan —contando colores
    distintos y no píxeles, que es lo que se puede saber acá sin volver a
    recorrer la imagen— y cada color va al más cercano por luma, que es
    exactamente lo que hace `cabe` en el conversor con los sprites.

    Las dos primeras paletas son las del texto y no se tocan: pintarle la cara
    encima al texto lo dejaría ilegible, que es peor que una cara con el tono
    cambiado.
    """
    candidatas = list(range(2, len(paletas)))
    cual = min(candidatas,
               key=lambda n: (sum(1 for c in colores if c not in paletas[n]), n))
    destino = paletas[cual]
    donde = {}
    for color in colores:
        if color in destino:
            donde[color] = destino.index(color)
        else:
            donde[color] = destino.index(
                min(destino, key=lambda p, c=color: (
                    asignador.luma_distance(p, c), p)))
    return cual, {c: donde[colores[k]] for c, k in indice_cara.items()}


# --- el menú de pausa ---------------------------------------------------------
#
# Es `Scene_Menu` de RM2k en 256x224 y no en 320x240, así que la geometría es
# nuestra y no la de allá: la columna de órdenes a la izquierda, el oro abajo
# a la izquierda y el grupo a la derecha, **sin las ventanas** —fondo negro,
# como la pantalla de ranuras— y sin lo que no entra: el título del actor, la
# experiencia y los SP. Del grupo se ve la cara, el nombre, el nivel, el
# estado y los HP. Es cosmético y está declarado: se ve bien o no se ve bien,
# y eso lo dice taro jugando.
#
# Vive en el **mismo banco de tiles y la misma paleta** que la pantalla de
# ranuras: las caras son las mismas, y la pantalla de guardar se abre desde
# el menú. Todo va alineado a celdas de 8 para que los bloques valgan en
# cualquier fila.
MENU_OPCIONES = 5
MENU_OPC_Y = 8                  # la primera orden, en pixeles
MENU_OPC_SALTO = 16             # y cada cuánto va la siguiente
MENU_OPC_COL = 3                # el texto de la orden, x = 24
MENU_OPC_COLS = 9               # hasta x = 96, donde empieza el grupo
MENU_CURSOR_COL = 1             # el ">", x = 8
# Qué órdenes hacen algo. Las otras se dibujan en el color de "no se puede",
# que es el 3 del sistema, como RM2k dibuja "Save" cuando está prohibido: hoy
# es sólo técnicas. Usar ítems abre la pantalla de ítems desde el 2026-09-11.
# La 3, guardar, depende de `ChangeSaveAccess`. La 4, End Game, abre la
# pantalla de fin_del_juego.py desde el 2026-09-28: hasta ahí iba en gris
# porque "terminar el juego pide volver al título sin reiniciar el SPC700", y
# eso dejó de hacer falta cuando el Game Over empezó a volver al título con un
# reinicio.
MENU_ITEMS = 0
MENU_EQUIPO = 2
MENU_GUARDAR = 3
MENU_FIN = 4
MENU_HECHAS = (MENU_ITEMS, MENU_EQUIPO, MENU_GUARDAR, MENU_FIN)
# El oro, abajo a la izquierda: hasta seis cifras **de a una celda cada una**
# —no a los 6 pixeles de la fuente, para que la ROM las escriba de a una sin
# rearmar tiles— y el término de la moneda detrás, en el color 1.
MENU_ORO_Y = 200
MENU_ORO_COL = 3
MENU_ORO_CIFRAS = 6
MENU_MONEDA_COL = MENU_ORO_COL + MENU_ORO_CIFRAS    # 9, x = 72
MENU_MONEDA_COLS = 3
# El grupo: una fila de siete celdas por actor, con la cara a la izquierda y
# el texto al lado. Cuatro filas son 224 pixeles justos.
MENU_ACTOR_COL = 12             # x = 96
MENU_ACTOR_COLS = COLS - MENU_ACTOR_COL
MENU_ACTOR_FILAS = 7
MENU_TEXTO_X = MENU_ACTOR_COL * CELL + CARA + 8     # 152
MENU_ESTADO_DX = 42             # "Normal" va a 42 del nivel, como en RM2k
MENU_FILAS_GRUPO = 4
# Los HP de ahora: tres cifras **de a una celda cada una**, por lo mismo que
# el oro —que la ROM las escriba de a una sin rearmar tiles—. Van en la
# tercera línea de la fila del actor, o sea las filas 4 y 5 del bloque, que es
# donde las cifras del oro caen alineadas: las dos se dibujan a dos pixeles
# del borde de arriba de su celda. El máximo va detrás, con la barra, y ése sí
# se hornea: no cambia nunca.
MENU_HP_CIFRAS = 3              # ningún actor del juego pasa de 999
MENU_HP_COL = 21                # x = 168, pegado al "HP" de la izquierda
MENU_HP_FILA = 4                # la tercera línea, adentro del bloque
MENU_MAX_X = (MENU_HP_COL + MENU_HP_CIFRAS) * CELL      # 192
# Y dónde caen, adentro de la fila del actor, las tres tiras que dependen de
# él y que la ROM compone con glifos: el nombre en la primera línea, las dos
# cifras del nivel detrás del término en la segunda, y el máximo detrás de los
# HP de ahora en la tercera. Ver "lo que depende del actor" allá arriba.
MENU_NOMBRE_COL = MENU_TEXTO_X // CELL                  # 19
MENU_NOMBRE_COLS = COLS - MENU_NOMBRE_COL               # 13
MENU_NOMBRE_FILA = 0
MENU_NIVEL_COL = (MENU_TEXTO_X + 2 * fuente.ANCHO) // CELL      # 20
MENU_NIVEL_FILA = LINEA // CELL                         # 2
MENU_MAX_COL = MENU_MAX_X // CELL                       # 24
MENU_MAX_CIFRAS = 4             # la barra y hasta tres cifras: "/168"
# La experiencia, que es la tercera línea de `Window_MenuStatus`: el término
# —"Ex" en el ABL— en el color 1, y a doce pixeles la de ahora y la del nivel
# que sigue, en seis cifras cada una con la barra en el medio, `"%6d/%6d"`
# como `DrawActorExp`. Con el nivel en el tope las dos son guiones, que es lo
# que el comentario de easyrpg dice que hace el RPG_RT.
#
# **Va en sprites, no en el tilemap**, y es la única línea de esta pantalla
# que no está en la grilla. No entraba en ningún otro lado: RM2k pone los HP a
# la derecha del nivel y la experiencia debajo, en dos columnas que en 256
# pixeles no caben, y una cuarta línea de celdas no cabe en los 56 pixeles de
# la fila. En sprites va donde haga falta: doce pixeles debajo de los HP, que
# es el paso de la fuente, y a los seis pixeles de la fuente y no a los ocho
# de las celdas —a ocho, las trece letras se salían de la pantalla—. Los
# tiles son los glifos del banco mismo: los sprites leen la VRAM desde
# `RANURA_VRAM`, así que el tile de un glifo es el mismo número.
#
# Doce y no dieciséis pixeles debajo de los HP deja un pixel de aire arriba y
# dos abajo, y en la cuarta fila la sombra de las cifras cae justo en la
# última línea de la pantalla.
MENU_EXP_X = MENU_TEXTO_X
MENU_EXP_Y = 2 + 2 * LINEA + 11         # donde arranca la letra, en la fila
MENU_EXP_NUM_DX = 12
MENU_EXP_CIFRAS = 6
MENU_EXP_LETRAS = 2 * MENU_EXP_CIFRAS + 1
MENU_EXP_TERM_CELDAS = 2        # "Ex": doce pixeles, en dos celdas de ancho


# --- la pantalla de ítems -----------------------------------------------------
#
# `Scene_Item`: arriba la descripción del ítem marcado y abajo la lista del
# inventario con cuántos hay. En RM2k la lista va en dos columnas de 144
# pixeles; acá no entran y va en **una**, con la cantidad a la derecha, y la
# descripción se parte en dos renglones.
#
# El texto no va ya dibujado sino **de a una letra por celda**: la pantalla
# lleva su propio banco de tiles con cada carácter de la fuente en dos celdas
# —blanco y gris—, y nombres y descripciones van como texto en la ROM, que
# escribe dos palabras del tilemap por letra. El primer intento dibujaba el
# texto de cada ítem en el banco compartido con las ranuras y el menú, y con
# una docena de ítems ya no entraba: cuatro ROMs de la tanda dejaron de
# armarse. Así el costo no depende de cuántos ítems haya, y el precio es que
# las letras van a 8 pixeles y no a los 6 de la fuente, como las cifras del
# oro del menú. Es cosmético y está declarado.
ITEM_DESC_Y = 8
ITEM_DESC_COL = 1
ITEM_DESC_ANCHO = 30            # letras por renglón, una por celda
ITEM_DESC_RENGLONES = 2
# La lista arranca una celda más abajo y tiene una fila menos que hasta el
# 2026-09-28, cuando llegaron las ventanas —ver `ITEM_VENTANAS`—: con once
# filas desde el 48 la última tocaba el marco de abajo, y la de arriba quedaba
# pegada al de la ventana. Así las dos ventanas dejan el mismo aire que RM2k.
ITEM_LISTA_Y = 56
ITEM_FILAS = 10                 # 56 + 10 * 16 = 216, y el marco en 222
ITEM_CURSOR_COL = 1
ITEM_NOMBRE_COL = 3             # x = 24, como las órdenes del menú
ITEM_NOMBRE_ANCHO = 20          # el nombre más largo del juego
ITEM_DOS_PUNTOS_COL = 27
ITEM_CIFRAS_COL = 28            # dos cifras, 28 y 29
ITEM_PRIMER_CARACTER = 32       # los que tiene la fuente: del espacio
ITEM_CARACTERES = 95            # a la tilde, que es lo que usan los ítems
# Las variantes de la fuente: el índice es lo que la ROM lleva en `temp + 1`,
# y también su paleta. La 2 es el color 2 del sistema, el de "sube" de
# `Window_EquipStatus`, y la usa sólo la pantalla de equipo para el valor
# nuevo de un parámetro, así que trae **sólo las cifras**: la fuente entera en
# un color más eran unos 150 tiles, y el banco de la pelea no los tiene —ver
# `ITEMS_TILES_MAX`—. La 3 es el color 1, el rojo de los términos de
# `Window_EquipStatus` y `Window_EquipLeft`, y ésa sí va **entera**: medido el
# 2026-09-28, la fuente en ese color son diez tiles más y no ciento y pico,
# porque los tiles se deduplican por índice y el degradé del rojo cae en los
# mismos índices que el del blanco. Sólo las letras de los términos eran
# treinta y cinco: con menos letras el orden de la paleta —por frecuencia— sale
# otro y ya no coincide.
ITEM_BLANCO, ITEM_GRIS, ITEM_SUBE, ITEM_ROJO = range(4)
ITEM_SUBE_CARACTERES = "0123456789 "
# Hasta dónde puede crecer el banco de la fuente: la pelea lo sube y después
# escribe el tilemap de su escena en la palabra $3800 de la VRAM, que es el
# tile 384 contando desde `RANURA_VRAM`. Lo que pase de ahí lo pisaría.
ITEMS_TILES_MAX = (0x3800 - 0x2000) // 16

# Las ventanas de la pantalla, como `Scene_Item`: la de la ayuda arriba y la
# de la lista abajo, cada una con el fondo estirado y el marco del System —
# `ventana.ventana`, la misma que la del mensaje—. RM2k las pega una contra
# la otra, así que el separador son los dos marcos juntos: cuatro pixeles.
# La de la ayuda es más alta que la de RM2k —32— porque acá la descripción va
# en dos renglones.
#
# Van en **BG1**, que en esta pantalla estaba apagado, y el texto sigue en
# BG2 como antes: así el texto no tiene que saber nada de las ventanas, y la
# descripción, que se sube de a filas enteras, no borra el marco. Los glifos
# ya llevan el bit de prioridad —ver `item_glifo_celdas` en el conversor—, así
# que el texto queda arriba de la franja del fondo que lo cruza, como en RM2k.
# En 8bpp un pixel es directamente su entrada de CGRAM: los colores del marco
# van desde `ITEM_MARCO_CGRAM`, después de las cuatro paletas del texto, y el
# negro es el 0, el transparente, que deja ver el color de fondo, que es
# negro.
ITEM_AYUDA_ALTO = 48
ITEM_VENTANAS = ((0, 0, ANCHO, ITEM_AYUDA_ALTO),
                 (0, ITEM_AYUDA_ALTO, ANCHO, ALTO - ITEM_AYUDA_ALTO))
ITEM_MARCO_CGRAM = 4 * MENU_CGRAM
# Los tiles del marco van en el banco de la fuente, detrás de ella: la base de
# BG1 es la misma que la de BG2, y un tile de 8bpp mide lo que dos de 4bpp.
# Todo tiene que caber antes del tilemap de BG1, que va en $3800 —donde la
# pelea pone el de su escena, así que ahí no hay nada de esta pantalla—.
ITEM_MARCO_MAPA = 0x3800
# El cursor de la lista es el del System —la barra roja de RM2k— y no el ">":
# cuatro pixeles más ancho que el texto de cada lado, que es lo que deja RM2k.
ITEM_BARRA_X = ITEM_NOMBRE_COL * CELL - 4
ITEM_BARRA_ANCHO = (ITEM_CIFRAS_COL + 2 - ITEM_NOMBRE_COL) * CELL + 8


def ventanas_items(sys_img, barra=None):
    """Las ventanas de la pantalla de ítems, en RGBA y del tamaño de la
    pantalla: lo que dibuja BG1. Con `barra`, el cursor en esa fila de la
    lista."""
    from PIL import Image
    from port import ventana as ventana_mod
    fuera = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    for x, y, ancho, alto in ITEM_VENTANAS:
        una = ventana_mod.ventana(sys_img, ancho, alto)
        fuera.paste(una, (x, y), una)
    if barra is not None:
        una = ventana_mod.cursor(sys_img, ITEM_BARRA_ANCHO, 2 * CELL)
        fuera.paste(una, (ITEM_BARRA_X, ITEM_LISTA_Y + 2 * CELL * barra), una)
    return fuera


def capas_items(sys_img):
    """Lo que `marcos` necesita de la pantalla de ítems: las ventanas sin
    cursor, y con el cursor en cada fila de la lista junto con la primera
    fila de celdas que ocupa."""
    return (ventanas_items(sys_img),
            [(ventanas_items(sys_img, k), ITEM_LISTA_Y // CELL + 2 * k)
             for k in range(ITEM_FILAS)])


def marcos(sys_img, primer_tile, pantallas, cgram=None, tope=256):
    """Las ventanas de varias pantallas como las sube la ROM: tiles de 8bpp,
    un tilemap de 32x28 por pantalla, sus cursores y los colores.

    `pantallas` es una lista de `(ventanas, barras)`, como las da
    `capas_items`: la imagen del tamaño de la pantalla sin cursor, y la de
    cada lugar del cursor con la primera fila de celdas que ocupa y, si no
    son dos, cuántas. Los tiles y
    los colores son **uno solo para todas**: las pantallas no están abiertas a
    la vez y suben sus tiles al mismo lugar de la VRAM, así que cada una sube
    el juego entero y el tilemap de cada una lo indexa igual.

    `primer_tile` es el número de tile de 8bpp del primero, contado desde la
    base de BG1. Devuelve `(tiles, colores, mapas)`: `tiles[i][y][x]` es la
    entrada de CGRAM de ese pixel; `colores` los de 15 bits desde `cgram`
    —`ITEM_MARCO_CGRAM` si no se dice—, que no pueden pasar de `tope`; y `mapas[p]` es `(mapa, barras)` de la pantalla `p`,
    con `mapa` las palabras del tilemap fila por fila y `barras[k]` las dos
    filas de celdas del cursor `k` con el cursor encima, que es lo que la ROM
    copia sobre `mapa` para pintarlo.

    Los tiles se deduplican también espejados, con los bits de volteo del
    tilemap: el marco es simétrico, y sin eso las ventanas y el cursor no
    entraban en lo que queda de VRAM —ver `_controlar_marco_de_items`—.
    """
    cgram = ITEM_MARCO_CGRAM if cgram is None else cgram
    imagenes = [imagen for fondo, barras in pantallas
                for imagen in [fondo] + [b[0] for b in barras]]
    cuenta = collections.Counter()
    for imagen in imagenes:
        pixeles = numpy.asarray(imagen).reshape(-1, 4)
        rgb = pixeles[pixeles[:, 3] != 0, :3].astype(numpy.int32) >> 3
        for r, g, b in rgb.tolist():
            if (r, g, b) != NEGRO:
                cuenta[(r, g, b)] += 1
    colores = sorted(cuenta, key=lambda c: (-cuenta[c], c))
    if cgram + len(colores) > tope:
        raise SystemExit("las ventanas usan %d colores y desde %d entran %d"
                         % (len(colores), cgram, tope - cgram))
    indice = {c: cgram + i for i, c in enumerate(colores)}
    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde = [vacio], {vacio: 0}

    def palabras(imagen, filas):
        px = imagen.load()
        salida = []
        for fila in filas:
            for col in range(COLS):
                celda = []
                for y in range(CELL):
                    renglon = []
                    for x in range(CELL):
                        r, g, b, a = px[col * CELL + x, fila * CELL + y]
                        color = (r >> 3, g >> 3, b >> 3)
                        renglon.append(indice[color]
                                       if a and color != NEGRO else 0)
                    celda.append(tuple(renglon))
                celda = tuple(celda)
                h = tuple(tuple(reversed(r)) for r in celda)
                for volteo, forma in ((0, celda), (0x4000, h),
                                      (0x8000, tuple(reversed(celda))),
                                      (0xC000, tuple(reversed(h)))):
                    if forma in donde:
                        salida.append((primer_tile + donde[forma]) | volteo)
                        break
                else:
                    donde[celda] = len(tiles)
                    tiles.append(celda)
                    salida.append(primer_tile + donde[celda])
        return salida

    mapas = []
    for fondo, barras in pantallas:
        mapas.append((palabras(fondo, range(FILAS)),
                      [palabras(b[0], range(b[1], b[1] + (b[2] if len(b) > 2
                                                         else 2)))
                       for b in barras]))
    return tiles, colores, mapas


def item_usable(item):
    """Si el ítem va en blanco y A hace algo con él en el mapa: es
    `Game_Party::IsItemUsable` fuera de batalla. Los de switch con
    `occasion_field2`, y las medicinas, que abren la elección de actor. Los
    libros, los materiales y los especiales todavía no: van en gris."""
    from rpgmaker import lcf
    return ((item.type == lcf.ITEM_TIPO_SWITCH and item.occasion_field2)
            or item.type == lcf.ITEM_TIPO_MEDICINA)


def item_pide_actor(item):
    """Si usarlo abre `Scene_ActorTarget`: las medicinas."""
    from rpgmaker import lcf
    return item.type == lcf.ITEM_TIPO_MEDICINA


def texto_de_item(texto, ancho):
    """Lo que la pantalla puede escribir: los caracteres que la fuente tiene,
    con un '?' en lugar de los otros, y cortado al ancho."""
    return "".join(c if ITEM_PRIMER_CARACTER <= ord(c)
                   < ITEM_PRIMER_CARACTER + ITEM_CARACTERES else "?"
                   for c in texto)[:ancho]


def partir_descripcion(texto, ancho=ITEM_DESC_ANCHO):
    """La descripción en dos renglones, cortada en un espacio. Lo que no
    entra en dos se pierde."""
    renglones, actual = [], ""
    for palabra in texto.split(" "):
        candidato = (actual + " " + palabra) if actual else palabra
        if len(candidato) <= ancho:
            actual = candidato
            continue
        renglones.append(actual)
        actual = palabra[:ancho]
    renglones.append(actual)
    renglones = [texto_de_item(r, ancho) for r in renglones]
    return (renglones + ["", ""])[:ITEM_DESC_RENGLONES]


def lista_de_items(items, inventario):
    """Los ítems que muestra la pantalla, en orden de número como
    `Game_Party`: los que hay y que la ROM conoce."""
    return [i for i in sorted(items) if inventario.get(i, 0) > 0]


def pantalla_items(sys_img, font_id=None):
    """El banco de la pantalla de ítems: cada carácter de la fuente en dos
    celdas, una arriba de la otra, en blanco, en gris y en rojo, y las cifras
    además en el color de "sube" —ver `ITEM_SUBE`—.

    Devuelve `(tiles, paletas, glifos)`: `paletas[v]` y `glifos[v][caracter]`
    —las dos palabras del tilemap— por variante: 0 el texto, 1 el gris, 2 el
    de "sube", que sólo tiene `ITEM_SUBE_CARACTERES`, y 3 el rojo. El espacio
    son dos celdas en blanco: es el que borra el cursor.
    """
    from PIL import Image
    from port import ventana as ventana_mod
    colores = {ITEM_BLANCO: 0, ITEM_GRIS: 3, ITEM_SUBE: 2, ITEM_ROJO: 1}
    capas = []
    for gris in (ITEM_BLANCO, ITEM_GRIS, ITEM_SUBE, ITEM_ROJO):
        for n in range(ITEM_CARACTERES):
            c = chr(ITEM_PRIMER_CARACTER + n)
            if gris == ITEM_SUBE and c not in ITEM_SUBE_CARACTERES:
                continue
            una = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
            ventana_mod.dibujar_linea(una, sys_img, 1, 2, c,
                                      color=colores[gris], font_id=font_id)
            capas.append((gris, n, una))
    # Los colores de cada juego, con numpy: es una imagen del tamaño de la
    # pantalla por carácter y por color, con la letra en una esquina, y
    # recorrerlas pixel por pixel era casi todo lo que costaba esta pantalla.
    # El orden en que se cuentan no importa: la paleta sale ordenada.
    vistos = [collections.Counter() for _ in colores]
    for gris, _, una in capas:
        pixeles = numpy.asarray(una).reshape(-1, 4)
        rgb = pixeles[pixeles[:, 3] != 0, :3].astype(numpy.int32) >> 3
        codigos, cuantos = numpy.unique(
            (rgb[:, 0] << 10) | (rgb[:, 1] << 5) | rgb[:, 2],
            return_counts=True)
        for c, k in zip(codigos.tolist(), cuantos.tolist()):
            vistos[gris][(c >> 10, (c >> 5) & 31, c & 31)] += k
    paletas, indices = [], []
    for cuenta in vistos:
        if len(cuenta) > 15:
            raise SystemExit("la fuente de la pantalla de ítems usa %d colores "
                             "y en 4bpp entran 15" % len(cuenta))
        paleta = [NEGRO] + sorted(cuenta, key=lambda c: (-cuenta[c], c))
        paletas.append(paleta)
        indices.append({color: i for i, color in enumerate(paleta)})
    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde = [vacio], {vacio: 0}
    glifos = [{} for _ in colores]
    for gris, n, una in capas:
        glifos[gris][chr(ITEM_PRIMER_CARACTER + n)] = _bloque_de_celdas(
            una, 0, 2, tiles, donde, indices[gris], 0, 1, gris)
    if len(tiles) > ITEMS_TILES_MAX:
        raise SystemExit("la fuente de la pantalla de ítems junta %d tiles y "
                         "en su banco entran %d" % (len(tiles),
                                                    ITEMS_TILES_MAX))
    return tiles, paletas, glifos


def _escribir_menu_fila(destino, sys_img, db, font_id):
    """El texto de una fila del grupo que **no depende del actor**: el término
    del nivel, el estado y el de los HP.

    Es un bloque solo para las cuatro filas y para todos los actores, y ésa es
    la diferencia con antes: el nombre, el número del nivel y el máximo —lo
    único que cambiaba de un actor a otro— los compone la ROM con glifos, así
    que este bloque no se multiplica por la cantidad de actores.

    Los HP de ahora tampoco van acá, y ése es el arreglo del 2026-09-13: este
    bloque se hornea al convertir y se sube tal cual, así que el número que
    llevara adentro no podía cambiar nunca. taro lo reportó jugando —"el hp se
    reduce en batalla, pero en el menú siempre se muestra en 40"—; los 40 son
    el máximo de Talan, que es quien lidera la intro.
    """
    from port import ventana as ventana_mod

    def escribir(x, y, texto, color=0):
        return ventana_mod.dibujar_linea(destino, sys_img, x, y, texto,
                                         color=color, font_id=font_id)

    _escribir_termino_nivel(destino, sys_img, MENU_TEXTO_X, 2 + LINEA, db,
                            font_id)
    escribir(MENU_TEXTO_X + MENU_ESTADO_DX, 2 + LINEA, db.term_normal_status)
    escribir(MENU_TEXTO_X, 2 + 2 * LINEA, db.term_hp_short, color=1)


def cifras_de(valor, cuantas):
    """Las cifras de un número topado a `cuantas`, sin ceros adelante.

    Es `cifras_del_oro` generalizada: la usan el oro del menú y los HP de cada
    actor, que la ROM escribe con los mismos bloques de una celda.
    """
    return [int(c) for c in str(max(0, min(valor, 10 ** cuantas - 1)))]


def hp_de_menu(db, actor, hp=None):
    """Los HP que la fila del actor tiene que mostrar: los de `hp` si están,
    y si no los máximos de su nivel, que es con lo que arranca la partida."""
    if hp is not None and actor in hp:
        return hp[actor]
    return parametro_de(db.actors[actor], "maxhp")


def _pegar_hp(pegar, menu, fila, cuanto):
    """Las cifras de los HP de una fila del grupo, alineadas a la derecha.

    Es lo que la ROM hace en `menu_hp_escribir`, con las mismas celdas y en
    las mismas columnas; lo que sobra a la izquierda queda en blanco.
    """
    cifras = cifras_de(cuanto, MENU_HP_CIFRAS)
    _pegar_texto(pegar, menu, "".join(str(c) for c in cifras),
                 fila * MENU_ACTOR_FILAS + MENU_HP_FILA,
                 MENU_HP_COL + MENU_HP_CIFRAS - len(cifras))


def cifras_del_oro(oro):
    """Las cifras que se escriben, sin ceros adelante: el 0 es "0"."""
    return cifras_de(oro, MENU_ORO_CIFRAS)


def pantalla_ranuras(sys_img, db, ranuras, font_id=None, actores=(),
                     game_dir=None, letras=""):
    """Los tiles de la pantalla de ranuras, sus paletas y sus bloques de celdas.

    Devuelve `(tiles, paletas, cabeceras, filas, caras, menu)`:

    * `paletas[0]` es la del texto, `paletas[1]` la de las órdenes
      deshabilitadas del menú, y las que siguen, una por cara.
    * `cabeceras[modo]` son las celdas del título de la pantalla, con `modo` 0
      para cargar y 1 para guardar. Los dos textos salen del LDB
      —`load_game_message` y `save_game_message`, que en el ABL dicen "Load
      which slot?" y "Save in which slot?"—.
    * `filas[ranura][llena][cursor]` son las celdas de una fila entera, con
      las celdas de las caras, del nombre y del nivel en blanco.
    * `caras[actor]` son las 36 celdas de la cara, con su paleta puesta, para
      los `actores` que tienen una. La ROM la escribe encima de la fila según
      el grupo que la partida guardó, y `render_ranuras` hace lo mismo.

    * `menu` son los bloques del menú de pausa, que comparte banco y paleta:
      `opciones[orden][deshabilitada]`, `cursor`, `moneda`, `fila` —el texto
      de una fila del grupo, uno solo para todas— y `glifos[letra]`, las dos
      celdas de cada letra que la ROM compone. Las diez cifras están ahí: son
      las que escriben el oro y los HP.

    Todas las variantes se dibujan antes de deduplicar, por lo mismo de siempre:
    el banco de tiles es uno solo.
    """
    from PIL import Image
    from port import ventana as ventana_mod

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
                if llena:
                    # El término del nivel va en la fila y no en la capa del
                    # actor: es el mismo para todos, y una ranura sin partida
                    # no lo muestra.
                    _escribir_termino_nivel(una, sys_img, RANURA_X,
                                            y + 2 + 2 * LINEA, db, font_id)
                capas.append(("fila", (numero, llena, cursor), una))
    # Las del menú de pausa, en el mismo banco. Todas en la fila de más arriba
    # que les toca: los bloques valen en cualquier otra porque van alineados.
    from port import ventana as ventana_mod
    for orden, texto in enumerate(db.term_menu):
        for deshabilitada in (0, 1):
            una = capa()
            ventana_mod.dibujar_linea(
                una, sys_img, MENU_OPC_COL * CELL,
                MENU_OPC_Y + orden * MENU_OPC_SALTO + 2, texto,
                color=3 if deshabilitada else 0, font_id=font_id)
            capas.append(("menu_opcion", (orden, deshabilitada), una))
    una = capa()
    escribir(una, MENU_CURSOR_COL * CELL, MENU_OPC_Y + 2, ">")
    capas.append(("menu_cursor", None, una))
    for letra in glifos_de(db, actores, letras):
        una = capa()
        escribir(una, GLIFO_COL * CELL + GLIFO_DX,
                 GLIFO_FILA * CELL + GLIFO_DY, letra)
        capas.append(("menu_glifo", letra, una))
    una = capa()
    ventana_mod.dibujar_linea(una, sys_img, MENU_MONEDA_COL * CELL,
                              MENU_ORO_Y + 2, db.term_gold, color=1,
                              font_id=font_id)
    capas.append(("menu_moneda", None, una))
    una = capa()
    _escribir_menu_fila(una, sys_img, db, font_id)
    capas.append(("menu_fila", None, una))
    # El término de la experiencia, suelto como un glifo: lo dibujan sprites.
    # Hasta dos letras, que son los doce pixeles que `DrawActorExp` le deja
    # antes de las cifras.
    una = capa()
    ventana_mod.dibujar_linea(una, sys_img, GLIFO_COL * CELL,
                              GLIFO_FILA * CELL + GLIFO_DY,
                              (db.term_exp_short or "")[:2], color=1,
                              font_id=font_id)
    capas.append(("menu_exp_termino", None, una))

    # Las órdenes deshabilitadas van en **su propia paleta**, la 1: el color 3
    # del sistema es un degradé que, sumado a los del texto, da 18 colores, y
    # en 4bpp entran 15. Le cuesta una paleta a las caras.
    def gris(clase, clave):
        return clase == "menu_opcion" and clave[1]

    vistos, vistos_gris = collections.Counter(), collections.Counter()
    for clase, clave, una in capas:
        cuenta = vistos_gris if gris(clase, clave) else vistos
        for r, g, b, a in una.get_flattened_data():
            if a:
                cuenta[(r >> 3, g >> 3, b >> 3)] += 1
    for cuantos, que in ((len(vistos), "el texto de las ranuras y el menú"),
                         (len(vistos_gris), "las órdenes deshabilitadas")):
        if cuantos > 15:
            raise SystemExit("%s usa %d colores y en 4bpp entran 15"
                             % (que, cuantos))
    paleta = [NEGRO] + sorted(vistos, key=lambda c: (-vistos[c], c))
    indice = {color: i for i, color in enumerate(paleta)}
    paleta_gris = [NEGRO] + sorted(vistos_gris,
                                   key=lambda c: (-vistos_gris[c], c))
    indice_gris = {color: i for i, color in enumerate(paleta_gris)}

    vacio = tuple(tuple([0] * CELL) for _ in range(CELL))
    tiles, donde = [vacio], {vacio: 0}
    cabeceras = [None, None]
    filas = [[[None, None], [None, None]] for _ in range(ranuras)]
    menu = {"opciones": [[None, None] for _ in range(MENU_OPCIONES)],
            "cursor": None, "glifos": {}, "moneda": None, "fila": None}
    for clase, clave, una in capas:
        if clase == "menu_opcion":
            orden, deshabilitada = clave
            menu["opciones"][orden][deshabilitada] = _bloque_de_celdas(
                una, (MENU_OPC_Y + orden * MENU_OPC_SALTO) // CELL, 2, tiles,
                donde, indice_gris if deshabilitada else indice,
                MENU_OPC_COL, MENU_OPC_COLS, 1 if deshabilitada else 0)
        elif clase == "menu_cursor":
            menu["cursor"] = _bloque_de_celdas(
                una, MENU_OPC_Y // CELL, 2, tiles, donde, indice,
                MENU_CURSOR_COL, 1)
        elif clase == "menu_glifo":
            menu["glifos"][clave] = _bloque_de_celdas(
                una, GLIFO_FILA, 2, tiles, donde, indice, GLIFO_COL, 1)
        elif clase == "menu_moneda":
            menu["moneda"] = _bloque_de_celdas(
                una, MENU_ORO_Y // CELL, 2, tiles, donde, indice,
                MENU_MONEDA_COL, MENU_MONEDA_COLS)
        elif clase == "menu_fila":
            menu["fila"] = _bloque_de_celdas(
                una, 0, MENU_ACTOR_FILAS, tiles, donde, indice,
                MENU_ACTOR_COL, MENU_ACTOR_COLS)
        elif clase == "menu_exp_termino":
            menu["exp_termino"] = _bloque_de_celdas(
                una, GLIFO_FILA, 2, tiles, donde, indice, GLIFO_COL,
                MENU_EXP_TERM_CELDAS)
        elif clase == "cabecera":
            cabeceras[clave] = _bloque_de_celdas(
                una, CABECERA_Y // CELL, CABECERA_FILAS, tiles, donde, indice)
        else:
            numero, llena, cursor = clave
            fila0 = (RANURA_Y + numero * RANURA_SALTO) // CELL
            filas[numero][llena][cursor] = _bloque_de_celdas(
                una, fila0, RANURA_FILAS, tiles, donde, indice)

    # Y las caras, cada una con su paleta, pegadas arriba a la izquierda de la
    # primera fila para cortarlas en celdas con la misma función.
    paletas, caras = [paleta, paleta_gris], {}
    # A qué caras hubo que prestarles paleta: sale en el informe del conversor,
    # igual que con los sprites.
    prestadas_cara = set()
    for actor in actores:
        cara = cara_de(db, actor, game_dir)
        if cara is None:
            continue
        colores, indice_cara = _paleta_de_cara(cara)
        if len(paletas) > CARAS_PALETAS_MAX:
            # No queda paleta de BG2: **se le presta una**, que es la misma
            # regla que `cabe` corre con los sprites y la misma razón de taro
            # —si no podemos incluir a todos, el proyecto entero se cae—. Cada
            # color de la cara va al más cercano por luma de la paleta que menos
            # le falte, y la cara se ve con colores que no son los suyos.
            #
            # Hizo falta al meter Lashe City entera: las caras son una paleta
            # cada una, quedan seis, y desde el mapa 20 pueden entrar al grupo
            # Arden, Saldra, el Gang Member de los Rat Tracks y AG7-17, o sea
            # ocho. La alternativa era dejar afuera los Rat Tracks B2 y toda la
            # cadena del auto, que son el camino de la historia.
            cual, indice_cara = _cara_prestada(colores, indice_cara, paletas)
            prestadas_cara.add(actor)
        else:
            cual = len(paletas)
            paletas.append(colores)
        una = capa()
        una.paste(cara, (CARA_COL * CELL, RANURA_Y))
        caras[actor] = _bloque_de_celdas(
            una, RANURA_Y // CELL, CARA_CELDAS, tiles, donde, indice_cara,
            CARA_COL, CARA_CELDAS, cual)
    if prestadas_cara:
        print("  caras sin paleta propia, dibujadas con una ajena: %s"
              % ", ".join(db.actors[a].name for a in sorted(prestadas_cara)))
    if len(tiles) > RANURA_TILES_MAX:
        raise SystemExit(
            "la pantalla de ranuras y el menú juntan %d tiles y en su banco "
            "entran %d" % (len(tiles), RANURA_TILES_MAX))
    return tiles, paletas, cabeceras, filas, caras, menu


def _pintor(fuera, tiles, paletas):
    """Una función que pega un bloque de celdas sobre `fuera`, como lo hace
    la ROM: tile y paleta de cada palabra del tilemap."""
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
    return pegar


def _pegar_sprite(fuera, tiles, paletas, palabra, x, y):
    """Un tile de 8x8 en cualquier pixel, como un sprite: lo transparente deja
    ver lo que había. La paleta es la de la palabra, que la ROM copia a la de
    los sprites."""
    px = fuera.load()
    celda = tiles[palabra & 0x3FF]
    paleta = paletas[(palabra >> 10) & 7]
    for dy in range(CELL):
        for dx in range(CELL):
            valor = celda[dy][dx]
            if valor and 0 <= x + dx < ANCHO and 0 <= y + dy < ALTO:
                px[x + dx, y + dy] = tuple(v << 3 for v in paleta[valor])


def _pegar_exp(fuera, tiles, paletas, menu, fila, texto):
    """La línea de la experiencia de una fila del grupo, en sprites: el
    término y las trece letras de `texto`, a seis pixeles. Es lo que hace
    `menu_exp_pintar` en la ROM; los espacios no llevan sprite."""
    y = fila * MENU_ACTOR_FILAS * CELL + MENU_EXP_Y - GLIFO_DY
    for n, palabra in enumerate(menu["exp_termino"]):
        _pegar_sprite(fuera, tiles, paletas, palabra,
                      MENU_EXP_X + (n % MENU_EXP_TERM_CELDAS) * CELL,
                      y + (n // MENU_EXP_TERM_CELDAS) * CELL)
    for n, letra in enumerate(texto):
        if letra == " ":
            continue
        x = MENU_EXP_X + MENU_EXP_NUM_DX + n * fuente.ANCHO - GLIFO_DX
        arriba, abajo = menu["glifos"][letra]
        _pegar_sprite(fuera, tiles, paletas, arriba, x, y)
        _pegar_sprite(fuera, tiles, paletas, abajo, x, y + CELL)


def _pegar_texto(pegar, menu, texto, fila, col):
    """Un texto compuesto de a una letra por celda, como lo escribe la ROM."""
    for n, letra in enumerate(texto):
        pegar(menu["glifos"][letra], fila, col + n, 1)


def _pegar_fila_de_actor(pegar, menu, caras, db, fila, actor, hp=None,
                         niveles=None):
    """Una fila del panel del grupo: el bloque fijo, la cara y las tres tiras
    que dependen del actor. Es lo que hace `menu_grupo_pintar`, en el mismo
    orden, y por eso lo comparten el menú y la elección de actor."""
    fila0 = fila * MENU_ACTOR_FILAS
    pegar(menu["fila"], fila0, MENU_ACTOR_COL, MENU_ACTOR_COLS)
    if actor in caras:
        pegar(caras[actor], fila0, MENU_ACTOR_COL, CARA_CELDAS)
    _pegar_texto(pegar, menu, texto_de_nombre(db, actor),
                 fila0 + MENU_NOMBRE_FILA, MENU_NOMBRE_COL)
    nivel = (niveles or {}).get(actor)
    _pegar_texto(pegar, menu, texto_de_nivel(db, actor, nivel),
                 fila0 + MENU_NIVEL_FILA, MENU_NIVEL_COL)
    _pegar_texto(pegar, menu, texto_de_maximo(db, actor, nivel),
                 fila0 + MENU_HP_FILA, MENU_MAX_COL)
    _pegar_hp(pegar, menu, fila, hp_de_menu(db, actor, hp))


def render_menu(sys_img, db, ranuras, grupo, oro, elegida=0,
                guardar_permitido=True, font_id=None, actores=None,
                game_dir=None, hp=None, niveles=None, exps=None):
    """El menú de pausa como lo tiene que mostrar la consola.

    `grupo` son los actores en orden, `oro` el oro, `elegida` la orden con el
    cursor y `guardar_permitido` lo que dejó `ChangeSaveAccess`. `actores` es
    la lista de la ROM —los que pueden entrar al grupo, `miembros_posibles`
    en el conversor—, que decide el banco de tiles; sin ella, el grupo.
    Se arma con los mismos bloques que sube la ROM, como `render_ranuras`.

    `hp` es lo que la partida tiene en `FAR_HP`, de actor a HP: sin ella se
    supone que están llenos, que es con lo que arranca. Va aparte del bloque
    del actor porque el bloque se hornea y esto cambia con cada pelea.
    `niveles`, de actor a nivel, es lo mismo para el nivel y el máximo: sin
    ella, los de arranque. `exps`, de actor a experiencia, lo mismo para la
    línea de la experiencia, que mira además el nivel.
    """
    from PIL import Image
    actores = sorted(set(actores if actores is not None else grupo))
    tiles, paletas, _, _, caras, menu = pantalla_ranuras(
        sys_img, db, ranuras, font_id, actores, game_dir)
    fuera = Image.new("RGB", (ANCHO, ALTO), (0, 0, 0))
    pegar = _pintor(fuera, tiles, paletas)
    for orden in range(MENU_OPCIONES):
        hecha = orden in MENU_HECHAS and (orden != MENU_GUARDAR
                                          or guardar_permitido)
        pegar(menu["opciones"][orden][0 if hecha else 1],
              (MENU_OPC_Y + orden * MENU_OPC_SALTO) // CELL, MENU_OPC_COL,
              MENU_OPC_COLS)
    pegar(menu["cursor"], (MENU_OPC_Y + elegida * MENU_OPC_SALTO) // CELL,
          MENU_CURSOR_COL, 1)
    cifras = cifras_del_oro(oro)
    _pegar_texto(pegar, menu, "".join(str(c) for c in cifras),
                 MENU_ORO_Y // CELL, MENU_MONEDA_COL - len(cifras))
    pegar(menu["moneda"], MENU_ORO_Y // CELL, MENU_MONEDA_COL,
          MENU_MONEDA_COLS)
    for fila, actor in enumerate(list(grupo)[:MENU_FILAS_GRUPO]):
        if actor in actores:
            _pegar_fila_de_actor(pegar, menu, caras, db, fila, actor, hp,
                                 niveles)
    # La experiencia va encima de todo, como los sprites sobre el fondo, y
    # sólo en el menú: `Window_ActorTarget` no la muestra.
    for fila, actor in enumerate(list(grupo)[:MENU_FILAS_GRUPO]):
        if actor in actores:
            _pegar_exp(fuera, tiles, paletas, menu, fila, texto_de_exp(
                db, actor, (niveles or {}).get(actor),
                (exps or {}).get(actor)))
    return fuera


# La elección de actor, `Scene_ActorTarget`: el panel del grupo del menú, y
# como en RM2k, tres ventanas del System en BG1 —como las de ítems y equipo,
# ver `ITEM_VENTANAS`— y la barra roja sobre la fila marcada. RM2k pone a la
# izquierda la ayuda con el nombre del ítem y debajo "Owned Items" en rojo con
# la cantidad, y a la derecha el grupo. Acá la columna de la izquierda llega
# hasta x = 104: las caras del banco miden 48 pero lo que se ve de ellas
# arranca doce pixeles adentro, en x = 108, así que la ventana del grupo
# puede empezar a la izquierda de la fila del menú (x = 96) sin taparlas. En
# 104 entran once letras de 8 pixeles, y el nombre va en dos renglones: once
# es lo que pide "Sandwich-HP".
#
# El nombre se escribe con los glifos del banco del menú —a una letra por
# celda, como el nombre del actor—, así que el banco lleva también las letras
# de las medicinas. "Owned Items" no: va **horneado en BG1**, en rojo y a los
# seis pixeles de la fuente, porque a ocho sus once letras llenan la ventana y
# no queda lugar para la cantidad, y porque el rojo no tiene paleta libre en
# BG2. La cantidad sí, con los glifos, a la derecha.
#
# Para elegir a quién equipar la pantalla es la misma sin las dos ventanas de
# la izquierda: no hay ítem.
#
# A usa la medicina sobre la fila marcada y la pantalla se queda, con los HP de
# esa fila y la cantidad al día: ver `medicina_usar` en rom/src/medicina.s.
# Esto dibuja los HP que se le pasen en `hp`, así que después de curar alcanza
# con pasarle los nuevos.
OBJETIVO_IZQ = 104
OBJETIVO_NOMBRE_ALTO = 48
OBJETIVO_CUANTOS_ALTO = 32
OBJETIVO_GRUPO = (OBJETIVO_IZQ, 0, ANCHO - OBJETIVO_IZQ, ALTO)
OBJETIVO_VENTANAS = ((0, 0, OBJETIVO_IZQ, OBJETIVO_NOMBRE_ALTO),
                     (0, OBJETIVO_NOMBRE_ALTO, OBJETIVO_IZQ,
                      OBJETIVO_CUANTOS_ALTO),
                     OBJETIVO_GRUPO)
OBJETIVO_NOMBRE_COL = 1
OBJETIVO_NOMBRE_FILA = 1        # y = 8, y el segundo renglón en y = 24
OBJETIVO_NOMBRE_ANCHO = (OBJETIVO_IZQ - 8) // CELL - OBJETIVO_NOMBRE_COL  # 11
OBJETIVO_CUANTOS_FILA = (OBJETIVO_NOMBRE_ALTO + 8) // CELL                # 7
OBJETIVO_CUANTOS_COL = OBJETIVO_NOMBRE_COL + OBJETIVO_NOMBRE_ANCHO - 2    # 10
# La barra va sobre las tres líneas de texto de la fila, como en RM2k, y no
# sobre la cara: cuatro pixeles antes del texto y hasta cuatro del borde, y
# desde dos pixeles adentro de la fila, para no tocar el marco de arriba.
# Termina en 48, en el borde de una celda, y no en 50, que es donde termina
# la tercera línea: con la punta de abajo a mitad de celda eran 64 tiles, lo
# que entra justo antes del tilemap, y así son 60. Lo que queda afuera es la
# sombra de las letras de los HP.
OBJETIVO_BARRA = (MENU_TEXTO_X - 4, 2, ANCHO - MENU_TEXTO_X, 3 * LINEA - 2)
# Los colores de BG1 van en 128..143: son los de la paleta 0 de los sprites,
# que en esta pantalla están apagados, y que `menu_exp_cerrar` repone al
# cerrar el menú. En 0..127 no hay lugar: son las paletas del banco del menú.
OBJETIVO_CGRAM = 128
OBJETIVO_COLORES_MAX = 16
# Los tiles y el tilemap de BG1, detrás del tilemap del menú ($3C00..$4000):
# BG1 tiene su propia base en $4000, así que no tocan el banco de BG2. Lo que
# importa es que todo quede en el banco de BG1 de los repartos, que es lo que
# `load_map` repone al volver: ver `_controlar_objetivo` en el conversor.
OBJETIVO_VRAM = 0x4000
OBJETIVO_MAPA = 0x4800


def nombre_en_renglones(nombre, ancho=OBJETIVO_NOMBRE_ANCHO, renglones=2):
    """El nombre partido en renglones de `ancho`, por palabras; una palabra
    que no entra se corta donde llega. Rellenados con espacios, que son los
    que borran lo que hubiera."""
    salida, linea = [], ""
    for palabra in nombre.strip().split():
        while len(palabra) > ancho:
            if linea:
                salida.append(linea)
                linea = ""
            salida.append(palabra[:ancho])
            palabra = palabra[ancho:]
        if not linea:
            linea = palabra
        elif len(linea) + 1 + len(palabra) <= ancho:
            linea += " " + palabra
        else:
            salida.append(linea)
            linea = palabra
    if linea:
        salida.append(linea)
    return [r.ljust(ancho) for r in (salida + [""] * renglones)[:renglones]]


def ventanas_objetivo(sys_img, db, con_item=True, barra=None, font_id=None):
    """Las ventanas de la elección de actor, en RGBA y del tamaño de la
    pantalla: lo que dibuja BG1. Con `con_item`, las dos de la izquierda con
    "Owned Items"; con `barra`, el cursor en esa fila del grupo."""
    from PIL import Image
    from port import ventana as ventana_mod
    fuera = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    for x, y, ancho, alto in (OBJETIVO_VENTANAS if con_item
                              else (OBJETIVO_GRUPO,)):
        una = ventana_mod.ventana(sys_img, ancho, alto)
        fuera.paste(una, (x, y), una)
    if con_item:
        ventana_mod.dibujar_linea(
            fuera, sys_img, OBJETIVO_NOMBRE_COL * CELL + GLIFO_DX,
            OBJETIVO_CUANTOS_FILA * CELL + GLIFO_DY,
            lcf_termino_poseidos(db), color=1, font_id=font_id)
    if barra is not None:
        x, y, ancho, alto = OBJETIVO_BARRA
        una = ventana_mod.cursor(sys_img, ancho, alto)
        fuera.paste(una, (x, barra * MENU_ACTOR_FILAS * CELL + y), una)
    return fuera


def lcf_termino_poseidos(db):
    """"Owned Items": `possessed_items` de los términos del LDB."""
    from rpgmaker import lcf
    return lcf.to_string(db.terminos["possessed_items"])


def capas_objetivo(sys_img, db, font_id=None):
    """Lo que `marcos` necesita de la elección de actor: con ítem y sin ítem,
    cada una sin cursor y con el cursor en cada fila del grupo, desde la
    primera fila de celdas de la fila del actor."""
    return [(ventanas_objetivo(sys_img, db, con_item, None, font_id),
             [(ventanas_objetivo(sys_img, db, con_item, k, font_id),
               k * MENU_ACTOR_FILAS, MENU_ACTOR_FILAS)
              for k in range(MENU_FILAS_GRUPO)])
            for con_item in (True, False)]


def objetivo_compacto(mapas):
    """Lo que la ROM guarda de los tilemaps de `marcos(capas_objetivo(...))`,
    que es mucho menos que lo que `marcos` devuelve.

    * **Un solo tilemap**, el con ítem: el de sin ítem es el mismo con las
      celdas de las dos ventanas de la izquierda en cero —las columnas de
      `OBJETIVO_IZQ` para la izquierda, hasta el fondo de la de "Owned
      Items"—, y la ROM las borra al subirlo.
    * **La barra, sólo donde cambia**: el rectángulo que cubre lo que difiere
      entre cada fila del grupo con barra y sin ella, igual para las cuatro
      filas, y que tiene que ser igual con ítem y sin ítem.

    Devuelve `(mapa, barras, fila0, filas, col0, cols, borrar_filas,
    borrar_cols)`: `barras[k]` son las `filas` por `cols` palabras de la fila
    `k` del grupo, desde la fila `fila0` de la fila del actor y la columna
    `col0`. Si algo de eso no vale, es un error y no un tilemap distinto: la
    ROM supone las dos cosas.
    """
    (con, barras_con), (sin, barras_sin) = mapas
    borrar_cols = OBJETIVO_IZQ // CELL
    borrar_filas = (OBJETIVO_NOMBRE_ALTO + OBJETIVO_CUANTOS_ALTO) // CELL
    esperado = [0 if (i // COLS < borrar_filas and i % COLS < borrar_cols)
                else p for i, p in enumerate(con)]
    if esperado != sin:
        raise SystemExit("el tilemap sin ítem de la elección de actor no es "
                         "el con ítem con las ventanas de la izquierda "
                         "borradas")
    distintas = set()
    for k, barra in enumerate(barras_con):
        base = con[k * MENU_ACTOR_FILAS * COLS:
                   (k + 1) * MENU_ACTOR_FILAS * COLS]
        distintas |= {(i // COLS, i % COLS)
                      for i, (a, b) in enumerate(zip(base, barra)) if a != b}
    fila0 = min(f for f, _ in distintas)
    filas = max(f for f, _ in distintas) + 1 - fila0
    col0 = min(c for _, c in distintas)
    cols = max(c for _, c in distintas) + 1 - col0
    if col0 < borrar_cols:
        raise SystemExit("la barra de la elección de actor llega a la "
                         "columna %d, que es de las ventanas del ítem" % col0)

    def recorte(barra):
        return [barra[(fila0 + f) * COLS + col0 + c]
                for f in range(filas) for c in range(cols)]

    barras = [recorte(b) for b in barras_con]
    if barras != [recorte(b) for b in barras_sin]:
        raise SystemExit("la barra de la elección de actor no es la misma con "
                         "ítem y sin ítem")
    return con, barras, fila0, filas, col0, cols, borrar_filas, borrar_cols


def render_objetivo(sys_img, db, ranuras, grupo, elegida=0, font_id=None,
                    actores=None, game_dir=None, hp=None, item=None,
                    cantidad=0):
    """La elección de actor como la tiene que mostrar la consola.

    Comparte el panel del grupo con el menú, así que también le escribe los
    HP: los pinta `menu_grupo_pintar`, que es la misma rutina de los dos
    lados. `item` es la medicina que se usa, con `cantidad` las que quedan;
    sin ella es la elección de a quién equipar.
    """
    from PIL import Image
    actores = sorted(set(actores if actores is not None else grupo))
    nombre = db.items[item].name if item else ""
    tiles, paletas, _, _, caras, menu = pantalla_ranuras(
        sys_img, db, ranuras, font_id, actores, game_dir, nombre)
    fuera = Image.new("RGB", (ANCHO, ALTO), (0, 0, 0))
    ventanas = ventanas_objetivo(sys_img, db, bool(item), elegida, font_id)
    fuera.paste(ventanas, (0, 0), ventanas)
    pegar = _pintor(fuera, tiles, paletas)
    for fila, actor in enumerate(list(grupo)[:MENU_FILAS_GRUPO]):
        if actor in actores:
            _pegar_fila_de_actor(pegar, menu, caras, db, fila, actor, hp)
    if item:
        for n, renglon in enumerate(nombre_en_renglones(nombre)):
            _pegar_texto(pegar, menu, renglon, OBJETIVO_NOMBRE_FILA + 2 * n,
                         OBJETIVO_NOMBRE_COL)
        _pegar_texto(pegar, menu, "%2d" % min(cantidad, 99),
                     OBJETIVO_CUANTOS_FILA, OBJETIVO_CUANTOS_COL)
    return fuera


def render_items(sys_img, db, inventario, elegida=0, arriba=0, font_id=None,
                 items=None):
    """La pantalla de ítems como la tiene que mostrar la consola.

    `inventario` va de número de ítem a cuántos hay; `items` son los que la
    ROM conoce —sin ella, los del inventario—; `elegida` es el lugar del
    cursor en la lista y `arriba` el primero que se ve. Se arma con las mismas
    celdas que escribe la ROM.
    """
    from PIL import Image
    items = sorted(items if items is not None
                   else [i for i, n in inventario.items() if n > 0])
    tiles, paletas, glifos = pantalla_items(sys_img, font_id)
    fuera = Image.new("RGB", (ANCHO, ALTO), (0, 0, 0))
    lista = lista_de_items(items, inventario)
    # El cursor es parte de las ventanas: ver `ITEM_BARRA_X`.
    ventanas = ventanas_items(sys_img, elegida - arriba if lista else None)
    fuera.paste(ventanas, (0, 0), ventanas)
    pegar = _pintor(fuera, tiles, paletas)

    def escribir(texto, fila0, col0, gris=0):
        for n, c in enumerate(texto):
            pegar(glifos[gris][c], fila0, col0 + n, 1)

    if lista:
        for n, renglon in enumerate(partir_descripcion(
                db.items[lista[elegida]].description)):
            escribir(renglon, ITEM_DESC_Y // CELL + 2 * n, ITEM_DESC_COL)
    for fila in range(ITEM_FILAS):
        k = arriba + fila
        if k >= len(lista):
            break
        item = db.items[lista[k]]
        fila0 = ITEM_LISTA_Y // CELL + 2 * fila
        gris = 0 if item_usable(item) else 1
        escribir(texto_de_item(item.name, ITEM_NOMBRE_ANCHO), fila0,
                 ITEM_NOMBRE_COL, gris)
        escribir(":%2d" % min(inventario[lista[k]], 99), fila0,
                 ITEM_DOS_PUNTOS_COL, gris)
    return fuera


def render_ranuras(sys_img, db, ranuras, llenas, elegida, modo=0, font_id=None,
                   grupos=None, game_dir=None, niveles=None):
    """La pantalla de ranuras como la tiene que mostrar la consola.

    `llenas` es una secuencia de booleanos, una por ranura; `elegida`, dónde
    está el cursor; `modo`, 0 para cargar y 1 para guardar; `grupos`, por
    ranura llena, los actores del grupo guardado, que ponen el nombre del
    primero y las caras de hasta CARAS_MAX; `niveles`, por ranura, el nivel
    que el líder tenía en esa partida —sin ella, el de arranque—.

    Se arma con **los mismos bloques de celdas que la ROM sube**, no volviendo a
    dibujar el texto ni pegando la cara: si se dibujara acá con la fuente y
    allá con los tiles, quedaría afuera justo el paso que puede salir mal.
    """
    from PIL import Image
    grupos = grupos or {}
    actores = sorted({a for g in grupos.values() for a in g})
    tiles, paletas, cabeceras, filas, caras, menu = pantalla_ranuras(
        sys_img, db, ranuras, font_id, actores, game_dir)
    fuera = Image.new("RGB", (ANCHO, ALTO), (0, 0, 0))
    pegar = _pintor(fuera, tiles, paletas)

    pegar(cabeceras[modo], CABECERA_Y // CELL)
    for numero in range(ranuras):
        fila0 = (RANURA_Y + numero * RANURA_SALTO) // CELL
        llena = bool(llenas[numero]) or numero in grupos
        pegar(filas[numero][1 if llena else 0][
            1 if numero == elegida else 0], fila0)
        if not llena:
            continue
        grupo = list(grupos.get(numero, ()))
        # El nombre del líder y su nivel, compuestos con glifos encima de la
        # fila, y las caras, que sí son bloques. Un actor sin cara no dibuja
        # nada, que es lo que hace `DrawFace` con un nombre vacío.
        if grupo and grupo[0] in actores:
            _pegar_texto(pegar, menu,
                         texto_de_nombre(db, grupo[0], NOMBRE_COLS),
                         fila0 + NOMBRE_FILA, NOMBRE_COL)
            _pegar_texto(pegar, menu,
                         texto_de_nivel(db, grupo[0],
                                        (niveles or {}).get(numero)),
                         fila0 + NIVEL_FILA, NIVEL_COL)
        for lugar, actor in enumerate(grupo[:CARAS_MAX]):
            if actor in caras:
                pegar(caras[actor], fila0, CARA_COL + lugar * CARA_PASO,
                      CARA_CELDAS)
    return fuera

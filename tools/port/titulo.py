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

from port.constantes import ALTO, ANCHO, CELL, COLS, MENU_CGRAM
from port.paleta import NEGRO, convertir


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

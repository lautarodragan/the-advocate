#!/usr/bin/env python3
"""Qué significan las cosas en RPG Maker 2000, sin ninguna consola de por medio.

Por dónde se puede caminar, qué capa tapa a cuál, qué gráfico le toca a un
evento, cuáles de ellos se dibujan. Son las reglas del motor original, y valen
igual para cualquier port —y para cualquier juego de RM2k—.

Lo que dicen estas reglas se contrasta contra liblcf y easyrpg-player; ninguno
de estos números se escribió de memoria.
"""

import os

from comun import perillas
from rpgmaker import lcf

CELL = 8

# --- la geometría del ChipSet ------------------------------------------------
#
# Dónde vive cada cosa en la imagen de un ChipSet, que es de 480x256. Los
# offsets son los de lmu2png de EasyRPG Tools, igual que los de
# `render/chipset.py`, que es quien expande el ChipSet con ellos.

TILE = 16


def caja_de_terreno(n):
    """Dónde vive, en la imagen del ChipSet, el bloque del autotile de terreno
    `n` —0 a 11, el que el mapa nombra con los ids 4000 + n * 50—.

    Son 48x64 píxeles con las piezas que `ChipsetAtlas._terrain_tile`
    combina. Está acá y no en quien lo use porque los offsets son de lmu2png y
    no tienen por qué escribirse dos veces: `ChipsetAtlas._terrain_tile`
    calcula su esquina con esta misma cuenta.
    """
    terrain = n + 4
    sx = (terrain % 2) * 48 + (terrain // 8) * 96
    sy = ((terrain // 2) % 4) * 64
    return (sx, sy, sx + 48, sy + 64)


def caja_de_comun(i):
    """Dónde vive el tile común `i` —0 a 287, las tres páginas de 96 de la
    mitad derecha—. Los 144 primeros son la capa baja (ids 5000 + i) y los 144
    de atrás la alta (ids 10000 + i - 144)."""
    x = 192 + (i % 6) * TILE + (i // 96) * 96
    y = ((i // 6) % TILE) * TILE
    return (x, y, x + TILE, y + TILE)


# --- colisión ---------------------------------------------------------------
#
# Cada tile de RM2k tiene cuatro bits que dicen por qué lados se lo puede
# cruzar. Moverse de un tile al de al lado pide permiso a los dos: el de origen
# tiene que dejar salir por ese lado y el destino dejar entrar por el opuesto.
#
# La capa alta manda sobre la baja, salvo que tenga el bit "Above" —que
# significa "se dibuja por encima del héroe", o sea decorado— en cuyo caso la
# que decide es la baja. Puerto de Game_Map::IsPassableTile de EasyRPG.

PASS_DOWN = 0x01
PASS_LEFT = 0x02
PASS_RIGHT = 0x04
PASS_UP = 0x08
PASS_ABOVE = 0x10
PASS_WALL = 0x20
PASS_ALL = PASS_DOWN | PASS_LEFT | PASS_RIGHT | PASS_UP

# Las combinaciones de un autotile de terreno que son la cara de una pared.
# Con el bit Wall puesto, esas se cruzan siempre.
WALL_FACES = frozenset(list(range(20, 24)) + list(range(33, 38))
                       + [42, 43, 45, 46])


def lower_passable(flags, raw, bit):
    if 4000 <= raw < 5000 and (flags[raw] & PASS_WALL):
        if (raw - 4000) % 50 in WALL_FACES:
            return True
    return bool(flags[raw] & bit)


def pasa_de_celda(flags, lower, upper):
    """Los cuatro bits de dirección de una celda, dados sus dos tiles."""
    byte = 0
    for bit in (PASS_DOWN, PASS_LEFT, PASS_RIGHT, PASS_UP):
        if not (flags[upper] & bit):
            continue                       # la capa alta bloquea
        if not (flags[upper] & PASS_ABOVE):
            byte |= bit                    # la capa alta manda, y deja
        elif lower_passable(flags, lower, bit):
            byte |= bit                    # es decorado: manda la baja
    return byte


def passability_map(game_map, flags):
    """Un byte por tile del mapa con los cuatro bits de dirección ya resueltos.

    Toda la lógica de RM2k se resuelve acá; la ROM sólo mira la tabla.
    """
    result = bytearray(game_map.width * game_map.height)
    for i in range(len(result)):
        result[i] = pasa_de_celda(flags, game_map.lower_layer[i],
                                  game_map.upper_layer[i])
    return bytes(result)


def hero_start(passable, width, height, blocked=()):
    """El tile abierto por los cuatro lados más cercano al centro del mapa."""
    cx, cy = width // 2, height // 2
    best = None
    for y in range(height):
        for x in range(width):
            if (passable[y * width + x] & PASS_ALL == PASS_ALL
                    and (x, y) not in blocked):
                distance = (x - cx) ** 2 + (y - cy) ** 2
                if best is None or distance < best[0]:
                    best = (distance, x, y)
    if best is None:
        # `sys.exit` sin `import sys`, que es lo que había, convertía un mensaje
        # escrito a propósito en un `NameError` que no dice nada. Y esta rama se
        # alcanza de verdad: hay mapas del juego —el 44 entre ellos— donde
        # ninguna celda está abierta por los cuatro lados, y el conversor tiene
        # que poder decirlo.
        raise ValueError(
            "el mapa no tiene ninguna celda abierta por los cuatro lados, así "
            "que no hay dónde poner al héroe")
    return best[1], best[2]


# --- la animación del ChipSet -----------------------------------------------
#
# Dos animaciones que no tienen nada que ver entre sí y corren a la vez, las dos
# en `TilemapLayer::Draw` de easyrpg (tilemap_layer.cpp:289):
#
#   los autotiles de agua A/B/C   3 dibujos, uno cada `AGUA_CUADROS` cuadros
#   los "tiles animados"          4 dibujos, uno cada `ANIMADO_CUADROS`
#
# El agua no recorre sus tres dibujos en círculo: el paso va de 0 a 3 y el 3
# **vuelve a dibujar el 1**, así que el ciclo es 0,1,2,1 y dura cuatro pasos.
# Eso es con `animation_type` en 0, que es el default y lo que tienen todos los
# chipsets de este juego salvo dos que no usa ninguno de los mapas del port;
# con el otro tipo son tres pasos en círculo.
#
# `animation_speed` elige entre 24 y 12 cuadros por paso —`Game_Map::
# GetAnimationSpeed`— y también está en el default en todo el juego.
#
# El reloj es el contador de cuadros del sistema, que no se reinicia al cambiar
# de mapa. Acá ese reloj es el tick, que en la ROM es `vueltas` —ver
# `Partida` en rom/pruebas/arnes/consola.py, que es quien lo lee—. La fase absoluta contra el juego
# original no significa nada, porque nuestro arranque no dura lo mismo; lo que
# tiene que coincidir es la cadencia y que los dos lados miren el mismo tick.
# Las dos familias, con cuántos dibujos tiene cada una. El orden es el de las
# corridas de tiles en la VRAM; ver `convert` en snes_convert.py.
FAMILIAS_ANIMADAS = (("agua", 3), ("animado", 4))
# El reloj de la ROM es `vueltas`, de dieciséis bits, así que da la vuelta cada
# 65536 ticks —dieciocho minutos— y ahí el ciclo se saltea un dibujo; el de RM2k
# es de treinta y dos. La referencia da la misma vuelta a propósito: lo que
# tiene que coincidir es lo que dibujan los dos lados, y perder un paso de agua
# una vez cada dieciocho minutos no lo ve nadie. Está declarado en
# workflow/divergencias/el-chipset-se-saltea-un-dibujo-cada-18-minutos.md.
TICK_MASCARA = 0xFFFF
AGUA_CUADROS_LENTO, AGUA_CUADROS_RAPIDO = 24, 12
# Tres dibujos recorridos en cuatro pasos, con el cuarto repitiendo el segundo.
# Es la misma forma en los dos lados de RM2k donde aparece: el agua del ChipSet
# —`animation_step_ab`— y el ciclo de caminata de un personaje, que tiene tres
# columnas y `Game_Character::columna` dibuja la 1 cuando el paso es el 3.
CICLO_TRES = (0, 1, 2, 1)
AGUA_CICLO = CICLO_TRES
ANIMADO_CUADROS = 6
ANIMADO_PASOS = 4


def paso_animado(tick):
    """Cuál de los cuatro dibujos de los tiles animados toca en ese tick."""
    return ((tick & TICK_MASCARA) // ANIMADO_CUADROS) % ANIMADO_PASOS


# --- el sprite del personaje ----------------------------------------------
#
# Un CharSet de RM2k son 4 personajes de ancho por 2 de alto; cada uno ocupa
# 72x128 y tiene 12 poses: 3 columnas de caminata por 4 direcciones. Cada pose
# mide 24x32, o sea 3x4 celdas de 8x8.

SPRITE_CELLS_W = 3
SPRITE_CELLS_H = 4
SPRITE_POSES = 12
POSE_W = SPRITE_CELLS_W * CELL
POSE_H = SPRITE_CELLS_H * CELL

SPRITE_WIDTH = 24
SPRITE_HEIGHT = 32

# El sprite es más ancho y más alto que la celda de 16x16 sobre la que se para:
# se centra horizontalmente y se apoya por los pies.
OFFSET_X = -(SPRITE_WIDTH - TILE) // 2
OFFSET_Y = -(SPRITE_HEIGHT - TILE)


# --- los NPCs ---------------------------------------------------------------
#
# Son los eventos del mapa que tienen CharSet, en la página que el motor
# mostraría al empezar una partida: la de número más alto sin condiciones. No se
# evalúan sus scripts, así que cada uno se queda quieto en la pose que declara
# su página. Los eventos sin CharSet —puertas, cofres, disparadores— quedan
# afuera por ahora.

# Las tres capas de un evento. El orden de dibujado de RM2k es primero por
# capa y recién después por Y: un evento "below" queda debajo del héroe aunque
# esté más adelante en la pantalla, y uno "above" lo tapa siempre. Sale de
# Game_Character::GetScreenZ, donde el z es L- YY XX II con la capa en el byte
# más alto.
FACE_DOWN = 2      # la fila del CharSet con la que arranca el héroe

LAYER_BELOW = 0
LAYER_SAME = 1     # la del héroe, y la única que le choca
LAYER_ABOVE = 2


# Un evento sin CharSet se dibuja con un tile de la página alta del chipset:
# así están hechas las puertas, los cofres y buena parte del decorado. Para el
# resto del programa es un CharSet más, con este nombre inventado, que lleva el
# chipset y el índice del tile; `render_map.Charsets` sabe fabricar su imagen.
TILE_PREFIX = "@tile:"


# Un evento **translúcido** —el "Trans" de la página, `translucent`— se dibuja
# en RM2k con opacidad 160 de 255. La consola tiene transparencia de verdad
# —el color math— pero la aplica a todos los sprites de las paletas 4 a 7, y
# un mapa como el 9, con once personajes en las ocho paletas, no puede dejar
# cuatro para los translúcidos solos. Así que va **tramado**: la mitad de los
# pixeles en damero, que es lo que hacían los juegos de la época y en un
# televisor de tubo se ve como semitransparencia. Para el port es otro
# CharSet, con este sufijo en el nombre: el lector lo pega en las páginas
# translúcidas —ver `decorar_translucido`, que prende `snes_convert`— y
# `render_map.Charsets` fabrica la imagen tramada. Todo lo demás —paletas,
# ranuras, poses, la referencia— lo trata como a cualquier otro.
TRAMA_SUFIJO = "~trama"

# Un CharSet con este sufijo es **el mismo dibujo, contado como otro gráfico**:
# el asignador le da su propia paleta. Existe por el destello del héroe, que en
# la consola se hace sobre la paleta del personaje: un NPC que dibuja con el
# gráfico de un líder posible compartía paleta con él y destellaba también. Ver
# `convertir` en snes_convert.py.
COPIA_SUFIJO = "~aparte"

# Con qué trama. Las opciones están en `render_map.TRAMAS`; se elige mirando
# un televisor de tubo, que es donde esto se ve.
TRAMA_PATRON = os.environ.get("TRAMA_PATRON", "cinco_de_ocho")


# La opacidad con la que RM2k dibuja una página translúcida: 160 de 255.
OPACIDAD_TRANSLUCIDO = 160

# La otra salida, y la de hoy: **hornear la mezcla en el gráfico**. Los 70
# translúcidos del juego son todos estáticos —`move_type` 0 y sin ruta propia,
# medido sobre los 35 mapas—, así que ni el objeto ni el fondo se mueven y la
# mezcla al 160/255 contra el fondo real se puede calcular una vez, en el
# conversor, y quedar horneada en el sprite: exacta, sin trama y sin gastar
# color math. Lo que se paga es que el sprite queda **opaco** —nadie se ve por
# detrás— y que el gráfico deja de ser el mismo para dos eventos parados sobre
# fondos distintos, así que cada uno se lleva su paleta.
#
# Para el resto del programa es, otra vez, otro CharSet: el nombre lleva este
# sufijo con el mapa y la celda donde está parado el evento, que es todo lo que
# hace falta para reconstruir el fondo. Lo pega el lector —ver
# `lcf.DECORAR_TRANSLUCIDO`, que prende el conversor— y `render_map.Charsets`
# fabrica la imagen.
HORNEADO_SUFIJO = "~horneado"

# Cuál de los dos caminos corre. Se cambia con MODO_TRANSLUCIDO=trama para
# poder comparar los dos sobre el mismo árbol.
MODO_TRANSLUCIDO = os.environ.get("MODO_TRANSLUCIDO", "horneado")


def nombre_horneado(nombre, map_id, x, y):
    return "%s%s:%d:%d:%d" % (nombre, HORNEADO_SUFIJO, map_id, x, y)


def parte_horneada(nombre):
    """(nombre de base, (mapa, x, y)) de un CharSet horneado, o (nombre, None).

    Todo lo que mire *qué* gráfico es —la pasabilidad del tile, quién es un
    tile y quién un CharSet de verdad— tiene que preguntar por la base: el
    sufijo lleva dónde está parado, no qué dibuja.
    """
    base, marca, resto = nombre.partition(HORNEADO_SUFIJO + ":")
    if not marca:
        return nombre, None
    return base, tuple(int(n) for n in resto.split(":"))


def sin_horneado(nombre):
    return parte_horneada(nombre)[0]


def sin_trama():
    """Los CharSets que se dibujan **opacos aunque su página diga
    translúcida**, en minúsculas: una divergencia deliberada de RM2k que
    decide el juego, en `[graphics] opaque` del archivo de proyecto."""
    return frozenset(n.lower() for n in perillas.valor(
        "graphics", "opaque", tipo=list))


def decorar_translucido(nombre, map_id, x, y):
    """El nombre que lleva el gráfico de una página translúcida.

    Tres salidas, y la primera manda: los de `sin_trama()` se dibujan **opacos**
    aunque su página diga translúcida —decisión de taro, ver la lista—, el
    resto va horneado contra el fondo de su celda, y `MODO_TRANSLUCIDO=trama`
    vuelve al damero para poder comparar los dos sobre el mismo árbol.
    """
    if nombre.lower() in sin_trama():
        return nombre
    if MODO_TRANSLUCIDO == "trama":
        return nombre + TRAMA_SUFIJO
    return nombre_horneado(nombre, map_id, x, y)



def nombre_de_tile(chipset, indice):
    return "%s%s:%d" % (TILE_PREFIX, chipset, indice)


# Las condiciones de página que la ROM sabe mirar. Un evento con una página
# que pida otra cosa queda afuera entero: sin sus páginas en la tabla, la ROM
# no puede saber cuál está activa, así que no cambia de gráfico ni frena.
# "variable" desde el 2026-09-10 a la noche: la página lleva la ranura, la
# comparación y el valor, y la ROM los mira en `condiciones_ok`. Falta el
# cronómetro, que pide una sola página del juego, la 81 del mapa 312.
CONDICIONES_SOPORTADAS = ("switch_a", "switch_b", "actor", "variable", "item")
# Y las que el port **no puede cumplir nunca**. Fue la de ítem durante un
# día: sin inventario, `ChangeItems` se aceptaba sin hacer nada y el grupo no
# tenía ningún ítem jamás, así que la página se emitía como una que no está
# activa nunca —ver `SWITCH_IMPOSIBLE` en eventos.py— y las demás páginas del
# evento corrían como corresponde. Desde el 2026-09-10 a la noche hay
# inventario y la condición de ítem se evalúa; la máquina queda por si
# aparece otra condición así.
CONDICIONES_IMPOSIBLES = ()


def pagina_imposible(page):
    """Si la página pide algo que este port no cumple nunca."""
    return any(c in CONDICIONES_IMPOSIBLES for c in page.condition.active)


def condiciones_soportadas(event):
    return not any(c not in CONDICIONES_SOPORTADAS
                   and c not in CONDICIONES_IMPOSIBLES
                   for page in event.pages for c in page.condition.active)


def grafico_de_pagina(page, chipset):
    """(CharSet, índice, pose) de lo que dibuja la página, o None si nada.

    Los que se dibujan con un tile del chipset van con un CharSet inventado
    —ver `nombre_de_tile`—, siempre que quien cargó el mapa le haya puesto
    `chipset_nombre`; el tile 0 es "sin gráfico".
    """
    if not page.character_name and (page.character_index == 0
                                    or chipset is None):
        return None
    # La caminata son cuatro fases sobre tres columnas: la del medio va dos
    # veces, así que la cuarta dibuja la misma que la segunda.
    column = 1 if page.character_pattern == 3 else page.character_pattern
    return (page.character_name or nombre_de_tile(chipset, page.character_index),
            page.character_index if page.character_name else 0,
            page.character_direction * 3 + column)


def pasabilidad_del_tile(game_map, charset, layer):
    """Los cuatro bits de paso que un evento dibujado con `charset` en la capa
    `layer` le impone a su celda, o None si no impone nada.

    Es la regla de `Game_Map::IsPassableTile`: un evento de la capa de abajo
    con gráfico de tile reemplaza la pasabilidad del terreno por la de su
    tile, salvo que el tile sea de los que van por encima. Así "se abre" una
    puerta en este juego: la celda es pared, y con el switch puesto la página
    muestra el tile de los escombros, que se pisa. Los bits salen de la misma
    tabla que la capa alta del mapa, que quien cargó el mapa deja en
    `pasabilidad_tiles`.
    """
    flags = getattr(game_map, "pasabilidad_tiles", None)
    base = sin_horneado(charset)
    if flags is None or layer != LAYER_BELOW \
            or not base.startswith(TILE_PREFIX):
        return None
    valor = flags[UPPER_BASE + int(base.rsplit(":", 1)[1])]
    if valor & PASS_ABOVE:
        return None
    return valor & PASS_ALL


UPPER_BASE = 10000      # el primer tile de la capa alta, en el mapa y en la tabla
# Y el primero de los tiles sueltos de la capa de abajo: el "bloque E" del
# formato, los 144 que la paleta del editor muestra debajo de los autotiles.
# Son los dos rangos con los que habla `TileSubstitution`, que numera desde el
# primero de cada uno. Los autotiles quedan afuera: no los sustituye ni RM2k.
LOWER_BASE = 5000
TILES_POR_CAPA = 144

# Los seis bloques de ids de tile del formato, como `map_data.h` de easyrpg:
# (primer id, cuántos, cuánto ocupa cada uno, primer índice). El **índice** es
# con lo que se lee la tabla de terrenos y la de pasabilidad del ChipSet, y no
# es el id: los autotiles ocupan 50 o 1000 ids cada uno —las combinaciones de
# bordes— y un solo índice.
BLOQUES_DE_CHIP = ((0, 2, 1000, 0), (2000, 1, 1000, 2), (3000, 3, 50, 3),
                   (4000, 12, 50, 6), (LOWER_BASE, 144, 1, 18),
                   (UPPER_BASE, 144, 1, 162))
# Cuántas entradas tiene la tabla de terrenos: las de la capa de abajo.
TERRENOS_POR_CHIPSET = 162


def indice_de_chip(chip_id):
    """`ChipIdToIndex`: de un id de tile del mapa a su entrada del ChipSet."""
    for base, cuantos, paso, indice in BLOQUES_DE_CHIP:
        if base <= chip_id < base + cuantos * paso:
            return indice + (chip_id - base) // paso
    return 0


def terreno_de(chipset, chip_id):
    """El terreno de un tile de la capa de abajo, como `GetTerrainTag`.

    Un ChipSet cuyo terreno es todo 1 **no guarda la tabla**: es una
    optimización de RPG_RT que el formato deja ver, y la respuesta entonces es
    1. Todos los ChipSets de este juego son así.
    """
    if not chipset.terrain:
        return 1
    return chipset.terrain[indice_de_chip(chip_id)]

# Los `animation_type` que piden animación continua: "Continuous" y "Fixed
# Dir/Continuous". El save point de Lashe City es del segundo tipo.
ANIMA_CONTINUO = (1, 3)


def collect_npcs(game_map):
    """Los eventos que se dibujan, con su pose y si bloquean el paso.

    Entra todo evento con gráfico en **alguna** página, aunque la activa al
    cargar no tenga: las puertas de este juego son eso, una página sin gráfico
    y otra con el tile de los escombros. `visible` dice si se ve al cargar, y
    `cambia` si el gráfico sigue a la página activa: es lo que la ROM refresca
    con los switches, y vale sólo para eventos cuyas condiciones entiende.
    `graficos` lleva el de cada página, o None, y `capas` la capa de cada una.
    """
    npcs = []
    chipset = getattr(game_map, "chipset_nombre", None)
    for numero, event in enumerate(game_map.events):
        # Una página imposible no se dibuja nunca: su gráfico no cuenta.
        graficos = [None if pagina_imposible(p) else grafico_de_pagina(p, chipset)
                    for p in event.pages]
        if not any(graficos):
            continue
        # Qué puede llegar a dibujar este evento a lo largo de la partida. No
        # es sólo el gráfico de cada página: si la **primera** tiene condición,
        # puede no haber ninguna activa, y entonces no dibuja nada. Ese "nada"
        # es un estado más.
        #
        # Sin contarlo, un evento de una sola página condicionada queda con un
        # solo gráfico posible, `cambia` da falso, y como al cargar el mapa
        # tampoco es visible, se lo saltea entero: no hay fila que actualizar
        # cuando el switch se prenda. taro lo vio el 2026-09-07 con el
        # `TalDoorBottom` del mapa 8, que se puede usar y corre sus comandos
        # pero no se dibuja nunca. Son **350 eventos en 68 mapas**.
        posibles = set(graficos)
        if event.pages and event.pages[0].condition.active:
            posibles.add(None)
        cambia = len(posibles) > 1 and condiciones_soportadas(event)
        page = event.active_page()
        visible = page is not None and grafico_de_pagina(page, chipset) is not None
        if not visible and not cambia:
            continue                # sin gráfico al cargar y sin cambio: no está
        if not visible:
            # La fila existe escondida: sus campos salen de la primera página
            # con gráfico, que es de donde va a salir cuando aparezca.
            page = next(p for p, g in zip(event.pages, graficos)
                        if g is not None)
        charset, index, pose = grafico_de_pagina(page, chipset)
        npcs.append({
            # El índice en la tabla de eventos del mapa, que es lo que lleva el
            # bytecode de una ruta forzada. **No es el id de RM2k**: hay mapas
            # con huecos en la numeración.
            "evento": numero,
            "x": event.x, "y": event.y,
            "charset": charset, "index": index, "pose": pose,
            "layer": page.layer,
            "blocks": page.layer == LAYER_SAME,
            # La velocidad de su página, que es la que lleva una ruta forzada
            # sobre él: RM2k la pone en `SetupFromPage` y `ForceMoveRoute` no
            # la toca. Por defecto es 3, dieciséis cuadros por celda.
            "velocidad": page.move_speed,
            # Si su página pide animación continua. Los que además caminan la
            # llevan adentro de su ranura de ruta; esto es para los quietos.
            "anima": page.animation_type in ANIMA_CONTINUO,
            "visible": visible,
            "cambia": cambia,
            "graficos": graficos,
            "capas": [p.layer for p in event.pages],
            "tile_pasa": pasabilidad_del_tile(game_map, charset, page.layer)
                         if visible else None,
        })
    return npcs


# El código de comando de `Teleport`, de liblcf. Lo usa el planificador de
# recorridos del arnés para saber a dónde lleva la página de un evento.
TELEPORT = 10810

#!/usr/bin/env python3
"""Qué significan las cosas en RPG Maker 2000, sin ninguna consola de por medio.

Por dónde se puede caminar, qué capa tapa a cuál, qué gráfico le toca a un
evento, cuáles de ellos son puertas. Son las reglas del motor original, y valen
igual para cualquier port —y para cualquier juego de RM2k—.

Salieron de `md_convert.py`, donde estaban mezcladas con el formato del VDP: el
port a SNES importaba de ahí dieciséis nombres que no tenían nada de Mega Drive.
Lo que dicen estas reglas se contrasta contra liblcf y easyrpg-player, que están
en /extras/ref; ninguno de estos números se escribió de memoria.
"""

import lcf

CELL = 8

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


def passability_map(game_map, flags):
    """Un byte por tile del mapa con los cuatro bits de dirección ya resueltos.

    Toda la lógica de RM2k se resuelve acá; la ROM sólo mira la tabla.
    """
    result = bytearray(game_map.width * game_map.height)
    for i in range(len(result)):
        lower = game_map.lower_layer[i]
        upper = game_map.upper_layer[i]
        byte = 0
        for bit in (PASS_DOWN, PASS_LEFT, PASS_RIGHT, PASS_UP):
            if not (flags[upper] & bit):
                continue                       # la capa alta bloquea
            if not (flags[upper] & PASS_ABOVE):
                byte |= bit                    # la capa alta manda, y deja
            elif lower_passable(flags, lower, bit):
                byte |= bit                    # es decorado: manda la baja
        result[i] = byte
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
        sys.exit("El mapa no tiene ningún tile abierto por los cuatro lados.")
    return best[1], best[2]


def puede_pasar(passable, width, height, x, y, dx, dy, blocked=(),
                pasa_evento=None):
    """Si desde (x,y) se puede dar un paso en (dx,dy).

    Las dos caras se consultan, la que se deja y la que se entra, que es la
    regla de RM2k. Está separada de `walk` porque hay quien necesita caminar de
    a un paso —para mirar entre paso y paso si la celda tiene una puerta— y las
    reglas tienen que ser las mismas, no una copia parecida.

    `pasa_evento(x, y)` es lo que un evento dibujado con un tile en la capa de
    abajo le impone a la celda, o None: ver `eventos.pasabilidad_de_evento`.
    Cuando hay uno, sus bits reemplazan a los del terreno en esa cara.
    """
    leaving = {(1, 0): PASS_RIGHT, (-1, 0): PASS_LEFT,
               (0, 1): PASS_DOWN, (0, -1): PASS_UP}[(dx, dy)]
    entering = {(1, 0): PASS_LEFT, (-1, 0): PASS_RIGHT,
                (0, 1): PASS_UP, (0, -1): PASS_DOWN}[(dx, dy)]
    nx, ny = x + dx, y + dy
    if not (0 <= nx < width and 0 <= ny < height):
        return False
    def bits(cx, cy):
        de_evento = pasa_evento(cx, cy) if pasa_evento is not None else None
        return passable[cy * width + cx] if de_evento is None else de_evento
    if not bits(x, y) & leaving:
        return False
    if not bits(nx, ny) & entering:
        return False
    if (nx, ny) in blocked:
        return False                # hay un NPC parado ahí
    return True


def walk(passable, width, height, start, dx, dy, blocked=()):
    """Hasta dónde llega el personaje caminando en una dirección sin soltar.

    Mismas reglas que la ROM, para poder predecir dónde va a terminar y
    comparar contra eso.
    """
    x, y = start
    while puede_pasar(passable, width, height, x, y, dx, dy, blocked):
        x, y = x + dx, y + dy
    return x, y


# --- el sprite del personaje ----------------------------------------------
#
# Un CharSet de RM2k son 4 personajes de ancho por 2 de alto; cada uno ocupa
# 72x128 y tiene 12 poses: 3 columnas de caminata por 4 direcciones. Cada pose
# mide 24x32, o sea 3x4 celdas del VDP, que es un tamaño legal de sprite.

SPRITE_CELLS_W = 3
SPRITE_CELLS_H = 4
SPRITE_POSES = 12
POSE_W = SPRITE_CELLS_W * CELL
POSE_H = SPRITE_CELLS_H * CELL


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


def nombre_de_tile(chipset, indice):
    return "%s%s:%d" % (TILE_PREFIX, chipset, indice)


# Las condiciones de página que la ROM sabe mirar. Un evento con una página
# que pida otra cosa queda afuera entero: sin sus páginas en la tabla, la ROM
# no puede saber cuál está activa, así que no cambia de gráfico ni frena.
CONDICIONES_SOPORTADAS = ("switch_a", "switch_b", "actor")


def condiciones_soportadas(event):
    return not any(c not in CONDICIONES_SOPORTADAS
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
    if flags is None or layer != LAYER_BELOW \
            or not charset.startswith(TILE_PREFIX):
        return None
    valor = flags[UPPER_BASE + int(charset.rsplit(":", 1)[1])]
    if valor & PASS_ABOVE:
        return None
    return valor & PASS_ALL


UPPER_BASE = 10000      # el primer tile de la capa alta, en el mapa y en la tabla


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
        graficos = [grafico_de_pagina(p, chipset) for p in event.pages]
        if not any(graficos):
            continue
        cambia = len(set(graficos)) > 1 and condiciones_soportadas(event)
        page = event.active_page()
        visible = page is not None and grafico_de_pagina(page, chipset) is not None
        if not visible and not cambia:
            continue                # sin gráfico al cargar y sin cambio: no está
        if not visible:
            # La fila existe escondida: sus campos salen de la primera página
            # con gráfico, que es de donde va a salir cuando aparezca.
            page = next(p for p in event.pages
                        if grafico_de_pagina(p, chipset) is not None)
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
            "visible": visible,
            "cambia": cambia,
            "graficos": graficos,
            "capas": [p.layer for p in event.pages],
            "tile_pasa": pasabilidad_del_tile(game_map, charset, page.layer)
                         if visible else None,
        })
    return npcs


# El código de Teleport y los triggers de una página, de liblcf.
TELEPORT = 10810
TRIGGER_TOCA_HEROE = 1

# Lo que puede acompañar a un teletransporte sin que deje de ser una puerta.
#
# El criterio no es "suena inofensivo" sino "que no lo hagamos no se ve en la
# pantalla que comparamos": un fundido, una espera y un sonido se saltean y la
# imagen final es la misma. Cualquier otra cosa —una condición, una variable,
# un diálogo, un cambio de música o del gráfico del héroe— hace que el evento
# haga algo más que mudarte, y ahí la puerta no alcanza.
#
# Estos números salen de tools/event_codes.py y hay que sacarlos de ahí. La
# primera versión los puso de memoria y tres estaban mal: dos de los que creía
# inofensivos eran PlayBGM y ChangeSpriteAssociation, o sea que el filtro
# aceptaba puertas que cambian la música y el sprite del héroe. Ese error la
# comparación no lo ve, porque la referencia usa esta misma lista.
PUERTA_ACOMPAÑAN = {
    10,      # END
    10120,   # MessageOptions
    11410,   # Wait
    11550,   # PlaySound: no tenemos efectos todavía, así que no se oye nada
    11030,   # TintScreen: el fundido con el que RM2k cruza una puerta
}


def collect_doors(game_map):
    """Las puertas del mapa: eventos cuyo único trabajo es mudarte de mapa.

    De los 959 teletransportes del juego, 238 son de éstos y todos se disparan
    con "toca el héroe". Los otros 721 están adentro de cinemáticas, con
    variables y condiciones, y ésos piden el intérprete de eventos.

    La gracia de separarlos es que las puertas se pueden hacer sin intérprete:
    el héroe pisa una celda, se mira si hay puerta, y si hay se carga el mapa
    de destino. Eso ya es un mundo en vez de un mapa suelto.
    """
    puertas = []
    for event in game_map.events:
        page = event.active_page()
        if page is None or getattr(page, "trigger", None) != TRIGGER_TOCA_HEROE:
            continue
        codes = [c.code for c in page.commands]
        if TELEPORT not in codes:
            continue
        if any(c != TELEPORT and c not in PUERTA_ACOMPAÑAN for c in codes):
            continue
        salto = next(c for c in page.commands if c.code == TELEPORT)
        if len(salto.parameters) < 3:
            continue
        destino, x, y = salto.parameters[0], salto.parameters[1], salto.parameters[2]
        puertas.append({"x": event.x, "y": event.y,
                        "mapa": destino, "destino_x": x, "destino_y": y})
    return puertas


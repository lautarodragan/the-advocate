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


def puede_pasar(passable, width, height, x, y, dx, dy, blocked=()):
    """Si desde (x,y) se puede dar un paso en (dx,dy).

    Las dos caras se consultan, la que se deja y la que se entra, que es la
    regla de RM2k. Está separada de `walk` porque hay quien necesita caminar de
    a un paso —para mirar entre paso y paso si la celda tiene una puerta— y las
    reglas tienen que ser las mismas, no una copia parecida.
    """
    leaving = {(1, 0): PASS_RIGHT, (-1, 0): PASS_LEFT,
               (0, 1): PASS_DOWN, (0, -1): PASS_UP}[(dx, dy)]
    entering = {(1, 0): PASS_LEFT, (-1, 0): PASS_RIGHT,
                (0, 1): PASS_UP, (0, -1): PASS_DOWN}[(dx, dy)]
    nx, ny = x + dx, y + dy
    if not (0 <= nx < width and 0 <= ny < height):
        return False
    if not passable[y * width + x] & leaving:
        return False
    if not passable[ny * width + nx] & entering:
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


def collect_npcs(game_map):
    """Los eventos visibles, con su pose y si bloquean el paso."""
    npcs = []
    for event in game_map.events:
        page = event.active_page()
        if page is None or not page.character_name:
            continue
        # La caminata son cuatro fases sobre tres columnas: la del medio va dos
        # veces, así que la cuarta dibuja la misma que la segunda.
        column = 1 if page.character_pattern == 3 else page.character_pattern
        npcs.append({
            "x": event.x, "y": event.y,
            "charset": page.character_name,
            "index": page.character_index,
            "pose": page.character_direction * 3 + column,
            "layer": page.layer,
            "blocks": page.layer == LAYER_SAME,
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


"""El que atraviesa paredes cae donde sea, también saltando.

`Game_Map::CheckOrMakeWayEx` corta con `if (self.GetThrough()) return true;`
apenas pasa el chequeo de límites del mapa, **antes** de mirar la pasabilidad de
la celda. Y el salto de una ruta forzada pasa por ahí: `BeginMoveRouteJump`
llama a `MakeWay(begin_x, begin_y, x, y)`.

Nuestro `puede_caer` miraba la pasabilidad y nada más, así que un salto a una
celda cerrada se saltaba aunque el personaje viniera con `walk_everywhere`
puesto.

El banco es el recuerdo de Core y Manta: la ruta que mueve a Core en el mapa 5
arranca con `atravesar_on` y lo hace saltar de su piedra a la de al lado y de ahí
a tierra, sobre celdas que la colisión da por cerradas —(31,18) tiene los cuatro
bits en cero—. taro lo reportó el 2026-09-07 como que Core se mueve arriba de su
islita y no salta nunca.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CORE = 3                # su índice en la tabla de eventos del mapa 5
DESDE = (31, 14)        # de dónde sale el primer salto
HASTA = (31, 18)        # y a dónde cae, cuatro celdas abajo
ESCENA = 16             # el switch que arranca el recuerdo


def celda(una, indice):
    base = una.simbolos["ev_pos_buf"] + indice * una.simbolos["EV_STRIDE"]
    b = una.consola.ram(base, 4)
    return (b[0] | (b[1] << 8), b[2] | (b[3] << 8))


def test_core_salta_a_la_segunda_piedra(partida):
    una = partida(switch=[ESCENA])
    visto = []
    for _ in range(2000):
        if una.byte("msg_abierto"):
            una.tocar("a")
        else:
            una.correr(1)
        c = celda(una, CORE)
        if not visto or visto[-1] != c:
            visto.append(c)
        if c == HASTA:
            break
    assert HASTA in visto, \
        "Core nunca llegó a %s: se quedó en %s. La celda está cerrada y el " \
        "salto se saltea si no se mira `walk_everywhere`" % (HASTA, visto[-3:])
    assert visto.index(DESDE) < visto.index(HASTA), \
        "llegó a la piedra sin pasar por %s: no fue el salto" % (DESDE,)

"""El minijuego de las luces del `Lazer Teeth HQ`, después del rediseño.

Las 52 baldosas de luz dejaron de ser eventos: el charco es un tile del mapa,
apagar un cono es un `TileSubstitution` y atrapar al héroe es un proceso
paralelo que mira el terreno de la celda en la que está. El porqué está en
`workflow/done/el-mapa-11-se-rediseno.md`.

Esto existe porque **ninguna otra prueba ejecuta ese camino**. La tanda de
pixeles no lo ve —el mapa se dibuja igual que antes, que es justamente lo que
el rediseño buscaba— y `test_sustitucion` y `test_terreno` cuidan los dos
comandos sueltos, no el minijuego armado con ellos. Sin esto, el rediseño se
podía romper entero sin que nada se pusiera en rojo.

El compañero que mide que el mapa **entra en el cuadro** es
`test_el_hq_de_los_lazer_teeth_entra_en_el_cuadro`, en
`pruebas/rpgmaker/test_paralelos.py`.
"""

import os

import pytest

from port import eventos
from rpgmaker import lcf
from render.render_map import REPO

from piedras import MAPAS, STONE, celda_de, hablarle_a_la_reja

MAPA11 = os.path.join(REPO, "parches", "manual", "mapas", "Map0011.json")

# Dónde busca `Light5` a la piedra en su página paralela: la celda es suya y
# está escrita en la página, así que acá se repite y no se deduce.
LUZ5 = (22, 43)
# El switch que `Light5` prende al romperse, que es lo que en el original
# cambiaba su gráfico por el de la lámpara rota.
LAMPARA_ROTA = 44
# El tile de la capa alta con que se dibuja el cono que **nunca** se apaga.
# Pararse en una de sus celdas tiene que atrapar al héroe siempre.
TILE_DEL_CONO_B = 10080


@pytest.fixture(scope="session")
def celdas_del_cono_b():
    """Las celdas que dibujan el charco del cono B, sacadas del mapa.

    Se descartan las de la última fila: ahí viven las celdas testigo que le
    dan al conversor las combinaciones que las sustituciones necesitan, y no
    son parte del minijuego. Ver el commit que las puso.
    """
    mapa = lcf.Map(MAPA11)
    return [(i % mapa.width, i // mapa.width)
            for i, tile in enumerate(mapa.upper_layer)
            if tile == TILE_DEL_CONO_B and i // mapa.width < mapa.height - 1]


@pytest.fixture(scope="session")
def eventos_del_11():
    """Para traducir el id de RM2k de la piedra al índice de la tabla de la
    ROM, con la misma función que usó el conversor."""
    return eventos.Eventos(lcf.Map(MAPA11))


def test_pararse_en_una_baldosa_iluminada_atrapa(partida, celdas_del_cono_b):
    """Lo que antes hacía el trigger de contacto de cada baldosa.

    El cono B es el que ninguna fuente apaga, así que sus celdas atrapan sin
    preparar nada. Lo que se mira es que se abra un mensaje, que es lo que la
    baldosa hacía cuando era un evento.
    """
    assert celdas_del_cono_b, "el mapa no dibuja el cono B en ninguna celda"
    una = partida(caso=MAPAS)
    una.correr(30)
    assert not una.byte("msg_abierto"), "algo abrió un mensaje antes de empezar"

    x, y = celdas_del_cono_b[len(celdas_del_cono_b) // 2]
    una.ir_al_mapa(11, x, y)
    una.correr(60)
    assert una.byte("msg_abierto"), (
        "parado en (%d,%d), que es una baldosa iluminada del cono B, el "
        "paralelo tendría que haber abierto el mensaje del 'me atraparon'"
        % (x, y))


def test_la_piedra_en_la_lampara_apaga_su_cono(partida, eventos_del_11):
    """El minijuego entero: la piedra rompe la lámpara y el cono se apaga.

    La piedra se planta en la celda del héroe —es lo que hace la A del motor,
    ver `test_piedras`—, así que parando al héroe encima de `Light5` queda
    justo donde su página paralela la busca. De ahí salen las tres cosas que
    el rediseño cambió de lugar: el switch de la lámpara rota, la piedra que
    se va a (98,98), y **el cono apagado**, que ahora es una sustitución de
    tiles y se cuenta en `sub_n`.
    """
    una = hablarle_a_la_reja(partida(caso=MAPAS))
    assert not una.byte("sub_n"), (
        "el mapa arranca sin ninguna sustitución puesta, y `sub_n` dio %d"
        % una.byte("sub_n"))

    una.ir_al_mapa(11, *LUZ5)
    una.correr(10)
    for _ in range(40):
        una.correr(1)
        una.tocar("a")
        if una.byte("sub_n"):
            break

    assert una.byte("sub_n"), (
        "con la piedra en %s la página de Light5 tendría que haber apagado su "
        "cono con TileSubstitution, y no hay ninguna puesta. La piedra quedó "
        "en %s" % (LUZ5, celda_de(una, eventos_del_11, STONE)))
    assert una.switch(LAMPARA_ROTA), (
        "la lámpara tendría que haber quedado rota: es el switch %d, el mismo "
        "que en el original cambiaba su gráfico" % LAMPARA_ROTA)

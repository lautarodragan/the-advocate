"""`StoreTerrainID`: el terreno de una celda, guardado en una variable.

Lo que se le pregunta a la ROM es su RAM lejana, como en `test_variables.py`:
el terreno no se ve, así que ninguna golden lo cobraría.

**El mapa es el 5 y no es al azar**: de los cuarenta del cartucho de pruebas es
el único cuyo ChipSet tiene más de un terreno —cuatro: 1, 2, 9 y 10—, así que
es el único donde la respuesta puede estar mal sin que se note. En todos los
demás el terreno es 1 en todas partes, que es también lo que contesta un
ChipSet **sin** tabla de terrenos: la optimización de RPG_RT que
`GetTerrainTag` documenta. O sea que un caso en cualquier otro mapa daría
verde con la tabla leída al revés.

Los valores esperados no están escritos: salen del `.lmu` y del `.ldb` con
`rm2k.terreno_de`, que es la misma regla de la que salió la tabla que la ROM
lleva. Lo que esto compara es que el camino entero —conversor, bytecode,
intérprete y la tabla del banco 1— devuelva lo que dice el juego.

Lo que **no** cubre, y queda anotado en `UNTESTED.md`: que una
`TileSubstitution` puesta le cambie el terreno a la celda, que es lo que hace
`GetTerrainTag` al pasar por `map_info.lower_tiles`. Está implementado —el
terreno sale del bloque, y el bloque es el sustituido— pero ningún ChipSet del
juego tiene dos tiles sueltos con terrenos distintos, así que no hay con qué
escribir el caso sin inventar datos.
"""

import os

import pytest

from port import eventos
from rpgmaker import lcf, rm2k
from render.render_map import GAME_DIR

from tanda import partida

MAPA = 5
# Qué celda pregunta el caso y en qué variable de RM2k deja la respuesta. Las
# celdas son una de cada terreno del mapa, elegidas con
# `/extras/scratch/motor-tiles/terrenos.py`.
CELDAS = (((16, 18), 17), ((23, 25), 19), ((91, 43), 20), ((28, 9), 21))
# La que cae fuera del mapa, que es otra respuesta y no un error: RPG_RT
# contesta el terreno del **primer tile del ChipSet**.
AFUERA = 39
# Y la que el caso pide con la celda en dos variables —el `ValueOrVariable` de
# `CommandStoreTerrainID`—, que es (23,25) otra vez: la misma respuesta por el
# otro camino.
POR_VARIABLE = (23, 25), 40


def ranuras():
    return eventos.variables_de(GAME_DIR, None, ())


@pytest.fixture(scope="module")
def del_juego():
    """El mapa y su ChipSet, de donde salen los valores esperados."""
    base = lcf.Database(GAME_DIR)
    mapa = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % MAPA))
    return mapa, base.chipsets[mapa.chipset_id]


def terreno_en(del_juego, celda):
    mapa, chipset = del_juego
    x, y = celda
    return rm2k.terreno_de(chipset, mapa.lower_layer[y * mapa.width + x])


@pytest.fixture(scope="module")
def corrida():
    una = partida("terreno")
    una.correr(30)      # la página corre en el primer tick; treinta de aire
    return una


@pytest.mark.parametrize("celda,variable", CELDAS,
                         ids=["%d-%d" % c for c, _v in CELDAS])
def test_el_terreno_de_la_celda_es_el_del_juego(corrida, del_juego, celda,
                                                variable):
    esperado = terreno_en(del_juego, celda)
    assert corrida.variable(ranuras()[variable]) == esperado, (
        "la celda %s del mapa %d tiene terreno %d en el juego"
        % (celda, MAPA, esperado))


def test_los_cuatro_terrenos_del_mapa_no_son_el_mismo(del_juego):
    """Sin esto, los cuatro casos de arriba podrían pasar leyendo cualquier
    cosa: la tabla entera en 1 contesta bien las cuatro preguntas."""
    distintos = {terreno_en(del_juego, celda) for celda, _v in CELDAS}
    assert len(distintos) == len(CELDAS), (
        "las celdas del caso ya no tienen cuatro terrenos distintos sino %s; "
        "hay que volver a elegirlas" % sorted(distintos))


def test_fuera_del_mapa_contesta_el_del_primer_tile(corrida, del_juego):
    """`GetTerrainTag` no se cae ni contesta el de la celda más cercana: usa
    el índice 0 del ChipSet."""
    _mapa, chipset = del_juego
    assert corrida.variable(ranuras()[AFUERA]) == rm2k.terreno_de(chipset, 0)


def test_la_celda_por_variable_da_lo_mismo_que_escrita(corrida, del_juego):
    """El modo 1 lee x e y **al correr**, y tiene que dar lo mismo que el 0
    sobre la misma celda."""
    celda, variable = POR_VARIABLE
    assert corrida.variable(ranuras()[variable]) == terreno_en(del_juego,
                                                               celda)

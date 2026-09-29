"""Que `just video` pueda jugar las jugadas del recorrido.

`arnes/video.py` juega las funciones de `test_recorrido_golden.py` tal cual,
pasándoles su propia fábrica de `recorrido` en lugar del fixture del conftest.
Si las dos fábricas no aceptan lo mismo, o no arrancan en la misma página, el
video se rompe y la tanda no se entera, porque ninguna prueba corre
`video.py`: pasó con el mapa de debug (`991bf935`), que le hizo pedir `caso` a
la apertura —`TypeError`— y movió "Begin the Story" a la entrada del mapa, así
que `talan` se trababa en el 900.

No graba ni juega nada: arranca la partida con cada una de las dos fábricas y
compara dónde quedó. Es lo barato que cobra las dos cosas.
"""

import inspect

import pytest

import cartuchos
from recorrido import UN_ANO_DESPUES
import video

# Lo que las jugadas le pasan a la fábrica hoy: nada, switches, o el caso de
# la entrada al mapa de debug. Una forma nueva de pedir la partida entra acá.
PEDIDOS = [
    pytest.param({}, id="nada"),
    pytest.param({"switch": [UN_ANO_DESPUES]}, id="switch"),
]
if cartuchos.con_mapa_de_debug():
    PEDIDOS.append(pytest.param(
        {"caso": cartuchos.entrada_al_mapa_de_debug()}, id="caso"))


def test_la_fabrica_del_video_acepta_lo_mismo_que_la_del_conftest(recorrido):
    """Misma firma: un argumento nuevo en el conftest que las jugadas
    empiecen a usar pone esto en rojo antes que el video."""
    assert (inspect.signature(video.fabrica(cartuchos.RELEASE))
            == inspect.signature(recorrido))


@pytest.mark.parametrize("pedido", PEDIDOS)
def test_el_video_arranca_donde_el_recorrido(recorrido, pedido):
    # Sin MSU-1, como la tanda: lo que se compara es la página y el mapa, y
    # así las dos consolas son iguales salvo por la fábrica.
    de_la_prueba = recorrido("video", **pedido)
    del_video = video.fabrica(cartuchos.RELEASE, msu=False)("video", **pedido)
    assert ((del_video.p.caso, del_video.p.mapa(), del_video.celda())
            == (de_la_prueba.p.caso, de_la_prueba.p.mapa(),
                de_la_prueba.celda())), (
        "la fábrica de video.py arrancó en otra página que la del conftest. "
        "Video: %s. Prueba: %s." % (del_video.estado(), de_la_prueba.estado()))

"""Los mapas nuevos del final del capítulo, recién llegados.

Tasgarde (74), su laboratorio (85), el minijuego de Eisen (95), el puente del
norte (259) y lo que hay debajo (255): los que se caminan del hito 4 de
`workflow/tasks/*/el-mundo-y-lo-que-sigue.md`. Los de la historia de Eisen
(86 a 94, 99 a 102) no van: son cinemáticas que arrancan solas al llegar, y
los juega `test_recorrido_capitulo_golden.py`, que es también el que camina
de uno a otro.

Del 259 y del 255 se prende antes el switch que apaga su automática de
llegada —la charla de los guardias del puente, el cartel de los crujidos—,
para que la captura sea la del mapa y no la de un mensaje. Ninguno de los dos
dibuja su panorama: el port no dibuja ninguno, ver
`workflow/tasks/wishlist/panorama-del-mapa-2.md`.
"""

import pytest

from tanda import golden, partida

TALAN = 14
# Lo que tarda en asentarse la llegada, con margen.
LLEGAR_TICKS = 40

# La charla de los guardias del 259 (su evento 10) y el cartel de los
# crujidos del 255 (su evento 1).
YA_HABLARON_LOS_GUARDIAS = 850
YA_SE_LEYO_EL_CARTEL = 848

LLEGADAS = (
    ("capitulo-74-llegada", 74, (19, 48), ()),
    ("capitulo-85-llegada", 85, (9, 26), ()),
    ("capitulo-95-llegada", 95, (11, 39), ()),
    ("capitulo-259-llegada", 259, (68, 10), (YA_HABLARON_LOS_GUARDIAS,)),
    ("capitulo-255-llegada", 255, (71, 7), (YA_SE_LEYO_EL_CARTEL,)),
)


@pytest.mark.parametrize("nombre,mapa,celda,prendidos", LLEGADAS,
                         ids=[n for n, _m, _c, _s in LLEGADAS])
def test_recien_llegado(nombre, mapa, celda, prendidos):
    p = partida("en-5", switches=prendidos)
    p.poner_grupo(TALAN)
    p.ir_al_mapa(mapa, *celda)
    p.correr(LLEGAR_TICKS)
    assert p.mapa() == mapa and p.heroe() == celda, (
        "pedí el %d en %s y la partida está en el %d, en %s"
        % (mapa, celda, p.mapa(), p.heroe()))
    assert not p.corriendo_una_pagina(), (
        "a los %d ticks de llegar al %d sigue corriendo una página"
        % (LLEGAR_TICKS, mapa))
    golden(nombre, p.imagen())
    malas, _ = p.celdas_mal_dibujadas()
    assert not malas, "%d celdas mal dibujadas en el %d: %s" % (
        len(malas), mapa, malas[:12])

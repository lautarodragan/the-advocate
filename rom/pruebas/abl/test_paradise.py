"""El camino a Paradise recién llegado: Mountain Path (105), la amnistía
(106) y el túnel (107).

El 106 y el 107 arrancan con una escena al llegar —la amnistía, Isabella—,
así que se llega con la escena ya vista: el switch que la apaga prendido
(331 y 332). El 105 se camina tal cual. Las escenas las juega
`test_recorrido_paradise_golden.py`. Ver
`workflow/tasks/*/mundo-7-camino-a-paradise.md`.

Se llega a donde deja el juego: al 105 desde el túnel del mundo (66 ev18), al
106 desde el 105, y al 107 desde el 106.
"""

import pytest

from tanda import golden, partida

TALAN = 14
LLEGAR_TICKS = 40

LLEGADAS = (
    ("paradise-105-llegada", 105, (68, 19), ()),
    ("paradise-106-llegada", 106, (10, 13), (331,)),
    ("paradise-107-llegada", 107, (1, 8), (332,)),
)


@pytest.mark.parametrize("nombre,mapa,celda,vistas", LLEGADAS,
                         ids=[n for n, _m, _c, _v in LLEGADAS])
def test_recien_llegado(nombre, mapa, celda, vistas):
    p = partida("en-5", switches=vistas)
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

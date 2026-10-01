"""Tangle Forest recién llegado: el bosque (310) y el claro (311).

Los dos que se caminan sin que nada arranque al llegar. El tram (313) y el
bosque en llamas (312) son cinemáticas, o un mapa donde el fuego da Game Over
con el cronómetro en cero: los juega `test_recorrido_tangle_golden.py`. Ver
`workflow/tasks/*/mundo-5-tangle-forest.md`.

Se llega a donde deja el juego: al 310 desde la entrada del mundo, el 66
ev19, y al 311 desde la salida del norte del bosque.
"""

import pytest

from tanda import golden, partida

TALAN = 14
LLEGAR_TICKS = 40

LLEGADAS = (
    ("tangle-310-llegada", 310, (48, 22)),
    ("tangle-311-llegada", 311, (10, 13)),
)


@pytest.mark.parametrize("nombre,mapa,celda", LLEGADAS,
                         ids=[n for n, _m, _c in LLEGADAS])
def test_recien_llegado(nombre, mapa, celda):
    p = partida("en-5")
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

"""Sorbe y la casa de Vago recién llegados, y la ventana en el reparto de la
capa de encima de 256.

Sorbe Village, el mapa 69, es el que estrena `LAYOUT_WINDOW_ABOVE`: la base
de BG2 en $5000, 157 tiles en la capa de encima, y la ventana de mensaje en
los índices 256 a 511 de BG2 y no en los 128 a 383 de los otros repartos. Sus
celdas salen de otro plano, `window_cells_256`, y si `stamp_window`
eligiera el equivocado la ventana saldría con los tiles de la capa de encima:
eso lo cobra `sorbe-69-mensaje`.

La montaña (76) y la casa de Vago (81) van porque son mapas nuevos del mismo
tramo, en los repartos de siempre. Se llega con `ir_al_mapa`; el camino entre
ellos lo juega `test_recorrido_sorbe_golden.py`.
"""

import pytest

from tanda import golden, partida

TALAN = 14
# Lo que tarda en asentarse la llegada, con margen.
LLEGAR_TICKS = 40

LLEGADAS = (
    ("sorbe-69-llegada", 69, (20, 38)),
    ("sorbe-76-llegada", 76, (13, 48)),
    ("sorbe-81-llegada", 81, (9, 13)),
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


def test_la_ventana_en_sorbe():
    """`sorbe-69-mensaje`: un mensaje en el 69, con la ventana armada desde el
    plano de la capa de encima de 256."""
    p = partida("sorbe-mensaje")
    for _ in range(600):
        if p.byte("msg_open") and p.byte("msg_state") != 1:
            break
        p.correr(1)
    else:
        raise AssertionError("el mensaje del caso no se abrió en 600 ticks")
    assert p.mapa() == 69, p.mapa()
    golden("sorbe-69-mensaje", p.imagen())

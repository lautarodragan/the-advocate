"""Yun Town y Drust Camp: lo opcional del mundo, recién llegado.

Los dos cuelgan del 66 y nada del camino principal depende de ellos. Yun Town
(67) tiene la armería, la posada, la casa del alcalde y la fiambrería (70 a
73); Drust Camp (68) las minas (103), el ring (199), la taberna (200) y la
tienda de Net (201), que tiene clave: la juega `rpgmaker/test_numero.py`.
Ver `workflow/tasks/*/mundo-6-yun-y-drust.md`.

Se llega a donde deja el juego: al pueblo desde su entrada del mundo, y a las
minas desde su boca en el campamento.
"""

import pytest

from tanda import golden, partida

TALAN = 14
LLEGAR_TICKS = 40
EL_MUNDO = 66

LLEGADAS = (
    ("yun-67-llegada", 67, (1, 17)),
    ("drust-68-llegada", 68, (48, 14)),
    ("drust-103-llegada", 103, (11, 73)),
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


# Las entradas del mundo: la celda de al lado, hacia dónde se camina, y a
# dónde lleva. Son el 66 ev9 y el ev11, que no compilaban mientras el pueblo
# no estaba en el cartucho; las salidas de los pueblos dejan al héroe en esa
# misma celda de al lado.
ENTRADAS = (
    ("yun", (92, 38), "right", 67, (1, 17)),
    ("drust", (30, 7), "left", 68, (48, 14)),
)


@pytest.mark.parametrize("al_lado,hacia,mapa,celda",
                         [e[1:] for e in ENTRADAS],
                         ids=[e[0] for e in ENTRADAS])
def test_se_entra_desde_el_mundo(al_lado, hacia, mapa, celda):
    p = partida("en-5")
    p.poner_grupo(TALAN)
    p.ir_al_mapa(EL_MUNDO, *al_lado)
    p.sostener(20, hacia)
    p.soltar()
    p.correr(LLEGAR_TICKS)
    assert p.mapa() == mapa and p.heroe() == celda, (
        "desde %s del mundo hacia %s, la partida está en el %d, en %s"
        % (al_lado, hacia, p.mapa(), p.heroe()))

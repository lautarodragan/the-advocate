"""`--caso`: varias páginas de prueba en un solo cartucho, elegidas al correr.

Es el corte 2 del paso 9d. Cada caso es una página del evento de prueba y la
elige una variable que el arnés escribe antes del primer cuadro; ver
`eventos.VARIABLE_DE_CASO`.

Lo que se compara es lo más fuerte que hay a mano: **la golden que ese mismo
caso ya tiene en su cartucho propio**. Si la página de un caso corriera la de
otro, o si las páginas de los demás cambiaran algo de lo que se ve, la captura
no sería esa.
"""

import pytest

from tanda import cartucho, golden, partida
from test_tanda_paginas import ANIMACIONES, PANEOS

# Cuatro casos del mapa 6 que no piden nada del cartucho aparte del mapa: dos
# animaciones y dos paneos, que son páginas bien distintas. Cada uno es
# (nombre, los cuadros de su golden), sacados de la tupla de su prueba para no
# copiarlos; el nombre es también el de su página en `pruebas/casos/`.
_CUADROS = {c[0]: c[1] for c in ANIMACIONES + PANEOS}
CASOS = tuple((n, _CUADROS[n]) for n in ("animacion", "animacion-dibujo",
                                         "pan", "pan-vuelve"))


def _cartucho():
    return cartucho("casos", "--map-id", "6",
                    caso=tuple(nombre for nombre, _ in CASOS))


@pytest.mark.parametrize("k", range(len(CASOS)),
                         ids=[caso[0] for caso in CASOS])
def test_cada_caso_da_la_golden_de_su_cartucho_propio(k):
    nombre, cuadros = CASOS[k]
    sfc, simbolos, mapas = _cartucho()
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas, caso=k)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())

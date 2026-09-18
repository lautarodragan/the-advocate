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

from consola import flags_de_grupo
from tanda import GRUPO, cartucho, golden, partida
from test_tanda_paginas import ANIMACIONES, PANEOS

# Cuatro casos del mapa 6 que no piden nada del cartucho aparte del mapa: dos
# animaciones y dos paneos, que son páginas bien distintas. Cada uno es
# (nombre, sus flags, los cuadros de su golden), sacados de la tupla de su
# prueba para no copiarlos.
_ANIM = {c[0]: c for c in ANIMACIONES}
_PAN = {c[0]: c for c in PANEOS}
CASOS = tuple(
    [(n, ("--animacion-de-prueba", *_ANIM[n][1].split(),
          "--pagina-de-prueba", "0", "0", "0", "50"), _ANIM[n][2])
     for n in ("animacion", "animacion-dibujo")]
    + [(n, ("--pan-de-prueba", *_PAN[n][1].split(),
            "--pagina-de-prueba", "0", "0", "0", "50"), _PAN[n][2])
       for n in ("pan", "pan-vuelve")])


def _cartucho():
    flags = ["--map-id", "6", *CASOS[0][1]]
    for _, suyos, _ in CASOS[1:]:
        # Cada `--caso` lleva su grupo: es un flag del caso, porque lo arma su
        # página. `cartucho` sólo se lo pone al primero.
        flags += ["--caso", *flags_de_grupo(GRUPO.split()), *suyos]
    return cartucho("casos", *flags)


@pytest.mark.parametrize("k", range(len(CASOS)),
                         ids=[caso[0] for caso in CASOS])
def test_cada_caso_da_la_golden_de_su_cartucho_propio(k):
    nombre, _, cuadros = CASOS[k]
    sfc, simbolos, mapas = _cartucho()
    for cuadro in cuadros:
        p = partida(sfc, simbolos, mapas, caso=k)
        p.correr(cuadro)
        golden("%s-%d" % (nombre, cuadro), p.imagen())

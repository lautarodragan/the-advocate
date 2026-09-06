"""Las piezas compartidas de las pruebas de estado.

Armar una ROM cuesta unos tres segundos —el conversor lee el mapa, los tiles y
las paletas— así que se cachea por configuración: dos pruebas que pidan los
mismos mapas y los mismos switches comparten el build.

Lo que **no** se comparte es la partida: cada prueba arranca su propia consola
desde el reset. Compartirla dejaría a una prueba corriendo sobre el estado que
dejó otra, que es la clase de error que este repo ya cobró con `mapdata.inc`.
"""

import os

import pytest

from consola import Partida, armar


@pytest.fixture(scope="session")
def builds():
    """Las ROMs ya armadas, por configuración."""
    return {}


@pytest.fixture
def partida(builds):
    """Devuelve una fábrica: `partida(map_id=5, mapas=[3, 6], switch=[16])`."""
    abiertas = []

    def hacer(map_id, mapas=(), switch=(), con_ventana=True):
        clave = (map_id, tuple(mapas), tuple(switch), con_ventana)
        if clave not in builds:
            destino = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "rom", "build", "pruebas",
                "m%s-%s-s%s%s" % (map_id, "_".join(str(m) for m in mapas) or "0",
                                  "_".join(str(s) for s in switch) or "0",
                                  "-v" if con_ventana else ""))
            builds[clave] = armar(map_id, mapas, switch, con_ventana, destino)
        sfc, simbolos, tabla = builds[clave]
        una = Partida(sfc, simbolos, tabla)
        abiertas.append(una)
        return una

    yield hacer

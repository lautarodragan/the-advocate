"""Las piezas compartidas de las pruebas de estado.

**La ROM no cambia entre prueba y prueba.** Lo que cambia es el estado inicial,
y eso se escribe en la RAM —ver `Partida.prender`— o lo pone el caso, en vez de
hornearse en un cartucho distinto para cada prueba. Desde el paso 9f el
cartucho es el mismo que usa la tanda —ver `pruebas/arnes/cartuchos.py`— y las
pruebas no arman nada: piden un caso por el nombre.

Una prueba que no pide ninguno arranca en el mapa 5 con el grupo del juego, que
es `en-5`: la prueba del recuerdo tiene una lista de toques de A afinada al
cuadro y conviene no moverle el arranque. Las demás llegan a su mapa con un
caso `en-<mapa>`, o con `Partida.ir_al_mapa`, que le pide a la ROM el mismo
fundido que una puerta.

Lo que **no** se comparte es la partida: cada prueba arranca su propia consola
desde el reset. Compartirla dejaría a una corriendo sobre lo que dejó otra, que
es la clase de error que este repo ya cobró con `mapdata.inc`.
"""

import os
import sys

import pytest

# El arnés vive en `arnes/` y las pruebas en una carpeta por lo que prueban,
# así que ninguna lo tiene al lado: este archivo es el que queda arriba de
# todas, y pytest lo carga antes que a cualquiera de ellas.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "arnes"))

import tanda                                                 # noqa: E402
import cartuchos                                             # noqa: E402

# Dónde arranca una prueba de estado que no pide otra cosa: el mapa 5, con el
# grupo del juego. Es el caso `en-5`, el `Teleport` a la celda donde el héroe
# caía cuando el 5 era el mapa de arranque de su cartucho.
ARRANQUE = "en-5"
# Y el mapa 2 solo: el Linkage Block entero. Sus dos cuartos parecen dos mapas
# jugando pero son el mismo, y se cruzan con teletransportes internos. Ver
# `test_puerta_misma.py`.
LINKAGE = "en-2"


@pytest.fixture
def partida():
    """Una fábrica: `partida()`, o `partida(switch=[16])`.

    Devuelve la partida arrancada en el caso que se pida —`en-5` si no se
    pide ninguno—. `switch` se escribe en la RAM antes del primer cuadro de
    juego; para ir a otro mapa, `.ir_al_mapa(...)`. Con `titulo` la partida
    es la de `release`, la ROM que se juega, que es la que lleva la pantalla
    de título; ahí no hay casos, porque una ROM que se entrega no lleva
    páginas de prueba.
    """
    def hacer(switch=(), caso=None, titulo=None, en=None):
        if titulo is not None:
            en = en or cartuchos.RELEASE
        if en == cartuchos.RELEASE:
            assert caso is None, (
                "`release` no lleva páginas de prueba, así que no tiene el "
                "caso %r" % caso)
            return tanda.partida(None, en=en, switches=switch, titulo=titulo)
        return tanda.partida(caso or ARRANQUE, en=en, switches=switch,
                             titulo=titulo)

    return hacer


# Dónde quedan las capturas de cada hito de las pruebas que **juegan**, una
# carpeta por tramo. Las goldens de `pruebas/golden/recorrido/<tramo>/` se
# buscan por ese mismo nombre: ver `Recorrido.foto`.
FOTOS = os.path.join(tanda.RAIZ, "rom", "build", "pruebas", "recorrido")

# "Begin the Story", la primera opción de la pantalla de título, que
# `release` lleva delante. Una jugada empieza por ahí como la empieza
# cualquiera.
EMPEZAR = 0


# Las dos que siguen **importan `recorrido` adentro** y no arriba, y no es
# descuido: ese módulo arrastra el lector de `.lmu` y el renderer, y eso no
# tiene por qué pagarlo cada prueba que no juega —este conftest lo carga
# pytest antes que cualquiera—. Vivían en un `conftest.py` de `pruebas/abl/`
# hasta el 2026-09-23, y eso duró una corrida: acá no hay paquetes, así que los
# dos conftest se importan los dos como `conftest` y el segundo tapa al
# primero. `test_batalla.py` hace `from conftest import LINKAGE` y cinco
# módulos se cayeron con `ImportError`.
@pytest.fixture(scope="session")
def mundo():
    """La colisión y los teletransportes del juego original, una vez por
    corrida: leer los `.lmu` y resolverles los cuatro bits a cada celda cuesta
    más que todo el BFS que viene después."""
    from recorrido import Mundo
    return Mundo()


@pytest.fixture
def recorrido(partida, mundo):
    """Una jugada sobre `release`, la ROM que se juega, entrando por la
    pantalla de título, con sus capturas en `FOTOS/<nombre>`."""
    from recorrido import Recorrido

    def hacer(nombre, switch=()):
        return Recorrido(partida(switch=switch, titulo=EMPEZAR),
                         mundo, fotos=os.path.join(FOTOS, nombre))
    return hacer


@pytest.fixture
def con_musica(recorrido):
    """Una fábrica: `con_musica()` es la apertura de `release` jugada hasta
    que Kersh toma el control, con su tema sonando.

    Es el primer lugar de la ROM que se juega con música y con el control:
    después de "Begin the Story" no suena nada —el tema del título se corta y
    el mapa 4 no trae uno— hasta que la apertura pone el suyo, y el héroe no
    se mueve hasta que termina. Hasta el 2026-09-24 las pruebas de música
    tenían eso gratis: corrían en `juego`, que arrancaba con un tema puesto.
    """
    def hacer():
        r = recorrido("con-musica")
        r.esperar("que la apertura termine y Kersh tome el control",
                  lambda p: p.switch(3) and not p.corriendo_una_pagina(),
                  tope=6000)
        return r.p
    return hacer

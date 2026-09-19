"""Las piezas compartidas de las pruebas de estado.

**La ROM no cambia entre prueba y prueba.** Lo que cambia es el estado inicial,
y eso se escribe en la RAM —ver `Partida.prender`— o lo pone el caso, en vez de
hornearse en un cartucho distinto para cada prueba. Desde el paso 9f el
cartucho es el mismo que usa la tanda —ver `pruebas/cartuchos.py`— y las
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

import pytest

import tanda

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
    pasa la pantalla de título del cartucho `titulo`, que es el único que
    la lleva.
    """
    def hacer(switch=(), caso=None, titulo=None, en=None):
        if titulo is not None:
            # El título va en su propio cartucho, que es el de pruebas con
            # la pantalla de título delante; ahí el caso que no pide nada es
            # `nada`, que deja el grupo del juego en el mapa de arranque.
            en = en or "titulo"
            caso = caso or "nada"
        return tanda.partida(caso or ARRANQUE, en=en, switches=switch,
                             titulo=titulo)

    return hacer

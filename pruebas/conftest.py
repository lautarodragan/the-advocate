"""Las piezas compartidas de las pruebas de estado.

**La ROM no cambia entre prueba y prueba.** Lo que cambia es el estado inicial,
y eso se escribe en la RAM —ver `Partida.prender`— en vez de hornearse en un
cartucho distinto para cada caso. Así dos pruebas que necesitan los mismos mapas
comparten el mismo build, y el build sobrevive entre corridas: sólo se rehace
cuando cambia algo de lo que participa en armarlo, que es lo que mira `huella`.

Hoy alcanza **una** ROM para todas las pruebas de estado: los mapas 5, 3, 6, 7
y 4, que es la cadena del juego.

Arranca en el 5 porque la prueba del recuerdo tiene una lista de toques de A
afinada al cuadro y conviene no moverle el arranque. Las demás llegan a su mapa
con `Partida.ir_al_mapa`, que le pide a la ROM el mismo fundido que una puerta.

Ese segundo no es capricho: el conversor se niega a poner la ventana de mensaje
en un mapa que no le deja 8 KB de tiles y 2 de tilemap, y el 66 es uno de ésos.

**Y una tercera, que es la cara**: la del recorrido largo, con los ocho mapas de
la cadena que se juega —ver `test_recorrido.py`—. Vale la pena saber cuánto
cuesta cada una: armar la del recorrido son unos veinte segundos de conversión y
cinco de ensamblado, contra los tres segundos que tarda en jugarse entera. Por
eso lleva ocho mapas y no los veintinueve de `demo-ciudad`, que son dos minutos.

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
    pasa la pantalla de título del cartucho del juego, que es el único que
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

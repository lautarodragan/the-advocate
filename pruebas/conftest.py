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

import os

import pytest

from consola import Partida, armar

# Los mapas que lleva la ROM de siempre. Agregar uno acá es más barato que armar
# un cartucho nuevo, mientras entre: son 512 KB y los mapas grandes pesan más de
# cien. Hasta el 2026-09-17 había otra, sin ventana, en el mapa 66: la ventana
# pasó a ser obligatoria y el 66 no la puede llevar.
MAPAS = (5, [3, 6, 7, 4])
# Y una tercera, con el mapa 2 solo: el Linkage Block entero. Sus dos cuartos
# parecen dos mapas jugando pero son el mismo, y se cruzan con teletransportes
# internos, así que para probarlos no hace falta ningún otro mapa. Ver
# `test_puerta_misma.py`.
LINKAGE = (2, [])


@pytest.fixture(scope="session")
def builds():
    """Las ROMs ya armadas, por configuración."""
    return {}


@pytest.fixture
def partida(builds):
    """Una fábrica: `partida()`, o `partida(switch=[16])`.

    Devuelve la partida arrancada en el primer mapa de la ROM que corresponda.
    `switch` se escribe en la RAM antes del primer cuadro de juego; para
    empezar en otro mapa, `.ir_al_mapa(...)`.
    """
    def hacer(switch=(), mapas=None, descartar=False, titulo=None, tema=None,
              timer=False, encuentros=0, caso=None):
        arranca, resto = mapas or MAPAS
        clave = (arranca, tuple(resto), descartar, titulo is not None, tema,
                 timer, encuentros, caso)
        if clave not in builds:
            destino = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "rom", "build", "pruebas",
                "m%s-%s%s%s" % (arranca, "_".join(str(m) for m in resto) or "0",
                                "-v",
                                ("-t" if titulo is not None else "")
                                + ("-" + tema if tema else "")
                                + ("-c" if timer else "")
                                + ("-e%d" % encuentros if encuentros else "")
                                + ("-" + caso if caso else "")))
            builds[clave] = armar(arranca, resto, destino, descartar,
                                  titulo is not None, tema, timer, encuentros,
                                  caso)
        sfc, simbolos, tabla = builds[clave]
        return Partida(sfc, simbolos, tabla, switch, titulo)

    return hacer

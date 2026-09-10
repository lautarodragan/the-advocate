"""Las piezas compartidas de las pruebas de estado.

**La ROM no cambia entre prueba y prueba.** Lo que cambia es el estado inicial,
y eso se escribe en la RAM —ver `Partida.prender`— en vez de hornearse en un
cartucho distinto para cada caso. Así dos pruebas que necesitan los mismos mapas
comparten el mismo build, y el build sobrevive entre corridas: sólo se rehace
cuando cambia algo de lo que participa en armarlo, que es lo que mira `huella`.

Hoy alcanzan **dos** ROMs para todas las pruebas:

    con ventana    los mapas 5, 3, 6, 7 y 4, que es la cadena del juego
    sin ventana    el mapa 66, que gasta demasiados tiles para llevarla

Arranca en el 5 porque la prueba del recuerdo tiene una lista de toques de A
afinada al cuadro y conviene no moverle el arranque. Las demás llegan a su mapa
con `Partida.ir_al_mapa`, que le pide a la ROM el mismo fundido que una puerta.

Ese segundo no es capricho: el conversor se niega a poner la ventana de mensaje
en un mapa que no le deja 8 KB de tiles y 2 de tilemap, y el 66 es uno de ésos.

Lo que **no** se comparte es la partida: cada prueba arranca su propia consola
desde el reset. Compartirla dejaría a una corriendo sobre lo que dejó otra, que
es la clase de error que este repo ya cobró con `mapdata.inc`.
"""

import os

import pytest

from consola import Partida, armar

# Los mapas que llevan las dos ROMs. Agregar uno acá es más barato que armar un
# cartucho nuevo, mientras entre: son 512 KB y los mapas grandes pesan más de
# cien.
CON_VENTANA = (5, [3, 6, 7, 4])
SIN_VENTANA = (66, [])
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
    def hacer(switch=(), con_ventana=True, rama=(), mapas=None,
              descartar=False, guardar=0, titulo=None, tema=None,
              variables=(), rama_var=()):
        arranca, resto = mapas or (CON_VENTANA if con_ventana else SIN_VENTANA)
        clave = (arranca, tuple(resto), con_ventana, tuple(rama), descartar,
                 guardar, titulo is not None, tema, tuple(variables),
                 tuple(rama_var))
        if clave not in builds:
            destino = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "rom", "build", "pruebas",
                "m%s-%s%s%s" % (arranca, "_".join(str(m) for m in resto) or "0",
                                "-v" if con_ventana else "",
                                ("-r" + "_".join(str(n) for n in rama)
                                 if rama else "")
                                + ("-g%d" % guardar if guardar else "")
                                + ("-t" if titulo is not None else "")
                                + ("-" + tema if tema else "")
                                + ("-v" + "_".join(str(n) for n in variables)
                                   if variables else "")
                                + ("-rv" + "_".join(str(n) for n in rama_var)
                                   if rama_var else "")))
            builds[clave] = armar(arranca, resto, con_ventana, destino, rama,
                                  descartar, guardar, titulo is not None, tema,
                                  variables, rama_var)
        sfc, simbolos, tabla = builds[clave]
        return Partida(sfc, simbolos, tabla, switch, titulo)

    return hacer

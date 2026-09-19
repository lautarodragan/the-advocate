"""La velocidad del héroe: que el pad camine a la que dejó la última ruta.

Lo que se ve de una ruta con 28 o 29 lo cobra la tanda —`ruta-vel` y
`ruta-vel-lenta` en `pruebas/*/test_tanda*.py`, cuadro por cuadro—. Lo que la tanda no
puede es apretar una dirección después de una ruta, así que acá se le escribe
al héroe la velocidad que una ruta le habría dejado y se lo hace caminar con el
pad. La cuenta de dónde tiene que estar es la de RM2k: 256 unidades por celda a
`PASO_POR_VELOCIDAD` por cuadro, y los pixeles que faltan son las unidades que
faltan sobre dieciséis, que es lo que `advance_step` hace con `step_left >> 3`
sobre medias unidades.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))
import eventos                                          # noqa: E402


def donde_queda(tile_y, velocidad, cuadros):
    """hero_y tras `cuadros` cuadros **subiendo** desde la celda `tile_y`: en
    el mapa de arranque de las pruebas, hacia abajo hay pared."""
    paso = eventos.PASO_POR_VELOCIDAD[velocidad - 1]
    unidades = cuadros * paso
    celdas, resto = divmod(unidades, eventos.SALTO_PASO)
    if resto:
        celdas += 1
        faltan = (eventos.SALTO_PASO - resto) >> 4
    else:
        faltan = 0
    return (tile_y - celdas) * 16 + faltan


def test_arranca_a_la_velocidad_normal(partida):
    una = partida()
    assert una.velocidad_del_heroe() == 4


def test_el_pad_camina_a_la_velocidad_que_dejo_la_ruta(partida):
    """A velocidad 2 el héroe avanza medio pixel por cuadro y tarda 32 cuadros
    por celda; a la 5, cuatro pixeles y cuatro cuadros; a la 1, un cuarto
    de pixel y 64 cuadros."""
    # Dos celdas arriba hay pared, así que ninguna cuenta pasa de ahí.
    for velocidad, cuadros in ((1, 20), (2, 10), (2, 40), (5, 3), (6, 3)):
        una = partida()
        una.correr(5)
        y0 = una.palabra("tile_y")
        una.poner_velocidad_del_heroe(velocidad)
        una.sostener(cuadros, "up")
        assert una.palabra("hero_y") == donde_queda(y0, velocidad, cuadros), (
            "a velocidad %d, tras %d cuadros subiendo desde la celda %d el "
            "héroe está en y=%d y RM2k lo tiene en %d"
            % (velocidad, cuadros, y0, una.palabra("hero_y"),
               donde_queda(y0, velocidad, cuadros)))
        una.soltar()


def test_la_velocidad_viaja_en_la_partida(partida):
    una = partida(caso="guardar-198")
    una.poner_velocidad_del_heroe(2)
    una.guardar_en(0)
    una.reiniciar()
    assert una.velocidad_del_heroe() == 2, (
        "la velocidad del héroe no volvió de la SRAM: el reset la pone en 4 y "
        "la partida tenía 2")

"""El menú de pausa, la lista de ítems y la pantalla del equipo, contra sus
goldens: abiertos, y el mapa de vuelta al cerrarlos.

Corren con el reloj en cuadros de hardware, porque adentro del menú no hay
ticks: el arnés
está explicado en `test_batalla_golden.py`.
"""

import pytest

from tanda import consola_cruda, correr_hardware, golden, partida


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("menu", 52, ("b:40",)),
    ("menu-2", 62, ("b:40", "down:52", "down:56")),
))
def test_menu(nombre, cuantos, toques):
    """`menu`: el menú de pausa, abierto con B desde el mapa."""
    consola = consola_cruda("grupo-11-en-73")
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("cuadro", (50, 120))
def test_menu_vuelve(cuadro):
    """`menu`: el mapa de vuelta al cerrar el menú de pausa."""
    p = partida("grupo-11-en-73")
    p.correr(cuadro, toques_hardware=("b:40", "b:52"))
    golden("menu-vuelve-%d" % cuadro, p.imagen())


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("items", 64, ("b:40", "a:52")),
    ("items-2", 74, ("b:40", "a:52", "down:64", "down:68")),
))
def test_items(nombre, cuantos, toques):
    """`items`: la lista de ítems del menú de pausa.

    Tres ítems distintos y uno de ellos repetido trece veces, que es lo que
    ejercita la columna de la cuenta además de la de los nombres.
    """
    consola = consola_cruda("items")
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("cuadro", (60, 120))
def test_items_vuelve(cuadro):
    """`items`: el mapa de vuelta al cerrar la lista de ítems."""
    p = partida("items")
    p.correr(cuadro, toques_hardware=("b:40", "a:52", "down:64", "down:68",
                                      "a:74"))
    golden("items-vuelve-%d" % cuadro, p.imagen())


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("equipo", 84, ("b:40", "down:52", "down:56", "a:60", "a:72")),
    # La lista de lo que se puede equipar en esa ranura, que es el otro camino:
    # la pantalla del equipo con el cursor adentro de la lista.
    ("equipo-lista", 124, ("b:40", "down:52", "down:56", "a:60", "a:72",
                           "a:92", "down:112")),
))
def test_equipo(nombre, cuantos, toques):
    """`equipo`: la pantalla del equipo de un actor."""
    consola = consola_cruda("equipo")
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("cuadro", (60, 120))
def test_equipo_vuelve(cuadro):
    """`equipo`: el mapa de vuelta, con tres B para salir de los tres
    niveles de menú."""
    p = partida("equipo")
    p.correr(cuadro, toques_hardware=("b:40", "down:52", "down:56", "a:60",
                                      "a:72", "a:92", "b:112", "b:132",
                                      "b:152"))
    golden("equipo-vuelve-%d" % cuadro, p.imagen())

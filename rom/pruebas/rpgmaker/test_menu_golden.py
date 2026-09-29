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


def test_menu_grupo():
    """`menu-grupo`: tres filas, con la experiencia de cada una —la línea que
    va en sprites— en cinco, cuatro y dos cifras: Kersh en el 20, Core en el
    15 y Talan en el 1, que arranca con cero."""
    consola = consola_cruda("menu-grupo")
    correr_hardware(consola, 52, toques_hardware=("b:40",))
    golden("menu-grupo", consola.imagen())


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("fin", 64, ("b:40", "up:52", "a:56")),
    ("fin-no", 70, ("b:40", "up:52", "a:56", "down:64")),
))
def test_fin(nombre, cuantos, toques):
    """`fin`: End Game, la última orden del menú —arriba desde la primera da
    la vuelta—, con el cursor en "Yes", como entra, y en "No". Lo que hace
    cada una lo mira `test_fin_del_juego.py`."""
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
    ("items-gris", 70, ("b:40", "a:52", "down:64")),
))
def test_items(nombre, cuantos, toques):
    """`items`: la lista de ítems del menú de pausa.

    Tres ítems distintos y uno de ellos repetido trece veces, que es lo que
    ejercita la columna de la cuenta además de la de los nombres. Las
    ventanas y el cursor son los del System: en `items-gris` el cursor está
    sobre el Club, que va en gris, con su descripción arriba.
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
    # Antes de la pantalla, la elección de a quién equipar: la de la
    # medicina, sin las ventanas del ítem.
    ("equipo-a-quien", 70, ("b:40", "down:52", "down:56", "a:60")),
    # La barra sobre una ranura que no es la primera: la cabeza.
    ("equipo-ranura", 104, ("b:40", "down:52", "down:56", "a:60", "a:72",
                            "down:88", "down:92", "down:96")),
))
def test_equipo(nombre, cuantos, toques):
    """`equipo`: la pantalla del equipo de un actor. Las ventanas y el cursor
    son los del System, como en la de ítems: la barra marca la ranura, o lo
    que se elige en la lista."""
    consola = consola_cruda("equipo")
    correr_hardware(consola, cuantos, toques_hardware=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("nombre,cuantos,toques", (
    # La armadura: el Leather Jacket en vez del Trenchcoat baja la defensa y
    # sube la agilidad —el Trenchcoat resta 3—, y el ataque y la mente quedan
    # igual. Son los tres colores de `GetNewParameterColor` a la vez.
    ("equipo-sube-baja", 116, ("b:40", "down:52", "down:56", "a:60", "a:72",
                               "down:88", "down:92", "a:100")),
    # El casco, con la ranura vacía: sólo sube la defensa.
    ("equipo-sube", 120, ("b:40", "down:52", "down:56", "a:60", "a:72",
                          "down:88", "down:92", "down:96", "a:104")),
))
def test_equipo_colores(nombre, cuantos, toques):
    """`equipo-colores`: el valor que quedaría, en el color que dice si sube,
    baja o queda igual."""
    consola = consola_cruda("equipo-colores")
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

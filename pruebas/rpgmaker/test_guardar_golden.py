"""La pantalla de ranuras de guardar, contra sus goldens: abierta desde el
save point, y el mapa de vuelta al cerrarla.

Estuvo en `test_tanda_pantallas.py` hasta el 2026-09-25. Corre con el reloj
en cuadros de hardware, porque adentro de la pantalla no hay ticks: el arnés
está explicado en `test_batalla_golden.py`. Lo que se guarda lo mira
`test_guardar.py`.
"""

import pytest

from tanda import consola_cruda, correr_hardware, golden, partida


@pytest.mark.parametrize("nombre,cuantos,toques", (
    ("guardar", 130, ()),
    # El cursor dos ranuras más abajo, que es lo único que ejercita el DMA del
    # otro tilemap; y de paso cobra que sostener abajo no baje un renglón por
    # cuadro, porque estos menús miran **flancos**.
    ("guardar-2", 140, ("down:130", "down:134")),
))
def test_guardar_pantalla(nombre, cuantos, toques):
    """`guardar`: la pantalla de ranuras abierta desde el save point.

    Las cuatro ranuras salen vacías porque la SRAM del emulador arranca virgen.
    La variante "llena" no la cubre esta tanda —haría falta precargar un
    `.srm`— y la cubren las pruebas de estado, que sí pueden guardar antes de
    mirar.

    Del arnés: los toques van con el nombre `toques` y no `toques_hardware`
    porque así los pasaba la receta, y eso les corre el cuadro en uno. Ver la
    cabecera de este archivo.
    """
    consola = consola_cruda("guardar")
    correr_hardware(consola, cuantos, toques=toques)
    golden(nombre, consola.imagen())


@pytest.mark.parametrize("cuadro", (122, 200))
@pytest.mark.parametrize("nombre,toques", (
    # Con B se sale sin guardar y con A se guarda: de vuelta en el mapa las dos
    # tienen que dar la misma pantalla, porque **guardar no cambia un pixel**.
    # Por eso los dos comparten golden en la receta y acá comparten tabla.
    ("guardar-vuelve", ("down:130", "down:134", "b:138")),
    ("guardar-elige", ("down:130", "a:134")),
))
def test_guardar_vuelve(nombre, toques, cuadro):
    """`guardar`: el mapa de vuelta, después de cerrar la de ranuras.

    Acá el reloj del juego vuelve a correr, así que los ticks son ticks; los
    toques siguen en cuadros de hardware porque caen adentro de la pantalla,
    donde no hay ticks en los que caer.
    """
    p = partida("guardar")
    p.correr(cuadro, toques_hardware=toques)
    golden("%s-%d" % (nombre, cuadro), p.imagen())

"""La pantalla de título y su lista de ranuras, contra sus goldens.

Estuvo en `test_tanda_pantallas.py` hasta el 2026-09-25. Corre con el reloj
en cuadros de hardware, porque el título no es el juego y no cuenta ticks:
el arnés está explicado en `test_batalla_golden.py`. Qué hace cada opción lo
mira `test_titulo_dibujo.py`.
"""

import pytest

from tanda import correr_hardware, encender, golden


# La pantalla de título se come cuadros de arranque que el mapa no: 150 en vez
# de los 115 de todo lo demás.
ARRANQUE_CON_TITULO = 150

@pytest.mark.parametrize("nombre,sosteniendo,toques", (
    ("titulo", (), ()),
    # El cursor una opción más abajo. No es un adorno: es lo único que
    # ejercita el DMA que sube el otro tilemap, que es como está hecho el
    # cursor. Y de paso cobra que **sostener abajo no baje un renglón por
    # cuadro** —se corre con el botón apretado veinte cuadros y el cursor tiene
    # que haberse movido una sola vez—.
    ("titulo-2", ("down",), ()),
    # La pantalla de ranuras, a la que se llega bajando el cursor a "Resume the
    # Story" y apretando A. Van con toques y no sostenidos porque el menú mira
    # **flancos**.
    ("titulo-ranuras", (), ("down:2", "a:6")),
    ("titulo-ranuras2", (), ("down:2", "a:6", "down:10", "down:14")),
))
def test_titulo(nombre, sosteniendo, toques):
    """`titulo`: la pantalla de título, contra la imagen del LDB.

    Es el caso que **más necesita** el reloj de cuadros: ahí `vueltas` no
    avanza, porque el título no es el juego —una ROM con título corre el mapa
    igual que una sin él—, así que esperar un tick no termina jamás.

    Las cuatro ranuras salen vacías porque la SRAM del emulador arranca virgen.
    """
    consola = encender("release", ARRANQUE_CON_TITULO)
    correr_hardware(consola, 20, toques=toques, sosteniendo=sosteniendo)
    golden(nombre, consola.imagen())


# `test_titulo_es_el_mismo_juego` estuvo acá hasta el 2026-09-20 y se fue con
# el cartucho `titulo`, que existía para ser su otra mitad: comparaba la ROM
# con título contra la misma sin él, 300 ticks adentro del mapa, y era el único
# caso de la tanda que comparaba **una ROM contra otra**.
#
# Se fue por dos razones medidas, y la primera sola ya alcanzaba. Sus dos
# goldens —`titulo-juego` y `titulo-juego-sin`— eran **la pantalla entera en
# negro**: a los 300 ticks con `start` sostenido no se ve nada, así que la
# comparación que daba nombre al caso comparaba negro contra negro. Y con el
# título mudado al cartucho del juego ya no hay dos ROMs que se distingan sólo
# por la pantalla: la que la lleva arranca en el 4 y con cronómetro.
#
# Lo que la pregunta buscaba —¿la ROM con título dibuja lo mismo adentro del
# mapa?— lo cobran ahora las diecisiete goldens de `cinematica`, `apertura` y
# `cartel` de `pruebas/abl/test_tanda_escenas.py`: se congelaron cuando el
# cartucho no llevaba título y hoy se sacan a través de él, byte por byte
# iguales, en imágenes que no son negras.

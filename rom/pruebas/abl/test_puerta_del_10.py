"""Las dos puertas del mapa 10 que el switch 231 cambia de destino.

`EV0018` (42,15) y `EV0020` (42,46) son puertas de dos páginas: la primera, sin
condiciones, lleva al mapa 8 —Lashe City—, y la segunda, con el switch 231
puesto, lleva al 38. O sea que **a dónde lleva la puerta depende de la
partida**, y eso es una página, no una tabla.

Mientras las puertas viajaron en una tabla por mapa, el conversor les congelaba
la página activa al empezar la partida: la primera, siempre. Con el switch 231
prendido la ROM te mandaba igual al 8, que es el destino equivocado. Es el
defecto que arregla haberlas pasado por el intérprete, y es lo que esta prueba
cobra.

Hasta el 2026-09-26 el 38 no estaba en el cartucho, así que un `Teleport`
hacia él no compilaba y con él se caía la página entera: lo único que se podía
cobrar era que **no llevara al 8**. Desde que los sectores con auto entraron en
`release`, se cobra la otra mitad: que lleve al 38, a la celda de su página.
"""

MAPA = 10
SWITCH = 231
PUERTA = (42, 15)               # EV0018
DESDE = (42, 16)                # la celda de abajo, desde donde se la pisa
EQUIVOCADO = 8                  # a donde lleva su primera página
DESTINO = (38, (48, 54))        # y a donde lleva la segunda, con el 231


def pisar_la_puerta(una):
    """Camina para arriba hasta pisar la puerta o hasta cambiar de mapa."""
    for _ in range(40):
        una.sostener(8, "up")
        una.soltar()
        una.correr(2)
        if una.mapa() != MAPA or una.heroe() == PUERTA:
            break
    # Y los ticks del fundido, por si la pisada disparó uno: `map_current`
    # cambia recién en el cuadro negro, decenas de ticks después.
    una.correr(90)
    return una


def test_con_el_switch_231_la_puerta_lleva_al_38(partida):
    una = partida(switch=[SWITCH])
    una.ir_al_mapa(MAPA, *DESDE)
    assert una.switch(SWITCH), "el switch no quedó prendido"
    pisar_la_puerta(una)
    assert una.mapa() != EQUIVOCADO, (
        "con el switch %d puesto la puerta del mapa %d tiene que llevar al 38, "
        "y llevó al %d: se está usando su primera página y no la activa"
        % (SWITCH, MAPA, EQUIVOCADO))
    assert (una.mapa(), una.heroe()) == DESTINO, (
        "con el switch %d la puerta del mapa %d lleva a %s, y la partida quedó "
        "en el mapa %d, celda %s" % (SWITCH, MAPA, DESTINO, una.mapa(),
                                    una.heroe()))


def test_sin_el_switch_la_misma_puerta_sigue_llevando_al_8(partida):
    """La otra mitad, que es la que no tiene que haber cambiado: sin el 231 la
    página activa es la primera y la puerta lleva a Lashe City como siempre."""
    una = partida()
    una.ir_al_mapa(MAPA, *DESDE)
    assert not una.switch(SWITCH)
    pisar_la_puerta(una)
    assert una.mapa() == EQUIVOCADO, (
        "sin el switch %d la puerta del mapa %d lleva al %d, y la partida "
        "quedó en el %d" % (SWITCH, MAPA, EQUIVOCADO, una.mapa()))

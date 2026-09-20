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

**El 38 no entra en ningún cartucho** —sus tiles de fondo y de sprite más la
ventana no entran en los 64 KB de VRAM, y por eso tampoco está en `abl`—, así
que un `Teleport` hacia él no compila y con él se cae la página entera. Lo que
se puede verificar desde acá, entonces, no es que lleve al 38: es que **no
lleva al 8**, que es la mitad que sí depende de este cambio. La otra mitad la
cobrará el día que el 38 entre en un cartucho.
"""

MAPA = 10
SWITCH = 231
PUERTA = (42, 15)               # EV0018
DESDE = (42, 16)                # la celda de abajo, desde donde se la pisa
EQUIVOCADO = 8                  # a donde lleva su primera página


def heroe(una):
    return (una.palabra("hero_x") // 16, una.palabra("hero_y") // 16)


def pisar_la_puerta(una):
    """Camina para arriba hasta pisar la puerta o hasta cambiar de mapa."""
    for _ in range(40):
        una.sostener(8, "up")
        una.soltar()
        una.correr(2)
        if una.mapa() != MAPA or heroe(una) == PUERTA:
            break
    # Y los ticks del fundido, por si la pisada disparó uno: `mapa_actual`
    # cambia recién en el cuadro negro, decenas de ticks después.
    una.correr(90)
    return una


def test_con_el_switch_231_la_puerta_no_lleva_al_8(partida):
    una = partida(switch=[SWITCH])
    una.ir_al_mapa(MAPA, *DESDE)
    assert una.switch(SWITCH), "el switch no quedó prendido"
    pisar_la_puerta(una)
    assert una.mapa() != EQUIVOCADO, (
        "con el switch %d puesto la puerta del mapa %d tiene que llevar al 38, "
        "y llevó al %d: se está usando su primera página y no la activa"
        % (SWITCH, MAPA, EQUIVOCADO))
    assert una.mapa() == MAPA, (
        "el 38 no está en el cartucho, así que la página de la puerta no "
        "compila y la partida se tiene que quedar en el %d; quedó en el %d"
        % (MAPA, una.mapa()))
    assert heroe(una) == PUERTA, (
        "el héroe no llegó a pisar la puerta —quedó en %s— así que la prueba "
        "pasaría igual sin puerta" % (heroe(una),))


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

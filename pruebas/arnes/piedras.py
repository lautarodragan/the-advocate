"""El minijuego de las piedras del mapa 11, desde afuera: hablarle a la reja
para que Talan tenga las piedras, y dónde está cada evento.

Vivía en `test_piedras.py`, y `test_luces.py` lo importaba de ahí.
"""

import datos

# El mapa del minijuego, con el grupo del juego: no sale de ahí.
MAPAS = "en-11"
# Abajo de `Grate1`, que está en (26,51) y es pared: desde acá se le habla
# mirando hacia arriba, que es como se juega el minijuego.
DEBAJO_DE_LA_REJA = (26, 52)
REJA = (26, 51)
# El evento que hace de piedra, y dónde lo deja el mapa antes de que nadie lo
# mueva: lejos, en (45,75).
STONE = 18


def ranura(numero):
    return datos.ranuras_de_variable()[numero]


def celda_de(p, mapa11, evento):
    """En qué celda tiene la ROM al evento `evento` de RM2k, ahora mismo."""
    return p.evento(mapa11.para(1).blanco(evento) - 1)


def hablarle_a_la_reja(p):
    """Los cuatro cuadros de texto de `Grate1`, hasta que Talan tiene tres
    piedras. Devuelve la partida con el minijuego ya andando."""
    p.ir_al_mapa(11, *DEBAJO_DE_LA_REJA)
    p.tocar("up")           # gira sin moverse: la reja no se pisa
    assert (p.palabra("tile_x"), p.palabra("tile_y")) == DEBAJO_DE_LA_REJA, (
        "tocar arriba contra la reja no tendría que mover al héroe")
    for _ in range(40):
        p.correr(1)
        p.tocar("a")
        if p.switch(43):
            return p
    raise AssertionError(
        "después de cuarenta toques de A el switch 43 sigue apagado: nadie le "
        "dio las piedras. La variable 4 quedó en %d" % p.variable(ranura(4)))

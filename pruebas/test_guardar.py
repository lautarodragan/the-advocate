"""Guardar la partida en la SRAM del cartucho, y volver a cargarla.

El save point de Lashe City —`SaveByTalansPad0`, el evento 67 del mapa 8— pide
`OpenSaveMenu`. Acá no hay menú: hay **una sola ranura**, el evento la pisa y la
página sigue de largo. Lo que se guarda lo dice `partida_tabla` en `main.s`.

Esto no lo puede cubrir la tanda de pixeles: guardar no cambia un pixel. Lo que
se mira acá es lo único que importa —que lo guardado sobreviva a apagar la
consola— y por eso la prueba **resetea la consola de verdad** en vez de leerle la
RAM: la SRAM sobrevive al reset y la WRAM no, así que si la partida vuelve es
porque salió del cartucho.

La página de prueba guarda después de una espera, que es lo que deja mover el
mundo antes: sin eso se guardaría el estado del arranque y cargar o no cargar
darían lo mismo.
"""

import pytest

# Cuántos ticks espera la página de prueba antes de guardar. Alcanzan para
# irse a otro mapa —el fundido son 90— y que sobre margen.
ESPERA = 200


@pytest.fixture
def guardada(partida):
    """Una partida que se fue al mapa 6, prendió un switch y guardó."""
    una = partida(guardar=ESPERA)
    una.ir_al_mapa(6, 20, 30)
    una.prender(7)
    una.correr(ESPERA)
    return una


def test_la_sram_queda_escrita(guardada):
    """La ranura tiene la magia y no es la basura con la que arranca."""
    sram = guardada.sram(0, 0x110)
    assert sram[0x100:0x104] == b"ABLS", (
        "la SRAM no lleva la magia de una partida guardada: %r"
        % sram[0x100:0x104])


def test_vuelve_donde_estaba(guardada):
    """Después del reset, la partida arranca donde se guardó y no en el mapa
    de arranque de la ROM."""
    assert guardada.mapa() == 6
    guardada.reiniciar()
    assert guardada.mapa() == 6, (
        "la ROM arrancó en el mapa %d en vez de en el 6" % guardada.mapa())
    assert (guardada.palabra("tile_x"), guardada.palabra("tile_y")) == (20, 30)


def test_los_switches_vuelven(guardada):
    """Y el estado del mundo con ella: un switch prendido antes de guardar
    sigue prendido después del reset."""
    assert guardada.switch(7)
    guardada.reiniciar()
    assert guardada.switch(7), "el switch 7 no sobrevivió al reset"


def test_sin_partida_arranca_de_cero(partida):
    """Y una consola sin nada guardado arranca en el mapa de la ROM.

    Es la otra mitad, y no es teórica: la SRAM sin escribir trae basura, y si la
    ROM la tomara por buena cargaría una partida inventada. Lo que lo evita son
    la magia y la suma.
    """
    una = partida()
    assert una.mapa() == 5

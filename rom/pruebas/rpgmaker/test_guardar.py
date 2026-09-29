"""Guardar la partida en la SRAM del cartucho, y volver a cargarla.

El save point de Lashe City —`SaveByTalansPad0`, el evento 67 del mapa 8— pide
`OpenSaveMenu`, y eso abre la pantalla de ranuras adentro del intérprete: se
elige una con el cursor, se guarda ahí y la página sigue. Lo que se guarda lo
dice `partida_tabla` en `runtime/banco1.s`; cómo se ve la pantalla lo cobra
`test_guardar_golden.py`.

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

# La página de prueba `guardar-198` espera 198 ticks antes de guardar. Alcanzan
# para irse a otro mapa —el fundido son 90— y que sobre margen.


@pytest.fixture
def guardada(partida):
    """Una partida que se fue al mapa 6, prendió un switch y guardó."""
    una = partida(caso="guardar-198")
    una.ir_al_mapa(6, 20, 30)
    una.prender(7)
    una.guardar_en()
    return una


def test_la_sram_queda_escrita(guardada):
    """La ranura tiene la magia y no es la basura con la que arranca."""
    assert guardada.hay_partida(), (
        "la SRAM no lleva la magia de una partida guardada: %r"
        % guardada.magia())


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


# --- las cuatro ranuras -----------------------------------------------------
#
# Cada una arranca en un múltiplo de SRAM_STRIDE, y de eso depende que llenar
# una no toque a las demás. Es la clase de cosa que anda de casualidad si el
# desplazamiento se calcula mal en un solo lado: guardar escribiría siempre en
# la primera y cargar la leería siempre de la primera, con lo cual todo
# "funcionaría" y habría una sola ranura disfrazada de cuatro.


def _base(simbolos, ranura):
    """Dónde arranca la ranura en la SRAM, con los números de la ROM."""
    return simbolos["SRAM_MAGIC"] + ranura * simbolos["SRAM_STRIDE"]


def test_guardar_escribe_en_la_ranura_elegida(partida):
    """Elegir otra ranura en la pantalla manda la partida a otro lado.

    Se corre dos veces la misma página de prueba, bajando el cursor a una
    ranura distinta cada vez. Si el desplazamiento se ignorara, las dos
    escribirían en la primera y este caso pasaría a medias: por eso se
    comprueba **las dos** cosas, que la elegida tenga la magia y que la otra
    no. Y de paso cobra que el número que elige el cursor llegue hasta
    `save_game`, que es el camino del save point de verdad.
    """
    for elegida in (0, 1):
        una = partida(caso="guardar-198")
        una.guardar_en(elegida)             # en la pantalla, con el cursor
        simbolos = una.simbolos
        assert una.hay_partida(elegida), (
            "se pidió guardar en la ranura %d y ahí no quedó ninguna partida"
            % elegida)
        otra = 1 - elegida
        assert not una.hay_partida(otra), (
            "guardar en la ranura %d también escribió en la %d: las ranuras se "
            "están pisando" % (elegida, otra))


def test_cancelar_no_guarda_ni_cambia_la_ranura(partida):
    """B cierra la pantalla sin escribir nada, y `ranura` queda como estaba.

    Lo segundo no es obvio: pintar la lista pisa `ranura` —`slot_full` la
    usa para direccionar la SRAM— y sin reponerla al salir, cancelar dejaría a
    la partida "cargada" de la última fila pintada. Verificado que da rojo
    sacando el `pla; sta ranura` de `cerrar`: queda en 3.
    """
    una = partida(caso="guardar-198")
    una.guardar_en(cancelar=True)
    assert una.byte("menu_abierto") == 0, "la pantalla sigue abierta"
    assert una.byte("ranura") == 0xFF, (
        "cancelar dejó `ranura` en %d y la partida no venía de ninguna"
        % una.byte("ranura"))
    for n in range(una.simbolos["SRAM_SLOTS"]):
        assert not una.hay_partida(n), (
            "se canceló y la ranura %d quedó escrita igual" % n)


def test_las_cuatro_ranuras_entran_en_la_sram(partida):
    """La última ranura termina adentro de los 32 KB de SRAM del cartucho.

    Es una cuenta y no una medición, pero conviene que la haga la prueba y no
    yo: `SAVE_BYTES` crece cada vez que se agrega un campo a la partida —ya
    pasó con la música— y el día que pase de `SRAM_STRIDE` cada ranura empezaría
    a pisar el final de la anterior **sin que nada avise**.
    """
    una = partida()
    simbolos = una.simbolos
    largo = simbolos["SAVE_BYTES"]
    stride = simbolos["SRAM_STRIDE"]
    ranuras = simbolos["SRAM_SLOTS"]
    assert simbolos["SRAM_DATA"] - simbolos["SRAM_MAGIC"] + largo <= stride, (
        "una partida ocupa %d bytes y las ranuras van cada %d: la %d pisaría "
        "el final de la anterior" % (largo, stride, ranuras))
    fin = _base(simbolos, ranuras - 1) + stride
    assert fin <= 0x8000, (
        "las %d ranuras terminan en $%04X y la SRAM son 32 KB" % (ranuras, fin))

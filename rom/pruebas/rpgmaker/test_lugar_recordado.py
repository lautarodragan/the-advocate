"""`MemorizeLocation`, `RecallToLocation` y el tema recordado.

`RecallToLocation` es un `Teleport` con el mapa y la celda leídos de tres
variables al correr, y `MemorizeLocation` escribe esas tres con el lugar del
héroe. **En las variables el mapa es el id de RM2k**, no el índice del
cartucho: los pisos que se rompen de la planta de reciclaje (mapas 60 y 62)
lo cargan con un `ControlVars` y enseguida saltan, así que la ROM lo traduce
con la tabla `map_rm2k`. Ver `remembered_place` en
runtime/remembered_place_and_song.s.

Los casos:

    lugar-caer          el piso que se rompe del mapa 60, entero: la variable
                        45 en 61, la 43 y la 44 con la celda del héroe, cinco
                        filas menos, y el salto. Después un `ControlVars` a la
                        17, que tiene que correr **en el mapa nuevo**
    lugar-ida-y-vuelta  recordar en el 6, ir al 61 y volver a lo recordado
    lugar-ausente       un mapa que el cartucho no lleva: no salta y sigue
    tema-recordado      recordar `evilrhys`, poner `lufsorr` y volver
    tema-recordado-el-mismo
                        recordar el que suena y ponerlo: no vuelve a empezar

La música no se ve, así que la tanda no la cobra: se le pregunta a la RAM.
"""

import datos
from consola import en_la_wram, indice_del_tema

# La que los casos escriben al final, para ver que la página siguió.
SIGUIO = 17
MARCA = 1234


def ranura(variable):
    return datos.ranuras_de_variable()[variable]


def celda(una):
    return una.palabra("tile_x"), una.palabra("tile_y")


def esperar(una, cond, tope, que):
    for _ in range(tope):
        if cond(una):
            return
        una.correr(1)
    raise AssertionError("%s no pasó en %d ticks: mapa %d, celda %s"
                         % (que, tope, una.mapa(), celda(una)))


def test_caer_por_un_piso_que_se_rompe_lleva_al_piso_de_abajo(partida):
    """Del 60 en (4,11) al 61 en (4,6), la celda que dicen las variables, y la
    página sigue corriendo allá."""
    una = partida(caso="lugar-caer")
    assert una.mapa() == 60, "el caso arranca en el 60: %d" % una.mapa()
    esperar(una, lambda u: u.mapa() == 61, 400, "caer al 61")
    esperar(una, lambda u: u.variable(ranura(SIGUIO)) == MARCA, 200,
            "que la página siga después del salto")
    assert celda(una) == (4, 6), (
        "el salto deja al héroe en la celda de las variables, (4,6), y quedó "
        "en %s" % (celda(una),))
    assert una.variable(ranura(45)) == 61
    assert (una.variable(ranura(43)), una.variable(ranura(44))) == (4, 6)


def test_recordar_y_volver(partida):
    """`MemorizeLocation` en el 6 escribe 6, 22 y 12 —el id de RM2k, no el
    índice—, y `RecallToLocation` desde el 61 vuelve ahí."""
    una = partida(caso="lugar-ida-y-vuelta")
    esperar(una, lambda u: u.mapa() == 61, 400, "llegar al 61")
    recordado = tuple(una.variable(ranura(v)) for v in (127, 128, 129))
    assert recordado == (6, 22, 12), (
        "lo recordado en el 6 tendría que ser (6, 22, 12) y es %s"
        % (recordado,))
    esperar(una, lambda u: u.mapa() == 6, 600, "volver al 6")
    esperar(una, lambda u: u.variable(ranura(SIGUIO)) == MARCA, 200,
            "que la página siga después de volver")
    assert celda(una) == (22, 12), celda(una)


def test_recordar_un_mapa_que_no_esta_no_salta(partida):
    """El mapa 999 no está en el cartucho: la ROM no salta, y la página
    sigue con el comando de después."""
    una = partida(caso="lugar-ausente")
    esperar(una, lambda u: u.variable(ranura(SIGUIO)) == MARCA, 400,
            "que la página siga")
    assert una.mapa() == 6 and celda(una) == (22, 12), (
        "un `RecallToLocation` a un mapa ausente no salta: quedó en el %d, %s"
        % (una.mapa(), celda(una)))
    assert not una.byte("jump_has")


def test_el_tema_recordado_vuelve(partida):
    """`MemorizeBGM` con `evilrhys`, `PlayBGM` de `lufsorr`, y
    `PlayMemorizedBGM` pone `evilrhys` otra vez."""
    una = partida(caso="tema-recordado")
    evilrhys = indice_del_tema(una, "evilrhys")
    lufsorr = indice_del_tema(una, "lufsorr")
    esperar(una, lambda u: u.palabra("song_current") == lufsorr, 200,
            "que suene lufsorr")
    recordado = una.consola.ram(
        en_la_wram(una.simbolos["REMEMBERED_SONG"]), 1)[0]
    assert recordado == evilrhys, (
        "el tema recordado es el %d y tendría que ser evilrhys, el %d"
        % (recordado, evilrhys))
    esperar(una, lambda u: u.palabra("song_current") == evilrhys, 200,
            "que vuelva evilrhys")
    assert not una.byte("music_off")


def test_poner_el_tema_recordado_que_ya_suena_no_lo_reinicia(partida):
    """Es `Game_System::BgmPlay` con el mismo nombre: sigue por donde iba.
    Si se reiniciara, el stream volvería atrás en algún cuadro."""
    una = partida(caso="tema-recordado-el-mismo")
    evilrhys = indice_del_tema(una, "evilrhys")
    esperar(una, lambda u: u.palabra("song_current") == evilrhys, 200,
            "que suene evilrhys")
    antes = una.avance_del_stream()
    for _ in range(420):
        una.correr(1)
        ahora = una.avance_del_stream()
        assert ahora >= antes, (
            "el stream volvió de $%06X a $%06X: el tema recordado se "
            "reinició, y en RM2k el mismo tema sigue sonando" % (antes, ahora))
        antes = ahora
    assert not una.corriendo_una_pagina(), "la página no llegó al final"
    assert una.palabra("song_current") == evilrhys

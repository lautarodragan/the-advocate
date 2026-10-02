"""Que pedir el tema que ya suena no lo haga empezar de nuevo.

Es `Game_System::BgmPlay` de easyrpg: con el mismo nombre, y sin un
`FadeOutBGM` de por medio —su `music_stopping`—, sólo ajusta volumen, tempo y
balance, y el tema sigue por donde iba. Lo notó taro en dos lugares: la
victoria de la pelea, donde el tema de batalla y el de victoria del LDB son el
mismo —eso lo mira `test_ganar_deja_seguir_el_tema_de_la_victoria`, en
`test_batalla.py`—, y la caminata a la fábrica, donde el `PlayBGM` de la
automática del 16 pide `hzbreach`, que ya venía sonando desde el 14.

Como todo lo de la música, no cambia un pixel: se mira por dónde va el
stream —`avance_del_stream`—, que avanza mientras el tema suena y vuelve al
principio si se reinicia. Pasar de un mapa a otro con el mismo tema ya lo cuida
`test_tema_del_mapa.py`, y volver al tema recordado, `test_lugar_recordado.py`.

La consola de las pruebas no le deja ver al core las pistas de MSU-1: esto
mide el camino del SPC700. El del MSU-1 pasa por la misma pregunta,
`song_playing`, que mira `MSU_PLAYING` antes que `music_off`.
"""

from consola import indice_del_tema


def test_pedir_dos_veces_el_mismo_tema_no_lo_reinicia(partida):
    """Dos `PlayBGM evilrhys` en la misma página, con treinta ticks entre
    uno y otro: el segundo no lo vuelve a empezar."""
    una = partida(caso="tema-pedido-dos-veces")
    evilrhys = indice_del_tema(una, "evilrhys")
    for _ in range(200):
        if una.palabra("song_current") == evilrhys:
            break
        una.correr(1)
    else:
        raise AssertionError("evilrhys no llegó a sonar: la prueba no mide "
                             "nada")
    antes = una.avance_del_stream()
    for _ in range(300):
        una.correr(1)
        ahora = una.avance_del_stream()
        assert ahora >= antes, (
            "el stream volvió de $%06X a $%06X: el segundo `PlayBGM` de "
            "evilrhys lo reinició, y en RM2k el mismo tema sigue sonando"
            % (antes, ahora))
        antes = ahora
    assert not una.corriendo_una_pagina(), "la página no llegó al final"
    assert una.palabra("song_current") == evilrhys
    assert not una.byte("music_off")


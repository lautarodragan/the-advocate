"""Que al entrar a un mapa suene el tema que trae en sus propiedades.

Es el `Game_Map::PlayBgm` de easyrpg, que corre cada vez que un teletransporte
cambia de mapa: el tema del mapa —`music_type` 2—, o el del padre si es 0, o
**nada** si es 1, "lo decide un evento". Sin esto, en los Rat Tracks se
entraba con el tema del mapa de antes.

Como todo lo de la música, esto **no cambia un pixel**, así que la tanda no lo
ve: se pregunta por la RAM. Y no alcanza con `tema_actual`, por lo mismo que en
`test_musica_paquete.py`: el tema tiene que llegar con sus muestras, que son
las que el conversor le agrega al paquete del mapa.

La consola de las pruebas no le deja ver al core las pistas de MSU-1 —ver
`retro.Console`—, así que esto mide el camino del SPC700. El del MSU-1 es el
mismo `music_start` que usa un `PlayBGM`.
"""

import pytest

from consola import indice_del_tema

# Los Rat Tracks: el 21 y el 26 traen `KSSMKEND`, y el 23 —hijo del 21— es un
# `music_type` 1, o sea que entrar ahí no cambia lo que suena.
CASO = "tema-del-mapa-21"
TEMA = "KSSMKEND"
AL_26 = (26, 13, 48)            # el `Teleport` del 21 al 26
AL_23 = (23, 11, 12)            # y el del 21 al 23

# Cuánto se queda en el 21 antes de seguir: lo bastante para que el stream
# vaya más adelante de lo que llegaría si se reiniciara en el cuadro negro del
# fundido siguiente, que es a mitad de sus noventa cuadros.
QUEDARSE = 300


def puntero_del_stream(una):
    """Por dónde va el stream que suena: `music`, tres bytes."""
    bajo, alto, banco = una.consola.ram(una.simbolos["music"], 3)
    return (banco << 16) | (alto << 8) | bajo


@pytest.fixture
def en_el_21(partida):
    una = partida(caso=CASO)
    assert una.mapa() == 21, "el caso tenía que llegar al 21 y está en el %d" \
        % una.mapa()
    return una


def test_entrar_a_los_rat_tracks_prende_su_tema(en_el_21):
    """El `Teleport` al 21 cambia el tema, y el tema llega con sus muestras.

    El caso arranca en el mapa de arranque del cartucho, que no trae tema, y
    salta con un `Teleport` de verdad: es el camino de `FUNDIDO_SALTO`, el de
    cualquier puerta del juego.
    """
    una = en_el_21
    tema = indice_del_tema(una, TEMA)
    assert una.palabra("tema_actual") == tema, (
        "se entró al 21 y suena el tema %d; el del mapa es %s, el %d"
        % (una.palabra("tema_actual"), TEMA, tema))
    assert not una.byte("music_apagada"), (
        "se entró al 21 y la música quedó callada: `music_start` no llegó a "
        "prender el tema del mapa")
    faltan = sorted(set(una.muestras_del_tema(tema))
                    - una.muestras_en_la_aram())
    assert not faltan, (
        "el tema del mapa suena y le faltan en la ARAM las muestras %s de las "
        "%s que usa: el conversor no lo metió en el paquete del 21"
        % (faltan, sorted(una.muestras_del_tema(tema))))


def test_pasar_al_otro_mapa_con_el_mismo_tema_no_lo_reinicia(en_el_21):
    """Del 21 al 26, que traen el mismo: el tema sigue por donde iba.

    Es `Game_System::BgmPlay` con el nombre que ya suena. Si se reiniciara, el
    stream estaría de vuelta cerca del principio, o sea **antes** de donde iba
    al salir del 21.
    """
    una = en_el_21
    una.correr(QUEDARSE)
    antes = puntero_del_stream(una)
    una.ir_al_mapa(*AL_26)
    assert una.mapa() == 26
    assert una.palabra("tema_actual") == indice_del_tema(una, TEMA)
    despues = puntero_del_stream(una)
    assert despues > antes, (
        "al pasar del 21 al 26 el stream volvió de $%06X a $%06X: el tema se "
        "reinició, y en RM2k el mismo tema sigue sonando" % (antes, despues))


def test_un_mapa_que_lo_deja_a_un_evento_no_cambia_lo_que_suena(en_el_21):
    """Del 21 al 23, que es `music_type` 1: sigue el tema del 21."""
    una = en_el_21
    una.correr(QUEDARSE)
    antes = puntero_del_stream(una)
    una.ir_al_mapa(*AL_23)
    assert una.mapa() == 23
    assert una.palabra("tema_actual") == indice_del_tema(una, TEMA), (
        "el 23 no trae tema propio y la música cambió al entrar")
    assert not una.byte("music_apagada"), (
        "el 23 no trae tema propio y la música se calló al entrar")
    assert puntero_del_stream(una) > antes, (
        "el 23 no trae tema propio y el de antes se reinició")

"""Cuánto dura un `Wait` más un `Teleport`, contra el RPG_RT.

La escena del mapa 16 —la corrida al trabajo— son cuatro vueltas de
`MoveEvent` del héroe, `Wait 15` y `Teleport` al mismo mapa. Se midió el
2026-09-29 en el RPG_RT de 2015 con Wine, grabando a 60 cuadros por segundo y
contando entre marcas del mismo video: **S**, el primer paso del héroe; **F**,
el primer cuadro más oscuro del fundido; **J**, el último del fundido, que es
el primero con el brillo entero. Salió igual en las tres vueltas internas y
en dos grabaciones:

    del primer paso a F          89
    el fundido, de F a J         67
    de J al primer paso          2
    la vuelta entera, S a S      158

La ROM daba 91, 68, 2 y 161, y la diferencia eran dos cosas: la espera
contaba un tick de más —ver `op_delay`— y el fundido arrancaba un tick
después del salto y terminaba uno más tarde —ver `start_fade`—. Y en la
tercera vuelta, donde la ruta dura más que la espera, el héroe caminaba un
tick más antes del corte: en el original la cámara se mueve 90 cuadros.

Se mira por la RAM y no por la imagen: el brillo y la posición llegan a la
pantalla en el mismo vblank, así que las distancias entre marcas son las
mismas. La partida llega al 16 por `ir_al_mapa`, sin el grupo con el que el
juego entra ahí, y el héroe no se ve; la cámara lo sigue igual, y lo que se
cuenta es su posición.
"""

import pytest

EL_16 = (16, 53, 7)             # donde entra el juego, y `test_recorrido_golden`
TICKS = 720                     # cuatro vueltas y la llegada, con holgura

# Lo medido en el RPG_RT.
DEL_PASO_AL_FUNDIDO = 89
EL_FUNDIDO = 67
DEL_FUNDIDO_AL_PASO = 2
LA_VUELTA = 158
PASOS_DE_LA_TERCERA = 90


@pytest.fixture(scope="module")
def vueltas():
    """Por vuelta, (S, F, J, ticks que el héroe se movió): S el primer tick
    con el héroe en otro lugar, F el primero con el brillo bajo el máximo y J
    el primero que lo recupera. La llegada de `ir_al_mapa` no es una vuelta:
    su fundido termina antes del primer paso."""
    import tanda
    p = tanda.partida("en-5")
    p.ir_al_mapa(*EL_16, cuadros=0)
    antes = None
    marcas = []
    s = f = None
    pasos = 0
    for _ in range(TICKS):
        p.correr(1)
        ahora = (p.palabra("hero_x"), p.palabra("hero_y"),
                 p.byte("brightness"), p.byte("fade"))
        if antes is not None:
            # Un paso es de un tick que arrancó sin fundido: el que lo carga
            # también mueve al héroe, a la celda de llegada.
            if ahora[:2] != antes[:2] and not antes[3]:
                if s is None:
                    s = p.cuadro
                pasos += 1
            if s is not None and f is None and ahora[2] < antes[2]:
                f = p.cuadro
            if f is not None and ahora[2] == 15 and antes[2] < 15:
                marcas.append((s, f, p.cuadro, pasos))
                s = f = None
                pasos = 0
        antes = ahora
    assert len(marcas) >= 4, (
        "tendría que haber cuatro vueltas con su fundido en %d ticks, y hay "
        "%d: %s" % (TICKS, len(marcas), marcas))
    return marcas


def test_del_primer_paso_al_fundido(vueltas):
    """El primer tick oscuro es el del salto, 90 después del de la espera."""
    for i, (s, f, _j, _p) in enumerate(vueltas):
        assert f - s == DEL_PASO_AL_FUNDIDO, (
            "vuelta %d: del primer paso (%d) al primer tick del fundido (%d) "
            "hay %d, y en el RPG_RT %d" % (i + 1, s, f, f - s,
                                           DEL_PASO_AL_FUNDIDO))


def test_el_fundido(vueltas):
    for i, (_s, f, j, _p) in enumerate(vueltas):
        assert j - f == EL_FUNDIDO, (
            "vuelta %d: el fundido va del %d al %d, %d ticks, y en el RPG_RT "
            "%d" % (i + 1, f, j, j - f, EL_FUNDIDO))


def test_del_fundido_al_paso_y_la_vuelta(vueltas):
    for i in range(len(vueltas) - 1):
        s, _f, j, _p = vueltas[i]
        s2 = vueltas[i + 1][0]
        assert (s2 - j, s2 - s) == (DEL_FUNDIDO_AL_PASO, LA_VUELTA), (
            "vuelta %d: del fin del fundido al paso siguiente %d, y la vuelta "
            "%d; en el RPG_RT %d y %d" % (i + 1, s2 - j, s2 - s,
                                          DEL_FUNDIDO_AL_PASO, LA_VUELTA))


def test_la_tercera_vuelta_camina_lo_mismo(vueltas):
    """La ruta de la tercera dura más que la espera: el héroe camina hasta el
    tick del salto, incluido, y ahí se corta."""
    pasos = vueltas[2][3]
    assert pasos == PASOS_DE_LA_TERCERA, (
        "en la tercera vuelta el héroe se mueve %d ticks antes del corte, y "
        "en el RPG_RT la cámara se mueve %d" % (pasos, PASOS_DE_LA_TERCERA))

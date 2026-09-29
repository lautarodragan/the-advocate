"""El autofire: X sostenido aprieta y suelta A solo.

No es de RM2k —ver `workflow/divergencias/autofire-de-a-con-x.md`—, pero vive
en el motor: es `read_pad`, que es por donde pasa todo el control. Lo que se
mira es lo que el juego ve, que es `pad_a` y su anterior: el juego no mira A
sino su flanco, así que cada vuelta de `pad_a` a prendido es un toque.

Las de ritmo leen la RAM **cuadro de hardware por cuadro**, no por tick: el
autofire cuenta vueltas de `read_pad`, que son cuadros, y un tick del juego
puede durar más de uno. Corren en `en-5`, donde el héroe está parado sin nada
enfrente y ningún cuadro se estira; si un día se estirara, la secuencia
esperada dejaría de ser exacta y habría que mirar por qué antes de aflojarla.
"""

import datos

# El caso `autofire`: cinco mensajes seguidos, y detrás de cada uno la
# variable 17 sube uno. Así la variable dice cuántos mensajes cerró el
# jugador, que es el toque de A tal como lo usa el juego.
CASO = "autofire"
VARIABLE = 17
MENSAJES = 5

# `AUTOFIRE_CUADROS` de `control.s`: vueltas prendido y vueltas apagado.
CUADROS = 4


def cerrados(p):
    return p.variable(datos.ranuras_de_variable()[VARIABLE])


def secuencia(p, cuadros, *botones):
    """`pad_a` y los flancos de subida que ve el juego, cuadro por cuadro,
    con `botones` apretados."""
    p.consola.apretar(*botones)
    prendido, flancos = [], []
    for _ in range(cuadros):
        p._un_cuadro()
        a, antes = p.byte("pad_a"), p.byte("pad_a_ant")
        prendido.append(bool(a))
        flancos.append(bool(a and not antes))
    return prendido, flancos


def test_sostener_x_cierra_los_mensajes_seguidos(partida):
    """Con X sostenido se cierran los cinco; con A sostenido, uno solo.

    El de A es el control: sin él, un cinco podría ser que la ROM cierra los
    mensajes sola, o que sostener cualquier botón repite. Los dos se aprietan
    con el primer mensaje ya abierto, a los treinta ticks: un flanco que cae
    mientras la ventana se compone no hace nada —ver `test_hablar`—, y A
    sostenido desde el tick 1 cerraría cero.
    """
    p = partida(caso=CASO)
    p.correr(30)
    p.correr(120, sosteniendo=("x",))
    assert cerrados(p) == MENSAJES, "con X sostenido cerró %d de %d" % (
        cerrados(p), MENSAJES)

    p = partida(caso=CASO)
    p.correr(30)
    p.correr(120, sosteniendo=("a",))
    assert cerrados(p) == 1, "con A sostenido cerró %d y no 1" % cerrados(p)


def test_el_ritmo_es_cuatro_prendido_y_cuatro_apagado(partida):
    """El primer cuadro con X ya aprieta, y después cuatro y cuatro: ocho
    toques en 64 cuadros, el primero en el cuadro 0."""
    p = partida()
    p.correr(10)
    prendido, flancos = secuencia(p, 64, "x")
    esperado = ([True] * CUADROS + [False] * CUADROS) * (64 // (2 * CUADROS))
    assert prendido == esperado, "".join("1" if x else "0" for x in prendido)
    assert [k for k, f in enumerate(flancos) if f] == list(
        range(0, 64, 2 * CUADROS))


def test_la_a_de_verdad_gana(partida):
    """A y X juntos es sostener A: prendido siempre, un solo toque."""
    p = partida()
    p.correr(10)
    prendido, flancos = secuencia(p, 64, "a", "x")
    assert all(prendido), "".join("1" if x else "0" for x in prendido)
    assert sum(flancos) == 1


def test_soltar_x_no_deja_a_trabado_ni_toca_de_mas(partida):
    """Se suelta X en cada una de las ocho fases del ciclo: el cuadro
    siguiente `pad_a` está apagado y no hay ningún flanco más. Y el próximo X
    vuelve a arrancar tocando en su primer cuadro, porque soltarlo reinicia el
    contador."""
    for fase in range(2 * CUADROS):
        p = partida()
        p.correr(10)
        secuencia(p, 2 * CUADROS + fase, "x")
        prendido, flancos = secuencia(p, 32)
        assert not any(prendido), "fase %d: %s" % (
            fase, "".join("1" if x else "0" for x in prendido))
        assert not any(flancos), "fase %d: un toque de más" % fase
        prendido, flancos = secuencia(p, 1, "x")
        assert flancos == [True], "fase %d: el X de nuevo no tocó ya" % fase


def test_soltar_x_con_a_apretado_no_suelta_a(partida):
    """Con A apretado de verdad, soltar X deja A prendido y sin flancos, en
    cualquier fase."""
    for fase in range(2 * CUADROS):
        p = partida()
        p.correr(10)
        secuencia(p, 2 * CUADROS + fase, "a", "x")
        prendido, flancos = secuencia(p, 16, "a")
        assert all(prendido) and not any(flancos), "fase %d" % fase


def test_soltar_x_a_mitad_deja_de_cerrar_mensajes(partida):
    """El mismo caso que la primera: se suelta X apenas cerró el segundo
    mensaje, y la cuenta se queda en dos aunque pasen dos segundos."""
    p = partida(caso=CASO)
    p.consola.apretar("x")
    for _ in range(600):
        p._un_cuadro()
        if cerrados(p) == 2:
            break
    assert cerrados(p) == 2
    p.soltar()
    p.correr(120)
    assert cerrados(p) == 2, "sin X siguió cerrando: %d" % cerrados(p)

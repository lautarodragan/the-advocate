"""RM2k's two text escapes, on the Python side: `\\|` and `\\^`.

It runs no ROM, and that is why it is here and not in the suite: what it looks
at is the **format**, that is, the header byte of the text box that the ROM's
interpreter reads with the same masks. That the message pauses and closes by
itself is enforced by `autocierre` and `autocierre-3` in
`test_comandos_golden.py`, which compare pixels.

What it does cover, and no compared text box could, is the deduplication:
two text boxes with the same text and a different tail sharing an offset
would be wrong from the day they were born, and a golden taken that day would
defend it. See "Una golden caza regresiones" in AGENTS.md.
"""


import pytest

from port import eventos
from port import constantes


def test_la_cola_sale_del_texto_y_se_cuenta():
    """`\\|\\^` is what the game uses 25 times: one pause and auto-close."""
    lineas, pausas, autocierre = eventos.cola_de_escapes(
        ["HELP!!", "That bandit... has a bow...\\|\\^"])
    assert lineas == ("HELP!!", "That bandit... has a bow...")
    assert (pausas, autocierre) == (1, True)


def test_tres_pausas_seguidas():
    """The `< Kiss >` of map 108, which is the most in the game."""
    _lineas, pausas, autocierre = eventos.cola_de_escapes(
        ["                  < Kiss >\\|\\|\\|\\^"])
    assert (pausas, autocierre) == (3, True)


def test_la_cola_con_espacios_entre_medio():
    """The `RunDirectorScene` of map 98 is the only one that writes `\\| \\| \\| \\^`.

    The spaces in the tail go away with it: a space at the end of a line
    draws no pixel, so removing it gives the same screen.
    The ones before the first escape stay, because those are text.
    """
    lineas, pausas, autocierre = eventos.cola_de_escapes(
        ["  ya vuelvo \\| \\| \\| \\^"])
    assert lineas == ("  ya vuelvo ",)
    assert (pausas, autocierre) == (3, True)


def test_un_escape_que_no_conocemos_no_compila():
    """The three `\\V` of the common events: a variable's value inserted into
    the text. They are still not done, and the page that uses them has to keep
    failing to compile instead of drawing them as two letters."""
    with pytest.raises(eventos.NoSePuede):
        eventos.cola_de_escapes(["tenés \\V[12] créditos"])


def test_un_escape_en_el_medio_tampoco():
    """With the window drawn all at once, a pause in the middle of the text
    cannot be modeled without making up how much text had been drawn. In the
    328 maps there is none: the 40 text boxes with escapes have them as a
    tail."""
    with pytest.raises(eventos.NoSePuede):
        eventos.cola_de_escapes(["uno\\|dos"])


def test_la_cabecera_lleva_los_renglones_el_cierre_y_las_pausas():
    """The byte `msg_empezar` reads, with the same masks as the ROM."""
    cabecera = eventos.mensaje_bytes(("a", "b"), pausas=3, autocierre=True)[0]
    assert cabecera & eventos.CABECERA_LINEAS == 2
    assert cabecera & eventos.CABECERA_AUTOCIERRE
    assert cabecera >> 4 == 3


def test_dos_cuadros_con_el_mismo_texto_y_distinta_cola_no_se_comparten():
    """The trap that would give zero: one waits for the player and the other does not."""
    mensajes = eventos.Mensajes()
    pelado = mensajes.agregar(["Ready for the big night?"])
    con_cola = mensajes.agregar(["Ready for the big night?\\|\\^"])
    assert pelado != con_cola, \
        "the same offset for two text boxes that last differently"
    assert mensajes.lineas(pelado) == mensajes.lineas(con_cola), \
        "the text is the same: the only thing that changes is the tail"
    assert mensajes.cola(pelado) == (0, False)
    assert mensajes.cola(con_cola) == (1, True)
    # And the same text box twice still costs a single offset.
    assert mensajes.agregar(["Ready for the big night?\\|\\^"]) == con_cola


def test_la_cola_se_saca_antes_de_recortar_el_renglon():
    """The other way around, a full line would eat its own `\\|\\^` and the
    text box would be left waiting for an A that RM2k does not ask for."""
    mensajes = eventos.Mensajes()
    largo = "x" * constantes.COLUMNAS
    donde = mensajes.agregar([largo + "\\|\\^"])
    assert mensajes.lineas(donde) == (largo,)
    assert mensajes.cola(donde) == (1, True)

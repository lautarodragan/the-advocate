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

from port import events
from port import constants


def test_the_tail_leaves_the_text_and_is_counted():
    """`\\|\\^` is what the game uses 25 times: one pause and auto-close."""
    lineas, pausas, autocierre = events.escape_tail(
        ["HELP!!", "That bandit... has a bow...\\|\\^"])
    assert lineas == ("HELP!!", "That bandit... has a bow...")
    assert (pausas, autocierre) == (1, True)


def test_three_pauses_in_a_row():
    """The `< Kiss >` of map 108, which is the most in the game."""
    _lineas, pausas, autocierre = events.escape_tail(
        ["                  < Kiss >\\|\\|\\|\\^"])
    assert (pausas, autocierre) == (3, True)


def test_the_tail_with_spaces_in_between():
    """The `RunDirectorScene` of map 98 is the only one that writes `\\| \\| \\| \\^`.

    The spaces in the tail go away with it: a space at the end of a line
    draws no pixel, so removing it gives the same screen.
    The ones before the first escape stay, because those are text.
    """
    lineas, pausas, autocierre = events.escape_tail(
        ["  ya vuelvo \\| \\| \\| \\^"])
    assert lineas == ("  ya vuelvo ",)
    assert (pausas, autocierre) == (3, True)


def test_an_unknown_escape_does_not_compile():
    """The three `\\V` of the common events: a variable's value inserted into
    the text. They are still not done, and the page that uses them has to keep
    failing to compile instead of drawing them as two letters."""
    with pytest.raises(events.CannotCompile):
        events.escape_tail(["tenés \\V[12] créditos"])


def test_an_escape_in_the_middle_does_not_either():
    """With the window drawn all at once, a pause in the middle of the text
    cannot be modeled without making up how much text had been drawn. In the
    328 maps there is none: the 40 text boxes with escapes have them as a
    tail."""
    with pytest.raises(events.CannotCompile):
        events.escape_tail(["uno\\|dos"])


def test_the_header_carries_lines_close_and_pauses():
    """The byte `msg_start` reads, with the same masks as the ROM."""
    cabecera = events.message_bytes(("a", "b"), pauses=3, auto_close=True)[0]
    assert cabecera & events.HEADER_LINES == 2
    assert cabecera & events.HEADER_AUTO_CLOSE
    assert cabecera >> 4 == 3


def test_two_boxes_with_same_text_and_different_tail_are_not_shared():
    """The trap that would give zero: one waits for the player and the other does not."""
    mensajes = events.Messages()
    pelado = mensajes.add(["Ready for the big night?"])
    con_cola = mensajes.add(["Ready for the big night?\\|\\^"])
    assert pelado != con_cola, \
        "the same offset for two text boxes that last differently"
    assert mensajes.lines(pelado) == mensajes.lines(con_cola), \
        "the text is the same: the only thing that changes is the tail"
    assert mensajes.tail(pelado) == (0, False)
    assert mensajes.tail(con_cola) == (1, True)
    # And the same text box twice still costs a single offset.
    assert mensajes.add(["Ready for the big night?\\|\\^"]) == con_cola


def test_the_tail_is_removed_before_trimming_the_line():
    """The other way around, a full line would eat its own `\\|\\^` and the
    text box would be left waiting for an A that RM2k does not ask for."""
    mensajes = events.Messages()
    largo = "x" * constants.COLUMNS
    donde = mensajes.add([largo + "\\|\\^"])
    assert mensajes.lines(donde) == (largo,)
    assert mensajes.tail(donde) == (1, True)

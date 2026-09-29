"""The text boxes rebuilt for the SNES width: `port.textos`.

It runs no ROM. It covers the function: that what it returns fits, that it
loses no words, and that it does not touch what already fit. That the
converter calls it, and that all of a game's text boxes fit, is checked by
the game's tests. Whether it reads well is for taro to say while playing.
"""

import pytest

from port import eventos                                # noqa: E402
from port import textos                                 # noqa: E402
from port import constants                             # noqa: E402


def _words(cuadros, con_hablante):
    desde = 1 if con_hablante else 0
    return " ".join(" ".join(c[desde:]) for c in cuadros).split()


def test_a_box_that_fits_is_left_alone():
    """Not even the spaces inside: they are the author's."""
    cuadro = ["                  < Kiss >"]
    assert textos.reajustar(cuadro) == [cuadro]


def test_it_is_rebuilt_and_keeps_the_speaker():
    cuadro = ["KERSH", "I have pressing business within the Linkage",
              "Block. No turning back."]
    salida = textos.reajustar(cuadro)
    assert len(salida) == 1
    assert salida[0][0] == "KERSH"
    assert all(len(t) <= constants.COLUMNS for t in salida[0])
    assert _words(salida, True) == _words([cuadro], True)


def test_what_does_not_fit_is_split_and_repeats_the_speaker():
    """As the game does with consecutive text boxes from the same character."""
    cuadro = ["MANTA",
              "According to this, the Catch Colony is connected",
              "to the Block by an electromagnetic Link, which",
              "keeps the Colony from drifting into space."]
    salida = textos.reajustar(cuadro)
    assert len(salida) == 2
    assert all(c[0] == "MANTA" for c in salida)
    assert all(len(c) <= constants.LINES for c in salida)
    assert _words(salida, True) == _words([cuadro], True)


def test_the_tail_goes_at_the_end_of_the_last_box():
    cuadro = ["CORE", "Thank you, Manta. And maybe... after all this,",
              "you'll be able to tell me the answer to the",
              "question none of my abilities... can.\\|\\^"]
    salida = textos.reajustar(cuadro)
    assert len(salida) > 1
    assert salida[-1][-1].endswith("can.\\|\\^")
    assert not any("\\" in t for c in salida[:-1] for t in c)


# A line that is not the last one and takes up less than this looks cut off.
CORTO = 2 * constants.COLUMNS // 3


@pytest.mark.parametrize("cuadro", [
    # The two that looked worst in what taro played on 2026-09-24: "Remember,"
    # and "Well," alone on their line, so that the ones below ended in a period.
    ["?????", "Remember, my alias for this operation is",
     '"Kersh." We should have the element of', "surprise."],
    ["TALAN", "Well, this decision won't get any easier.",
     "I've got to make up my mind and go!"],
    # The others from his captures that had the same problem.
    ["?????", "That security droid has been deactivated.",
     "Its attack mode has been switched off."],
    ["TALAN", "...but the Hover-Trams don't always run on",
     "time, and I might get stuck waiting for one."],
    ["TALAN", "It's Trash Dump 004 - right near my apartment.",
     "I'm not getting anywhere!"],
    ["TALAN", "Maybe there'll be another one along",
     "really soon... at least, I hope there will!"],
    ["CONDA", "Do you think he's one of the Lazer Teeth?",
     "Maybe they found out about our spy..."],
    ["CORE", "Thank you, Manta. And maybe... after all this,",
     "you'll be able to tell me the answer to the",
     "question none of my abilities... can."],
])
def test_no_line_breaks_too_early(cuadro):
    """Except the last one of each text box, no line ends up shorter than
    `CORTO`. All of these have a way of breaking that satisfies it."""
    salida = textos.reajustar(cuadro)
    for c in salida:
        assert c[0] == cuadro[0]
        cortos = [t for t in c[1:-1] if len(t) < CORTO]
        assert not cortos, c
    assert _words(salida, True) == _words([cuadro], True)


def test_a_line_of_whole_sentences_may_be_short():
    """The other side of the rule: breaking between two short sentences reads
    as the author's line break, and it is not traded for filling the line."""
    assert textos.reajustar(
        ["KERSH", "Time is running out. There's no turning back."]) == [
        ["KERSH", "Time is running out.", "There's no turning back."]]
    assert textos.reajustar(
        ["TALAN", "Ten minutes... I'm not sure I can make it."]) == [
        ["TALAN", "Ten minutes...", "I'm not sure I can make it."]]


def test_a_name_is_not_split_from_its_number():
    salida = textos.reajustar(
        ["TALAN", "I'd better not go back through Sector 33. The Lazer",
         "Teeth wouldn't be happy to see me..."])
    renglones = [t for c in salida for t in c]
    assert not any(t.endswith("Sector") for t in renglones), salida


def test_no_box_is_added_for_nothing():
    """If the text fits in one text box, it is not split in two to look
    better: one more text box is one more key press."""
    cuadro = ["TALAN", "Well... time to get away from the Agency. Now I've",
              "got an entire world to hide in..."]
    assert len(textos.reajustar(cuadro)) == 1


@pytest.mark.parametrize("linea, es", [
    ("KERSH", True),
    ("TRAM OFFICER", True),
    ("?????", True),
    ("WHAT?", False),
    ("NO!", False),
    ("Kersh", False),
])
def test_who_speaks(linea, es):
    assert textos.es_hablante(linea) is es


def test_unchanged_commands_are_the_same_objects():
    cuadro_que_entra = {"code": eventos.SHOW_MESSAGE, "indent": 1,
                        "parameters": [], "string": "Hi."}
    otro = {"code": 10310, "indent": 1, "parameters": [0, 0], "string": ""}
    largo = [{"code": eventos.SHOW_MESSAGE, "indent": 2, "parameters": [],
              "string": "MANTA"},
             {"code": eventos.SHOW_MESSAGE_2, "indent": 2, "parameters": [],
              "string": "I already told you. He didn't go this way. Twice."}]
    salida = textos.reajustar_comandos([cuadro_que_entra, otro] + largo)
    assert salida[0] is cuadro_que_entra and salida[1] is otro
    nuevos = salida[2:]
    assert nuevos[0]["code"] == eventos.SHOW_MESSAGE
    assert all(c["code"] == eventos.SHOW_MESSAGE_2 for c in nuevos[1:])
    assert all(c["indent"] == 2 for c in nuevos)

"""That the index in this folder's `README.md` names every test, and nothing
else.

It is the same rule as the index of A Blurred Line's tests, and for the same
reason: a hand-written index goes stale without warning. It does not check
whether what it says about each one is true; it checks that they are all
there and that they exist.
"""

import glob
import os
import re

AQUI = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(AQUI, "README.md")

# A bare file name: tests here do not go in subfolders.
NOMBRADA = re.compile(r"`(test_\w+\.py)`")


def _en_disco():
    return {os.path.basename(r)
            for r in glob.glob(os.path.join(AQUI, "test_*.py"))}


def _en_el_indice():
    with open(README, encoding="utf-8") as f:
        texto = f.read()
    indice = texto.split("## Which test covers what", 1)
    assert len(indice) == 2, "README.md no longer has \"Which test covers what\""
    return set(NOMBRADA.findall(indice[1]))


def test_toda_prueba_esta_en_el_indice():
    faltan = sorted(_en_disco() - _en_el_indice())
    assert not faltan, (
        "the index in tools/pruebas/README.md does not name: %s"
        % ", ".join(faltan))


def test_el_indice_no_nombra_pruebas_que_no_existen():
    sobran = sorted(_en_el_indice() - _en_disco())
    assert not sobran, (
        "the index in tools/pruebas/README.md names tests that do not exist: "
        "%s. Were they renamed or deleted?" % ", ".join(sobran))

"""Que el índice de `README.md`, en esta carpeta, nombre todas las pruebas, y
nada más.

Es la misma regla que el índice de las pruebas de A Blurred Line, y por la
misma razón: un índice escrito a mano se queda viejo sin avisar. No mira si
lo que dice de cada una es verdad; mira que estén todas y que existan.
"""

import glob
import os
import re

AQUI = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(AQUI, "README.md")

# Un nombre de archivo suelto: acá las pruebas no van en subcarpetas.
NOMBRADA = re.compile(r"`(test_\w+\.py)`")


def _en_disco():
    return {os.path.basename(r)
            for r in glob.glob(os.path.join(AQUI, "test_*.py"))}


def _en_el_indice():
    with open(README, encoding="utf-8") as f:
        texto = f.read()
    indice = texto.split("## Qué prueba cubre qué", 1)
    assert len(indice) == 2, "README.md ya no tiene \"Qué prueba cubre qué\""
    return set(NOMBRADA.findall(indice[1]))


def test_toda_prueba_esta_en_el_indice():
    faltan = sorted(_en_disco() - _en_el_indice())
    assert not faltan, (
        "el índice de tools/pruebas/README.md no nombra: %s"
        % ", ".join(faltan))


def test_el_indice_no_nombra_pruebas_que_no_existen():
    sobran = sorted(_en_el_indice() - _en_disco())
    assert not sobran, (
        "el índice de tools/pruebas/README.md nombra pruebas que no existen: "
        "%s. ¿Se renombraron o se borraron?" % ", ".join(sobran))

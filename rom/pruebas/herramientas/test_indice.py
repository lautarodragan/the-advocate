"""Que el índice de `pruebas/README.md` nombre todas las pruebas, y nada más.

Un índice escrito a mano se queda viejo sin avisar: alguien suma
`test_foo.py` y no lo anota, o renombra uno y el README sigue diciendo el
nombre viejo. Esto no mira si lo que dice de cada una es verdad —eso no lo
puede mirar nadie más que el que lee—; mira que estén todas y que existan.
"""

import glob
import os
import re

PRUEBAS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(PRUEBAS, "README.md")

# Una ruta desde `pruebas/`: `rpgmaker/test_menu_dibujo.py`.
NOMBRADA = re.compile(r"\b(\w+/test_\w+\.py)\b")


def _en_disco():
    return {os.path.relpath(r, PRUEBAS)
            for r in glob.glob(os.path.join(PRUEBAS, "*", "test_*.py"))}


def _en_el_readme():
    with open(README, encoding="utf-8") as f:
        return set(NOMBRADA.findall(f.read()))


def test_toda_prueba_esta_en_el_indice():
    faltan = sorted(_en_disco() - _en_el_readme())
    assert not faltan, (
        "pruebas/README.md, \"Qué prueba cubre qué\", no nombra: %s. Sumalas "
        "bajo su sistema, con la ruta desde pruebas/." % ", ".join(faltan))


def test_el_indice_no_nombra_pruebas_que_no_existen():
    sobran = sorted(_en_el_readme() - _en_disco())
    assert not sobran, (
        "pruebas/README.md nombra pruebas que no existen: %s. ¿Se renombraron "
        "o se borraron?" % ", ".join(sobran))


# Lo único que importa de una prueba, a propósito: el video juega las jugadas
# del recorrido tal cual. Ver el encabezado de `arnes/video.py`.
IMPORTAN_PRUEBAS = {"arnes/video.py"}


def test_ninguna_prueba_importa_de_otra():
    """Lo que dice el índice de `arnes/`: lo compartido vive ahí. Una prueba
    que importa de otra ata las dos sin que se vea —renombrar una, o correr
    sólo una carpeta, rompe la otra—, y así estuvo hasta el 2026-09-29."""
    importa = re.compile(r"^\s*(from|import)\s+test_\w+", re.MULTILINE)
    culpables = []
    for ruta in sorted(glob.glob(os.path.join(PRUEBAS, "**", "*.py"),
                                 recursive=True)):
        nombre = os.path.relpath(ruta, PRUEBAS)
        with open(ruta, encoding="utf-8") as f:
            if nombre not in IMPORTAN_PRUEBAS and importa.search(f.read()):
                culpables.append(nombre)
    assert not culpables, (
        "%s importan de otra prueba: lo que comparten va a un módulo de "
        "pruebas/arnes/" % ", ".join(culpables))

"""Que cada tramo con goldens del recorrido, o con fotos pendientes, lo juegue
alguna prueba.

Foto por foto lo cobra el recorrido mismo —`Recorrido.foto` y
`Recorrido.verificar_el_tramo`—, pero sólo en los tramos que se juegan: una
carpeta de `pruebas/golden/playthrough/` cuya prueba se renombró o se borró no
la abre nadie, y sus goldens no comparan nada sin que ninguna prueba falle.
Esto lo mira sin emular: el nombre del tramo tiene que estar escrito en alguna
prueba.

**Escrito** quiere decir una constante de texto de algún `.py` de `pruebas/`,
entera o partida en dos —`"debug-auto-" + nombre`, con `nombre` sacado de
otra constante—, que es como las arman las pruebas parametrizadas. No evalúa
nada: un nombre armado de otra manera da un falso rojo, y ahí lo que hay que
hacer es escribirlo entero.
"""

import ast
import glob
import os
import re

import recorrido

PRUEBAS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RENGLON = re.compile(r"^[a-z0-9-]+/\d\d-[a-z0-9-]+\.png$")


def _constantes():
    textos = set()
    for ruta in glob.glob(os.path.join(PRUEBAS, "**", "*.py"), recursive=True):
        with open(ruta, encoding="utf-8") as archivo:
            arbol = ast.parse(archivo.read(), ruta)
        textos |= {n.value for n in ast.walk(arbol)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    return textos


def _nombrado(tramo, textos):
    return tramo in textos or any(
        tramo.startswith(t) and tramo[len(t):] in textos
        for t in textos if t.endswith("-") and len(t) > 1)


def test_los_renglones_de_pendientes_son_fotos():
    malos = sorted(f for f in recorrido.pendientes() if not RENGLON.match(f))
    assert not malos, (
        "%s tiene renglones que no son `<tramo>/<NN>-<hito>.png`: %s"
        % (recorrido.PENDIENTES, ", ".join(malos)))


def test_todo_tramo_con_goldens_o_pendientes_lo_juega_una_prueba():
    tramos = {n for n in os.listdir(recorrido.GOLDEN)
              if os.path.isdir(os.path.join(recorrido.GOLDEN, n))}
    tramos |= {f.split("/", 1)[0] for f in recorrido.pendientes()}
    textos = _constantes()
    huerfanos = sorted(t for t in tramos if not _nombrado(t, textos))
    assert not huerfanos, (
        "ninguna prueba nombra los tramos %s, que tienen goldens en %s o "
        "renglones en %s: si la prueba se renombró, renombrá la carpeta; si "
        "se borró, sobran."
        % (", ".join(huerfanos), recorrido.GOLDEN, recorrido.PENDIENTES))

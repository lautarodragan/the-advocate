"""Que lo que declara el archivo de proyecto no esté también escrito en las
herramientas.

Desde el 2026-09-29 lo que es de A Blurred Line —qué mapas entran, cómo se
llama la ROM, qué efectos van enteros— vive en `rm2k-snes.toml`, y las
herramientas lo leen de ahí. Un valor del archivo que vuelve a aparecer
escrito en un `.py` de las herramientas es un default de ABL que se coló: si
el archivo cambia, ese lugar sigue con el de antes y nadie se entera.

Mira los textos del archivo —valores y nombres de clave de tablas como
`[sound_effects.whole]`— contra los strings de los `.py`, sin contar
comentarios ni docstrings, que nombran valores para que uno los encuentre.
Los números no, porque se repiten por cualquier otra razón; ni los textos
de menos de cinco caracteres, ni los flags del conversor, que son de él y
el archivo sólo los usa.
"""

import ast
import os

from common import settings, project

# Los que el archivo usa como palabra clave de su propio formato, y el nombre
# del cartucho que se juega, que las herramientas exigen: es su contrato, no
# una decisión del juego.
DEL_FORMATO = {"game", "all", "release"}

# Las listas de casos de cada cartucho: son nombres de archivo de
# `pruebas/casos/`, y los hay tan comunes —`batalla`— que cualquier string
# los repite. Sólo las listas: `[cases]` es la tabla de los dos casos con
# nombre propio, y ésos sí se miran.
SIN_MIRAR = {"cases", "excluded_cases"}

# `[paths]` entera: son nombres de carpeta, y las herramientas usan las mismas
# palabras para la forma de lo que arman —`parches/auto/` adentro del
# directorio de cada cartucho, a imagen de la del juego—. Armar a mano una
# ruta del juego con esas palabras lo cobra `test_proyecto.py`, de las
# herramientas, que mira las rutas y no los textos.
TABLAS_SIN_MIRAR = {"paths"}


def _textos(nodo):
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if clave in SIN_MIRAR and isinstance(valor, list):
                continue
            yield clave
            yield from _textos(valor)
    elif isinstance(nodo, list):
        for valor in nodo:
            yield from _textos(valor)
    elif isinstance(nodo, str):
        yield nodo


def _del_archivo():
    """Los textos del archivo que valen como valor, no como nombre de clave
    de las herramientas: las claves de las secciones fijas —`[rom]`,
    `name`…— no cuentan, porque ésas sí las escriben las herramientas."""
    datos = {k: v for k, v in settings.load().items()
             if k not in TABLAS_SIN_MIRAR}
    fijas = set()

    def claves(nodo, libres):
        if isinstance(nodo, dict):
            for clave, valor in nodo.items():
                if not libres:
                    fijas.add(clave)
                # Las tablas cuyas claves son del juego: nombres de efecto,
                # de CharSet, de cartucho.
                claves(valor, clave in ("whole", "palette_weight",
                                        "cartridges"))
        elif isinstance(nodo, list):
            for valor in nodo:
                claves(valor, False)
    claves(datos, False)
    return {t for t in _textos(datos)
            if len(t) >= 5 and not t.startswith("--") and t not in fijas
            and t not in DEL_FORMATO}


def _docstrings(arbol):
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.ClassDef,
                             ast.AsyncFunctionDef)):
            cuerpo = nodo.body
            if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                    and isinstance(cuerpo[0].value, ast.Constant)):
                yield cuerpo[0].value


def _nuestros():
    herramientas = project.tools()
    for raiz, subs, archivos in os.walk(herramientas):
        subs[:] = sorted(s for s in subs
                         if s not in ("target", "__pycache__")
                         and not os.path.isfile(os.path.join(raiz, s,
                                                             "Cargo.toml")))
        for archivo in sorted(archivos):
            if archivo.endswith(".py"):
                yield os.path.join(raiz, archivo)


def test_ninguna_herramienta_repite_un_valor_del_archivo_de_proyecto():
    del_archivo = _del_archivo()
    assert "ABLBackdropSJ08" in del_archivo, (
        "la prueba no está mirando lo que cree: %r" % sorted(del_archivo))
    repetidos = []
    for ruta in _nuestros():
        with open(ruta, encoding="utf-8") as archivo:
            arbol = ast.parse(archivo.read(), ruta)
        docs = {id(d) for d in _docstrings(arbol)}
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)
                    and id(nodo) not in docs and nodo.value in del_archivo):
                repetidos.append("%s:%d: %r" % (
                    os.path.relpath(ruta, project.tools()),
                    nodo.lineno, nodo.value))
    assert not repetidos, (
        "estos valores ya están en el archivo de proyecto y se leen de ahí: "
        "escritos en una herramienta, son un default del juego que no sigue "
        "al archivo.\n" + "\n".join(repetidos))

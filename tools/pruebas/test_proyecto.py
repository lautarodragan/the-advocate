"""Que dónde está cada cosa lo sepa `comun/proyecto.py`, y nadie más.

Antes de ese módulo, once `.py` calculaban la raíz del repo subiendo tres
carpetas desde `__file__`, y otros tantos armaban a mano `data/`,
`parches/manual/` o `rom/src/` a partir de ella. El 2026-09-29 el motor se
mudó a `tools/runtime/`, y `data/`, `parches/` y `pruebas/` adentro de
`rom/`: cada uno de ésos habría sido un lugar más para buscar, y con esto
fue cambiar unas líneas de `proyecto.py`. Ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`.

Mira los `.py` de `tools/` —los paquetes y sus pruebas—, y falla si alguno:

* **sube hasta la raíz desde `__file__`**: tres `dirname` o un `".."` en la
  misma sentencia que `__file__`. Subir dos, hasta `tools/`, sí se puede: es
  cómo un script que se ejecuta pone sus paquetes en el `sys.path` antes de
  poder importar nada, y eso incluye a `proyecto`;
* **arma una ruta del repo a mano**: un `os.path.join` que empieza por una
  carpeta de la raíz —`"data"`, `"tools/runtime"`…—, o que la pega detrás de la
  raíz —`RAIZ`, `proyecto.raiz()`—. Detrás de otra cosa no cuenta:
  `pruebas/` adentro de `tools/` es otra carpeta;
* **lee una variable de ambiente de las que dicen dónde está algo**, o
  escribe el valor por omisión de una: ésos viven en `proyecto.py`.

Lo que no mira: la prosa —comentarios, docstrings, `help=`—, que nombra
rutas para que uno las encuentre; ni este archivo, que las escribe a
propósito para ver que la red las agarra.
"""

import ast
import os

import pytest

from comun import proyecto

HERRAMIENTAS = proyecto.herramientas()
PROYECTO = os.path.join(HERRAMIENTAS, "comun", "proyecto.py")
ESTE = os.path.realpath(__file__)

# Las carpetas de la raíz. Un pedazo de ruta que empieza por una de éstas es
# una ruta del repo armada a mano.
DE_LA_RAIZ = {"data", "parches", "rom", "pruebas", "tools"}

# Cómo se llama la raíz cuando se la tiene en una variable.
RAIZ = {"RAIZ", "REPO", "raiz"}

# Las variables que dicen dónde está algo.
DE_AMBIENTE = {"ABL_GAME_DIR", "ABL_RTP_DIR", "ABL_SOUNDFONT", "ABL_CACHE",
               "CARTUCHOS", "SHARED"}

# Lo que se permite, con su porqué: (archivo relativo a `tools/`, pedazo).
PERMITIDOS = {
    # La forma del directorio de cada cartucho, que imita la de `rom/parches/`:
    # no es dónde está `rom/parches/` en el repo, y no se mueve con él.
    ("port/parches.py", "parches"),
}


def _nuestros():
    """Los `.py` de `tools/`, menos los proyectos de Rust y `proyecto.py`."""
    for raiz, subs, archivos in os.walk(HERRAMIENTAS):
        subs[:] = sorted(s for s in subs
                         if s not in ("target", "__pycache__")
                         and not os.path.isfile(os.path.join(raiz, s,
                                                             "Cargo.toml")))
        for archivo in sorted(archivos):
            ruta = os.path.join(raiz, archivo)
            if archivo.endswith(".py") and ruta not in (PROYECTO, ESTE):
                yield ruta


def _texto(nodo):
    return nodo.value if (isinstance(nodo, ast.Constant)
                          and isinstance(nodo.value, str)) else None


def _es_join(nodo):
    funcion = nodo.func
    return (isinstance(funcion, ast.Attribute) and funcion.attr == "join"
            and isinstance(funcion.value, ast.Attribute)
            and funcion.value.attr == "path")


def _es_la_raiz(nodo):
    """`RAIZ`, `REPO`, `raiz` o `algo.raiz()`."""
    if isinstance(nodo, ast.Name):
        return nodo.id in RAIZ
    return (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "raiz")


def _es_lectura_de_ambiente(nodo):
    """`os.environ.get("X", …)`, `os.getenv("X")` u `os.environ["X"]`."""
    if isinstance(nodo, ast.Call):
        funcion = nodo.func
        if (isinstance(funcion, ast.Attribute) and funcion.attr == "get"
                and isinstance(funcion.value, ast.Attribute)
                and funcion.value.attr == "environ") or (
                isinstance(funcion, ast.Attribute)
                and funcion.attr == "getenv"):
            return _texto(nodo.args[0]) if nodo.args else None
    if (isinstance(nodo, ast.Subscript)
            and isinstance(nodo.value, ast.Attribute)
            and nodo.value.attr == "environ"):
        return _texto(nodo.slice)
    return None


def violaciones(ruta, fuente=None):
    """Las violaciones de un archivo, como `línea: qué`."""
    if fuente is None:
        with open(ruta, encoding="utf-8") as archivo:
            fuente = archivo.read()
    relativo = os.path.relpath(ruta, HERRAMIENTAS)
    arbol = ast.parse(fuente, ruta)
    malas = []
    for sentencia in ast.walk(arbol):
        if not isinstance(sentencia, ast.stmt):
            continue
        # Sólo las sentencias simples: una compuesta —un `def`, un `if`—
        # contiene a las otras, y cada una se mira por su lado.
        if any(isinstance(h, ast.stmt) for h in ast.iter_child_nodes(sentencia)):
            continue
        nodos = list(ast.walk(sentencia))
        if any(isinstance(n, ast.Name) and n.id == "__file__" for n in nodos):
            dirnames = sum(1 for n in nodos if isinstance(n, ast.Attribute)
                           and n.attr == "dirname")
            if dirnames >= 3 or any(_texto(n) == ".." for n in nodos):
                malas.append("%d: sube hasta la raíz desde __file__: "
                             "proyecto.raiz()" % sentencia.lineno)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and _es_join(nodo):
            for k, arg in enumerate(nodo.args):
                texto = _texto(arg)
                if texto is None or (k and not _es_la_raiz(nodo.args[k - 1])):
                    continue
                primero = texto.split("/")[0]
                if (primero in DE_LA_RAIZ
                        and (relativo, primero) not in PERMITIDOS):
                    malas.append("%d: arma a mano una ruta de %s/: va en "
                                 "proyecto.py" % (nodo.lineno, primero))
        variable = _es_lectura_de_ambiente(nodo)
        if variable in DE_AMBIENTE:
            malas.append("%d: lee %s: va en proyecto.py"
                         % (nodo.lineno, variable))
        texto = _texto(nodo)
        if texto and texto.startswith(("/extras", "/shared")):
            malas.append("%d: un valor por omisión del ambiente: va en "
                         "proyecto.py" % nodo.lineno)
    return malas


def test_nadie_mas_sabe_donde_esta_cada_cosa():
    malas = []
    for ruta in _nuestros():
        malas += ["%s:%s" % (os.path.relpath(ruta, HERRAMIENTAS), v)
                  for v in violaciones(ruta)]
    assert not malas, (
        "dónde está cada cosa lo sabe comun/proyecto.py y nadie más:\n  "
        + "\n  ".join(malas))


@pytest.mark.parametrize("fuente", [
    'RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(\n'
    '    os.path.realpath(__file__))))\n',
    'REPO = os.path.join(os.path.dirname(__file__), "..", "..")\n',
    'DATOS = os.path.join(RAIZ, "data", "maps")\n',
    'MAIN = os.path.join(RAIZ, "tools/runtime/main.s")\n',
    'JUEGO = os.environ.get("ABL_GAME_DIR", "/extras/abl-rm")\n',
    'REEMPLAZOS = "/extras/msu"\n',
])
def test_la_red_ve_cada_forma(fuente):
    """Cada forma que había antes de `proyecto.py` tiene que dar una
    violación: si no, la prueba de arriba no está mirando."""
    assert violaciones(os.path.join(HERRAMIENTAS, "x", "y.py"), fuente)


def test_subir_hasta_tools_se_puede():
    """El arranque de un script, que pone `tools/` en el `sys.path` antes de
    poder importar `proyecto`."""
    assert not violaciones(os.path.join(HERRAMIENTAS, "x", "y.py"),
                           'sys.path.insert(0, os.path.dirname(os.path.dirname('
                           'os.path.realpath(__file__))))\n')

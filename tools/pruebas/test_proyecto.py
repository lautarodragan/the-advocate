"""That where each thing is is known by `common/proyecto.py`, and nobody else.

Before that module, eleven `.py` files computed the repo root by climbing
three folders from `__file__`, and as many more built `data/`,
`parches/manual/` or `rom/src/` by hand from it. On 2026-09-29 the runtime
moved to `tools/runtime/`, and `data/`, `parches/` and `pruebas/` into
`rom/`: each of those would have been one more place to search, and with
this it took changing a few lines of `proyecto.py`. See
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`.

It looks at the `.py` files of `tools/` —the packages and their tests—, and
fails if any of them:

* **climbs up to the root from `__file__`**: three `dirname` or a `".."` in
  the same statement as `__file__`. Climbing two, up to `tools/`, is allowed:
  that is how an executed script puts its packages on `sys.path` before it
  can import anything, and that includes `proyecto`;
* **builds a repo path by hand**: an `os.path.join` that starts with a root
  folder —`"data"`, `"tools/runtime"`…—, or that sticks it after the root
  —`RAIZ`, `proyecto.raiz()`—. After anything else it does not count:
  `pruebas/` inside `tools/` is another folder;
* **reads one of the environment variables that say where something is**, or
  writes the default value of one: since 2026-09-29 that arrives by flags
  —see `common/ambiente.py`—, and the machine's values belong to whoever
  calls the tools.

And separately, `test_ninguna_herramienta_sabe_de_abl`, because it is another
rule and the one above does not see it: that no `.py` of `tools/` reads an
`ABL_*` variable —any of them, not only those in the list—, or writes `rom/`
as a piece of a path. The tools find the game through its project file, and
its paths are declared by it: knowing that A Blurred Line lives in `rom/` is
knowing about a game.

What it does not look at: the prose —comments, docstrings, `help=`, the
messages—, which names paths so one can find them; nor this file, which
writes them on purpose to see that the net catches them.
"""

import ast
import os

import pytest

from common import proyecto

HERRAMIENTAS = proyecto.herramientas()
ESTE = os.path.realpath(__file__)

# The root folders. A piece of a path that starts with one of these is a repo
# path built by hand.
DE_LA_RAIZ = {"data", "parches", "rom", "pruebas", "tools"}

# What the root is called when it is held in a variable.
RAIZ = {"RAIZ", "REPO", "raiz"}

# The variables that say where something is.
DE_AMBIENTE = {"ABL_GAME_DIR", "ABL_RTP_DIR", "ABL_SOUNDFONT", "ABL_CACHE",
               "CARTUCHOS", "SHARED"}

# What is allowed, with its reason: (file relative to `tools/`, piece).
PERMITIDOS = {
    # The shape of each cartridge's directory, which imitates `rom/parches/`:
    # it is not where `rom/parches/` is in the repo, and does not move with it.
    ("port/parches.py", "parches"),
}


def _nuestros():
    """The `.py` files of `tools/`, minus the Rust projects. `proyecto.py`
    too: until 2026-09-29 it was the exception, because the machine's values
    lived there, and it no longer has them."""
    for raiz, subs, archivos in os.walk(HERRAMIENTAS):
        subs[:] = sorted(s for s in subs
                         if s not in ("target", "__pycache__")
                         and not os.path.isfile(os.path.join(raiz, s,
                                                             "Cargo.toml")))
        for archivo in sorted(archivos):
            ruta = os.path.join(raiz, archivo)
            if archivo.endswith(".py") and ruta != ESTE:
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
    """`RAIZ`, `REPO`, `raiz` or `something.raiz()`."""
    if isinstance(nodo, ast.Name):
        return nodo.id in RAIZ
    return (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "raiz")


def _es_lectura_de_ambiente(nodo):
    """`os.environ.get("X", …)`, `os.getenv("X")` or `os.environ["X"]`."""
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
    """A file's violations, as `line: what`."""
    if fuente is None:
        with open(ruta, encoding="utf-8") as archivo:
            fuente = archivo.read()
    relativo = os.path.relpath(ruta, HERRAMIENTAS)
    arbol = ast.parse(fuente, ruta)
    malas = []
    for sentencia in ast.walk(arbol):
        if not isinstance(sentencia, ast.stmt):
            continue
        # Only the simple statements: a compound one —a `def`, an `if`—
        # contains the others, and each is looked at on its own.
        if any(isinstance(h, ast.stmt) for h in ast.iter_child_nodes(sentencia)):
            continue
        nodos = list(ast.walk(sentencia))
        if any(isinstance(n, ast.Name) and n.id == "__file__" for n in nodos):
            dirnames = sum(1 for n in nodos if isinstance(n, ast.Attribute)
                           and n.attr == "dirname")
            if dirnames >= 3 or any(_texto(n) == ".." for n in nodos):
                malas.append("%d: climbs up to the root from __file__: "
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
                    malas.append("%d: builds a path to %s/ by hand: it goes in "
                                 "proyecto.py" % (nodo.lineno, primero))
        variable = _es_lectura_de_ambiente(nodo)
        if variable in DE_AMBIENTE:
            malas.append("%d: reads %s: it arrives by flag, see common/ambiente.py"
                         % (nodo.lineno, variable))
        texto = _texto(nodo)
        if texto and texto.startswith(("/extras", "/shared")):
            malas.append("%d: a machine default value: it belongs to whoever "
                         "calls the tools" % nodo.lineno)
    return malas


def _prosa(arbol):
    """The strings that are prose: docstrings and `help=`."""
    ids = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.FunctionDef, ast.ClassDef,
                             ast.AsyncFunctionDef)):
            cuerpo = nodo.body
            if (cuerpo and isinstance(cuerpo[0], ast.Expr)
                    and isinstance(cuerpo[0].value, ast.Constant)):
                ids.add(id(cuerpo[0].value))
        if isinstance(nodo, ast.keyword) and nodo.arg == "help":
            ids.update(id(n) for n in ast.walk(nodo.value))
    return ids


def de_abl(ruta, fuente=None):
    """What a file knows about A Blurred Line, as `line: what`: an `ABL_*`
    variable read, or `rom/` written as a piece of a path —a string without
    whitespace, which is what a path looks like and not a message—."""
    if fuente is None:
        with open(ruta, encoding="utf-8") as archivo:
            fuente = archivo.read()
    arbol = ast.parse(fuente, ruta)
    prosa = _prosa(arbol)
    malas = []
    for nodo in ast.walk(arbol):
        variable = _es_lectura_de_ambiente(nodo)
        if variable and variable.startswith("ABL_"):
            malas.append("%d: reads %s, which belongs to A Blurred Line"
                         % (nodo.lineno, variable))
        texto = _texto(nodo)
        if (texto and id(nodo) not in prosa
                and not any(c.isspace() for c in texto)
                and (texto.startswith("rom/") or "/rom/" in texto)):
            malas.append("%d: names %r, which is where A Blurred Line lives"
                         % (nodo.lineno, texto))
    return malas


def test_nadie_mas_sabe_donde_esta_cada_cosa():
    malas = []
    for ruta in _nuestros():
        malas += ["%s:%s" % (os.path.relpath(ruta, HERRAMIENTAS), v)
                  for v in violaciones(ruta)]
    assert not malas, (
        "where each thing is is known by common/proyecto.py and nobody else:\n  "
        + "\n  ".join(malas))


def test_ninguna_herramienta_sabe_de_abl():
    malas = []
    for ruta in _nuestros():
        malas += ["%s:%s" % (os.path.relpath(ruta, HERRAMIENTAS), v)
                  for v in de_abl(ruta)]
    assert not malas, (
        "the tools know about no game: they find the project "
        "through its rm2k-snes.toml, its paths are declared by it and the "
        "machine's values arrive by flags:\n  " + "\n  ".join(malas))


@pytest.mark.parametrize("fuente", [
    'JUEGO = os.environ.get("ABL_GAME_DIR", "/extras/abl-rm")\n',
    'JUEGO = os.environ["ABL_OTRA_COSA"]\n',
    'JUEGO = os.getenv("ABL_LO_QUE_SEA")\n',
    'DATOS = "rom/data"\n',
    'open("../rom/rm2k-snes.toml")\n',
    'DATOS = os.path.join(RAIZ, "rom/data")\n',
])
def test_la_red_de_abl_ve_cada_forma(fuente):
    assert de_abl(os.path.join(HERRAMIENTAS, "x", "y.py"), fuente)


@pytest.mark.parametrize("fuente", [
    '"""Lee `rom/data/`."""\n',
    'parser.add_argument("x", help="rom/build/release")\n',
    'sys.exit("pasame `rom/build/release` y no dos")\n',
    'perillas.valor("rom", "name")\n',
    'AVISO = os.environ.get("SIN_CACHE")\n',
])
def test_la_prosa_y_la_seccion_rom_no_son_abl(fuente):
    """Naming `rom/` so that one can find it is not knowing where it is:
    neither is `[rom]`, which is a section of the project file."""
    assert not de_abl(os.path.join(HERRAMIENTAS, "x", "y.py"), fuente)


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
    """Every form that existed before `proyecto.py` has to give a violation:
    otherwise the test above is not looking."""
    assert violaciones(os.path.join(HERRAMIENTAS, "x", "y.py"), fuente)


def test_subir_hasta_tools_se_puede():
    """A script's startup, which puts `tools/` on `sys.path` before it can
    import `proyecto`."""
    assert not violaciones(os.path.join(HERRAMIENTAS, "x", "y.py"),
                           'sys.path.insert(0, os.path.dirname(os.path.dirname('
                           'os.path.realpath(__file__))))\n')

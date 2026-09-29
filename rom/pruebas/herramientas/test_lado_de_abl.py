"""Que el lado de ABL no sepa dónde viven las herramientas.

Es el primer paso para separar las herramientas de ABL en dos repos —ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`—: ABL no sabe que
existe el directorio de las herramientas, ni que están escritas en Python;
sabe que hay una suite de ejecutables en el PATH. La regla es de taro, el
2026-09-28, y esto es su prueba: un grep.

**Qué es el lado de ABL**, para esta prueba:

* `justfile`, entero, salvo las recetas de `RECETAS_QUE_NOMBRAN_TOOLS`. Las
  que arman, prueban o instalan las herramientas están en `tools/justfile`,
  que es del otro lado. En el resto no se nombra `tools/` ni Python, ni en
  una receta ni en un comentario.
* `parches/` y `data/`: el contenido del juego. Son lo más claramente de ABL
  que hay en el repo.
* `pruebas/` y `pytest.ini`, **con una lista de excepciones por archivo**
  (`PRUEBAS_QUE_TODAVIA_NOMBRAN_TOOLS`). Las pruebas son de ABL, pero hoy
  importan los paquetes de las herramientas y los nombran en su prosa: la
  lista es lo que falta. **Sólo puede achicarse**: falla si un archivo que
  no está nombra `tools/`, y también si uno de la lista ya no lo hace, para
  que la lista diga siempre la verdad. Agregarle un archivo es deshacer la
  regla, y eso se habla con taro antes.

Lo que **no** es el lado de ABL, y por qué: `rom/src/` y `tools/` son el
motor y las herramientas, del otro lado. `README.md`, `AGENTS.md`, `docs/` y
`workflow/` describen el repo entero, las dos mitades, y se parten con él.

**Qué es "nombrar `tools/`"**: la ruta escrita (`tools/…`), el nombre del
directorio como pedazo de ruta en un string (`"tools"`, que es cómo se arma
con `os.path.join`) o en el `pythonpath` de pytest. No cuenta la palabra
suelta: `data/` tiene diálogos en inglés que dicen "tools". Y no mira los
imports —`from rpgmaker import lcf`—, que nombran un paquete y no dónde
está: ésos se van cuando se separen las pruebas.
"""

import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

NOMBRA_TOOLS = re.compile(
    r"\btools/|[\"']tools[\"']|^\s*pythonpath\s*=.*\btools\b", re.MULTILINE)

# `python`, `python3`, `Python`… pero no `python-pytest-xdist`, que es el
# nombre del paquete de Arch que se le dice a uno que instale.
NOMBRA_PYTHON = re.compile(r"\bpython(?!-)", re.IGNORECASE)

# Las recetas del `justfile` que pueden nombrar `tools/`. Hasta el
# 2026-09-29 eran las nueve que arman, prueban o instalan las herramientas;
# ese día se mudaron a `tools/justfile`, y queda una sola: la guarda que, en
# un worktree sin sus herramientas, tiene que decir el comando que las
# instala, y ése vive en `tools/`. Sólo puede achicarse.
RECETAS_QUE_NOMBRAN_TOOLS = {
    "_herramientas_del_checkout",
}

# Relativas a la raíz del repo. Las que arman el camino de los imports con
# `tools/` —`pytest.ini`, `video.py`— se van cuando las pruebas se separen de
# las herramientas. Las demás lo nombran en la prosa, para decir dónde está
# lo que prueban, y se van al reescribirla. El 2026-09-29 salieron cinco: las
# pruebas que no necesitan el juego se mudaron con las herramientas, y los
# pedazos que se quedaron ya no nombran `tools/`.
PRUEBAS_QUE_TODAVIA_NOMBRAN_TOOLS = {
    "pytest.ini",
    "pruebas/README.md",
    "pruebas/conftest.py",
    "pruebas/abl/test_msu.py",
    "pruebas/abl/test_msu_datos.py",
    "pruebas/abl/test_msu_efectos.py",
    "pruebas/abl/test_recorrido_capitulo_golden.py",
    "pruebas/abl/test_recorrido_carrera_golden.py",
    "pruebas/arnes/consola.py",
    "pruebas/arnes/datos.py",
    "pruebas/arnes/dibujo.py",
    "pruebas/arnes/lz2.py",
    "pruebas/arnes/tanda.py",
    "pruebas/arnes/video.py",
    "pruebas/herramientas/test_lz2.py",
    "pruebas/rpgmaker/test_batalla.py",
    "pruebas/rpgmaker/test_batalla_escena_dibujo.py",
    "pruebas/rpgmaker/test_comandos_golden.py",
    "pruebas/rpgmaker/test_experiencia_dibujo.py",
    "pruebas/rpgmaker/test_musica_escrituras.py",
    "pruebas/rpgmaker/test_musica_paquete.py",
    "pruebas/rpgmaker/test_musica_techos.py",
    "pruebas/rpgmaker/test_pila.py",
}

# Lo que no es fuente: salida de las pruebas y cachés de Python.
NO_SE_MIRA = {"__pycache__", "snapshots"}

# Esta prueba nombra `tools/` porque es la regla, no porque lo use.
ESTA = os.path.relpath(os.path.abspath(__file__), RAIZ)

# Una receta del `justfile`: el nombre en la columna 0, y los primeros dos
# puntos de la línea no son los de una asignación (`:=`). Los parámetros
# pueden llevar `=`, por sus valores por omisión: `datos DIR="data":`.
RECETA = re.compile(r"^@?([A-Za-z_][\w-]*)[^:\n]*:(?!=)")


def _archivos(*directorios):
    for directorio in directorios:
        for raiz, subs, archivos in os.walk(os.path.join(RAIZ, directorio)):
            subs[:] = sorted(s for s in subs if s not in NO_SE_MIRA)
            for archivo in sorted(archivos):
                yield os.path.relpath(os.path.join(raiz, archivo), RAIZ)


def _nombra_tools(relativo):
    with open(os.path.join(RAIZ, relativo), "rb") as f:
        texto = f.read().decode("utf-8", errors="replace")
    return bool(NOMBRA_TOOLS.search(texto))


def _recetas_del_justfile():
    """Cada línea del `justfile` con la receta a la que pertenece: la receta
    y su cuerpo —lo indentado, aunque tenga blancos en el medio— son de
    ella, y los comentarios y asignaciones de arriba son de la receta que
    viene. Lo que quede después de la última no es de ninguna."""
    with open(os.path.join(RAIZ, "justfile"), encoding="utf-8") as f:
        lineas = f.read().splitlines()
    de = [None] * len(lineas)
    pendientes = []
    actual = None
    for i, linea in enumerate(lineas):
        receta = RECETA.match(linea)
        if receta:
            actual = receta.group(1)
            for j in pendientes:
                de[j] = actual
            pendientes = []
            de[i] = actual
        elif actual is not None and linea[:1] in (" ", "\t"):
            de[i] = actual
        else:
            if linea.strip():
                actual = None
            pendientes.append(i)
    return list(zip(lineas, de))


def test_el_justfile_no_nombra_python():
    malas = ["%d: %s" % (n, linea.strip())
             for n, (linea, receta) in enumerate(_recetas_del_justfile(), 1)
             if NOMBRA_PYTHON.search(linea)
             and receta not in RECETAS_QUE_NOMBRAN_TOOLS]
    assert not malas, (
        "el justfile nombra Python, y no tiene que saber que existe: llama "
        "ejecutables por su nombre, que instala `just -f tools/justfile herramientas`.\n"
        + "\n".join(malas))


def test_el_justfile_no_nombra_tools_fuera_de_sus_recetas():
    lineas = _recetas_del_justfile()
    malas = ["%d (%s): %s" % (n, receta or "fuera de toda receta",
                              linea.strip())
             for n, (linea, receta) in enumerate(lineas, 1)
             if NOMBRA_TOOLS.search(linea)
             and receta not in RECETAS_QUE_NOMBRAN_TOOLS]
    assert not malas, (
        "el justfile nombra tools/ en recetas de ABL: ABL conoce ejecutables "
        "del PATH y no dónde viven. Si es una herramienta nueva, instalala en "
        "`just -f tools/justfile herramientas` y llamala por su nombre.\n" + "\n".join(malas))
    limpias = sorted(RECETAS_QUE_NOMBRAN_TOOLS - {
        receta for linea, receta in lineas if NOMBRA_TOOLS.search(linea)})
    assert not limpias, (
        "estas recetas ya no nombran tools/: sacalas de "
        "RECETAS_QUE_NOMBRAN_TOOLS, que sólo puede achicarse: %s"
        % ", ".join(limpias))


def test_parches_y_data_no_nombran_tools():
    malos = [r for r in _archivos("parches", "data") if _nombra_tools(r)]
    assert not malos, (
        "parches/ y data/ son el juego, y no saben dónde viven las "
        "herramientas: %s" % ", ".join(malos))


def test_las_pruebas_nuevas_no_nombran_tools():
    nombran = {r for r in _archivos("pruebas")
               if r != ESTA and _nombra_tools(r)}
    if _nombra_tools("pytest.ini"):
        nombran.add("pytest.ini")
    nuevas = sorted(nombran - PRUEBAS_QUE_TODAVIA_NOMBRAN_TOOLS)
    assert not nuevas, (
        "estos archivos nombran tools/ y no están en la lista de "
        "excepciones, que sólo puede achicarse: %s. Si hace falta un script "
        "de las herramientas, que lo llame por el nombre con que lo instala "
        "`just -f tools/justfile herramientas`." % ", ".join(nuevas))
    limpias = sorted(PRUEBAS_QUE_TODAVIA_NOMBRAN_TOOLS - nombran)
    assert not limpias, (
        "estos ya no nombran tools/ —o no existen—: sacalos de "
        "PRUEBAS_QUE_TODAVIA_NOMBRAN_TOOLS: %s" % ", ".join(limpias))

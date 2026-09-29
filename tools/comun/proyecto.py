"""Dónde está cada cosa: el único lugar que lo sabe.

Una función por lugar, y los valores por omisión del ambiente, que antes
calculaban por su cuenta once módulos y armaban a mano otros tantos. Ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`.

**Las herramientas no saben dónde vive el juego: lo encuentran.** Buscan
`rm2k-snes.toml` desde el directorio actual hacia arriba, como cargo busca
su `Cargo.toml`, o lo reciben por `--proyecto`. Lo del repo —las
herramientas, el runtime, la raíz— sale de dónde está este archivo.

Son funciones y no constantes para que un lugar pueda depender de otro sin
que importe el orden en que se escriben, y para que nada se calcule al
importar: el proyecto se busca la primera vez que alguien pregunta por él,
así que importar las herramientas no pide un juego.

No importa nada de `tools/`: está en la capa de más abajo, y la usan todas.
"""

import os

# `realpath` y no `abspath`: los scripts que se ejecutan se instalan en el
# PATH como symlinks, y lo que importa es dónde está el archivo de verdad.
_HERRAMIENTAS = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


# Lo que es del repo.

def herramientas():
    """`tools/`: los paquetes de Python, que es donde vive este archivo."""
    return _HERRAMIENTAS


def raiz():
    """La raíz del repo: donde corren `ca65` y `ld65`, y contra la que se
    escriben las rutas relativas que terminan adentro de un `.dbg` o de un
    `.inc`. Es para lo que es del repo, como `.git`: el juego no se busca
    desde acá."""
    return os.path.dirname(_HERRAMIENTAS)


def runtime():
    """El motor en ensamblador: viaja con las herramientas, y se arma junto
    con los `.inc` de cada juego."""
    return os.path.join(herramientas(), "runtime")


# El proyecto: el juego que se arma. Las herramientas no saben dónde vive;
# lo encuentran.

ARCHIVO = "rm2k-snes.toml"


class NoHayProyecto(SystemExit):
    """No se encontró el archivo de proyecto. Es un `SystemExit` y no un error
    cualquiera porque lo que lo arregla es cómo se corrió la herramienta, no
    su código: un ejecutable corta con el mensaje y sin traza."""


_directorio = None


def buscar(desde):
    """El directorio más cercano, `desde` o uno de más arriba, que tiene un
    `rm2k-snes.toml`; o None. Es cómo cargo encuentra su `Cargo.toml`."""
    actual = os.path.abspath(desde)
    while True:
        if os.path.isfile(os.path.join(actual, ARCHIVO)):
            return actual
        padre = os.path.dirname(actual)
        if padre == actual:
            return None
        actual = padre


def fijar(directorio):
    """Usa el proyecto de `directorio`, sin buscar: es `--proyecto`, y lo que
    hacen las pruebas de un juego, que saben dónde están."""
    global _directorio
    directorio = os.path.abspath(directorio)
    if not os.path.isfile(os.path.join(directorio, ARCHIVO)):
        raise NoHayProyecto("%s no tiene un %s: --proyecto es el directorio "
                            "donde está ese archivo" % (directorio, ARCHIVO))
    _directorio = directorio


def directorio():
    """La raíz del proyecto: donde está `rm2k-snes.toml`. Si nadie la fijó,
    se busca desde el directorio actual hacia arriba, la primera vez que se
    pide y no al importar: importar las herramientas no pide un juego."""
    global _directorio
    if _directorio is None:
        desde = os.getcwd()
        encontrado = buscar(desde)
        if encontrado is None:
            raise NoHayProyecto(
                "no encontré un %s en %s ni en ninguna carpeta de más arriba: "
                "corré esto desde adentro del proyecto, o pasale "
                "--proyecto <directorio>" % (ARCHIVO, desde))
        _directorio = encontrado
    return _directorio


def argumento(parser):
    """Suma `--proyecto` al parser de un ejecutable, para que figure en su
    `--help` y no lo rechace. Quien lo usa es `desde_la_linea_de_comandos`."""
    parser.add_argument(
        "--proyecto", metavar="DIRECTORIO",
        help="el directorio donde está %s. Sin esto, se busca desde el "
             "directorio actual hacia arriba" % ARCHIVO)


def desde_la_linea_de_comandos(argv=None):
    """Toma `--proyecto` de la línea de comandos, si está.

    Va en el arranque de cada ejecutable, antes de importar nada que lea el
    archivo de proyecto —`cartuchos` lo lee al importarse—, así que no puede
    esperar al `parse_args` de su `main`: lee sólo este flag y deja los demás
    para él."""
    import argparse
    previo = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    previo.add_argument("--proyecto")
    leidos, _resto = previo.parse_known_args(argv)
    if leidos.proyecto:
        fijar(leidos.proyecto)


def archivo_de_proyecto():
    """`rm2k-snes.toml`: las perillas del juego. Lo lee `comun/perillas.py`."""
    return os.path.join(directorio(), ARCHIVO)


def _ruta(clave):
    """Una ruta de `[paths]`: la declara el archivo, relativa a él. Cómo está
    armado el juego por dentro es del juego, no de las herramientas."""
    from comun import perillas      # adentro: `perillas` importa éste
    return os.path.normpath(os.path.join(
        directorio(), perillas.valor("paths", clave, tipo=str)))


def build():
    """`[paths] build`: todo lo que se arma, y nada versionado."""
    return _ruta("build")


def data():
    """`[paths] data`: el juego volcado a JSON."""
    return _ruta("data")


def parches():
    """`[paths] patches`: lo que se decidió sobre el juego, `manual/` y
    `auto/`. Lo de adentro tiene la forma que le dan las herramientas."""
    return _ruta("patches")


def parches_manual():
    """Lo rediseñado a mano: los forks, los mapas nuevos, los ChipSets."""
    return os.path.join(parches(), "manual")


def parches_auto():
    """Lo que decidió el conversor y se versiona."""
    return os.path.join(parches(), "auto")


def casos():
    """`[paths] cases`: los casos de la tanda, un JSON por caso. Los lee
    `cartuchos.py`, que los mete en las páginas de prueba."""
    return _ruta("cases")


# Lo que es de la máquina. Los nombres de las variables y sus valores por
# omisión son los de siempre: cambiar uno cambia dónde se lee el juego.

def juego():
    """El proyecto RM2k original: ver `rpgmaker/recursos.py`."""
    return os.environ.get("ABL_GAME_DIR", "/extras/abl-rm")


def rtp():
    """El RTP de Don Miguel: ver `rpgmaker/recursos.py`."""
    return os.environ.get("ABL_RTP_DIR", "/extras/rtp")


def soundfont():
    """El banco del que salen las muestras: ver `audio/snes_samples.py`."""
    return os.environ.get(
        "ABL_SOUNDFONT",
        "/extras/soundfonts/Microsoft GS Wavetable Synth.sf2")


def reemplazos_msu():
    """Dónde se buscan los reemplazos de las pistas de MSU-1. No tiene
    variable: se cambia con `--reemplazos` de `rm2k-snes-msu`."""
    return "/extras/msu"


def cache():
    """El caché en disco del conversor: ver `comun/cache_disco.py`."""
    return os.environ.get("ABL_CACHE", os.path.join(build(), "cache"))


def cartuchos_de_prueba():
    """Dónde se arman los cartuchos de la tanda, menos `release`: ver
    `cartuchos.directorio`."""
    return os.environ.get("CARTUCHOS", os.path.join(build(), "tests"))


def compartido():
    """Donde taro encuentra lo que se le entrega: ver `ensamblado/entregar.py`."""
    return os.environ.get("SHARED", "/shared")

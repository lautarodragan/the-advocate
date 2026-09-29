"""Dónde está cada cosa: el único lugar que lo sabe.

Una función por lugar, y los valores por omisión del ambiente, que antes
calculaban por su cuenta once módulos y armaban a mano otros tantos. El
2026-09-29 el motor se mudó a `tools/runtime/`, y `data/`, `parches/` y
`pruebas/` adentro de `rom/` —ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md`—, y eso fue
cambiar las líneas de acá y nada más.

Son funciones y no constantes para que un lugar pueda depender de otro sin
que importe el orden en que se escriben, y para que las de ambiente lean la
variable cuando se las llama. Los módulos que ya tenían su constante —
`recursos.GAME_DIR`, `snes_samples.SOUNDFONT`— la siguen teniendo, leída de
acá al importarse, igual que antes leían `os.environ`.

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
    `.inc`."""
    return os.path.dirname(_HERRAMIENTAS)


def runtime():
    """El motor en ensamblador: viaja con las herramientas, y se arma junto
    con los `.inc` de cada juego."""
    return os.path.join(herramientas(), "runtime")


def abl():
    """`rom/`: la raíz de A Blurred Line. Lo que sigue cuelga de acá."""
    return os.path.join(raiz(), "rom")


def archivo_de_proyecto():
    """`rom/rm2k-snes.toml`: las perillas del juego. Lo lee `comun/perillas.py`."""
    return os.path.join(abl(), "rm2k-snes.toml")


def build():
    """`rom/build/`: todo lo que se arma, y nada versionado."""
    return os.path.join(abl(), "build")


def data():
    """El juego volcado a JSON."""
    return os.path.join(abl(), "data")


def parches():
    """Lo que se decidió sobre el juego: `manual/` y `auto/`."""
    return os.path.join(abl(), "parches")


def parches_manual():
    """Lo rediseñado a mano: los forks, los mapas nuevos, los ChipSets."""
    return os.path.join(parches(), "manual")


def parches_auto():
    """Lo que decidió el conversor y se versiona."""
    return os.path.join(parches(), "auto")


def pruebas():
    return os.path.join(abl(), "pruebas")


def casos():
    """Los casos de la tanda, un JSON por caso."""
    return os.path.join(pruebas(), "casos")


def goldens():
    """Las capturas congeladas: `tanda/`, `playthrough/`…"""
    return os.path.join(pruebas(), "golden")


def snapshots():
    """Lo que dejan las pruebas para mirar: no se versiona."""
    return os.path.join(pruebas(), "snapshots")


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

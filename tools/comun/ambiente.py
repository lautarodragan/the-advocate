"""Lo que es de la máquina y no del proyecto: dónde está el juego original,
el RTP, el SoundFont, los reemplazos de las pistas de MSU-1, el caché y
dónde se entrega.

**Llega por flags, no por variables de ambiente.** Hasta el 2026-09-29 las
herramientas leían `ABL_GAME_DIR` y compañía, con los valores de esta
máquina de default: sabían cómo se llama el juego y dónde vive. Ahora cada
ejecutable recibe lo que necesita —`--game-dir`, `--rtp-dir`,
`--soundfont`…—, lo fija acá con `desde_argumentos`, y el resto de las
herramientas lo lee de acá. Qué variable apunta a qué, y los valores de la
máquina, son del que las llama: el `justfile` del juego.

**Un valor que nadie fijó es un error, no un default**, salvo los que
cuelgan del proyecto —el caché y los cartuchos de prueba, adentro de su
`build`—: un default de la máquina sería el de una máquina.

Es un solo lugar que se configura, y no un parámetro en cada función, a
propósito: `recursos.GAME_DIR`, `recursos.RTP_DIR` y `snes_samples.SOUNDFONT`
se leen adentro de unas cuarenta funciones del conversor y de la música, y
pasarlos por parámetro tocaba todas esas firmas. Esos nombres siguen
existiendo, pero se resuelven acá al leerlos —ver el `__getattr__` de cada
módulo—, así que fallan claro si se los lee sin fijar.
"""

import os

from comun import proyecto


class FaltaElAmbiente(SystemExit):
    """Un valor de la máquina que nadie pasó. Es un `SystemExit` por lo mismo
    que `proyecto.NoHayProyecto`: lo arregla cómo se corrió, no el código."""


# Lo que se puede fijar: el nombre, que es también el `dest` del flag, y
# el flag con su ayuda.
FLAGS = {
    "game_dir": ("--game-dir", "el proyecto RM2k original, del que salen los "
                               "PNG, los MIDI y los .lmu"),
    "rtp_dir": ("--rtp-dir", "el RTP con que se armó el juego: lo que el "
                             "juego no trae, se busca ahí"),
    "soundfont": ("--soundfont", "el banco del que salen las muestras del "
                                 "SPC700 y las pistas de MSU-1"),
    "reemplazos": ("--reemplazos", "dónde buscar un <tema>.mp3 —u .ogg, "
                                   ".flac, .wav— que reemplace al MIDI de "
                                   "ese tema en las pistas de MSU-1"),
    "cache": ("--cache", "el caché en disco del conversor. Sin esto, "
                         "cache/ adentro del build del proyecto"),
    "test_cartridges": ("--test-cartridges", "dónde se arman los cartuchos "
                                             "de prueba. Sin esto, tests/ "
                                             "adentro del build del proyecto"),
    "compartido": ("--compartido", "la carpeta donde se entrega lo que se "
                                   "arma"),
}

_fijados = {}


def fijar(**valores):
    """Fija los valores que no son None. Un nombre que no está en `FLAGS`
    es un error de programación, no del que corre."""
    for nombre, valor in valores.items():
        if nombre not in FLAGS:
            raise KeyError(nombre)
        if valor is not None:
            # Absolutas: el conversor corre parado en otro directorio que
            # el que lo llamó.
            _fijados[nombre] = os.path.abspath(valor)


def argumentos(parser, *nombres):
    """Suma los flags de `nombres` al parser de un ejecutable."""
    for nombre in nombres:
        flag, ayuda = FLAGS[nombre]
        parser.add_argument(flag, dest=nombre, metavar="RUTA", help=ayuda)


def desde_argumentos(args, *nombres):
    """Fija lo que vino en la línea de comandos."""
    fijar(**{nombre: getattr(args, nombre) for nombre in nombres})


def como_flags(*nombres):
    """Los valores fijados de `nombres`, como flags: para pasárselos a otra
    herramienta que se corre en un proceso aparte."""
    flags = []
    for nombre in nombres:
        if nombre in _fijados:
            flags += [FLAGS[nombre][0], _fijados[nombre]]
    return flags


def _pedir(nombre):
    if nombre not in _fijados:
        raise FaltaElAmbiente(
            "falta %s: %s. Es de la máquina, así que no tiene valor por "
            "omisión; lo pasa el que corre esto" % (FLAGS[nombre][0],
                                                   FLAGS[nombre][1]))
    return _fijados[nombre]


def juego():
    """El proyecto RM2k original: ver `rpgmaker/recursos.py`."""
    return _pedir("game_dir")


def rtp():
    """El RTP de Don Miguel: ver `rpgmaker/recursos.py`."""
    return _pedir("rtp_dir")


def soundfont():
    """El banco del que salen las muestras: ver `audio/snes_samples.py`."""
    return _pedir("soundfont")


def reemplazos_msu():
    """Dónde se buscan los reemplazos de las pistas de MSU-1, o None: sin
    reemplazos, cada pista sale de su MIDI."""
    return _fijados.get("reemplazos")


def cache():
    """El caché en disco del conversor: ver `comun/cache_disco.py`."""
    return _fijados.get("cache") or os.path.join(proyecto.build(), "cache")


def cartuchos_de_prueba():
    """Dónde se arman los cartuchos de la tanda, menos `release`: ver
    `cartuchos.directorio`."""
    return (_fijados.get("test_cartridges")
            or os.path.join(proyecto.build(), "tests"))


def compartido():
    """Donde se entrega lo que se arma: ver `ensamblado/entregar.py`."""
    return _pedir("compartido")

"""Dónde están el juego y el RTP, y cómo se encuentra un recurso adentro.

No es de dibujo: es la configuración del juego y la búsqueda de recursos de
RM2k, que usan por igual el render, el audio y el conversor.
"""

import os

from comun import ambiente

# `GAME_DIR` es el proyecto RM2k original, y `RTP_DIR` el RTP con que se armó.
# Los fija el ejecutable desde `--game-dir` y `--rtp-dir` —ver
# `comun/ambiente.py`— y se leen al usarlos: leerlos sin fijar falla diciendo
# qué flag falta.
#
# Para ABL, el RTP es el de Don Miguel (junio de 2000), extraído de RTPE.EXE.
# No es el RTP "oficial": el RPG Maker 2000 que se usaba fuera de Japón era su
# traducción, y de paso le agregó archivos propios (Future1-3, entre otros)
# que ABL usa. El RTP libre de EasyRPG no sirve acá: es un reemplazo con arte
# distinto. Ni el juego ni el RTP viven en el repo: no son nuestros para
# redistribuir. Antes el RTP era `RTP/` adentro del repo, excluido por
# .gitignore, que es la peor combinación —ocupaba lugar, no se versionaba, y
# parecía del proyecto—.
_DEL_AMBIENTE = {"GAME_DIR": ambiente.juego, "RTP_DIR": ambiente.rtp}


def __getattr__(nombre):
    if nombre in _DEL_AMBIENTE:
        return _DEL_AMBIENTE[nombre]()
    raise AttributeError("module %r has no attribute %r" % (__name__, nombre))


def find_resource(dirs, folder, name, extensions=(".png", ".bmp")):
    """Busca <dir>/<folder>/<name>.<ext> sin distinguir mayúsculas.

    RM2k guarda los nombres sin extensión y el juego original corría en
    Windows, así que los .lmu no dicen nada del case real del archivo.
    """
    for directory in dirs:
        for entry in os.listdir(directory) if os.path.isdir(directory) else []:
            if entry.lower() != folder.lower():
                continue
            subdir = os.path.join(directory, entry)
            for filename in os.listdir(subdir):
                base, ext = os.path.splitext(filename)
                if base.lower() == name.lower() and ext.lower() in extensions:
                    return os.path.join(subdir, filename)
    return None

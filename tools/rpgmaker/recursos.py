"""Dónde están el juego y el RTP, y cómo se encuentra un recurso adentro.

No es de dibujo: es la configuración del juego y la búsqueda de recursos de
RM2k, que usan por igual el render, el audio y el conversor.
"""

import os

# El proyecto RM2k original. Es una copia dentro del contenedor, no un montaje
# del host: así el directorio original ni siquiera es alcanzable desde acá, que
# protege más que un montaje de sólo lectura. Todas las herramientas aceptan
# --game-dir para apuntar a otro lado.
GAME_DIR = os.environ.get("ABL_GAME_DIR", "/extras/abl-rm")
# El RTP de Don Miguel (junio de 2000), extraído de RTPE.EXE. No es el RTP
# "oficial": el RPG Maker 2000 que se usaba fuera de Japón era su traducción, y
# de paso le agregó archivos propios (Future1-3, entre otros) que ABL usa. El
# RTP libre de EasyRPG no sirve acá: es un reemplazo con arte distinto.
# El RTP de Don Miguel vive en /extras, del mismo lado que el juego original y
# por la misma razón: no es nuestro para redistribuir y no tiene por qué estar
# en el árbol. Antes era `RTP/` adentro del repo, excluido por .gitignore, que
# es la peor combinación —ocupaba lugar, no se versionaba, y parecía del
# proyecto—. Con ABL_RTP_DIR se apunta a otra copia.
RTP_DIR = os.environ.get("ABL_RTP_DIR", "/extras/rtp")


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

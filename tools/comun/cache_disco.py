"""Un caché en disco para lo que el conversor calcula igual en cada build.

Convertir `demo-ciudad` tardaba 77 s, y casi nada de eso depende de algo que
cambie entre un build y el siguiente: las muestras del soundfont son las mismas
y los mapas también. Lo que sí cambia —el código— entra en la clave: cada
categoría lleva el hash de los fuentes de los que sale, así que tocar el
codificador o el conversor invalida lo suyo solo, sin que nadie tenga que
acordarse de borrar nada.

Vive en `rom/build/cache/`, que git ignora y que existe de los dos lados —el
host y el contenedor—, porque las recetas se corren desde los dos. Se puede
mover con `ABL_CACHE` y apagar con `SIN_CACHE=1`, que es lo que se usa para
comprobar que con caché y sin caché sale **el mismo `.sfc` byte por byte**: la
única verificación honesta de un caché es ésa.

Un valor que no se pueda serializar no se guarda y no rompe nada: el caché es
un atajo, no una dependencia.
"""

import hashlib
import os
import pickle
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DONDE = os.environ.get("ABL_CACHE", os.path.join(RAIZ, "rom", "build", "cache"))
APAGADO = os.environ.get("SIN_CACHE") == "1"


def version_de(*archivos):
    """El hash de los fuentes de los que sale un valor, para meterlo en la
    clave: rutas relativas a `tools/`."""
    h = hashlib.sha256()
    for nombre in archivos:
        with open(os.path.join(RAIZ, "tools", nombre), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def clave(*partes):
    """Una clave a partir de sus partes, cada una bytes o texto, con el largo
    delante para que dos particiones distintas no den lo mismo."""
    h = hashlib.sha256()
    for parte in partes:
        if isinstance(parte, str):
            parte = parte.encode("utf-8")
        h.update(len(parte).to_bytes(8, "little"))
        h.update(parte)
    return h.hexdigest()


def leer(categoria, clave):
    """Lo guardado bajo esa clave, o None."""
    if APAGADO:
        return None
    ruta = os.path.join(DONDE, categoria, clave)
    try:
        with open(ruta, "rb") as f:
            return pickle.load(f)
    except (OSError, EOFError, pickle.UnpicklingError, ValueError):
        return None


def guardar(categoria, clave, valor):
    """Guarda el valor, entero o nada: se escribe aparte y se renombra, así una
    corrida cortada a la mitad no deja un archivo a medias que otra lea."""
    if APAGADO:
        return
    carpeta = os.path.join(DONDE, categoria)
    try:
        os.makedirs(carpeta, exist_ok=True)
        fd, temporal = tempfile.mkstemp(dir=carpeta, prefix=".tmp-")
        with os.fdopen(fd, "wb") as f:
            pickle.dump(valor, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporal, os.path.join(carpeta, clave))
    except (OSError, pickle.PicklingError, TypeError):
        pass

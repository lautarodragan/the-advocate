"""Un caché en disco para lo que el conversor calcula igual en cada build.

Casi nada de lo que cuesta una conversión depende de algo que cambie entre un
build y el siguiente: las muestras del soundfont son las mismas y los mapas
también. Lo que sí cambia —el código— entra en la clave: cada categoría lleva
el hash de los fuentes de los que sale, así que tocar el codificador o el
conversor invalida lo suyo solo, sin que nadie tenga que acordarse de borrar
nada.

Hoy son cuatro categorías: `capas` —los mapas convertidos a tiles—, `brr` —lo
que devuelve el codificador—, `muestras` —la voz ya preparada, que es el
remuestreo y la normalización que van antes de codificar— y `msu` —las pistas
de MSU-1—. Las dos del SPC700 son categorías separadas a propósito: una sola,
más arriba, ahorraría claves pero se caería entera cada vez que se toque
cualquiera de los dos lados.

`msu` es la rara y conviene saber por qué: **no guarda el valor sino su
sha256**, porque el valor es un archivo de decenas de megas que ya está
escrito al lado de la ROM, que es donde el MSU-1 lo va a buscar. Lo que el
caché contesta ahí no es "tomá esto" sino "lo que hay es lo que yo haría".

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

from comun import proyecto

APAGADO = os.environ.get("SIN_CACHE") == "1"


def donde():
    """El directorio del caché. Se pide al usarlo y no al importar: sale del
    proyecto, que se encuentra al usarlo."""
    return proyecto.cache()


def version_de(*archivos):
    """El hash de los fuentes de los que sale un valor, para meterlo en la
    clave: rutas relativas a `tools/`."""
    h = hashlib.sha256()
    for nombre in archivos:
        with open(os.path.join(proyecto.herramientas(), nombre), "rb") as f:
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
    ruta = os.path.join(donde(), categoria, clave)
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
    carpeta = os.path.join(donde(), categoria)
    try:
        os.makedirs(carpeta, exist_ok=True)
        fd, temporal = tempfile.mkstemp(dir=carpeta, prefix=".tmp-")
        with os.fdopen(fd, "wb") as f:
            pickle.dump(valor, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporal, os.path.join(carpeta, clave))
    except (OSError, pickle.PicklingError, TypeError):
        pass

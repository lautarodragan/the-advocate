"""A disk cache for what the converter computes the same way on every build.

Almost nothing of what a conversion costs depends on something that changes
between one build and the next: the soundfont's samples are the same and so
are the maps. What does change —the code— goes into the key: each category
carries the hash of the sources it comes from, so touching the encoder or the
converter invalidates only its own part, without anyone having to remember to
delete anything.

Today there are four categories: `capas` —the maps converted to tiles—, `brr`
—what the encoder returns—, `muestras` —the voice already prepared, which is
the resampling and normalization that come before encoding— and `msu` —the
MSU-1 tracks—. The two SPC700 ones are separate categories on purpose: a
single one, further up, would save keys but would be dropped entirely every
time either side is touched.

`msu` is the odd one and it is worth knowing why: **it does not store the
value but its sha256**, because the value is a file of tens of megabytes that
is already written next to the ROM, which is where the MSU-1 will look for
it. What the cache answers there is not "take this" but "what is there is
what I would make".

It lives in `rom/build/cache/`, which git ignores and which exists on both
sides —the host and the container—, because the recipes are run from both.
It can be moved with `--cache` and turned off with `SIN_CACHE=1`, which is
what is used to check that with and without the cache **the same `.sfc` comes
out byte for byte**: that is the only honest verification of a cache.

A value that cannot be serialized is not stored and breaks nothing: the
cache is a shortcut, not a dependency.
"""

import hashlib
import os
import pickle
import tempfile

from common import ambiente
from common import project

APAGADO = os.environ.get("SIN_CACHE") == "1"


def donde():
    """The cache directory. It is asked for when used and not at import: it
    comes from the project, which is found when used, or from `--cache`."""
    return ambiente.cache()


def version_de(*archivos):
    """The hash of the sources a value comes from, to put it into the key:
    paths relative to `tools/`."""
    h = hashlib.sha256()
    for nombre in archivos:
        with open(os.path.join(project.tools(), nombre), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def clave(*partes):
    """A key from its parts, each bytes or text, with the length in front so
    that two different partitions do not give the same thing."""
    h = hashlib.sha256()
    for parte in partes:
        if isinstance(parte, str):
            parte = parte.encode("utf-8")
        h.update(len(parte).to_bytes(8, "little"))
        h.update(parte)
    return h.hexdigest()


def leer(categoria, clave):
    """What is stored under that key, or None."""
    if APAGADO:
        return None
    ruta = os.path.join(donde(), categoria, clave)
    try:
        with open(ruta, "rb") as f:
            return pickle.load(f)
    except (OSError, EOFError, pickle.UnpicklingError, ValueError):
        return None


def guardar(categoria, clave, valor):
    """Stores the value, whole or not at all: it is written aside and renamed,
    so a run cut halfway does not leave a half-written file for another to
    read."""
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

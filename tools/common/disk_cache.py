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
It can be moved with `--cache` and turned off with `NO_CACHE=1`, which is
what is used to check that with and without the cache **the same `.sfc` comes
out byte for byte**: that is the only honest verification of a cache.

A value that cannot be serialized is not stored and breaks nothing: the
cache is a shortcut, not a dependency.
"""

import hashlib
import os
import pickle
import tempfile

from common import environment
from common import project

DISABLED = os.environ.get("NO_CACHE") == "1"


def directory():
    """The cache directory. It is asked for when used and not at import: it
    comes from the project, which is found when used, or from `--cache`."""
    return environment.cache()


def version_of(*files):
    """The hash of the sources a value comes from, to put it into the key:
    paths relative to `tools/`."""
    h = hashlib.sha256()
    for name in files:
        with open(os.path.join(project.tools(), name), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def key(*parts):
    """A key from its parts, each bytes or text, with the length in front so
    that two different partitions do not give the same thing."""
    h = hashlib.sha256()
    for part in parts:
        if isinstance(part, str):
            part = part.encode("utf-8")
        h.update(len(part).to_bytes(8, "little"))
        h.update(part)
    return h.hexdigest()


def read(category, key):
    """What is stored under that key, or None."""
    if DISABLED:
        return None
    path = os.path.join(directory(), category, key)
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except (OSError, EOFError, pickle.UnpicklingError, ValueError):
        return None


def write(category, key, value):
    """Stores the value, whole or not at all: it is written aside and renamed,
    so a run cut halfway does not leave a half-written file for another to
    read."""
    if DISABLED:
        return
    folder = os.path.join(directory(), category)
    try:
        os.makedirs(folder, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
        with os.fdopen(fd, "wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temp, os.path.join(folder, key))
    except (OSError, pickle.PicklingError, TypeError):
        pass

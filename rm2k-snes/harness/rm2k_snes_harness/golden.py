"""The goldens: a capture against its frozen one, at 15 bits."""

import os

from PIL import Image

from . import retro
from .cores import core_name
from .game import current


def _save(image, *parts):
    snapshots = current().snapshots
    os.makedirs(os.path.join(snapshots, *parts[:-1]), exist_ok=True)
    path = os.path.join(snapshots, *parts)
    image.save(path)
    return path


def golden(name, image, core):
    """The capture against its frozen one, identical **at 15 bits**, the
    console's depth: the golden is snes9x's, and bsnes's is compared against
    it too. A capture with no golden is left in `snapshots/golden/` and is a
    red: it is looked at and, if it is right, copied to the goldens in its
    own commit. A golden is never overwritten from here."""
    path = os.path.join(current().goldens, "%s.png" % name)
    if not os.path.exists(path):
        # snes9x's under the golden's name, since it is the one taken; the
        # other core's beside it, so it does not overwrite it.
        suffix = "" if core_name(core) == "snes9x" else "-" + core_name(core)
        where = _save(image, "golden", "%s%s.png" % (name, suffix))
        raise AssertionError("%r has no golden: the capture was left in %s"
                             % (name, where))
    expected = retro.fifteen_bits(Image.open(path))
    actual = retro.fifteen_bits(image)
    if expected == actual:
        return
    distinct = sum(1 for a, b in zip(expected, actual) if a != b)
    where = _save(image, "golden", "%s-%s.png" % (name, core_name(core)))
    raise AssertionError(
        "%r on %s differs from its golden in %d of %d pixels, at 15 bits. The "
        "capture was left in %s and the golden is %s."
        % (name, core_name(core), distinct, len(expected), where, path))

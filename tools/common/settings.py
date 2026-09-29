"""The project file: what a game decides and the tools do not.

Until 2026-09-29 A Blurred Line's choices —which maps go into the cartridge,
what the ROM is called, which sound effects go whole— were written in the
`.py` files of `tools/`, and each tool had them as a default. Now they live
in a TOML at the game's root —`project.project_file()`—, and the
tools read them from here. See
`workflow/decisiones/las-herramientas-se-separan-de-abl.md` and steps 3 and 4
of `docs/research/el-mapa-de-las-herramientas-de-python.md`.

**A missing key is an error, not a default.** If a tool had a default value
for a setting, that value would be ABL's, and a game that forgot to declare
it would be built with another game's without a warning.

The keys are in English, because they are the tools' interface; the file's
comments, in the game's language.
"""

import tomllib

from common import project

_loaded = {}


class MissingKey(KeyError):
    """A setting the file does not declare, or declares with another type."""

    def __str__(self):
        return self.args[0]


def load(path=None):
    """The whole file, as a dictionary. It is read once per path: the tools
    consult it when imported and on every map."""
    path = path or project.project_file()
    if path not in _loaded:
        with open(path, "rb") as handle:
            _loaded[path] = tomllib.load(handle)
    return _loaded[path]


def value(*keys, kind=None, path=None):
    """The setting at `keys` —`value("rom", "name")` is `[rom] name`—.
    It fails with the key's name if it is missing, or if `kind` is not its
    type: `bool` does not pass for `int`, even though Python says it does."""
    path = path or project.project_file()
    current = load(path)
    for k, key in enumerate(keys):
        if not isinstance(current, dict) or key not in current:
            raise MissingKey("%s: missing key %s" % (
                path, ".".join(str(c) for c in keys[:k + 1])))
        current = current[key]
    if kind is not None and (not isinstance(current, kind)
                             or (isinstance(current, bool)
                                 and not _accepts_bool(kind))):
        raise MissingKey("%s: %s must be %s and is %r" % (
            path, ".".join(keys), _kind_name(kind), current))
    return current


def _accepts_bool(kind):
    kinds = kind if isinstance(kind, tuple) else (kind,)
    return bool in kinds


def _kind_name(kind):
    kinds = kind if isinstance(kind, tuple) else (kind,)
    return " or ".join(t.__name__ for t in kinds)


def ascii(*keys, length=None, max_length=None, path=None):
    """A text setting that ends up in the ROM as is: printable ASCII,
    without quotes —it goes between quotes in the `.inc`—, and exactly
    `length` characters long or at most `max_length`."""
    text = value(*keys, kind=str, path=path)
    name = ".".join(keys)
    path = path or project.project_file()
    if not all(" " <= c <= "~" and c != '"' for c in text):
        raise MissingKey("%s: %s must be printable ASCII without "
                         "quotes, and is %r" % (path, name, text))
    if length is not None and len(text) != length:
        raise MissingKey("%s: %s must have %d characters, and has %d"
                         % (path, name, length, len(text)))
    if max_length is not None and not 0 < len(text) <= max_length:
        raise MissingKey("%s: %s must have 1 to %d characters, and "
                         "has %d" % (path, name, max_length, len(text)))
    return text

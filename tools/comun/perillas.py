"""The project file: what a game decides and the tools do not.

Until 2026-09-29 A Blurred Line's choices —which maps go into the cartridge,
what the ROM is called, which sound effects go whole— were written in the
`.py` files of `tools/`, and each tool had them as a default. Now they live
in a TOML at the game's root —`proyecto.archivo_de_proyecto()`—, and the
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

from comun import proyecto

_leidos = {}


class FaltaUnaClave(KeyError):
    """A setting the file does not declare, or declares with another type."""

    def __str__(self):
        return self.args[0]


def leer(ruta=None):
    """The whole file, as a dictionary. It is read once per path: the tools
    consult it when imported and on every map."""
    ruta = ruta or proyecto.archivo_de_proyecto()
    if ruta not in _leidos:
        with open(ruta, "rb") as archivo:
            _leidos[ruta] = tomllib.load(archivo)
    return _leidos[ruta]


def valor(*claves, tipo=None, ruta=None):
    """The setting at `claves` —`valor("rom", "name")` is `[rom] name`—.
    It fails with the key's name if it is missing, or if `tipo` is not its
    type: `bool` does not pass for `int`, even though Python says it does."""
    ruta = ruta or proyecto.archivo_de_proyecto()
    actual = leer(ruta)
    for k, clave in enumerate(claves):
        if not isinstance(actual, dict) or clave not in actual:
            raise FaltaUnaClave("%s: missing key %s" % (
                ruta, ".".join(str(c) for c in claves[:k + 1])))
        actual = actual[clave]
    if tipo is not None and (not isinstance(actual, tipo)
                             or (isinstance(actual, bool)
                                 and not _admite_bool(tipo))):
        raise FaltaUnaClave("%s: %s must be %s and is %r" % (
            ruta, ".".join(claves), _nombre(tipo), actual))
    return actual


def _admite_bool(tipo):
    tipos = tipo if isinstance(tipo, tuple) else (tipo,)
    return bool in tipos


def _nombre(tipo):
    tipos = tipo if isinstance(tipo, tuple) else (tipo,)
    return " or ".join(t.__name__ for t in tipos)


def ascii(*claves, largo=None, hasta=None, ruta=None):
    """A text setting that ends up in the ROM as is: printable ASCII,
    without quotes —it goes between quotes in the `.inc`—, and exactly
    `largo` characters long or at most `hasta`."""
    texto = valor(*claves, tipo=str, ruta=ruta)
    nombre = ".".join(claves)
    ruta = ruta or proyecto.archivo_de_proyecto()
    if not all(" " <= c <= "~" and c != '"' for c in texto):
        raise FaltaUnaClave("%s: %s must be printable ASCII without "
                            "quotes, and is %r" % (ruta, nombre, texto))
    if largo is not None and len(texto) != largo:
        raise FaltaUnaClave("%s: %s must have %d characters, and has %d"
                            % (ruta, nombre, largo, len(texto)))
    if hasta is not None and not 0 < len(texto) <= hasta:
        raise FaltaUnaClave("%s: %s must have 1 to %d characters, and "
                            "has %d" % (ruta, nombre, hasta, len(texto)))
    return texto

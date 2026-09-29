"""El archivo de proyecto: lo que un juego decide y las herramientas no.

Hasta el 2026-09-29 lo de A Blurred Line —qué mapas entran en el cartucho,
cómo se llama la ROM, qué efectos de sonido van enteros— estaba escrito en los
`.py` de `tools/`, y cada herramienta lo tenía de default. Ahora vive en un
TOML en la raíz del juego —`proyecto.archivo_de_proyecto()`—, y las
herramientas lo leen de acá. Ver
`workflow/decisiones/las-herramientas-se-separan-de-abl.md` y los pasos 3 y 4
de `docs/research/el-mapa-de-las-herramientas-de-python.md`.

**Una clave que falta es un error, no un default.** Si una herramienta tuviera
un valor por omisión para una perilla, ese valor sería el de ABL, y un juego
que se olvidara de declararla se armaría con lo de otro sin avisar.

Las claves van en inglés, porque son la interfaz de las herramientas; los
comentarios del archivo, en el idioma del juego.
"""

import tomllib

from comun import proyecto

_leidos = {}


class FaltaUnaClave(KeyError):
    """Una perilla que el archivo no declara, o que declara con otro tipo."""

    def __str__(self):
        return self.args[0]


def leer(ruta=None):
    """El archivo entero, como diccionario. Se lee una vez por ruta: las
    herramientas lo consultan al importarse y en cada mapa."""
    ruta = ruta or proyecto.archivo_de_proyecto()
    if ruta not in _leidos:
        with open(ruta, "rb") as archivo:
            _leidos[ruta] = tomllib.load(archivo)
    return _leidos[ruta]


def valor(*claves, tipo=None, ruta=None):
    """La perilla en `claves` —`valor("rom", "name")` es `[rom] name`—.
    Falla con el nombre de la clave si no está, o si `tipo` no es el suyo:
    `bool` no pasa por `int`, aunque Python diga que sí."""
    ruta = ruta or proyecto.archivo_de_proyecto()
    actual = leer(ruta)
    for k, clave in enumerate(claves):
        if not isinstance(actual, dict) or clave not in actual:
            raise FaltaUnaClave("%s: falta la clave %s" % (
                ruta, ".".join(str(c) for c in claves[:k + 1])))
        actual = actual[clave]
    if tipo is not None and (not isinstance(actual, tipo)
                             or (isinstance(actual, bool)
                                 and not _admite_bool(tipo))):
        raise FaltaUnaClave("%s: %s tiene que ser %s y es %r" % (
            ruta, ".".join(claves), _nombre(tipo), actual))
    return actual


def _admite_bool(tipo):
    tipos = tipo if isinstance(tipo, tuple) else (tipo,)
    return bool in tipos


def _nombre(tipo):
    tipos = tipo if isinstance(tipo, tuple) else (tipo,)
    return " o ".join(t.__name__ for t in tipos)


def ascii(*claves, largo=None, hasta=None, ruta=None):
    """Una perilla de texto que termina en la ROM tal cual: ASCII imprimible,
    sin comillas —va entre comillas en el `.inc`—, y de `largo` caracteres
    exactos o de `hasta` como mucho."""
    texto = valor(*claves, tipo=str, ruta=ruta)
    nombre = ".".join(claves)
    ruta = ruta or proyecto.archivo_de_proyecto()
    if not all(" " <= c <= "~" and c != '"' for c in texto):
        raise FaltaUnaClave("%s: %s tiene que ser ASCII imprimible y sin "
                            "comillas, y es %r" % (ruta, nombre, texto))
    if largo is not None and len(texto) != largo:
        raise FaltaUnaClave("%s: %s tiene que tener %d caracteres, y tiene %d"
                            % (ruta, nombre, largo, len(texto)))
    if hasta is not None and not 0 < len(texto) <= hasta:
        raise FaltaUnaClave("%s: %s tiene que tener de 1 a %d caracteres, y "
                            "tiene %d" % (ruta, nombre, hasta, len(texto)))
    return texto

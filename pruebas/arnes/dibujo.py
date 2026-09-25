"""Las pantallas que se comparan contra un dibujo de Python y no contra una
golden: el menú, la tienda, los ítems, el equipo, las ranuras.

El dibujo lo hace `tools/port/` —`titulo.render_menu`, `pantallas.pantalla_tienda`
y compañía— con la base de datos y el System de `arnes/datos.py`, y se compara
a 15 bits, que es lo que la consola puede mostrar.
"""

import os

from consola import RAIZ
from tanda import quince_bits

# Cuando difieren, la captura y la esperada quedan acá para mirarlas, como las
# de la tanda en snapshots/tanda.
PANTALLAS = os.path.join(RAIZ, "pruebas", "snapshots", "pantallas")


def pantalla_distinta(nombre, captura, esperada, distintos):
    """Si difieren, deja la captura y la esperada en PANTALLAS; si no, borra
    las que haya dejado una corrida anterior, así el directorio tiene sólo lo
    que está en rojo ahora. Devuelve el patrón de los dos archivos, para el
    mensaje de la prueba."""
    base = os.path.join(PANTALLAS, nombre)
    rutas = (base + ".png", base + ".esperado.png")
    if distintos:
        os.makedirs(PANTALLAS, exist_ok=True)
        captura.save(rutas[0])
        esperada.save(rutas[1])
    else:
        for ruta in rutas:
            if os.path.exists(ruta):
                os.remove(ruta)
    return os.path.relpath(base, RAIZ) + "*.png"


def pixeles_distintos(una, otra):
    """Cuántos pixeles difieren entre dos imágenes, a 15 bits."""
    return sum(1 for x, y in zip(quince_bits(una), quince_bits(otra))
               if x != y)


def diferencia(una, esperada, nombre=None):
    """Cuántos pixeles de la pantalla de la partida `una` no son los de
    `esperada`. Con `nombre`, las dos quedan en `PANTALLAS` si difieren."""
    captura = una.imagen().convert("RGB")
    distintos = pixeles_distintos(captura, esperada)
    if nombre is not None:
        pantalla_distinta(nombre, captura, esperada, distintos)
    return distintos


def comparar_pantalla(una, esperada, nombre=None, que=None):
    """La pantalla de la partida `una` tiene que ser `esperada`, pixel por
    pixel. `que` dice qué se está mirando, para el mensaje; `nombre`, con qué
    nombre quedan las dos en `PANTALLAS` cuando difieren."""
    captura = una.imagen().convert("RGB")
    distintos = pixeles_distintos(captura, esperada)
    donde = ""
    if nombre is not None:
        donde = "; están en %s" % pantalla_distinta(nombre, captura, esperada,
                                                    distintos)
    assert distintos == 0, "%s difiere de la referencia en %d pixeles%s" % (
        que or nombre or "la pantalla", distintos, donde)

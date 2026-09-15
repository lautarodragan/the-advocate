"""Dónde está el ensamblador, y compilarlo si hace falta.

Existe porque desde el 2026-09-15 el ensamblador de 65816 es un binario de Rust
—`w65/`— y hay dos clases de llamador con arranques distintos:

* el justfile, que lo resuelve con la receta `w65-binario`, de la que dependen
  las nueve recetas que ensamblan;
* **pytest**, que no tiene recetas. `pruebas/consola.py` arma sus propias ROMs,
  y `python3 -m pytest pruebas` tiene que seguir andando sin pasar por `just`.

Para el segundo está esto: se compila **a pedido y una sola vez por proceso**,
la primera vez que alguien pide el binario. Cargo al día cuesta 0,025 s medidos
—contra 14,7 s en frío—, así que pagarlo al arrancar la tanda no se nota, y a
cambio nunca se usa en silencio un binario viejo, que es la única forma en que
esto fallaría sin verse.

Lo que **no** hace es buscar un `w65` en el `PATH`: el que vale es el que sale
de este árbol, porque la ROM tiene que poder rearmarse desde el repo y nada
más.
"""

import os
import shutil
import subprocess

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W65 = os.path.join(RAIZ, "w65")
BINARIO = os.path.join(W65, "target", "release", "w65")

# El mismo texto que da la receta `w65-binario`, porque el que corre pytest
# directo se choca con esto y no con ella.
FALTA_CARGO = (
    "falta cargo: desde el 2026-09-15 el ensamblador de 65816 es un binario\n"
    "de Rust (w65/) y hay que compilarlo para armar la ROM.\n"
    "  en Arch:   pacman -S rust   (o rustup, y 'rustup default stable')\n"
    "  y después: just w65-binario")

_compilado = False


class FaltaCargo(RuntimeError):
    """No hay con qué compilar el ensamblador."""


def binario():
    """La ruta al ensamblador, ya compilado y al día.

    Compila una sola vez por proceso: dos llamadas seguidas no vuelven a
    llamar a cargo, que igual contestaría "está al día" pero cuesta arrancarlo.
    """
    global _compilado
    if _compilado:
        return BINARIO

    if shutil.which("cargo") is None:
        # Si ya hay un binario compilado de antes, sirve: sin cargo no se puede
        # comprobar que esté al día, pero un ensamblador viejo es mejor que no
        # poder correr las pruebas, y quien no tiene cargo tampoco tiene cómo
        # haber cambiado los fuentes de Rust.
        if os.path.exists(BINARIO):
            _compilado = True
            return BINARIO
        raise FaltaCargo(FALTA_CARGO)

    subprocess.run(["cargo", "build", "--release", "--quiet"],
                   check=True, cwd=W65)
    _compilado = True
    return BINARIO

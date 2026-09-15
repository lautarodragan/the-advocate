"""Dónde está el ensamblador.

El de 65816 es un binario de Rust —`w65/`— y el port lo consume **desde el
PATH**, como consume `python3` o un core de libretro: ningún script ni prueba
de este juego llama a `cargo`. Se instala una vez, con `just herramientas`, y a
partir de ahí es una herramienta del sistema.

Lo que esto resuelve es sólo encontrarlo y decir qué falta cuando no está. La
alternativa —compilarlo a pedido— ataba cada corrida de las pruebas al
toolchain de Rust, que es exactamente lo que se quería sacar.
"""

import shutil

FALTA = """falta `w65`, el ensamblador de 65816.

Es un binario de Rust que vive en `w65/` y se instala como herramienta del
sistema, no se compila en cada corrida:

    just herramientas

Eso hace `cargo install --locked --path w65`. Si falta cargo, en Arch es
`pacman -S rust`."""


class FaltaW65(RuntimeError):
    """No está el ensamblador, con qué hacer para tenerlo."""


def binario():
    """La ruta del `w65` del PATH. Levanta `FaltaW65` si no hay."""
    ruta = shutil.which("w65")
    if ruta is None:
        raise FaltaW65(FALTA)
    return ruta

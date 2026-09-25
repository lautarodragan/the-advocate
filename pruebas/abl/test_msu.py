"""Que las pistas de MSU-1 al lado de `release/abl.sfc` no lleguen a la tanda.

`release` lleva siempre sus pistas —`just build release` las deja al lado de
la ROM— y el emulador busca el `.msu` al lado del `.sfc`: si el core lo
encontrara, cada prueba que escucha correría con el SPC700 callado. Hasta el
2026-09-25 lo evitaba tenerlas en otro directorio; ahora lo evita el arnés,
que le da al core una copia de la ROM en un directorio vacío —ver
`retro.Consola`—, y esto es lo que lo cobra si deja de hacerlo.

Se escucha la pantalla de título, que es lo primero que suena y tiene pista.
La referencia es la misma ROM copiada a un directorio sin pistas, y el control
es pedirle el MSU-1 a la de `release/`: si con él el audio no cambiara, que
sin él sea igual a la referencia no probaría nada.
"""

import os
import shutil

from emulador import retro

import tanda
from consola import NUCLEO
from ensamblado import cartuchos

# Del encendido: a esta altura el tema del título ya suena, y con el MSU-1 lo
# toca la pista. Medido en snes9x y en bsnes.
CUADROS = 600


def _con_msu(sfc):
    consola = retro.Consola(sfc, NUCLEO, msu=True)
    consola.correr(CUADROS)
    return bytes(consola.audio)


def test_las_pistas_de_release_no_llegan_al_core(tmp_path):
    sfc = tanda.cartucho(cartuchos.RELEASE).sfc
    base = os.path.splitext(sfc)[0]
    assert os.path.exists(base + ".msu") and os.path.exists(base + "-1.pcm"), (
        "a %s le faltan sus pistas de MSU-1, así que esta prueba no compara "
        "nada: las deja `just build release`" % os.path.dirname(sfc))

    sola = os.path.join(tmp_path, os.path.basename(sfc))
    shutil.copyfile(sfc, sola)
    spc700 = _con_msu(sola)

    assert _con_msu(sfc) != spc700, (
        "con el MSU-1 pedido y las pistas al lado, el título suena igual que "
        "sin ellas: o el core dejó de buscarlas, o el tema dejó de tener "
        "pista, y la comparación de abajo no prueba nada")
    # Por donde entran las pruebas, sin pedir nada: es lo que se protege.
    assert bytes(tanda.encender(cartuchos.RELEASE, CUADROS).audio) == spc700, (
        "la consola de las pruebas encontró las pistas de MSU-1 de %s: la "
        "tanda está escuchando las pistas y no el SPC700. `retro.Consola` "
        "tiene que darle al core un directorio sin ellas"
        % os.path.dirname(sfc))

"""`just espacio`, contra la medición a mano que reemplazó.

La receta lee lo que dejó el armado en vez de relinkear, así que puede
equivocarse callada: leer el segmento que no es, o contar el relleno del
`.align` como código. Esto la compara con el método de antes —un `.res N`
linkeado contra el `.o` de la ROM, y `ld65` diciendo por cuánto se pasa—
sobre `release`, que es el que se juega.
"""

import os
import re
import subprocess

import pytest

from assembly import cartridges
from assembly import space


def _libre_con_res(sfc, segmento, tmp_path, n):
    """Lo libre en `segmento` según `ld65`: `n` menos por cuánto se pasa."""
    fuente = tmp_path / "relleno.s"
    # En un segmento `ro` el `.res` sin valor no ocupa nada, y la medición
    # daría "no se pasa" siempre.
    fuente.write_text('.segment "%s"%s\n.res %d%s\n' % (
        segmento, ": zeropage" if segmento == "ZEROPAGE" else "", n,
        ", $00" if segmento == "TABLAS" else ""))
    objeto = tmp_path / "relleno.o"
    subprocess.run(["ca65", "--cpu", "65816", str(fuente), "-o", str(objeto)],
                   check=True)
    hecho = subprocess.run(
        ["ld65", "-C", os.path.join(os.path.dirname(sfc), "memoria.cfg"),
         sfc + ".o", str(objeto), "-o", str(tmp_path / "x.sfc")],
        capture_output=True, text=True)
    # `ld65` escribe el nombre del área con comillas tipográficas.
    se_pasa = re.search(r"overflows memory area .\w+. by (\d+) byte",
                        hecho.stderr)
    assert se_pasa, hecho.stderr
    return n - int(se_pasa.group(1))


@pytest.mark.parametrize("segmento,clave,n", [
    ("TABLAS", "bank0", 40000),
    ("BSS", "bss", 20000),
    ("ZEROPAGE", "zeropage", 1000),
])
def test_lo_libre_es_lo_que_dice_ld65(segmento, clave, n, tmp_path):
    sfc = cartridges.rom_of(cartridges.RELEASE)
    assert space.measure(sfc)[clave] == _libre_con_res(sfc, segmento,
                                                        tmp_path, n)


def test_el_banco_1_es_lo_que_rellena_el_align():
    """`FAR` termina en código y no en ceros, así que lo libre es lo que queda
    detrás de su último byte distinto de cero: la medición de antes, que no
    sirve si el código terminara en un `.byte 0`, pero sí para controlar."""
    sfc = cartridges.rom_of(cartridges.RELEASE)
    with open(sfc, "rb") as archivo:
        banco1 = archivo.read()[0x8000:0x10000]
    assert space.measure(sfc)["bank1"] == len(banco1) - len(banco1.rstrip(b"\0"))


def test_los_textos_son_el_bloque_entero():
    """`MENSAJES_BYTES` y `MENSAJES_TOPE` los emite el conversor al lado de
    `mensajes`: sin ellos la receta diría que la ROM no sabe cuánto miden."""
    sfc = cartridges.rom_of(cartridges.RELEASE)
    medido = space.measure(sfc)
    assert 0 < medido["texts"] <= medido["texts_cap"]

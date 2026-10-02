"""Goombario sobre el runtime: las trampas que ensamblan bien y están mal.

`goombario` —del PATH, como cualquier herramienta de la suite— lee cada
cartucho armado, su `.dbg` y el fuente, y marca cuatro cosas: un salto condicional sobre una bandera que dejó un `pl*` (la trampa de
AGENTS.md que mordió cuatro veces), una rutina que se entra con `jsl` y
vuelve con `rts` o al revés, un camino que deja bytes en la pila o saca de
más, y un ancho de A o de X/Y que no es el que el fuente declara. Su README
dice cómo mira cada una y qué no ve.

Lo que está bien y lo marca igual va en `rom/excepciones-del-linter.txt`,
cada cosa con su porqué; una excepción que ya no tapa nada también hace
fallar, para que la lista no crezca sola. Sólo se mira el runtime: lo que
genera el conversor son datos.

Se corre sobre los tres cartuchos porque los anchos y los caminos dependen
de las perillas: `test-special` arma con otros flags.
"""

import os
import re
import subprocess

import pytest

import cartuchos
import lugares
import tanda

EXCEPCIONES = os.path.join(lugares.ABL, "excepciones-del-linter.txt")


def _goombario(nombre):
    sfc = tanda.cartucho(nombre).sfc
    raiz = cartuchos.raiz()
    runtime = os.path.relpath(cartuchos.runtime(), raiz) + "/"
    return subprocess.run(
        ["goombario", sfc, "--root", raiz, "--only", runtime,
         "--allow", EXCEPCIONES, "--stats"],
        capture_output=True, text=True)


@pytest.mark.parametrize("nombre", sorted(cartuchos.nombres()))
def test_el_runtime_no_cae_en_ninguna_trampa(nombre):
    hecho = _goombario(nombre)
    assert hecho.returncode != 2, hecho.stderr
    assert hecho.returncode == 0, "\n" + hecho.stdout
    # Y que haya mirado algo: un `.dbg` mal leído da cero sin revisar nada,
    # que es lo que le pasó a la primera versión de la guarda de los bancos.
    vistos = {k: int(v) for k, v in re.findall(
        r"(instructions|pulls|entries|returns reached) (\d+)", hecho.stderr)}
    assert all(vistos.get(k, 0) > 100 for k in
               ("instructions", "pulls", "entries", "returns reached")), (
        hecho.stderr)

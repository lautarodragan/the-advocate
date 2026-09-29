"""Los cartuchos de la tanda: que su huella cubra todo lo que los arma, que
su `.dbg` le sirva a Mesen2, y que la lista de mapas y de casos de cada uno
diga lo que parece.

Lo que el armado hace sin un cartucho —el checksum, la cabecera, los
símbolos, qué fuentes se incluyen, que un caso corra en el cartucho que
lleva todos sea cual sea el orden del archivo— son pruebas de las
herramientas, y viven con ellas. Acá se mira lo mismo sobre lo que este
juego declara.
"""

import os
import re

import pytest

import cartuchos
import tanda


def test_todo_lo_que_arma_la_rom_esta_en_la_huella():
    """Si no, editar un archivo incluido deja el cartucho "al día" y las
    pruebas corren contra una ROM vieja sin avisar."""
    huella = {os.path.realpath(r)
              for r in cartuchos.lista()["fingerprint_files"]}
    principal = os.path.join(cartuchos.runtime(), "main.s")
    fuera = [r for r in cartuchos.fuentes(principal)
             if os.path.realpath(r) not in huella]
    assert fuera == []


@pytest.mark.parametrize("nombre", sorted(cartuchos.nombres()))
def test_el_dbg_nombra_los_fuentes_relativos_a_la_raiz(nombre):
    """Mesen2 busca cada `file` del `.dbg` al lado del `.dbg` y subiendo de
    carpeta: con una ruta absoluta del contenedor no lo encuentra en el clon
    del host, y muestra el desensamblado sin el fuente. Ver "Depurar con
    Mesen2" en `docs/snes/emulators.md`."""
    uno = tanda.cartucho(nombre)
    with open(uno.sfc + ".dbg") as archivo:
        nombres = re.findall(r'^file\t.*?name="([^"]+)"', archivo.read(), re.M)
    assert nombres
    absolutos = [n for n in nombres if os.path.isabs(n)]
    assert absolutos == []
    faltan = [n for n in nombres
              if not os.path.isfile(os.path.join(cartuchos.raiz(), n))]
    assert faltan == []


def test_un_caso_que_esta_en_dos_corre_en_el_que_lleva_todos():
    """Con `test-special` primero, `parado-tapado` corrió en el chico y movió
    su golden. Que no dependa del orden lo cobran las pruebas de
    `rm2k-snes-cartridges`; esto mira que este juego tenga un caso así, que
    es lo que hace que la regla importe."""
    todos = {c["name"] for c in cartuchos.lista()["cartridges"]
             if c["all_cases"]}
    en_dos = {caso: donde for caso in cartuchos.todos_los_casos()
              for donde in [cartuchos.donde_esta(caso)] if len(donde) > 1}
    assert en_dos, "ningún caso está en dos cartuchos: esta prueba no mira nada"
    for caso, donde in en_dos.items():
        assert donde[0] in todos, (caso, donde)


def test_la_exclusion_y_los_agregados_de_release_hacen_algo():
    """Cada excluido es un mapa que la regla metería, y cada agregado uno que
    no: si no, el número está de adorno en la lista y nadie se entera. Pasa
    si `below` baja por debajo de un excluido, o si se excluye un área del
    árbol, que la regla ya deja afuera sola."""
    mapas = cartuchos.lista()["maps"]
    sin_excluir = set(mapas["by_the_rule_alone"])
    assert set(mapas["excluded"]) <= sin_excluir
    assert not set(mapas["added"]) & sin_excluir

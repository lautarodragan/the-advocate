"""Los cartuchos de la tanda: que su huella cubra todo lo que los arma, que
su `.dbg` le sirva a Mesen2, y que la lista de mapas y de casos de cada uno
diga lo que parece.

Lo que el ensamblado hace sin un cartucho —el checksum, la cabecera, los
símbolos, qué fuentes se incluyen— son pruebas de las herramientas, y viven
con ellas.
"""

import os
import re

import pytest

from assembly import cartuchos, ensamblar
import tanda


def test_todo_lo_que_arma_la_rom_esta_en_la_huella(tmp_path):
    """Si no, editar un archivo incluido deja el cartucho "al día" y las
    pruebas corren contra una ROM vieja sin avisar. Sobre el árbol de verdad, y
    sobre uno armado a mano con un solo `.include`, que no depende de cuáles
    tenga el árbol."""

    def cubiertas(fuente):
        huella = {os.path.realpath(r)
                  for r in cartuchos.archivos_de_la_huella(fuente)}
        principal = os.path.join(fuente, "main.s")
        return [r for r in ensamblar.fuentes(principal)
                if os.path.realpath(r) not in huella]

    assert cubiertas(cartuchos.FUENTE) == []
    (tmp_path / "main.s").write_text('.include "tienda.s"\n')
    (tmp_path / "tienda.s").write_text("")
    assert cubiertas(str(tmp_path)) == []


@pytest.mark.parametrize("nombre", sorted(cartuchos.CARTUCHOS))
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
              if not os.path.isfile(os.path.join(cartuchos.RAIZ, n))]
    assert faltan == []


def test_donde_corre_un_caso_no_depende_del_orden_de_los_cartuchos(monkeypatch):
    """Un caso que está en dos cartuchos corre en el que lleva todos, lo diga
    como lo diga el diccionario. Con `test-special` primero, `parado-tapado`
    corrió en el chico y movió su golden."""
    antes = {caso: cartuchos.donde_esta(caso)
             for caso in cartuchos.todos_los_casos()}
    monkeypatch.setattr(cartuchos, "CARTUCHOS",
                        dict(reversed(list(cartuchos.CARTUCHOS.items()))))
    despues = {caso: cartuchos.donde_esta(caso)
               for caso in cartuchos.todos_los_casos()}
    assert antes == despues
    assert any(len(donde) > 1 for donde in antes.values()), (
        "ningún caso está en dos cartuchos: esta prueba no mira nada")


def test_la_exclusion_y_los_agregados_de_release_hacen_algo():
    """Cada excluido es un mapa que la regla metería, y cada agregado uno que
    no: si no, el número está de adorno en la lista y nadie se entera. Pasa
    si `MENOR_A` baja por debajo de un excluido, o si se excluye un área del
    árbol, que la regla ya deja afuera sola."""
    sin_excluir = cartuchos.mapas_de_la_regla(excluidos={}, agregados=())
    assert set(cartuchos.EXCLUIDOS) <= set(sin_excluir)
    assert not set(cartuchos.AGREGADOS) & set(sin_excluir)

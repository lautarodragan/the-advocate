"""El compresor LZ2 contra la referencia, sobre **todos** los bloques que la ROM
descomprime al cargar un mapa, en todos los cartuchos.

`tools/snes/lz2/` tiene sus propias pruebas, en inglés y sin nada de este juego,
y `rm2k-snes-mapdata` las suyas de cómo parte cada bloque en flujos y qué tope
de la WRAM tiene cada uno; éstas son las del port: que cada bloque que el
conversor dejó en `crudos/` —ver `write_raw` en materials.py— vuelva igual
pasando por los flujos que arma la etapa y por `pruebas/arnes/lz2.py`, que está
escrita aparte a propósito. Lo que la ROM hace con esos flujos lo mira
`test_carga_descomprimida.py`.
"""

import collections
import glob
import os

import pytest

import tanda
import cartuchos
from lz2 import descomprimir
from port.materials import COMPRESSED_KINDS, compress_blocks


def _crudos(nombre):
    """{archivo: bytes} de lo que dejó el conversor para ese cartucho."""
    uno = tanda.cartucho(nombre)
    rutas = sorted(glob.glob(os.path.join(uno.dir, "crudos", "*.bin")))
    return {os.path.basename(r): open(r, "rb").read() for r in rutas}


class _Mapa(dict):
    """Lo que `compress_blocks` lee de un mapa: sus cinco bloques crudos, con
    los nombres del `map_info`."""

    def __init__(self, numero, bloques):
        super().__init__(id=numero, tiles=bloques["map_tiles"],
                         above=(bloques["above_tiles"],),
                         sprite=(bloques["sprite_tiles"],),
                         anim=bloques["anim_tiles"],
                         celdas=bloques["map_cells"])


@pytest.mark.parametrize("nombre", sorted(cartuchos.nombres()))
def test_cada_bloque_vuelve_igual_por_la_referencia(nombre):
    crudos = _crudos(nombre)
    clases = {r.split(".")[1] for r in crudos}
    assert clases == set(COMPRESSED_KINDS), (
        "crudos/ trae %s y las clases que se comprimen son %s"
        % (sorted(clases), sorted(COMPRESSED_KINDS)))
    por_mapa = collections.defaultdict(dict)
    for archivo, datos in crudos.items():
        numero, clase, _bin = archivo.split(".")
        por_mapa[int(numero)][clase] = datos
    # La ida y vuelta se hace sobre lo mismo que va al cartucho: la etapa
    # devuelve los flujos de cada bloque pegados —las grillas van en dos, y
    # los fondos de más de un buffer también—, y la referencia los lee uno
    # detrás del otro.
    flujos, _cuadros = compress_blocks(
        [_Mapa(n, por_mapa[n]) for n in sorted(por_mapa)])
    mal = []
    for (clase, crudo), pegados in flujos.items():
        vuelta, fin = bytearray(), 0
        while fin < len(pegados):
            uno, fin = descomprimir(pegados, fin)
            vuelta += uno
        if bytes(vuelta) != crudo:
            mal.append("%s de %d bytes: volvieron %d"
                       % (clase, len(crudo), len(vuelta)))
    assert not mal, "\n".join(mal)
    assert sum(len(c) for c in crudos.values()) > 0, "no había nada que comprimir"


def test_la_referencia_lee_los_cinco_comandos_y_los_encabezados_largos():
    # Uno de cada, a mano y desde el formato: si la referencia leyera mal un
    # comando que el compresor no emite en los bloques de hoy, la ida y vuelta
    # de arriba no lo vería.
    flujo = bytes([
        0x02, 1, 2, 3,              # literal de 3
        0x23, 9,                    # relleno de 4 con 9
        0x44, 7, 8,                 # palabra de 5: 7 8 7 8 7
        0x62, 0xFE,                 # creciente de 3: FE FF 00
        0x81, 0x00, 0x01,           # repetición de 2 desde la posición 1
        0xE4, 0x20, 5,              # relleno largo de 33 con 5
        0xFF])
    esperado = (bytes([1, 2, 3]) + bytes([9] * 4) + bytes([7, 8, 7, 8, 7])
                + bytes([0xFE, 0xFF, 0x00]) + bytes([2, 3]) + bytes([5] * 33))
    assert descomprimir(flujo) == (esperado, len(flujo))

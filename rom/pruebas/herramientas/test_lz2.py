"""El compresor LZ2 contra la referencia, sobre **todos** los bloques que la ROM
descomprime al cargar un mapa, en todos los cartuchos.

`tools/lz2/` tiene sus propias pruebas, en inglés y sin nada de este juego;
éstas son las del port: que cada bloque que el conversor dejó en `crudos/` —ver
`escribir_crudos` en snes_convert.py— vuelva igual pasando por el binario y por
`pruebas/arnes/lz2.py`, que está escrita aparte a propósito. Lo que la ROM hace
con esos flujos lo mira `test_carga_descomprimida.py`.
"""

import glob
import os

import pytest

import tanda
from assembly import cartridges
from lz2 import descomprimir
from port import comprimir
from port.snes_convert import (CLASES_COMPRIMIDAS, LZ2_TOPE_FONDO,
                               controlar_flujos, partes_comprimidas)


def _crudos(nombre):
    """{archivo: bytes} de lo que dejó el conversor para ese cartucho."""
    uno = tanda.cartucho(nombre)
    rutas = sorted(glob.glob(os.path.join(uno.dir, "crudos", "*.bin")))
    return {os.path.basename(r): open(r, "rb").read() for r in rutas}


@pytest.mark.parametrize("nombre", sorted(cartridges.CARTRIDGES))
def test_cada_bloque_vuelve_igual_por_la_referencia(nombre):
    crudos = _crudos(nombre)
    clases = {r.split(".")[1] for r in crudos}
    assert clases == set(CLASES_COMPRIMIDAS), (
        "crudos/ trae %s y las clases que se comprimen son %s"
        % (sorted(clases), sorted(CLASES_COMPRIMIDAS)))
    # La ida y vuelta se hace sobre lo mismo que va al cartucho: las grillas
    # van en dos flujos, y los fondos de más de un buffer también. Ver
    # `partes_comprimidas`.
    trozos = []
    for archivo, datos in crudos.items():
        partes = partes_comprimidas(archivo.split(".")[1], datos)
        trozos += [(archivo, k, parte) for k, parte in enumerate(partes)]
    flujos = comprimir.comprimir_varios([t[2] for t in trozos])
    mal = []
    for (archivo, k, parte), flujo in zip(trozos, flujos):
        vuelta, fin = descomprimir(flujo)
        if vuelta != parte or fin != len(flujo):
            mal.append("%s, trozo %d: %d bytes, volvieron %d y el flujo termina "
                       "en %d de %d" % (archivo, k, len(parte), len(vuelta), fin,
                                        len(flujo)))
    assert not mal, "\n".join(mal)
    assert sum(len(t[2]) for t in trozos) > 0, "no había nada que comprimir"


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


def test_un_fondo_de_mas_de_un_buffer_va_en_dos_flujos_y_de_tres_no_arma():
    """El fondo se parte en tramos de `LZ2_TOPE_FONDO` exactos, que es lo que
    `lz2_fondo` supone para saber cuántos tiles trae cada flujo; uno que entra
    en el buffer va entero, como antes. Y la ROM lee dos: con tres, el
    conversor se niega en vez de dejar un fondo a medias."""
    tope = LZ2_TOPE_FONDO
    assert partes_comprimidas("map_tiles", bytes(tope)) == [bytes(tope)]
    dos = bytes(range(256)) * ((tope + 960) // 256) + bytes(192)
    partes = partes_comprimidas("map_tiles", dos)
    assert [len(t) for t in partes] == [tope, len(dos) - tope]
    assert b"".join(partes) == dos
    controlar_flujos(66, "map_tiles", dos)
    with pytest.raises(SystemExit, match="3 streams"):
        controlar_flujos(66, "map_tiles", bytes(2 * tope + 64))


def test_un_flujo_que_no_entra_en_su_lugar_de_la_wram_no_arma():
    """La capa de encima y los sprites van en un solo flujo, y más grande que
    su lugar pisaría los dibujos de la animación."""
    with pytest.raises(SystemExit, match="a stream of sprite_tiles"):
        controlar_flujos(1, "sprite_tiles", bytes(0x6000 + 32))

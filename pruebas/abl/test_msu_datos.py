"""El puerto de datos del MSU-1: los fondos de batalla leídos del `.msu`.

El cartucho lleva en la ROM el respaldo liviano de cada fondo —4bpp, 16
colores— y el conversor escribe en el `.msu` el de calidad —8bpp, 96—: ver
"El respaldo liviano" en tools/port/escena.py. Con MSU-1 y el `.msu` de este
cartucho la ROM lee el de calidad; sin MSU-1, o con otro `.msu`, el suyo. La
tanda entera corre sin MSU-1 —el arnés le esconde el `.msu` al core, ver
`retro.Consola`—, así que cubre el respaldo; esto cubre el otro camino, y que
el respaldo se elija cuando tiene que elegirse.

Como los dos fondos son distintos a propósito, **cada camino se compara
contra su propia golden** —`msu-datos-rom` y `msu-datos-msu`—, y además el
fondo limpio de la WRAM contra los bytes que el conversor arma de este lado:
el de calidad tal cual, y el liviano agrandado a 8bpp como lo agranda la ROM.

**Lo que prueba que la imagen salió del `.msu`** sigue siendo el control: el
mismo `.msu` con los tiles del fondo cambiados y la firma de la cabecera
intacta —la ROM no puede hashear 98 KB— tiene que dibujar otra cosa.

Corre en snes9x y en bsnes, que implementan el puerto igual (`readIO` de
`$2001` en `sfc/coprocessor/msu1/msu1.cpp` de bsnes, `S9xMSU1ReadPort` en
`msu1.c` de snes9x) y aceptan DMA desde `$2001`. mesen-s también lo hace
—medido a mano—, pero no se suma por lo que dice `test_cores.py`: arrastra
estado de una consola a la siguiente en el mismo proceso.
"""

import os
import shutil

import pytest

from port import escena, msu_datos, snes_convert
from render.render_map import GAME_DIR

import tanda
from consola import Partida, en_la_rom, en_la_wram
from ensamblado import cartuchos

SNES9X = "/usr/lib/libretro/snes9x_libretro.so"
BSNES = "/usr/lib/libretro/bsnes_libretro.so"

# El encuentro al azar de Sector 27 con la tropa 100, el mismo de
# `test_batalla_escena_dibujo.py`: hereda el fondo del mapa, así que tiene uno.
SECTOR_27 = (28, 20, 30)
SEMILLA_TROPA_100 = 22
ARRANQUE = "en-5"
FONDO_SECTOR_27 = "ABLBackdropSJ03"


def _pelea(tmp_path, nombre, nucleo, msu):
    """La pelea de Sector 27 recién abierta, con `msu` —los bytes de un `.msu`,
    o None— al lado de una copia de la ROM. Devuelve (la imagen a 15 bits, de
    dónde salió el fondo, qué fondo, la captura y el fondo limpio de la
    WRAM)."""
    uno = tanda.cartucho(cartuchos.PRUEBAS)
    k = uno.casos.index(ARRANQUE)
    directorio = os.path.join(tmp_path, nombre)
    os.makedirs(directorio)
    sfc = os.path.join(directorio, os.path.basename(uno.sfc))
    shutil.copyfile(uno.sfc, sfc)
    if msu is not None:
        with open(os.path.splitext(sfc)[0] + ".msu", "wb") as archivo:
            archivo.write(msu)
    una = Partida(sfc, uno.simbolos, uno.mapas, nucleo=nucleo, caso=k,
                  salta=uno.saltan[k], msu=msu is not None)
    una.ir_al_mapa(*SECTOR_27)
    s = uno.simbolos
    una.consola.escribir_ram(en_la_wram(s["ENC_SEM"]),
                             [SEMILLA_TROPA_100 & 0xFF, SEMILLA_TROPA_100 >> 8])
    una.consola.escribir_ram(en_la_wram(s["ENC_PIDE"]), [1])
    for _ in range(400):
        if una.byte("menu_abierto"):
            break
        una.consola.correr(1)
    else:
        raise AssertionError("la pelea de Sector 27 no se abrió")
    una.consola.correr(3)

    def byte(nombre):
        return una.consola.ram(en_la_wram(s[nombre]), 1)[0]
    # La captura, llevada a 15 bits antes de compararla con su golden: snes9x
    # y bsnes pasan el mismo color de 15 bits a 24 de distinta manera —98 y
    # 99—, y esta prueba corre en los dos contra la misma golden.
    imagen = una.consola.imagen().convert("RGB").point(lambda v: v & 0xF8)
    limpio = una.consola.ram(en_la_wram(s["ESC_LIMPIO"]), escena.TILES * 64)
    return (tanda.quince_bits(imagen), byte("ESC_MSU"), byte("ESC_FONDO"),
            imagen, bytes(limpio))


def _fondo_8bpp(liviano):
    """Los 32 KB que la ROM deja en la WRAM para el fondo de Sector 27: el de
    calidad tal cual, o el liviano con los planos 4 a 7 pegados a cada tile."""
    info = escena.fondo(FONDO_SECTOR_27, GAME_DIR)
    if not liviano:
        return snes_convert.fondo_bytes(info)[0]
    info["respaldo"] = escena.fondo_liviano(FONDO_SECTOR_27, GAME_DIR)
    tiles, _colores = snes_convert.respaldo_bytes(info)
    alto = snes_convert.respaldo_alto()
    ancho = escena.RESPALDO_PLANOS * 8
    return b"".join(tiles[k:k + ancho] + alto
                    for k in range(0, len(tiles), ancho))


def _msu_del_cartucho():
    tanda.cartucho(cartuchos.PRUEBAS)       # se niega si está viejo
    with open(cartuchos.msu_de(cartuchos.PRUEBAS), "rb") as archivo:
        return archivo.read()


def _tiles_cambiados(msu, fondo):
    """Una copia del `.msu` con los tiles del fondo `fondo` negados, y la
    cabecera tal cual: la firma sigue siendo la que la ROM espera."""
    donde, largo = msu_datos.indice(msu)[2 * fondo]
    otro = bytearray(msu)
    for i in range(donde, donde + largo):
        otro[i] ^= 0xFF
    return bytes(otro)


@pytest.mark.parametrize("nucleo", [SNES9X, BSNES], ids=["snes9x", "bsnes"])
def test_msu_cada_camino_dibuja_su_fondo(tmp_path, nucleo):
    """Sin MSU-1 el fondo liviano de la ROM, con MSU-1 el de calidad del `.msu`:
    cada uno contra su golden, y el control de que salió del `.msu`."""
    msu = _msu_del_cartucho()
    sin, de_donde, fondo, imagen, limpio = _pelea(tmp_path, "sin", nucleo,
                                                  None)
    assert fondo != 0xFF, "la pelea de Sector 27 quedó sin fondo"
    assert de_donde == 0, "sin MSU-1, la ROM dice que leyó el fondo del .msu"
    assert limpio == _fondo_8bpp(liviano=True), (
        "sin MSU-1 el fondo de la WRAM no es el respaldo liviano agrandado a "
        "8bpp: la copia de dos canales de `esc_llenar` no anda")
    tanda.golden("msu-datos-rom", imagen)

    con, de_donde, _fondo, imagen, limpio = _pelea(tmp_path, "con", nucleo,
                                                   msu)
    assert de_donde == 1, (
        "con MSU-1 y el .msu del cartucho, la ROM leyó el fondo de sí misma: "
        "o no encontró la firma, o el MSU-1 no se encendió")
    assert limpio == _fondo_8bpp(liviano=False), (
        "con MSU-1 el fondo de la WRAM no es el de calidad: los bytes del .msu "
        "no son los del conversor, o el DMA desde $2001 no anda")
    tanda.golden("msu-datos-msu", imagen)
    assert con != sin, (
        "con MSU-1 la pelea se ve igual que sin él, y los fondos son distintos "
        "a propósito: alguno de los dos caminos no está leyendo lo suyo")

    cambiado, de_donde, _fondo, _imagen, _limpio = _pelea(
        tmp_path, "control", nucleo, _tiles_cambiados(msu, fondo))
    assert de_donde == 1
    assert cambiado != con, (
        "con los tiles del .msu cambiados la pelea se ve igual: la ROM no está "
        "leyendo el fondo del .msu, y la comparación de arriba no prueba nada")


@pytest.mark.parametrize("nucleo", [SNES9X, BSNES], ids=["snes9x", "bsnes"])
def test_msu_de_otro_build_cae_al_cartucho(tmp_path, nucleo):
    """Un `.msu` que no es el de este cartucho no se lee: la ROM usa el suyo.

    El de otro build es un `.msu` bien formado, con su firma correcta, y otros
    datos: los tiles cambiados del control de arriba con la firma recalculada.
    Si la ROM lo aceptara, la pelea se vería distinta. Y el vacío es el que
    deja `msu.py` cuando no hay otro, que tiene que andar igual.
    """
    msu = _msu_del_cartucho()
    sin, _de_donde, fondo, _imagen, _limpio = _pelea(tmp_path, "sin", nucleo,
                                                     None)
    entradas = [bytearray(e) for e in msu_datos.leer(msu)]
    for i in range(len(entradas[2 * fondo])):
        entradas[2 * fondo][i] ^= 0xFF
    otro, _posiciones = msu_datos.armar([bytes(e) for e in entradas])
    assert otro[:msu_datos.FIRMA] != msu[:msu_datos.FIRMA]
    for nombre, archivo in (("otro", otro), ("vacio", b"")):
        imagen, de_donde, _fondo, _captura, _limpio = _pelea(
            tmp_path, nombre, nucleo, archivo)
        assert de_donde == 0, (
            "con el .msu %s la ROM leyó el fondo de ahí: no está mirando la "
            "firma" % nombre)
        assert imagen == sin, (
            "con el .msu %s la pelea no se ve como sin MSU-1" % nombre)


def test_msu_la_rom_sabe_donde_esta_cada_fondo():
    """La firma que la ROM espera es la del `.msu` de su cartucho, y
    `msu_fondo_pos` apunta a las entradas de su índice, que miden lo que la
    ROM lee de ahí: 512 tiles de 8bpp y 96 colores. Sin emulador: lee el
    archivo, la ROM y su tabla de símbolos. Qué hay adentro lo cubre
    `test_msu_cada_camino_dibuja_su_fondo`."""
    for nombre in cartuchos.CARTUCHOS:
        uno = tanda.cartucho(nombre)
        with open(uno.sfc, "rb") as archivo:
            rom = archivo.read()
        with open(cartuchos.msu_de(nombre), "rb") as archivo:
            msu = archivo.read()
        indice = msu_datos.indice(msu)
        s = uno.simbolos
        assert msu[:msu_datos.FIRMA] == rom[en_la_rom(s["msu_datos_firma"]):][
            :msu_datos.FIRMA], "%s: la firma de la ROM no es la del .msu" % nombre
        pos = en_la_rom(s["msu_fondo_pos"])
        for k in range(len(indice) // 2):
            (dt, lt), (dc, lc) = indice[2 * k], indice[2 * k + 1]
            assert rom[pos + 8 * k:pos + 8 * k + 8] == (
                dt.to_bytes(4, "little") + dc.to_bytes(4, "little")), (
                "%s: msu_fondo_pos del fondo %d no apunta a sus entradas"
                % (nombre, k))
            assert (lt, lc) == (escena.TILES * 64, escena.COLORES * 2), (
                "%s: el fondo %d del .msu mide %d y %d" % (nombre, k, lt, lc))

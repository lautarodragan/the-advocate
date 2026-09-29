"""El puerto de datos del MSU-1: los fondos de batalla leídos del `.msu`.

El cartucho lleva en la ROM el respaldo liviano de cada fondo —128x64 en
4bpp, 16 colores, que la ROM agranda al doble— y el conversor escribe en el `.msu` el de calidad —8bpp, 96—: ver
"El respaldo liviano" en tools/port/scene.py. Con MSU-1 y el `.msu` de este
cartucho la ROM lee el de calidad; sin MSU-1, o con otro `.msu`, el suyo. La
tanda entera corre sin MSU-1 —el arnés le esconde el `.msu` al core, ver
`retro.Console`—, así que cubre el respaldo; esto cubre el otro camino, y que
el respaldo se elija cuando tiene que elegirse.

Como los dos fondos son distintos a propósito, **cada camino se compara
contra su propia golden** —`msu-datos-rom` y `msu-datos-msu`—, y además el
fondo limpio de la WRAM contra los bytes que el conversor arma de este lado:
el de calidad tal cual, y el liviano agrandado a 8bpp como lo agranda la ROM.

**Lo que prueba que la imagen salió del `.msu`** sigue siendo el control: el
mismo `.msu` con los tiles del fondo cambiados y la firma de la cabecera
intacta —la ROM no puede hashear 98 KB— tiene que dibujar otra cosa.

**Y el `.msu` lleva todos los fondos del juego**, cada uno en su lugar fijo
—ver "El formato" en tools/port/msu_data.py—, y la ROM los que piden las
peleas del cartucho. Lo prueba una pelea del mundo, el 66, cuyo fondo es el
del terreno que pisa el héroe: con el `.msu` sale el de calidad, y sin él su
respaldo. El reemplazo, para un fondo que la ROM no lleva, lo prueba
`test_escena_una_pelea_cuyo_fondo_no_esta_usa_el_reemplazo`.

Corre en snes9x y en bsnes, que implementan el puerto igual (`readIO` de
`$2001` en `sfc/coprocessor/msu1/msu1.cpp` de bsnes, `S9xMSU1ReadPort` en
`msu1.c` de snes9x) y aceptan DMA desde `$2001`. mesen-s también lo hace
—medido a mano—, pero no se suma por lo que dice `test_cores.py`: arrastra
estado de una consola a la siguiente en el mismo proceso.
"""

import os
import shutil

import pytest

from port import scene, events, snes_format, msu_data, snes_convert
from rpgmaker.resources import GAME_DIR
from rpgmaker import lcf, rm2k

import tanda
from consola import Partida, en_la_rom, en_la_wram
from assembly import cartridges

SNES9X = "/usr/lib/libretro/snes9x_libretro.so"
BSNES = "/usr/lib/libretro/bsnes_libretro.so"

# El encuentro al azar de Sector 27 con la tropa 100, el mismo de
# `test_batalla_escena_dibujo.py`: hereda el fondo del mapa, así que tiene uno.
SECTOR_27 = (28, 20, 30)
SEMILLA_TROPA_100 = 22
ARRANQUE = "en-5"
FONDO_SECTOR_27 = "ABLBackdropSJ03"

# La llegada al mundo, la de `test_mundo.py`: el 66 no nombra fondo, así que
# la pelea usa el del terreno de la celda. Lo que corre la automática del
# evento 1 al llegar, con margen.
EL_MUNDO = (66, 71, 29)
# El viaje de Dalia (la automática 14 del 66) arranca con `DummyHero`, el
# actor 10, en el grupo, que es el de `en-5`: con él corriendo no se abre
# ninguna pelea. El 278, "ya llegó a Tasgarde", le pone la página vacía.
DALIA_LLEGO = 278
LLEGAR_TICKS = 30


def _pelea(tmp_path, nombre, nucleo, msu, lugar=SECTOR_27, antes=0,
           semilla=SEMILLA_TROPA_100):
    """La pelea de `lugar` —la de Sector 27, si no— recién abierta, con `msu`
    —los bytes de un `.msu`, o None— al lado de una copia de la ROM, y `antes`
    ticks de espera al llegar. Devuelve (la imagen a 15 bits, de dónde salió
    el fondo, qué fondo, la captura y el fondo limpio de la WRAM)."""
    uno = tanda.cartucho(cartridges.RELEASE)
    k = uno.casos.index(ARRANQUE)
    directorio = os.path.join(tmp_path, nombre)
    os.makedirs(directorio)
    sfc = os.path.join(directorio, os.path.basename(uno.sfc))
    shutil.copyfile(uno.sfc, sfc)
    if msu is not None:
        with open(os.path.splitext(sfc)[0] + ".msu", "wb") as archivo:
            archivo.write(msu)
    una = Partida(sfc, uno.simbolos, uno.mapas, nucleo=nucleo, caso=k,
                  salta=uno.saltan[k], msu=msu is not None, titulo=uno.titulo)
    if lugar[0] == EL_MUNDO[0]:
        una.prender(DALIA_LLEGO)
    una.ir_al_mapa(*lugar)
    if antes:
        una.correr(antes)
    s = uno.simbolos
    una.consola.write_ram(en_la_wram(s["ENC_RNG"]),
                          [semilla & 0xFF, semilla >> 8])
    una.consola.write_ram(en_la_wram(s["ENC_ASKS"]), [1])
    for _ in range(400):
        if una.byte("menu_open"):
            break
        una.consola.run(1)
    else:
        raise AssertionError("la pelea en %s no se abrió" % (lugar,))
    una.consola.run(3)

    def byte(nombre):
        return una.consola.ram(en_la_wram(s[nombre]), 1)[0]
    # La captura, llevada a 15 bits antes de compararla con su golden: snes9x
    # y bsnes pasan el mismo color de 15 bits a 24 de distinta manera —98 y
    # 99—, y esta prueba corre en los dos contra la misma golden.
    imagen = una.consola.image().convert("RGB").point(lambda v: v & 0xF8)
    limpio = una.consola.ram(en_la_wram(s["SCN_CLEAN"]), scene.TILES * 64)
    return (tanda.quince_bits(imagen), byte("SCN_MSU"), byte("SCN_BACKDROP"),
            imagen, bytes(limpio))


def _fondo_8bpp(liviano, nombre=FONDO_SECTOR_27):
    """Los 32 KB que la ROM deja en la WRAM para un fondo —el de Sector 27, si
    no—: el de calidad tal cual, o el liviano agrandado al doble. El liviano
    se arma de sus índices ya duplicados y en 8bpp, sin pasar por
    `fallback_bytes`: así lo que se compara es lo que hace la ROM contra la
    imagen, y no contra el mismo orden de bytes del que ella lee."""
    if not liviano:
        return snes_convert.backdrop_bytes(scene.backdrop(nombre, GAME_DIR))[0]
    grande = scene.light_backdrop(nombre, GAME_DIR)["indices"]
    return b"".join(snes_format.pack_tile(celda, planes=8)
                    for celda in scene.tiles(grande))


def _msu_del_cartucho():
    tanda.cartucho(cartridges.RELEASE)       # se niega si está viejo
    with open(cartridges.msu_of(cartridges.RELEASE), "rb") as archivo:
        return archivo.read()


def _tiles_cambiados(msu, fondo):
    """Una copia del `.msu` con los tiles del fondo `fondo` negados, y la
    cabecera tal cual: la firma sigue siendo la que la ROM espera."""
    donde, largo = msu_data.index(msu)[2 * fondo]
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
        "8bpp y al doble: `scn_fill` o `scn_double` no andan")
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
    entradas = [bytearray(e) for e in msu_data.read(msu)]
    for i in range(len(entradas[2 * fondo])):
        entradas[2 * fondo][i] ^= 0xFF
    otro, _posiciones = msu_data.build([bytes(e) for e in entradas])
    assert otro[:msu_data.SIGNATURE_SIZE] != msu[:msu_data.SIGNATURE_SIZE]
    for nombre, archivo in (("otro", otro), ("vacio", b"")):
        imagen, de_donde, _fondo, _captura, _limpio = _pelea(
            tmp_path, nombre, nucleo, archivo)
        assert de_donde == 0, (
            "con el .msu %s la ROM leyó el fondo de ahí: no está mirando la "
            "firma" % nombre)
        assert imagen == sin, (
            "con el .msu %s la pelea no se ve como sin MSU-1" % nombre)


def _fondos_del_juego():
    db = events.database(GAME_DIR)
    tree = lcf.TreeMap(GAME_DIR + "/RPG_RT.lmt")
    return scene.game_backdrops(events.named_backdrops(GAME_DIR), tree,
                                db.terrain_backdrops, GAME_DIR)


def _fondo_del_terreno(mapa, x, y):
    """El nombre del fondo del terreno de una celda, desde el juego: el tile
    de la capa de abajo, su terreno en el ChipSet y el fondo del terreno. Es lo
    que `Spriteset_Battle` usa cuando el mapa no nombra fondo."""
    db = events.database(GAME_DIR)
    game_map = lcf.Map("%s/Map%04d.lmu" % (GAME_DIR, mapa))
    terreno = rm2k.terrain_of(db.chipsets[game_map.chipset_id],
                              game_map.lower_layer[y * game_map.width + x])
    return db.terrain_backdrops[terreno]


@pytest.mark.parametrize("nucleo", [SNES9X, BSNES], ids=["snes9x", "bsnes"])
def test_msu_una_pelea_del_mundo_lee_su_terreno(tmp_path, nucleo):
    """El 66 no nombra fondo: la pelea usa el del terreno donde está el héroe.
    Con el `.msu`, el de calidad de ese terreno; sin él, su respaldo, que la
    ROM lleva porque el 66 tiene encuentros al azar y el conversor mete los
    fondos de todos sus terrenos. Cada camino contra su golden
    —`msu-mundo-rom` y `msu-mundo-msu`— y el fondo limpio de la WRAM contra
    la imagen convertida de este lado."""
    juego = _fondos_del_juego()
    suyo = _fondo_del_terreno(*EL_MUNDO)
    assert suyo, "la celda de la llegada al mundo pisa un terreno sin fondo"
    msu = _msu_del_cartucho()

    sin, de_donde, fondo, imagen, limpio = _pelea(
        tmp_path, "sin", nucleo, None, lugar=EL_MUNDO, antes=LLEGAR_TICKS)
    assert fondo == juego.index(suyo), (
        "la pelea del mundo eligió el fondo %d y el terreno de la celda es "
        "%r, el %d: la ROM no está leyendo el terreno bajo el héroe"
        % (fondo, suyo, juego.index(suyo)))
    assert de_donde == 0
    assert limpio == _fondo_8bpp(liviano=True, nombre=suyo), (
        "sin MSU-1 la pelea del mundo no tiene el respaldo de %r" % suyo)
    assert any(limpio), "sin MSU-1 la pelea del mundo salió en negro"
    tanda.golden("msu-mundo-rom", imagen)

    con, de_donde, fondo, imagen, limpio = _pelea(
        tmp_path, "con", nucleo, msu, lugar=EL_MUNDO, antes=LLEGAR_TICKS)
    assert fondo == juego.index(suyo)
    assert de_donde == 1, "con el .msu la pelea del mundo leyó de la ROM"
    assert limpio == _fondo_8bpp(liviano=False, nombre=suyo), (
        "con el .msu la pelea del mundo no tiene el fondo de %r de calidad"
        % suyo)
    tanda.golden("msu-mundo-msu", imagen)
    assert con != sin


def test_msu_la_rom_sabe_donde_esta_cada_fondo():
    """La firma que la ROM espera es la del `.msu` de su cartucho, y
    `msu_backdrop_pos` apunta a las entradas de su índice, que miden lo que la
    ROM lee de ahí: 512 tiles de 8bpp y 96 colores. Y el `.msu` lleva **todos
    los fondos del juego**, cada uno en su lugar fijo: el mismo en todos los
    cartuchos, con los mismos bytes, lleve cada uno los mapas que lleve. Sin
    emulador: lee el archivo, la ROM y su tabla de símbolos. Qué hay adentro
    lo cubre `test_msu_cada_camino_dibuja_su_fondo`."""
    juego = _fondos_del_juego()
    regiones = {}
    for nombre in cartridges.CARTRIDGES:
        uno = tanda.cartucho(nombre)
        with open(uno.sfc, "rb") as archivo:
            rom = archivo.read()
        with open(cartridges.msu_of(nombre), "rb") as archivo:
            msu = archivo.read()
        indice = msu_data.index(msu)
        s = uno.simbolos
        assert msu[:msu_data.SIGNATURE_SIZE] == rom[en_la_rom(s["msu_data_signature"]):][
            :msu_data.SIGNATURE_SIZE], "%s: la firma de la ROM no es la del .msu" % nombre
        assert s["MSU_BACKDROPS_N"] == s["BACKDROPS_GAME"] == len(juego), (
            "%s: el .msu lleva %d fondos, la ROM cuenta con %d y el juego "
            "tiene %d" % (nombre, s["MSU_BACKDROPS_N"], s["BACKDROPS_GAME"],
                          len(juego)))
        pos = en_la_rom(s["msu_backdrop_pos"])
        # Los fondos van primero, dos entradas cada uno, y detrás los efectos
        # de sonido de calidad: ver `write_msu` en snes_convert.py.
        assert len(indice) == 2 * s["MSU_BACKDROPS_N"] + s["MSU_EFFECTS_N"], (
            "%s: el .msu tiene %d entradas y la ROM cuenta con %d fondos y %d "
            "efectos" % (nombre, len(indice), s["MSU_BACKDROPS_N"],
                         s["MSU_EFFECTS_N"]))
        for k in range(s["MSU_BACKDROPS_N"]):
            (dt, lt), (dc, lc) = indice[2 * k], indice[2 * k + 1]
            assert (dt, dc) == (msu_data.backdrop_offset(k),
                                msu_data.backdrop_offset(k) + msu_data.COLORS_AT), (
                "%s: el fondo %d no está en su lugar fijo" % (nombre, k))
            assert rom[pos + 8 * k:pos + 8 * k + 8] == (
                dt.to_bytes(4, "little") + dc.to_bytes(4, "little")), (
                "%s: msu_backdrop_pos del fondo %d no apunta a sus entradas"
                % (nombre, k))
            assert (lt, lc) == (scene.TILES * 64, scene.COLORS * 2), (
                "%s: el fondo %d del .msu mide %d y %d" % (nombre, k, lt, lc))
        regiones[nombre] = msu[msu_data.BACKDROPS_START:
                               msu_data.backdrop_offset(len(juego))]
    assert len(set(regiones.values())) == 1, (
        "la región de los fondos del .msu no es la misma en todos los "
        "cartuchos: %s" % sorted(regiones))

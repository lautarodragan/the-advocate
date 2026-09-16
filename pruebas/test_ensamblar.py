"""Las tres cosas que `tools/ensamblar.py` hace además de llamar a `ca65` + `ld65`.

Lo grande —que la ROM salga igual que la de antes— lo cobran todas las pruebas
que arman un cartucho. Esto es lo chico, que un error ahí no rompe ninguna
imagen: un checksum mal escrito lo nota un flash cart y no un emulador, y un
símbolo que falta se nota recién en la prueba que lo pide.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))

import ensamblar                                             # noqa: E402


def test_el_checksum_y_su_complemento_no_mueven_la_suma():
    rom = bytearray(4 * 1024 * 1024)
    rom[1234] = 0x56
    rom[ensamblar.CHECKSUM:ensamblar.CHECKSUM + 2] = b"\xff\xff"
    suma = ensamblar.checksum(rom)
    assert suma == (0x56 + 0xFF + 0xFF) & 0xFFFF
    assert rom[ensamblar.CHECKSUM:ensamblar.CHECKSUM + 2] == suma.to_bytes(2, "little")
    assert rom[ensamblar.COMPLEMENTO:ensamblar.COMPLEMENTO + 2] == \
        (suma ^ 0xFFFF).to_bytes(2, "little")
    assert sum(rom) & 0xFFFF == suma


def test_una_cabecera_sin_los_cuatro_bytes_de_siempre_es_un_error():
    rom = bytearray(4 * 1024 * 1024)
    rom[5] = 1
    with pytest.raises(ValueError, match="no se asentó"):
        ensamblar.checksum(rom)


def test_los_simbolos_salen_con_su_scope_y_su_signo(tmp_path):
    dbg = tmp_path / "x.dbg"
    dbg.write_text(
        'scope\tid=0,name="",mod=0,size=10\n'
        'scope\tid=1,name="batalla_correr",mod=0,type=scope,size=5,parent=0\n'
        'sym\tid=0,name="enc_azar",addrsize=absolute,scope=0,val=0x19FDD,seg=1,type=lab\n'
        'sym\tid=1,name="espera",addrsize=absolute,scope=1,val=0x1993E,seg=1,type=lab\n'
        'sym\tid=2,name="IMAGEN_X",addrsize=absolute,scope=0,val=0xFFFFFFF3,type=equ\n'
        'sym\tid=3,name="afuera",addrsize=absolute,scope=0,type=imp\n')
    assert ensamblar.simbolos(str(dbg)) == {
        "enc_azar": 0x19FDD,
        "batalla_correr::espera": 0x1993E,
        "IMAGEN_X": -13,
    }


def test_no_arma_con_un_inc_generado_al_lado_de_la_fuente(tmp_path):
    """`ca65` lo leería antes que el del cartucho, sin avisar."""
    (tmp_path / "main.s").write_text("")
    (tmp_path / "mapdata.inc").write_text("")
    with pytest.raises(RuntimeError, match="mapdata.inc"):
        ensamblar.ensamblar(str(tmp_path / "main.s"), str(tmp_path / "otro"),
                            str(tmp_path / "x.sfc"))

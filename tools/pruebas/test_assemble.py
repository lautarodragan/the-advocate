"""What `tools/assembly/ensamblar.py` does besides calling `ca65` + `ld65`.

The big part —that the ROM comes out the same as before— is enforced by every
test that builds a cartridge. This is the small part, where an error breaks
no image: a badly written checksum is noticed by a flash cart and not by an
emulator, and a missing symbol only shows up in the test that asks for it.
"""

import pytest

from assembly import ensamblar


def test_checksum_and_complement_do_not_move_the_sum():
    rom = bytearray(4 * 1024 * 1024)
    rom[1234] = 0x56
    rom[ensamblar.CHECKSUM:ensamblar.CHECKSUM + 2] = b"\xff\xff"
    suma = ensamblar.checksum(rom)
    assert suma == (0x56 + 0xFF + 0xFF) & 0xFFFF
    assert rom[ensamblar.CHECKSUM:ensamblar.CHECKSUM + 2] == suma.to_bytes(2, "little")
    assert rom[ensamblar.COMPLEMENTO:ensamblar.COMPLEMENTO + 2] == \
        (suma ^ 0xFFFF).to_bytes(2, "little")
    assert sum(rom) & 0xFFFF == suma


def test_a_header_without_the_usual_four_bytes_is_an_error():
    rom = bytearray(4 * 1024 * 1024)
    rom[5] = 1
    with pytest.raises(ValueError, match="did not settle"):
        ensamblar.checksum(rom)


def test_symbols_come_out_with_their_scope_and_sign(tmp_path):
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


def test_refuses_a_generated_inc_next_to_the_source(tmp_path):
    """`ca65` would read it before the cartridge's, without a warning."""
    (tmp_path / "main.s").write_text("")
    (tmp_path / "mapdata.inc").write_text("")
    with pytest.raises(RuntimeError, match="mapdata.inc"):
        ensamblar.ensamblar(str(tmp_path / "main.s"), str(tmp_path / "otro"),
                            str(tmp_path / "x.sfc"))


def test_sources_are_the_included_s_files_not_the_generated_ones(tmp_path):
    (tmp_path / "main.s").write_text(
        '.include "event_opcodes.inc"\n'
        '.include "tienda.s"\n'
        '; .include "citado.s" en un comentario no cuenta\n')
    (tmp_path / "tienda.s").write_text('.include "precios.s"\n')
    (tmp_path / "precios.s").write_text("")
    principal = str(tmp_path / "main.s")
    assert ensamblar.fuentes(principal) == [
        principal, str(tmp_path / "tienda.s"), str(tmp_path / "precios.s")]
    assert ensamblar.texto_de_la_fuente(principal).endswith(
        '.include "precios.s"\n')

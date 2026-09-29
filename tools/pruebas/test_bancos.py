"""The bank packing, which the converter does and no longer the assembler.

What these tests guard is not that the filling is pretty but that it respects
what the converter declares: a block that crosses a bank is uploaded by DMA
reading the WRAM from the middle onwards, and that does not fail at assembly,
it fails by drawing garbage. Since 2026-09-27 the packing is first-fit
decreasing and the ROM no longer comes out byte for byte the same as with the
sequential packing, so the big net is the goldens and the suite; this is the
small one, and it makes an error show up here and not in a capture.
"""

import re

import pytest

from ensamblado import bancos


def resolver(texto, tmp_path, segundo=None):
    """Runs the packing over one or two files and returns what is left."""
    rutas = []
    for i, cuerpo in enumerate([texto] + ([segundo] if segundo else [])):
        ruta = tmp_path / ("parte%d.inc" % i)
        ruta.write_text(cuerpo)
        rutas.append(str(ruta))
    cuenta = bancos.resolver(rutas)
    return [open(r).read() for r in rutas], cuenta


B2, B3 = '.segment "BANK02"', '.segment "BANK03"'


def bytes_(n):
    return "    .byte " + ",".join(["$00"] * n) + "\n"


def test_rodata_pasa_a_ser_el_banco_donde_arrancan_los_datos(tmp_path):
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n.bloque 16\n' + bytes_(1), tmp_path)
    assert B2 in salida and "RODATA" not in salida and ".bloque" not in salida
    assert cuenta == (1, 1)


def test_un_bloque_que_no_entra_va_a_otro_banco(tmp_path):
    """The case that gives meaning to everything: a block is never split. The
    big one goes first, and the 16 bytes no longer fit in the 8 it leaves."""
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n.bloque 16\nchico:\n' + bytes_(16)
        + ".bloque %d\netiqueta:\n" % (bancos.BANCO - 8)
        + bytes_(8) * ((bancos.BANCO - 8) // 8), tmp_path)
    b2, b3 = salida.split(B3)
    assert "etiqueta:" in b2 and "chico:" in b3
    assert cuenta == (2, 2)


def test_first_fit_decreasing_llena_los_huecos(tmp_path):
    """What the packing gained: in order, two blocks of more than half a bank
    and two of less ask for three banks, because the second big one jumps and
    the last small one no longer fits behind the first. From largest to
    smallest, two."""
    mitad = bancos.BANCO // 2
    texto = '.segment "RODATA"\n'
    for nombre, n in (("a", mitad + 16), ("b", mitad + 16),
                      ("c", mitad - 16), ("d", mitad - 16)):
        texto += ".bloque %d\n%s:\n" % (n, nombre) + bytes_(16) * (n // 16)
    (salida,), cuenta = resolver(texto, tmp_path)
    assert cuenta == (4, 2)
    b2, b3 = salida.split(B3)
    assert "a:" in b2 and "c:" in b2 and "b:" in b3 and "d:" in b3


def test_uno_de_mas_de_un_banco_arranca_banco_y_presta_lo_que_sobra(tmp_path):
    """The text block: it starts at a bank's `$8000` and continues in the
    next, as the sequential packing decided —it is walked by code that
    switches banks by hand—, and what is left over in its last bank is used
    by another."""
    texto = ('.segment "RODATA"\n.bloque 64\nchico:\n' + bytes_(16) * 4
             + ".bloque %d\ntextos:\n" % (bancos.BANCO + 32)
             + bytes_(16) * (bancos.BANCO // 16 + 2))
    (salida,), cuenta = resolver(texto, tmp_path)
    assert cuenta == (2, 2)
    b2, b3 = salida.split(B3)
    assert b2.split("\n")[1] == "textos:", "it has to start the bank"
    assert "chico:" in b3 and b3.index("chico:") > b3.index("$00")


def test_el_borde_justo_entra(tmp_path):
    (salida,), _ = resolver(
        '.segment "RODATA"\n.bloque %d\n' % bancos.BANCO, tmp_path)
    assert B3 not in salida


def test_un_banco_lleno_se_deja_antes_de_la_etiqueta(tmp_path):
    """A label at the end of a bank would point outside the ROM."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16)
        + "etiqueta:\n" + bytes_(1), tmp_path)
    assert salida.index(B3) < salida.index("etiqueta:")


def test_lo_que_no_entra_se_parte_entre_los_dos_bancos(tmp_path):
    """The cell grid: larger than a bank, contiguous in the file."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16 - 1)
        + bytes_(8) + "    .word $1111,$2222,$3333,$4444,$5555,$6666\n",
        tmp_path)
    antes, despues = salida.split(B3)
    assert "$1111, $2222, $3333, $4444" in antes
    assert "$5555, $6666" in despues and "$4444" not in despues


def test_una_palabra_no_se_parte(tmp_path):
    with pytest.raises(ValueError, match="middle of a"):
        resolver('.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16 - 1)
                 + bytes_(15) + "    .word $1111,$2222\n", tmp_path)


def test_lo_que_no_es_rodata_no_cuenta(tmp_path):
    """The bank 0 tables go through another area and do not shift the data."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16)
        + '.segment "TABLAS"\n' + bytes_(bancos.BANCO - 16)
        + '.segment "RODATA"\n'
        + ".bloque %d\n" % (bancos.BANCO - 16), tmp_path)
    assert B3 not in salida
    assert '.segment "TABLAS"' in salida


def test_los_bancos_van_al_final_del_ultimo_archivo(tmp_path):
    """To move the pieces they have to be taken out of their place: `ca65`
    fills a segment in text order. The constants stay where they were."""
    (primero, segundo), _ = resolver(
        '.segment "RODATA"\nCONSTANTE = 7\n.bloque 16\nuna:\n' + bytes_(16),
        tmp_path,
        segundo='.segment "RODATA"\n.bloque %d\notra:\n    .res %d\n'
        % ((bancos.BANCO - 8,) * 2))
    assert "BANK" not in primero and "una:" not in primero
    assert "CONSTANTE = 7" in primero
    assert B2 in segundo and B3 in segundo and "una:" in segundo


def test_lo_que_no_entra_en_el_cartucho_lo_dice(tmp_path):
    """Without this `ld65` complains, with an internal error that does not
    say space is short."""
    entran = bancos.BANCOS - bancos.BANCOS_RESERVADOS - bancos.PRIMER_BANCO
    texto = '.segment "RODATA"\n' + "".join(
        ".bloque %d\nb%d:\n    .res %d\n" % (bancos.BANCO, k, bancos.BANCO)
        for k in range(entran + 1))
    with pytest.raises(ValueError, match="needs %d banks and %d fit"
                       % (entran + 1, entran)):
        resolver(texto, tmp_path)


@pytest.mark.parametrize("linea,bytes_", [
    ("    .byte $00,$01,$02", 3),
    ("    .word $0000,$0001", 4),
    ("    .dword $00000000", 4),
    ("    .byte", 0),
    ("    .byte  ; sin nada", 0),
    ("    .byte $00,$01  ; dos, y una coma en el comentario", 2),
    ("etiqueta:", 0),
    ("CONSTANTE = 7", 0),
    ("; un comentario", 0),
    ("", 0),
    ("    .res 12", 12),
])
def test_cuánto_ocupa_cada_línea(linea, bytes_):
    assert bancos._tamano(linea) == bytes_


def test_alinear_no_se_toca_pero_se_cuenta(tmp_path):
    """`.align` belongs to `ca65`, so it survives the pass.

    What cannot happen is that it stops being counted: if its padding does
    not enter the count, every block below is packed against a shifted
    number.
    """
    (salida,), _ = resolver(
        '.segment "RODATA"\n'
        ".bloque %d\ngrande:\n    .res %d\n" % ((bancos.BANCO - 1,) * 2)
        + ".align 2\n.bloque 1\nalineada:\n    .byte $00\n", tmp_path)
    assert ".align 2" in salida
    # One byte is left, and with the alignment counted the one-byte one no
    # longer fits.
    assert salida.index(B3) < salida.index("alineada:")


def test_un_bloque_fuera_de_rodata_no_pasa_callado(tmp_path):
    """The case found while writing this: one in TABLAS.

    There the packing cannot be computed —the area depends on the size of the
    code, which the converter does not know— and it is not needed either,
    because TABLAS lives entirely inside bank 0. What it cannot do is slip
    through: the directive still exists for the two in `tools/runtime/`, so
    the assembler would accept it.
    """
    ruta = tmp_path / "tablas.inc"
    ruta.write_text('.segment "TABLAS"\n.bloque 12\n    .byte $00\n')
    with pytest.raises(ValueError, match="unresolved"):
        bancos.resolver([str(ruta)])


def test_una_tabla_sin_bloque_no_pasa_callada(tmp_path):
    """A table the ROM reads with `lda f:tabla, x` cannot cross a bank: the
    index carries the address to the next bank's `$0000`, which in LoROM is
    not ROM. Without `.bloque`, the packing splits it wherever the end of the
    bank falls, and if it falls between two words nothing complains: the ROM
    reads garbage for the last entries. That is how `actor_hpmax`,
    `actor_spmax` and some thirty more were until 2026-09-27, and it was
    uncovered by a variant of `release` with more maps, where the cut fell in
    the middle of a word.

    That is why the packing **always** refuses, not only on the day the cut
    lands on it: the error is latent, and depends on how much comes before it
    in RODATA.
    """
    with pytest.raises(ValueError, match="tabla_suelta"):
        resolver('.segment "RODATA"\n.bloque 4\ncubierta:\n'
                 "    .word $1111,$2222\n"
                 "tabla_suelta:\n    .word $3333,$4444\n", tmp_path)


def test_un_bloque_cubre_las_tablas_que_entran_en_él(tmp_path):
    """A `.bloque` that spans several tables covers them all, and a one-byte
    label cannot be split."""
    resolver('.segment "RODATA"\n.bloque 8\nuna:\n    .word 1,2\n'
             "otra:\n    .word 3,4\nsuelta:\n    .byte 5\n", tmp_path)


def test_lo_que_cruza_a_proposito_se_declara(tmp_path):
    """The music stream, the driver and the SPC700 samples do cross: they are
    walked by code that switches banks by hand. `.cruza` says so."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16 - 1)
        + ".cruza\nstream:\n" + bytes_(16) + bytes_(16), tmp_path)
    antes, despues = salida.split(B3)
    assert "stream:" in antes and ".cruza" not in salida
    # And the continuation goes first in the next bank, which is where
    # `spc_block` and `advance` look for it: at its `$8000`.
    assert despues.split("\n")[1].startswith("    .byte")


def test_lo_que_cruza_y_entra_entero_llena_un_hueco(tmp_path):
    """A small stream does not need to be split: if it fits in what is left of
    a bank, it goes there whole, and the chain of what crosses does not
    grow."""
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n.bloque %d\ngrande:\n    .res %d\n'
        % ((bancos.BANCO - 64,) * 2)
        + ".bloque %d\notro:\n    .res %d\n" % ((bancos.BANCO - 16,) * 2)
        + ".cruza\nstream:\n" + bytes_(16) * 3, tmp_path)
    assert cuenta == (3, 2)
    b2, b3 = salida.split(B3)
    assert "otro:" in b2 and "grande:" in b3 and "stream:" in b3


def test_el_mapa_de_memoria_pone_cada_banco_en_su_lugar():
    """What ties the `.cfg` to the packing: `BANKnn` starts at `$nn:8000`."""
    texto = bancos.cfg()
    assert "BANK01: start = $018000, size = $8000, fill = yes;" in texto
    assert "BANK7D: start = $7D8000, size = $8000, fill = yes;" in texto
    assert "BANK7E" not in texto, "banks $7E and $7F are the WRAM"
    assert "FAR:      load = BANK01" in texto
    assert "%s: load = %s" % ((bancos.segmento_de(bancos.PRIMER_BANCO),) * 2) in texto
    # The file has to be 4 MB: 126 data banks, plus bank 0 split into three
    # areas, plus the two reserved ones.
    tamanos = [int(t, 16) for t in re.findall(r"size = \$([0-9A-F]+), fill", texto)]
    assert sum(tamanos) == 4 * 1024 * 1024

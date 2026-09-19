"""El acomodo de bancos, que hace el conversor y ya no el ensamblador.

Lo que estas pruebas cuidan no es que el relleno sea lindo sino que sea **el
mismo** que decidía `.bloque`: un bloque que cruza de banco se sube por DMA
leyendo la WRAM de la mitad para adelante, y eso no falla al ensamblar, falla
dibujando basura. La red grande es que la ROM salga byte por byte igual; ésta
es la chica, y sirve para que un error se vea acá y no en un md5.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "tools"))

import bancos                                                # noqa: E402


def resolver(texto, tmp_path, segundo=None):
    """Corre el acomodo sobre uno o dos archivos y devuelve lo que quedó."""
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
    assert cuenta == (1, 0)


def test_un_bloque_que_no_entra_empieza_el_banco_siguiente(tmp_path):
    """El caso que da sentido a todo: 32 bytes libres y un bloque de más."""
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n' + bytes_(16)
        + ".bloque %d\netiqueta:\n" % (bancos.BANCO - 8), tmp_path)
    assert salida.index(B3) < salida.index("etiqueta:")
    assert cuenta == (1, 1)


def test_el_borde_justo_entra(tmp_path):
    (salida,), _ = resolver(
        '.segment "RODATA"\n.bloque %d\n' % bancos.BANCO, tmp_path)
    assert B3 not in salida


def test_un_banco_lleno_se_deja_antes_de_la_etiqueta(tmp_path):
    """Una etiqueta en el final de un banco apuntaría afuera de la ROM."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16)
        + "etiqueta:\n" + bytes_(1), tmp_path)
    assert salida.index(B3) < salida.index("etiqueta:")


def test_lo_que_no_entra_se_parte_entre_los_dos_bancos(tmp_path):
    """La grilla de celdas: más grande que un banco, contigua en el archivo."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16 - 1)
        + bytes_(8) + "    .word $1111,$2222,$3333,$4444,$5555,$6666\n",
        tmp_path)
    antes, despues = salida.split(B3)
    assert "$1111, $2222, $3333, $4444" in antes
    assert "$5555, $6666" in despues and "$4444" not in despues


def test_una_palabra_no_se_parte(tmp_path):
    with pytest.raises(ValueError, match="medio de un operando"):
        resolver('.segment "RODATA"\n' + bytes_(16) * (bancos.BANCO // 16 - 1)
                 + bytes_(15) + "    .word $1111,$2222\n", tmp_path)


def test_lo_que_no_es_rodata_no_cuenta(tmp_path):
    """Las tablas del banco 0 van por otra área y no corren a los datos."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16)
        + '.segment "TABLAS"\n' + bytes_(bancos.BANCO - 16)
        + '.segment "RODATA"\n'
        + ".bloque %d\n" % (bancos.BANCO - 16), tmp_path)
    assert B3 not in salida
    assert '.segment "TABLAS"' in salida


def test_el_segundo_archivo_sigue_donde_terminó_el_primero(tmp_path):
    (_, segundo), _ = resolver(
        '.segment "RODATA"\n' + bytes_(16), tmp_path,
        segundo='.segment "RODATA"\n.bloque %d\n' % (bancos.BANCO - 8))
    assert B3 in segundo


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
    """`.align` es de `ca65`, así que sobrevive al paso.

    Lo que no puede pasar es que deje de contarse: si su relleno no entra en la
    cuenta, todos los bloques de abajo se acomodan contra un número corrido.
    """
    (salida,), _ = resolver(
        '.segment "RODATA"\n'
        "    .byte $00\n"
        ".align 2\n"
        + ".bloque %d\n" % (bancos.BANCO - 1), tmp_path)
    assert ".align 2" in salida
    # Con la alineación contada van dos bytes, y lo que sigue ya no entra.
    assert B3 in salida


def test_un_bloque_fuera_de_rodata_no_pasa_callado(tmp_path):
    """El caso que se descubrió al escribir esto: uno en TABLAS.

    Ahí el acomodo no se puede calcular —el área depende del tamaño del código,
    que el conversor no conoce— y tampoco hace falta, porque TABLAS vive entera
    adentro del banco 0. Lo que no puede es colarse: la directiva todavía
    existe para los dos de `main.s`, así que el ensamblador lo aceptaría.
    """
    ruta = tmp_path / "tablas.inc"
    ruta.write_text('.segment "TABLAS"\n.bloque 12\n    .byte $00\n')
    with pytest.raises(ValueError, match="sin resolver"):
        bancos.resolver([str(ruta)])


def test_el_codigo_a_mano_entra_en_el_banco_1():
    """`FAR` va entero en el banco 1, y lo generado arranca pegado al 2.

    El ensamblador no puede cuidarlo: `.controlar` se evalúa antes de que haya
    direcciones. Si el código a mano de `main.s` pasara de 32 KB, el
    `.alinear $8000` del final empujaría lo generado al banco 3 sin decir nada,
    y los `jsr` que cruzaran del 1 al 2 saltarían a cualquier lado. Así que se
    mira el resultado: **lo primero que hay pasando el banco 1 tiene que estar
    en `$02:8000` justo**. Si `FAR` se pasa, lo primero es una etiqueta suya a
    mitad del banco 2; si lo generado arranca más lejos, no hay nada en
    `$02:8000`.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "arnes"))
    import tanda
    simbolos = tanda.cartucho().simbolos
    rom = [int(v) for v in simbolos.tabla.values()
           if 0x028000 <= int(v) < 0x7E0000]
    assert min(rom) == 0x028000, "lo primero pasando el banco 1 está en $%06X" % min(rom)


def test_el_mapa_de_memoria_pone_cada_banco_en_su_lugar():
    """Lo que ata el `.cfg` al reparto: `BANKnn` arranca en `$nn:8000`."""
    texto = bancos.cfg()
    assert "BANK01: start = $018000, size = $8000, fill = yes;" in texto
    assert "BANK7D: start = $7D8000, size = $8000, fill = yes;" in texto
    assert "BANK7E" not in texto, "los bancos $7E y $7F son la WRAM"
    assert "FAR:      load = BANK01" in texto
    assert "%s: load = %s" % ((bancos.segmento_de(bancos.PRIMER_BANCO),) * 2) in texto
    # El archivo tiene que medir 4 MB: 126 bancos de datos, más el 0 partido
    # en tres áreas, más los dos reservados.
    tamanos = [int(t, 16) for t in re.findall(r"size = \$([0-9A-F]+), fill", texto)]
    assert sum(tamanos) == 4 * 1024 * 1024

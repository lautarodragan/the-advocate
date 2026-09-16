"""El acomodo de bancos, que hace el conversor y ya no el ensamblador.

Lo que estas pruebas cuidan no es que el relleno sea lindo sino que sea **el
mismo** que decidía `.bloque`: un bloque que cruza de banco se sube por DMA
leyendo la WRAM de la mitad para adelante, y eso no falla al ensamblar, falla
dibujando basura. La red grande es que la ROM salga byte por byte igual; ésta
es la chica, y sirve para que un error se vea acá y no en un md5.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))

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


def test_un_bloque_que_entra_no_deja_relleno(tmp_path):
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n.bloque 16\n    .byte $00\n', tmp_path)
    assert ".res" not in salida
    assert cuenta == (1, 0)


def test_un_bloque_que_no_entra_rellena_hasta_el_banco(tmp_path):
    """El caso que da sentido a todo: 32 bytes libres y un bloque de 64."""
    (salida,), cuenta = resolver(
        '.segment "RODATA"\n'
        + "    .byte " + ",".join(["$00"] * 16) + "\n" * 1
        + ".bloque %d\n" % (bancos.BANCO - 8), tmp_path)
    assert ".res %d" % (bancos.BANCO - 16) in salida
    assert cuenta == (1, 1)


def test_el_relleno_se_mide_desde_el_arranque_del_banco(tmp_path):
    """Exactamente en el borde no hay que rellenar: entra justo."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n.bloque %d\n' % bancos.BANCO, tmp_path)
    assert ".res" not in salida


def test_lo_que_no_es_rodata_no_mueve_el_offset(tmp_path):
    """Las tablas del banco 0 van por otra área y no corren a los datos."""
    (salida,), _ = resolver(
        '.segment "RODATA"\n'
        + "    .byte " + ",".join(["$00"] * 16) + "\n"
        + '.segment "TABLAS"\n'
        + "    .byte " + ",".join(["$00"] * (bancos.BANCO - 16)) + "\n"
        + '.segment "RODATA"\n'
        + ".bloque %d\n" % (bancos.BANCO - 8), tmp_path)
    # Si las tablas contaran, acá ya no entraría y habría relleno.
    assert ".res %d" % (bancos.BANCO - 16) in salida


def test_el_segundo_archivo_sigue_donde_terminó_el_primero(tmp_path):
    """El acomodo depende de todo lo anterior: por eso van en orden."""
    (_, segundo), _ = resolver(
        '.segment "RODATA"\n'
        + "    .byte " + ",".join(["$00"] * 16) + "\n",
        tmp_path,
        segundo='.segment "RODATA"\n.bloque %d\n' % (bancos.BANCO - 8))
    assert ".res %d" % (bancos.BANCO - 16) in segundo


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

    Lo que no puede pasar es que deje de contarse: si su relleno no entra en el
    offset, todos los bloques de abajo se acomodan contra un número corrido.
    """
    (salida,), _ = resolver(
        '.segment "RODATA"\n'
        "    .byte $00\n"
        ".align 2\n"
        + ".bloque %d\n" % (bancos.BANCO - 1), tmp_path)
    assert ".align 2" in salida
    # Con la alineación contada van dos bytes, y lo que sigue ya no entra.
    assert ".res %d" % (bancos.BANCO - 2) in salida


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
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import consola
    _sfc, simbolos, _mapas = consola.armar(7)
    rom = [int(v) for v in simbolos.tabla.values()
           if 0x028000 <= int(v) < 0x7E0000]
    assert min(rom) == 0x028000, "lo primero pasando el banco 1 está en $%06X" % min(rom)

"""El acomodo de bancos, sobre el cartucho armado.

Cómo acomoda el conversor los bloques de datos se prueba con archivos armados
a mano, en las pruebas de las herramientas. Lo que queda acá es lo que sólo se
ve con la ROM linkeada: dónde terminó el código a mano.
"""

import tanda


def test_el_codigo_a_mano_entra_en_el_banco_1_y_lo_generado_en_los_suyos():
    """`FAR` va entero en el banco 1, y lo generado arranca en el primer banco
    del reparto, `$C2:0000`.

    El ensamblador no puede cuidarlo: `.assert` se evalúa antes de que haya
    direcciones. En LoROM, si el código a mano de `runtime/` pasaba de 32 KB,
    el `.align $8000` del final empujaba lo generado al banco siguiente sin
    decir nada. En ExHiROM cada uno tiene su área en el `.cfg` y `ld65` se
    queja, pero lo que se mira es el resultado: **ninguna etiqueta del código
    a mano pasa de `$01:FFFF`, y lo primero de lo generado está en
    `$C2:0000` justo**.
    """
    simbolos = tanda.cartucho().simbolos
    valores = [int(v) for v in simbolos.tabla.values()]
    banco1 = [v for v in valores if 0x018000 <= v < 0x020000]
    assert banco1, "no hay nada en el banco 1"
    generado = [v for v in valores if 0xC00000 <= v <= 0xFFFFFF]
    assert min(generado) == 0xC20000, (
        "lo primero de lo generado está en $%06X" % min(generado))

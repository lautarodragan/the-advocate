"""El acomodo de bancos, sobre el cartucho armado.

Cómo acomoda el conversor los bloques de datos se prueba con archivos armados
a mano, en las pruebas de las herramientas. Lo que queda acá es lo que sólo se
ve con la ROM linkeada: dónde terminó el código a mano.
"""

import tanda


def test_el_codigo_a_mano_entra_en_el_banco_1():
    """`FAR` va entero en el banco 1, y lo generado arranca pegado al 2.

    El ensamblador no puede cuidarlo: `.controlar` se evalúa antes de que haya
    direcciones. Si el código a mano de `rom/src/` pasara de 32 KB, el
    `.alinear $8000` del final empujaría lo generado al banco 3 sin decir nada,
    y los `jsr` que cruzaran del 1 al 2 saltarían a cualquier lado. Así que se
    mira el resultado: **lo primero que hay pasando el banco 1 tiene que estar
    en `$02:8000` justo**. Si `FAR` se pasa, lo primero es una etiqueta suya a
    mitad del banco 2; si lo generado arranca más lejos, no hay nada en
    `$02:8000`.
    """
    simbolos = tanda.cartucho().simbolos
    rom = [int(v) for v in simbolos.tabla.values()
           if 0x028000 <= int(v) < 0x7E0000]
    assert min(rom) == 0x028000, "lo primero pasando el banco 1 está en $%06X" % min(rom)

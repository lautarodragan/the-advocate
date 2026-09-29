"""Lo que el capítulo usa de la guarida de Boss Wick: cómo leer las
transiciones de pantalla que la ROM guarda.

Vivía en `abl/test_recorrido_lashe_wick_golden.py` hasta el 2026-09-29.
"""

from consola import en_la_wram

# Lo que la ROM guarda de `ChangeScreenTransitions`: ver `transicion_poner`.
MOSAICO = 1
FUNDIDO = 0


def transiciones(p):
    borrar, mostrar = (p.consola.ram(en_la_wram(p.simbolos[n]), 1)[0]
                       for n in ("TRANSICION_BORRAR", "TRANSICION_MOSTRAR"))
    return borrar, mostrar

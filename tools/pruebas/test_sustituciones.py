"""El tope de la tabla de `TileSubstitution` está escrito de los dos lados.

Y tiene que estarlo: la ROM **no puede avisar** que se le pasó —los pares que
no entren simplemente no se aplicarían, y el mapa dibujaría de más sin que
nada lo diga—, así que quien se niega a emitir un mapa que no entre es el
conversor. Eso son dos números, y dos números escritos en dos lados es de lo
que este repo ya se quemó con los opcodes; acá no se puede generar uno del
otro —el `.res` de la BSS y el corte del conversor no comparten nada— así que
lo que queda es compararlos.
"""

import os
import re

from port import snes_convert                            # noqa: E402
from comun import proyecto  # noqa: E402
from ensamblado import ensamblar  # noqa: E402

MAIN = os.path.join(proyecto.runtime(), "main.s")


def de_main(nombre):
    fuente = ensamblar.texto_de_la_fuente(MAIN)
    hallado = re.search(r"^%s\s*=\s*(\d+)\s*$" % nombre, fuente, re.M)
    assert hallado, "rom/src/ ya no declara %s" % nombre
    return int(hallado.group(1))


def reserva(nombre):
    fuente = ensamblar.texto_de_la_fuente(MAIN)
    hallado = re.search(r"^%s:\s*\.res\s+([^;\n]+)" % nombre, fuente, re.M)
    assert hallado, "rom/src/ ya no reserva %s" % nombre
    return hallado.group(1).strip()


def test_el_tope_de_la_tabla_es_el_mismo_de_los_dos_lados():
    assert de_main("SUB_MAX") == snes_convert.SUB_MAX


def test_la_tabla_de_la_rom_mide_lo_que_dice_el_tope():
    """Dos palabras por par, claves y valores en arreglos paralelos: así los
    recorre `celda_sustituida` con un solo índice."""
    assert reserva("sub_clave") == "SUB_MAX * 2"
    assert reserva("sub_valor") == "SUB_MAX * 2"

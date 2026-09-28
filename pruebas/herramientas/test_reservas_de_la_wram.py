"""La mitad alta de los dos bancos de la WRAM es de la grilla, del buffer de
carga y de la escena de la pelea, y de nadie más.

`$7E8000-$7EFFFF` se reservó para la grilla del mapa el 2026-09-26, sabiendo
que era la mitad de la RAM lejana que quedaba libre y que quizás haya que
revertirlo: ver `workflow/decisiones/la-grilla-vive-en-la-wram.md`. Esta
prueba es la alarma de esa decisión: **falla si un símbolo nuevo cae adentro
de esos rangos**, que es lo que haría quien necesite RAM lejana y no sepa que
ahí vive la grilla. Si falla, no es para agregar el símbolo a la lista: es
para leer la decisión.

Mira la tabla de símbolos del cartucho armado, que tiene las constantes del
ensamblador con su banco. Lo que no ve: una dirección escrita de dieciséis
bits y usada con el banco de datos en `$7E` —como `FAR_BATALLA`—, que en la
tabla es un número chico. Para ésas queda `test_carga_descomprimida.py`, que
compara la grilla entera en cada carga y a la vuelta de una pelea.
"""

import pytest

import tanda
from ensamblado import cartuchos

# Cada rango con los símbolos que tienen derecho a caer adentro.
RESERVAS = (
    ((0x7E8000, 0x7F0000), {"GRILLA"}),
    ((0x7F0000, 0x800000), {"GRILLA_FIN", "GRILLA_ALTA", "LZ2_BUFFER",
                            "ANIM_DIBUJOS", "ANIM_DIBUJOS_FIN",
                            "ESC_LIMPIO", "ESC_ESCENA",
                            # La pantalla de Game Over: pisa el banco entero,
                            # grilla incluida, porque de ahí no se vuelve al
                            # mapa sino al arranque. Ver rom/src/game_over.s.
                            "PANTALLA_BUFFER"}),
)


@pytest.mark.parametrize("nombre", sorted(cartuchos.CARTUCHOS))
def test_nadie_mas_cae_en_la_mitad_alta_de_la_wram(nombre):
    tabla = {n: int(v) for n, v in tanda.cartucho(nombre).simbolos.tabla.items()}
    intrusos = []
    for (desde, hasta), permitidos in RESERVAS:
        intrusos += ["%s = $%06X" % (simbolo, valor)
                     for simbolo, valor in sorted(tabla.items())
                     if desde <= valor < hasta and simbolo not in permitidos]
    assert not intrusos, (
        "estos símbolos caen en la mitad alta de la WRAM, que es de la grilla "
        "y de la pelea: %s. Ver workflow/decisiones/la-grilla-vive-en-la-wram.md"
        % ", ".join(intrusos))


def test_los_permitidos_existen():
    # Si uno se renombra, la lista de arriba dejaría pasar a su reemplazo.
    tabla = tanda.cartucho(cartuchos.RELEASE).simbolos.tabla
    faltan = sorted(n for _, permitidos in RESERVAS for n in permitidos
                    if n not in tabla)
    assert not faltan, "la tabla de símbolos no tiene %s" % faltan

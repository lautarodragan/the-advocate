"""El salto del héroe dura lo que dice su velocidad, como el de los eventos.

En RM2k lo que baja el arco por cuadro es `jump_speed[move_speed - 1]` —8, 12,
16, 24, 32, 64 sobre los 256 de una celda— y `Game_Character::Update` lo lee
con la velocidad de ese cuadro. Así que un salto dura `ceil(256 / s)` cuadros
contando el del aterrizaje, y `remaining_step` es distinto de cero en todos
menos en ése: el primer descuento cae en el mismo cuadro que arma el salto.

Hasta el 2026-09-26 el héroe usaba una constante, la de la velocidad 4, y los
eventos ya la sacaban de `salto_por_vel`: con `increase_movement_speed` delante
el héroe caminaba a la velocidad nueva y saltaba en los once cuadros de
siempre. Lo que se cuenta acá son los ticks con `ruta_salto` distinto de cero.
"""

import pytest

from port import events


def cuadros_en_el_aire(una, tope=200):
    """Los ticks seguidos con `ruta_salto` distinto de cero, desde el primero."""
    en_el_aire = 0
    for _ in range(tope):
        una.correr(1)
        if una.byte("ruta_salto"):
            en_el_aire += 1
        elif en_el_aire:
            return en_el_aire
    raise AssertionError(
        "en %d ticks el héroe %s" % (
            tope, "no aterrizó" if en_el_aire
            else "nunca saltó: el caso dejó de reproducir"))


@pytest.mark.parametrize("caso, velocidad", [
    ("salto-heroe-lento", 1),
    ("salto", 4),
    ("salto-heroe-veloz", 6),
])
def test_el_salto_del_heroe_dura_lo_que_dice_su_velocidad(partida, caso,
                                                         velocidad):
    una = partida(caso=caso)
    dura = cuadros_en_el_aire(una)
    assert una.velocidad_del_heroe() == velocidad, \
        "la ruta dejó al héroe a velocidad %d" % una.velocidad_del_heroe()
    s = events.JUMP_PER_SPEED[velocidad - 1]
    esperado = -(-events.JUMP_STEP // s) - 1
    assert dura == esperado, (
        "a velocidad %d el salto baja %d por cuadro y en RM2k está %d ticks en "
        "el aire; acá estuvo %d" % (velocidad, s, esperado, dura))
    assert una.palabra("hero_x") == una.palabra("tile_x") * 16, \
        "aterrizó a medias: hero_x = %d con tile_x = %d" % (
            una.palabra("hero_x"), una.palabra("tile_x"))

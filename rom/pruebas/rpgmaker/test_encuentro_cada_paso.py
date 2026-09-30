"""Un mapa con `encounter_steps` 1: un encuentro en cada paso.

Ningún mapa del juego tiene 1, y hasta el 2026-09-29 un cartucho con
`--test-encounters 1` no ensamblaba: `1 / 1` en 1/65536 es 65536, que no entra
en la palabra de `ENC_BASE`. Desde ese día satura en 65535 —ver `base` en
`rm2k-snes-battle`—, y la pregunta es si sigue siendo "siempre", que es lo
que hace RM2k: en `Game_Player::UpdateEncounterSteps` el primer paso ya da
`ratio` 100, la fila 4, cuyo `pmod` es 2, así que la chance es 2 y
`PercentChance` dice que sí. En la consola es el acarreo de `$FFFF << 1`.

El cartucho es `test-encounter-every-step`: el mapa 21 y el grupo de la
intro del encuentro de `test-special` —el caso `encuentro-cada-paso` es una
copia de `grupo-11-12-13`—, que ahí sale en el paso 8 —lo fija
`test_batalla_golden.PASO_DEL_ENCUENTRO`—. Acá tiene que salir en el primero.
"""

from tanda import partida

CARTUCHO = "test-encounter-every-step"
# Adónde lleva el caso: (21, 25, 25).
LLEGADA_Y = 25
# Medido el 2026-09-29: el encuentro queda pedido en el primer cuadro del
# paso, se cobra en el noveno y la pelea se abre —`menu_open`— en el 173,
# después de la transición. Mientras tanto el héroe no camina más aunque se
# siga apretando, así que la fila donde queda dice en qué paso salió.
TOPE = 400


def test_el_primer_paso_es_una_pelea():
    p = partida("encuentro-cada-paso", en=CARTUCHO)
    assert p.mapa() == 21, p.mapa()
    assert p.palabra("tile_y") == LLEGADA_Y, p.palabra("tile_y")
    for cuadro in range(TOPE):
        if p.byte("menu_open"):
            break
        p.consola.hold("up")
        p.consola.run(1)
    else:
        raise AssertionError(
            "con encounter_steps 1 no salió ningún encuentro en %d cuadros "
            "caminando para arriba: tendría que salir en el primer paso"
            % TOPE)
    p.consola.hold()
    pasos = LLEGADA_Y - p.palabra("tile_y")
    assert pasos == 1, (
        "el encuentro salió después de %d paso(s), en el cuadro %d; con "
        "encounter_steps 1 sale en el primero" % (pasos, cuadro))

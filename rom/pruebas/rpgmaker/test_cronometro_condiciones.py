"""Las dos preguntas por el cronómetro: la rama y la condición de página.

Las dos son de Tangle Forest, y son las únicas del juego: el 312 —el bosque
en llamas— tiene una rama de cronómetro en el evento 10, la salida, y una
condición de página en el 81, el que da Game Over cuando el fuego alcanza a
Talan. Se prueban con esas páginas, que es lo que importa que corra: la tabla
de páginas de prueba de `release` está llena —el número de página es un byte,
y hay 256—, así que un caso nuevo no entra. Ver
`workflow/tasks/*/mundo-5-tangle-forest.md`.

**La rama** es `CommandConditionalBranch`, caso 2, en easyrpg: los segundos
del cronómetro —`GetTimerSeconds`, los cuadros sobre 60— contra el operando,
con `>=` si `parameters[2]` es 0 y `<=` si es 1. La del 312 pide `>= 0`, que
vale siempre: el `else` del Game Over no corre nunca, y lo que importa es que
la página compile y saque del bosque. La comparación es la misma que la del
oro, con otro valor, y sus dos sentidos los cobra `test_oro.py`.

**La condición de página** es `Game_Event::AreConditionsMet`: la página vale
mientras los segundos sean **a lo sumo** `timer_sec`. Y en RM2k el cambio de
segundo pide un refresco —`Game_Party::UpdateTimers`, `SetNeedRefresh`—, así
que la página se activa sola cuando el cronómetro baja. La prueba pone el
cronómetro en 6 y salta al 312: la página del 81 pide 1, así que tiene que
quedarse quieta mientras quedan 2 o más, y correr cuando queda 1.
"""

TANGLE_EN_LLAMAS = 312
EL_TRAM = 313
# El evento 81 del 312 es el índice 80 de su tabla: el mapa no lleva el evento
# vacío de las páginas de prueba, que va en el mapa de arranque.
FUEGO = 80
# Lo que prende la salida del bosque, el evento 10, en (30, 52).
SALIO = 845


def poner_el_cronometro(una, segundos):
    """El cronómetro corriendo, como lo deja `TimerOperation`."""
    una.consola.write_ram(una.simbolos["timer_sec"], [segundos & 0xFF, segundos >> 8])
    una.consola.write_ram(una.simbolos["timer_sub"], [59])
    una.consola.write_ram(una.simbolos["timer_active"], [1])


def test_la_rama_del_cronometro_saca_del_bosque(partida):
    una = partida()
    poner_el_cronometro(una, 100)
    # Desde el costado: por abajo y por arriba hay fuego.
    una.ir_al_mapa(TANGLE_EN_LLAMAS, 29, 52)
    una.sostener(20, "right")
    for _ in range(600):
        if una.mapa() == EL_TRAM:
            break
        if una.byte("msg_open"):
            una.tocar_ticks("a")
        una.correr(1)
    assert una.switch(SALIO), (
        "la salida del bosque no corrió: la rama del cronómetro no compiló")
    assert una.mapa() == EL_TRAM, "la salida no llevó al tram"
    assert not una.byte("timer_active"), "la salida no paró el cronómetro"


def test_la_pagina_del_cronometro_espera_al_segundo(partida):
    una = partida()
    poner_el_cronometro(una, 6)
    una.ir_al_mapa(TANGLE_EN_LLAMAS, 11, 53, cuadros=40)
    assert una.mapa() == TANGLE_EN_LLAMAS
    # Mientras quedan dos segundos o más, la página no vale.
    for _ in range(600):
        if una.palabra("timer_sec") <= 1:
            break
        assert not (una.corriendo_una_pagina()
                    and una.palabra("ev_running") == FUEGO), (
            "la página del fuego corrió con %d segundos, y pide 1 o menos"
            % una.palabra("timer_sec"))
        una.correr(1)
    else:
        raise AssertionError("el cronómetro no bajó a 1")
    # Y en cuanto queda uno, corre: el cambio de segundo pidió el refresco.
    for _ in range(10):
        una.correr(1)
        if una.corriendo_una_pagina() and una.palabra("ev_running") == FUEGO:
            return
    raise AssertionError(
        "el cronómetro llegó a 1 y la página del fuego no corrió: o el evento "
        "quedó afuera de la tabla, o el cambio de segundo no pidió el refresco")

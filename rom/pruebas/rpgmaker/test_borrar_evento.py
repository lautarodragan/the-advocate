"""`EraseEvent` después de un `Teleport`: no hace nada, y la página sigue.

Es el del 311, el claro de Tangle Forest: la página automática del evento 4
—con el switch 840, que prende el tram del 313— tira las latas de fuego,
salta al 312 y sigue corriendo ahí: los mensajes de Talan, las ramas por
quién lo acompaña, el `EraseEvent` y el cronómetro de dos minutos. Pero en
easyrpg el salto le pone 0 al evento de cada cuadro de la pila
—`Game_Interpreter_Map::OnMapChange`—, y `CommandEraseEvent` con el evento
en 0 devuelve sin hacer nada: no hay a quién borrar. Así que compila a nada,
y lo que la prueba cobra es que la página compile y llegue hasta el final,
que arranca el cronómetro en el 312.

Un `EraseEvent` antes del salto, que sí borra, sigue sin compilar: el único
otro del juego es el del mapa 150, que no está en ningún cartucho.
"""

EL_CLARO = 311
TANGLE_EN_LLAMAS = 312
TRAM_ARRIBA = 840


def test_borrar_despues_del_salto_no_frena_la_pagina(partida):
    una = partida(switch=[TRAM_ARRIBA])
    una.ir_al_mapa(EL_CLARO, 6, 9)
    for _ in range(3000):
        if una.mapa() == TANGLE_EN_LLAMAS and una.byte("timer_active") \
                and not una.corriendo_una_pagina():
            break
        if una.byte("msg_open"):
            una.tocar_ticks("a")
        una.correr(1)
    assert una.mapa() == TANGLE_EN_LLAMAS, (
        "la página del claro no saltó al 312: no compiló")
    assert una.byte("timer_active"), (
        "la página no llegó al cronómetro, que va después del `EraseEvent`")
    assert 100 <= una.palabra("timer_sec") <= 120, (
        "el cronómetro no quedó en los dos minutos que pone la página: %d"
        % una.palabra("timer_sec"))

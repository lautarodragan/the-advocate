"""Un `CallEvent` de una página del mapa a un cuerpo compartido, y un
`Teleport` en el medio.

La página `llamada-acarreada` llama al común 43, *ChangeEmily'sTape* —un
mensaje y una elección, sin nada del mapa—, y después prende el 753. El común
no se pega en la página: es un `OP_CALL` a su cuerpo, que vive en el
cartucho, y la página que llamó queda abajo en la pila de llamadas, con su
puntero al bytecode del mapa en la WRAM.

Con la elección abierta, la prueba pide un salto a otro mapa como lo pediría
una paralela. Dos veces: con la página en el bytecode de su mapa —la de
`llamada-acarreada-en-casa`, que corre en el mapa de arranque—, y con la
página ya acarreada de un salto anterior —`llamada-acarreada`, que como
todas las páginas de prueba empieza saltando al mapa 5—: el marco se muda en
la primera y se queda donde está en la segunda, y en las dos el mapa que se
acarrea es el suyo. El bytecode del mapa nuevo cae donde estaba el de la página que
llamó, así que `code_carry_before` tiene que mudar **también los marcos de la
pila** a `CODE_CARRY`, no sólo el cursor de arriba —que está en el cartucho y
no se mueve—. Elegida la cinta, el común vuelve y la página tiene que seguir:
el 753 prendido.

Ningún común del juego que se comparta hoy salta de mapa —los que saltan,
16, 32, 36, 42 y 44, no compilan como cuerpo compartido—, así que el salto
se pide desde afuera: es el único camino que lo ejecuta.

En rojo, sin mirar los marcos de la pila: la vuelta lee el bytecode del
mapa nuevo, y el 753 no se prende.
"""

import pytest

from consola import en_la_wram

FIN = 753
CINTA = 806         # el que prende la primera opción, Workout Tape
MAPA_NUEVO = 2


@pytest.mark.parametrize("caso", ["llamada-acarreada-en-casa",
                                  "llamada-acarreada"])
def test_la_pagina_que_llamo_sigue_despues_del_salto(partida, caso):
    una = partida(caso=caso)
    s = una.simbolos
    for _ in range(200):
        if una.byte("pick_active"):
            break
        if una.byte("msg_open"):
            una.tocar_ticks("a")
        else:
            una.correr(1)
    assert una.byte("pick_active"), "la elección del común 43 no se abrió"
    profundidad = una.consola.ram(en_la_wram(s["CALL_DEPTH"]), 1)[0]
    assert profundidad == 1, (
        "la página tenía que llamar al común 43, no pegarlo: la pila tiene %d"
        % profundidad)
    # El salto, como lo deja `OP_TELEPORT` en una paralela.
    indice = una.mapas.index(MAPA_NUEVO)
    for nombre, valor in (("jump_map", indice), ("jump_x", 10),
                          ("jump_y", 10)):
        una.consola.write_ram(s[nombre], [valor & 0xFF, valor >> 8])
    una.consola.write_ram(s["jump_has"], [1])
    una.correr(120)
    assert una.mapa() == MAPA_NUEVO, "el salto no se hizo"
    marco = una.consola.ram(en_la_wram(s["CALL_STACK"]), 3)
    direccion = (marco[2] << 16) | (marco[1] << 8) | marco[0]
    assert (s["CODE_CARRY"] <= direccion
            < s["CODE_CARRY"] + s["LZ2_CAP_CODE"]), (
        "el marco de la página que llamó no se mudó a CODE_CARRY: $%06X"
        % direccion)
    for _ in range(200):
        if not una.corriendo_una_pagina():
            break
        if una.byte("pick_active") or una.byte("msg_open"):
            una.tocar_ticks("a")
        else:
            una.correr(1)
    assert una.switch(CINTA), "la elección no corrió"
    assert una.switch(FIN), (
        "la página que llamó no siguió después del salto: el 753 no se prendió")

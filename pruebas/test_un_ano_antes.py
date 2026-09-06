"""La secuencia del "1 year earlier": el recuerdo termina y el juego sigue.

El final del recuerdo de CORE y MANTA prende el switch 21 y salta al mapa 4. Ahí
lo espera el evento 1, página 3, que es donde la historia continuaba y se
cortaba: da siete objetos, funde la música, tiñe a negro, arranca `hzstream`,
muestra el cartel de "One year previous" y teletransporta al mapa 7 —Talan's
Pad—.

De todos esos comandos, los únicos que la frenaban eran `ChangeItems` y los tres
de `Picture`. Se aceptan sin hacerlos, así que lo que se pierde es el cartel
—la pantalla ya está en negro cuando aparece— y el inventario, que todavía no
lo lee nadie: no hay menú, y `ConditionalBranch` sólo mira switches.

Lo que esta prueba mira es lo que sí tiene que pasar: que la página corra y el
juego llegue a Talan's Pad. Nada de eso se ve en una pantalla comparada contra
la referencia, porque los dos lados estarían igual de negros.
"""

# La escena dura más de lo que parece: los `Wait` de RM2k son décimas de
# segundo, y ésta suma 105 —diez segundos y medio—. Prende el switch 23 en el
# cuadro 635 y aterriza en el 659; 900 deja margen sin ser una eternidad.
CUADROS = 900

MAPA = 4          # 'Blank (Leave START here)', donde aterriza el recuerdo
DESTINO = 7       # Talan's Pad
SI = 21           # el switch que el final del recuerdo prende
DESPUES = 23      # el que la página prende antes de teletransportar


def test_la_pagina_del_ano_antes_corre(partida):
    una = partida()
    una.ir_al_mapa(MAPA, 9, 9)      # donde la escena de Talan deja al héroe
    una.prender(SI)
    una.correr(CUADROS)
    assert una.switch(DESPUES), \
        "la página no llegó al final: o no compiló, o se trabó en el camino"


def test_el_juego_llega_al_pad_de_talan(partida):
    una = partida()
    una.ir_al_mapa(MAPA, 9, 9)      # donde la escena de Talan deja al héroe
    una.prender(SI)
    una.correr(CUADROS)
    assert una.mapa() == DESTINO

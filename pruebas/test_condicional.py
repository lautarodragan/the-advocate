"""`ConditionalBranch`: la rama que corre y la que se saltea.

Hacen falta las dos mitades, y se prueban en lugares distintos por una razón de
orden que conviene tener presente.

**La rama que se saltea** se prueba con una página del juego, que es lo que
importa: que el dato real compile y corra. El banco es el mapa 66, evento 1,
página 1, de las más chicas que lo usan:

    MoveEvent   (el héroe)
    if switch 162:
        switch 239 <- prendido
    else:
    end
    switch 237 <- prendido

Son dos cosas distintas: que la rama no corra, y que la página **siga después
del `end`**. Una implementación que saltee de más deja el 237 apagado, y eso no
se ve en ninguna pantalla: los dos switches son invisibles.

**La rama que corre** no se puede probar con una página del juego. Ninguna de
las que usan `ConditionalBranch` prende antes el switch que la decide —todas
leen uno que viene de otra parte— y `--switch` lo prende desde la página de
prueba, que corre **después** de las del mapa: su evento es el último de la
tabla, y el barrido va de menor a mayor. Cuando la página del mapa 66 pregunta
por el 162, el 162 todavía no está.

Así que esa mitad va sobre una rama en la página de prueba, que prende el switch
arriba y ramifica abajo, en la misma página: ahí el orden es nuestro. El
bytecode que sale es el mismo que emite `compilar_pagina` para una página del
juego, byte por byte.
"""

MAPA = 66
SI = 162          # el switch que decide la rama, y que acá nunca llega a tiempo
ADENTRO = 239     # lo que prende la rama que se saltea
DESPUES = 237     # lo que prende la página después del `end`, siempre

# (el switch que decide, el de adentro, el de después) para `--rama-de-prueba`.
RAMA = (300, 301, 302)


def test_la_pagina_del_juego_sigue_despues_del_end(partida):
    """Con la rama salteada, la página tiene que llegar igual al final."""
    una = partida(map_id=MAPA, con_ventana=False)
    una.correr(120)
    assert una.switch(DESPUES), \
        "la página no llegó al final: o no compiló, o el salto se pasó de largo"


def test_la_rama_del_juego_se_saltea(partida):
    una = partida(map_id=MAPA, con_ventana=False)
    una.correr(120)
    assert not una.switch(ADENTRO), \
        "corrió la rama de adentro con el switch apagado"


def test_la_rama_corre_con_el_switch_prendido(partida):
    una = partida(map_id=MAPA, switch=[RAMA[0]], rama=RAMA, con_ventana=False)
    una.correr(120)
    assert una.switch(RAMA[1]), "no corrió la rama de adentro"
    assert una.switch(RAMA[2]), "la página no siguió después del `end`"


def test_la_rama_no_corre_con_el_switch_apagado(partida):
    una = partida(map_id=MAPA, rama=RAMA, con_ventana=False)
    una.correr(120)
    assert not una.switch(RAMA[1]), "corrió la rama con el switch apagado"
    assert una.switch(RAMA[2]), "la página no siguió después del `end`"

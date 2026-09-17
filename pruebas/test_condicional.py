"""`ConditionalBranch`: la rama que corre y la que se saltea.

Hacen falta las dos mitades, y se prueban en lugares distintos por una razón de
orden que conviene tener presente.

**La rama que se saltea** se prueba con una página del juego, que es lo que
importa: que el dato real compile y corra. El banco es el mapa 52, evento 1,
página 1 —la entrada a la persecución—, que es automática y sin condiciones:

    PlayBGM, PanScreen, y el héroe a su lugar
    saca del grupo al 10, 14, 15, 17, 18, 19 y 20
    if switch 130:
        agrega al 19
        MoveEvent (el héroe), Wait
    else:
    end
    if switch 131: ... lo mismo con el 20
    MoveEvent (el héroe)
    switch 175 <- prendido

Son dos cosas distintas: que la rama no corra —el 19 no vuelve al grupo— y que
la página **siga después del `end`** —el 175 se prende—. Una implementación que
saltee de más deja el 175 apagado.

Hasta el 2026-09-17 el banco era el mapa 66, que se había elegido porque ahí la
ventana de mensaje no entra y ninguna página con mensajes compilaba. La ventana
pasó a ser obligatoria, y el 66 dejó de armar.

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

# La página del juego, y lo que deja.
MAPA = 52
QUE_VUELVE = 19       # lo agrega la rama que se saltea
DESPUES = 175         # lo que prende la página después de los `end`, siempre
# Lo que tarda en llegar al final: un PanScreen y dos caminatas del héroe.
CUADROS = 1200

# (el switch que decide, el de adentro, el de después) para `--rama-de-prueba`.
RAMA = (300, 301, 302)


def hasta_el_final(una):
    for _ in range(CUADROS):
        una.correr(1)
        if una.switch(DESPUES):
            return
    raise AssertionError(
        "la página no llegó al final: o no compiló, o el salto se pasó de largo")


def test_la_pagina_del_juego_sigue_despues_del_end(partida):
    """Con la rama salteada, la página tiene que llegar igual al final."""
    hasta_el_final(partida(mapas=(MAPA, [])))


def test_la_rama_del_juego_se_saltea(partida):
    una = partida(mapas=(MAPA, []))
    hasta_el_final(una)
    grupo = una.consola.ram(una.simbolos["grupo"], una.byte("grupo_n"))
    assert QUE_VUELVE not in grupo, \
        "corrió la rama de adentro con el switch apagado: el %d volvió al " \
        "grupo" % QUE_VUELVE


def test_la_rama_corre_con_el_switch_prendido(partida):
    una = partida(switch=[RAMA[0]], rama=RAMA)
    una.correr(120)
    assert una.switch(RAMA[1]), "no corrió la rama de adentro"
    assert una.switch(RAMA[2]), "la página no siguió después del `end`"


def test_la_rama_no_corre_con_el_switch_apagado(partida):
    una = partida(rama=RAMA)
    una.correr(120)
    assert not una.switch(RAMA[1]), "corrió la rama con el switch apagado"
    assert una.switch(RAMA[2]), "la página no siguió después del `end`"

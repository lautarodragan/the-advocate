"""`ConditionalBranch` de actor, "¿está en el grupo?": `OP_IF` con el tipo 5.

Es la pregunta con que las cinemáticas deciden quién aparece, y hasta el
2026-09-21 contestaba que sí **siempre**. taro lo encontró jugando: en el techo
del Warehouse la página pregunta si Arden —el actor 15— está en el grupo, y lo
mueve a escena si está. Por el camino del hover tram Arden no se suma, y
aparecía igual.

Las ramas de actor con dos operandos —equipo y habilidad— tienen su prueba en
`test_comandos_golden.py::test_rama_actor`.

Los dos casos son la misma página preguntando por dos actores: el 10, que está
en el grupo con que arranca el cartucho, y Arden, que no. **Ninguno de los dos
toca el grupo, y es a propósito**: la primera versión sumaba y sacaba a Arden
con `ChangePartyMembers` y movió cinco goldens de escenas que no tenían nada que
ver —`autos9`, `mecanico`, `puerta-8-9` y dos del `tram`—. Eso está medido: sin
el cambio de grupo no se mueve ninguna. **Por qué, no**: la explicación probable
es que `possible_leaders` mira también las páginas de los casos, así que Arden
pasa a ser un líder posible y se le reserva sprite y paleta en cada mapa.

La rama prende el switch 709, que ningún comando del juego toca. Sin el
arreglo de `if_actor` en `runtime/interprete_condiciones.s`, `rama-grupo-no` lo prende
igual.
"""

import pytest

SWITCH = 709


@pytest.mark.parametrize("caso, esta", [("rama-grupo", True),
                                        ("rama-grupo-no", False)])
def test_rama_grupo(partida, caso, esta):
    una = partida(caso=caso)
    una.correr(60)
    assert una.switch(SWITCH) == esta, (
        "la rama pregunta si un actor está en el grupo, que %s, y %s"
        % ("sí" if esta else "no",
           "no entró" if esta else "entró igual"))

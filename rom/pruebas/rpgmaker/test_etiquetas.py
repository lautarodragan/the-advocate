"""`Label` y `JumpToLabel`: el salto se resuelve al compilar y es un `OP_GOTO`.

La página `etiquetas` hace, en orden:

* una vuelta hacia atrás: la variable 40 sube de a uno, y mientras sea menor
  que 3 una rama salta a la etiqueta 1, de adentro de la rama hacia afuera;
* un salto hacia adelante, a la 2, por encima del switch 726;
* un salto a la 9, que la página no tiene: en RM2k no hace nada, y sigue;
* y un salto a la 3, que está **adentro del `else`** de una rama que daría
  verdadero —es lo que hace el común 39, la portable console—: corre el
  cuerpo del `else` y no el de arriba.

Los switches los toca sólo esta página, ningún comando del juego. Sin los
dos comandos en el compilador, la página entera no compilaba y no prendía
nada: visto en rojo así.
"""

import datos

FUERA = 726     # el que los saltos esquivan
SIGUE = 733     # después del salto a una etiqueta que no está
ELSE = 735      # el cuerpo del `else`, al que se entra saltando
FIN = 753       # lo último de la página


def test_los_saltos_a_etiquetas(partida):
    una = partida(caso="etiquetas")
    una.correr(30)
    assert una.switch(FIN), "la página no llegó al final: ¿compiló?"
    assert una.variable(datos.ranuras_de_variable()[40]) == 3, (
        "la vuelta hacia atrás no dio tres pasadas")
    assert not una.switch(FUERA), (
        "un salto no esquivó el switch: o el de adelante cayó antes de su "
        "etiqueta, o el del else corrió el cuerpo de arriba")
    assert una.switch(SIGUE), "el salto a una etiqueta que no está cortó la página"
    assert una.switch(ELSE), "el salto adentro del else no corrió su cuerpo"

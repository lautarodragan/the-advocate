"""`TileSubstitution`: cambiar un tile del mapa por otro, corriendo.

Estas pruebas **no miran una golden**, y es a propósito: una golden congela lo
que la ROM dibujaba, así que no puede decir si una feature nació bien —ver
AGENTS.md—. Lo que se compara es **el mismo tick de dos corridas**: una que
sustituye y otra que hace exactamente lo mismo sin sustituir. De ahí salen
tres afirmaciones, y ninguna depende de ninguna imagen guardada:

* antes de sustituir, las dos pantallas son idénticas —que es lo que hace
  válida la comparación: los dos casos son el mismo, salvo el comando—;
* después de sustituir, son distintas;
* y después de la sustitución inversa vuelven a ser idénticas, que es lo que
  el minijuego del mapa 11 necesita de prender y apagar un cono, y lo que
  `ResetPuzzle` va a pedir.

**Contra un control y no contra el tick de antes**, y eso costó un rojo: en la
misma corrida, dos ticks distintos no dibujan lo mismo aunque el mapa no haya
cambiado. Los NPCs del mapa 6 caminan y los tiles animados del ChipSet cambian
de dibujo con `vueltas`, así que la vuelta atrás daba 141.972 bytes iguales y
después uno distinto que no tenía nada que ver con la sustitución. Con el
control, las dos corridas están en el mismo tick y todo eso pasa igual en las
dos.

La inversa devuelve la pantalla porque el tile hacia el que se sustituye está
dibujado **fuera de cámara**: `23 -> 25` cambia las 30 celdas del tile 23 que
se ven desde (18,15), y las tres del 25 que tiene el mapa están en x <= 9, o
sea afuera. Si estuvieran adentro, la vuelta no sería identidad y eso no sería
un error: `DoSubstitute` cambia los valores de la traducción, no las claves,
así que `25 -> 23` manda a 23 **todo** lo que hoy dibuja 25. Los dos casos
están elegidos con esa cuenta hecha; los scripts descartables con que se
eligieron quedaron en `/extras/scratch/motor-tiles/`.
"""

import pytest

from tanda import partida

# Cuándo hace cada cosa la página del caso, en ticks, y de dónde salen: el
# primer `Wait` es de 10 décimas y el segundo de 30, o sea 60 y 180 cuadros.
SUSTITUYE = 60
INVIERTE = SUSTITUYE + 180
# Lo que tarda la ventana en ponerse al día. La sustitución no reescribe el
# tilemap de la VRAM —`stream_map` sólo arma la columna que la cámara
# destapa—, así que se rehace de a una columna por cuadro y son `WINDOW_COLS`
# = 64. Acá se le dan 70; que con 70 alcance es lo que mide el tercer assert.
AL_DIA = 70

# Los dos pares: el caso que sustituye, su control, y qué sustituye. La capa no
# cambia lo que se mira —son la misma pregunta— pero sí el camino del
# conversor: la alta obliga a armar bloques que el mapa no dibuja en ninguna
# celda, y la de abajo no.
CASOS = (
    ("tile-sub", "tile-sub-nada", "la capa de abajo, tiles 23 y 25"),
    ("tile-sub-alta", "tile-sub-alta-nada", "la capa de encima, tiles 121 y 52"),
)


@pytest.mark.parametrize("caso,control,que", CASOS,
                         ids=[c[0] for c in CASOS])
def test_sustituir_cambia_el_dibujo_y_la_inversa_lo_devuelve(caso, control,
                                                             que):
    """Ida y vuelta de una sustitución, mirando la pantalla de verdad."""
    con, sin = partida(caso), partida(control)

    def en(ticks, cuantos):
        con.correr(cuantos)
        sin.correr(cuantos)
        return con.imagen().tobytes(), sin.imagen().tobytes()

    antes, testigo = en(SUSTITUYE - 10, SUSTITUYE - 10)
    assert antes == testigo, (
        "%s: los dos casos ya dibujan distinto **antes** de sustituir, así "
        "que no son el mismo caso y la comparación no mide la sustitución"
        % caso)

    sustituido, testigo = en(SUSTITUYE + AL_DIA, 10 + AL_DIA)
    assert sustituido != testigo, (
        "%s: la pantalla no cambió al sustituir (%s). O el comando no compiló "
        "—mirá el conversor.log del cartucho— o el tile nuevo se dibuja igual "
        "que el viejo, y entonces el caso no prueba nada." % (caso, que))

    quieta, testigo = en(INVIERTE - 10, INVIERTE - SUSTITUYE - AL_DIA - 10)
    assert quieta != testigo, (
        "%s: la sustitución se deshizo sola antes de que nadie la invirtiera"
        % caso)

    # Y acá se cobran las dos cosas de una: que la inversa deshaga, y que el
    # refresco de la ventana termine en `AL_DIA` cuadros. Si le faltara una
    # columna por rehacer, esa columna seguiría mostrando el tile sustituido y
    # la comparación contra el control daría distinto.
    vuelta, testigo = en(INVIERTE + AL_DIA, 10 + AL_DIA)
    assert vuelta == testigo, (
        "%s: la sustitución inversa no dejó la pantalla como la del control "
        "(%s), o la ventana todavía no se puso al día a los %d cuadros"
        % (caso, que, AL_DIA))

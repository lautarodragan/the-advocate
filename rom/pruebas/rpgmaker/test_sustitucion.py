"""`TileSubstitution`: cambiar un tile del mapa por otro, corriendo.

Estas pruebas **no miran una golden**, y es a propósito: una golden congela lo
que la ROM dibujaba, así que no puede decir si una feature nació bien —ver
AGENTS.md—. Lo que se compara es **el mismo tick de dos corridas**: una que
sustituye y otra que hace exactamente lo mismo pero sustituyendo un tile por
**sí mismo**, que pone la tabla y rehace la ventana igual sin cambiar un pixel.
Así lo único distinto entre las dos es lo que la sustitución dibuja, y la
comparación es en **cero pixeles**, como cualquier golden.

**Contra un control y no contra el tick de antes**, y eso costó un rojo: en la
misma corrida dos ticks distintos no dibujan lo mismo aunque el mapa no haya
cambiado, porque los NPCs caminan y los tiles animados del ChipSet cambian de
dibujo con `vueltas`. Con el control las dos corridas están en el mismo tick.

**Y las dos corridas van una después de la otra, nunca a la vez.** Eso costó
el segundo rojo, y no se ve leyendo el código: el core de libretro es **uno
solo por proceso**, así que dos `Partida` vivas a la vez comparten la consola
y la segunda se lleva puesta a la primera. Lo que se veía era una diferencia
de 28 pixeles de 57.344 entre dos corridas que tenían la misma OAM, la misma
CGRAM y el mismo `vueltas` —o sea, imposible— y tablas de sustitución que no
eran las suyas. Por eso `capturas` corre una partida entera, se guarda las
imágenes, y recién después arranca la otra.
"""

from tanda import partida

# Cuándo hace cada cosa la página de los casos, en ticks: el primer `Wait` es
# de 10 décimas y el segundo de 30, o sea 60 y 180 cuadros.
SUSTITUYE = 60
INVIERTE = SUSTITUYE + 180
# Lo que tarda la ventana en ponerse al día. La sustitución no reescribe el
# tilemap de la VRAM —`stream_map` sólo arma la columna que la cámara
# destapa—, así que se rehace de a una columna por cuadro y son `WINDOW_COLS`
# = 64. Que con 70 alcance es lo que mide el último assert de la ida y vuelta.
AL_DIA = 70


def capturas(caso, ticks):
    """Las capturas de un caso en esos ticks, con **una sola** partida viva."""
    una = partida(caso)
    salida = []
    for tope in ticks:
        una.correr(tope - una.cuadro)
        salida.append(una.imagen().convert("RGB").tobytes())
    return salida


def test_la_capa_de_abajo_va_y_vuelve():
    """Tiles 23 y 25 del ChipSet 8, en el mapa 6, desde (18,17).

    La inversa devuelve la pantalla porque el tile hacia el que se sustituye
    está dibujado **fuera de cámara**: `23 -> 25` cambia las 27 celdas del tile
    23 que se ven desde ahí, y las tres del 25 que tiene el mapa están en
    x <= 9, o sea afuera. Si estuvieran adentro la vuelta no sería identidad y
    eso no sería un error: `DoSubstitute` cambia los valores de la traducción,
    no las claves, así que `25 -> 23` manda a 23 **todo** lo que hoy dibuja 25.
    El caso está elegido con esa cuenta hecha.
    """
    ticks = (SUSTITUYE - 10, SUSTITUYE + AL_DIA, INVIERTE - 10,
             INVIERTE + AL_DIA)
    con = capturas("tile-sub", ticks)
    sin = capturas("tile-sub-nada", ticks)

    assert con[0] == sin[0], (
        "los dos casos ya dibujan distinto **antes** de sustituir, así que no "
        "son el mismo caso y la comparación no mide la sustitución")
    assert con[1] != sin[1], (
        "la pantalla no cambió al sustituir. O el comando no compiló —mirá el "
        "conversor.log del cartucho— o el tile nuevo se dibuja igual que el "
        "viejo, y entonces el caso no prueba nada.")
    assert con[2] != sin[2], (
        "la sustitución se deshizo sola antes de que nadie la invirtiera")
    # Acá se cobran las dos cosas de una: que la inversa deshaga, y que el
    # refresco de la ventana termine en `AL_DIA` cuadros. Si le faltara una
    # columna por rehacer, esa columna seguiría mostrando el tile sustituido.
    assert con[3] == sin[3], (
        "la sustitución inversa no dejó la pantalla como la del control, o la "
        "ventana todavía no se puso al día a los %d cuadros" % AL_DIA)


def test_la_capa_de_encima_tambien_se_sustituye():
    """Tiles 49 y 54 del ChipSet 6, en el mapa 1, desde (15,50).

    El mapa y los tiles no son los de arriba por dos razones medidas. Una: en
    el mapa 6 **no hay dos tiles altos que se dibujen en BG2**, y un tile alto
    sin el bit `Above` no va a BG2 sino horneado en el fondo, así que la
    sustitución no se puede armar —ver `Sustituciones._hornea`—. La otra: el
    tile 49 se combina con **tres** tiles de abajo y por lo tanto usa tres
    entradas de la tabla de la RAM, que lleva `SUB_MAX`.

    Va de ida y no de vuelta a propósito: la inversa sumaría las claves de
    todas las combinaciones del 54, que son siete.
    """
    ticks = (SUSTITUYE - 10, SUSTITUYE + AL_DIA)
    con = capturas("tile-sub-alta", ticks)
    sin = capturas("tile-sub-alta-nada", ticks)
    assert con[0] == sin[0], (
        "los dos casos ya dibujan distinto antes de sustituir")
    assert con[1] != sin[1], (
        "sustituir en la capa de encima no cambió la pantalla")

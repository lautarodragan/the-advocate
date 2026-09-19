"""Hablarle a algo: la familia `hablar` de la tanda.

Estuvo en `test_tanda_escenas.py` hasta que las pruebas se separaron por qué
prueban. Las escenas y las cinemáticas son de ABL; esto es la regla de RM2k
para disparar una página con A —`Game_Player::CheckActionEvent`—, sus
condiciones, el giro hacia el héroe y la cola de interacciones, aunque el
material sean los personajes de ABL. El arnés es el mismo que el de las
escenas, y está explicado en `pruebas/abl/test_tanda_escenas.py`.
"""

import pytest

from tanda import golden, partida

# Hablarle a algo: nombre, la página de prueba —el `Teleport` al mapa y a la
# celda del héroe, el switch que arranca prendido y, si hace falta, la ruta
# terminada de un evento—, los ticks de los toques de A y los ticks que se
# capturan.
HABLADAS = (
    ("hablar", "hablar", (25,), (20, 60)),
    # Diecisiete toques de A sobre el mismo evento, o sea nueve aperturas de
    # mensaje. Es el primer caso que pasa de la octava interacción, que era
    # justo donde se rompía la cola de ocho punteros que los eventos tenían
    # antes de los dos bits. Verificado que **da rojo con la ROM de antes del
    # anillo**, en el cuadro 360 y sólo ahí.
    ("hablar-repetido", "hablar", tuple(range(25, 346, 20)),
     (40, 200, 360)),
    # El mismo con el switch **25** en vez del 24: la página no queda activa y
    # apretar A no tiene que hacer nada. Es lo único que ejercita que se miren
    # las condiciones.
    ("hablar-sin-switch", "hablar-sin-switch", (25,), (20, 60)),
    # El viaje en el Hover-Tram, la única página que traba el mapa 13: la
    # sacudida del tranvía y la ruta forzada que le da vuelta la cabeza a Talan
    # mientras arranca. Pide el 16 adentro —Sector 30, a donde el viaje termina
    # teletransportando— porque sin él el Teleport del final no compila y la
    # página se cae con él. La A cae en el tick 900, o sea después de las tres
    # capturas: lo que se compara es el arranque de la escena.
    #
    # Verificado en rojo **de un solo lado**, que es lo que hay que hacer con
    # una pieza que vive entera en el conversor: con `eventos.CHANGE_PBG = -1`
    # puesto sólo del lado de la referencia, ésta no compilaba la página, la
    # ROM sí, y el cuadro 10 daba 1,22%. Poco en pixeles y mucho en
    # significado: la pose de Talan y el corrimiento de la cámara, o sea la
    # escena entera contra ninguna.
    ("tram-viaje", "hablar-tram-viaje", (900,), (10, 30, 60)),
    # Los dos de Lashe City que taro no podía usar el 2026-09-08: caminan y
    # además aparecen con la página, y hasta ese día eso era un solo bit. El
    # `Mechanic` habla porque su página ya no se frena por el giro.
    ("mecanico", "hablar-mecanico", (25,), (20, 60)),
    ("bum", "hablar-bum", (25,), (20, 60)),
    # El giro hacia el héroe: el que camina gira en su ranura, y el quieto se
    # muda a la de giro del mapa y deja a su gemelo —el 14, el mismo Future2:6—
    # como estaba. Los ticks del medio lo miran girado y el último de vuelta en
    # su pose, después de cerrar el último mensaje. `bum-vuelve` encontró que
    # la fila guardada del que gira pasaba a ser de otro cuando las filas se
    # reordenan.
    ("bum-vuelve", "hablar-bum", (24, 70, 110, 150, 190),
     (60, 170, 200)),
    ("gemelo", "hablar-gemelo", (25, 70, 110, 150),
     (20, 60, 140, 160)),
    # El mismo con una ruta terminada: la orden 13 lo deja mirando a la
    # derecha, y la ranura de ruta queda. Tiene que girar igual y volver a la
    # derecha. Es el `GangMember1` que taro encontró sin girar.
    ("gemelo-ruta", "gemelo-ruta", (25, 70, 110, 150),
     (20, 60, 140, 160)),
    # Los fuegos translúcidos de los barriles del mapa 9, con la mezcla
    # horneada en el gráfico: ver `rm2k.HORNEADO_SUFIJO`. Es el caso que cobra
    # que el conversor y la referencia horneen contra el mismo fondo.
    ("fuego", "hablar-fuego", (900,), (20, 40)),
    # El Tram Officer del mapa 9 con el 13 adentro: **es el caso de
    # `CallEvent`**, y sin ese mapa el `Teleport` del Hover-Tram no compila,
    # con él no compila el Hover-Tram entero, y entonces la llamada se saltea.
    ("tram", "hablar-tram", tuple(range(25, 1786, 40)),
     (200, 420, 620, 900, 1200)),
    # Parallel Process: los dos autos y los dos que los reubican del mapa 9,
    # mirados a lo largo de cuatro segundos. Verificado que da rojo sin
    # `paralelos_tick`: 232 pixeles en el cuadro 2. El mapa 8 tiene nueve y no
    # se puede mirar todavía: pierde dos cuadros al entrar y la comparación
    # arranca corrida.
    ("autos9", "hablar-autos9", (900,), (2, 20, 60, 120, 240)),
)


@pytest.mark.parametrize(
    "nombre,caso,apretar,cuadros", HABLADAS,
    ids=[caso[0] for caso in HABLADAS])
def test_hablar(nombre, caso, apretar, cuadros):
    """`hablar`: hablarle a algo, que es lo que convierte esto en un juego.

    La regla sale de `Game_Player::CheckActionEvent`: se mira la celda del
    héroe y después la de adelante, y gana la página de número más alto que
    cumpla sus condiciones.

    El switch 24 que prenden las páginas de prueba `hablar-*` no es una
    licencia: **todas** las páginas del pad de Talan lo piden, y lo
    prende la cinemática de apertura. Ponerlo a mano es dejar el mundo en el
    estado al que el juego llega solo.

    Del arnés, dos cosas:

    * **un toque de A que cae adentro de los primeros ticks de un mensaje no
      hace nada.** La ROM ignora el botón mientras `msg_abierto` esté en cero,
      y componer la ventana le lleva de nueve a diecinueve ticks según el
      texto. Al armar una lista de toques hay que dejar treinta ticks desde que
      el mensaje abre, no veinte: con veinte, un toque llegó **uno** antes de
      tiempo;
    * **un `apretar` más allá del último tick capturado es a propósito**:
      `fuego`, `autos9` y `tram-viaje` aprietan en el 900 y capturan mucho
      antes. Lo que se compara ahí es la escena corriendo sola.
    """
    for cuadro in cuadros:
        p = partida(caso)
        p.correr(cuadro, apretar_a=apretar)
        golden("%s-%d" % (nombre, cuadro), p.imagen())

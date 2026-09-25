"""El recorrido largo: se juega el juego y se le pregunta a la RAM si llegó.

Es la prueba que pidió taro: **emular una jugada entera** —desde el arranque, y
desde la casa de Talan hasta el auditorio— verificando el estado con lecturas de
RAM y sacando una captura en cada hito, para que él las mire una vez y las
bendiga. No compara contra ninguna referencia: acá hay un juego que
tiene que seguir siendo jugable de punta a punta.

Lo que la hace barata es que **la emulación no es el problema**: snes9x corre
unos 2.900 ticks por segundo, así que los cinco mil ticks de las dos jugadas
cuestan menos de tres segundos. Corre en `release`, la ROM que se juega, que
arranca en el 4 como el juego de verdad y lleva la pantalla de título: por eso
la jugada empieza eligiendo "Begin the Story", que es por donde entra el
jugador. Hasta el 2026-09-24 corría en `juego`, un cartucho parecido.

**Dos cosas que esta prueba no hace, las dos medidas.**

* **No camina de Lashe City a la fábrica**, porque no se puede: el grafo de
  islas del juego dice que desde la casa de Talan se llega a los mapas 7, 8, 9 y
  10 y a ninguno más. La calle que lleva a la puerta de Delcentric —la isla del
  mapa 9 donde están los eventos 28 y 29— sólo se alcanza desde el HQ de los
  Lazer Teeth, y el camino hasta ahí lo corta el teletransporte de (64,49), que
  con el switch 24 puesto —Talan yendo a trabajar— devuelve a Lashe City. Así
  que el recorrido entra al mapa 16 **por donde el juego entra**, con las mismas
  coordenadas que usan el evento 65 del mapa 8 y el 28 del mapa 9: (53,7).
* **No compara pixel por pixel.** Cada hito se guarda en
  `pruebas/snapshots/playthrough/` y se compara con su golden de
  `pruebas/golden/playthrough/`, que taro bendijo el 2026-09-13, con una
  tolerancia grande: lo que caza es la pantalla rota, no el detalle. El
  porqué, en `Recorrido.foto`.
"""

from recorrido import UN_ANO_DESPUES

# Adónde entra el juego al mapa 16, y de dónde sale el número: el `Teleport` de
# los eventos 65 y 66 del mapa 8 y de los 28 y 29 del mapa 9, que son las cuatro
# celdas por las que se entra a la corrida al trabajo. No es una celda elegida.
CORRIDA_AL_TRABAJO = (16, 53, 7)


def test_la_apertura_termina_con_kersh_en_el_linkage_block(recorrido):
    """Del reset al Linkage Block, jugando.

    El arranque cae en el mapa 4, que es un enrutador vacío —"Blank (Leave
    START here)"— y de ahí a la apertura del mapa 1: Kersh subiendo la escalera,
    el texto, y el droide que sale por la puerta y vuelve a entrar. **El map id
    no cambia en toda la escena**, así que el hito no puede ser el mapa: es el
    switch 3, que la propia escena prende al terminar, y que el jugador toma el
    control.
    """
    r = recorrido("apertura")
    r.empezar("la cinemática de apertura del mapa 1")
    r.esperar("que la apertura termine y Kersh tome el control",
              lambda p: p.switch(3) and not p.corriendo_una_pagina(),
              tope=6000)
    assert r.p.mapa() == 1, r.estado()
    # Donde la escena lo deja, medido: es la celda del evento 2, el que acaba
    # de correr, y de ahí para arriba el jugador camina solo.
    assert r.celda() == (59, 46), r.estado()
    r.foto("kersh-toma-el-control")

    r.empezar("de la escalera al Linkage Block")
    r.viajar(2)
    assert r.celda() == (9, 80), r.estado()
    r.foto("linkage-block")


def test_de_la_casa_de_talan_al_auditorio(recorrido):
    """La jugada que pidió taro, entera.

    El cartel de "One year previously", el despertador de Talan, la puerta a
    Lashe City, la corrida al trabajo, la fábrica de Delcentric y el guardia que
    abre el auditorio —que es una elección de dos opciones, así que además pasa
    por `ShowChoice`—.
    """
    r = recorrido("talan", switch=[UN_ANO_DESPUES])

    r.empezar("el cartel de One year previously y el viaje a la casa de Talan")
    r.esperar_mapa(7, tope=3000)
    assert r.celda() == (15, 7), r.estado()
    r.foto("casa-de-talan")

    r.empezar("el despertador de Talan")
    # El switch 24 es "Talan se levantó y va a trabajar": lo prende el evento 4
    # del mapa 7 y es lo que abre su puerta y arranca el cronómetro.
    r.esperar_switch(24, tope=4000)
    r.esperar_el_control(tope=3000)
    assert (r.p.byte("timer_activo"), r.p.palabra("timer_seg")) == (1, 600), (
        "el despertador tiene que haber arrancado la cuenta atrás de diez "
        "minutos. %s" % r.estado())
    r.foto("talan-despierto")

    r.empezar("la puerta de la casa de Talan a Lashe City")
    r.viajar(8)
    assert r.celda() == (11, 56), r.estado()
    r.foto("lashe-city")

    r.empezar("la corrida al trabajo")
    r.p.ir_al_mapa(*CORRIDA_AL_TRABAJO)
    r.foto("corrida-al-trabajo")
    r.esperar_mapa(17, tope=20000)
    assert r.celda() == (36, 73), r.estado()
    # **El cronómetro tiene que haber quedado parado**, porque lo para la
    # escena del mapa 16: es la única prueba de que la cinemática corrió entera
    # y no que el mapa 17 se cargó por otro lado. Medido, queda en 581 de 600.
    assert not r.p.byte("timer_activo"), (
        "la corrida al trabajo tiene que parar el cronómetro. %s" % r.estado())
    assert 0 < r.p.palabra("timer_seg") < 600, r.estado()
    r.foto("fabrica-de-delcentric")

    r.empezar("el guardia que abre el auditorio")
    r.viajar(18)
    assert r.celda() == (9, 14), r.estado()
    r.foto("auditorio")

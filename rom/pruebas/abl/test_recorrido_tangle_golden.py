"""Tangle Forest: del bosque al fin de la demo, en el túnel a Paradise.

Sigue donde termina `test_recorrido_capitulo_golden.py`: Talan y Arden
recién llegados al 310 por la entrada del mundo. El recorrido:

    310 el bosque: la salida del norte, el evento 2 -> 311 (10, 13)
    311 el claro: el evento 1, al pisarlo, trae el tram de la Agency y una
        pelea (la tropa 191) -> 313
    313 el tram: la escena de los guardias, que abren las compuertas (840)
        -> 311
    311 las latas de fuego: la automática del evento 4 (con el 840) salta al
        312 y sigue ahí: el `EraseEvent` después del salto, que no hace nada,
        y el cronómetro de dos minutos
    312 el bosque en llamas, contra el cronómetro: la salida, el evento 10,
        pregunta por el cronómetro —`>= 0`, siempre— y lo para (845) -> 313
    313 el tram otra vez: los guardias bajan (846) -> 312
    312 la nave: la automática del evento 81 —la de la condición de
        cronómetro, que acá no vale— pelea con la tropa 239 y sale al mundo
        (847) -> 66 (34, 56)
    66  el túnel a Paradise, el evento 18: "Yes - Continue onward" es el fin
        de la demo, en el fork del 66

**Los encuentros al azar se apagan** al llegar a cada mapa, como en los
recorridos de antes. Las peleas se juegan, con los HP del grupo en 999 y
**el grupo en el nivel 20**: la prueba arranca acá con los actores como los
deja la base de datos, y en su nivel de arranque los golpes no les sacan nada
a los Para Guard del claro —la pelea no termina nunca—. Una partida que
llegó jugando trae el nivel que haya ganado.

Las capturas van a `pruebas/snapshots/playthrough/tangle/` y **no están
bendecidas**: son para que taro las mire. Lo que cobra esta prueba es la RAM.
Las llegadas al 310 y al 311 tienen golden de la tanda en `test_tangle.py`.
Ver `workflow/tasks/*/mundo-5-tangle-forest.md`.
"""

from batalla import grupo_de, poner_exp

from tramo_lashe import CON_ARDEN
from tramo_sorbe import (
    ARDEN, CONTO_LA_HISTORIA, DALIA_LLEGO, EL_MUNDO, RECHAZO_A_WICK, TALAN,
    TOBILLO_CURADO, en_pelea_hace, jugar, sin_encuentros)

# Lo que dejó el capítulo: Vago contó lo de Paradise, cruzaron el puente por
# debajo, y Talan ya dijo lo suyo a la entrada del bosque.
SE_VAN_A_PARADISE = 310
CRUZARON = 849
ENTRARON_AL_BOSQUE = 880

TANGLE, EL_CLARO, EN_LLAMAS, EL_TRAM = 310, 311, 312, 313
EN_TANGLE = (48, 22)
# En el claro, la celda que trae el tram.
EL_TRAM_LLEGA = (10, 11)
# Lo que prenden las escenas: el tram arriba, la salida del bosque en llamas,
# los guardias que bajan, y la nave vencida.
TRAM_ARRIBA, SALIERON, BAJAN, LA_NAVE = 840, 845, 846, 847
# La salida del bosque en llamas, el evento 10.
LA_SALIDA = (30, 52)
DOS_MINUTOS = 120
# Del otro lado del bosque, en el mundo: el túnel a Paradise, el evento 18, y
# "Yes - Continue onward".
DEL_OTRO_LADO = (34, 56)
EL_TUNEL = (5, 64)
SEGUIR = 1


NIVEL = 20


def con_vida(p):
    for actor in grupo_de(p):
        p.poner_hp(actor, 999)


def quieto_en(mapa):
    return lambda p: (p.mapa() == mapa and not p.corriendo_una_pagina()
                      and not p.byte("fade") and not p.byte("menu_open"))


def test_tangle_forest(recorrido):
    r = recorrido("tangle", switch=[CON_ARDEN, RECHAZO_A_WICK,
                                    CONTO_LA_HISTORIA, TOBILLO_CURADO,
                                    DALIA_LLEGO, SE_VAN_A_PARADISE, CRUZARON,
                                    ENTRARON_AL_BOSQUE])
    p = r.p

    r.empezar("la llegada al bosque")
    p.poner_grupo(TALAN, ARDEN)
    for actor in (TALAN, ARDEN):
        poner_exp(p, actor, 0, NIVEL)
    p.ir_al_mapa(TANGLE, *EN_TANGLE)
    r.esperar_el_control()
    sin_encuentros(p)
    r.foto("el-bosque")

    r.empezar("hasta el claro")
    r.viajar(EL_CLARO)
    r.esperar_el_control()
    sin_encuentros(p)
    r.foto("el-claro")

    r.empezar("el tram y las latas de fuego")
    con_vida(p)
    r.caminar_a(EL_TRAM_LLEGA, hasta=lambda p: p.corriendo_una_pagina())
    jugar(r, "el tram y las latas",
          lambda p: quieto_en(EN_LLAMAS)(p) and p.byte("timer_active"),
          fotos={"el-tram": lambda p: p.mapa() == EL_TRAM,
                 "las-latas": lambda p: p.mapa() == EL_CLARO
                 and p.switch(TRAM_ARRIBA)},
          momentos={"la-pelea-del-claro": en_pelea_hace(120)})
    assert p.switch(TRAM_ARRIBA), r.estado()
    assert DOS_MINUTOS - 10 <= p.palabra("timer_sec") <= DOS_MINUTOS, (
        "la página del claro arranca el cronómetro en dos minutos después de "
        "saltar al 312, y quedan %d segundos. %s"
        % (p.palabra("timer_sec"), r.estado()))
    assert grupo_de(p) == [TALAN, ARDEN], r.estado()
    r.foto("el-bosque-en-llamas")

    r.empezar("la salida del bosque en llamas")
    sin_encuentros(p)
    r.caminar_a(LA_SALIDA, tope=8000, hasta=lambda p: p.corriendo_una_pagina())
    jugar(r, "la salida", lambda p: p.switch(SALIERON) and p.mapa() == EL_TRAM)
    assert not p.byte("timer_active"), (
        "la salida del bosque para el cronómetro. %s" % r.estado())
    assert p.palabra("timer_sec") > 1, (
        "se llegó a la salida con el cronómetro en %d: la ruta tarda más que "
        "lo que da el fuego. %s" % (p.palabra("timer_sec"), r.estado()))

    r.empezar("la nave")
    con_vida(p)
    jugar(r, "el tram y la nave", quieto_en(EL_MUNDO),
          fotos={"los-guardias-bajan": lambda p: p.mapa() == EL_TRAM
                 and p.switch(SALIERON),
                 "la-nave": lambda p: p.mapa() == EN_LLAMAS
                 and p.switch(BAJAN)},
          momentos={"la-pelea-con-la-nave": en_pelea_hace(120)})
    assert p.switch(BAJAN) and p.switch(LA_NAVE), r.estado()
    assert r.celda() == DEL_OTRO_LADO, r.estado()
    # La página termina con el tinte de vuelta a neutro, y la ROM lo sube a
    # CGRAM en el vblank siguiente: sin esperar, la foto sale todavía roja.
    p.correr(4)
    r.foto("del-otro-lado-del-bosque")

    r.empezar("el túnel a Paradise")
    sin_encuentros(p)
    r.caminar_a(EL_TUNEL, tope=8000, hasta=lambda p: p.corriendo_una_pagina())
    r.elegir(SEGUIR)
    # Lo que dice Talan al seguir, y el cartel del fin.
    mensajes = []

    def contar(p):
        mensajes.append(grupo_de(p))
        return False
    jugar(r, "el fin de la demo hasta el título",
          lambda p: len(mensajes) >= 2 and not p.byte("msg_open"),
          fotos={"contar": contar,
                 "el-fin-de-la-demo": lambda p: len(mensajes) == 2})
    assert len(mensajes) == 2, (
        "al seguir hacia Paradise salen un mensaje de Talan y el cartel del "
        "fin; salieron %d. %s" % (len(mensajes), r.estado()))
    p.consola.run(p.simbolos["BOOT_FRAMES"] + 60)
    r.foto("el-titulo-despues-del-fin", asentar=False)

"""El final del capítulo: de la entrada de Tasgarde al bosque de Tangle.

Es el hito 4 de `workflow/tasks/*/el-mundo-y-lo-que-sigue.md`, y sigue donde
termina `test_recorrido_sorbe_golden.py`: Dalia pisando la entrada de
Tasgarde al final de su viaje en auto. El recorrido, por la rama de Arden:

    66  la entrada de Tasgarde, el evento 13 -> 74 (19, 48)
    74  el guardia de la puerta abre (280); arriba, el evento 5 -> 85
    85  Eisen en su simulación (283) y el interruptor: la historia de Eisen,
        con `DummyHero` en el grupo, encadenada de automáticas por 86 a 94.
        El 89 y el 93 alternan el 286; el 93 borra con "ninguna" -> 95
    95  "Into The Machine", el minijuego, con Eisen: las tres palancas de la
        escotilla, saltando entre plataformas; la escotilla (303), y el 55
        borra con el corte -> 99, 100, 95, 101, 102, 101 -> 81
    81  Talan y Arden; Vago cuenta lo de Paradise (310) -> 69
    66  del lado de Sorbe, el puente (evento 15, con el 252) -> 259
    259 el plan de Arden: por debajo -> 255
    255 los crujidos, una pelea, y el evento 64 (849) -> 66 (73, 7)
    66  la entrada a Tangle Forest, el evento 19 -> 310 (48, 22), con los
        dos mensajes de Talan. El bosque lo juega
        `test_recorrido_tangle_golden.py`

**Los encuentros al azar del mundo se apagan** al llegar, como en el
recorrido de Sorbe. La pelea de debajo del puente se juega, con los HP del
grupo en 999.

Las capturas van a `pruebas/snapshots/playthrough/el-capitulo/` y **no están
bendecidas**: son para que taro las mire. Lo que cobra esta prueba es la RAM.
Las llegadas a los mapas nuevos tienen golden de la tanda en
`test_capitulo.py`.
"""

import datos
from batalla import grupo_de

from tramo_lashe import CON_ARDEN
from tramo_wick import FUNDIDO, MOSAICO, transiciones
from tramo_sorbe import (
    ARDEN, CONTO_LA_HISTORIA, DALIA, DALIA_LLEGO, EL_MUNDO, ENTRADA_A_TASGARDE,
    RECHAZO_A_WICK, TALAN, TOBILLO_CURADO, en_pelea_hace, jugar, sin_encuentros)

EISEN_ACTOR = 23
TASGARDE, EL_LABORATORIO = 74, 85
# Lo que guarda la ROM para el corte de `ChangeScreenTransitions`: ver
# las transiciones del teletransporte en `arnes/events.py`.
CORTE = 2
INTO_THE_MACHINE = 95
LA_CASA_DE_VAGO = 81
EL_PUENTE, DEBAJO_DEL_PUENTE = 259, 255
# En el puente, el control donde Arden propone cruzar por debajo, y "Yeah,
# let's do that!".
EL_PLAN_DE_ARDEN = (48, 10)
VAMOS = 1
# Debajo del puente: los eventos que crujen al pisarlos (cada uno suma uno a
# la variable 165, y la paralela 10 arranca una pelea en 7, 13, 20…), y los
# que hay que pisar sí o sí, que son diez —medido con un BFS que minimiza los
# crujidos—: la pelea es la del séptimo. El 64, arriba a la izquierda, lleva
# de vuelta al mundo del otro lado del río y prende el 849.
CRUJIDOS = range(2, 64)
PISADOS = ((66, 8), (65, 8), (60, 5), (59, 5), (42, 11), (40, 1), (32, 7),
           (22, 2), (11, 4), (1, 2))
DEL_OTRO_LADO = (1, 0)
CRUZARON = 849
# Del otro lado, la entrada a Tangle Forest, el 66 ev19: el camino al túnel a
# Paradise cruza el bosque. Lleva al 310, a (48, 22), y Talan dice lo suyo ahí.
EL_BOSQUE = (43, 57)
TANGLE, EN_TANGLE = 310, (48, 22)
# Lo prende la automática del 81 al terminar de contar Vago lo de Paradise.
SE_VAN_A_PARADISE = 310

# En Tasgarde: el guardia que abre la puerta, y la celda de arriba que lleva al
# laboratorio.
EL_GUARDIA = (22, 40)
PUERTA_ABIERTA = 280
AL_LABORATORIO = (19, 0)
# En el laboratorio: Eisen, y el interruptor de su simulación.
EISEN = (5, 16)
HABLO_CON_EISEN = 283
EL_INTERRUPTOR = (12, 19)

# El minijuego del 95, "Into The Machine": la voz del Advocate al pisar el
# pasillo, y de ahí las tres palancas de la escotilla, saltando entre las
# plataformas. Cada salto es un evento de los que se hablan desde encima, con
# una ruta que mueve al héroe; los de contacto del medio de un pasillo son
# escaleras, y ésas las cruza `caminar_a` sin saberlo.
LA_VOZ = (13, 39)
EMPIEZA_EL_MINIJUEGO = 315
FORTALEZA = 48
LA_ESCOTILLA = (23, 31)
PALANCAS = {(17, 44): 300, (48, 39): 301, (27, 14): 302, (24, 31): 303}
SALTOS = (
    ((21, 38), (24, 38)),
    ((26, 40), (26, 44)),
    ((17, 44), None),
    ((26, 43), (26, 39)),
    ((26, 36), (26, 32)),
    ((27, 14), None),
    ((30, 28), (33, 28)),
    ((44, 40), (47, 40)),
    ((48, 39), None),
    ((46, 40), (43, 40)),
    ((32, 28), (30, 29)),
    ((24, 31), None),
)


def fortaleza(p):
    return p.variable(datos.ranuras_de_variable()[FORTALEZA])


def saltar(r, celda, llega, tope=2000):
    """Pararse sobre `celda`, que es un evento de los que se hablan desde
    encima, y tocarle A hasta que la ruta del salto deje al héroe en
    `llega`."""
    p = r.p
    r.caminar_a(celda)
    gastado = 0
    while gastado < tope:
        if r.celda() == llega and not p.corriendo_una_pagina():
            return
        p.tocar_ticks("a")
        p.correr(8)
        gastado += 10
    raise AssertionError("saltando desde %s no se llegó a %s. %s"
                         % (celda, llega, r.estado()))


def dejar_crujir(r, momentos):
    """Después de pisar un crujido: unos cuadros para que la paralela del 255
    arranque la pelea si tocaba, y la pelea jugada hasta volver al mapa."""
    visto = [0]

    def listo(p):
        visto[0] += 1
        return (visto[0] > 40 and not p.byte("menu_open")
                and not p.corriendo_una_pagina() and not p.byte("fade"))
    jugar(r, "un crujido del puente", listo, momentos=momentos)


def test_tasgarde_eisen_y_el_puente(recorrido):
    r = recorrido("el-capitulo", switch=[CON_ARDEN, RECHAZO_A_WICK,
                                         CONTO_LA_HISTORIA, TOBILLO_CURADO,
                                         DALIA_LLEGO])
    p = r.p

    r.empezar("la entrada de Tasgarde")
    p.poner_grupo(DALIA)
    x, y = ENTRADA_A_TASGARDE
    p.ir_al_mapa(EL_MUNDO, x + 1, y)
    r.esperar_el_control()
    sin_encuentros(p)
    r.caminar_a(ENTRADA_A_TASGARDE, hasta=lambda p: p.mapa() == TASGARDE)
    r.esperar_mapa(TASGARDE)
    r.esperar_el_control()
    assert grupo_de(p) == [DALIA], r.estado()
    r.foto("tasgarde")

    r.empezar("el guardia de la puerta")
    r.activar(EL_GUARDIA, lambda p: p.switch(PUERTA_ABIERTA)
              and not p.corriendo_una_pagina())
    r.empezar("hasta el laboratorio")
    r.caminar_a(AL_LABORATORIO, hasta=lambda p: p.corriendo_una_pagina())
    jugar(r, "la llegada al laboratorio",
          lambda p: p.mapa() == EL_LABORATORIO and not p.corriendo_una_pagina()
          and not p.byte("fade"))
    r.foto("el-laboratorio")

    r.empezar("Eisen en su simulación")
    r.activar(EISEN, lambda p: p.switch(HABLO_CON_EISEN)
              and not p.corriendo_una_pagina())
    r.activar(EL_INTERRUPTOR, lambda p: p.mapa() != EL_LABORATORIO)
    jugar(r, "la historia de Eisen", lambda p: p.mapa() == INTO_THE_MACHINE
          and not p.corriendo_una_pagina() and not p.byte("fade"),
          fotos={"la-historia-de-eisen-%d" % m: lambda p, m=m: p.mapa() == m
                 for m in (86, 89, 93)})
    assert grupo_de(p) == [EISEN_ACTOR], r.estado()
    assert transiciones(p)[0] == CORTE, (
        "el 93 borra con \"ninguna\" antes de saltar al 95, y eso es el "
        "corte: %s. %s" % (transiciones(p), r.estado()))
    r.foto("into-the-machine")

    r.empezar("la voz del Advocate")
    r.caminar_a(LA_VOZ, hasta=lambda p: p.corriendo_una_pagina())
    jugar(r, "la nota de la fortaleza", lambda p: p.switch(EMPIEZA_EL_MINIJUEGO)
          and not p.corriendo_una_pagina())

    for celda, llega in SALTOS:
        r.empezar("el minijuego, en %s con fortaleza %d"
                  % (celda, fortaleza(p)))
        if celda in PALANCAS:
            r.activar(celda, lambda p, sw=PALANCAS[celda]: p.switch(sw)
                      and not p.corriendo_una_pagina())
        else:
            saltar(r, celda, llega)
        # Con la fortaleza en cero, la paralela 56 devuelve a Eisen al
        # principio y apaga las palancas: la ruta de la prueba no puede
        # gastar más de lo que hay.
        assert fortaleza(p) > 0, r.estado()
    r.foto("la-escotilla")

    r.empezar("la escotilla y el final de la historia de Eisen")
    r.caminar_a(LA_ESCOTILLA, hasta=lambda p: p.mapa() != INTO_THE_MACHINE)
    jugar(r, "el final de la historia", lambda p: p.mapa() == LA_CASA_DE_VAGO
          and not p.byte("fade"), tope=120000,
          fotos={"el-final-de-la-historia-%d" % m: lambda p, m=m: p.mapa() == m
                 for m in (99, 100, 101, 102)})
    assert grupo_de(p) == [TALAN], r.estado()
    assert transiciones(p) == (MOSAICO, FUNDIDO), (
        "el 101 deja el mosaico para borrar al volver a Sorbe: %s. %s"
        % (transiciones(p), r.estado()))
    jugar(r, "Vago y Talan", lambda p: p.switch(SE_VAN_A_PARADISE)
          and not p.corriendo_una_pagina(), tope=60000,
          fotos={"vago-y-talan": lambda p: p.mapa() == LA_CASA_DE_VAGO})
    assert transiciones(p) == (FUNDIDO, FUNDIDO), (
        "la automática del 81 vuelve las dos transiciones al fundido: %s. %s"
        % (transiciones(p), r.estado()))
    assert grupo_de(p) == [TALAN, ARDEN], r.estado()

    r.empezar("de Sorbe al puente")
    r.viajar(EL_MUNDO)
    r.esperar_el_control()
    sin_encuentros(p)
    r.viajar(EL_PUENTE)
    jugar(r, "la llegada al puente", lambda p: not p.corriendo_una_pagina()
          and not p.byte("fade"))
    r.foto("el-puente")

    r.empezar("el plan de Arden")
    r.caminar_a(EL_PLAN_DE_ARDEN, hasta=lambda p: p.corriendo_una_pagina())
    r.elegir(VAMOS)
    jugar(r, "la bajada", lambda p: p.mapa() == DEBAJO_DEL_PUENTE
          and not p.corriendo_una_pagina() and not p.byte("fade"))
    r.foto("debajo-del-puente")

    r.empezar("por debajo del puente")
    for actor in grupo_de(p):
        p.poner_hp(actor, 999)
    crujidos = {(e.x, e.y) for e in r.mundo.eventos(DEBAJO_DEL_PUENTE)
                if e.id in CRUJIDOS}
    fotos = {"la-pelea-debajo-del-puente": en_pelea_hace(120)}
    for celda in PISADOS:
        r.caminar_a(celda, evitar=crujidos - {celda})
        dejar_crujir(r, fotos)
    assert any(nombre in fotos for nombre, _, _ in r.fotos), (
        "debajo del puente no hubo ninguna pelea. %s" % r.estado())
    r.caminar_a(DEL_OTRO_LADO, evitar=crujidos,
                hasta=lambda p: p.mapa() != DEBAJO_DEL_PUENTE)
    jugar(r, "del otro lado", lambda p: p.mapa() == EL_MUNDO
          and not p.corriendo_una_pagina() and not p.byte("fade"))
    assert p.switch(CRUZARON), r.estado()
    r.foto("del-otro-lado")

    r.empezar("hasta el bosque")
    sin_encuentros(p)
    r.caminar_a(EL_BOSQUE, tope=8000, hasta=lambda p: p.corriendo_una_pagina())

    r.empezar("la entrada al bosque")
    # Los mensajes de la entrada, de a uno: los dos de Talan, ya en el 310.
    mensajes = []

    def contar(p):
        mensajes.append((p.mapa(), grupo_de(p), p.heroe()))
        return False
    jugar(r, "la llegada al bosque",
          lambda p: len(mensajes) >= 2 and not p.corriendo_una_pagina()
          and not p.byte("fade"),
          fotos={"contar": contar,
                 "el-bosque": lambda p: len(mensajes) == 1})
    assert len(mensajes) == 2 and all(
        m == (TANGLE, [TALAN, ARDEN], EN_TANGLE) for m in mensajes), (
        "a la entrada del bosque salen dos mensajes de Talan, ya en el %d en "
        "%s y con el grupo de Talan y Arden; salieron %s. %s"
        % (TANGLE, EN_TANGLE, mensajes, r.estado()))

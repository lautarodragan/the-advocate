"""Lo que el tramo de los Neon Vipers deja afuera por tocar A sin mover el cursor.

`test_recorrido_vipers_golden.py` juega la cinemática del `NV hotplate` por
"Yes, I'll do it!", que es la opción de arriba. Esto juega las otras tres
cosas de la misma zona, y las tres necesitan `Recorrido.elegir`:

    el no       la rama de "No, it's a waste of time!": Talan baja caminando
                hasta la reja, salta dos celdas, el `Teleport` lo deja en el
                mapa 8 y ahí salta **cinco** —de los movimientos más rápidos
                del juego—, justo al lado del Bum, cuya página automática
                arranca con el switch 36 que prende la rama
    la reja     el evento 1 del mapa 12, en (1,47): "Don't Bother" primero
                —Talan se queja y da un paso atrás— y "Climb the Fence"
                después, que es el mismo par de saltos que el no
    el mapa 14  al que no lleva **ninguna** de las dos ramas: se entra con el
                Idol of the Streets —ítem 90— y el switch 53, por la página 2
                de la puerta del HQ, que deja al héroe sobre el hotplate, cuya
                página 2 es automática y termina en un `Teleport` al 14. La
                cinemática del 14 corre sola y termina en el 16

Los saltos largos son el caso extremo de `jump_advance_hero`, y el salto
colgado de la semana del 2026-09-22 vivía justo ahí: cada salto se cobra con el
vigilante de `sin_quedarse_en_el_aire` y con `route_jump` en cero al final. El
de cinco celdas, medido tick por tick el 2026-09-26 a la velocidad 4, que es la
del héroe acá: once vueltas de 7 u 8 px, con la cámara detrás a lo mismo, así
que **tampoco** llega a los más de 8 px por vuelta que hacen falta para dejar
una fila sin redibujar —ver `test_recorrido_vipers_golden.py`, "no alcanza,
medido"—.

**El salto de dos celdas sobre la reja no se da, y está bien.** La ruta es
`begin_jump`, `through`, abajo, abajo, `end_jump`, y el `through` queda
**adentro** del salto: RM2k lo ignora ahí —`Game_Character` sólo suma los
movimientos y los giros entre el par, y el resto se consume sin efecto—, así
que salta sin atravesar, a (1,49), que no es pisable, y el salto falla. La ROM
lo saltea igual —`accumulate_jump` no mira la 36—, el héroe se queda en (1,47) y
el `Teleport` lo saca de ahí. Por eso no se le cobra la celda.

**No se arranca desde la calle.** El camino del caño y los techos ya lo juega
el tramo del "Yes"; acá se arranca con `ir_al_mapa` en el techo del HQ y se
entra por la puerta, que es la parte que cambia entre las ramas: su página 2
es la del Idol.

Las capturas van a `pruebas/snapshots/playthrough/vipers-otras-ramas/` y **no
están bendecidas**: son para que taro las mire. Hasta entonces pasan siempre, y
lo que cobra esta prueba es la RAM.
"""

from recorrido import A_CADA
from port import events

# Los mismos de `test_recorrido_vipers_golden.py`, que se repiten porque
# ninguna prueba importa de otra —ver `pruebas/README.md`—.
VA_A_TRABAJAR = 24

# Talan, que es el que juega esta parte. Hace falta ponerlo porque la partida
# que arranca por "Begin the Story" tiene de líder a DummyHero —el actor 10—,
# que no tiene gráfico, y quien lo cambia es la apertura, que acá no se juega:
# sin esto las fotos salen sin héroe. Y la página 2 del hotplate lo **saca** del
# grupo, así que para ella no es decoración.
TALAN = 14
EN_EL_TECHO_DEL_HQ = (64, 17)
LA_PUERTA_DEL_HQ = (71, 14)
# El `Teleport` de la puerta deja al héroe en (9,1), y la ruta que sigue lo hace
# caer cinco celdas: es donde toma el control.
ADENTRO_DEL_HQ = (9, 6)
EL_HOTPLATE = (5, 39)

# Las dos opciones de la cinemática: "Yes, I'll do it!" / "No, it's a waste of
# time!". Y las de la reja: "Climb the Fence" / "Don't Bother".
NO_ES_UNA_PERDIDA_DE_TIEMPO = 1
TREPAR_LA_REJA = 0
NO_VALE_LA_PENA = 1

# Lo que prende el "No": el 38 es el que después le hace decir al caño "No way...
# I'm not going back to the Neon Vipers", y el 36 es el que arranca la página
# automática del Bum —el evento 10 del mapa 8, en (38,55)— que la apaga ella
# misma al terminar. El 39 lo apagan las dos ramas y la reja.
SE_PELEO_CON_LOS_VIPERS = 38
EL_BUM_LO_VE_CAER = 36
EL_VIGIA_DEL_HQ = 39

# La reja, que es un evento de la capa de abajo: se le habla parado encima.
LA_REJA = (1, 47)
# "Don't Bother" termina con la ruta `[0]` del héroe: un paso para arriba.
UN_PASO_ATRAS = (1, 46)

# Adónde deja el `Teleport` de la reja —el mismo en la rama del no—, y dónde
# termina el salto de cinco celdas para abajo que viene después.
AFUERA_DE_LA_REJA = (40, 51)
DESPUES_DEL_SALTO = (40, 56)

# El Idol of the Streets y el switch que prende quien lo consiguió.
EL_IDOL = 90
TIENE_EL_IDOL = 53
# Y lo que prende el final de la cinemática del mapa 14, que es lo último que
# hace antes de irse al 16, en (53,7).
PASO_POR_EL_14 = 73
EL_MAPA_16 = (16, 53, 7)


def sin_quedarse_en_el_aire(partida, a_cada=A_CADA):
    """Un vigilante para `esperar(mirando=...)`: el héroe aterriza siempre.

    Es el de `test_recorrido_vipers_golden.py`: tolera lo que dura un salto a
    la velocidad que el héroe tenga, contado de los símbolos de la ROM, y una
    muestra más. Un salto de cinco celdas dura lo mismo que uno en el lugar —el
    arco es fijo y lo que cambia es cuánto se avanza por vuelta—, así que el
    tope no depende del salto.
    """
    seguidas = [0]

    def mirar(p):
        if not p.byte("route_jump"):
            seguidas[0] = 0
            return
        dura = -(-partida.simbolos["JUMP_STEP"]
                 // events.JUMP_PER_SPEED[p.velocidad_del_heroe() - 1])
        tope = -(-dura // a_cada) + 1
        seguidas[0] += 1
        assert seguidas[0] <= tope, (
            "el héroe lleva %d muestras de %d ticks en el aire y un salto dura "
            "%d: le queda %d de arco con la ruta en %d de %d órdenes"
            % (seguidas[0], a_cada, dura, p.byte("route_jump"),
               p.byte("route_i"), p.byte("route_n")))

    return mirar


def entrar_al_hq(r):
    """Del techo del HQ, por la puerta de arriba, hasta que el jugador tiene
    el control adentro. La página de la puerta la eligen los switches: sin el
    Idol es la 0."""
    r.empezar("el techo del HQ")
    r.p.poner_grupo(TALAN)
    r.p.ir_al_mapa(8, *EN_EL_TECHO_DEL_HQ)
    r.empezar("entrar al HQ por la puerta de arriba")
    r.activar(LA_PUERTA_DEL_HQ, lambda p: p.mapa() == 12, tope=2000)
    r.esperar_el_control(tope=4000)
    assert r.celda() == ADENTRO_DEL_HQ, r.estado()


def aterrizar_afuera(r, que):
    """Del `Teleport` de la reja al control en el mapa 8: el salto de cinco
    celdas, y la página automática del Bum, que arranca con el switch 36 que
    prende la reja y lo apaga ella misma al terminar. Así que "el Bum habló" es
    haber visto el 36 prendido y después apagado, sin página corriendo."""
    r.esperar(que, lambda p: p.mapa() == 8, tope=4000,
              mirando=sin_quedarse_en_el_aire(r.p))
    aire = sin_quedarse_en_el_aire(r.p)
    vio = []

    def mirando(p):
        aire(p)
        if p.switch(EL_BUM_LO_VE_CAER):
            vio.append(p.cuadro)
    r.esperar("que el salto de cinco celdas termine y el Bum hable",
              lambda p: vio and not p.switch(EL_BUM_LO_VE_CAER)
              and not p.corriendo_una_pagina(), tope=4000, mirando=mirando)
    assert r.celda() == DESPUES_DEL_SALTO, (
        "el salto de la reja termina cinco celdas abajo de %s. %s"
        % (AFUERA_DE_LA_REJA, r.estado()))
    assert r.p.byte("route_jump") == 0, r.estado()
    assert r.p.palabra("hero_y") == DESPUES_DEL_SALTO[1] * 16, (
        "el héroe quedó en la celda pero no en su pixel: hero_y es %d. %s"
        % (r.p.palabra("hero_y"), r.estado()))
    assert not r.p.switch(EL_VIGIA_DEL_HQ), r.estado()


def test_la_rama_del_no_baja_hasta_la_reja_y_salta_afuera(recorrido):
    """La cinemática por "No, it's a waste of time!": elegida con el cursor
    abajo, y comprobada por lo que sólo esa rama hace."""
    r = recorrido("vipers-otras-ramas", switch=[VA_A_TRABAJAR])
    entrar_al_hq(r)

    r.empezar("bajar hasta el hotplate de los Neon Vipers")
    r.caminar_a(EL_HOTPLATE, tope=8000,
                hasta=lambda p: p.corriendo_una_pagina())
    assert r.celda() == EL_HOTPLATE, r.estado()

    r.empezar("la cinemática, hasta la elección")
    r.marcar(NO_ES_UNA_PERDIDA_DE_TIEMPO, tope=8000)
    r.foto("la-eleccion-con-el-no-marcado")
    r.confirmar()
    assert not r.p.switch(SE_PELEO_CON_LOS_VIPERS), (
        "el switch 38 lo prende la rama del no recién después de sus "
        "mensajes, y ya estaba prendido. %s" % r.estado())

    r.empezar("la rama del no: bajar caminando hasta la reja y saltar")
    aterrizar_afuera(r, "que la rama del no salga por la reja")
    assert r.p.switch(SE_PELEO_CON_LOS_VIPERS), (
        "llegó afuera sin el switch 38: no corrió la rama del no. %s"
        % r.estado())
    r.foto("afuera-de-la-reja")


def test_la_reja_primero_no_y_despues_si(recorrido):
    """El evento 1 del mapa 12, con sus dos opciones. Se llega sin pisar el
    hotplate: el camino corto de la puerta a la reja pasa por la columna 3, y
    el hotplate está en la 5."""
    r = recorrido("vipers-la-reja", switch=[VA_A_TRABAJAR])
    entrar_al_hq(r)

    r.empezar("bajar hasta la reja")
    r.caminar_a(LA_REJA, tope=8000)
    assert not r.p.switch(SE_PELEO_CON_LOS_VIPERS), r.estado()

    r.empezar("la reja: Don't Bother")
    r.activar(LA_REJA, lambda p: p.corriendo_una_pagina())
    r.marcar(NO_VALE_LA_PENA)
    r.foto("la-reja-con-don-t-bother-marcado")
    r.confirmar()
    r.esperar_el_control()
    assert (r.p.mapa(), r.celda()) == (12, UN_PASO_ATRAS), (
        "\"Don't Bother\" termina con un paso para arriba. %s" % r.estado())

    r.empezar("la reja: Climb the Fence")
    r.activar(LA_REJA, lambda p: p.corriendo_una_pagina())
    r.elegir(TREPAR_LA_REJA)
    aterrizar_afuera(r, "que la reja teletransporte afuera")
    assert not r.p.switch(SE_PELEO_CON_LOS_VIPERS), (
        "el switch 38 es de la rama del no de la cinemática, no de la reja. %s"
        % r.estado())
    r.foto("afuera-de-la-reja")


def test_con_el_idol_la_puerta_lleva_al_mapa_14(recorrido):
    """El único camino del 12 al 14, y la cinemática del 14 entera."""
    r = recorrido("vipers-el-idol", switch=[VA_A_TRABAJAR, TIENE_EL_IDOL])
    r.p.consola.write_ram(r.p.simbolos["FAR_ITEMS"] + EL_IDOL, [1])

    r.empezar("el techo del HQ")
    r.p.poner_grupo(TALAN)
    r.p.ir_al_mapa(8, *EN_EL_TECHO_DEL_HQ)
    r.empezar("entrar al HQ con el Idol")
    r.activar(LA_PUERTA_DEL_HQ, lambda p: p.mapa() == 12, tope=2000)

    r.empezar("la página 2 del hotplate, que lleva al mapa 14")
    r.esperar("el mapa 14", lambda p: p.mapa() == 14, tope=8000,
              mirando=sin_quedarse_en_el_aire(r.p))
    assert not r.p.item(EL_IDOL), (
        "la página 2 del hotplate se queda con el Idol antes de irse. %s"
        % r.estado())
    r.asentar()
    r.foto("el-mapa-14")

    r.empezar("la cinemática de los Lazer Teeth, hasta el mapa 16")
    r.esperar("el mapa 16", lambda p: p.mapa() == EL_MAPA_16[0], tope=20000,
              mirando=sin_quedarse_en_el_aire(r.p))
    # Se mira apenas llega y no con el control: el 16 tiene su propia
    # cinemática automática, que sigue sola hasta el mapa 17.
    assert r.celda() == EL_MAPA_16[1:], r.estado()
    r.esperar_switch(PASO_POR_EL_14, tope=200, a_cada=None)
    r.foto("el-mapa-16")

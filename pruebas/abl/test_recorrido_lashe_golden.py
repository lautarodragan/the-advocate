"""Lashe City con auto: los cuatro sectores desde el 36, y el fin de la demo.

Es el hito 1 de `workflow/tasks/*/lashe-city-hasta-la-carrera.md`. El mapa 36,
`LasheCityVehicle`, es una pantalla negra con el auto y una sola cosa que
hacer: el evento 3, automático, que la primera vez —switch 148— dice qué hay
que hacer según el compañero y abre `Sector 32 / 33 / 34 / 35`. Cada opción
salta a su sector y **la página sigue corriendo allá**: saca a `DummyHero`
—el 10— y mete a Talan y al compañero. En cada sector, subirse al auto apaga
el 148, prende el 149, deja a `DummyHero` solo y vuelve al 36, donde manda la
página 2: la misma elección, y —con lo que pide la rama del compañero— la
pregunta de irse de la ciudad, que en el original lleva a la carrera y acá
termina la demo (el 36 está forkeado: `parches/manual/mapas/Map0036.json`).

    la elección   36 -> 48 (6,55), 47 (8,36), 38 (49,66) y 37 (19,32), con el
                  auto rojo; con el azul, una columna a la derecha
    el pad        37, la puerta de Talan -> 39 (9,11); la computadora prende
                  el 151, que es lo que abre la puerta de salida -> 37 (10,31)
    el HQ         38, el caño —eventos 20 y 21, sólo con Arden— -> (2,10) del
                  mismo 38; la escena de los Vipers (evento 25) prende el 168,
                  Arden vuelve al grupo hablándole, el susurro prende el 169, y
                  la salida del evento 26 vuelve a la calle en (73,65)
    el 33         47, los guardias de la Agency (evento 15): con Saldra, la
                  escena entera con su `PanScreen`, y el 181; la tienda del 56
                  por el evento 10 y de vuelta
    el fin        36 con el 161 y el 169: "Stay" sigue en la ciudad, y la vez
                  siguiente "We've got to get out of here" muestra el cartel
                  del fin de la demo y vuelve al título

**La partida arranca por donde la arranca el juego**: la página 5 del evento 1
del mapa 4, que es la charla en el auto de después de escaparse del 33 y corre
con el 132. Pasa por la cinemática del 34 —el director y Kersh— y llega al 36
con el 148 prendido. Salvo el HQ y los guardias, que arrancan con
`ir_al_mapa` en su sector: lo que prueban es la escena, no el viaje.

Las capturas van a `pruebas/snapshots/playthrough/lashe-*/` y **no están
bendecidas**: son para que taro las mire. Hasta entonces pasan siempre, y lo
que cobra esta prueba es la RAM.
"""

from batalla import grupo_de

# Los switches del juego que mueven esto. El 132 es "ya tiene el auto", y es
# el que hace correr la charla del mapa 4; el 130 es el auto rojo.
TIENE_EL_AUTO = 132
AUTO_ROJO = 130
# El compañero, que lo eligió el jugador en la escena de los Vipers (el 54,
# Arden) o en la de los Lazer Teeth (el 56, Saldra).
CON_ARDEN = 54
CON_SALDRA = 56
# El 36 la primera vez, y las siguientes: los prenden y apagan los autos de
# los sectores.
PRIMERA_VEZ = 148
VOLVIO_AL_AUTO = 149
# Lo que prende la computadora del 39, y lo que prende entrar por la puerta del
# 37 —y la computadora apaga—.
VIO_LA_COMPUTADORA = 151
ENTRO_AL_PAD = 153
# El vidcast del vecino, que es el hito 2 y acá se prende a mano.
VIO_EL_VIDCAST = 161
# El HQ de los Vipers con Arden: el caño, la escena y el susurro.
TOMO_EL_ATAJO = 167
VIO_EL_HQ_VACIO = 168
EL_SUSURRO_DE_ARDEN = 169
# Los guardias de la Agency en el Sector 33.
VIO_A_LOS_GUARDIAS = 181
# "We've got to get out of here", y el auto de la Agency que los sigue.
SE_VAN = 182
LOS_SIGUE_LA_AGENCY = 238

DUMMY_HERO = 10
TALAN = 14
ARDEN = 15
SALDRA = 17
AG7 = 18

# Las opciones de la elección, desde cero, con adónde lleva cada una con el
# auto rojo y dónde está el auto rojo de ese sector: el héroe llega a la celda
# de arriba y se sube hablándole.
SECTOR_32, SECTOR_33, SECTOR_34, SECTOR_35 = range(4)
SECTORES = {
    SECTOR_32: (48, (6, 55), (6, 56)),
    SECTOR_33: (47, (8, 36), (8, 37)),
    SECTOR_34: (38, (49, 66), (49, 67)),
    SECTOR_35: (37, (19, 32), (19, 33)),
}
EL_36 = (36, 10, 9)

# El pad de Talan: la puerta del 37 y la de salida del 39, la computadora, y
# adónde deja cada `Teleport`.
LA_PUERTA_DE_TALAN = (10, 30)
ADENTRO_DEL_PAD = (9, 11)
LA_COMPUTADORA = (11, 4)
LA_PUERTA_DEL_PAD = (9, 12)
AFUERA_DEL_PAD = (10, 31)

# El HQ del 38: el caño, adónde deja, la escena, Arden —el evento 19, que la
# escena deja en (19,21)— y la salida.
EL_CANO = (57, 56)
ARRIBA_DEL_CANO = (2, 10)
LA_ESCENA_DEL_HQ = (6, 18)
ARDEN_EN_EL_HQ = 19
LA_SALIDA_DEL_HQ = (1, 21)
DE_VUELTA_EN_LA_CALLE = (73, 65)

# El Sector 33: los guardias, adónde los deja la huida de Saldra, y la tienda.
LOS_GUARDIAS = (32, 28)
DESPUES_DE_LA_HUIDA = (5, 36)
LA_PUERTA_DE_LA_TIENDA = (3, 34)
ADENTRO_DE_LA_TIENDA = (9, 12)
LA_SALIDA_DE_LA_TIENDA = (9, 14)
AFUERA_DE_LA_TIENDA = (3, 35)

# "Stay in the city a little longer" / "We've got to get out of here".
QUEDARSE, IRSE = 0, 1


def llegar_al_36(r):
    """De la charla del auto del mapa 4, por la cinemática del 34, hasta el 36
    con la elección por abrirse. Se corta al llegar al mapa y no antes de la
    elección: la paciencia de `esperar` toca A, y un A con la elección abierta
    se lleva la opción de arriba."""
    r.empezar("la charla del auto y la cinemática del 34")
    r.esperar("el mapa 36", lambda p: p.mapa() == 36, tope=20000)
    r.asentar()
    assert r.p.switch(PRIMERA_VEZ), (
        "el 36 se abre la primera vez con el 148, que prende el 34. %s"
        % r.estado())


def ir_al_sector(r, opcion, companero, ag7=False):
    """Elige el sector en el 36 abierto y espera el control allá. Comprueba
    el mapa, la celda del `Teleport` y el grupo que arma la página al llegar,
    que es lo que corre **en el sector** y no en el 36: Talan, el compañero,
    y AG7-17 detrás si está el 150."""
    mapa, llegada, _auto = SECTORES[opcion]
    r.empezar("el 36: elegir el sector %d" % (32 + opcion))
    r.elegir(opcion)
    r.esperar("el mapa %d" % mapa, lambda p: p.mapa() == mapa, tope=2000)
    r.esperar_el_control()
    assert r.celda() == llegada, (
        "el `Teleport` al mapa %d deja al héroe en %s. %s"
        % (mapa, llegada, r.estado()))
    grupo = ([TALAN] + ([companero] if companero else [])
             + ([AG7] if ag7 else []))
    assert grupo_de(r.p) == grupo, (
        "al llegar al sector la página saca a DummyHero y mete a Talan y al "
        "compañero: el grupo tendría que ser %s y es %s. %s"
        % (grupo, grupo_de(r.p), r.estado()))


def subir_al_auto(r, opcion):
    """Del sector al 36 por el auto rojo, y lo que dejó al subir."""
    mapa, _llegada, auto = SECTORES[opcion]
    r.empezar("el sector %d: subir al auto" % (32 + opcion))
    r.activar(auto, lambda p: p.mapa() == 36, tope=4000)
    r.asentar()
    assert r.p.switch(VOLVIO_AL_AUTO) and not r.p.switch(PRIMERA_VEZ), (
        "el auto apaga el 148 y prende el 149. %s" % r.estado())
    assert grupo_de(r.p) == [DUMMY_HERO], (
        "el auto deja a DummyHero solo, y el grupo es %s. %s"
        % (grupo_de(r.p), r.estado()))


def irse_termina_la_demo(r):
    """Con la pregunta de irse abierta en el 36 —o por abrirse—, "We've got to
    get out of here": el 182, el cartel del fin de la demo y la vuelta al
    título. Lo usan también los cierres de las tres ramas, en
    `test_recorrido_lashe_cierre_golden.py`."""
    r.empezar("el 36: irse")
    r.elegir(IRSE)
    # El cartel y el reinicio. Por cuadros de hardware y no por ticks: la
    # pantalla de título no hace correr `vueltas`, así que esperar un tick ahí
    # se colgaría. El reinicio se ve en los switches, que `reset` borra.
    p = r.p
    vio_el_cartel = False
    for _ in range(3000):
        if not p.switch(VOLVIO_AL_AUTO):
            break
        if p.switch(SE_VAN) and p.byte("msg_abierto") and not vio_el_cartel:
            # El mensaje de Talan va antes de prender el 182, así que éste es
            # el cartel. Se lo deja componer para la foto: `msg_estado` en 1
            # es "componiendo".
            vio_el_cartel = True
            for _ in range(120):
                if p.byte("msg_estado") != 1:
                    break
                p.consola.correr(1)
            r.foto("el-fin-de-la-demo", asentar=False)
        p.consola.apretar("a")
        p.consola.correr(2)
        p.consola.apretar()
        p.consola.correr(6)
    else:
        raise AssertionError("después de \"We've got to get out of here\" la "
                             "partida no volvió al título. %s" % r.estado())
    assert vio_el_cartel, (
        "el 182 se prende antes del cartel del fin, y no hubo mensaje con él "
        "prendido. %s" % r.estado())
    p.consola.correr(p.simbolos["BOOT_CUADROS"] + 60)
    r.foto("el-titulo-despues-del-fin", asentar=False)


def test_la_eleccion_del_36_lleva_a_los_cuatro_sectores(recorrido):
    """Con Arden, los cuatro sectores uno detrás de otro: el primero por la
    página 1 del 36 y los otros tres por la 2, que es la que se traba si no
    compila. Uno por sector, con su foto."""
    r = recorrido("lashe-sectores", switch=[TIENE_EL_AUTO, AUTO_ROJO,
                                            CON_ARDEN])
    llegar_al_36(r)
    r.foto("el-36-la-primera-vez")
    for opcion in (SECTOR_35, SECTOR_34, SECTOR_33, SECTOR_32):
        ir_al_sector(r, opcion, ARDEN)
        r.foto("sector-%d" % (32 + opcion))
        subir_al_auto(r, opcion)
    assert not r.p.switch(LOS_SIGUE_LA_AGENCY), (
        "sin el 161 y el 169 la página 2 no pregunta si irse. %s" % r.estado())


def test_el_pad_de_talan_con_auto(recorrido):
    """El Sector 35 por la puerta de Talan: el 39, que es el 7 celda por celda,
    no deja salir hasta mirar la computadora."""
    r = recorrido("lashe-pad", switch=[TIENE_EL_AUTO, AUTO_ROJO])
    llegar_al_36(r)
    ir_al_sector(r, SECTOR_35, None)

    r.empezar("la puerta de Talan")
    r.activar(LA_PUERTA_DE_TALAN, lambda p: p.mapa() == 39, tope=4000)
    r.esperar_el_control()
    assert r.celda() == ADENTRO_DEL_PAD, r.estado()
    assert r.p.switch(ENTRO_AL_PAD), r.estado()
    r.foto("el-pad-de-talan")

    r.empezar("la computadora")
    r.activar(LA_COMPUTADORA, lambda p: p.switch(VIO_LA_COMPUTADORA),
              tope=4000)
    r.esperar_el_control()
    assert not r.p.switch(ENTRO_AL_PAD), r.estado()

    r.empezar("salir del pad")
    r.activar(LA_PUERTA_DEL_PAD, lambda p: p.mapa() == 37, tope=4000)
    r.esperar_el_control()
    assert r.celda() == AFUERA_DEL_PAD, r.estado()
    subir_al_auto(r, SECTOR_35)


def test_el_hq_de_los_vipers_por_el_cano_con_arden(recorrido):
    """El Sector 34 con Arden: el caño, la escena del HQ vacío, Arden que
    vuelve al grupo, el susurro que la página 2 del 36 pide, y la salida."""
    r = recorrido("lashe-hq", switch=[CON_ARDEN, AUTO_ROJO])
    r.p.poner_grupo(TALAN, ARDEN)
    r.p.ir_al_mapa(38, *SECTORES[SECTOR_34][1])
    r.esperar_el_control()
    el_hq_por_el_cano(r)


def el_hq_por_el_cano(r):
    """Del 38 con el control, Talan y Arden, hasta la calle de vuelta del HQ
    con el 169. Lo usa también el cierre de la rama de Arden."""
    r.empezar("el caño")
    r.caminar_a(EL_CANO, tope=4000, hasta=lambda p: p.corriendo_una_pagina())
    r.esperar("el atajo de Arden", lambda p: p.switch(TOMO_EL_ATAJO),
              tope=4000)
    r.esperar_el_control()
    assert (r.p.mapa(), r.celda()) == (38, (ARRIBA_DEL_CANO[0],
                                            ARRIBA_DEL_CANO[1] + 3)), (
        "el caño deja al héroe en %s y la ruta lo baja tres celdas. %s"
        % (ARRIBA_DEL_CANO, r.estado()))
    assert grupo_de(r.p) == [TALAN], (
        "Arden se adelanta: el caño la saca del grupo. %s" % r.estado())
    r.foto("arriba-del-cano")

    r.empezar("la escena del HQ vacío")
    r.caminar_a(LA_ESCENA_DEL_HQ, tope=4000,
                hasta=lambda p: p.corriendo_una_pagina())
    r.esperar("el 168", lambda p: p.switch(VIO_EL_HQ_VACIO), tope=4000)
    r.esperar_el_control()
    r.foto("el-hq-vacio")

    r.empezar("hablarle a Arden")
    arden = r.p.evento(ARDEN_EN_EL_HQ - 1)
    r.activar(arden, lambda p: ARDEN in grupo_de(p),
              tope=4000)
    r.esperar_el_control()

    r.empezar("el susurro")
    r.caminar_a(LA_ESCENA_DEL_HQ, tope=4000,
                hasta=lambda p: p.switch(EL_SUSURRO_DE_ARDEN))
    r.esperar("el 169", lambda p: p.switch(EL_SUSURRO_DE_ARDEN), tope=4000)
    r.esperar_el_control()

    r.empezar("la salida del HQ")
    r.caminar_a(LA_SALIDA_DEL_HQ, tope=4000,
                hasta=lambda p: p.corriendo_una_pagina())
    r.esperar("la calle", lambda p: p.palabra("tile_y") > 33, tope=4000)
    r.esperar_el_control()
    assert r.p.mapa() == 38 and r.celda()[1] > 33, (
        "la salida del HQ vuelve a la calle, cerca de %s. %s"
        % (DE_VUELTA_EN_LA_CALLE, r.estado()))
    r.foto("de-vuelta-en-la-calle")


def test_los_guardias_del_sector_33_con_saldra(recorrido):
    """El Sector 33 con Saldra: la tienda del 56 y de vuelta, y los guardias de
    la Agency, que es la escena que la página 2 del 36 le pide a esta rama."""
    r = recorrido("lashe-guardias", switch=[CON_SALDRA, AUTO_ROJO])
    r.p.poner_grupo(TALAN, SALDRA)
    r.p.ir_al_mapa(47, *SECTORES[SECTOR_33][1])
    r.esperar_el_control()
    la_tienda_y_los_guardias(r, [TALAN, SALDRA])


def la_tienda_y_los_guardias(r, grupo):
    """Del 47 con el control y Saldra, la tienda del 56 y de vuelta, y los
    guardias hasta el 181. Lo usa también el cierre de la rama de Saldra, que
    puede llevar a AG7 además: `grupo` es el que tiene que quedar."""
    r.empezar("la tienda del Sector 33")
    r.caminar_a(LA_PUERTA_DE_LA_TIENDA, tope=4000,
                hasta=lambda p: p.mapa() == 56)
    r.esperar("el mapa 56", lambda p: p.mapa() == 56, tope=400)
    r.esperar_el_control()
    assert r.celda() == ADENTRO_DE_LA_TIENDA, r.estado()
    r.foto("la-tienda")
    r.caminar_a(LA_SALIDA_DE_LA_TIENDA, tope=4000,
                hasta=lambda p: p.mapa() == 47)
    r.esperar("el mapa 47", lambda p: p.mapa() == 47, tope=400)
    r.esperar_el_control()
    assert r.celda() == AFUERA_DE_LA_TIENDA, r.estado()

    r.empezar("los guardias")
    r.caminar_a(LOS_GUARDIAS, tope=6000,
                hasta=lambda p: p.corriendo_una_pagina())
    r.esperar("el 181", lambda p: p.switch(VIO_A_LOS_GUARDIAS), tope=20000)
    r.esperar_el_control()
    assert r.celda() == DESPUES_DE_LA_HUIDA, (
        "la huida de Saldra termina con un `Teleport` a %s. %s"
        % (DESPUES_DE_LA_HUIDA, r.estado()))
    assert grupo_de(r.p) == grupo, r.estado()
    r.foto("despues-de-los-guardias")


def test_irse_de_la_ciudad_termina_la_demo(recorrido):
    """Con la rama de Arden cumplida —el 161 y el 169—, la página 2 del 36
    pregunta si irse. "Stay" sigue en la ciudad; la vez siguiente, con el 238
    ya prendido, "We've got to get out of here" muestra el cartel del fin de
    la demo y el `ReturntoTitleScreen` del fork vuelve al título."""
    r = recorrido("lashe-fin", switch=[TIENE_EL_AUTO, AUTO_ROJO, CON_ARDEN,
                                       VIO_EL_VIDCAST, EL_SUSURRO_DE_ARDEN])
    llegar_al_36(r)
    ir_al_sector(r, SECTOR_35, ARDEN)
    subir_al_auto(r, SECTOR_35)

    r.empezar("el 36: quedarse")
    r.marcar(QUEDARSE)
    assert r.p.switch(LOS_SIGUE_LA_AGENCY), (
        "la pregunta de irse viene después de prender el 238. %s" % r.estado())
    r.foto("irse-o-quedarse")
    r.confirmar()
    ir_al_sector(r, SECTOR_35, ARDEN)
    assert not r.p.switch(SE_VAN), r.estado()
    subir_al_auto(r, SECTOR_35)

    irse_termina_la_demo(r)


# La puerta de arriba de la casa de empeño del 37: el evento 11, `PawnDoorTop`,
# un tile opaco de `BLchp1` que la regla de `eventos_horneables` alcanza, pero
# que el reparto de paletas dibuja con una prestada. Horneado se vería con los
# colores de verdad y el sprite con los prestados, así que va dibujado.
LA_PUERTA_DE_LA_CASA_DE_EMPENO = (67, 29)


def test_la_puerta_de_la_casa_de_empeno_no_se_hornea(partida):
    """La fila del evento 11 del 37 se dibuja: no está escondida como las de
    los horneados. Las filas se buscan por la celda, en pixeles —el +0 y el
    +2 de `npc_buf`—, porque el conversor no las ordena como los eventos, y
    el +14 es si se dibuja. Hasta el 2026-09-26 el conversor se plantaba acá."""
    una = partida(switch=[AUTO_ROJO])
    una.poner_grupo(TALAN)
    una.ir_al_mapa(37, 67, 31)
    paso = una.simbolos["NPC_STRIDE"]
    total = una.palabra("npc_total") // paso
    filas = una.consola.ram(una.simbolos["npc_buf"], total * paso)
    x, y = (16 * c for c in LA_PUERTA_DE_LA_CASA_DE_EMPENO)
    visibles = [filas[k * paso + 14] for k in range(total)
                if filas[k * paso] | filas[k * paso + 1] << 8 == x
                and filas[k * paso + 2] | filas[k * paso + 3] << 8 == y]
    assert visibles == [1], (
        "la puerta de %s tendría que ser una fila dibujada, y las filas en esa "
        "celda son %s" % (LA_PUERTA_DE_LA_CASA_DE_EMPENO, visibles))

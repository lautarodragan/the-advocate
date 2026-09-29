"""Lashe City con auto, lo que más de un recorrido juega: el 36 y su
elección, los sectores, subir al auto, el HQ de los Vipers por el caño, la
tienda y los guardias del Sector 33, e irse a la carrera; y los switches y
actores con que arrancan las ramas.

Vivía en `abl/test_recorrido_lashe_golden.py` hasta el 2026-09-29, y de ahí lo
importaban los cierres, la carrera, Sorbe y el capítulo. Lo que el 36 es y
por qué cada tramo sale como sale lo sigue contando esa prueba.
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

# A dónde lleva irse: el `Teleport [49, 1, 26]` de la página 2 del 36.
LA_CARRERA = 49
LA_LARGADA = (1, 26)


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


def irse_lleva_a_la_carrera(r):
    """Con la pregunta de irse abierta en el 36 —o por abrirse—, "We've got to
    get out of here": el 182 y el `Teleport [49, 1, 26]` a la largada de la
    carrera, donde arranca su intro. Lo usan también los cierres de las tres
    ramas, en `test_recorrido_lashe_cierre_golden.py`; la carrera la juega
    `test_recorrido_carrera_golden.py`.

    Hasta el 2026-09-27 esto era el fin de la demo: la carrera no entraba y
    el 36 estaba forkeado para mostrar un cartel y volver al título."""
    r.empezar("el 36: irse")
    r.elegir(IRSE)
    r.esperar("el mapa 49", lambda p: p.mapa() == LA_CARRERA, tope=2000)
    assert r.p.switch(SE_VAN), (
        "\"We've got to get out of here\" prende el 182 antes de saltar. %s"
        % r.estado())
    assert r.celda() == LA_LARGADA, (
        "el `Teleport` del 36 deja al auto en %s. %s" % (LA_LARGADA,
                                                         r.estado()))
    r.asentar()
    r.foto("la-carrera")


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

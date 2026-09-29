"""Lashe City, de Stash a AG7-17 en el grupo: la escena de Stash, la planta
de reciclaje cayendo por sus pisos, el chip, el túnel y la página 5 de Stash.

Vivía en `abl/test_recorrido_lashe_planta_golden.py` hasta el 2026-09-29, y
de ahí lo importaba el cierre de la rama sin compañero. Lo que es cada piso y
cada pozo lo sigue contando esa prueba.
"""

from batalla import grupo_de
from consola import en_la_wram, indice_del_tema

import datos

# Cómo fue el Hover-Tram: el ladrón se llevó el ídolo.
ROBO_EL_IDOL = 71

# Lo que deja la planta: el chip agarrado, y el 205 del evento 13 del 61, que
# es lo que la página 5 de Stash pide junto con el chip.
AGARRO_EL_CHIP = 203
BAJO_POR_EL_TUNEL = 205
AG7_EN_EL_GRUPO = 150

TALAN = 14
AG7 = 18
EL_CHIP = 126

LA_PUERTA_DE_STASH = (3, 38)
AFUERA_DE_LA_PLANTA = (20, 47)
LA_PUERTA_DE_LA_PLANTA = (21, 22)
EN_EL_PISO_1 = (11, 13)
EL_POZO_DE_LA_ENTRADA = (4, 10)
LA_ESCALERA_DEL_OESTE = (1, 14)
AL_OESTE_DEL_PISO_1 = (1, 12)
LA_ESCALERA_AL_PISO_2 = (13, 0)
EN_EL_PISO_2 = (13, 3)
# El pozo del 62 que cae al 60 del lado de la escalera de la derecha, y el
# del 60 que cae al 61 por el mismo lado.
EL_POZO_DEL_PISO_2 = (17, 5)
EL_POZO_AL_PISO_0 = (17, 10)
LA_ESCALERA_DEL_PISO_0 = (14, 14)
DE_VUELTA_EN_EL_PISO_1 = (14, 12)
EL_POZO_AL_CHIP = (17, 13)
EL_MOTIVATOR_CHIP = (17, 12)
LA_SALIDA_AL_TUNEL = (18, 13)
LA_SALIDA_DEL_TUNEL = (4, 2)
AFUERA_DEL_TUNEL = (43, 51)
DESPUES_DEL_TUTORIAL = (3, 39)

RECALL_TO_LOCATION = 10830


def ranura(variable):
    return datos.ranuras_de_variable()[variable]


def sin_encuentros(r):
    """Apaga los encuentros al azar del mapa en que se está. El mapa los
    vuelve a prender al cargarse, así que va después de cada llegada."""
    r.p.consola.write_ram(en_la_wram(r.p.simbolos["ENC_BASE"]), [0, 0])


def pozos(r, mapa):
    """Las celdas de los pisos que se rompen del mapa: los eventos con una
    página que hace `RecallToLocation`. El `Mundo` no los ve como puertas,
    porque su destino sale de variables, así que se esquivan a mano."""
    return {(e.x, e.y) for e in r.mundo.eventos(mapa)
            if any(c.code == RECALL_TO_LOCATION
                   for pagina in e.pages for c in pagina.commands)}


def llegar(r, mapa, celda, que, tope=4000):
    """Espera el mapa, el control y la celda de llegada."""
    r.esperar(que, lambda p: p.mapa() == mapa, tope=tope)
    r.esperar_el_control()
    sin_encuentros(r)
    assert r.celda() == celda, (
        "%s deja al héroe en %s. %s" % (que, celda, r.estado()))


def caer(r, pozo, mapa, que):
    """Pisa el pozo y espera la caída al mapa de abajo, a la misma celda: el
    salto es a cinco filas más arriba y la ruta lo baja cinco."""
    desde = r.p.mapa()
    r.empezar(que)
    r.caminar_a(pozo, tope=6000, evitar=pozos(r, desde) - {pozo},
                hasta=lambda p: p.corriendo_una_pagina())
    llegar(r, mapa, pozo, "la caída al mapa %d" % mapa)


def entrar_a_lo_de_stash(r):
    r.empezar("la puerta de Stash")
    r.activar(LA_PUERTA_DE_STASH, lambda p: p.mapa() == 57, tope=6000)
    r.asentar()


def la_escena_de_stash(r):
    """De la puerta a la planta: la escena corre sola y termina en el 59."""
    entrar_a_lo_de_stash(r)
    r.foto("la-escena-de-stash")
    llegar(r, 59, AFUERA_DE_LA_PLANTA, "el final de la escena de Stash",
           tope=20000)


def de_stash_a_ag7(r):
    """Del 48 con el control y Talan solo, hasta AG7-17 en el grupo de vuelta
    del tutorial, en (3,39) del 48: la escena, la planta cayendo por tres
    pisos, el chip, el túnel, y la página 5 de Stash. Lo usa también el cierre
    de la rama sin compañero, en `test_recorrido_lashe_cierre_golden.py`."""
    la_escena_de_stash(r)
    r.foto("afuera-de-la-planta")

    r.empezar("la puerta de la planta")
    r.caminar_a(LA_PUERTA_DE_LA_PLANTA, tope=6000,
                hasta=lambda p: p.mapa() == 60)
    llegar(r, 60, EN_EL_PISO_1, "la puerta de la planta")
    r.foto("el-piso-1")

    caer(r, EL_POZO_DE_LA_ENTRADA, 61, "el pozo de la entrada")
    r.foto("caido-en-el-piso-0")
    assert r.p.variable(ranura(45)) == 61, r.estado()
    r.empezar("la escalera del oeste")
    r.caminar_a(LA_ESCALERA_DEL_OESTE, tope=6000, evitar=pozos(r, 61),
                hasta=lambda p: p.mapa() == 60)
    llegar(r, 60, AL_OESTE_DEL_PISO_1, "la escalera del oeste")

    r.empezar("la escalera al piso 2")
    r.caminar_a(LA_ESCALERA_AL_PISO_2, tope=6000, evitar=pozos(r, 60),
                hasta=lambda p: p.mapa() == 62)
    llegar(r, 62, EN_EL_PISO_2, "la escalera al piso 2")

    caer(r, EL_POZO_DEL_PISO_2, 60, "el pozo del piso 2")
    assert r.p.variable(ranura(46)) == 60, r.estado()
    caer(r, EL_POZO_AL_PISO_0, 61, "el pozo al piso 0")

    r.empezar("la escalera del piso 0")
    r.caminar_a(LA_ESCALERA_DEL_PISO_0, tope=6000, evitar=pozos(r, 61),
                hasta=lambda p: p.mapa() == 60)
    llegar(r, 60, DE_VUELTA_EN_EL_PISO_1, "la escalera del piso 0")
    caer(r, EL_POZO_AL_CHIP, 61, "el pozo al cuarto del chip")
    r.foto("el-cuarto-del-chip")

    r.empezar("el Motivator Chip")
    r.activar(EL_MOTIVATOR_CHIP, lambda p: p.item(EL_CHIP) == 1, tope=4000)
    r.esperar_el_control()
    assert r.p.switch(AGARRO_EL_CHIP), r.estado()

    r.empezar("la salida al túnel")
    r.caminar_a(LA_SALIDA_AL_TUNEL, tope=4000,
                hasta=lambda p: p.mapa() == 63)
    r.esperar("el túnel", lambda p: p.mapa() == 63, tope=2000)
    r.esperar_el_control()
    assert r.p.switch(BAJO_POR_EL_TUNEL), r.estado()
    r.foto("el-tunel")

    r.empezar("la salida del túnel")
    r.caminar_a(LA_SALIDA_DEL_TUNEL, tope=8000,
                hasta=lambda p: p.mapa() == 48)
    llegar(r, 48, AFUERA_DEL_TUNEL, "la salida del túnel")

    # La página 5 de Stash: AG7 en el grupo, el salto a (3,39), lo recordado
    # y el tutorial. La vuelta del tutorial es el `RecallToLocation`.
    entrar_a_lo_de_stash(r)
    r.empezar("AG7-17 y el tutorial")
    r.esperar("el 150", lambda p: p.switch(AG7_EN_EL_GRUPO), tope=6000)
    r.esperar("el tutorial", lambda p: p.mapa() == 164, tope=6000)
    recordado = tuple(r.p.variable(ranura(v)) for v in (127, 128, 129))
    assert recordado == (48,) + DESPUES_DEL_TUTORIAL, (
        "la página recuerda (3,39) del 48 antes de ir al tutorial, y quedó "
        "%s. %s" % (recordado, r.estado()))
    # El primer texto del tutorial, sin tocar A: la paciencia de `esperar`
    # lo cerraría antes de la foto.
    r.esperar("el primer texto del tutorial",
              lambda p: p.byte("msg_abierto") and p.byte("msg_estado") != 1,
              tope=600, a_cada=None)
    r.foto("el-tutorial", asentar=False)
    llegar(r, 48, DESPUES_DEL_TUTORIAL, "la vuelta del tutorial", tope=20000)
    assert grupo_de(r.p) == [TALAN, AG7], (
        "AG7-17 entra al grupo detrás de Talan, y el grupo es %s. %s"
        % (grupo_de(r.p), r.estado()))
    assert r.p.item(EL_CHIP) == 0, "Stash se queda con el chip. %s" % r.estado()
    assert r.p.palabra("tema_actual") == indice_del_tema(
        r.p, "golden_axe-turtlevillage2"), (
        "el tutorial vuelve a poner el tema con el que llegó. %s" % r.estado())
    r.foto("ag7-en-el-grupo")

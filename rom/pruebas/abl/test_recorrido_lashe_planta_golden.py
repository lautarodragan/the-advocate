"""Lashe City: Stash, la planta de reciclaje y AG7-17 entrando al grupo.

Es el hito 3 de `workflow/tasks/*/lashe-city-hasta-la-carrera.md`. El camino
del droide sale del Sector 32 con auto (48): la puerta de Stash, la escena del
"bald man" que te robó en el Hover-Tram, la planta de reciclaje con sus pisos
que se rompen, el Motivator Chip, el túnel de vuelta y AG7-17 en el grupo, con
su tutorial.

    la puerta     48, el evento 9 en (3,38) -> 57 (9,12). Sin condición golpea
                  y entra; con el chip (ítem 126) entra directo; con Arden (el
                  54) dice "Looks like they're closed"
    Stash         57, el evento 2, automático: una página por cómo fue el
                  tram —1 robó los créditos (72), 2 el ídolo (71), 3 nada
                  (186)— y la 4 si se sobornó al guardia (29). Termina en la
                  planta -> 59 (20,47)
    la planta     59 -> 60 (11,13) por la puerta de (21,22)
    los pisos     de la entrada del 60 no se sube sin caer: el pozo de
                  (4,10) cae al 61, y la escalera de (1,14) del 61 vuelve al
                  60 del otro lado; de ahí al 62 por la escalera; un pozo del
                  62 cae al 60 del lado de la derecha, otro de ahí al 61, la
                  escalera del 61 vuelve al 60 al lado del chip, y el último
                  pozo cae al cuarto del chip, en el 61
    el chip       61, el evento 12 en (17,12): el ítem 126 y el 203; el evento
                  13 en (18,13) prende el 205 y salta al túnel -> 63 (26,1)
    el túnel      63, el evento 9 en (4,2) -> 48 (43,51)
    AG7           57, la página 5 del evento 2 (el 205 y el chip): prende el
                  150, mete al actor 18, saca el chip, salta a (3,39) del 48,
                  **recuerda ese lugar** en las variables 127 a 129 y salta al
                  tutorial (164), que recuerda el tema, lo vuelve a poner y
                  **vuelve a lo recordado** con `RecallToLocation`

Cada pozo es un evento de contacto que carga el mapa de abajo en una variable,
la celda del héroe en otras dos, cinco filas menos, y hace `RecallToLocation`:
el héroe cae al piso de abajo desde cinco celdas más arriba, con una ruta que
lo baja atravesando. Ver `test_lugar_recordado.py` para el opcode solo.

**Los encuentros al azar de la planta se apagan** (`ENC_BASE` en cero al
llegar a cada mapa): ninguna prueba del recorrido camina por un área con
encuentros —las que pasan por esos mapas saltan con `ir_al_mapa`—, lo que esto
cobra es el camino, y las peleas de la planta son del hito 4.

Las capturas van a `pruebas/snapshots/playthrough/lashe-planta*/` y **no
están bendecidas**: son para que taro las mire. Hasta entonces pasan siempre,
y lo que cobra esta prueba es la RAM.
"""

from batalla import grupo_de
from consola import en_la_wram, indice_del_tema

import datos

AUTO_ROJO = 130
CON_ARDEN = 54
# Cómo fue el Hover-Tram: el ladrón se llevó el ídolo; y el soborno al guardia
# del mapa 8, que abre la misma escena por la página 4.
ROBO_EL_IDOL = 71
SOBORNO_AL_GUARDIA = 29
# Lo que deja la planta: el chip agarrado, y el 205 del evento 13 del 61, que
# es lo que la página 5 de Stash pide junto con el chip.
AGARRO_EL_CHIP = 203
BAJO_POR_EL_TUNEL = 205
AG7_EN_EL_GRUPO = 150

TALAN = 14
ARDEN = 15
AG7 = 18
EL_CHIP = 126

LA_PUERTA_DE_STASH = (3, 38)
ADENTRO_DE_STASH = (9, 12)
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
    r.p.consola.escribir_ram(en_la_wram(r.p.simbolos["ENC_BASE"]), [0, 0])


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


def test_stash_la_planta_y_ag7_en_el_grupo(recorrido):
    """Sin compañero y con el ídolo robado en el tram: la escena, la planta
    cayendo por tres pisos, el chip, el túnel, y AG7-17 en el grupo con su
    tutorial y la vuelta a lo recordado."""
    r = recorrido("lashe-planta", switch=[AUTO_ROJO, ROBO_EL_IDOL])
    r.p.poner_grupo(TALAN)
    r.p.ir_al_mapa(48, 6, 55)
    r.esperar_el_control()
    de_stash_a_ag7(r)


def test_la_escena_de_stash_con_el_soborno(recorrido):
    """La página 4: el guardia sobornado en vez del tram. La escena es otra y
    termina igual, en la planta."""
    r = recorrido("lashe-planta-soborno",
                  switch=[AUTO_ROJO, SOBORNO_AL_GUARDIA])
    r.p.poner_grupo(TALAN)
    r.p.ir_al_mapa(48, 6, 55)
    r.esperar_el_control()
    la_escena_de_stash(r)


def test_con_arden_la_puerta_de_stash_esta_cerrada(recorrido):
    """Con Arden de compañera la página 5 de la puerta dice "Looks like
    they're closed", y no se entra."""
    r = recorrido("lashe-planta-arden", switch=[AUTO_ROJO, CON_ARDEN,
                                                ROBO_EL_IDOL])
    r.p.poner_grupo(TALAN, ARDEN)
    r.p.ir_al_mapa(48, 6, 55)
    r.esperar_el_control()
    r.empezar("la puerta cerrada")
    r.activar(LA_PUERTA_DE_STASH, lambda p: p.byte("msg_abierto"), tope=6000)
    r.foto("cerrado")
    r.esperar_el_control()
    assert r.p.mapa() == 48, (
        "con Arden la puerta de Stash no abre. %s" % r.estado())

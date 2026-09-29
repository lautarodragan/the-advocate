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

from tramo_planta import (LA_PUERTA_DE_STASH, ROBO_EL_IDOL, TALAN,
                          de_stash_a_ag7, la_escena_de_stash)

AUTO_ROJO = 130
CON_ARDEN = 54
# El soborno al guardia del mapa 8, que abre la escena de Stash por la página
# 4.
SOBORNO_AL_GUARDIA = 29

ARDEN = 15

ADENTRO_DE_STASH = (9, 12)


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
    r.activar(LA_PUERTA_DE_STASH, lambda p: p.byte("msg_open"), tope=6000)
    r.foto("cerrado")
    r.esperar_el_control()
    assert r.p.mapa() == 48, (
        "con Arden la puerta de Stash no abre. %s" % r.estado())

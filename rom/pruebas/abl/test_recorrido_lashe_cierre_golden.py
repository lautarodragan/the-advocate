"""Lashe City: el cierre del 36 por las tres ramas, hasta la carrera.

Es el hito 5 de `workflow/tasks/*/lashe-city-hasta-la-carrera.md`, el único
lugar donde se juntan los tres caminos. La página 2 del evento 3 del 36 —la
de cada vuelta al auto— pregunta si irse sólo cuando se cumple la condición de
la rama del compañero:

    Arden   161 + 169   el susurro, en el HQ de los Vipers (38)
    Saldra  161 + 181   los guardias de la Agency (47)
    solo    161 + 150   AG7-17 en el grupo (48, Stash y la planta)

Con eso prende el 238 —el compañero nota el auto de la Agency— y pregunta.
"Stay" sigue en la ciudad, y la vuelta siguiente la rama de arriba de la misma
página lo vuelve a preguntar; "We've got to get out of here" prende el 182 y
salta a la carrera, el mapa 49.

Cada recorrido arranca por donde arranca el juego —la charla del auto del mapa
4, con el 132— con el tramo de Wick ya hecho (el 161: lo juega
`test_recorrido_lashe_wick_golden.py`) y **con el switch de otra rama que se
puede tener sin ser la propia**, para que "sin su condición" no sea sólo "sin
nada": Arden y la rama sin compañero pueden haber visto a los guardias del 33
(el 181, que anda en las tres ramas), y Saldra puede llevar al droide (el 150,
que con ella es opcional). Con eso, cada uno:

    1. elige su sector, vuelve al auto sin hacer lo suyo, y el 36 **no**
       pregunta: el 238 sigue apagado y se abre la elección de sectores;
    2. juega lo suyo en su sector y vuelve al auto;
    3. "Stay" (el 238 prendido, el 182 no), otra vuelta a un sector y al auto;
    4. "We've got to get out of here": el 182 y la largada de la carrera.

Las capturas van a `pruebas/snapshots/playthrough/lashe-cierre-*/` y **no
están bendecidas**: son para que taro las mire. Lo que cobra esta prueba es la
RAM.
"""

from batalla import grupo_de

from tramo_lashe import (
    AG7, ARDEN, AUTO_ROJO, CON_ARDEN, CON_SALDRA, EL_SUSURRO_DE_ARDEN,
    LOS_SIGUE_LA_AGENCY, QUEDARSE, SALDRA, SE_VAN, SECTOR_32, SECTOR_33,
    SECTOR_34, SECTOR_35, SECTORES, TALAN, TIENE_EL_AUTO, VIO_A_LOS_GUARDIAS,
    VIO_EL_VIDCAST, el_hq_por_el_cano, ir_al_sector, irse_lleva_a_la_carrera,
    la_tienda_y_los_guardias, llegar_al_36, subir_al_auto)
from tramo_planta import ROBO_EL_IDOL, de_stash_a_ag7

AG7_EN_EL_GRUPO = 150


def no_pregunta(r):
    """De vuelta en el 36 sin la condición de la rama: la página 2 no prende
    el 238 y abre directo la elección de sectores."""
    r.empezar("el 36 sin la condición de la rama")
    # La primera elección que se abre, pasando los mensajes del compañero, y
    # sin confirmar: la de irse tiene dos opciones y la de sectores cuatro.
    r.marcar(0)
    assert r.p.byte("eleg_n") == len(SECTORES), (
        "la primera elección del 36 tendría que ser la de sectores, y tiene "
        "%d opciones. %s" % (r.p.byte("eleg_n"), r.estado()))
    assert not r.p.switch(LOS_SIGUE_LA_AGENCY), (
        "sin la condición de la rama la página 2 del 36 no nota el auto de "
        "la Agency. %s" % r.estado())
    assert not r.p.switch(SE_VAN), r.estado()


def al_auto_desde(r, opcion):
    """Camina del lugar donde se esté en el sector hasta la celda de llegada
    del `Teleport`, que es la de arriba del auto rojo, y se sube."""
    mapa, llegada, _auto = SECTORES[opcion]
    r.empezar("volver al auto del sector %d" % (32 + opcion))
    assert r.p.mapa() == mapa, r.estado()
    r.caminar_a(llegada, tope=8000)
    subir_al_auto(r, opcion)


def quedarse_e_irse(r, opcion, companero, ag7=False):
    """Con la condición cumplida y el 36 por preguntar: "Stay", una vuelta
    más al sector `opcion` y al auto, y "We've got to get out of here"."""
    r.empezar("el 36: quedarse")
    r.marcar(QUEDARSE)
    assert r.p.switch(LOS_SIGUE_LA_AGENCY), (
        "con la condición de la rama la página 2 prende el 238 antes de "
        "preguntar. %s" % r.estado())
    assert not r.p.switch(SE_VAN), r.estado()
    r.foto("irse-o-quedarse")
    r.confirmar()
    ir_al_sector(r, opcion, companero, ag7=ag7)
    assert not r.p.switch(SE_VAN), (
        "\"Stay\" no prende el 182. %s" % r.estado())
    subir_al_auto(r, opcion)
    irse_lleva_a_la_carrera(r)


def test_el_cierre_con_arden(recorrido):
    """Arden: el 181 de los guardias no alcanza; el susurro del HQ, sí."""
    r = recorrido("lashe-cierre-arden",
                  switch=[TIENE_EL_AUTO, AUTO_ROJO, CON_ARDEN,
                          VIO_EL_VIDCAST, VIO_A_LOS_GUARDIAS])
    llegar_al_36(r)
    ir_al_sector(r, SECTOR_34, ARDEN)
    subir_al_auto(r, SECTOR_34)
    no_pregunta(r)

    ir_al_sector(r, SECTOR_34, ARDEN)
    el_hq_por_el_cano(r)
    assert r.p.switch(EL_SUSURRO_DE_ARDEN), r.estado()
    assert grupo_de(r.p) == [TALAN, ARDEN], r.estado()
    al_auto_desde(r, SECTOR_34)
    quedarse_e_irse(r, SECTOR_35, ARDEN)


def test_el_cierre_con_saldra(recorrido):
    """Saldra con AG7-17 en el grupo: el 150 no alcanza —la rama de la
    página que lo mira pide que no esté Saldra—; los guardias del 33, sí."""
    r = recorrido("lashe-cierre-saldra",
                  switch=[TIENE_EL_AUTO, AUTO_ROJO, CON_SALDRA,
                          VIO_EL_VIDCAST, AG7_EN_EL_GRUPO])
    llegar_al_36(r)
    ir_al_sector(r, SECTOR_33, SALDRA, ag7=True)
    subir_al_auto(r, SECTOR_33)
    no_pregunta(r)

    ir_al_sector(r, SECTOR_33, SALDRA, ag7=True)
    la_tienda_y_los_guardias(r, [TALAN, SALDRA, AG7])
    al_auto_desde(r, SECTOR_33)
    quedarse_e_irse(r, SECTOR_32, SALDRA, ag7=True)


def test_el_cierre_sin_companero(recorrido):
    """Sin compañero: el 181 no alcanza, y sin el droide la rama se queda en
    la ciudad como en el original. Con Stash, la planta y AG7-17, se va."""
    r = recorrido("lashe-cierre-solo",
                  switch=[TIENE_EL_AUTO, AUTO_ROJO, VIO_EL_VIDCAST,
                          VIO_A_LOS_GUARDIAS, ROBO_EL_IDOL])
    llegar_al_36(r)
    ir_al_sector(r, SECTOR_32, None)
    subir_al_auto(r, SECTOR_32)
    no_pregunta(r)

    ir_al_sector(r, SECTOR_32, None)
    de_stash_a_ag7(r)
    assert r.p.switch(AG7_EN_EL_GRUPO), r.estado()
    al_auto_desde(r, SECTOR_32)
    quedarse_e_irse(r, SECTOR_34, None, ag7=True)

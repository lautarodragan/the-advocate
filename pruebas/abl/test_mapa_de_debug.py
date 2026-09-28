"""El mapa de debug: donde arranca "Begin the Story" en `release`, con una
puerta a cada punto clave del juego y un NPC por compañero.

Es un mapa que el juego no tiene —`parches/manual/nuevos/Map0900.json`, ver
`fork.nuevos`— y lo prende `CON_MAPA_DE_DEBUG` en cartuchos.py. Cada puerta
es una página de contacto que pone el estado de alguien que jugó hasta ahí
—switches, grupo, oro, ítems, la velocidad del héroe— y salta; de dónde sale
cada número lo dicen los comentarios de esa página. Acá se cobra que cada una
llegue adonde dice con lo que dice, y que ningún NPC deje de cambiar el grupo.

Se entra como entra el jugador: `partida("mapa-de-debug")` es la página 0 de
`release`, la que corre "Begin the Story". Las puertas se cruzan caminando.

Las capturas de las llegadas van a `pruebas/snapshots/playthrough/debug-*/`
sin golden: la que cuenta es la del mapa mismo, `mapa-de-debug-llegada`.
"""

import os

import pytest

from batalla import grupo_de, sabe
from ensamblado import cartuchos
from recorrido import Recorrido
from tanda import golden, partida

pytestmark = pytest.mark.skipif(
    not cartuchos.CON_MAPA_DE_DEBUG,
    reason="release se arma sin el mapa de debug (CON_MAPA_DE_DEBUG)")

EL_MAPA = cartuchos.MAPA_DE_DEBUG
# El `Teleport` de la entrada, `pruebas/casos/mapa-de-debug.json`.
LA_LLEGADA = (13, 9)
# Las seis puertas, en la fila de abajo, de izquierda a derecha.
PUERTAS = [(x, 14) for x in (4, 7, 10, 13, 16, 19)]
NORMAL, PAD, CALLEJONES, AUTO, CARRERA, MUNDO = range(6)
# Los NPC: (celda, actor).
ARDEN, SALDRA, AG7 = (8, 6), (13, 6), (18, 6)

DUMMY_HERO, TALAN, ARDEN_ID, SALDRA_ID, AG7_ID, AUTO_ROJO = 10, 14, 15, 17, 18, 19
EN_EL_GRUPO = 150           # el switch de AG7-17
CONCENTRATED_SPRAY = 237    # la de su ArmCannon: ver test_ag7_y_la_planta.py
DETECT_AURA = 133           # la que Talan aprende en el almacén del 32

FOTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "snapshots", "playthrough")


def entrar(mundo, fotos=None):
    """La partida recién llegada al mapa de debug por "Begin the Story"."""
    p = partida(cartuchos.ENTRADA_AL_MAPA_DE_DEBUG)
    return Recorrido(p, mundo, fotos=fotos and os.path.join(FOTOS, fotos))


def cruzar(r, puerta):
    """Camina hasta la puerta y espera a salir del mapa."""
    r.empezar("la puerta %d" % (puerta + 1))
    r.caminar_a(PUERTAS[puerta], hasta=lambda p: p.mapa() != EL_MAPA)
    r.esperar("salir del mapa de debug", lambda p: p.mapa() != EL_MAPA,
              tope=400)


def test_begin_the_story_arranca_en_el_mapa_de_debug(mundo):
    """`mapa-de-debug-llegada`: la página 0 de `release` lleva al mapa, con
    Talan en el grupo para que el héroe se vea, y el mapa sale bien dibujado."""
    r = entrar(mundo)
    r.p.correr(30)
    assert r.p.mapa() == EL_MAPA and r.celda() == LA_LLEGADA, r.estado()
    assert grupo_de(r.p) == [TALAN], r.estado()
    assert not r.p.corriendo_una_pagina(), r.estado()
    golden("mapa-de-debug-llegada", r.p.imagen())
    malas, _ = r.p.celdas_mal_dibujadas()
    assert not malas, "%d celdas mal dibujadas en el mapa de debug: %s" % (
        len(malas), malas[:12])


def test_sin_el_mapa_de_debug_la_pagina_cero_es_la_del_juego():
    """La entrega limpia, sin armarla: sin el mapa, la página 0 es `nada` y
    la entrada al mapa no va en el cartucho. Que `nada` arranque el juego lo
    cobran las pruebas que juegan desde el título, que la eligen igual con el
    mapa puesto —ver `tanda.partida`—; y que la ROM salga byte por byte igual
    a la de antes del mapa se midió al agregarlo, no lo mira esta prueba."""
    limpia = cartuchos.casos_de(cartuchos.RELEASE, con_mapa_de_debug=False)
    assert limpia[0] == cartuchos.LA_PARTIDA_DE_VERDAD
    assert cartuchos.ENTRADA_AL_MAPA_DE_DEBUG not in limpia
    con = cartuchos.casos_de(cartuchos.RELEASE, con_mapa_de_debug=True)
    assert con[0] == cartuchos.ENTRADA_AL_MAPA_DE_DEBUG
    assert cartuchos.LA_PARTIDA_DE_VERDAD in con


def test_la_puerta_del_comienzo_normal_arranca_la_apertura(mundo):
    """El `Teleport` del arranque del LDB: el enrutador del 4 corre su página
    1 y salta a la apertura del mapa 1, con DummyHero solo y sin lo que los
    NPC hayan cambiado."""
    r = entrar(mundo, "debug-normal")
    r.activar(AG7, lambda p: AG7_ID in grupo_de(p))
    r.esperar_el_control()
    cruzar(r, NORMAL)
    r.esperar("el mapa 1", lambda p: p.mapa() == 1, tope=2000)
    assert grupo_de(r.p) == [DUMMY_HERO], r.estado()
    assert not r.p.switch(EN_EL_GRUPO), r.estado()
    assert r.p.switch(20), "la página 1 del 4 prende el 20. %s" % r.estado()
    r.foto("la-apertura")


def test_la_puerta_de_talans_pad_pasa_por_el_cartel(mundo):
    """Con el prólogo hecho, el enrutador corre su página 3 —el cartel de
    "One year previously"— y deja a Talan en su casa, con la consola."""
    r = entrar(mundo, "debug-pad")
    cruzar(r, PAD)
    r.esperar("el mapa 7", lambda p: p.mapa() == 7, tope=3000)
    assert r.celda() == (15, 7), r.estado()
    # El grupo lo cambia la página del 4 **después** del `Teleport`, ya en
    # el 7.
    r.esperar("Talan en el grupo", lambda p: grupo_de(p) == [TALAN],
              tope=200)
    assert r.p.switch(21) and r.p.switch(15), r.estado()
    assert r.p.item(81) == 1, "el enrutador da la consola (81). %s" % r.estado()
    r.esperar_switch(24, tope=4000)
    r.esperar_el_control(tope=3000)
    assert r.p.velocidad_del_heroe() == 4, (
        "el despertador baja dos y sube uno desde el 5 del prólogo. %s"
        % r.estado())
    r.foto("talan-despierto")


def test_la_puerta_de_los_callejones(mundo):
    """Los callejones del Sector 30 al salir de la oficina del director, en
    la rama de Arden, con el oro del despertador y el cheque."""
    r = entrar(mundo, "debug-callejones")
    cruzar(r, CALLEJONES)
    r.esperar("el mapa 20", lambda p: p.mapa() == 20, tope=400)
    r.asentar()
    assert r.celda() == (93, 0), r.estado()
    assert grupo_de(r.p) == [TALAN], r.estado()
    for s in (24, 54, 77, 78, 89, 90, 92):
        assert r.p.switch(s), "falta el switch %d. %s" % (s, r.estado())
    for s in (56, 68, 91):
        assert not r.p.switch(s), "sobra el switch %d. %s" % (s, r.estado())
    assert r.p.oro() == 400, r.estado()
    assert r.p.item(81) == 1 and r.p.item(88) == 1, r.estado()
    assert r.p.velocidad_del_heroe() == 5, r.estado()
    r.foto("los-callejones")


def test_la_puerta_del_auto_abre_la_eleccion_y_lleva_al_pad(mundo):
    """El 36 con la elección abierta; el Sector 35 es el pad de Talan con el
    auto, y la página que sigue allá mete a Talan y a Arden."""
    r = entrar(mundo, "debug-auto")
    cruzar(r, AUTO)
    r.esperar("el mapa 36", lambda p: p.mapa() == 36, tope=400)
    r.asentar()
    for s in (54, 130, 132, 133, 137, 148):
        assert r.p.switch(s), "falta el switch %d. %s" % (s, r.estado())
    assert grupo_de(r.p) == [DUMMY_HERO], r.estado()
    assert r.p.oro() == 845, r.estado()
    assert r.p.item(97) == 8 and r.p.item(123) == 1, r.estado()
    assert sabe(r.p, TALAN, DETECT_AURA), r.estado()
    assert r.p.velocidad_del_heroe() == 4, r.estado()
    r.empezar("el 36: el Sector 35")
    r.elegir(3)
    r.esperar("el mapa 37", lambda p: p.mapa() == 37, tope=2000)
    r.esperar_el_control()
    assert r.celda() == (19, 32), r.estado()
    assert grupo_de(r.p) == [TALAN, ARDEN_ID], r.estado()
    r.foto("el-pad-con-auto")


def test_la_puerta_de_la_carrera(mundo):
    """La largada del 49, con la rama de Arden cerrada y Wick rechazado."""
    r = entrar(mundo, "debug-carrera")
    cruzar(r, CARRERA)
    r.esperar("el mapa 49", lambda p: p.mapa() == 49, tope=400)
    assert r.celda() == (1, 26), r.estado()
    for s in (161, 162, 169, 182, 238):
        assert r.p.switch(s), "falta el switch %d. %s" % (s, r.estado())
    assert not r.p.switch(164), r.estado()
    assert r.p.oro() == 1095, r.estado()
    r.asentar()
    r.foto("la-largada")


def test_la_puerta_del_mundo_pasa_por_el_premio_y_la_despedida(mundo):
    """Con las tres vueltas ganadas, el premio del 53 da lo suyo y la
    despedida del 64 deja a Talan y a Arden en el mundo."""
    r = entrar(mundo, "debug-mundo")
    cruzar(r, MUNDO)
    r.esperar("el mapa 66", lambda p: p.mapa() == 66, tope=6000)
    # La página del 64 sigue corriendo en el mundo: el 236 lo prende allá.
    r.esperar_el_control(tope=3000)
    assert r.p.switch(180) and r.p.switch(236), r.estado()
    assert grupo_de(r.p) == [TALAN, ARDEN_ID], r.estado()
    assert r.p.oro() == 1095 + 2000, r.estado()
    assert r.p.item(158) == 1 and r.p.item(107) == 1 + 2, r.estado()
    r.foto("el-mundo")


@pytest.mark.parametrize("celda,actor", [(ARDEN, ARDEN_ID),
                                         (SALDRA, SALDRA_ID), (AG7, AG7_ID)],
                         ids=["arden", "saldra", "ag7"])
def test_cada_npc_suma_y_saca_a_su_companero(mundo, celda, actor):
    """Hablarle lo suma al grupo; hablarle otra vez, lo saca. AG7-17 prende
    y apaga además el 150, y al entrar sabe la habilidad de su arma."""
    r = entrar(mundo)
    r.activar(celda, lambda p: actor in grupo_de(p))
    r.esperar_el_control()
    assert grupo_de(r.p) == [TALAN, actor], r.estado()
    if actor == AG7_ID:
        assert r.p.switch(EN_EL_GRUPO), r.estado()
        assert sabe(r.p, AG7_ID, CONCENTRATED_SPRAY), r.estado()
    r.activar(celda, lambda p: actor not in grupo_de(p))
    r.esperar_el_control()
    assert grupo_de(r.p) == [TALAN], r.estado()
    if actor == AG7_ID:
        assert not r.p.switch(EN_EL_GRUPO), r.estado()

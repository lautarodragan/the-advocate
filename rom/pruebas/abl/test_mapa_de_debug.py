"""El mapa de debug: donde arranca "Begin the Story" en `release`, con una
puerta a cada punto clave del juego y un NPC por compañero.

Es un mapa que el juego no tiene —`parches/manual/nuevos/Map0900.json`, ver
`fork.new_maps`— y lo prende `CON_MAPA_DE_DEBUG` en cartuchos.py. Cada puerta
es una página de contacto que pone el estado de alguien que jugó hasta ahí
—switches, grupo, oro, ítems, la velocidad del héroe— y salta; de dónde sale
cada número lo dicen los comentarios de esa página. Acá se cobra que cada una
llegue adonde dice con lo que dice, y que ningún NPC deje de cambiar el grupo.

**La rama la elige el compañero.** Hablarle a un NPC lo suma —y saca al que
hubiera: uno a la vez— y prende el switch de su rama apagando los de las
otras: el 54 (Arden, los Neon Vipers), el 56 (Saldra, los Lazer Teeth) o el
150 (AG7-17, la rama sin pandilla del droide). Cada puerta lee esos tres y
pone lo de esa rama en ese tramo; sin ninguno, la rama sin compañero, que a
la carrera y al mundo no llega: esas dos puertas lo dicen y no saltan.

**Talan es siempre el primero.** Una puerta que armaba el grupo sacando a
Talan y metiendo a DummyHero, con un compañero adentro, lo dejaba a él de
líder: al compañero el conversor no le prevé gráfico —en el juego nunca
lidera, ver `lideres_posibles`— y el héroe no se veía. Por eso cada llegada
mira el líder y `hero_poses`.

Se entra como entra el jugador: `partida("mapa-de-debug")` es la página 0 de
`release`, la que corre "Begin the Story". Las puertas se cruzan caminando.

Las capturas de las llegadas van a `pruebas/snapshots/playthrough/debug-*/`
sin golden: la que cuenta es la del mapa mismo, `mapa-de-debug-llegada`.
"""

import os

import pytest

from batalla import grupo_de, sabe
import lugares
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

DUMMY_HERO, TALAN, ARDEN, SALDRA, AG7, AUTO_ROJO = 10, 14, 15, 17, 18, 19
# Los NPC, por actor.
NPC = {ARDEN: (8, 6), SALDRA: (13, 6), AG7: (18, 6)}
# El switch de la rama de cada uno: `NVAlly`, `LTAlly` y `AG7-17 In Party`.
RAMA = {ARDEN: 54, SALDRA: 56, AG7: 150}
CONCENTRATED_SPRAY = 237    # la de su ArmCannon: ver test_ag7_y_la_planta.py
DETECT_AURA = 133           # la que Talan aprende en el almacén del 32
TARJETA_DE_STASH = 91       # la que da en el Hover-Tram
EL_CHIP = 126

# Lo que cada rama prende antes del director, en los callejones: ver la
# página de la puerta 3. Sin compañero y con AG7-17 es la misma, la del
# Hover-Tram: el droide se suma con auto.
DEL_DIRECTOR = {ARDEN: (48, 54, 58, 73), SALDRA: (38, 55, 56, 58),
                None: (69, 72), AG7: (69, 72)}
# Y lo que suma con auto hasta la carrera.
DE_LA_CARRERA = {ARDEN: (159, 167, 168, 169), SALDRA: (158, 181),
                 AG7: (150, 183, 203, 205)}
CON_TODAS = sorted({s for t in (DEL_DIRECTOR, DE_LA_CARRERA)
                    for sws in t.values() for s in sws})

COMPANEROS = [None, ARDEN, SALDRA, AG7]
NOMBRES = ["solo", "arden", "saldra", "ag7"]

FOTOS = os.path.join(lugares.SNAPSHOTS, "playthrough")


def entrar(mundo, fotos=None, companero=None):
    """La partida recién llegada al mapa de debug por "Begin the Story", con
    el compañero sumado si hay uno."""
    p = partida(cartuchos.ENTRADA_AL_MAPA_DE_DEBUG)
    r = Recorrido(p, mundo, fotos=fotos and os.path.join(FOTOS, fotos))
    if companero:
        sumar(r, companero)
    return r


def sumar(r, actor):
    r.empezar("hablarle al NPC del %d" % actor)
    r.activar(NPC[actor], lambda p: actor in grupo_de(p))
    r.esperar_el_control()


def cruzar(r, puerta):
    """Camina hasta la puerta y espera a salir del mapa."""
    r.empezar("la puerta %d" % (puerta + 1))
    r.caminar_a(PUERTAS[puerta], hasta=lambda p: p.mapa() != EL_MAPA)
    r.esperar("salir del mapa de debug", lambda p: p.mapa() != EL_MAPA,
              tope=400)


def talan_se_ve(r):
    """Talan de líder, y con las poses de su gráfico: sin entrada en la tabla
    de actores del cartucho, `elegir_grafico_heroe` deja `hero_poses` en
    cero y el héroe no se dibuja."""
    grupo = grupo_de(r.p)
    assert grupo and grupo[0] == TALAN, (
        "el líder tendría que ser Talan, y el grupo es %s. %s"
        % (grupo, r.estado()))
    poses = r.p.consola.ram(r.p.simbolos["hero_poses"], 3)
    assert any(poses), "el héroe no tiene poses: no se dibuja. %s" % r.estado()


def la_rama_es(r, companero, tablas):
    """Prendidos los switches de la rama de `companero` en `tablas`, y
    apagados todos los de las otras."""
    prende = {s for t in tablas for s in t.get(companero, ())}
    for s in CON_TODAS:
        if s in prende:
            assert r.p.switch(s), "falta el switch %d. %s" % (s, r.estado())
        else:
            assert not r.p.switch(s), "sobra el switch %d. %s" % (s,
                                                                 r.estado())


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
    r = entrar(mundo, "debug-normal", companero=AG7)
    cruzar(r, NORMAL)
    r.esperar("el mapa 1", lambda p: p.mapa() == 1, tope=2000)
    assert grupo_de(r.p) == [DUMMY_HERO], r.estado()
    for s in RAMA.values():
        assert not r.p.switch(s), "sobra el switch %d. %s" % (s, r.estado())
    assert r.p.switch(20), "la página 1 del 4 prende el 20. %s" % r.estado()
    r.foto("la-apertura")


def test_la_puerta_de_talans_pad_pasa_por_el_cartel(mundo):
    """Con el prólogo hecho, el enrutador corre su página 3 —el cartel de
    "One year previously"— y deja a Talan en su casa, con la consola. Con
    Arden sumado, que es lo que vio taro: Arden quedaba primero y el héroe
    no se veía. Todavía no hay rama, así que Arden sale y el 54 se apaga."""
    r = entrar(mundo, "debug-pad", companero=ARDEN)
    cruzar(r, PAD)
    r.esperar("el mapa 7", lambda p: p.mapa() == 7, tope=3000)
    assert r.celda() == (15, 7), r.estado()
    # El grupo lo cambia la página del 4 **después** del `Teleport`, ya en
    # el 7.
    r.esperar("Talan en el grupo", lambda p: grupo_de(p) == [TALAN],
              tope=200)
    assert r.p.switch(21) and r.p.switch(15), r.estado()
    assert not r.p.switch(RAMA[ARDEN]), r.estado()
    assert r.p.item(81) == 1, "el enrutador da la consola (81). %s" % r.estado()
    r.esperar_switch(24, tope=4000)
    r.esperar_el_control(tope=3000)
    talan_se_ve(r)
    assert r.p.velocidad_del_heroe() == 4, (
        "el despertador baja dos y sube uno desde el 5 del prólogo. %s"
        % r.estado())
    r.foto("talan-despierto")


# Donde termina la ruta del evento 15 del 19, arriba del puente al save
# point, y una celda del puente más abajo.
FIN_DE_LA_CINEMATICA = (90, 17)
EN_EL_PUENTE = (90, 22)


@pytest.mark.parametrize("companero", COMPANEROS, ids=NOMBRES)
def test_la_puerta_de_los_callejones(mundo, companero):
    """Los callejones del Sector 30 donde termina la cinemática del director
    —antes caía en (93,0), donde la ruta arranca, y ahí no se podía mover—,
    con la rama del compañero, y Talan caminando. El compañero sale: en el
    juego se suma en las Rat Tracks."""
    nombre = NOMBRES[COMPANEROS.index(companero)]
    r = entrar(mundo, "debug-callejones-" + nombre, companero=companero)
    cruzar(r, CALLEJONES)
    r.esperar("el mapa 20", lambda p: p.mapa() == 20, tope=400)
    r.esperar_el_control()
    assert r.celda() == FIN_DE_LA_CINEMATICA, r.estado()
    assert grupo_de(r.p) == [TALAN], r.estado()
    talan_se_ve(r)
    for s in (24, 77, 78, 89, 90, 92):
        assert r.p.switch(s), "falta el switch %d. %s" % (s, r.estado())
    for s in (68, 91, 150):
        assert not r.p.switch(s), "sobra el switch %d. %s" % (s, r.estado())
    la_rama_es(r, companero, [DEL_DIRECTOR])
    solo = companero in (None, AG7)
    assert r.p.oro() == (300 if solo else 400), (
        "sin pandilla Stash se lleva los 100 del despertador en el tram. %s"
        % r.estado())
    assert r.p.item(TARJETA_DE_STASH) == (1 if solo else 0), r.estado()
    assert r.p.item(81) == 1 and r.p.item(88) == 1, r.estado()
    assert r.p.velocidad_del_heroe() == 5, r.estado()
    r.foto("los-callejones")
    r.empezar("caminar por el puente")
    r.caminar_a(EN_EL_PUENTE, tope=600)


@pytest.mark.parametrize("companero", COMPANEROS, ids=NOMBRES)
def test_la_puerta_del_auto_abre_la_eleccion_y_lleva_al_pad(mundo, companero):
    """El 36 con la elección abierta; el Sector 35 es el pad de Talan con el
    auto, y la página que sigue allá mete a Talan y al compañero, en ese
    orden, con Talan visible. Con Saldra es lo que vio taro."""
    nombre = NOMBRES[COMPANEROS.index(companero)]
    r = entrar(mundo, "debug-auto-" + nombre, companero=companero)
    cruzar(r, AUTO)
    r.esperar("el mapa 36", lambda p: p.mapa() == 36, tope=400)
    r.asentar()
    for s in (130, 132, 133, 137, 148):
        assert r.p.switch(s), "falta el switch %d. %s" % (s, r.estado())
    la_rama_es(r, companero, [DEL_DIRECTOR] + (
        [{AG7: DE_LA_CARRERA[AG7]}] if companero == AG7 else []))
    assert grupo_de(r.p) == [DUMMY_HERO], r.estado()
    solo = companero in (None, AG7)
    assert r.p.oro() == (745 if solo else 845), r.estado()
    assert r.p.item(97) == 8 and r.p.item(123) == 1, r.estado()
    assert r.p.item(EL_CHIP) == 0, r.estado()
    assert sabe(r.p, TALAN, DETECT_AURA), r.estado()
    assert r.p.velocidad_del_heroe() == 4, r.estado()
    r.empezar("el 36: el Sector 35")
    r.elegir(3)
    r.esperar("el mapa 37", lambda p: p.mapa() == 37, tope=2000)
    r.esperar_el_control()
    assert r.celda() == (19, 32), r.estado()
    esperado = [TALAN] + ([companero] if companero else [])
    assert grupo_de(r.p) == esperado, r.estado()
    talan_se_ve(r)
    r.foto("el-pad-con-auto")


@pytest.mark.parametrize("companero", [ARDEN, SALDRA, AG7],
                         ids=["arden", "saldra", "ag7"])
def test_la_puerta_de_la_carrera(mundo, companero):
    """La largada del 49, con la rama del compañero cerrada y Wick
    rechazado."""
    nombre = NOMBRES[COMPANEROS.index(companero)]
    r = entrar(mundo, "debug-carrera-" + nombre, companero=companero)
    cruzar(r, CARRERA)
    r.esperar("el mapa 49", lambda p: p.mapa() == 49, tope=400)
    assert r.celda() == (1, 26), r.estado()
    for s in (161, 162, 182, 238):
        assert r.p.switch(s), "falta el switch %d. %s" % (s, r.estado())
    for s in (90, 92, 148, 164):
        assert not r.p.switch(s), "sobra el switch %d. %s" % (s, r.estado())
    la_rama_es(r, companero, [DEL_DIRECTOR, DE_LA_CARRERA])
    assert r.p.oro() == {ARDEN: 1095, SALDRA: 845, AG7: 745}[companero], (
        r.estado())
    r.asentar()
    r.foto("la-largada")


def test_la_carrera_sin_companero_no_salta(mundo):
    """Sin compañero el juego no llega a la carrera —la rama sola se queda
    en la ciudad sin el droide—: la puerta lo dice, no salta y no pone
    nada."""
    r = entrar(mundo)
    r.empezar("la puerta de la carrera sin compañero")
    r.caminar_a(PUERTAS[CARRERA], hasta=lambda p: p.byte("msg_abierto"))
    r.esperar("el cartel", lambda p: p.byte("msg_abierto"), tope=200,
              a_cada=0)
    r.esperar_el_control()
    assert r.p.mapa() == EL_MAPA, r.estado()
    assert grupo_de(r.p) == [TALAN], r.estado()
    for s in (161, 182, 709):
        assert not r.p.switch(s), "sobra el switch %d. %s" % (s, r.estado())


def test_la_puerta_del_mundo_pasa_por_el_premio_y_la_despedida(mundo):
    """Con las tres vueltas ganadas, el premio del 53 da lo suyo y la
    despedida del 64 deja a Talan y a Arden en el mundo."""
    r = entrar(mundo, "debug-mundo", companero=ARDEN)
    cruzar(r, MUNDO)
    r.esperar("el mapa 66", lambda p: p.mapa() == 66, tope=6000)
    # La página del 64 sigue corriendo en el mundo: el 236 lo prende allá.
    r.esperar_el_control(tope=3000)
    assert r.p.switch(180) and r.p.switch(236), r.estado()
    assert grupo_de(r.p) == [TALAN, ARDEN], r.estado()
    talan_se_ve(r)
    assert r.p.oro() == 1095 + 2000, r.estado()
    assert r.p.item(158) == 1 and r.p.item(107) == 1 + 2, r.estado()
    r.foto("el-mundo")


@pytest.mark.parametrize("actor", [ARDEN, SALDRA, AG7],
                         ids=["arden", "saldra", "ag7"])
def test_cada_npc_suma_y_saca_a_su_companero(mundo, actor):
    """Hablarle lo suma al grupo detrás de Talan y prende su rama; hablarle
    otra vez, lo saca y la apaga. AG7-17, al entrar, sabe la habilidad de su
    arma."""
    r = entrar(mundo, companero=actor)
    assert grupo_de(r.p) == [TALAN, actor], r.estado()
    for otro, s in RAMA.items():
        assert r.p.switch(s) == (otro == actor), r.estado()
    if actor == AG7:
        assert sabe(r.p, AG7, CONCENTRATED_SPRAY), r.estado()
    r.activar(NPC[actor], lambda p: actor not in grupo_de(p))
    r.esperar_el_control()
    assert grupo_de(r.p) == [TALAN], r.estado()
    assert not any(r.p.switch(s) for s in RAMA.values()), r.estado()


def test_un_companero_a_la_vez(mundo):
    """Con Arden en el grupo, sumar a Saldra saca a Arden y cambia la rama;
    sumar después a AG7-17 saca a Saldra."""
    r = entrar(mundo, companero=ARDEN)
    sumar(r, SALDRA)
    assert grupo_de(r.p) == [TALAN, SALDRA], r.estado()
    assert r.p.switch(RAMA[SALDRA]) and not r.p.switch(RAMA[ARDEN]), (
        r.estado())
    sumar(r, AG7)
    assert grupo_de(r.p) == [TALAN, AG7], r.estado()
    assert r.p.switch(RAMA[AG7]) and not r.p.switch(RAMA[SALDRA]), r.estado()

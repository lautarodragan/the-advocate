"""Lashe City con auto: los cuatro sectores desde el 36, y la salida a la carrera.

Es el hito 1 de `workflow/tasks/*/lashe-city-hasta-la-carrera.md`. El mapa 36,
`LasheCityVehicle`, es una pantalla negra con el auto y una sola cosa que
hacer: el evento 3, automático, que la primera vez —switch 148— dice qué hay
que hacer según el compañero y abre `Sector 32 / 33 / 34 / 35`. Cada opción
salta a su sector y **la página sigue corriendo allá**: saca a `DummyHero`
—el 10— y mete a Talan y al compañero. En cada sector, subirse al auto apaga
el 148, prende el 149, deja a `DummyHero` solo y vuelve al 36, donde manda la
página 2: la misma elección, y —con lo que pide la rama del compañero— la
pregunta de irse de la ciudad, que lleva a la carrera: el mapa 49, que juega
`test_recorrido_carrera_golden.py`.

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
    la salida     36 con el 161 y el 169: "Stay" sigue en la ciudad, y la vez
                  siguiente "We've got to get out of here" prende el 182 y
                  salta al 49 (1,26), la largada de la carrera

**La partida arranca por donde la arranca el juego**: la página 5 del evento 1
del mapa 4, que es la charla en el auto de después de escaparse del 33 y corre
con el 132. Pasa por la cinemática del 34 —el director y Kersh— y llega al 36
con el 148 prendido. Salvo el HQ y los guardias, que arrancan con
`ir_al_mapa` en su sector: lo que prueban es la escena, no el viaje.

Las capturas van a `pruebas/snapshots/playthrough/lashe-*/` y **no están
bendecidas**: son para que taro las mire. Hasta entonces pasan siempre, y lo
que cobra esta prueba es la RAM.
"""

from tramo_lashe import (
    ARDEN, AUTO_ROJO, CON_ARDEN, CON_SALDRA, EL_SUSURRO_DE_ARDEN,
    LOS_SIGUE_LA_AGENCY, QUEDARSE, SALDRA, SE_VAN, SECTOR_32, SECTOR_33,
    SECTOR_34, SECTOR_35, SECTORES, TALAN, TIENE_EL_AUTO, VIO_EL_VIDCAST,
    el_hq_por_el_cano, ir_al_sector, irse_lleva_a_la_carrera,
    la_tienda_y_los_guardias, llegar_al_36, subir_al_auto)

# Lo que prende la computadora del 39, y lo que prende entrar por la puerta del
# 37 —y la computadora apaga—.
VIO_LA_COMPUTADORA = 151
ENTRO_AL_PAD = 153

EL_36 = (36, 10, 9)

# El pad de Talan: la puerta del 37 y la de salida del 39, la computadora, y
# adónde deja cada `Teleport`.
LA_PUERTA_DE_TALAN = (10, 30)
ADENTRO_DEL_PAD = (9, 11)
LA_COMPUTADORA = (11, 4)
LA_PUERTA_DEL_PAD = (9, 12)
AFUERA_DEL_PAD = (10, 31)


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


def test_los_guardias_del_sector_33_con_saldra(recorrido):
    """El Sector 33 con Saldra: la tienda del 56 y de vuelta, y los guardias de
    la Agency, que es la escena que la página 2 del 36 le pide a esta rama."""
    r = recorrido("lashe-guardias", switch=[CON_SALDRA, AUTO_ROJO])
    r.p.poner_grupo(TALAN, SALDRA)
    r.p.ir_al_mapa(47, *SECTORES[SECTOR_33][1])
    r.esperar_el_control()
    la_tienda_y_los_guardias(r, [TALAN, SALDRA])


def test_irse_de_la_ciudad_lleva_a_la_carrera(recorrido):
    """Con la rama de Arden cumplida —el 161 y el 169—, la página 2 del 36
    pregunta si irse. "Stay" sigue en la ciudad; la vez siguiente, con el 238
    ya prendido, "We've got to get out of here" salta a la carrera."""
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

    irse_lleva_a_la_carrera(r)


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

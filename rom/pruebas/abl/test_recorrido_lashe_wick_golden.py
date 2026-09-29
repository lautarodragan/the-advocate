"""Lashe City con auto: la guarida de Boss Wick, los vidcasts y el favor.

Es el hito 2 de `workflow/tasks/*/lashe-city-hasta-la-carrera.md`. Desde el
Sector 35 (el 37), la puerta del vecino de Talan —el evento 13, que pide el 151
de la computadora del pad— golpea, prende el 155, y la página 3 lleva a la
guarida. De ahí en más son páginas automáticas encadenadas, sin que el
jugador tome el control hasta volver al 37:

    37  la puerta (evento 13, página 3) ................. -> 41 -> 40
    40  Boss Wick, escena 1 (evento 7, página 1): las transiciones a zoom,
        que van como fundido, y el 156 ................... -> 42
    42  los vidcasts: las transiciones a mosaico .......... -> 43 -> 44 -> 45
    45  el video de seguridad: la escena del director, sin el "REC" (deuda);
        el 160 y el borrar de vuelta al fundido .......... -> 40
    40  página 3: Wick sobre el video ...................... -> 43 -> 42
    42  página 2: el 161, DoneWithVidcast ................... -> 40
    40  página 4: todo al fundido, y el favor:
          "Accept" y "Yes": el 164, el cirujano (página 5), el 267 -> 41
          "Refuse": el 162 ........................................ -> 41
    41  páginas 2 y 3: rearma el grupo, el 163, y la rama del 162 lo hace
        renguear —la orden 29, un punto menos de velocidad— -> 37
    37  evento 17 (163 y el compañero): el comentario, que apaga el 163

El título de Talan, 'Fugitive', lo pide el cirujano con `ChangeHeroTitle`, que
la ROM acepta sin hacer —no hay pantalla que lo muestre—, así que no hay RAM
donde cobrarlo.

Las capturas van a `pruebas/snapshots/playthrough/lashe-wick-*/` y **no
están bendecidas**: son para que taro las mire. Lo que cobra esta prueba es la
RAM.
"""

from batalla import grupo_de
from tramo_wick import FUNDIDO, MOSAICO, transiciones

# Los del camino: la computadora del pad abre la puerta del vecino, que prende
# el 155 al golpear. La escena 1 prende el 156, el video el 160, y los vidcasts
# el 161, que es lo que las tres ramas le piden al 36 para irse.
VIO_LA_COMPUTADORA = 151
GOLPEO_LA_PUERTA = 155
VIO_A_WICK = 156
VIO_EL_VIDEO = 160
VIO_EL_VIDCAST = 161
# El favor.
RECHAZO_A_WICK = 162
VOLVIO_DE_LA_GUARIDA = 163
LO_OPERO_EL_CIRUJANO = 164
EL_TOBILLO_CURADO = 267

CON_ARDEN = 54
CON_SALDRA = 56
AUTO_ROJO = 130

TALAN = 14
ARDEN = 15
SALDRA = 17

LA_PUERTA_DEL_VECINO = (29, 30)
DELANTE_DE_LA_PUERTA = (29, 31)

# "Accept, and owe him a Favor." / "Refuse to be healed.", y la confirmación
# de aceptar: "Yes! I need my ankle healed!" / "No! I'm not owing Wick
# anything!".
ACEPTAR, RECHAZAR = 0, 1
SI = 0


def hasta_el_favor(r, companero):
    """De la puerta del vecino hasta la elección del favor, con las fotos de
    la escena 1, el mosaico de los vidcasts y el video. Devuelve la velocidad
    del héroe con la elección abierta."""
    p = r.p
    p.poner_grupo(TALAN, companero)
    p.ir_al_mapa(37, *DELANTE_DE_LA_PUERTA)
    r.esperar_el_control()

    r.empezar("la puerta del vecino")
    r.activar(LA_PUERTA_DEL_VECINO, lambda p: p.switch(GOLPEO_LA_PUERTA),
              tope=4000)
    r.esperar("la guarida de Boss Wick", lambda p: p.mapa() == 40,
              tope=6000)
    # Se llega en negro —la puerta tiñó la pantalla antes de saltar— y el 41
    # recién aclara después del salto: la foto va con la escena ya andando.
    llegada = p.cuadro
    r.esperar("la escena 1", lambda p: p.cuadro >= llegada + 300, tope=400)
    r.foto("la-guarida")

    r.empezar("la escena 1 de Wick")
    # El 156 se prende **en el 42**: la página del 40 sigue corriendo después
    # del `Teleport`, como en RM2k.
    r.esperar("los vidcasts y el 156",
              lambda p: p.mapa() == 42 and p.switch(VIO_A_WICK), tope=20000)
    assert transiciones(p) == (FUNDIDO, FUNDIDO), (
        "la escena 1 pide el zoom para borrar y para mostrar, y el zoom va "
        "como fundido: %s. %s" % (transiciones(p), r.estado()))

    r.empezar("el mosaico de los vidcasts")
    r.esperar("que el 42 salte al 43",
              lambda p: p.byte("fundido") and p.byte("fundido_que"),
              tope=6000)
    assert transiciones(p) == (MOSAICO, MOSAICO), (
        "la página 1 del 42 pide el mosaico para borrar y para mostrar: %s. %s"
        % (transiciones(p), r.estado()))
    p.correr(13)
    r.foto("el-mosaico-de-los-vidcasts", asentar=False)

    r.empezar("hasta el video de seguridad")
    r.esperar("el video de seguridad", lambda p: p.mapa() == 45, tope=20000)
    r.asentar()
    p.correr(150)
    r.foto("el-video-de-seguridad")
    r.esperar("el 160", lambda p: p.switch(VIO_EL_VIDEO), tope=6000)
    assert transiciones(p) == (FUNDIDO, MOSAICO), (
        "el video vuelve a borrar con fundido, y mostrar sigue en mosaico: "
        "%s. %s" % (transiciones(p), r.estado()))

    r.empezar("de vuelta con Wick, hasta el favor")
    r.marcar(ACEPTAR, tope=30000)
    assert p.mapa() == 40 and p.switch(VIO_EL_VIDCAST), (
        "el favor es la página 4 del 40, que pide el 161. %s" % r.estado())
    assert transiciones(p) == (FUNDIDO, FUNDIDO), (
        "la página 4 vuelve todo al fundido: %s. %s"
        % (transiciones(p), r.estado()))
    r.foto("el-favor")
    # La velocidad se toma acá y no al entrar: la escena del video la sube un
    # punto —la orden 28 de la ruta del héroe, en el 45— y en RM2k eso queda.
    return p.velocidad_del_heroe()


def de_vuelta_en_el_37(r, companero):
    """Del 41 al 37, y el comentario del compañero, que apaga el 163."""
    p = r.p
    r.empezar("de vuelta en el Sector 35")
    r.esperar("el mapa 37", lambda p: p.mapa() == 37, tope=6000)
    r.esperar_el_control(tope=6000)
    assert r.celda() == DELANTE_DE_LA_PUERTA, (
        "el 41 deja al héroe delante de la puerta del vecino. %s" % r.estado())
    assert grupo_de(p) == [TALAN, companero], (
        "el 41 rearma el grupo con Talan y el compañero, y es %s. %s"
        % (grupo_de(p), r.estado()))
    assert not p.switch(VOLVIO_DE_LA_GUARIDA), (
        "el evento 17 del 37 es el comentario del compañero, que corre con el "
        "163 y lo apaga. %s" % r.estado())
    assert p.switch(VIO_EL_VIDCAST), r.estado()
    assert transiciones(p) == (FUNDIDO, FUNDIDO), r.estado()
    r.foto("de-vuelta-en-el-37")


def test_aceptar_el_favor_con_saldra(recorrido):
    """"Accept" y "Yes": el cirujano opera, el tobillo se cura (el 267), y
    Talan le debe un favor a Wick (el 164), que el resto del juego mira."""
    r = recorrido("lashe-wick-acepta", switch=[VIO_LA_COMPUTADORA,
                                               CON_SALDRA, AUTO_ROJO])
    velocidad = hasta_el_favor(r, SALDRA)
    r.confirmar()
    r.elegir(SI)

    r.empezar("el cirujano")
    r.esperar("el 164", lambda p: p.switch(LO_OPERO_EL_CIRUJANO), tope=6000)
    r.asentar()
    r.p.correr(60)
    r.foto("el-cirujano")
    r.esperar("el 267", lambda p: p.switch(EL_TOBILLO_CURADO), tope=10000)
    assert not r.p.switch(RECHAZO_A_WICK), r.estado()

    de_vuelta_en_el_37(r, SALDRA)
    assert r.p.velocidad_del_heroe() == velocidad, (
        "con el tobillo curado el 41 no lo hace renguear: la velocidad era "
        "%d y es %d. %s" % (velocidad, r.p.velocidad_del_heroe(), r.estado()))


def test_rechazar_el_favor_con_arden(recorrido):
    """"Refuse to be healed": el 162, sin cirujano ni 164, y el 41 lo hace
    renguear."""
    r = recorrido("lashe-wick-rechaza", switch=[VIO_LA_COMPUTADORA,
                                                CON_ARDEN, AUTO_ROJO])
    velocidad = hasta_el_favor(r, ARDEN)
    # La elección quedó abierta con el cursor en "Accept": se lo baja.
    r.marcar(RECHAZAR)
    r.confirmar()
    r.esperar("el 162", lambda p: p.switch(RECHAZO_A_WICK), tope=4000)
    assert not r.p.switch(LO_OPERO_EL_CIRUJANO), r.estado()
    assert not r.p.switch(EL_TOBILLO_CURADO), r.estado()

    de_vuelta_en_el_37(r, ARDEN)
    assert r.p.velocidad_del_heroe() == max(1, velocidad - 1), (
        "rechazar deja a Talan rengueando: la orden 29 del 41 le baja un "
        "punto de velocidad, de %d a %d, y quedó en %d. %s"
        % (velocidad, max(1, velocidad - 1), r.p.velocidad_del_heroe(),
           r.estado()))

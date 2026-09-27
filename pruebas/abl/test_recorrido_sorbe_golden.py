"""El mundo hasta Tasgarde: Sorbe, la curación del tobillo y el viaje de Dalia.

Es el hito 2 de `workflow/tasks/*/el-mundo-y-lo-que-sigue.md`. El recorrido,
por la rama en que Talan le dijo que no a Wick (el 162) y llega al mundo
rengo:

    66  la llegada, en la celda del `Teleport [66, 71, 29]` de la despedida:
        la automática 1 prende el 239, "StillLimping". Se camina hasta la
        entrada de Sorbe Village, el evento 10 -> 69 (20, 38)
    69  el guardia del camino a la montaña (evento 17, de contacto) no deja
        pasar a un rengo; la vieja (evento 7) prende el 259, y con él el
        guardia da permiso (268). La salida del evento 16 -> 76 (13, 48)
    76  arriba, el evento 3: el doctor Vago, bajo el efecto de la bloodroot,
        ataca. La pelea es contra la tropa 178, y al ganarla -> 81 (10, 7)
    81  la curación (evento 6, página 1): prende el 267, el 270 y el 266; con
        el 270, la página 3: Talan cuenta su historia, el cartel "Meanwhile,
        in Lashe City" —en el original una imagen, en el fork del 81 un
        mensaje—, el grupo pasa a `DummyHero` -> 82 (8, 8)
    82  la oficina del director (evento 3): Dalia -> 83 (68, 68)
    83  la fábrica: la automática 9 la hace pasar al capataz, y se camina a
        la salida de abajo -> 84 (9, 10)
    84  el transporte (evento 1): el grupo vuelve a `DummyHero` -> 66 (59, 20)
    66  la automática 14, `DaliaGoingToTasgarde`, con `DummyHero` en el
        grupo: apaga los encuentros (`ChangeEncounterSteps` 0), cambia el
        grupo por el auto y le fuerza la ruta hasta Tasgarde; al terminar el
        grupo es Dalia. Pisar la entrada de Tasgarde, el evento 13, es el fin
        de la demo (el 66 está forkeado: `parches/manual/mapas/Map0066.json`,
        porque el original salta al 74)

**Los encuentros al azar del mundo y de la montaña se apagan** al llegar a
cada uno, escribiendo `ENC_BASE`: lo que se cobra acá es el camino, y la pelea
en el mundo la mira `test_mundo.py`. La pelea con Vago sí se juega: es la que
lleva a la curación.

Arranca en el mundo por `ir_al_mapa`: la despedida del 64 la juega
`test_recorrido_carrera_golden.py`, que termina pisando Sorbe.

Las capturas van a `pruebas/snapshots/playthrough/sorbe-*/` y **no están
bendecidas**: son para que taro las mire. Lo que cobra esta prueba es la RAM.
Las del 69, con su reparto propio de VRAM, tienen golden de la tanda en
`test_sorbe.py`.
"""

from batalla import grupo_de
from consola import en_la_wram

from test_recorrido_lashe_golden import CON_ARDEN

# La rama de Wick: el 162 es "le dijo que no", y con él la llegada al mundo
# prende el 239 y Talan renguea hasta la casa de Vago.
RECHAZO_A_WICK = 162
RENGO = 239

TALAN, ARDEN, DUMMY, DALIA, EL_AUTO = 14, 15, 10, 21, 22

EL_MUNDO, SORBE, LA_MONTANA, LA_CASA_DE_VAGO = 66, 69, 76, 81
LA_OFICINA, LA_FABRICA, AFUERA_DE_LA_FABRICA = 82, 83, 84

LLEGA_AL_MUNDO = (71, 29)
ENTRADA_A_SORBE = (75, 10)
ENTRADA_A_TASGARDE = (93, 4)

# En Sorbe: la vieja, la celda del guardia y la salida a la montaña.
LA_VIEJA = (16, 21)
HABLO_CON_LA_VIEJA = 259
EL_GUARDIA = (21, 5)
PERMISO_DEL_GUARDIA = 268
# En la montaña, el evento de contacto donde ataca Vago.
VAGO_ATACA = (24, 8)
DESPUES_DE_LA_MONTANA = 265
# En la casa de Vago: el tobillo curado, y la historia contada.
TOBILLO_CURADO = 267
CONTO_LA_HISTORIA = 252
# En la oficina del director, y afuera de la fábrica.
TERMINO_LA_OFICINA = 275
EL_TRANSPORTE = (9, 13)
# El viaje de Dalia: lo prende la automática 14 al terminar.
DALIA_LLEGO = 278

BOTON_CADA = 9       # cuadros de hardware entre toques de A en una pelea


def sin_encuentros(p):
    """El mapa los vuelve a prender en cada carga: se apagan después de
    llegar."""
    p.consola.escribir_ram(en_la_wram(p.simbolos["ENC_BASE"]), [0, 0])


def jugar(r, que, hasta, tope=60000, fotos=None, momentos=None):
    """Juega de a un cuadro de hardware hasta que `hasta(partida)`: pasa cada
    mensaje con A cuando terminó de componerse, y en una pelea toca A cada
    `BOTON_CADA` cuadros —que pasa los mensajes y elige atacar—.

    De a cuadros y no de a ticks porque la pelea no hace correr `vueltas`, y
    una espera por ticks se planta ahí. `fotos` es {nombre: cond}: la primera
    vez que un mensaje está compuesto con `cond(partida)` verdadera, se saca
    esa foto antes de cerrarlo. `momentos` es lo mismo en cualquier cuadro,
    haya mensaje o no."""
    p = r.p
    pendientes = dict(fotos or {})
    momentos = dict(momentos or {})
    for cuadro in range(tope):
        if hasta(p):
            return r
        for nombre, cond in list(momentos.items()):
            if cond(p):
                r.foto(nombre, asentar=False)
                del momentos[nombre]
        if p.byte("menu_abierto"):
            p.consola.apretar(*(("a",) if cuadro % BOTON_CADA < 2 else ()))
            p._un_cuadro()
            continue
        if p.byte("msg_abierto") and p.byte("msg_estado") != 1:
            for nombre, cond in list(pendientes.items()):
                if cond(p):
                    r.foto(nombre, asentar=False)
                    del pendientes[nombre]
            p.consola.apretar("a")
            p._un_cuadro()
            p._un_cuadro()
            p.consola.apretar()
            for _ in range(60):
                if not p.byte("msg_abierto"):
                    break
                p._un_cuadro()
            continue
        p.consola.apretar()
        p._un_cuadro()
    raise AssertionError("jugando %s no se llegó en %d cuadros. %s"
                         % (que, tope, r.estado()))


def en_pelea_hace(cuadros):
    """Una condición de `momentos`: la pelea lleva `cuadros` de hardware
    abierta, que es cuando la escena ya está dibujada."""
    visto = [0]

    def cond(p):
        visto[0] = visto[0] + 1 if p.byte("menu_abierto") else 0
        return visto[0] >= cuadros
    return cond


def test_sorbe_la_curacion_y_el_viaje_de_dalia(recorrido):
    r = recorrido("sorbe-y-la-curacion", switch=[CON_ARDEN, RECHAZO_A_WICK])
    p = r.p

    r.empezar("la llegada al mundo")
    p.poner_grupo(TALAN, ARDEN)
    p.ir_al_mapa(EL_MUNDO, *LLEGA_AL_MUNDO)
    r.esperar_el_control()
    assert p.switch(RENGO), (
        "con el 162 la llegada al mundo prende el 239. %s" % r.estado())
    r.foto("llega-al-mundo")

    r.empezar("caminando a Sorbe")
    sin_encuentros(p)
    r.caminar_a(ENTRADA_A_SORBE, tope=4000, hasta=lambda p: p.mapa() == SORBE)
    r.esperar_mapa(SORBE)
    r.esperar_el_control()
    r.foto("sorbe")

    r.empezar("la vieja de Sorbe")
    r.activar(LA_VIEJA, lambda p: p.byte("msg_abierto")
              and p.byte("msg_estado") != 1)
    r.foto("la-vieja", asentar=False)
    r.esperar("el switch de la vieja", lambda p: p.switch(HABLO_CON_LA_VIEJA)
              and not p.corriendo_una_pagina(), tope=3000)

    r.empezar("el guardia de la montaña")
    r.caminar_a(EL_GUARDIA, tope=3000,
                hasta=lambda p: p.switch(PERMISO_DEL_GUARDIA))
    r.esperar("el permiso del guardia",
              lambda p: p.switch(PERMISO_DEL_GUARDIA)
              and not p.corriendo_una_pagina(), tope=2000)
    r.viajar(LA_MONTANA)
    r.esperar_el_control()
    sin_encuentros(p)
    r.foto("la-montana")

    r.empezar("Vago en la montaña")
    for actor in (TALAN, ARDEN):
        p.poner_hp(actor, 999)
    r.caminar_a(VAGO_ATACA, tope=4000, hasta=lambda p: p.corriendo_una_pagina())
    jugar(r, "la pelea con Vago", lambda p: p.mapa() == LA_CASA_DE_VAGO,
          momentos={"la-pelea-con-vago": en_pelea_hace(120)})
    assert p.switch(DESPUES_DE_LA_MONTANA), r.estado()

    r.empezar("la curación")
    jugar(r, "la curación y la historia",
          lambda p: p.mapa() == LA_OFICINA,
          fotos={"la-curacion": lambda p: p.mapa() == LA_CASA_DE_VAGO,
                 "meanwhile-in-lashe-city":
                     lambda p: p.switch(CONTO_LA_HISTORIA)})
    assert p.switch(TOBILLO_CURADO), r.estado()
    assert grupo_de(p) == [DUMMY], (
        "la historia de Talan deja a `DummyHero` solo, y el grupo es %s. %s"
        % (grupo_de(p), r.estado()))
    r.asentar()
    r.foto("la-oficina")

    r.empezar("la oficina del director")
    # La página sigue corriendo en la fábrica: el grupo cambia después del
    # `Teleport`.
    jugar(r, "la oficina", lambda p: p.mapa() == LA_FABRICA
          and p.switch(TERMINO_LA_OFICINA))
    assert p.switch(TERMINO_LA_OFICINA) and grupo_de(p) == [DALIA], (
        "la oficina termina con Dalia sola en el grupo: %s. %s"
        % (grupo_de(p), r.estado()))
    jugar(r, "la llegada a la fábrica",
          lambda p: not p.corriendo_una_pagina() and not p.byte("fundido"))
    r.foto("la-fabrica")

    r.empezar("la fábrica")
    r.viajar(AFUERA_DE_LA_FABRICA)
    r.esperar_el_control()
    r.foto("afuera-de-la-fabrica")

    r.empezar("el transporte")
    r.activar(EL_TRANSPORTE, lambda p: p.mapa() == EL_MUNDO)

    # La ruta del auto termina justo en la entrada de Tasgarde, el evento 13,
    # que es de contacto: RPG_RT cancela la ruta al dar el último paso y ahí
    # mira qué hay bajo el héroe —`Game_Character::UpdateMovement` y
    # `Game_Player::UpdateMovement` de easyrpg—, y el evento queda esperando a
    # que termine la página del viaje. O sea que el fin de la demo sale solo,
    # sin que el jugador camine.
    r.empezar("el viaje de Dalia y el fin de la demo")
    vio = []
    jugar(r, "el viaje de Dalia hasta el título",
          lambda p: vio and not p.switch(DALIA_LLEGO),
          fotos={"el-fin-de-la-demo":
                     lambda p: p.switch(DALIA_LLEGO) and not vio.append(
                         (grupo_de(p), p.heroe()))},
          momentos={"el-auto-de-dalia":
                        lambda p: grupo_de(p) == [EL_AUTO]
                        and p.heroe()[1] <= 10})
    assert vio, "el viaje de Dalia terminó sin ningún mensaje. %s" \
        % r.estado()
    (grupo, celda), = vio[:1]
    assert grupo == [DALIA] and celda == ENTRADA_A_TASGARDE, (
        "el cartel del fin sale con Dalia sola en la entrada de Tasgarde %s, "
        "y salió con el grupo %s en %s" % (ENTRADA_A_TASGARDE, grupo, celda))
    p.consola.correr(p.simbolos["BOOT_CUADROS"] + 60)
    r.foto("el-titulo-despues-del-fin", asentar=False)

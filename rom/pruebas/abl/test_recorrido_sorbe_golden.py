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
        grupo es Dalia, y la ruta termina sobre la entrada de Tasgarde, el
        evento 13 -> 74 (19, 48), donde sigue `test_recorrido_capitulo_golden.py`

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

from tramo_lashe import CON_ARDEN
from tramo_sorbe import (
    ARDEN, CONTO_LA_HISTORIA, DALIA, DALIA_LLEGO, DUMMY, EL_AUTO, EL_MUNDO,
    ENTRADA_A_TASGARDE, LA_CASA_DE_VAGO, LA_MONTANA, RECHAZO_A_WICK, SORBE,
    TALAN, TOBILLO_CURADO, en_pelea_hace, jugar, sin_encuentros)

# Con `RECHAZO_A_WICK`, la llegada al mundo prende el 239 y Talan renguea
# hasta la casa de Vago.
RENGO = 239


LA_OFICINA, LA_FABRICA, AFUERA_DE_LA_FABRICA = 82, 83, 84
TASGARDE = 74

LLEGA_AL_MUNDO = (71, 29)
ENTRADA_A_SORBE = (75, 10)

# En Sorbe: la vieja, la celda del guardia y la salida a la montaña.
LA_VIEJA = (16, 21)
HABLO_CON_LA_VIEJA = 259
EL_GUARDIA = (21, 5)
PERMISO_DEL_GUARDIA = 268
# En la montaña, el evento de contacto donde ataca Vago.
VAGO_ATACA = (24, 8)
DESPUES_DE_LA_MONTANA = 265
# En la oficina del director, y afuera de la fábrica.
TERMINO_LA_OFICINA = 275
EL_TRANSPORTE = (9, 13)


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
    # que termine la página del viaje. O sea que Dalia entra a Tasgarde sola,
    # sin que el jugador camine.
    r.empezar("el viaje de Dalia hasta Tasgarde")
    vio = []
    jugar(r, "el viaje de Dalia hasta Tasgarde",
          lambda p: p.mapa() == TASGARDE and not p.byte("fundido"),
          momentos={"el-auto-de-dalia":
                        lambda p: grupo_de(p) == [EL_AUTO]
                        and p.heroe()[1] <= 10,
                    # No saca ninguna foto: anota con qué grupo se está
                    # parado en la entrada, cuadro por cuadro.
                    "en-la-entrada":
                        lambda p: p.heroe() == ENTRADA_A_TASGARDE
                        and p.mapa() == EL_MUNDO and vio.append(
                            grupo_de(p))})
    assert p.switch(DALIA_LLEGO) and vio and vio[-1] == [DALIA], (
        "el viaje de Dalia termina con Dalia sola en la entrada de Tasgarde "
        "%s, y se fue con %s. %s" % (ENTRADA_A_TASGARDE, vio[-1:], r.estado()))
    r.esperar_el_control()
    r.foto("tasgarde")

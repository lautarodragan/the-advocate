"""El camino a Paradise: del túnel del mundo al fin de la demo.

Sigue donde termina `test_recorrido_tangle_golden.py`: Talan y Arden del
otro lado del bosque, eligiendo "Yes - Continue onward" en el túnel del
mundo (66 ev18), que ahora salta al 105. El recorrido:

    105 Mountain Path: el evento 4, al pisarlo, trae los vehículos de la
        Agency (326, 327) y un guardia que persigue (el 5, con 328 o 329):
        tocarlo es una pelea con la tropa 184 que, si se huye, termina la
        página —`escape_mode` 1—. El evento 7, al pisarlo, es la emboscada
        antes del túnel: otra pelea con la 184, Arden se queda atrás y salta
        al 106
    106 la amnistía: la automática del evento 7, que salta al 107
    107 el túnel: la automática del evento 4, Isabella, que salta al 108 y
        pregunta si se guarda: se contesta que no
    108 Distant Paradise: la automática del evento 5, Isabella que lleva a
        Talan al Consejo. Antes de que la escena salte al 110 —que no entra—
        el fork del 108 pone el cartel del fin, y vuelve al título

**Los encuentros al azar se apagan** al llegar, como en los recorridos de
antes, y el grupo va en el nivel 20 con los HP en 999, igual que en Tangle:
las peleas se ganan atacando. El guardia que persigue no se esquiva: si
alcanza al héroe, la pelea se juega y gana.

Las capturas van a `pruebas/snapshots/playthrough/paradise/` y **no están
bendecidas**. Lo que cobra esta prueba es la RAM. Las llegadas tienen golden
de la tanda en `test_paradise.py`. Ver
`workflow/tasks/*/mundo-7-camino-a-paradise.md`.
"""

from batalla import grupo_de, poner_exp

from tramo_lashe import CON_ARDEN
from tramo_sorbe import ARDEN, TALAN, jugar, en_pelea_hace, sin_encuentros

MOUNTAIN_PATH, AMNISTIA, EL_TUNEL, PARADISE = 105, 106, 107, 108
# Donde deja el túnel del mundo.
AL_PIE = (68, 19)
# El evento 4, que trae los vehículos, y el 7, la emboscada.
LOS_VEHICULOS = (52, 17)
LA_EMBOSCADA = (14, 16)
VEHICULOS, PERSIGUE = 326, 327
# Arden se queda atrás: la escena del 7 lo saca del grupo.
NIVEL = 20


def con_vida(p):
    for actor in grupo_de(p):
        p.poner_hp(actor, 999)


def quieto_en(mapa):
    return lambda p: (p.mapa() == mapa and not p.corriendo_una_pagina()
                      and not p.byte("fade") and not p.byte("menu_open"))


def test_el_camino_a_paradise(recorrido):
    r = recorrido("paradise", switch=[CON_ARDEN])
    p = r.p

    r.empezar("la llegada a Mountain Path")
    p.poner_grupo(TALAN, ARDEN)
    for actor in (TALAN, ARDEN):
        poner_exp(p, actor, 0, NIVEL)
    p.ir_al_mapa(MOUNTAIN_PATH, *AL_PIE)
    r.esperar_el_control()
    sin_encuentros(p)
    r.foto("mountain-path")

    r.empezar("los vehículos de la Agency")
    con_vida(p)
    r.caminar_a(LOS_VEHICULOS, hasta=lambda p: p.corriendo_una_pagina())
    # La página arranca el tick que sigue a pisar la celda: se espera el
    # switch y no sólo el control, que todavía está.
    jugar(r, "los vehículos",
          lambda p: p.switch(PERSIGUE) and quieto_en(MOUNTAIN_PATH)(p),
          fotos={"los-vehiculos": lambda p: True})
    assert p.switch(VEHICULOS) and p.switch(PERSIGUE), r.estado()

    r.empezar("hasta la emboscada, con el guardia detrás")
    sin_encuentros(p)
    con_vida(p)
    r.caminar_a(LA_EMBOSCADA, tope=12000,
                hasta=lambda p: (p.corriendo_una_pagina()
                                 and r.celda() == LA_EMBOSCADA))
    # Hasta la pregunta de guardar, que el túnel hace ya en el 108: se le
    # contesta que no, que es seguir sin abrir la pantalla de ranuras.
    jugar(r, "la emboscada, la amnistía y el túnel",
          lambda p: p.mapa() == PARADISE and p.byte("pick_active"),
          fotos={"arden-se-queda": lambda p: p.mapa() == MOUNTAIN_PATH
                 and grupo_de(p) == [TALAN],
                 "la-amnistia": lambda p: p.mapa() == AMNISTIA,
                 "isabella": lambda p: p.mapa() == EL_TUNEL},
          momentos={"la-emboscada": en_pelea_hace(120)})
    r.elegir(1)

    # Los mensajes del 108, con la imagen del último: el cartel del fin es
    # el que se ve antes de que la ROM vuelva al título.
    en_paradise = []

    def contar(p):
        if p.mapa() == PARADISE:
            en_paradise.append(p.imagen())
        return False
    jugar(r, "la llegada a Paradise",
          lambda p: bool(en_paradise) and p.mapa() != PARADISE,
          fotos={"paradise": lambda p: p.mapa() == PARADISE,
                 "contar": contar})
    assert len(en_paradise) >= 2, (
        "en el 108 hablan Talan e Isabella y después sale el cartel del fin; "
        "salieron %d mensajes. %s" % (len(en_paradise), r.estado()))
    r.foto("el-fin-de-la-demo", asentar=False, imagen=en_paradise[-1])
    p.consola.run(p.simbolos["BOOT_FRAMES"] + 60)
    r.foto("el-titulo-despues-del-fin", asentar=False)

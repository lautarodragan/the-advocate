"""La lista de eventos con página paralela: qué la invalida, y qué cuesta.

El HQ de los Lazer Teeth —el mapa 11— tiene once eventos con página paralela, y
hasta el 2026-09-13 cada uno volvía a resolver su página activa en cada cuadro:
`un_paralelo` llamaba a `pagina_desde_eleg`, que lee del cartucho los
veinticuatro bytes de la cabecera de la página por la ventana de banco. Con el
décimo paralelo el lazo se pasaba del cuadro y el mapa caía a 30 fps de golpe
—no hay 45: perder el vblank cuesta el cuadro entero—.

Ahora la página de cada paralelo viaja **en la lista**, que `aplicar_paginas`
rehace entera. O sea que la respuesta se calcula donde RM2k la calcula, en
`Game_Map::Refresh`, y no una vez por paralelo y por cuadro.

De ahí salen las dos cosas que se miran acá, y la primera importa más que la
segunda: **la lista tiene que seguir cambiando cuando cambia la página activa.**
Si un evento deja de tener página paralela y se queda en la lista, su página
vieja sigue corriendo para siempre; si una página se vuelve paralela con el mapa
ya cargado y nadie la anota, no arranca nunca. Antes había una red de más
—`un_paralelo` volvía a preguntar qué página era y si era paralela— y esa red ya
no está, así que esto es lo único que lo cuida.
"""

# El HQ de los Lazer Teeth, que es el mapa con más paralelos del juego.
HQ = (11, [])

# Dónde vive la lista, para leerla: la RAM lejana se direcciona igual que el
# banco $7E, así que el offset de `FAR_PAR_LISTA` es el de la WRAM.
#
# Los números son **índices de evento**, o sea la posición en la tabla del mapa
# y no el id de RM2k: el evento 8 es el `LTSentry1` (id 14) y el 65 es el
# `NVSpy` (id 71).
TODOS = [1, 2, 3, 4, 5, 6, 7, 8, 26, 29, 65]
SENTRY1 = 8
NVSPY = 65


def lista_de(una):
    """Los índices de evento que la ROM tiene anotados como paralelos."""
    n = una.byte("par_n")
    datos = una.consola.ram(una.simbolos["FAR_PAR_LISTA"],
                            n * una.simbolos["PAR_LISTA_BYTES"])
    return [datos[i * una.simbolos["PAR_LISTA_BYTES"]] for i in range(n)]


def test_la_lista_sigue_a_la_pagina_activa(partida):
    """Un switch cambia qué página está activa, y la lista tiene que enterarse.

    Los dos eventos elegidos son los que el juego usa así:

    * el `LTSentry1` tiene la paralela en la página 0 y una de contacto en la 1,
      que pide el switch 45 —el que prende el `LTComputer` cuando le tiran la
      piedra—: con el switch puesto **deja** de ser paralelo;
    * el `NVSpy` tiene la paralela en la página 1 y una de acción en la 2, con
      el switch 48.

    Y se apagan de vuelta, que es la otra mitad: una página que vuelve a ser la
    activa tiene que volver a la lista. Sin eso, lo que se mide es que la ROM
    sabe sacar y no que sabe poner.
    """
    una = partida(mapas=HQ)
    una.correr(10)
    assert lista_de(una) == TODOS, "los once paralelos del mapa 11"

    una.prender(45)
    una.correr(3)
    assert lista_de(una) == [e for e in TODOS if e != SENTRY1], \
        "con el switch 45 el LTSentry1 pasa a su página de contacto"

    una.prender(48)
    una.correr(3)
    assert lista_de(una) == [e for e in TODOS
                             if e not in (SENTRY1, NVSPY)], \
        "y con el 48 el NVSpy pasa a la suya de acción"

    una.apagar(45, 48)
    una.correr(3)
    assert lista_de(una) == TODOS, \
        "apagados los dos, las dos paralelas vuelven a ser las activas"


def test_el_hq_de_los_lazer_teeth_entra_en_el_cuadro(partida):
    """El mapa 11 no puede volver a caer a la mitad del cuadro.

    Se cuentan vueltas del lazo contra cuadros de hardware, que es lo que
    `vueltas` permite preguntar: con la página resuelta en cada cuadro daban 90
    de 180 —30,00 fps clavados—, y con la lista dan 173. El piso está puesto en
    150 y no en 173 para que un cuadro de más no pinte de rojo lo que anda: lo
    que esta prueba cuida es la caída a la mitad, que es la que se ve jugando.
    """
    una = partida(mapas=HQ)
    una.correr(30)
    antes = una.palabra("vueltas")
    una.consola.correr(180)
    vueltas = una.palabra("vueltas") - antes
    assert vueltas > 150, (
        "el mapa 11 dio %d vueltas en 180 cuadros (%.2f fps): volvió a "
        "perder el cuadro" % (vueltas, vueltas * 60.0 / 180))

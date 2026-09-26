"""Un salto que es la última orden de una ruta forzada tiene que aterrizar.

En RM2k el salto no lo baja el procesador de la ruta: lo baja
`Game_Character::Update`, que mira `IsJumping()` **antes** de mirar si quedan
órdenes, y `Game_Character::UpdateMovement` es el que apaga `SetJumping(false)`
cuando el descuento llega a cero. Un salto en el aire no es "estar quieto"
—`IsStopping()` es `!(IsMoving() || IsJumping())`— así que mientras dura no se
lee ni la ruta ni el pad, y `IsAnyMovePending` lo sigue dando por pendiente:
`MoveRouteFinished` se prende recién adentro de `UpdateMovement`.

Nuestro `move_hero` llamaba a `paso_de_ruta` sólo mientras `ruta_i < ruta_n`, y
`paso_de_ruta` era el único que bajaba `ruta_salto`. Con el salto como última
orden el contador ya estaba al final en el cuadro siguiente, así que nadie
volvía a tocar el descuento: el héroe quedaba flotando a mitad del arco para
siempre. taro lo vio en el mapa 11, cuando Talan salta del susto y se queda
arriba mientras habla, y lo capturó cuadro por cuadro en la consola
—`/extras/capturas/ares/`—.

**No es un caso de borde**: 196 de las 410 rutas con salto del juego terminan en
el salto.

Los eventos no lo tenían, y la razón está medida en
`test_una_ruta_de_evento_que_termina_en_salto_no_se_cuelga`: a ellos
`mover_eventos` les llama a `cuadro_de_ruta_ev` una vez por cuadro pase lo que
pase, sin mirar el contador de órdenes, que es justo lo que el héroe no hacía.
"""


def sin_ruta_ni_mensaje(una, cuadros):
    """Corre `cuadros` ticks cerrando todo mensaje que se abra."""
    for _ in range(cuadros):
        if una.byte("msg_abierto"):
            una.tocar_ticks("a")
        else:
            una.correr(1)


def salto_de_los_eventos(una):
    """Lo que le queda al salto de cada ranura de ruta de evento ocupada.

    Es el byte +13 de `ruta_ev`, el mismo que mira `hay_rutas` para saber que un
    evento sigue en el aire.
    """
    base = una.simbolos["ruta_ev"]
    paso = una.simbolos["RUTA_EV_STRIDE"]
    crudo = una.consola.ram(base, una.simbolos["RUTA_EV_MAX"] * paso)
    return [crudo[k * paso + 13] for k in range(una.simbolos["RUTA_EV_MAX"])
            if crudo[k * paso] != 0xFF]


def test_el_heroe_aterriza_cuando_el_salto_es_la_ultima_orden(partida):
    """El caso pelado: ruta forzada de un salto y nada detrás.

    Sin el arreglo `ruta_salto` se queda en 232 —`SALTO_PASO` menos el primer
    descuento— y `hero_y` en 323 con la celda de destino ya en `tile_y = 22`,
    indefinidamente. El número de aterrizaje no se escribe: en reposo
    `salto_posicion_heroe` deja `hero_y = tile_y * 16`, porque el descuento que
    le resta es cero.
    """
    una = partida(caso="camara-salto-colgado")
    sin_ruta_ni_mensaje(una, 120)
    assert una.byte("ruta_salto") == 0, (
        "el salto se quedó con %d en el aire: nadie lo baja cuando la ruta ya "
        "se consumió" % una.byte("ruta_salto"))
    assert una.palabra("hero_y") == una.palabra("tile_y") * 16, (
        "el héroe quedó en hero_y = %d y su celda es tile_y = %d, que en reposo "
        "son %d: aterrizó a medias"
        % (una.palabra("hero_y"), una.palabra("tile_y"),
           una.palabra("tile_y") * 16))


def test_un_proceed_with_movement_espera_el_salto_del_heroe(partida):
    """`ProceedWithMovement` pegado atrás del salto no suelta la página hasta
    que el héroe toca el piso.

    Es `IsAnyMovePending`, que para el jugador es
    `IsMoveRouteOverwritten() && !IsMoveRouteFinished()` y `MoveRouteFinished`
    se prende adentro de `UpdateMovement`, o sea al terminar el salto.
    `hay_rutas` no miraba `ruta_salto`, así que la página seguía con el héroe
    todavía en el aire.
    """
    una = partida(caso="salto-final-espera")
    volando = 0
    for _ in range(120):
        if una.byte("ruta_salto"):
            volando += 1
            assert una.corriendo_una_pagina(), (
                "la página soltó el control con el héroe a %d del piso: "
                "`hay_rutas` no está mirando el salto" % una.byte("ruta_salto"))
        elif volando:
            break
        una.correr(1)
    assert volando, \
        "el salto nunca estuvo en el aire: el caso dejó de reproducir"
    assert una.byte("ruta_salto") == 0, \
        "el salto no terminó en 120 cuadros"
    sin_ruta_ni_mensaje(una, 10)
    assert not una.corriendo_una_pagina(), \
        "la página no terminó después de que el héroe aterrizara"


def test_un_teleport_al_mismo_mapa_no_deja_al_heroe_con_arco(partida):
    """Un `Teleport` disparado con el héroe en el aire lo deja en su celda y sin
    arco pendiente.

    Es la única forma que tiene el héroe de cambiar de celda sin pasar por el
    salto: el atajo del teletransporte al mismo mapa escribe `hero_x`/`hero_y`
    desde `entrada_x`/`entrada_y` y llama a `fill_window`, pero **no** toca
    `ruta_salto`. Si quedara arco, `salto_avanzar_heroe` volvería a correr al
    héroe hasta 29 px desde donde el teletransporte lo puso —dy por lo que
    quedaba, sobre 16— con la ventana recién llena. En RM2k eso no pasa porque
    `MoveTo` hace `SetRemainingStep(0)` y `GetSpriteY` deja de restar el arco en
    el acto.

    Medido: acá no pasa tampoco, y por una razón que no es la de RM2k sino de
    plazos. Un `Teleport` cuesta el fundido —la celda nueva aparece unos noventa
    ticks después del comando— y un salto del héroe dura once: `SALTO_PASO`
    sobre `SALTO_VELOCIDAD`. El salto siempre aterriza antes. La prueba está acá
    para que se sepa si algún día eso deja de valer, porque el orden es lo único
    que lo sostiene.
    """
    una = partida(caso="salto-teleport-en-el-aire")
    volo = False
    llego = False
    for _ in range(300):
        una.correr(1)
        volo = volo or bool(una.byte("ruta_salto"))
        if una.palabra("tile_x") == 30:         # la celda a la que teletransporta
            llego = True
            break
    assert volo, "el héroe nunca saltó: el caso dejó de reproducir"
    assert llego, \
        "el teletransporte al mismo mapa nunca llegó: el caso dejó de reproducir"
    assert una.byte("ruta_salto") == 0, (
        "el héroe llegó al destino con %d de arco todavía: los próximos cuadros "
        "lo van a correr de donde el teletransporte lo puso"
        % una.byte("ruta_salto"))
    assert una.palabra("hero_y") == una.palabra("tile_y") * 16, (
        "llegó a tile_y = %d y su hero_y es %d, que en reposo son %d"
        % (una.palabra("tile_y"), una.palabra("hero_y"),
           una.palabra("tile_y") * 16))


def test_una_ruta_de_evento_que_termina_en_salto_no_se_cuelga(partida):
    """El mismo agujero en los eventos, que no lo tienen.

    Está acá y no en un comentario porque es lo único que sostiene que el
    arreglo del héroe no tenga que repetirse del otro lado: `mover_eventos`
    llama a `cuadro_de_ruta_ev` para toda ranura ocupada, sin mirar si le
    quedan órdenes, así que el descuento del salto baja igual. Si alguien algún
    día le pone la guarda que tenía `move_hero`, esto se pone en rojo.
    """
    una = partida(caso="salto-final-evento")
    volando = 0
    for _ in range(180):
        if any(salto_de_los_eventos(una)):
            volando += 1
        elif volando:
            break
        una.correr(1)
    assert volando, \
        "ningún evento llegó a saltar: el caso dejó de reproducir"
    assert not any(salto_de_los_eventos(una)), (
        "un evento quedó en el aire con %s: su salto no lo baja nadie"
        % salto_de_los_eventos(una))
    sin_ruta_ni_mensaje(una, 10)
    assert not una.corriendo_una_pagina(), \
        "la página no terminó después de que el evento aterrizara"

"""El tramo de los Neon Vipers, jugado: del caño de Lashe City al HQ y de vuelta.

Es el recorrido que pidió taro el 2026-09-22, y el motivo no es la cobertura en
abstracto: **los dos defectos de esa semana aparecieron acá y ninguna prueba
pasaba por esta escena**. Del mapa 12 no había nada, y de los techos del 8
tampoco: `test_recorrido_golden.py` cruza Lashe City por la calle de abajo y
se va a la fábrica.

El camino es el del juego, y cada tramo lo mueve el evento que lo mueve:

    la calle    mapa 8, isla de arriba —la de Sector 33—, donde deja el
                teletransporte interno de (0,56)
    el caño     el evento 41 de (52,23): salta, sube cuatro celdas y salta
                tres a la derecha, y con eso el héroe queda en el techo
    el techo    el evento 45 de (58,17), que lo cruza al techo del HQ con un
                salto, cinco pasos y otro salto
    la puerta   el evento 47 de (71,14), de los que se hablan **de al lado**:
                Talan sube por el caño, se cae, y el `Teleport` lo deja adentro
                del HQ, en el mapa 12
    el HQ       se baja hasta el hotplate de (5,39), que es un evento de
                contacto y el que dispara la cinemática
    la vuelta   la cinemática entera, con su `ShowChoice` de dos opciones, y el
                `Teleport` que devuelve a la calle en (44,13)

**Lo que esta prueba caza, y está medido contra la ROM de antes del arreglo**
—el padre de `f50d654`—: el salto que quedaba colgado. La cinemática le da al
héroe una ruta forzada de un salto **en el lugar** —`begin_jump` y `end_jump`
pegados, que es Talan saltando del susto cuando el Gang Member le grita "Hold
it!"— y ese salto es la última orden de su ruta. Sin el arreglo nadie baja el
descuento: `ruta_salto` se queda en 232 con `ruta_i == ruta_n` durante **49
muestras seguidas** del vigilante, seis de ellas con un mensaje en pantalla;
con el arreglo la racha más larga es de **una**. Ojo con que ese salto no se
**ve**: sin desplazamiento, `jump_hero_position` deja `hero_y` en su lugar, así
que lo único que lo delata es el estado.

**Y lo que no caza, medido también**: el mapa dibujado corrido —el arreglo de
`stream_map`, `9997bf2`—. Este tramo no lo puede reproducir y no es cuestión de
mirar mejor: para que una fila quede sin redibujar la cámara tiene que cruzar
dos celdas en una vuelta, o sea moverse más de 8 px, y **en todo el tramo la
cámara no se mueve más de 5** —medido sobre la ROM de antes del arreglo, vuelta
por vuelta, fuera de los fundidos; el pico son los saltos del caño—. Las dos
cosas que llegan a los 16 px son el héroe a velocidad 6 y un `PanScreen` a
velocidad 6 sumados en el mismo eje, y acá no hay ninguno de los dos: ver
`pruebas/rpgmaker/test_camara.py`, que los arma a mano. La comprobación de la
ventana se hace igual en los tres hitos donde se puede —es baratísima y es la
única que ve esa clase de error— pero **hoy no puede dar rojo**, y eso se dice
acá para que nadie la cuente como red de algo.

El 2026-09-23 taro propuso que la caminata de después lo destapara: volver a la
calle y caminar a la izquierda cruzando además una fila. Está agregada —el
último hito— y **no alcanza, medido**: sobre la ROM de antes del arreglo la
prueba entera pasa, y muestreando la cámara vuelta por vuelta en esa caminata el
peor salto es de **2 px**. La cámara sigue al héroe y el héroe camina a
velocidad normal; sin un `PanScreen` encima no hay con qué llegar a 8. El único
`PanScreen` de esta parte del mapa 8 es la escena de los chicos y el dueño del
negocio —los eventos 51 y 53 de (59,23) y (59,24), que piden el switch 33— y la
otra candidata es la reja del mapa 12, que sale con un salto de cinco celdas:
las dos están en `workflow/tasks/wishlist/la-otra-rama-de-los-neon-vipers.md`.

Las capturas de los hitos van a `pruebas/snapshots/playthrough/vipers/` y **no
están bendecidas**: son para que taro las mire. Ver `Recorrido.foto`.
"""

from recorrido import A_CADA
from port import events

# El switch que prende el despertador de Talan —"se levantó y va a trabajar"—.
# No es decoración: la página 0 del hotplate lo pide, y las tres del caño
# también, así que sin él esta escena no existe. Lo prende el evento 4 del mapa
# 7, y `test_recorrido_golden.py` lo cruza jugando.
VA_A_TRABAJAR = 24

# Dónde empieza el tramo: la celda a la que el mapa 8 **se teletransporta a sí
# mismo** cuando uno camina hacia la izquierda en (0,56), que es por donde el
# jugador entra a esta parte de la ciudad desde la calle de Talan —los eventos
# 14 y 15—. No es una celda elegida a dedo.
LA_CALLE = (8, 73, 32)

# El caño, y dónde lo deja: el evento 41 y las celdas que salen de contar su
# ruta forzada —salto de una arriba, cuatro pasos arriba, salto de tres a la
# derecha—.
EL_CANO = (52, 23)
EN_EL_TECHO = (55, 18)

# El cruce al techo del HQ: el evento 45 y el final de su ruta.
CRUZAR_EL_TECHO = (58, 17)
EN_EL_TECHO_DEL_HQ = (64, 17)

# La puerta del HQ y adónde teletransporta, los dos del evento 47.
LA_PUERTA_DEL_HQ = (71, 14)
ADENTRO_DEL_HQ = (9, 1)

# El `NV hotplate`, que es de contacto: pisarlo dispara la cinemática. Y adónde
# devuelve el `Teleport` con el que termina la rama de "Yes, I'll do it!", que
# es la que se toma tocando A sin mover el cursor.
EL_HOTPLATE = (5, 39)
DE_VUELTA_EN_LA_CALLE = (44, 13)

# Y adónde se camina después de volver, que es lo que taro pidió mirar: catorce
# celdas a la izquierda y una para arriba, o sea la cámara moviéndose por los
# dos ejes con los eventos del HQ ya corridos. Es el pasillo de las filas 12 y
# 13, que está entero en la misma isla.
CAMINAR_POR_LA_CALLE = (30, 12)


def sin_quedarse_en_el_aire(partida, a_cada=A_CADA):
    """Un vigilante para `esperar(mirando=...)`: el héroe aterriza siempre.

    Lo que mira es `ruta_salto`, el descuento del arco, y lo que le tolera es
    **lo que dura un salto y una muestra más**, contado de los símbolos de la
    ROM y de la velocidad del héroe, no a ojo: `SALTO_PASO` sobre lo que baja
    el salto a esa velocidad son las vueltas que tarda en aterrizar, y el
    vigilante corre una vez cada `a_cada`. Si una ruta le cambia la velocidad,
    el tope se mueve solo.

    Un salto que no se termina no da rojo en ningún otro lado de este tramo: la
    escena no espera a que el héroe toque el piso —sus esperas son `Wait` de
    décimas y no `ProceedWithMovement`— así que sigue de largo y lo único que
    queda mal es el estado.
    """
    seguidas = [0]

    def mirar(p):
        if not p.byte("ruta_salto"):
            seguidas[0] = 0
            return
        dura = -(-partida.simbolos["SALTO_PASO"]
                 // events.JUMP_PER_SPEED[p.velocidad_del_heroe() - 1])
        tope = -(-dura // a_cada) + 1
        seguidas[0] += 1
        assert seguidas[0] <= tope, (
            "el héroe lleva %d muestras de %d ticks en el aire y un salto dura "
            "%d: le queda %d de arco con la ruta en %d de %d órdenes, o sea que "
            "nadie le va a bajar el descuento. Es el salto en el lugar de la "
            "cinemática de los Neon Vipers, que es la última orden de su ruta"
            % (seguidas[0], a_cada, dura, p.byte("ruta_salto"),
               p.byte("ruta_i"), p.byte("ruta_n")))

    return mirar


def quedarse_quieto(p, tope=60):
    """Corre hasta que la cámara deja de moverse, que es lo que
    `Partida.celdas_mal_dibujadas` pide para poder comparar.

    Caminar termina apenas cambia la celda —ver `Recorrido._paso`— y ahí el
    héroe todavía está a mitad de paso: la cámara le queda doce pixeles atrás y
    el teletransporte de referencia la recentra, así que la comparación se
    quejaba de que no comparaba lo mismo. No es el defecto que se busca; es que
    todavía no terminó de caminar.
    """
    anterior = None
    for _ in range(tope):
        ahora = (p.palabra("camara_x"), p.palabra("camara_y"))
        if ahora == anterior:
            return
        anterior = ahora
        p.correr(2)


def mirar_la_ventana(r):
    quedarse_quieto(r.p)
    # El teletransporte con que compara repara lo que encuentre: lo que se
    # mire después en la jugada ya no ve la fila rota.
    distintas, todas = r.p.celdas_mal_dibujadas()
    assert not distintas, (
        "%d de las %d celdas que se ven tienen dibujada otra celda del mapa; "
        "las primeras: %s. %s"
        % (len(distintas), len(todas), distintas[:6], r.estado()))


def test_del_cano_de_lashe_city_al_hq_de_los_neon_vipers(recorrido):
    """La escena entera, jugada, y el héroe aterrizando en cada hito."""
    r = recorrido("vipers", switch=[VA_A_TRABAJAR])

    r.empezar("la calle de Lashe City")
    r.p.ir_al_mapa(*LA_CALLE)
    r.foto("la-calle")

    r.empezar("subir por el caño")
    r.activar(EL_CANO, lambda p: (p.palabra("tile_x"),
                                  p.palabra("tile_y")) == EN_EL_TECHO
              and not p.corriendo_una_pagina())
    assert r.celda() == EN_EL_TECHO, r.estado()
    assert r.p.byte("ruta_salto") == 0, (
        "el caño termina en un salto de tres celdas y el héroe quedó con %d de "
        "arco. %s" % (r.p.byte("ruta_salto"), r.estado()))
    r.foto("en-el-techo")

    r.empezar("cruzar el techo hasta el del HQ")
    r.activar(CRUZAR_EL_TECHO, lambda p: (p.palabra("tile_x"),
                                          p.palabra("tile_y"))
              == EN_EL_TECHO_DEL_HQ and not p.corriendo_una_pagina())
    assert r.celda() == EN_EL_TECHO_DEL_HQ, r.estado()
    assert r.p.byte("ruta_salto") == 0, r.estado()
    r.foto("el-techo-del-hq")

    r.empezar("entrar al HQ por la puerta de arriba")
    r.activar(LA_PUERTA_DEL_HQ, lambda p: p.mapa() == 12, tope=2000)
    assert r.celda() == ADENTRO_DEL_HQ, r.estado()
    r.esperar_el_control(tope=4000)
    r.foto("adentro-del-hq")
    # Acá la ventana tiene que coincidir, y acá se puede preguntar: el héroe
    # llegó por un `Teleport` y desde entonces sólo caminó. Ver el docstring.
    mirar_la_ventana(r)

    r.empezar("bajar hasta el hotplate de los Neon Vipers")
    r.caminar_a(EL_HOTPLATE, tope=8000,
                hasta=lambda p: p.corriendo_una_pagina())
    assert r.celda() == EL_HOTPLATE, r.estado()
    r.foto("el-hotplate")

    r.empezar("la cinemática de los Neon Vipers y la vuelta a la calle")
    r.esperar("que la cinemática termine y devuelva a la calle",
              lambda p: p.mapa() == 8, tope=8000,
              mirando=sin_quedarse_en_el_aire(r.p))
    r.esperar_el_control(tope=4000)
    assert r.celda() == DE_VUELTA_EN_LA_CALLE, r.estado()
    assert r.p.byte("ruta_salto") == 0, r.estado()
    r.foto("de-vuelta-en-la-calle")
    mirar_la_ventana(r)

    # Y acá es donde se vería el otro defecto, porque **el mapa corrido se ve
    # caminando, no llegando**: el `Teleport` de la cinemática rellena la
    # ventana entera, así que el hito de arriba siempre está bien, y lo que
    # quedaría mal es lo que se dibuja después, con la cámara siguiendo al
    # héroe. Pero esta caminata no lo reproduce —la cámara no llega a cruzar
    # dos celdas en una vuelta—: ver el docstring, "no alcanza, medido".
    r.empezar("caminar por la calle con la cámara siguiendo al héroe")
    r.caminar_a(CAMINAR_POR_LA_CALLE, tope=8000)
    assert r.celda() == CAMINAR_POR_LA_CALLE, r.estado()
    r.foto("caminando-por-la-calle")
    mirar_la_ventana(r)

"""Guardar en el **save point de verdad**, caminando hasta él.

Las demás pruebas de guardar usan la *página de prueba* de los casos
`guardar*`; ésta usa el `OpenSaveMenu` del juego, que es el que juega taro. Con
pantalla de título se midió que la página de prueba no llegaba a guardar si la
partida cambiaba de mapa —es una automática con espera, y el doble
`enter_map` del menú la reinicia—, y eso no decía nada del camino del juego.

El save point es `SaveByTalansPad0`, el evento de índice **66** del mapa 8 —el
editor de RM2k lo numera 67, desde uno—, en la celda (9,56), con tres
comandos: `PlaySound`, `OpenSaveMenu` y `ChangeSaveAccess`. Se llega
**caminando** por el recorrido de `test_recorrido_golden.py`: el cartel de
"One year previously" deja la partida en la casa de Talan (mapa 7) y la puerta
la saca a Lashe City (mapa 8), o sea que para cuando se guarda ya se cambió de
mapa dos veces, que es exactamente la condición que hacía fallar a la página
de prueba.

Los dos primeros casos son el mismo camino por dos entradas: la partida de
verdad, que arranca en el 4 desde el título, y el caso `en-4`, que llega al 4
con un `Teleport` y la página de prueba ya corrida. Hasta el 2026-09-25 la
pareja era **sin y con pantalla de título** —el `en-4` corría en `test-main`,
que no tenía—, y era el punto: si el save point guardara en uno y no en el
otro, el defecto sería del título. Al juntar `release` y `test-main` no quedó
ninguna ROM sin título que llegue al 8 —`test-special` no lleva ni el 7 ni el
8—, así que ese control se perdió, y lo que queda del par es la entrada por el
caso contra la entrada por el arranque. Lo que se mira es el `OpenSaveMenu`
del mapa 8, a dos mapas de distancia, y no la rampa del fundido con que se
entra al 4.

**Nada de lo que espera al menú abierto puede contarse en ticks**, y ésa fue la
única dificultad: mientras la pantalla de ranuras se ve `ticks` no avanza
—`OpenSaveMenu` bloquea adentro del intérprete, como `Scene_Save` en RM2k— así
que `Partida.correr` se planta con "la ROM no llegó al tick N", y ese error es
el **éxito** disfrazado. Por eso guardar acá no pasa por `Recorrido.activar`
—que le toca A al evento con `correr`— sino por
`Recorrido.guardar_en_el_save_point`, que corre por cuadros de hardware.
"""

from consola import EMPEZAR, SEGUIR
from recorrido import UN_ANO_DESPUES, Recorrido

# El save point de al lado del pad de Talan, y el mapa donde está.
MAPA, CELDA = 8, (9, 56)


def caminar_hasta_el_save_point(p, mundo):
    """Del arranque al save point de Lashe City, jugando."""
    r = Recorrido(p, mundo)
    r.empezar("el cartel de One year previously y la casa de Talan")
    r.esperar_mapa(7, tope=3000)
    # El switch 24 es "Talan se levantó": lo prende el despertador y es lo que
    # abre su puerta. Sin él no hay camino al mapa 8.
    r.esperar_switch(24, tope=4000)
    r.esperar_el_control(tope=3000)
    r.empezar("la puerta de la casa de Talan a Lashe City")
    r.viajar(MAPA)
    r.empezar("el save point")
    r.caminar_a(CELDA)
    assert r.celda() == CELDA, (
        "el recorrido no llegó a pararse sobre el save point. %s" % r.estado())
    return r


def guardar(r, ranura=0):
    """Guarda en el save point, con la SRAM virgen comprobada de antemano.

    Que la SRAM esté vacía **antes** de tocar nada es lo que separa este caso
    de uno que pase en vacío: sin eso, "quedó la magia" lo cumpliría cualquier
    otra cosa que hubiera guardado por el camino.
    """
    assert not r.p.hay_partida(), (
        "la SRAM ya tenía una partida antes de tocar el save point: este caso "
        "no probaría nada. %s" % r.estado())
    r.guardar_en_el_save_point(ranura)
    return r.p


def test_el_save_point_guarda_llegando_por_un_caso(partida, mundo):
    """El mismo camino, llegando al 4 con el caso `en-4` y no por el arranque.

    Era el control **sin** pantalla de título, y dejó de serlo al juntar los
    cartuchos: ver el encabezado.
    """
    r = caminar_hasta_el_save_point(
        partida(caso="en-4", switch=[UN_ANO_DESPUES]), mundo)
    p = guardar(r)
    assert p.hay_partida(), (
        "se eligió la ranura y la partida no quedó en la SRAM. %s" % r.estado())
    assert not p.byte("menu_open"), (
        "la pantalla de ranuras no se cerró al elegir. %s" % r.estado())
    assert p.mapa() == MAPA, (
        "guardar tiene que devolver al mapa donde está el save point, y quedó "
        "en el %d. %s" % (p.mapa(), r.estado()))


def test_el_save_point_guarda_con_titulo_y_tras_cambiar_de_mapa(partida,
                                                                mundo):
    """**La respuesta**: con pantalla de título y después de cambiar de mapa
    dos veces, el save point del juego guarda y la partida se vuelve a cargar.

    El viaje de vuelta —resetear la consola y elegir "Resume the Story"— es la
    mitad que no se puede saltear: que la magia esté en la SRAM dice que se
    escribieron cuatro bytes, y que la partida vuelva **en el mapa 8** dice que
    lo que se escribió era esta partida y no el estado del arranque.
    """
    r = caminar_hasta_el_save_point(
        partida(switch=[UN_ANO_DESPUES], titulo=EMPEZAR), mundo)
    p = guardar(r)
    assert p.hay_partida(), (
        "se eligió la ranura y la partida no quedó en la SRAM. %s" % r.estado())
    assert p.mapa() == MAPA, (
        "guardar tiene que devolver al mapa donde está el save point, y quedó "
        "en el %d. %s" % (p.mapa(), r.estado()))

    p.reiniciar(SEGUIR, ranura=0)
    assert p.mapa() == MAPA, (
        "'Resume the Story' tenía que volver al mapa %d, donde se guardó, y "
        "volvió al %d" % (MAPA, p.mapa()))
    assert (p.palabra("tile_x"), p.palabra("tile_y")) == CELDA, (
        "la partida cargada quedó en %s y se había guardado en %s"
        % ((p.palabra("tile_x"), p.palabra("tile_y")), CELDA))
    assert p.switch(24), (
        "el switch que prendió el despertador de Talan no sobrevivió a "
        "guardar y cargar")


def test_el_cursor_de_guardar_arranca_en_la_ranura_en_uso(partida, mundo):
    """Con una partida cargada de la ranura 2, el save point abre con el cursor
    en la 2: es el `latest_slot` de `Scene_File::Start`, sin fechas. Elegir sin
    mover el cursor vuelve a escribir la misma ranura, que es lo que uno espera
    de "guardar" después de "continuar".

    Hace falta el título porque es la única forma de llegar con `ranura`
    puesta: cargar es lo que la escribe.

    No sirve la página de prueba de guardado, que abre la pantalla de ranuras
    sola a los 198 ticks, y la razón es del mapa y no del título: el cartucho
    con pantalla arranca en el 4, que es el enrutador del juego, y al volver de
    cargar su página automática se lleva la partida al mapa 1 antes de que la
    de prueba llegue al `OpenSaveMenu` —medido: `ev_active` en 1, el mapa en 1
    y la pantalla sin abrir a las 874 vueltas—. Así que el cursor se mira
    donde el jugador lo ve, que es el save point de verdad: la
    partida vuelve de la ranura 2 parada encima de él, y volver a tocarle A
    abre la pantalla sin caminar un paso.
    """
    r = caminar_hasta_el_save_point(
        partida(switch=[UN_ANO_DESPUES], titulo=EMPEZAR), mundo)
    p = guardar(r, ranura=2)
    assert p.hay_partida(2), (
        "no quedó nada en la ranura 2. %s" % r.estado())

    p.reiniciar(SEGUIR, ranura=2)
    assert p.byte("slot") == 2, "no se cargó de la ranura 2"
    assert (p.palabra("tile_x"), p.palabra("tile_y")) == CELDA, (
        "la partida cargada tenía que quedar parada en el save point, en %s, "
        "y quedó en %s"
        % (CELDA, (p.palabra("tile_x"), p.palabra("tile_y"))))

    # Y se le toca A otra vez, sin moverse: la pantalla de ranuras del save
    # point, con el cursor donde lo dejó `load_game`.
    r.p = p
    r.abrir_el_save_point()
    assert p.byte("title_sel") == 2, (
        "el cursor arrancó en la ranura %d y la partida vino de la 2"
        % p.byte("title_sel"))

"""Una flecha sostenida en el menú mueve el cursor sola: `Input::IsRepeated`.

RM2k —y easyrpg, `src/input.cpp`— la dispara en el cuadro en que se aprieta,
otra vez 23 cuadros después, y de ahí cada 4. Lo hace `flechas_repetir` en
`control.s`, adentro de `read_pad`, así que lo lleva toda pantalla que mira el
flanco de las flechas; acá se prueba en el menú de pausa, que es donde lo pidió
taro. La otra mitad, que la entrada de teclas con espera **no** la lleve, es
`test_sostener_una_direccion_no_contesta` de `test_tecla.py`.

Se cuenta en **cuadros de hardware**, como el autofire, porque la repetición
cuenta vueltas de `read_pad`: el menú lee el control una vez por vblank y
mover el cursor no le estira ninguno. Si un día se estirara, la secuencia
dejaría de ser exacta y hay que mirar por qué antes de aflojarla.
"""

from consola import TITULO_AIRE
from menu import abrir, con_grupo

# `REPETIR_ESPERA` y `REPETIR_CADA` de `control.s`, que son los de easyrpg y
# los que se midieron en el RPG_RT: ver la tarea en `workflow/tasks/`.
ESPERA = 23
CADA = 4


def cursor(una):
    return una.byte("titulo_sel")


def cuadros_en_que_se_mueve(una, cuadros, *botones):
    """Los cuadros, contados desde el primero con `botones` apretados, en que
    el cursor del menú cambió."""
    una.consola.hold(*botones)
    movidas, antes = [], cursor(una)
    for n in range(cuadros):
        una.consola.run(1)
        ahora = cursor(una)
        if ahora != antes:
            movidas.append(n)
            antes = ahora
    return movidas


def test_sostener_abajo_mueve_al_apretar_a_los_23_y_cada_4(partida):
    """Tres segundos sosteniendo abajo: el primer movimiento en el cuadro del
    flanco, el segundo 23 cuadros después, y los demás cada 4. El menú da la
    vuelta también repitiendo, como el `endless_scrolling` de easyrpg."""
    una = abrir(con_grupo(partida()))
    movidas = cuadros_en_que_se_mueve(una, 180, "down")
    assert movidas, "sostener abajo no movió el cursor"
    primero = movidas[0]
    esperado = [primero] + list(range(primero + ESPERA, 180, CADA))
    assert movidas == esperado, "se movió en los cuadros %s" % movidas


def test_arriba_repite_igual(partida):
    """La misma cuenta con arriba: el contador es de las cuatro flechas."""
    una = abrir(con_grupo(partida()))
    movidas = cuadros_en_que_se_mueve(una, 60, "up")
    primero = movidas[0]
    assert movidas == [primero] + list(range(primero + ESPERA, 60, CADA)), (
        "se movió en los cuadros %s" % movidas)


def test_soltar_corta_y_la_espera_vuelve_a_empezar(partida):
    """Soltar a mitad de la repetición no deja nada andando, y volver a
    apretar espera otra vez los 23 cuadros enteros: si el contador no se
    reiniciara, la segunda tanda repetiría enseguida."""
    una = abrir(con_grupo(partida()))
    cuadros_en_que_se_mueve(una, 40, "down")
    assert cuadros_en_que_se_mueve(una, 60) == [], "siguió moviéndose suelto"
    movidas = cuadros_en_que_se_mueve(una, 40, "down")
    primero = movidas[0]
    assert movidas == [primero] + list(range(primero + ESPERA, 40, CADA)), (
        "se movió en los cuadros %s" % movidas)


def test_b_sostenido_no_repite(partida):
    """B no es una flecha: sostenerlo cierra el menú una sola vez y no lo
    vuelve a abrir, que es lo que haría si repitiera —el mapa abre el menú
    con el flanco de B—."""
    una = abrir(con_grupo(partida()))
    una.consola.hold("b")
    for _ in range(120):
        una.consola.run(1)
    assert not una.menu_abierto(), "B sostenido volvió a abrir el menú"


def test_en_las_ranuras_la_repeticion_no_da_la_vuelta(partida):
    """La pantalla de ranuras es `Scene_File` y no `Window_Selectable`: ahí
    sólo el toque da la vuelta, y la repetición se queda en la punta. Abajo
    sostenido desde la primera baja a la segunda al apretar, a la tercera y a
    la cuarta repitiendo, y se queda ahí; un toque nuevo vuelve a la primera.
    """
    una = partida(caso="guardar-198")
    una.correr(198 - 10)
    una.esperar_la_pantalla_de_ranuras()
    una.consola.run(TITULO_AIRE)
    assert cursor(una) == 0
    movidas = cuadros_en_que_se_mueve(una, 120, "down")
    primero = movidas[0]
    assert movidas == [primero, primero + ESPERA, primero + ESPERA + CADA], (
        "se movió en los cuadros %s" % movidas)
    assert cursor(una) == una.simbolos["SRAM_SLOTS"] - 1
    cuadros_en_que_se_mueve(una, 4)
    cuadros_en_que_se_mueve(una, 2, "down")
    assert cursor(una) == 0, "el toque no dio la vuelta: quedó en %d" % (
        cursor(una))

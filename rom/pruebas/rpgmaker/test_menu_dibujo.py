"""El menú de pausa: que se abra con B como en RM2k, que se vea como
`menus.render_menu` pixel por pixel, y que guardar ande desde ahí.

El mapa después de cerrarlo lo cobra `menu` en `test_menu_golden.py`; acá se
mira lo que una captura suelta no puede: el menú con un grupo y oro
puestos, los permisos de `ChangeSaveAccess` y `ChangeMainMenuAccess` puestos
por la página de prueba, guardar desde el menú, y el pedido de menú hecho a
mitad de un paso.
"""

from consola import TITULO_AIRE
import datos
from dibujo import pixeles_distintos
from menu import GRUPO, ORO, abrir, comparar, con_grupo


def test_el_menu_se_ve_como_la_referencia_y_no_cuenta_ticks(partida):
    """Se abre con B, el cursor baja y da la vuelta para arriba, y B lo
    cierra. Mientras está abierto el reloj del juego no avanza, que es lo
    que deja a la tanda comparar el mapa después con la golden del mismo
    tick."""
    una = con_grupo(partida())
    abrir(una)
    antes = una.palabra("ticks")
    comparar(una, 0)
    una.tocar_cuadros("down")
    una.tocar_cuadros("down")
    comparar(una, 2)
    for _ in range(3):
        una.tocar_cuadros("up")
    comparar(una, 4)                    # desde la primera, arriba da la vuelta
    assert una.palabra("ticks") == antes, "el reloj corrió con el menú"
    una.tocar_cuadros("b", 10)
    assert not una.menu_abierto()
    una.correr(30)
    assert not una.menu_abierto(), "el B que cerró el menú lo volvió a abrir"


def test_guardar_desde_el_menu(partida):
    """Save abre la pantalla de ranuras; elegir la primera guarda la partida
    y vuelve al menú con el cursor en Save, como `Scene_Save`."""
    una = con_grupo(partida())
    abrir(una)
    for _ in range(3):                  # hasta Save
        una.tocar_cuadros("down")
    una.tocar_cuadros("a", TITULO_AIRE)  # la pantalla de ranuras
    una.tocar_cuadros("a", TITULO_AIRE)  # la primera ranura
    assert una.hay_partida(), "la partida no se guardó"
    assert una.menu_abierto(), "después de guardar se cerró el menú"
    comparar(una, 3, nombre="menu-guardado")


def test_guardar_prohibido_va_en_gris_y_no_hace_nada(partida):
    """`ChangeSaveAccess` en 0, desde el bytecode de la página de prueba: Save
    va en gris y A no abre la pantalla de ranuras."""
    una = con_grupo(partida(caso="sin-guardar"))
    una.correr(30)
    assert una.acceso() & 1, "la página no prohibió guardar"
    abrir(una)
    for _ in range(3):
        una.tocar_cuadros("down")
    una.tocar_cuadros("a", TITULO_AIRE)
    comparar(una, 3, guardar=False, nombre="menu-sin-guardar")
    assert not una.hay_partida()


def test_menu_prohibido_b_no_lo_abre(partida):
    una = con_grupo(partida(caso="sin-menu"))
    una.correr(30)
    una.tocar_cuadros("b", 40)
    assert not una.menu_abierto(), "el menú se abrió estando prohibido"
    assert not una.acceso() & 0x80, "quedó un pedido de menú anotado"


def test_b_caminando_abre_el_menu_al_terminar_el_paso(partida):
    """RM2k anota el pedido y lo atiende cuando el héroe está quieto: a
    mitad de un paso el menú no se abre, y se abre en cuanto el paso termina,
    con el héroe parado en su celda."""
    una = con_grupo(partida())
    una.consola.hold("up")
    for _ in range(3):
        una.consola.run(1)
    assert una.byte("step_left"), "el héroe no arrancó a caminar"
    una.consola.hold("up", "b")
    una.consola.run(1)
    una.consola.hold()
    assert not una.menu_abierto(), "el menú se abrió a mitad del paso"
    assert una.acceso() & 0x80, "el B a mitad del paso no quedó anotado"
    for _ in range(20):
        if una.menu_abierto():
            break
        una.consola.run(1)
    assert una.menu_abierto(), "el menú no se abrió al terminar el paso"
    assert una.byte("step_left") == 0
    assert una.palabra("hero_y") % 16 == 0, "el héroe quedó entre dos celdas"


def test_los_permisos_viajan_en_la_partida(partida):
    una = partida(caso="sin-guardar-guardar-198")
    una.guardar_en(0)
    assert una.acceso() & 1
    una.reiniciar()
    assert una.acceso() & 1, "el permiso de guardar no volvió de la SRAM"


def test_escapar_prohibido_es_su_bit_y_nada_más(partida):
    """`ChangeEscapeAccess` en 0 prende **el bit 2 y sólo ése**.

    El permiso de huir todavía no lo lee nadie —la huida es de la batalla—,
    así que no cambia un pixel y ninguna captura de la tanda lo puede ver. Lo
    que esta prueba cuida es justamente lo que no se ve: que el bit sea el $04
    y que no se lleve puestos a los otros dos.

    No es una precaución abstracta. Hasta el 2026-09-12 el operando del opcode
    era el **número** del permiso y la ROM sacaba el bit con un `inc a`: 0 da
    $01 y 1 da $02, pero el 2 daba **$03**, o sea prohibir guardar y el menú de
    una y no tocar el de escapar. Con el defecto puesto —el `inc a` de vuelta—
    esta prueba da rojo en el `assert` de guardar.
    """
    una = con_grupo(partida(caso="sin-escapar"))
    una.correr(30)
    assert una.acceso() & 4, "la página no prohibió escapar"
    assert not una.acceso() & 1, "se llevó puesto el permiso de guardar"
    assert not una.acceso() & 2, "se llevó puesto el permiso del menú"


def test_el_permiso_de_escapar_viaja_en_la_partida(partida):
    """Va en el mismo byte que los otros dos, así que la partida ya lo lleva;
    lo que esto cuida es que siga siendo cierto el día que alguien mude
    `FAR_ACCESS`."""
    una = partida(caso="sin-escapar-guardar-198")
    una.guardar_en(0)
    assert una.acceso() & 4
    una.reiniciar()
    assert una.acceso() & 4, "el permiso de escapar no volvió de la SRAM"


# --- los HP de ahora, que no son los del bloque ------------------------------

# Talan con dos cifras y Kersh con tres: las tres cifras se escriben alineadas
# a la derecha, así que un número corto tiene que **borrar** la celda que
# quedaba a su izquierda. Con un solo largo el caso pasaría igual con la ROM
# escribiendo basura ahí.
HP_DE_PELEA = {14: 7, 11: 103}


def test_el_menu_muestra_los_hp_que_dejo_la_pelea(partida):
    """Lo que taro reportó jugando: el número del menú no se movía nunca.

    Los HP iban horneados adentro del bloque de la fila del actor, que el
    conversor dibuja una vez y la ROM sube tal cual, así que el menú mostraba
    siempre el máximo del nivel —"siempre se muestra en 40", que es el de
    Talan— por más que la pelea los hubiera bajado. Las tres cifras las
    escribe la ROM desde `FAR_HP`, con las mismas celdas que el oro.

    **Comprobado en rojo con la ROM de antes**: 111 pixeles de diferencia, los
    de las tres cifras que la ROM no escribía.
    """
    una = con_grupo(partida())
    for actor, valor in HP_DE_PELEA.items():     # como los deja una pelea
        una.poner_hp(actor, valor)
    abrir(una)
    comparar(una, 0, nombre="menu-hp", hp=HP_DE_PELEA)


def test_los_hp_del_menu_cambian_de_verdad():
    """Y el control de que el caso de arriba mide algo: la referencia con los
    HP de la pelea **no** es la misma imagen que con los HP llenos.

    Sin esto, una ROM que siguiera horneando el máximo pasaría el caso de
    arriba el día que la referencia se equivocara igual, que es la forma de
    falla de toda comparación de dos lados: ver AGENTS.md, "La regla que
    sostiene todo".
    """
    from port import menus
    from rpgmaker.resources import GAME_DIR
    db, skin = datos.base(), datos.skin()
    llena = menus.render_menu(skin, db, 4, GRUPO, ORO, 0, True, db.font_id,
                               None, GAME_DIR)
    herida = menus.render_menu(skin, db, 4, GRUPO, ORO, 0, True, db.font_id,
                                None, GAME_DIR, HP_DE_PELEA)
    distintos = pixeles_distintos(llena, herida)
    assert distintos > 50, (
        "la referencia dibuja lo mismo con el grupo entero y con el grupo "
        "herido: %d pixeles de diferencia" % distintos)

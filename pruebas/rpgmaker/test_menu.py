"""El menú de pausa: que se abra con B como en RM2k, que se vea como
`titulo.render_menu` pixel por pixel, y que guardar ande desde ahí.

La tanda cobra el mapa después de cerrarlo —`menu` en `pruebas/*/test_tanda*.py`—;
acá se mira lo que una captura suelta no puede: el menú con un grupo y oro
puestos, los permisos de `ChangeSaveAccess` y `ChangeMainMenuAccess` puestos
por la página de prueba, guardar desde el menú, y el pedido de menú hecho a
mitad de un paso.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))

from consola import TITULO_AIRE

GRUPO = (14, 11)
ORO = 1234


def tocar(una, boton, cuadros=4):
    """Un toque en cuadros de hardware: el menú no cuenta ticks."""
    una.consola.apretar(boton)
    una.consola.correr(2)
    una.consola.apretar()
    una.consola.correr(cuadros)


def abrir(una, tope=60):
    tocar(una, "b", 0)
    for _ in range(tope):
        if una.menu_abierto():
            una.consola.correr(3)
            return una
        una.consola.correr(1)
    raise AssertionError("B no abrió el menú en %d cuadros" % tope)


def comparar(una, elegida, guardar=True, nombre="menu", hp=None):
    import lcf
    import titulo
    import ventana
    from render_map import GAME_DIR
    from tanda import quince_bits
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    skin = ventana.skin(GAME_DIR, db.system_name)
    captura = una.imagen().convert("RGB")
    esperada = titulo.render_menu(skin, db, una.simbolos["SRAM_RANURAS"],
                                  GRUPO, ORO, elegida, guardar, db.font_id,
                                  None, GAME_DIR, hp)
    distintos = sum(1 for x, y in zip(quince_bits(captura), quince_bits(esperada))
                    if x != y)
    if distintos:
        donde = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "rom", "shots")
        os.makedirs(donde, exist_ok=True)
        captura.save(os.path.join(donde, "prueba-%s.png" % nombre))
        esperada.save(os.path.join(donde, "prueba-%s.esperado.png" % nombre))
    assert distintos == 0, (
        "el menú con el cursor en la %d difiere de la referencia en %d "
        "pixeles; están en rom/shots/prueba-%s*.png"
        % (elegida, distintos, nombre))


def con_grupo(una):
    una.correr(5)
    una.poner_grupo(*GRUPO)
    una.consola.escribir_ram(una.simbolos["oro"],
                             list(ORO.to_bytes(3, "little")))
    return una


def test_el_menu_se_ve_como_la_referencia_y_no_cuenta_ticks(partida):
    """Se abre con B, el cursor baja y da la vuelta para arriba, y B lo
    cierra. Mientras está abierto el reloj del juego no avanza, que es lo
    que deja a la tanda comparar el mapa después con la referencia del mismo
    tick."""
    una = con_grupo(partida())
    abrir(una)
    antes = una.palabra("vueltas")
    comparar(una, 0)
    tocar(una, "down")
    tocar(una, "down")
    comparar(una, 2)
    for _ in range(3):
        tocar(una, "up")
    comparar(una, 4)                    # desde la primera, arriba da la vuelta
    assert una.palabra("vueltas") == antes, "el reloj corrió con el menú"
    tocar(una, "b", 10)
    assert not una.menu_abierto()
    una.correr(30)
    assert not una.menu_abierto(), "el B que cerró el menú lo volvió a abrir"


def test_guardar_desde_el_menu(partida):
    """Save abre la pantalla de ranuras; elegir la primera guarda la partida
    y vuelve al menú con el cursor en Save, como `Scene_Save`."""
    una = con_grupo(partida())
    abrir(una)
    for _ in range(3):                  # hasta Save
        tocar(una, "down")
    tocar(una, "a", TITULO_AIRE)        # la pantalla de ranuras
    tocar(una, "a", TITULO_AIRE)        # la primera ranura
    assert una.sram(0x100, 4) == b"ABLS", "la partida no se guardó"
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
        tocar(una, "down")
    tocar(una, "a", TITULO_AIRE)
    comparar(una, 3, guardar=False, nombre="menu-sin-guardar")
    assert una.sram(0x100, 4) != b"ABLS"


def test_menu_prohibido_b_no_lo_abre(partida):
    una = con_grupo(partida(caso="sin-menu"))
    una.correr(30)
    tocar(una, "b", 40)
    assert not una.menu_abierto(), "el menú se abrió estando prohibido"
    assert not una.acceso() & 0x80, "quedó un pedido de menú anotado"


def test_b_caminando_abre_el_menu_al_terminar_el_paso(partida):
    """RM2k anota el pedido y lo atiende cuando el héroe está quieto: a
    mitad de un paso el menú no se abre, y se abre en cuanto el paso termina,
    con el héroe parado en su celda."""
    una = con_grupo(partida())
    una.consola.apretar("up")
    for _ in range(3):
        una.consola.correr(1)
    assert una.byte("step_left"), "el héroe no arrancó a caminar"
    una.consola.apretar("up", "b")
    una.consola.correr(1)
    una.consola.apretar()
    assert not una.menu_abierto(), "el menú se abrió a mitad del paso"
    assert una.acceso() & 0x80, "el B a mitad del paso no quedó anotado"
    for _ in range(20):
        if una.menu_abierto():
            break
        una.consola.correr(1)
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
    `FAR_ACCESO`."""
    una = partida(caso="sin-escapar-guardar-198")
    una.guardar_en(0)
    assert una.acceso() & 4
    una.reiniciar()
    assert una.acceso() & 4, "el permiso de escapar no volvió de la SRAM"


# --- los HP de ahora, que no son los del bloque ------------------------------

def poner_hp(una, cuanto):
    """Los HP del grupo en la RAM lejana, como los deja una pelea."""
    for actor, valor in cuanto.items():
        una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * actor,
                                 [valor & 0xFF, valor >> 8])
    return una


# Talan con dos cifras y Kersh con tres: las tres cifras se escriben alineadas
# a la derecha, así que un número corto tiene que **borrar** la celda que
# quedaba a su izquierda. Con un solo largo el caso pasaría igual con la ROM
# escribiendo basura ahí.
HP_DE_PELEA = {14: 7, 11: 103}


def test_el_menu_muestra_los_hp_que_dejo_la_pelea(partida):
    """Lo que taro reportó jugando: el número del menú no se movía nunca.

    Hasta el 2026-09-13 los HP iban horneados adentro del bloque de la fila del
    actor, que el conversor dibuja una vez y la ROM sube tal cual, así que el
    menú mostraba siempre el máximo del nivel —"siempre se muestra en 40", que
    es el de Talan— por más que la pelea los hubiera bajado. Ahora las tres
    cifras las escribe la ROM desde `FAR_HP`, con las mismas celdas que el oro.

    **Comprobado en rojo con la ROM de antes**: 111 pixeles de diferencia, los
    de las tres cifras que la ROM no escribía.
    """
    una = con_grupo(partida())
    poner_hp(una, HP_DE_PELEA)
    abrir(una)
    comparar(una, 0, nombre="menu-hp", hp=HP_DE_PELEA)


def test_los_hp_del_menu_cambian_de_verdad():
    """Y el control de que el caso de arriba mide algo: la referencia con los
    HP de la pelea **no** es la misma imagen que con los HP llenos.

    Sin esto, una ROM que siguiera horneando el máximo pasaría el caso de
    arriba el día que la referencia se equivocara igual, que es la forma de
    falla que AGENTS.md nombra primero.
    """
    import lcf
    import titulo
    import ventana
    from render_map import GAME_DIR
    from tanda import quince_bits
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    skin = ventana.skin(GAME_DIR, db.system_name)
    llena = titulo.render_menu(skin, db, 4, GRUPO, ORO, 0, True, db.font_id,
                               None, GAME_DIR)
    herida = titulo.render_menu(skin, db, 4, GRUPO, ORO, 0, True, db.font_id,
                                None, GAME_DIR, HP_DE_PELEA)
    distintos = sum(1 for x, y in zip(quince_bits(llena), quince_bits(herida))
                    if x != y)
    assert distintos > 50, (
        "la referencia dibuja lo mismo con el grupo entero y con el grupo "
        "herido: %d pixeles de diferencia" % distintos)

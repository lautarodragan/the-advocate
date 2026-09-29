"""Usar una medicina desde el menú de pausa, fuera de la pelea.

Es el reporte de taro del 2026-09-21, que eran tres síntomas:

* el `Cold Sandwich-HP` curaba en la pelea y no desde el menú: la elección de
  actor no hacía nada con A, a propósito, desde que se escribió —"fuera de
  batalla nadie tiene los HP por debajo del máximo"—, y eso dejó de ser cierto
  el día que los HP pasaron a ser estado;
* al volver de la elección a la lista y entrar otra vez, la primera fila del
  panel salía rota;
* el `Pungent Elixir-LIFE`, que es `ko_only`, no levantaba a Arden en cero.

Lo que la ROM tiene que hacer es `Scene_ActorTarget::UpdateItem` de easyrpg:
`Game_Party::UseItem` sobre el actor elegido —que pasa por
`Game_Actor::IsItemUsable`, o sea el `actor_set` del ítem, y por
`Game_Battler::UseItem`—, gastar uno si sirvió, y **quedarse en la elección**
con el panel al día.

El caso `curar-menu` da dos sándwiches, un vino, un elixir y unas botas. Las botas
—equipo, en gris— están para el síntoma 2: son las últimas de la lista, así que
son lo último que la pantalla de ítems pinta antes de abrir la elección.
"""

from consola import TITULO_AIRE
import datos
from dibujo import comparar_pantalla, diferencia
from datos import maximos
from menu import abrir

TALAN, ARDEN = 14, 15
SANDWICH, VINO, ELIXIR, BOTAS = 97, 103, 115, 262
# Las filas de la lista, que va por número de ítem.
FILA_SANDWICH, FILA_VINO, FILA_ELIXIR = 0, 1, 2
AG7 = 18


def en_los_items(partida, hp_arden):
    """El grupo de Talan y Arden, Arden con `hp_arden`, y la pantalla de
    ítems abierta con el cursor en el sándwich, que es el primero."""
    una = partida(caso="curar-menu")
    una.correr(5)
    una.poner_grupo(TALAN, ARDEN)
    una.poner_hp(ARDEN, hp_arden)
    una.correr(30)
    abrir(una)
    una.tocar_cuadros("a", TITULO_AIRE)
    assert una.menu_abierto()
    return una


def usar_sobre_la_segunda(una, fila_del_item):
    """El ítem de esa fila, sobre la segunda fila del grupo."""
    for _ in range(fila_del_item):
        una.tocar_cuadros("down")
    una.tocar_cuadros("a", TITULO_AIRE)  # la elección de actor
    una.tocar_cuadros("down")           # la segunda fila
    una.tocar_cuadros("a", 20)


def diferencia_con_la_eleccion(una, elegida, hp, sandwiches):
    """Cuántos pixeles, a 15 bits, difiere la pantalla de `render_objetivo`,
    con el sándwich y los que quedan de él al lado de "Owned Items"."""
    from port import menus
    from rpgmaker.recursos import GAME_DIR
    db, skin = datos.base(), datos.skin()
    esperada = menus.render_objetivo(skin, db, 4, (TALAN, ARDEN), elegida,
                                      db.font_id, None, GAME_DIR, hp,
                                      SANDWICH, sandwiches)
    return diferencia(una, esperada, "curar-eleccion")


# --- síntoma 1: el sándwich ---------------------------------------------------

def test_el_sandwich_cura_desde_el_menu_y_se_gasta(partida):
    """Arden en 10: el sándwich suma 30, se gasta uno, y la elección se queda
    abierta con los HP nuevos en el panel, como `Scene_ActorTarget`, que
    refresca las dos ventanas y no vuelve.

    Visto en rojo sin el arreglo: Arden seguía en 10 y quedaban dos."""
    una = en_los_items(partida, 10)
    usar_sobre_la_segunda(una, FILA_SANDWICH)
    assert una.hp(ARDEN) == 40, (
        "el sándwich dejó a Arden en %d HP desde 10, y cura 30"
        % una.hp(ARDEN))
    assert una.item(SANDWICH) == 1, (
        "quedan %d sándwiches después de usar uno de dos"
        % una.item(SANDWICH))
    assert una.menu_abierto()
    assert diferencia_con_la_eleccion(una, 1, {ARDEN: 40}, 1) == 0, (
        "la elección, después de curar, no muestra los HP nuevos de Arden; "
        "está en pruebas/snapshots/pantallas/curar-eleccion*.png")


def test_el_sandwich_topa_en_el_maximo(partida):
    tope = maximos()[ARDEN][0]
    una = en_los_items(partida, tope - 5)
    usar_sobre_la_segunda(una, FILA_SANDWICH)
    assert una.hp(ARDEN) == tope, (
        "el sándwich dejó a Arden en %d HP y su máximo es %d"
        % (una.hp(ARDEN), tope))


def test_el_sandwich_no_se_gasta_en_quien_esta_lleno(partida):
    """`UseItem` devuelve que no sirvió si no subió nada, y entonces no se
    gasta: es lo que suena a error en RM2k."""
    una = en_los_items(partida, maximos()[ARDEN][0])
    usar_sobre_la_segunda(una, FILA_SANDWICH)
    assert una.item(SANDWICH) == 2, (
        "el sándwich se gastó sobre Arden, que tenía los HP llenos")


def test_el_sandwich_no_levanta_a_un_caido(partida):
    """Un caído sólo se levanta con un ítem que saque el estado de muerto:
    el sándwich no lo tiene en su `state_set`."""
    una = en_los_items(partida, 0)
    usar_sobre_la_segunda(una, FILA_SANDWICH)
    assert una.hp(ARDEN) == 0, (
        "el sándwich levantó a Arden, que estaba caído: quedó en %d"
        % una.hp(ARDEN))
    assert una.item(SANDWICH) == 2


def test_el_vino_repone_los_sp(partida):
    """Los SP, que son la otra mitad de `Game_Battler::UseItem`: el Cheap
    Wine-SP suma 20, topado en el máximo."""
    una = partida(caso="curar-menu")
    una.correr(5)
    una.poner_grupo(TALAN, ARDEN)
    una.poner_sp(ARDEN, 0)
    una.correr(30)
    abrir(una)
    una.tocar_cuadros("a", TITULO_AIRE)
    usar_sobre_la_segunda(una, FILA_VINO)
    esperado = min(20, maximos()[ARDEN][1])
    assert una.sp(ARDEN) == esperado, (
        "el vino dejó a Arden en %d SP desde cero, y tenía que quedar en %d"
        % (una.sp(ARDEN), esperado))
    assert una.item(VINO) == (0 if esperado else 1)


def test_el_sandwich_no_sirve_a_quien_no_puede_usarlo(partida):
    """`Game_Actor::IsItemUsable`: el `actor_set` del sándwich deja afuera a
    AG7-17, que es un robot. Con él en 1 HP, A no hace nada."""
    una = partida(caso="curar-menu")
    una.correr(5)
    una.poner_grupo(TALAN, AG7)
    una.poner_hp(AG7, 1)
    una.correr(30)
    abrir(una)
    una.tocar_cuadros("a", TITULO_AIRE)
    usar_sobre_la_segunda(una, FILA_SANDWICH)
    assert una.hp(AG7) == 1, (
        "el sándwich curó a AG7-17, que no lo puede usar: quedó en %d"
        % una.hp(AG7))
    assert una.item(SANDWICH) == 2


# --- síntoma 3: el elixir -----------------------------------------------------

def test_el_elixir_levanta_a_un_caido(partida):
    """El Pungent Elixir-LIFE, `ko_only` y con el estado de muerto en su
    `state_set`, sobre Arden en cero. `Game_Battler::UseItem`: sacar la muerte
    lo deja en 1, y después `ChangeHp(hp_change - 1)`, con `hp_change` el 25%
    de su máximo. Así que termina en `max(1, 25 * max / 100)`.

    Visto en rojo sin el arreglo: Arden seguía en cero y el elixir no se
    gastaba."""
    tope = maximos()[ARDEN][0]
    una = en_los_items(partida, 0)
    usar_sobre_la_segunda(una, FILA_ELIXIR)
    esperado = max(1, 25 * tope // 100)
    assert una.hp(ARDEN) == esperado, (
        "el elixir dejó a Arden en %d HP desde cero, y tenía que quedar en %d"
        % (una.hp(ARDEN), esperado))
    assert una.item(ELIXIR) == 0, "el elixir no se gastó"


def test_el_elixir_no_sirve_sobre_uno_en_pie(partida):
    """`ko_only`: sobre un vivo, `UseItem` dice que no, y no se gasta."""
    una = en_los_items(partida, 10)
    usar_sobre_la_segunda(una, FILA_ELIXIR)
    assert una.hp(ARDEN) == 10, (
        "el elixir curó a Arden, que estaba en pie: quedó en %d"
        % una.hp(ARDEN))
    assert una.item(ELIXIR) == 1, "el elixir se gastó sobre uno en pie"


def test_el_ultimo_elixir_sale_de_la_lista_al_volver(partida):
    """`Scene_Item::Continue` rehace la lista: el elixir, gastado, ya no está,
    y el cursor que estaba sobre él baja al que ahora ocupa su lugar."""
    from port import menus
    una = en_los_items(partida, 0)
    usar_sobre_la_segunda(una, FILA_ELIXIR)
    una.tocar_cuadros("b", TITULO_AIRE)
    db, skin = datos.base(), datos.skin()
    quedan = {SANDWICH: 2, VINO: 1, BOTAS: 1}
    esperada = menus.render_items(skin, db, quedan, FILA_ELIXIR, 0,
                                   db.font_id)
    comparar_pantalla(una, esperada,
                      que="la lista, al volver sin el elixir,")


# --- síntoma 2: volver a entrar sin cerrar el menú ----------------------------

def test_la_eleccion_se_ve_igual_al_volver_a_entrar(partida):
    """La elección entrando derecho desde la lista, y otra vez después de
    volver con B, contra `render_objetivo`: las dos tienen que ser la misma.

    Lo que la rompía era la última fila de la lista, que acá son las botas, en
    gris: `ranura_rect_subir` leía de `temp` los bytes por fila **en dieciséis
    bits**, `menu_grupo_pintar` le escribía sólo el byte bajo, y el alto
    quedaba con la variante de la última letra de la lista —1, gris—. Así que
    el primer DMA de la primera fila subía 256 bytes de más encima del
    tilemap.

    A taro le andaba la primera vez porque había movido el cursor, y mover el
    cursor repinta la descripción, que es en blanco; volver de la elección
    repinta la lista entera, y la variante queda en la de la última fila. Acá
    el cursor no se mueve, así que ya la primera entrada sale rota: visto en
    rojo sin el arreglo, 1580 pixeles.
    """
    una = en_los_items(partida, 10)
    una.tocar_cuadros("a", TITULO_AIRE)
    assert diferencia_con_la_eleccion(una, 0, {ARDEN: 10}, 2) == 0, (
        "la elección, entrando derecho desde la lista, difiere de la "
        "referencia; está en pruebas/snapshots/pantallas/curar-eleccion*.png")
    una.tocar_cuadros("b", TITULO_AIRE)
    una.tocar_cuadros("a", TITULO_AIRE)
    assert diferencia_con_la_eleccion(una, 0, {ARDEN: 10}, 2) == 0, (
        "la elección, al volver a entrar sin cerrar el menú, difiere de la "
        "referencia; está en pruebas/snapshots/pantallas/curar-eleccion*.png")


# --- la elección como la de RM2k ----------------------------------------------

def test_la_eleccion_con_el_sandwich_sobre_la_segunda(partida):
    """La golden de la elección de actor: el Cold Sandwich, con su nombre y
    cuántos quedan a la izquierda, y la barra sobre la segunda fila del
    grupo. Es el caso que taro dio el 2026-09-28 para compararla con la de
    RM2k (`Scene_ActorTarget`)."""
    from tanda import golden
    una = en_los_items(partida, 10)
    una.tocar_cuadros("a", TITULO_AIRE)  # la elección de actor
    una.tocar_cuadros("down")           # la segunda fila
    golden("eleccion-sandwich", una.imagen())

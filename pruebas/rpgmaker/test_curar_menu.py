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

El caso `curar-menu` da dos sándwiches, un elixir y unas botas. Las botas
—equipo, en gris— están para el síntoma 2: son las últimas de la lista, así que
son lo último que la pantalla de ítems pinta antes de abrir la elección.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools"))

from consola import TITULO_AIRE                             # noqa: E402
from test_menu import abrir, tocar                          # noqa: E402

TALAN, ARDEN = 14, 15
SANDWICH, ELIXIR, BOTAS = 97, 115, 262
INVENTARIO = {SANDWICH: 2, ELIXIR: 1, BOTAS: 1}


def poner_hp(una, actor, valor):
    una.consola.escribir_ram(una.simbolos["FAR_HP"] + 2 * actor,
                             [valor & 0xFF, valor >> 8])


def en_los_items(partida, hp_arden):
    """El grupo de Talan y Arden, Arden con `hp_arden`, y la pantalla de
    ítems abierta con el cursor en el sándwich, que es el primero."""
    una = partida(caso="curar-menu")
    una.correr(5)
    una.poner_grupo(TALAN, ARDEN)
    poner_hp(una, ARDEN, hp_arden)
    una.correr(30)
    abrir(una)
    tocar(una, "a", TITULO_AIRE)
    assert una.menu_abierto()
    return una


def usar_sobre_arden(una, fila_del_item):
    """El ítem de esa fila, sobre la segunda fila del grupo."""
    for _ in range(fila_del_item):
        tocar(una, "down")
    tocar(una, "a", TITULO_AIRE)        # la elección de actor
    tocar(una, "down")                  # Arden
    tocar(una, "a", 20)


def diferencia_con_la_eleccion(una, elegida, hp):
    """Cuántos pixeles, a 15 bits, difiere la pantalla de `render_objetivo`."""
    from rpgmaker import lcf
    from port import titulo, ventana
    from render.render_map import GAME_DIR
    from tanda import quince_bits
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    skin = ventana.skin(GAME_DIR, db.system_name)
    captura = una.imagen().convert("RGB")
    esperada = titulo.render_objetivo(skin, db, 4, (TALAN, ARDEN), elegida,
                                      db.font_id, None, GAME_DIR, hp)
    distintos = sum(1 for x, y in zip(quince_bits(captura),
                                      quince_bits(esperada)) if x != y)
    if distintos:
        donde = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "rom", "shots")
        os.makedirs(donde, exist_ok=True)
        captura.save(os.path.join(donde, "prueba-curar-eleccion.png"))
        esperada.save(os.path.join(donde,
                                   "prueba-curar-eleccion.esperado.png"))
    return distintos


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
    tocar(una, "a", TITULO_AIRE)
    assert diferencia_con_la_eleccion(una, 0, {ARDEN: 10}) == 0, (
        "la elección, entrando derecho desde la lista, difiere de la "
        "referencia; está en rom/shots/prueba-curar-eleccion*.png")
    tocar(una, "b", TITULO_AIRE)
    tocar(una, "a", TITULO_AIRE)
    assert diferencia_con_la_eleccion(una, 0, {ARDEN: 10}) == 0, (
        "la elección, al volver a entrar sin cerrar el menú, difiere de la "
        "referencia; está en rom/shots/prueba-curar-eleccion*.png")

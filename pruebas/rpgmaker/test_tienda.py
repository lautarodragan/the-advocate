"""La tienda: el vendedor de armas de Lashe City Interiors —EV0021 del mapa
10, `OpenShop` tipo 0 y juego de mensajes 0— abierto por el camino de verdad,
A para el mensaje y A para cerrarlo, y cada modo de `Scene_Shop` pixel por
pixel contra `pantallas.pantalla_tienda`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))
from port import pantallas as P                         # noqa: E402

from consola import TITULO_AIRE
from test_menu import tocar

VENDE = [96, 92, 93]                    # el cuchillo, el caño y la cachiporra
CANO = 92
ORO = 150
KERSH = 11


def db_y_skin():
    from rpgmaker import lcf
    from port import ventana
    from render.render_map import GAME_DIR
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    return db, ventana.skin(GAME_DIR, db.system_name)


def oro(una):
    b = una.consola.ram(una.simbolos["oro"], 3)
    return b[0] | (b[1] << 8) | (b[2] << 16)


def entrar(partida):
    una = partida(caso="en-10")
    una.correr(5)
    una.poner_grupo(KERSH)
    una.consola.escribir_ram(una.simbolos["oro"],
                             list(ORO.to_bytes(3, "little")))
    una.ir_al_mapa(10, 42, 6)
    una.poner_byte("hero_dir", 0)       # mirando al vendedor
    una.correr(5)
    una.tocar("a")                      # "Yo. I got weapons."
    una.correr(40)
    tocar(una, "a", 0)                  # y la tienda, que congela el reloj
    for _ in range(60):
        if una.menu_abierto():
            break
        una.consola.correr(1)
    assert una.menu_abierto(), "la tienda no se abrió"
    una.consola.correr(TITULO_AIRE)
    return una


def comparar(una, esperada, nombre):
    from tanda import quince_bits
    captura = una.imagen().convert("RGB")
    distintos = sum(1 for x, y in zip(quince_bits(captura), quince_bits(esperada))
                    if x != y)
    if distintos:
        donde = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "rom", "shots")
        os.makedirs(donde, exist_ok=True)
        captura.save(os.path.join(donde, "prueba-%s.png" % nombre))
        esperada.save(os.path.join(donde, "prueba-%s.esperado.png" % nombre))
    assert distintos == 0, (
        "%s difiere de la referencia en %d pixeles; están en "
        "rom/shots/prueba-%s*.png" % (nombre, distintos, nombre))


def test_comprar_y_vender(partida):
    db, skin = db_y_skin()
    una = entrar(partida)
    equipos = [list(db.actors[KERSH].initial_equipment)]

    def ver(modo, inv, oro_, elegido=0, cuantos=1, resaludo=False, nombre=""):
        comparar(una, P.pantalla_tienda(
            db, 0, 0, VENDE, oro_, inv, equipos, modo, elegido, 0, cuantos,
            resaludo).render(skin, db.font_id), "tienda-" + nombre)

    ver(P.TI_PRINCIPAL, {}, ORO, nombre="principal")
    tocar(una, "a", 8)
    ver(P.TI_COMPRAR, {}, ORO, nombre="comprar")
    tocar(una, "down", 8)
    ver(P.TI_COMPRAR, {}, ORO, 1, nombre="comprar-2")
    tocar(una, "a", 8)
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, nombre="cuantos")
    tocar(una, "right", 8)
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, 2, nombre="cuantos-2")
    tocar(una, "right", 8)              # 150 / 65: no alcanza para tres
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, 2, nombre="cuantos-tope")
    tocar(una, "a", 8)
    queda = ORO - 2 * 65
    assert oro(una) == queda
    assert una.item(CANO) == 2
    ver(P.TI_COMPRADO, {CANO: 2}, queda, 1, nombre="comprado")
    una.consola.correr(P.TI_SEGUNDO)
    ver(P.TI_COMPRAR, {CANO: 2}, queda, 1, nombre="comprar-despues")
    tocar(una, "b", 8)
    ver(P.TI_PRINCIPAL, {CANO: 2}, queda, 0, resaludo=True,
        nombre="resaludo")
    tocar(una, "down", 8)
    tocar(una, "a", 8)
    ver(P.TI_VENDER, {CANO: 2}, queda, nombre="vender")
    tocar(una, "a", 8)
    tocar(una, "up", 8)                 # +10, topado en los dos que tiene
    ver(P.TI_CUANTOS_VENTA, {CANO: 2}, queda, 0, 2, nombre="cuantos-venta")
    tocar(una, "a", 8)
    assert oro(una) == queda + 2 * (65 // 2)
    assert una.item(CANO) == 0
    una.consola.correr(P.TI_SEGUNDO)
    tocar(una, "b", 8)
    tocar(una, "down", 8)
    tocar(una, "down", 8)
    tocar(una, "a", 20)                 # Leave
    assert not una.menu_abierto(), "Leave no cerró la tienda"

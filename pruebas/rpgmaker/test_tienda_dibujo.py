"""La tienda: el vendedor de armas de Lashe City Interiors —EV0021 del mapa
10, `OpenShop` tipo 0 y juego de mensajes 0— abierto por el camino de verdad,
A para el mensaje y A para cerrarlo, y cada modo de `Scene_Shop` pixel por
pixel contra `pantallas.pantalla_tienda`.
"""

from port import pantallas as P

from consola import TITULO_AIRE
import datos
from dibujo import comparar_pantalla

VENDE = [96, 92, 93]                    # el cuchillo, el caño y la cachiporra
CANO = 92
ORO = 150
KERSH = 11


def entrar(partida):
    una = partida(caso="en-10")
    una.correr(5)
    una.poner_grupo(KERSH)
    una.poner_oro(ORO)
    una.ir_al_mapa(10, 42, 6)
    una.poner_byte("hero_dir", una.simbolos["DIR_UP"])  # mirando al vendedor
    una.correr(5)
    una.tocar_ticks("a")                # "Yo. I got weapons."
    una.correr(40)
    una.tocar_cuadros("a", 0)           # y la tienda, que congela el reloj
    for _ in range(60):
        if una.menu_abierto():
            break
        una.consola.correr(1)
    assert una.menu_abierto(), "la tienda no se abrió"
    una.consola.correr(TITULO_AIRE)
    return una


def test_comprar_y_vender(partida):
    db, skin = datos.base(), datos.skin()
    una = entrar(partida)
    equipos = [list(db.actors[KERSH].initial_equipment)]

    def ver(modo, inv, oro_, elegido=0, cuantos=1, resaludo=False, nombre=""):
        comparar_pantalla(una, P.pantalla_tienda(
            db, 0, 0, VENDE, oro_, inv, equipos, modo, elegido, 0, cuantos,
            resaludo).render(skin, db.font_id), "tienda-" + nombre)

    ver(P.TI_PRINCIPAL, {}, ORO, nombre="principal")
    una.tocar_cuadros("a", 8)
    ver(P.TI_COMPRAR, {}, ORO, nombre="comprar")
    una.tocar_cuadros("down", 8)
    ver(P.TI_COMPRAR, {}, ORO, 1, nombre="comprar-2")
    una.tocar_cuadros("a", 8)
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, nombre="cuantos")
    una.tocar_cuadros("right", 8)
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, 2, nombre="cuantos-2")
    una.tocar_cuadros("right", 8)       # 150 / 65: no alcanza para tres
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, 2, nombre="cuantos-tope")
    una.tocar_cuadros("a", 8)
    queda = ORO - 2 * 65
    assert una.oro() == queda
    assert una.item(CANO) == 2
    ver(P.TI_COMPRADO, {CANO: 2}, queda, 1, nombre="comprado")
    una.consola.correr(P.TI_SEGUNDO)
    ver(P.TI_COMPRAR, {CANO: 2}, queda, 1, nombre="comprar-despues")
    una.tocar_cuadros("b", 8)
    ver(P.TI_PRINCIPAL, {CANO: 2}, queda, 0, resaludo=True,
        nombre="resaludo")
    una.tocar_cuadros("down", 8)
    una.tocar_cuadros("a", 8)
    ver(P.TI_VENDER, {CANO: 2}, queda, nombre="vender")
    una.tocar_cuadros("a", 8)
    una.tocar_cuadros("up", 8)          # +10, topado en los dos que tiene
    ver(P.TI_CUANTOS_VENTA, {CANO: 2}, queda, 0, 2, nombre="cuantos-venta")
    una.tocar_cuadros("a", 8)
    assert una.oro() == queda + 2 * (65 // 2)
    assert una.item(CANO) == 0
    una.consola.correr(P.TI_SEGUNDO)
    una.tocar_cuadros("b", 8)
    una.tocar_cuadros("down", 8)
    una.tocar_cuadros("down", 8)
    una.tocar_cuadros("a", 20)          # Leave
    assert not una.menu_abierto(), "Leave no cerró la tienda"

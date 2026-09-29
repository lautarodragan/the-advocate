"""La tienda: tres tenderos de Lashe City Interiors, el mapa 10, abiertos por
el camino de verdad —A para el mensaje y A para cerrarlo—, y cada modo de
`Scene_Shop` pixel por pixel contra `pantallas.pantalla_tienda`, con las
ventanas y la barra.

* El de armas, EV0021: `OpenShop` tipo 0 y juego de mensajes 0, tres ítems.
  Cada modo, una vez.
* El de armaduras, EV0023: el juego 1, cuyo resaludo ocupa dos renglones y
  baja las órdenes uno; y vender con una lista más larga que su ventana.
* El de repuestos, EV0025 con el switch 150: once ítems, así que la lista de
  comprar se corre.

Entre los tres, la barra pasa por cada lugar cuyo parche es distinto —la
última fila de cada lista y la última orden, que cruzan la franja del fondo
de su ventana: ver `pantallas.tienda_compacta`—.
"""

from port import pantallas as P

from consola import TITULO_AIRE
import datos
from dibujo import comparar_pantalla
from tanda import golden

VENDE = [96, 92, 93]                    # el cuchillo, el caño y la cachiporra
CANO = 92
ORO = 150
KERSH = 11


def entrar(partida, x=42, y=6, oro=ORO, inventario=None, switches=()):
    una = partida(caso="en-10")
    una.correr(5)
    una.poner_grupo(KERSH)
    una.poner_oro(oro)
    for numero, cuantos in (inventario or {}).items():
        una.consola.escribir_ram(una.simbolos["FAR_ITEMS"] + numero,
                                 [cuantos])
    una.prender(*switches)
    una.ir_al_mapa(10, x, y)
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

    def ver(modo, inv, oro_, elegido=0, cuantos=1, resaludo=False, nombre="",
            congelar=False):
        comparar_pantalla(una, P.pantalla_tienda(
            db, 0, 0, VENDE, oro_, inv, equipos, modo, elegido, 0, cuantos,
            resaludo).render(skin, db.font_id), "tienda-" + nombre)
        if congelar:
            golden("tienda-" + nombre, una.imagen())

    ver(P.TI_PRINCIPAL, {}, ORO, nombre="principal", congelar=True)
    una.tocar_cuadros("a", 8)
    ver(P.TI_COMPRAR, {}, ORO, nombre="comprar")
    una.tocar_cuadros("down", 8)
    ver(P.TI_COMPRAR, {}, ORO, 1, nombre="comprar-2", congelar=True)
    una.tocar_cuadros("a", 8)
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, nombre="cuantos")
    una.tocar_cuadros("right", 8)
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, 2, nombre="cuantos-2",
        congelar=True)
    una.tocar_cuadros("right", 8)       # 150 / 65: no alcanza para tres
    ver(P.TI_CUANTOS_COMPRA, {}, ORO, 1, 2, nombre="cuantos-tope")
    una.tocar_cuadros("a", 8)
    queda = ORO - 2 * 65
    assert una.oro() == queda
    assert una.item(CANO) == 2
    ver(P.TI_COMPRADO, {CANO: 2}, queda, 1, nombre="comprado",
        congelar=True)
    una.consola.correr(P.TI_SEGUNDO)
    ver(P.TI_COMPRAR, {CANO: 2}, queda, 1, nombre="comprar-despues")
    una.tocar_cuadros("b", 8)
    ver(P.TI_PRINCIPAL, {CANO: 2}, queda, 0, resaludo=True,
        nombre="resaludo")
    una.tocar_cuadros("down", 8)
    una.tocar_cuadros("a", 8)
    ver(P.TI_VENDER, {CANO: 2}, queda, nombre="vender", congelar=True)
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


# El de armaduras: el juego 1, y diez ítems en el inventario para vender —
# ocho entran en la lista—.
ARMADURAS = [110, 113, 112, 111]
INVENTARIO = {n: 1 for n in (92, 93, 96, 110, 111, 112, 113, 124, 125, 127)}


def test_el_resaludo_de_dos_renglones_y_vender_con_la_lista_corrida(partida):
    db, skin = datos.base(), datos.skin()
    una = entrar(partida, 42, 37, 5000, INVENTARIO)
    equipos = [list(db.actors[KERSH].initial_equipment)]
    inv = dict(INVENTARIO)

    def ver(modo, oro_, elegido=0, arriba=0, cuantos=1, resaludo=False,
            nombre="", congelar=False):
        comparar_pantalla(una, P.pantalla_tienda(
            db, 0, 1, ARMADURAS, oro_, inv, equipos, modo, elegido, arriba,
            cuantos, resaludo).render(skin, db.font_id),
            "tienda-armaduras-" + nombre)
        if congelar:
            golden("tienda-armaduras-" + nombre, una.imagen())

    ver(P.TI_PRINCIPAL, 5000, nombre="principal")
    una.tocar_cuadros("a", 8)
    una.tocar_cuadros("b", 8)
    ver(P.TI_PRINCIPAL, 5000, 0, resaludo=True, nombre="resaludo")
    una.tocar_cuadros("down", 8)
    una.tocar_cuadros("down", 8)
    ver(P.TI_PRINCIPAL, 5000, 2, resaludo=True, nombre="resaludo-salir",
        congelar=True)
    una.tocar_cuadros("up", 8)
    una.tocar_cuadros("a", 8)
    ver(P.TI_VENDER, 5000, nombre="vender")
    for _ in range(9):
        una.tocar_cuadros("down", 8)
    ver(P.TI_VENDER, 5000, 9, 2, nombre="vender-corrida", congelar=True)
    una.tocar_cuadros("a", 8)
    ver(P.TI_CUANTOS_VENTA, 5000, 9, nombre="cuantos-venta", congelar=True)
    una.tocar_cuadros("a", 8)
    ultimo = sorted(INVENTARIO)[-1]
    oro = 5000 + db.items[ultimo].price // 2
    assert una.oro() == oro
    assert una.item(ultimo) == 0
    inv[ultimo] = 0
    # Vendido el último, el cursor sube al que queda último.
    ver(P.TI_VENDIDO, oro, 8, nombre="vendido", congelar=True)
    una.consola.correr(P.TI_SEGUNDO)
    ver(P.TI_VENDER, oro, 8, 2, nombre="vender-despues")


# El de repuestos: once ítems, cinco a la vista.
REPUESTOS = [129, 130, 282, 278, 279, 135, 269, 283, 271, 270, 287]


def test_comprar_con_la_lista_corrida(partida):
    db, skin = datos.base(), datos.skin()
    una = entrar(partida, 47, 7, 5000, switches=(150,))
    equipos = [list(db.actors[KERSH].initial_equipment)]

    def ver(elegido, arriba, nombre, congelar=False):
        comparar_pantalla(una, P.pantalla_tienda(
            db, 0, 0, REPUESTOS, 5000, {}, equipos, P.TI_COMPRAR, elegido,
            arriba).render(skin, db.font_id), "tienda-repuestos-" + nombre)
        if congelar:
            golden("tienda-repuestos-" + nombre, una.imagen())

    una.tocar_cuadros("a", 8)
    for _ in range(4):
        una.tocar_cuadros("down", 8)
    ver(4, 0, "ultima")
    una.tocar_cuadros("down", 8)
    una.tocar_cuadros("down", 8)
    ver(6, 2, "corrida", congelar=True)
    una.tocar_cuadros("up", 8)
    una.tocar_cuadros("up", 8)
    una.tocar_cuadros("up", 8)
    ver(3, 2, "corrida-arriba")

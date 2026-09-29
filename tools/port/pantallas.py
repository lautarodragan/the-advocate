"""Las pantallas de texto del menú: el equipo y la tienda.

Son pantallas de puro texto, así que no llevan bloques dibujados de antemano
como las ranuras o el menú: usan la fuente de la pantalla de ítems —cada
carácter en dos celdas, en blanco y en gris, ver `menus.pantalla_items`— y
se componen **enteras**. La ROM arma el tilemap completo, 32 por 28 celdas, en
`texto_buf` y lo sube de un DMA por cuadro: son 1792 bytes y entran en el
vblank, así que no hay que cuidar qué se escribe cuándo. Acá `Texto` es lo
mismo: una grilla de (carácter, gris) que se pinta con las mismas celdas.

Lo que hace cada pantalla —qué se equipa, qué suma, qué se compra— también
vive acá, y la ROM lo copia. La geometría es nuestra: RM2k tiene estas
pantallas en 320x240 con ventanas y la fuente a 6 pixeles; acá van en
256x224 y a una letra por celda. Es cosmético y está declarado. El equipo
y la tienda llevan las ventanas del System en BG1, como la pantalla de ítems
—ver `ventanas_equipo` y `ventanas_tienda`—.
"""

from port import constantes
from port import menus
from port.constantes import ALTO, ANCHO, CELL, RANURAS_EQUIPO
from port.eventos import ELEGIR_CURSOR, ITEM_MAX
from port.reglas import parametros

FILAS, COLS = 28, 32


class Texto:
    """La pantalla como grilla de celdas, como la arma la ROM. `ventanas`, si
    está, es lo que dibuja BG1 debajo del texto: ver `ventanas_equipo`."""

    def __init__(self):
        self.celdas = {}
        self.ventanas = None

    def escribir(self, fila, col, texto, gris=0):
        for n, c in enumerate(texto):
            if col + n < COLS:
                self.celdas[(fila, col + n)] = (c, gris)

    def numero(self, fila, col, valor, ancho, gris=0):
        """Alineado a la derecha, con espacios adelante."""
        self.escribir(fila, col, ("%*d" % (ancho, valor))[-ancho:], gris)

    def render(self, sys_img, font_id=None):
        from PIL import Image
        tiles, paletas, glifos = menus.pantalla_items(sys_img, font_id)
        fuera = Image.new("RGB", (ANCHO, ALTO), (0, 0, 0))
        if self.ventanas is not None:
            ventanas = self.ventanas(sys_img)
            fuera.paste(ventanas, (0, 0), ventanas)
        pegar = menus._pintor(fuera, tiles, paletas)
        for (fila, col), (c, gris) in self.celdas.items():
            pegar(glifos[gris][c], fila, col, 1)
        return fuera


def descripcion(pantalla, texto):
    """Los dos renglones de arriba, como en la pantalla de ítems."""
    for n, renglon in enumerate(menus.partir_descripcion(texto)):
        pantalla.escribir(menus.ITEM_DESC_Y // CELL + 2 * n,
                          menus.ITEM_DESC_COL, renglon)


# --- el equipo -----------------------------------------------------------------
#
# `Scene_Equip`: el actor, sus cuatro parámetros, las cinco ranuras con lo que
# tiene puesto, y al elegir una ranura la lista de lo que puede ponerse ahí,
# con los parámetros que quedarían. RM2k muestra la ranura y la lista a la vez;
# acá la lista **reemplaza** a las ranuras mientras se elige. Al final de la
# lista hay una línea vacía, que es sacarse lo que tiene: es lo de RM2k.
#
# Las ventanas son las del System, en BG1 detrás del texto, como en la
# pantalla de ítems —ver `menus.ITEM_VENTANAS`—, y el cursor es su barra roja.
# RM2k tiene cuatro: la ayuda arriba, el actor con sus parámetros a la
# izquierda y las ranuras a la derecha, y la lista abajo en dos columnas. Acá
# el actor y las ranuras no entran lado a lado: con letras de 8 pixeles los
# parámetros con el valor que quedaría son quince celdas y una ranura con lo
# que tiene son veintinueve, y la pantalla tiene treinta y dos. Así que van
# **tres, una debajo de la otra**: la ayuda, igual que la de ítems; la del
# actor, con los parámetros en una columna como RM2k y el nombre a la derecha;
# y la de abajo, que muestra las ranuras o la lista. La lista va en una
# columna, por lo mismo que la de ítems.
EQ_ARMA, EQ_ESCUDO = 0, 1
EQ_ESTADO_Y = menus.ITEM_AYUDA_ALTO
EQ_ABAJO_Y = 128                # cuatro parámetros de 16, y el aire de RM2k
EQ_VENTANAS = ((0, 0, ANCHO, menus.ITEM_AYUDA_ALTO),
               (0, EQ_ESTADO_Y, ANCHO, EQ_ABAJO_Y - EQ_ESTADO_Y),
               (0, EQ_ABAJO_Y, ANCHO, ALTO - EQ_ABAJO_Y))
EQ_ACTOR_FILA = EQ_ESTADO_Y // CELL + 1
EQ_ACTOR_COL = 19              # dos celdas de aire, y doce letras hasta la 30
EQ_PARAMS = tuple((EQ_ACTOR_FILA + 2 * n, 1) for n in range(4))
EQ_PARAM_VALOR = 9              # el valor, tres cifras desde acá, con aire
EQ_PARAM_FLECHA = 12            # ">" y el valor nuevo, en la elección
EQ_RANURA_FILA0 = EQ_ABAJO_Y // CELL + 1
# Las tres ventanas arrancan su texto en la misma columna, la de los
# parámetros: los términos de las ranuras debajo de los de los parámetros, y
# los nombres de la lista debajo de ellos. Lo pidió taro el 2026-09-28, al ver
# las ranuras corridas una celda —la columna 2 salía de hacer coincidir la
# punta de la barra con la de ítems, no de nada que se viera—.
EQ_TEXTO_COL = EQ_PARAMS[0][1]
# El término y lo puesto van pegados, sin una celda en el medio: así los pone
# RM2k —"Right HandModified Blaster-R"— y así entra el nombre más largo antes
# de donde termina la barra, que es donde termina la de ítems.
EQ_RANURA_TERM_COL = EQ_TEXTO_COL
EQ_RANURA_TERM_ANCHO = 10       # "Right Hand"
EQ_RANURA_NOMBRE_COL = EQ_RANURA_TERM_COL + EQ_RANURA_TERM_ANCHO
EQ_RANURA_NOMBRE_ANCHO = 19     # hasta la columna 29, como la cuenta de ítems
EQ_LISTA_FILA0 = EQ_RANURA_FILA0
EQ_LISTA_FILAS = 5              # 17 + 5 * 2 = 27: el marco de abajo
# La lista, con los nombres en esa columna y no en la de ítems; los dos
# puntos y la cuenta, en las de ítems.
EQ_LISTA_NOMBRE_COL = EQ_TEXTO_COL
# Las barras, cuatro pixeles más anchas que el texto de cada lado, como en
# ítems: la de las ranuras sobre el término y lo puesto, que es lo que marca
# RM2k, y la de la lista sobre el nombre y la cuenta. Con el texto en la misma
# columna son la misma barra, y termina donde la de ítems.
EQ_BARRA_RANURA = (EQ_TEXTO_COL * CELL - 4,
                   (menus.ITEM_CIFRAS_COL + 2 - EQ_TEXTO_COL) * CELL
                   + 8)
EQ_BARRA_LISTA = EQ_BARRA_RANURA


def ventanas_equipo(sys_img, barra=None):
    """Las ventanas de la pantalla de equipo, en RGBA y del tamaño de la
    pantalla: lo que dibuja BG1. `barra` es el cursor: el número de ranura, o
    `RANURAS_EQUIPO` más la fila de la lista que se ve."""
    from PIL import Image
    from port import ventana as ventana_mod
    fuera = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    for x, y, ancho, alto in EQ_VENTANAS:
        una = ventana_mod.ventana(sys_img, ancho, alto)
        fuera.paste(una, (x, y), una)
    if barra is not None:
        x, ancho = (EQ_BARRA_RANURA if barra < RANURAS_EQUIPO
                    else EQ_BARRA_LISTA)
        una = ventana_mod.cursor(sys_img, ancho, 2 * CELL)
        fuera.paste(una, (x, fila_de_barra(barra) * CELL), una)
    return fuera


def fila_de_barra(barra):
    """La primera fila de celdas del cursor `barra` de `ventanas_equipo`."""
    if barra < RANURAS_EQUIPO:
        return EQ_RANURA_FILA0 + 2 * barra
    return EQ_LISTA_FILA0 + 2 * (barra - RANURAS_EQUIPO)


def capas_equipo(sys_img):
    """Lo que `menus.marcos` necesita de esta pantalla: las ventanas sin
    cursor y con cada cursor —las ranuras y después las filas de la lista—,
    en el orden en que la ROM los indexa: ver `eq_barra`."""
    return (ventanas_equipo(sys_img),
            [(ventanas_equipo(sys_img, k), fila_de_barra(k))
             for k in range(RANURAS_EQUIPO + EQ_LISTA_FILAS)])


def color_del_valor_nuevo(ahora, luego):
    """`Window_EquipStatus::GetNewParameterColor`: el valor que quedaría va en
    el color 0 si no cambia, en el 2 si sube y en el 3 si baja. En el skin del
    ABL el 2 es un durazno y el 3 el gris de "no se puede"; así lo muestra el
    original, capturado con el RPG_RT de 2015 el 2026-09-28. Devuelve la
    variante de la fuente —`menus.ITEM_*`—, que es lo que la ROM compara en
    `eq_componer`."""
    if luego == ahora:
        return menus.ITEM_BLANCO
    return menus.ITEM_SUBE if luego > ahora else menus.ITEM_GRIS


def tipo_de_ranura(ranura):
    """El tipo de ítem que va en la ranura: 1 arma ... 5 accesorio."""
    return ranura + 1


def candidatos(db, actor, ranura, inventario, items_rom=None):
    """Lo que el actor puede ponerse en la ranura, en orden de número, y el 0
    del final que es sacarse lo que tiene. Sólo lo que la ROM conoce."""
    return [i for i in sorted(inventario)
            if inventario[i] > 0 and (items_rom is None or i in items_rom)
            and db.items[i].type == tipo_de_ranura(ranura)
            and db.items[i].equipable_por(actor)] + [0]


def equipar(db, equipo, inventario, ranura, item):
    """`Game_Actor::ChangeEquipment`: lo que tenía vuelve al inventario y lo
    nuevo sale de ahí. Un arma a dos manos saca el escudo, y un escudo saca
    el arma a dos manos. `item` en 0 es sacarse lo de la ranura."""
    def sacar(r):
        if equipo[r]:
            inventario[equipo[r]] = inventario.get(equipo[r], 0) + 1
            equipo[r] = 0

    sacar(ranura)
    if item:
        inventario[item] -= 1
        equipo[ranura] = item
        if ranura == EQ_ARMA and db.items[item].two_handed:
            sacar(EQ_ESCUDO)
        if ranura == EQ_ESCUDO and equipo[EQ_ARMA] \
                and db.items[equipo[EQ_ARMA]].two_handed:
            sacar(EQ_ARMA)


def pantalla_equipo(db, actor, equipo, inventario, ranura, eligiendo=False,
                    elegido=0, arriba=0, items_rom=None):
    """El equipo del actor: con `eligiendo`, la lista de la ranura con el
    cursor en `elegido` y el primero que se ve en `arriba`."""
    t = Texto()
    t.escribir(EQ_ACTOR_FILA, EQ_ACTOR_COL, db.actors[actor].name)
    lista = candidatos(db, actor, ranura, inventario, items_rom)
    barra = RANURAS_EQUIPO + elegido - arriba if eligiendo else ranura
    t.ventanas = lambda sys_img: ventanas_equipo(sys_img, barra)
    ahora = parametros(db, actor, equipo)
    luego = None
    if eligiendo:
        prueba = list(equipo)
        inv = dict(inventario)
        equipar(db, prueba, inv, ranura, lista[elegido])
        luego = parametros(db, actor, prueba)
        if lista[elegido]:
            descripcion(t, db.items[lista[elegido]].description)
    elif equipo[ranura]:
        descripcion(t, db.items[equipo[ranura]].description)
    for n, (fila, col) in enumerate(EQ_PARAMS):
        t.escribir(fila, col, db.term_params[n][:EQ_PARAM_VALOR - 1],
                   menus.ITEM_ROJO)
        t.numero(fila, col + EQ_PARAM_VALOR, ahora[n], 3)
        if luego is not None:
            t.escribir(fila, col + EQ_PARAM_FLECHA, ">", menus.ITEM_ROJO)
            t.numero(fila, col + EQ_PARAM_FLECHA + 1, luego[n], 3,
                     color_del_valor_nuevo(ahora[n], luego[n]))
    if not eligiendo:
        for r in range(RANURAS_EQUIPO):
            fila = EQ_RANURA_FILA0 + 2 * r
            t.escribir(fila, EQ_RANURA_TERM_COL,
                       db.term_equipo[r][:EQ_RANURA_TERM_ANCHO],
                       menus.ITEM_ROJO)
            if equipo[r]:
                t.escribir(fila, EQ_RANURA_NOMBRE_COL, menus.texto_de_item(
                    db.items[equipo[r]].name, EQ_RANURA_NOMBRE_ANCHO))
        return t
    for f in range(EQ_LISTA_FILAS):
        k = arriba + f
        if k >= len(lista):
            break
        fila = EQ_LISTA_FILA0 + 2 * f
        if lista[k]:
            t.escribir(fila, EQ_LISTA_NOMBRE_COL, menus.texto_de_item(
                db.items[lista[k]].name, menus.ITEM_NOMBRE_ANCHO))
            t.escribir(fila, menus.ITEM_DOS_PUNTOS_COL,
                       ":%2d" % min(inventario[lista[k]], 99))
    return t


# --- la tienda ----------------------------------------------------------------
#
# `Scene_Shop`. En la principal, el saludo del tendero, del juego de términos
# que pide `OpenShop`, y las órdenes. Comprar muestra lo que vende con su
# precio —en gris lo que no alcanza el oro o ya se tiene 99— y el oro, cuántos
# se tienen y cuántos lleva puestos el grupo; vender, el inventario a mitad de
# precio —en gris lo que vale 0—. Elegido uno, la cantidad: derecha e
# izquierda de a uno, arriba y abajo de a diez, entre 1 y lo que se puede.
# Después de cada compra o venta el mensaje dice "listo" un segundo.
#
# Las ventanas son las del System, en BG1 detrás del texto, como en ítems y
# en equipo, y el cursor es su barra roja. RM2k, capturado con el RPG_RT de
# 2015 el 2026-09-28, arma la pantalla así, en 320x240: la ayuda arriba (32
# de alto), con la descripción de lo que marca el cursor; abajo el mensaje
# (80), con las órdenes debajo del saludo en la principal; y en el medio
# (128), la lista a la izquierda (184 de ancho) y a la derecha, una encima de
# la otra, el grupo con sus sprites, "Owned Items" y "Equipped Items" en rojo
# con sus cuentas, y el oro con la moneda en rojo. Vender es la lista a lo
# ancho, sin la columna de la derecha. En la principal el medio es una ventana
# vacía, y al elegir la cantidad o mientras dice "listo", la de la lista queda
# vacía o con el ítem, la cantidad y el total.
#
# Acá, en 256x224 y con letras de 8 pixeles, la lista y la columna de la
# derecha **no entran lado a lado**: un nombre de veinte letras con su precio
# son veintiséis celdas, y "Equipped Items" con su cuenta diecisiete, y la
# pantalla tiene treinta y dos. Así que la columna de la derecha baja, entre
# la lista y el mensaje: "Owned Items" y "Equipped Items" en una ventana, y el
# oro en otra a su derecha, que es donde RM2k lo tiene. La lista queda de
# cinco filas y no de siete. El grupo no está: ver la tarea.
#
# Son tres distribuciones —`TI_CAPAS`—, que comparten la ayuda de arriba:
#
#   la principal    la ayuda vacía, el medio vacío, y abajo el mensaje de
#                   dos renglones con las órdenes debajo
#   la de comprar   la ayuda, la lista de cinco o la cantidad, la cuenta y el
#                   oro, y el mensaje de un renglón; la usan también la
#                   cantidad de vender y los dos "listo"
#   la de vender    la ayuda, la lista de ocho, y el mensaje de un renglón
#
# La ayuda mide 48 y no 32, con dos renglones, como en ítems.
TI_PRINCIPAL, TI_COMPRAR, TI_CUANTOS_COMPRA, TI_COMPRADO, TI_VENDER, \
    TI_CUANTOS_VENTA, TI_VENDIDO = range(7)
TI_SEGUNDO = 60                 # cuadros que dura el "listo": DEFAULT_FPS
TI_CAPA_PRINCIPAL, TI_CAPA_COMPRA, TI_CAPA_VENTA = range(3)
TI_CAPA_DE_MODO = (TI_CAPA_PRINCIPAL, TI_CAPA_COMPRA, TI_CAPA_COMPRA,
                   TI_CAPA_COMPRA, TI_CAPA_VENTA, TI_CAPA_COMPRA,
                   TI_CAPA_COMPRA)
TI_MEDIO_Y = menus.ITEM_AYUDA_ALTO             # 48
# La principal: el mensaje abajo con dos renglones —el resaludo de los juegos
# 1 y 2 mide 31 y 32 letras y en un renglón entran 30— y las tres órdenes.
# Las órdenes van **pegadas al mensaje**, como en RM2k: con un saludo de un
# renglón arrancan uno más arriba, y la ventana tiene lugar para el caso de
# dos.
TI_PRINCIPAL_MSG_Y = 128
TI_PRINCIPAL_MSG_FILA = TI_PRINCIPAL_MSG_Y // CELL + 1     # 17
TI_ORDEN_COL = 3                # 16 pixeles más adentro que el mensaje: RM2k
TI_ORDEN_POSICIONES = 4         # la primera, con un saludo de un renglón
# La de comprar: la cuenta y el oro debajo de la lista, lado a lado, y el
# mensaje de un renglón.
TI_ESTADO_Y = 144
TI_MSG_Y = 192
TI_ORO_X = 152                  # "Equipped Items" y dos cifras, y el marco
TI_MSG_FILA = TI_MSG_Y // CELL + 1                          # 25
TI_TENGO_FILA = TI_ESTADO_Y // CELL + 1                     # 19
TI_LLEVO_FILA = TI_TENGO_FILA + 2
TI_ESTADO_COL = 1
TI_ESTADO_NUM = TI_ORO_X // CELL - 3     # dos cifras, hasta el marco
TI_ORO_FILA = TI_TENGO_FILA + 1                 # en el medio de su ventana
TI_ORO_COL = 28                 # la última cifra del oro; la moneda detrás
TI_LISTA_FILA0 = TI_MEDIO_Y // CELL + 1                     # 7
TI_LISTA_COL = 1
TI_LISTA_FILAS_COMPRA = 5       # 7 + 5 * 2 = 17: el marco de abajo
TI_LISTA_FILAS_VENTA = 8        # 7 + 8 * 2 = 23
TI_PRECIO_COL = 29              # la última cifra del precio
# La cantidad: el ítem, "x" y las dos cifras, que llevan la barra, y el total
# debajo, como RM2k, que los pone a un tercio de la ventana.
TI_CUANTOS_FILA = TI_LISTA_FILA0 + 2                               # 9
TI_CUANTOS_X_COL = 24
TI_CUANTOS_COL = 26             # dos cifras
TI_TOTAL_FILA = TI_CUANTOS_FILA + 4
TI_VENTANAS = {
    TI_CAPA_PRINCIPAL: ((0, TI_MEDIO_Y, ANCHO,
                         TI_PRINCIPAL_MSG_Y - TI_MEDIO_Y),
                        (0, TI_PRINCIPAL_MSG_Y, ANCHO,
                         ALTO - TI_PRINCIPAL_MSG_Y)),
    TI_CAPA_COMPRA: ((0, TI_MEDIO_Y, ANCHO, TI_ESTADO_Y - TI_MEDIO_Y),
                     (0, TI_ESTADO_Y, TI_ORO_X, TI_MSG_Y - TI_ESTADO_Y),
                     (TI_ORO_X, TI_ESTADO_Y, ANCHO - TI_ORO_X,
                      TI_MSG_Y - TI_ESTADO_Y),
                     (0, TI_MSG_Y, ANCHO, ALTO - TI_MSG_Y)),
    TI_CAPA_VENTA: ((0, TI_MEDIO_Y, ANCHO, TI_MSG_Y - TI_MEDIO_Y),
                    (0, TI_MSG_Y, ANCHO, ALTO - TI_MSG_Y)),
}
# Las barras. Las de las listas son la del equipo —cuatro pixeles antes del
# nombre y hasta cuatro después del precio o la cuenta—. La de las órdenes
# arranca donde el mensaje y termina donde las otras: en RM2k cruza la
# ventana. La de la cantidad, sobre las dos cifras, con dos pixeles de aire
# como las demás.
TI_BARRA_LISTA = (TI_LISTA_COL * CELL - 4,
                  (TI_PRECIO_COL + 1 - TI_LISTA_COL) * CELL + 8)
TI_BARRA_ORDEN = (12, TI_BARRA_LISTA[0] + TI_BARRA_LISTA[1] - 12)
TI_BARRA_CUANTOS = (TI_CUANTOS_COL * CELL - 4, 2 * CELL + 8)
# Dónde van en la VRAM. Los tiles, con **su propia base de BG1**: en la de
# la fuente no queda lugar —ítems y equipo llegan justo a $3800—, y
# `$4000..$4C00` está siempre en el banco de BG1 que `load_map` repone al
# cerrar; la elección de actor usa lo mismo, pero nunca está abierta a la vez.
# El tilemap, donde el de ítems y equipo. Lo controla `_controlar_tienda`,
# en el conversor.
TI_VRAM = 0x4000
TI_MAPA = menus.ITEM_MARCO_MAPA


def barras_tienda(capa):
    """Los lugares del cursor de la capa, en el orden en que la ROM los
    cuenta: `(x, ancho, fila)`, con `fila` la primera de las dos filas de
    celdas que cubre."""
    if capa == TI_CAPA_PRINCIPAL:
        return [TI_BARRA_ORDEN + (TI_PRINCIPAL_MSG_FILA + 2 + 2 * n,)
                for n in range(TI_ORDEN_POSICIONES)]
    filas = (TI_LISTA_FILAS_COMPRA if capa == TI_CAPA_COMPRA
             else TI_LISTA_FILAS_VENTA)
    barras = [TI_BARRA_LISTA + (TI_LISTA_FILA0 + 2 * f,)
              for f in range(filas)]
    if capa == TI_CAPA_COMPRA:
        barras.append(TI_BARRA_CUANTOS + (TI_CUANTOS_FILA,))
    return barras


def ventanas_tienda(sys_img, capa, barra=None):
    """Las ventanas de la tienda en la capa `capa`, en RGBA y del tamaño de la
    pantalla: lo que dibuja BG1. `barra` es el lugar del cursor en
    `barras_tienda(capa)`."""
    from PIL import Image
    from port import ventana as ventana_mod
    fuera = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    for x, y, ancho, alto in ((0, 0, ANCHO, TI_MEDIO_Y),) \
            + TI_VENTANAS[capa]:
        una = ventana_mod.ventana(sys_img, ancho, alto)
        fuera.paste(una, (x, y), una)
    if barra is not None:
        x, ancho, fila = barras_tienda(capa)[barra]
        una = ventana_mod.cursor(sys_img, ancho, 2 * CELL)
        fuera.paste(una, (x, fila * CELL), una)
    return fuera


def capas_tienda(sys_img):
    """Lo que `menus.marcos` necesita de la tienda: cada capa sin cursor, y
    con cada cursor desde su primera fila de celdas."""
    return [(ventanas_tienda(sys_img, capa),
             [(ventanas_tienda(sys_img, capa, k), fila)
              for k, (_, _, fila) in enumerate(barras_tienda(capa))])
            for capa in (TI_CAPA_PRINCIPAL, TI_CAPA_COMPRA, TI_CAPA_VENTA)]


def barra_de_tienda(modo, elegido, arriba, dos_renglones):
    """El lugar de la barra en `barras_tienda` de la capa del modo, o None:
    los dos "listo" no tienen cursor."""
    if modo == TI_PRINCIPAL:
        return elegido + (1 if dos_renglones else 0)
    if modo in (TI_COMPRAR, TI_VENDER):
        return elegido - arriba
    if modo in (TI_CUANTOS_COMPRA, TI_CUANTOS_VENTA):
        return TI_LISTA_FILAS_COMPRA
    return None


def tienda_compacta(mapas):
    """Lo que la ROM guarda de `marcos(capas_tienda(...))`, que es mucho menos
    que lo que `marcos` devuelve.

    * **Las tres capas comparten las filas de la ayuda**, que se suben una
      vez al abrir: se comprueba que sean iguales.
    * **El resto de cada capa, como tramos de filas**, y un tramo que ya está
      guardado —de otra capa, o de antes en la misma— no se guarda de nuevo.
    * **Cada barra, sólo donde cambia**: el rectángulo de celdas que difiere
      de su capa sin cursor, y un rectángulo igual a otro no se repite.

    Devuelve `(filas, arriba, capas, parches, barras)`: `filas` las filas del
    tilemap guardadas, de a 32 palabras, con las `arriba` de la ayuda
    primero; `capas[c]` los tramos de la capa `c` desde la fila `arriba`,
    como `(fila, origen, cuantas)` con `origen` el índice en `filas`;
    `parches` las palabras de las barras, seguidas; y `barras[c][k]` el
    rectángulo de la barra `k` de la capa `c` como `(fila, col, filas, cols,
    origen)`, con `origen` el índice de su primera palabra en `parches`.
    """
    COLS, FILAS_ = constantes.COLS, constantes.FILAS
    arriba = TI_MEDIO_Y // CELL

    def fila(mapa, n):
        return tuple(mapa[n * COLS:(n + 1) * COLS])

    fondos = [mapa for mapa, _ in mapas]
    if any(fila(f, n) != fila(fondos[0], n)
           for f in fondos for n in range(arriba)):
        raise SystemExit("las capas de la tienda no comparten la ayuda")
    filas = [fila(fondos[0], n) for n in range(arriba)]
    capas = []
    for mapa in fondos:
        tramos, n = [], arriba
        while n < FILAS_:
            largo, origen = 0, None
            for o in range(len(filas)):
                k = 0
                while (n + k < FILAS_ and o + k < len(filas)
                       and filas[o + k] == fila(mapa, n + k)):
                    k += 1
                if k > largo:
                    largo, origen = k, o
            if not largo:
                filas.append(fila(mapa, n))
                largo, origen = 1, len(filas) - 1
            if tramos and tramos[-1][0] + tramos[-1][2] == n \
                    and tramos[-1][1] + tramos[-1][2] == origen:
                d, o, k = tramos.pop()
                tramos.append((d, o, k + largo))
            else:
                tramos.append((n, origen, largo))
            n += largo
        capas.append(tramos)
    parches, vistos, barras = [], {}, []
    for capa, (mapa, cursores) in enumerate(mapas):
        de_capa = []
        for (_, _, fila0), cursor in zip(barras_tienda(capa), cursores):
            distintas = [(f, c) for f in range(2) for c in range(COLS)
                         if cursor[f * COLS + c] != mapa[(fila0 + f) * COLS
                                                         + c]]
            f0 = min(f for f, _ in distintas)
            nf = max(f for f, _ in distintas) + 1 - f0
            c0 = min(c for _, c in distintas)
            nc = max(c for _, c in distintas) + 1 - c0
            trozo = tuple(cursor[(f0 + f) * COLS + c0 + c]
                          for f in range(nf) for c in range(nc))
            if trozo not in vistos:
                vistos[trozo] = len(parches)
                parches.extend(trozo)
            de_capa.append((fila0 + f0, c0, nf, nc, vistos[trozo]))
        barras.append(de_capa)
    return filas, arriba, capas, parches, barras


# Los términos de un juego de mensajes. En el LDB hay tres juegos, y el nombre
# de cada término termina en cuál es: `shop_greeting1`, `shop_greeting2`.
# Hasta el 2026-09-20 acá había un número de chunk —trece seguidos desde
# 0x29—, que andaba porque los tres juegos van uno atrás del otro; ahora es el
# nombre, que es lo que `db.terminos` tiene.
TI_TERMINOS = (
    ("saludo", "shop_greeting"), ("resaludo", "shop_regreeting"),
    ("comprar", "shop_buy"), ("vender", "shop_sell"),
    ("salir", "shop_leave"), ("que_compra", "shop_buy_select"),
    ("cuantos_compra", "shop_buy_number"), ("comprado", "shop_purchased"),
    ("que_vende", "shop_sell_select"),
    ("cuantos_vende", "shop_sell_number"), ("vendido", "shop_sold"),
)
TI_TERMINO_TENGO, TI_TERMINO_LLEVO = "possessed_items", "equipped_items"


def terminos_tienda(db, juego):
    from rpgmaker import lcf
    return {n: lcf.to_string(db.terminos["%s%d" % (t, juego + 1)])
            for n, t in TI_TERMINOS}


def ordenes_tienda(tipo):
    """Qué órdenes hay: `OpenShop` 0 compra y vende, 1 sólo compra, 2 sólo
    vende. Con una sola no hay pantalla principal: se entra derecho."""
    return {0: ("comprar", "vender", "salir"), 1: ("comprar",),
            2: ("vender",)}[tipo]


def puede_comprar(db, numero, oro, inventario):
    """`Window_ShopBuy::CheckEnable`: que alcance y que no tenga 99."""
    precio = db.items[numero].price
    return precio <= oro and inventario.get(numero, 0) < ITEM_MAX


def llevados(equipos, numero):
    """Cuántos lleva puestos el grupo: `GetEquippedItemCount`."""
    return sum(1 for eq in equipos for i in eq if i == numero)


def lista_venta(items_rom, inventario):
    return [i for i in sorted(inventario)
            if inventario[i] > 0 and i in items_rom]


def pantalla_tienda(db, tipo, juego, vende, oro, inventario, equipos, modo,
                    elegido=0, arriba=0, cuantos=1, resaludo=False,
                    items_rom=None):
    """La tienda en `modo`. `vende` son los ítems de `OpenShop`, `equipos`
    el equipo de cada uno del grupo, `elegido` el cursor —de la principal o
    de la lista—, `arriba` el primero que se ve de la lista y `cuantos` la
    cantidad que se está eligiendo."""
    t = Texto()
    term = terminos_tienda(db, juego)
    items_rom = set(items_rom if items_rom is not None else
                    list(vende) + list(inventario))
    mensaje = {TI_PRINCIPAL: "resaludo" if resaludo else "saludo",
               TI_COMPRAR: "que_compra", TI_CUANTOS_COMPRA: "cuantos_compra",
               TI_COMPRADO: "comprado", TI_VENDER: "que_vende",
               TI_CUANTOS_VENTA: "cuantos_vende", TI_VENDIDO: "vendido"}[modo]
    capa = TI_CAPA_DE_MODO[modo]
    renglones = menus.partir_descripcion(term[mensaje])
    rojo = menus.ITEM_ROJO
    if modo == TI_PRINCIPAL:
        for n, renglon in enumerate(renglones):
            t.escribir(TI_PRINCIPAL_MSG_FILA + 2 * n, menus.ITEM_DESC_COL,
                       renglon)
        dos = bool(renglones[1])
        fila0 = TI_PRINCIPAL_MSG_FILA + (4 if dos else 2)
        for n, orden in enumerate(ordenes_tienda(tipo)):
            # Del primer renglón, como la ROM, que los guarda partidos: el
            # juego 0 los trae con un espacio adelante —" Buy"— y partir los
            # renglones lo come.
            t.escribir(fila0 + 2 * n, TI_ORDEN_COL,
                       menus.partir_descripcion(term[orden])[0])
        barra = barra_de_tienda(modo, elegido, arriba, dos)
        t.ventanas = lambda sys_img: ventanas_tienda(sys_img, capa, barra)
        return t
    # Los otros mensajes miden 26 letras a lo sumo: un renglón. Lo controla
    # el conversor.
    t.escribir(TI_MSG_FILA, menus.ITEM_DESC_COL, renglones[0])
    comprando = modo in (TI_COMPRAR, TI_CUANTOS_COMPRA, TI_COMPRADO)
    lista = ([i for i in vende if i in items_rom] if comprando
             else lista_venta(items_rom, inventario))
    barra = barra_de_tienda(modo, elegido, arriba, False) if lista else None
    t.ventanas = lambda sys_img: ventanas_tienda(sys_img, capa, barra)
    if lista:
        descripcion(t, db.items[lista[elegido]].description)
    if capa == TI_CAPA_COMPRA:
        # El oro, y cuántos tiene y lleva puestos el grupo del que marca el
        # cursor.
        cifras = str(min(oro, 999999))
        t.escribir(TI_ORO_FILA, TI_ORO_COL + 1 - len(cifras), cifras)
        t.escribir(TI_ORO_FILA, TI_ORO_COL + 1, db.term_gold, rojo)
        if lista:
            numero = lista[elegido]
            t.escribir(TI_TENGO_FILA, TI_ESTADO_COL,
                       lcf_termino(db, TI_TERMINO_TENGO), rojo)
            t.numero(TI_TENGO_FILA, TI_ESTADO_NUM,
                     inventario.get(numero, 0), 2)
            t.escribir(TI_LLEVO_FILA, TI_ESTADO_COL,
                       lcf_termino(db, TI_TERMINO_LLEVO), rojo)
            t.numero(TI_LLEVO_FILA, TI_ESTADO_NUM, llevados(equipos, numero),
                     2)
    if modo in (TI_CUANTOS_COMPRA, TI_CUANTOS_VENTA):
        numero = lista[elegido]
        precio = db.items[numero].price
        if modo == TI_CUANTOS_VENTA:
            precio //= 2
        t.escribir(TI_CUANTOS_FILA, TI_LISTA_COL, menus.texto_de_item(
            db.items[numero].name, menus.ITEM_NOMBRE_ANCHO))
        t.escribir(TI_CUANTOS_FILA, TI_CUANTOS_X_COL, "x")
        t.numero(TI_CUANTOS_FILA, TI_CUANTOS_COL, cuantos, 2)
        total = str(precio * cuantos)
        t.escribir(TI_TOTAL_FILA, TI_ORO_COL + 1 - len(total), total)
        t.escribir(TI_TOTAL_FILA, TI_ORO_COL + 1, db.term_gold, rojo)
        return t
    if modo in (TI_COMPRADO, TI_VENDIDO):
        return t                # la ventana del medio, vacía: RM2k
    filas = TI_LISTA_FILAS_COMPRA if comprando else TI_LISTA_FILAS_VENTA
    for f in range(filas):
        k = arriba + f
        if k >= len(lista):
            break
        numero = lista[k]
        item = db.items[numero]
        fila = TI_LISTA_FILA0 + 2 * f
        if comprando:
            gris = 0 if puede_comprar(db, numero, oro, inventario) else 1
        else:
            gris = 0 if item.price > 0 else 1
        t.escribir(fila, TI_LISTA_COL, menus.texto_de_item(
            item.name, menus.ITEM_NOMBRE_ANCHO), gris)
        if comprando:
            precio = str(item.price)
            t.escribir(fila, TI_PRECIO_COL + 1 - len(precio), precio, gris)
        else:
            t.escribir(fila, menus.ITEM_DOS_PUNTOS_COL,
                       ":%2d" % min(inventario[numero], 99), gris)
    return t


# --- la batalla ----------------------------------------------------------------
#
# `Scene_Battle_Rpg2k`, pero **de texto y sobre un color plano**. taro lo pidió
# así el 2026-09-12, con todas las letras: *"podemos ignorar desafíos
# relacionados con la imagen de fondo ... así nos podemos enfocar en la
# mecánica de la batalla por turnos"*. Así que no hay fondo, no hay battlers
# dibujados y no hay ventanas: la misma grilla de 32 por 28 celdas que usan el
# equipo y la tienda, sobre negro —ellos, hasta que llegaron sus ventanas—.
#
# Lo que **sí** es de RM2k son las palabras —todas del LDB, ninguna inventada—
# y las cuentas, que viven en `batalla.py`.
#
# Una cosa de esta pantalla no está en RM2k y es una decisión:
#
# * **huir es una orden del actor** y no del grupo. En RM2k "Escape" está en el
#   menú de arriba, antes de elegir qué hace cada uno; meterlo en la lista de
#   cada actor ahorra un modo entero de la máquina. Declarado.
BA_ENEMIGO_FILA0 = 0
BA_GRUPO_FILA0 = 16
BA_MSG_FILA1 = 24
BA_MSG_FILA2 = 26
BA_CURSOR_COL = 0
BA_NOMBRE_COL = 2
BA_NOMBRE_ANCHO = 14
# **Los HP de un enemigo no se ven**, como en RM2k: su renglón es sólo el
# nombre. Con `[debug] enemy_hp` del archivo de proyecto vuelven, en
# estas mismas columnas, para depurar.
BA_HP_COL = 18
BA_HP_NUM = 21                  # tres cifras
BA_BARRA_COL = 24
BA_HP_MAX_NUM = 25              # y las tres del máximo, en el grupo
# Las cinco órdenes del menú de batalla del ABL, en los dos renglones del
# mensaje: tres arriba y dos abajo. Mientras se elige, el de abajo está libre.
#
# Hasta el 2026-09-13 eran tres en un renglón —`Attack`, `Defend`, `Escape`— y
# taro pidió el menú del original, que tiene además `Use Item` y `Tech Skill`.
# El ancho es diez porque es lo que mide la orden más larga: `Tech Skill`, y
# `AgentTrain`, que es como se llama la de Kersh.
BA_ORDEN_ANCHO = 10
# **El orden es el del original**: Attack, la habilidad, Defend, Use Item. En
# una captura del juego de verdad, del 2026-09-12, el menú de Manta dice
# Attack / Slicing / Defend / Use Item. `Escape` no
# está allá —huir es una orden del grupo, de otro menú— y acá va quinta; es la
# simplificación que `batalla.py` declara.
(BA_ORDEN_ATACAR, BA_ORDEN_HABILIDAD, BA_ORDEN_DEFENDER, BA_ORDEN_USAR,
 BA_ORDEN_HUIR) = range(5)
# Por orden: qué término la nombra, en qué renglón va y en qué columna.
#
# **La columna de la habilidad tiene que dejar diez celdas libres**: su texto es
# el `skill_name` del actor, y `AgentTrain` y `Tech Skill` miden diez justos,
# sin dejarle lugar al cursor del que sigue —que va una celda antes del texto—.
# Por eso el renglón de arriba es 1 / 11 / 22 y no 1 / 11 / 21: la habilidad va
# en el medio y Defend arranca una celda más allá. Las otras cuatro palabras
# del ABL miden ocho o menos.
BA_ORDENES = (
    ("atacar", 0, 1),
    ("habilidad", 0, 11),
    ("defender", 0, 22),
    ("usar", 1, 1),
    ("huir", 1, 13),
)

# Ninguna orden está sin hacer desde el 2026-09-13: la habilidad era la única y
# ahora se puede elegir. Queda la tupla porque el conversor la consulta y porque
# es donde va la próxima que se agregue a medias.
#
# Lo que sí se pone en gris es la habilidad **de un actor que no sabe ninguna**
# —Talan, que es de nivel 1 y no aprendió ni la primera— igual que el menú de
# pausa con lo que no lleva a ningún lado.
BA_ORDEN_SIN_HACER = ()

# La lista de habilidades, que ocupa los mismos renglones que la de ítems y por
# lo mismo. Es la forma del original —ver la captura
# `capturas-batalla/auto_20260912_123023.png`—: la descripción de la que marca
# el cursor arriba de todo, y abajo dos columnas con el nombre a la izquierda y
# el costo en SP a la derecha, con un guión delante.
#
# Se lee **por filas**: en la captura, la lista de Manta ordenada por número
# —130, 143, 144, 150— sale Mental Hack y MindShield arriba y MindProbe y
# MindBlast abajo.
#
# La descripción va en un solo renglón y **se corta a treinta y un caracteres**:
# el original la escribe entera con una fuente más chica, y acá un renglón de
# texto ocupa dos filas del tilemap, así que la de abajo no está libre. Es
# deuda declarada.
BA_HAB_DESC_FILA = 0
BA_HAB_DESC_COL = 1
BA_HAB_DESC_ANCHO = 31
BA_HAB_FILA0 = 2
BA_HAB_FILAS = 7
BA_HAB_COLUMNAS = 2
BA_HAB_COLUMNA_DX = 16          # de una columna a la de al lado
BA_HAB_NOMBRE_COL = 2           # relativas al principio de la columna
BA_HAB_NOMBRE_ANCHO = 11
BA_HAB_GUION_COL = 13
# El costo va en **dos cifras y no tres**, que es lo que deja que las dos
# columnas entren en las 32 celdas: la segunda arranca en la 16 y su número
# termina en la 31 justo. Con tres se pasaba de la pantalla. Ningún `sp_cost`
# del ABL llega a 100 —el más caro de las siete que el grupo sabe es 20— y el
# conversor **corta si alguna vez lo hiciera**, en vez de dibujar mal.
BA_HAB_COSTO_COL = 14
BA_HAB_COSTO_CIFRAS = 2

# La lista de ítems ocupa los renglones de los enemigos: mientras se elige qué
# usar, los enemigos no hacen falta y el grupo sí, que es a quién se cura.
BA_ITEM_CUENTA_COL = 18

# El `ShowMessage` de una página de tropa. En RM2k la ventana de mensaje de la
# pelea **tapa la del grupo**: es la misma de 320x80 del mapa, abajo, encima del
# estado y de las órdenes. Acá eso son los cuatro renglones del grupo, que se
# dejan de dibujar mientras el mensaje está en pantalla; los dos del mensaje de
# la pelea quedan vacíos debajo.
#
# El renglón se corta en **treinta y un caracteres**, que es lo que entra
# desde la columna 1 de las 32 de esta pantalla; la ventana del mapa lleva
# treinta y nueve. De los mensajes de los sistemas de Talan hay renglones de
# hasta cuarenta —dos técnicas en uno, "     RainDrop...       GatheringWaves...",
# que ya en la ventana del mapa pierde la última letra— y ésos pierden acá su
# segunda técnica. Es deuda declarada.
BA_PAG_MSG_FILA0 = BA_GRUPO_FILA0
BA_PAG_MSG_COL = 1
BA_PAG_MSG_ANCHO = 31


# Lo que la victoria cuenta va, como en RM2k, en la ventana de mensaje que tapa
# al grupo: los mismos cuatro renglones de `BA_PAG_MSG_FILA0`, con su ancho.
# La primera página es el término de la victoria y la experiencia; cada actor
# que subió de nivel tiene la suya después.
#
# El término de la victoria del ABL no entra en un renglón —" The combat has
# resulted in victory!" son 36— así que el conversor lo parte en dos, en un
# espacio: `renglones_de_la_victoria`. Lo demás se arma en la ROM con un
# número o un nombre en el medio, y lo que el conversor cobra es que entre.
BA_VIC_TERMINO_MAX = 2


def renglones_de_la_victoria(termino, ancho=BA_PAG_MSG_ANCHO):
    """El término de la victoria partido en renglones de `ancho`, en los
    espacios. **Los espacios de adelante se quedan**: RM2k los escribe, y en la
    ventana del mapa de este port también se ven."""
    sangria = termino[:len(termino) - len(termino.lstrip(" "))]
    renglones, actual = [], sangria
    for palabra in termino.split():
        vacio = not actual.strip()
        junto = actual + palabra if vacio else actual + " " + palabra
        if len(junto) <= ancho:
            actual = junto
            continue
        if vacio:
            raise SystemExit("el término de la victoria tiene una palabra más "
                             "larga que el renglón: %r" % palabra)
        renglones.append(actual)
        actual = palabra
    renglones.append(actual)
    return renglones


def renglon_de_experiencia(term, exp):
    """`GetExperienceGainedMessage` de RM2k sin placeholders: el número pegado
    al término. El `\\.` que easyrpg le agrega es una espera, no una letra."""
    return "%d%s" % (exp, term["exp_recibida"])


def renglon_de_nivel(term, nombre, nivel):
    """`GetLevelUpMessage` de RM2k en inglés: "<nombre> <level> <n><level_up>",
    que en el ABL es "Kersh LEVEL 21 achieved!"."""
    return "%s %s %d%s" % (nombre, term["nivel"], nivel, term["subio"])


def renglon_de_habilidad(term, habilidad):
    """`GetLearningMessage`: el nombre pegado al término."""
    return habilidad + term["aprendio"]


def renglon_de_oro(term, oro):
    """`GetGoldReceivedMessage` de RM2k sin placeholders: `gold_recieved_a`,
    un espacio, el número pegado a `gold` y `gold_recieved_b`. En el ABL,
    " You found 285Cr credits!": la moneda y "credits" van los dos, que es lo
    que arma RM2k con estos términos."""
    return "%s %d%s%s" % (term["oro_a"], oro, term["moneda"], term["oro_b"])


def renglon_de_item(term, nombre):
    """`GetItemReceivedMessage` de RM2k: el nombre pegado a `item_recieved`,
    sin espacio en el medio —ése es de RM2k3—. El nombre es el que la ROM
    lleva, cortado a `ITEM_NOMBRE_ANCHO`."""
    from port import menus
    return menus.texto_de_item(nombre, menus.ITEM_NOMBRE_ANCHO) \
        + term["obtenido"]


def cobrar_la_victoria(term, exp_max, actores, habilidades, oro_max=0,
                       items=()):
    """Corta el armado si algún renglón de la victoria no entra en
    `BA_PAG_MSG_ANCHO`: la ROM los arma pegando pedazos y no los parte, así
    que uno largo se pasaría al renglón de abajo. Los niveles se miden con dos
    cifras, que es el tope de RM2k."""
    renglones = ([renglon_de_experiencia(term, exp_max)]
                 + [renglon_de_oro(term, oro_max)]
                 + [renglon_de_item(term, n) for n in items]
                 + [renglon_de_nivel(term, n, 99) for n in actores]
                 + [renglon_de_habilidad(term, h) for h in habilidades])
    largos = [r for r in renglones if len(r) > BA_PAG_MSG_ANCHO]
    if largos:
        raise SystemExit("estos renglones de la victoria no entran en los %d "
                         "caracteres de la ventana: %r"
                         % (BA_PAG_MSG_ANCHO, largos))


def texto_revivio(db):
    """Lo que la pelea escribe detrás del nombre de un caído que un ítem
    levantó: el `message_recovery` del estado 1, el de muerto, que es lo que
    `BattleMessage::GetStateRecoveryMessage` pega al nombre. En el ABL dice
    " has revived!"."""
    from rpgmaker import lcf
    muerto = lcf.por_id(db.secciones["states"])[1]
    return lcf.campo(muerto, "message_recovery")


def texto_de_orden(termino):
    """Una de las cinco órdenes como la escribe la pantalla.

    Los términos del LDB traen espacios adelante —`battle_escape` del ABL dice
    " Escape"— y en el renglón de abajo eso correría el texto de su columna.
    Va acá y no en la ROM porque el conversor emite el texto **ya recortado**:
    así la ROM no tiene que saber recortar.
    """
    return menus.texto_de_item(termino.strip(), BA_ORDEN_ANCHO)


def lcf_termino(db, nombre):
    from rpgmaker import lcf
    return lcf.to_string(db.terminos[nombre])

"""The menu's text screens: equipment and shop.

They are pure text screens, so they carry no blocks drawn in advance like
the slots or the menu: they use the item screen's font —each character in
two cells, in white and in gray, see `menus.pantalla_items`— and are
composed **whole**. The ROM builds the complete tilemap, 32 by 28 cells, in
`texto_buf` and uploads it with one DMA per frame: it is 1792 bytes and fits
in vblank, so there is no need to be careful about what is written when.
Here `Texto` is the same: a grid of (character, gray) painted with the same
cells.

What each screen does —what gets equipped, what adds up, what gets bought—
also lives here, and the ROM copies it. The geometry is ours: RM2k has these
screens at 320x240 with windows and the font at 6 pixels; here they go at
256x224 and one letter per cell. It is cosmetic and it is declared. The
equipment and shop screens carry the System's windows on BG1, like the item
screen —see `ventanas_equipo` and `ventanas_tienda`—.
"""

from port import constantes
from port import menus
from port.constantes import ALTO, ANCHO, CELL, RANURAS_EQUIPO
from port.eventos import ELEGIR_CURSOR, ITEM_MAX
from port.reglas import parametros

FILAS, COLS = 28, 32


class Texto:
    """The screen as a grid of cells, as the ROM builds it. `ventanas`, if
    set, is what BG1 draws under the text: see `ventanas_equipo`."""

    def __init__(self):
        self.celdas = {}
        self.ventanas = None

    def escribir(self, fila, col, texto, gris=0):
        for n, c in enumerate(texto):
            if col + n < COLS:
                self.celdas[(fila, col + n)] = (c, gris)

    def numero(self, fila, col, valor, ancho, gris=0):
        """Right-aligned, with leading spaces."""
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
    """The top two lines, as on the item screen."""
    for n, renglon in enumerate(menus.partir_descripcion(texto)):
        pantalla.escribir(menus.ITEM_DESC_Y // CELL + 2 * n,
                          menus.ITEM_DESC_COL, renglon)


# --- equipment -----------------------------------------------------------------
#
# `Scene_Equip`: the actor, its four parameters, the five slots with what it
# has equipped, and on choosing a slot the list of what can go there, with
# the parameters that would result. RM2k shows the slot and the list at the
# same time; here the list **replaces** the slots while choosing. At the end
# of the list there is an empty line, which is unequipping: it is RM2k's.
#
# The windows are the System's, on BG1 behind the text, as on the item screen
# —see `menus.ITEM_VENTANAS`—, and the cursor is its red bar. RM2k has four:
# the help on top, the actor with its parameters on the left and the slots on
# the right, and the list below in two columns. Here the actor and the slots
# do not fit side by side: with 8-pixel letters the parameters with the value
# that would result are fifteen cells and a slot with what it has is
# twenty-nine, and the screen has thirty-two. So they go **three, one below
# the other**: the help, same as the item screen's; the actor's, with the
# parameters in one column like RM2k and the name on the right; and the
# bottom one, which shows the slots or the list. The list goes in one column,
# for the same reason as the item screen's.
EQ_ARMA, EQ_ESCUDO = 0, 1
EQ_ESTADO_Y = menus.ITEM_AYUDA_ALTO
EQ_ABAJO_Y = 128                # four parameters of 16, and RM2k's spacing
EQ_VENTANAS = ((0, 0, ANCHO, menus.ITEM_AYUDA_ALTO),
               (0, EQ_ESTADO_Y, ANCHO, EQ_ABAJO_Y - EQ_ESTADO_Y),
               (0, EQ_ABAJO_Y, ANCHO, ALTO - EQ_ABAJO_Y))
EQ_ACTOR_FILA = EQ_ESTADO_Y // CELL + 1
EQ_ACTOR_COL = 19              # two cells of spacing, and twelve letters up to 30
EQ_PARAMS = tuple((EQ_ACTOR_FILA + 2 * n, 1) for n in range(4))
EQ_PARAM_VALOR = 9              # the value, three digits from here, with spacing
EQ_PARAM_FLECHA = 12            # ">" and the new value, while choosing
EQ_RANURA_FILA0 = EQ_ABAJO_Y // CELL + 1
# The three windows start their text in the same column, the parameters':
# the slot terms under the parameter terms, and the list names under them.
# taro asked for it on 2026-09-28, on seeing the slots shifted by one cell
# —column 2 came from making the tip of the bar match the item screen's, not
# from anything visible—.
EQ_TEXTO_COL = EQ_PARAMS[0][1]
# The term and what is equipped go together, with no cell in between: that is
# how RM2k puts them —"Right HandModified Blaster-R"— and that is how the
# longest name fits before where the bar ends, which is where the item
# screen's ends.
EQ_RANURA_TERM_COL = EQ_TEXTO_COL
EQ_RANURA_TERM_ANCHO = 10       # "Right Hand"
EQ_RANURA_NOMBRE_COL = EQ_RANURA_TERM_COL + EQ_RANURA_TERM_ANCHO
EQ_RANURA_NOMBRE_ANCHO = 19     # up to column 29, like the item count
EQ_LISTA_FILA0 = EQ_RANURA_FILA0
EQ_LISTA_FILAS = 5              # 17 + 5 * 2 = 27: the bottom frame
# The list, with the names in that column and not in the item screen's; the
# colon and the count, in the item screen's.
EQ_LISTA_NOMBRE_COL = EQ_TEXTO_COL
# The bars, four pixels wider than the text on each side, as on the item
# screen: the slots' over the term and what is equipped, which is what RM2k
# marks, and the list's over the name and the count. With the text in the
# same column they are the same bar, and it ends where the item screen's
# does.
EQ_BARRA_RANURA = (EQ_TEXTO_COL * CELL - 4,
                   (menus.ITEM_CIFRAS_COL + 2 - EQ_TEXTO_COL) * CELL
                   + 8)
EQ_BARRA_LISTA = EQ_BARRA_RANURA


def ventanas_equipo(sys_img, barra=None):
    """The equipment screen's windows, in RGBA and the size of the screen:
    what BG1 draws. `barra` is the cursor: the slot number, or
    `RANURAS_EQUIPO` plus the visible row of the list."""
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
    """The first cell row of cursor `barra` of `ventanas_equipo`."""
    if barra < RANURAS_EQUIPO:
        return EQ_RANURA_FILA0 + 2 * barra
    return EQ_LISTA_FILA0 + 2 * (barra - RANURAS_EQUIPO)


def capas_equipo(sys_img):
    """What `menus.marcos` needs from this screen: the windows without a
    cursor and with each cursor —the slots and then the list rows—, in the
    order the ROM indexes them: see `eq_barra`."""
    return (ventanas_equipo(sys_img),
            [(ventanas_equipo(sys_img, k), fila_de_barra(k))
             for k in range(RANURAS_EQUIPO + EQ_LISTA_FILAS)])


def color_del_valor_nuevo(ahora, luego):
    """`Window_EquipStatus::GetNewParameterColor`: the value that would
    result goes in color 0 if it does not change, in 2 if it goes up and in
    3 if it goes down. In ABL's skin 2 is a peach and 3 the "cannot" gray;
    that is how the original shows it, captured with the 2015 RPG_RT on
    2026-09-28. Returns the font variant —`menus.ITEM_*`—, which is what the
    ROM compares in `eq_componer`."""
    if luego == ahora:
        return menus.ITEM_BLANCO
    return menus.ITEM_SUBE if luego > ahora else menus.ITEM_GRIS


def tipo_de_ranura(ranura):
    """The item type that goes in the slot: 1 weapon ... 5 accessory."""
    return ranura + 1


def candidatos(db, actor, ranura, inventario, items_rom=None):
    """What the actor can put in the slot, in number order, and the 0 at the
    end which is unequipping. Only what the ROM knows."""
    return [i for i in sorted(inventario)
            if inventario[i] > 0 and (items_rom is None or i in items_rom)
            and db.items[i].type == tipo_de_ranura(ranura)
            and db.items[i].equipable_por(actor)] + [0]


def equipar(db, equipo, inventario, ranura, item):
    """`Game_Actor::ChangeEquipment`: what it had goes back to the inventory
    and the new one comes out of there. A two-handed weapon removes the
    shield, and a shield removes the two-handed weapon. `item` at 0 is
    unequipping the slot."""
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
    """The actor's equipment: with `eligiendo`, the slot's list with the
    cursor on `elegido` and the first visible one at `arriba`."""
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


# --- the shop ----------------------------------------------------------------
#
# `Scene_Shop`. On the main one, the shopkeeper's greeting, from the set of
# terms `OpenShop` asks for, and the commands. Buying shows what it sells with
# its price —in gray what the gold does not cover or is already at 99— and
# the gold, how many are owned and how many the party has equipped; selling,
# the inventory at half price —in gray what is worth 0—. Once one is chosen,
# the quantity: right and left by one, up and down by ten, between 1 and what
# is possible. After each purchase or sale the message says "done" for one
# second.
#
# The windows are the System's, on BG1 behind the text, as on the item and
# equipment screens, and the cursor is its red bar. RM2k, captured with the
# 2015 RPG_RT on 2026-09-28, lays the screen out like this, at 320x240: the
# help on top (32 tall), with the description of what the cursor marks; the
# message at the bottom (80), with the commands under the greeting on the main
# one; and in the middle (128), the list on the left (184 wide) and on the
# right, one on top of the other, the party with its sprites, "Owned Items"
# and "Equipped Items" in red with their counts, and the gold with the
# currency in red. Selling is the list at full width, without the right
# column. On the main one the middle is an empty window, and when choosing the
# quantity or while it says "done", the list's is left empty or with the
# item, the quantity and the total.
#
# Here, at 256x224 and with 8-pixel letters, the list and the right column
# **do not fit side by side**: a twenty-letter name with its price is
# twenty-six cells, and "Equipped Items" with its count seventeen, and the
# screen has thirty-two. So the right column goes down, between the list and
# the message: "Owned Items" and "Equipped Items" in one window, and the gold
# in another to its right, which is where RM2k has it. The list is left with
# five rows and not seven. The party is not there: see the task.
#
# There are three layouts —`TI_CAPAS`—, which share the help on top:
#
#   the main one    the help empty, the middle empty, and at the bottom the
#                   two-line message with the commands under it
#   the buy one     the help, the list of five or the quantity, the count and
#                   the gold, and the one-line message; the sell quantity and
#                   both "done"s use it too
#   the sell one    the help, the list of eight, and the one-line message
#
# The help is 48 tall and not 32, with two lines, as on the item screen.
TI_PRINCIPAL, TI_COMPRAR, TI_CUANTOS_COMPRA, TI_COMPRADO, TI_VENDER, \
    TI_CUANTOS_VENTA, TI_VENDIDO = range(7)
TI_SEGUNDO = 60                 # frames the "done" lasts: DEFAULT_FPS
TI_CAPA_PRINCIPAL, TI_CAPA_COMPRA, TI_CAPA_VENTA = range(3)
TI_CAPA_DE_MODO = (TI_CAPA_PRINCIPAL, TI_CAPA_COMPRA, TI_CAPA_COMPRA,
                   TI_CAPA_COMPRA, TI_CAPA_VENTA, TI_CAPA_COMPRA,
                   TI_CAPA_COMPRA)
TI_MEDIO_Y = menus.ITEM_AYUDA_ALTO             # 48
# The main one: the message at the bottom with two lines —the regreeting of
# sets 1 and 2 is 31 and 32 letters and a line fits 30— and the three
# commands. The commands go **right after the message**, as in RM2k: with a
# one-line greeting they start one line higher, and the window has room for
# the two-line case.
TI_PRINCIPAL_MSG_Y = 128
TI_PRINCIPAL_MSG_FILA = TI_PRINCIPAL_MSG_Y // CELL + 1     # 17
TI_ORDEN_COL = 3                # 16 pixels further in than the message: RM2k
TI_ORDEN_POSICIONES = 4         # the first, with a one-line greeting
# The buy one: the count and the gold under the list, side by side, and the
# one-line message.
TI_ESTADO_Y = 144
TI_MSG_Y = 192
TI_ORO_X = 152                  # "Equipped Items" and two digits, and the frame
TI_MSG_FILA = TI_MSG_Y // CELL + 1                          # 25
TI_TENGO_FILA = TI_ESTADO_Y // CELL + 1                     # 19
TI_LLEVO_FILA = TI_TENGO_FILA + 2
TI_ESTADO_COL = 1
TI_ESTADO_NUM = TI_ORO_X // CELL - 3     # two digits, up to the frame
TI_ORO_FILA = TI_TENGO_FILA + 1                 # in the middle of its window
TI_ORO_COL = 28                 # the gold's last digit; the currency after it
TI_LISTA_FILA0 = TI_MEDIO_Y // CELL + 1                     # 7
TI_LISTA_COL = 1
TI_LISTA_FILAS_COMPRA = 5       # 7 + 5 * 2 = 17: the bottom frame
TI_LISTA_FILAS_VENTA = 8        # 7 + 8 * 2 = 23
TI_PRECIO_COL = 29              # the price's last digit
# The quantity: the item, "x" and the two digits, which carry the bar, and
# the total below, like RM2k, which puts them at a third of the window.
TI_CUANTOS_FILA = TI_LISTA_FILA0 + 2                               # 9
TI_CUANTOS_X_COL = 24
TI_CUANTOS_COL = 26             # two digits
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
# The bars. The lists' are the equipment one —four pixels before the name and
# up to four after the price or the count—. The commands' starts where the
# message does and ends where the others do: in RM2k it crosses the window.
# The quantity's, over the two digits, with two pixels of spacing like the
# rest.
TI_BARRA_LISTA = (TI_LISTA_COL * CELL - 4,
                  (TI_PRECIO_COL + 1 - TI_LISTA_COL) * CELL + 8)
TI_BARRA_ORDEN = (12, TI_BARRA_LISTA[0] + TI_BARRA_LISTA[1] - 12)
TI_BARRA_CUANTOS = (TI_CUANTOS_COL * CELL - 4, 2 * CELL + 8)
# Where they go in VRAM. The tiles, with **their own BG1 base**: there is no
# room left in the font's —items and equipment reach exactly $3800—, and
# `$4000..$4C00` is always in the BG1 bank that `load_map` restores on
# closing; the actor choice uses the same, but it is never open at the same
# time. The tilemap, where the items' and equipment's is. `_controlar_tienda`
# checks it, in the converter.
TI_VRAM = 0x4000
TI_MAPA = menus.ITEM_MARCO_MAPA


def barras_tienda(capa):
    """The layer's cursor positions, in the order the ROM counts them:
    `(x, ancho, fila)`, with `fila` the first of the two cell rows it
    covers."""
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
    """The shop's windows in layer `capa`, in RGBA and the size of the
    screen: what BG1 draws. `barra` is the cursor's position in
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
    """What `menus.marcos` needs from the shop: each layer without a cursor,
    and with each cursor from its first cell row."""
    return [(ventanas_tienda(sys_img, capa),
             [(ventanas_tienda(sys_img, capa, k), fila)
              for k, (_, _, fila) in enumerate(barras_tienda(capa))])
            for capa in (TI_CAPA_PRINCIPAL, TI_CAPA_COMPRA, TI_CAPA_VENTA)]


def barra_de_tienda(modo, elegido, arriba, dos_renglones):
    """The bar's position in `barras_tienda` of the mode's layer, or None:
    the two "done"s have no cursor."""
    if modo == TI_PRINCIPAL:
        return elegido + (1 if dos_renglones else 0)
    if modo in (TI_COMPRAR, TI_VENDER):
        return elegido - arriba
    if modo in (TI_CUANTOS_COMPRA, TI_CUANTOS_VENTA):
        return TI_LISTA_FILAS_COMPRA
    return None


def tienda_compacta(mapas):
    """What the ROM stores of `marcos(capas_tienda(...))`, which is much
    less than what `marcos` returns.

    * **The three layers share the help rows**, which are uploaded once on
      opening: it is checked that they are equal.
    * **The rest of each layer, as runs of rows**, and a run already stored
      —from another layer, or earlier in the same one— is not stored again.
    * **Each bar, only where it changes**: the rectangle of cells that
      differs from its cursorless layer, and a rectangle equal to another is
      not repeated.

    Returns `(filas, arriba, capas, parches, barras)`: `filas` the stored
    tilemap rows, 32 words each, with the help's `arriba` ones first;
    `capas[c]` the runs of layer `c` from row `arriba`, as
    `(fila, origen, cuantas)` with `origen` the index in `filas`; `parches`
    the bars' words, one after another; and `barras[c][k]` the rectangle of
    bar `k` of layer `c` as `(fila, col, filas, cols, origen)`, with `origen`
    the index of its first word in `parches`.
    """
    COLS, FILAS_ = constantes.COLS, constantes.FILAS
    arriba = TI_MEDIO_Y // CELL

    def fila(mapa, n):
        return tuple(mapa[n * COLS:(n + 1) * COLS])

    fondos = [mapa for mapa, _ in mapas]
    if any(fila(f, n) != fila(fondos[0], n)
           for f in fondos for n in range(arriba)):
        raise SystemExit("the shop's layers do not share the help")
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


# The terms of a message set. In the LDB there are three sets, and the name of
# each term ends in which one it is: `shop_greeting1`, `shop_greeting2`.
# Until 2026-09-20 there was a chunk number here —thirteen in a row from
# 0x29—, which worked because the three sets come one after the other; now it
# is the name, which is what `db.terminos` has.
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
    """Which commands there are: `OpenShop` 0 buys and sells, 1 only buys, 2
    only sells. With a single one there is no main screen: it goes straight
    in."""
    return {0: ("comprar", "vender", "salir"), 1: ("comprar",),
            2: ("vender",)}[tipo]


def puede_comprar(db, numero, oro, inventario):
    """`Window_ShopBuy::CheckEnable`: that there is enough and that it does
    not have 99."""
    precio = db.items[numero].price
    return precio <= oro and inventario.get(numero, 0) < ITEM_MAX


def llevados(equipos, numero):
    """How many the party has equipped: `GetEquippedItemCount`."""
    return sum(1 for eq in equipos for i in eq if i == numero)


def lista_venta(items_rom, inventario):
    return [i for i in sorted(inventario)
            if inventario[i] > 0 and i in items_rom]


def pantalla_tienda(db, tipo, juego, vende, oro, inventario, equipos, modo,
                    elegido=0, arriba=0, cuantos=1, resaludo=False,
                    items_rom=None):
    """The shop in `modo`. `vende` are the items of `OpenShop`, `equipos`
    the equipment of each party member, `elegido` the cursor —of the main
    one or of the list—, `arriba` the first visible one of the list and
    `cuantos` the quantity being chosen."""
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
            # From the first line, like the ROM, which stores them split: set
            # 0 has them with a leading space —" Buy"— and splitting the
            # lines eats it.
            t.escribir(fila0 + 2 * n, TI_ORDEN_COL,
                       menus.partir_descripcion(term[orden])[0])
        barra = barra_de_tienda(modo, elegido, arriba, dos)
        t.ventanas = lambda sys_img: ventanas_tienda(sys_img, capa, barra)
        return t
    # The other messages are 26 letters at most: one line. The converter
    # checks it.
    t.escribir(TI_MSG_FILA, menus.ITEM_DESC_COL, renglones[0])
    comprando = modo in (TI_COMPRAR, TI_CUANTOS_COMPRA, TI_COMPRADO)
    lista = ([i for i in vende if i in items_rom] if comprando
             else lista_venta(items_rom, inventario))
    barra = barra_de_tienda(modo, elegido, arriba, False) if lista else None
    t.ventanas = lambda sys_img: ventanas_tienda(sys_img, capa, barra)
    if lista:
        descripcion(t, db.items[lista[elegido]].description)
    if capa == TI_CAPA_COMPRA:
        # The gold, and how many of the one the cursor marks the party owns
        # and has equipped.
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
        return t                # the middle window, empty: RM2k
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


# --- the battle ----------------------------------------------------------------
#
# `Scene_Battle_Rpg2k`, but **text-only and over a flat color**. taro asked for
# it that way on 2026-09-12, spelled out: *"we can ignore challenges related
# to the background image ... so we can focus on the mechanics of the
# turn-based battle"*. So there is no backdrop, no drawn battlers and no
# windows: the same 32 by 28 cell grid the equipment and shop screens use,
# over black —those, until their windows arrived—.
#
# What **is** RM2k's are the words —all from the LDB, none made up— and the
# math, which lives in `batalla.py`.
#
# One thing on this screen is not in RM2k and is a decision:
#
# * **escaping is an actor command** and not a party one. In RM2k "Escape" is
#   in the top menu, before choosing what each one does; putting it in each
#   actor's list saves a whole mode of the machine. Declared.
BA_ENEMIGO_FILA0 = 0
BA_GRUPO_FILA0 = 16
BA_MSG_FILA1 = 24
BA_MSG_FILA2 = 26
BA_CURSOR_COL = 0
BA_NOMBRE_COL = 2
BA_NOMBRE_ANCHO = 14
# **An enemy's HP is not shown**, as in RM2k: its line is just the name.
# With `[debug] enemy_hp` in the project file it comes back, in these same
# columns, for debugging.
BA_HP_COL = 18
BA_HP_NUM = 21                  # three digits
BA_BARRA_COL = 24
BA_HP_MAX_NUM = 25              # and the three of the maximum, in the party
# The five commands of ABL's battle menu, on the two message lines: three on
# top and two below. While choosing, the bottom one is free.
#
# Until 2026-09-13 they were three on one line —`Attack`, `Defend`, `Escape`—
# and taro asked for the original's menu, which also has `Use Item` and
# `Tech Skill`. The width is ten because that is the length of the longest
# command: `Tech Skill`, and `AgentTrain`, which is what Kersh's is called.
BA_ORDEN_ANCHO = 10
# **The order is the original's**: Attack, the skill, Defend, Use Item. In a
# capture of the real game, from 2026-09-12, Manta's menu says
# Attack / Slicing / Defend / Use Item. `Escape` is not there —escaping is a
# party command, from another menu— and here it goes fifth; it is the
# simplification `batalla.py` declares.
(BA_ORDEN_ATACAR, BA_ORDEN_HABILIDAD, BA_ORDEN_DEFENDER, BA_ORDEN_USAR,
 BA_ORDEN_HUIR) = range(5)
# Per command: which term names it, which line it goes on and in which column.
#
# **The skill's column has to leave ten free cells**: its text is the actor's
# `skill_name`, and `AgentTrain` and `Tech Skill` are exactly ten, leaving no
# room for the next one's cursor —which goes one cell before the text—. That
# is why the top line is 1 / 11 / 22 and not 1 / 11 / 21: the skill goes in
# the middle and Defend starts one cell further. ABL's other four words are
# eight or less.
BA_ORDENES = (
    ("atacar", 0, 1),
    ("habilidad", 0, 11),
    ("defender", 0, 22),
    ("usar", 1, 1),
    ("huir", 1, 13),
)

# No command is unimplemented since 2026-09-13: the skill was the only one and
# now it can be chosen. The tuple stays because the converter checks it and
# because it is where the next half-done one would go.
#
# What does get grayed out is the skill **of an actor that knows none**
# —Talan, who is level 1 and has not learned even the first— just like the
# pause menu with what leads nowhere.
BA_ORDEN_SIN_HACER = ()

# The skill list, which takes the same lines as the item list and for the same
# reason. It is the original's shape —see the capture
# `capturas-batalla/auto_20260912_123023.png`—: the description of the one the
# cursor marks at the very top, and below two columns with the name on the
# left and the SP cost on the right, with a dash in front.
#
# It reads **by rows**: in the capture, Manta's list sorted by number —130,
# 143, 144, 150— comes out as Mental Hack and MindShield on top and MindProbe
# and MindBlast below.
#
# The description goes on a single line and **is cut at thirty-one
# characters**: the original writes it whole with a smaller font, and here a
# line of text takes two tilemap rows, so the one below is not free. It is
# declared debt.
BA_HAB_DESC_FILA = 0
BA_HAB_DESC_COL = 1
BA_HAB_DESC_ANCHO = 31
BA_HAB_FILA0 = 2
BA_HAB_FILAS = 7
BA_HAB_COLUMNAS = 2
BA_HAB_COLUMNA_DX = 16          # from one column to the next
BA_HAB_NOMBRE_COL = 2           # relative to the start of the column
BA_HAB_NOMBRE_ANCHO = 11
BA_HAB_GUION_COL = 13
# The cost goes in **two digits and not three**, which is what lets the two
# columns fit in the 32 cells: the second starts at 16 and its number ends
# exactly at 31. With three it went past the screen. No `sp_cost` in ABL
# reaches 100 —the most expensive of the seven the party knows is 20— and the
# converter **stops if one ever did**, instead of drawing wrong.
BA_HAB_COSTO_COL = 14
BA_HAB_COSTO_CIFRAS = 2

# The item list takes the enemies' lines: while choosing what to use, the
# enemies are not needed and the party is, since it is who gets healed.
BA_ITEM_CUENTA_COL = 18

# The `ShowMessage` of a troop page. In RM2k the battle's message window
# **covers the party's**: it is the same 320x80 one as the map's, at the
# bottom, over the status and the commands. Here that is the party's four
# lines, which stop being drawn while the message is on screen; the two lines
# of the battle message are left empty below.
#
# The line is cut at **thirty-one characters**, which is what fits from
# column 1 of this screen's 32; the map window carries thirty-nine. Among
# Talan's systems messages there are lines of up to forty —two techniques in
# one, "     RainDrop...       GatheringWaves...", which already loses the
# last letter in the map window— and those lose their second technique here.
# It is declared debt.
BA_PAG_MSG_FILA0 = BA_GRUPO_FILA0
BA_PAG_MSG_COL = 1
BA_PAG_MSG_ANCHO = 31


# What the victory reports goes, as in RM2k, in the message window that covers
# the party: the same four lines of `BA_PAG_MSG_FILA0`, with its width. The
# first page is the victory term and the experience; each actor that leveled
# up has its own after that.
#
# ABL's victory term does not fit in one line —" The combat has resulted in
# victory!" is 36— so the converter splits it in two, at a space:
# `renglones_de_la_victoria`. The rest is built in the ROM with a number or a
# name in the middle, and what the converter enforces is that it fits.
BA_VIC_TERMINO_MAX = 2


def renglones_de_la_victoria(termino, ancho=BA_PAG_MSG_ANCHO):
    """The victory term split into lines of `ancho`, at the spaces. **The
    leading spaces stay**: RM2k writes them, and in this port's map window
    they show too."""
    sangria = termino[:len(termino) - len(termino.lstrip(" "))]
    renglones, actual = [], sangria
    for palabra in termino.split():
        vacio = not actual.strip()
        junto = actual + palabra if vacio else actual + " " + palabra
        if len(junto) <= ancho:
            actual = junto
            continue
        if vacio:
            raise SystemExit("the victory term has a word longer than the "
                             "line: %r" % palabra)
        renglones.append(actual)
        actual = palabra
    renglones.append(actual)
    return renglones


def renglon_de_experiencia(term, exp):
    """RM2k's `GetExperienceGainedMessage` without placeholders: the number
    stuck to the term. The `\\.` easyrpg adds is a wait, not a letter."""
    return "%d%s" % (exp, term["exp_recibida"])


def renglon_de_nivel(term, nombre, nivel):
    """RM2k's `GetLevelUpMessage` in English: "<name> <level> <n><level_up>",
    which in ABL is "Kersh LEVEL 21 achieved!"."""
    return "%s %s %d%s" % (nombre, term["nivel"], nivel, term["subio"])


def renglon_de_habilidad(term, habilidad):
    """`GetLearningMessage`: the name stuck to the term."""
    return habilidad + term["aprendio"]


def renglon_de_oro(term, oro):
    """RM2k's `GetGoldReceivedMessage` without placeholders:
    `gold_recieved_a`, a space, the number stuck to `gold` and
    `gold_recieved_b`. In ABL, " You found 285Cr credits!": the currency and
    "credits" both go, which is what RM2k builds with these terms."""
    return "%s %d%s%s" % (term["oro_a"], oro, term["moneda"], term["oro_b"])


def renglon_de_item(term, nombre):
    """RM2k's `GetItemReceivedMessage`: the name stuck to `item_recieved`,
    with no space in between —that one is RM2k3's—. The name is the one the
    ROM carries, cut to `ITEM_NOMBRE_ANCHO`."""
    from port import menus
    return menus.texto_de_item(nombre, menus.ITEM_NOMBRE_ANCHO) \
        + term["obtenido"]


def cobrar_la_victoria(term, exp_max, actores, habilidades, oro_max=0,
                       items=()):
    """Stops the build if any victory line does not fit in
    `BA_PAG_MSG_ANCHO`: the ROM builds them by joining pieces and does not
    split them, so a long one would spill onto the line below. Levels are
    measured with two digits, which is RM2k's cap."""
    renglones = ([renglon_de_experiencia(term, exp_max)]
                 + [renglon_de_oro(term, oro_max)]
                 + [renglon_de_item(term, n) for n in items]
                 + [renglon_de_nivel(term, n, 99) for n in actores]
                 + [renglon_de_habilidad(term, h) for h in habilidades])
    largos = [r for r in renglones if len(r) > BA_PAG_MSG_ANCHO]
    if largos:
        raise SystemExit("these victory lines do not fit in the window's %d "
                         "characters: %r"
                         % (BA_PAG_MSG_ANCHO, largos))


def texto_revivio(db):
    """What the battle writes after the name of a downed one an item revived:
    the `message_recovery` of state 1, the dead one, which is what
    `BattleMessage::GetStateRecoveryMessage` sticks to the name. In ABL it
    says " has revived!"."""
    from rpgmaker import lcf
    muerto = lcf.por_id(db.secciones["states"])[1]
    return lcf.campo(muerto, "message_recovery")


def texto_de_orden(termino):
    """One of the five commands as the screen writes it.

    The LDB terms carry leading spaces —ABL's `battle_escape` says
    " Escape"— and on the bottom line that would shift the text out of its
    column. It goes here and not in the ROM because the converter emits the
    text **already trimmed**: that way the ROM does not have to know how to
    trim.
    """
    return menus.texto_de_item(termino.strip(), BA_ORDEN_ANCHO)


def lcf_termino(db, nombre):
    from rpgmaker import lcf
    return lcf.to_string(db.terminos[nombre])

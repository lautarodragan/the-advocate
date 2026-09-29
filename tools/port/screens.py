"""The menu's text screens: equipment and shop.

They are pure text screens, so they carry no blocks drawn in advance like
the slots or the menu: they use the item screen's font —each character in
two cells, in white and in gray, see `menus.items_screen`— and are
composed **whole**. The ROM builds the complete tilemap, 32 by 28 cells, in
`texto_buf` and uploads it with one DMA per frame: it is 1792 bytes and fits
in vblank, so there is no need to be careful about what is written when.
Here `TextGrid` is the same: a grid of (character, gray) painted with the same
cells.

What each screen does —what gets equipped, what adds up, what gets bought—
also lives here, and the ROM copies it. The geometry is ours: RM2k has these
screens at 320x240 with windows and the font at 6 pixels; here they go at
256x224 and one letter per cell. It is cosmetic and it is declared. The
equipment and shop screens carry the System's windows on BG1, like the item
screen —see `equipment_windows` and `shop_windows`—.
"""

from port import constants
from port import menus
from port.constants import HEIGHT, WIDTH, CELL, EQUIPMENT_SLOTS
from port.events import CHOICE_CURSOR, ITEM_MAX
from port.rules import equipped_params

ROWS, COLS = 28, 32


class TextGrid:
    """The screen as a grid of cells, as the ROM builds it. `windows`, if
    set, is what BG1 draws under the text: see `equipment_windows`."""

    def __init__(self):
        self.cells = {}
        self.windows = None

    def write(self, row, col, text, gray=0):
        for n, c in enumerate(text):
            if col + n < COLS:
                self.cells[(row, col + n)] = (c, gray)

    def write_number(self, row, col, value, width, gray=0):
        """Right-aligned, with leading spaces."""
        self.write(row, col, ("%*d" % (width, value))[-width:], gray)

    def render(self, sys_img, font_id=None):
        from PIL import Image
        tiles, palettes, glyphs = menus.items_screen(sys_img, font_id)
        outside = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        if self.windows is not None:
            windows = self.windows(sys_img)
            outside.paste(windows, (0, 0), windows)
        paste = menus._painter(outside, tiles, palettes)
        for (row, col), (c, gray) in self.cells.items():
            paste(glyphs[gray][c], row, col, 1)
        return outside


def description(screen, text):
    """The top two lines, as on the item screen."""
    for n, line in enumerate(menus.split_description(text)):
        screen.write(menus.ITEM_DESC_Y // CELL + 2 * n,
                     menus.ITEM_DESC_COL, line)


# --- equipment -----------------------------------------------------------------
#
# `Scene_Equip`: the actor, its four parameters, the five slots with what it
# has equipped, and on choosing a slot the list of what can go there, with
# the parameters that would result. RM2k shows the slot and the list at the
# same time; here the list **replaces** the slots while choosing. At the end
# of the list there is an empty line, which is unequipping: it is RM2k's.
#
# The windows are the System's, on BG1 behind the text, as on the item screen
# —see `menus.ITEM_WINDOWS`—, and the cursor is its red bar. RM2k has four:
# the help on top, the actor with its parameters on the left and the slots on
# the right, and the list below in two columns. Here the actor and the slots
# do not fit side by side: with 8-pixel letters the parameters with the value
# that would result are fifteen cells and a slot with what it has is
# twenty-nine, and the screen has thirty-two. So they go **three, one below
# the other**: the help, same as the item screen's; the actor's, with the
# parameters in one column like RM2k and the name on the right; and the
# bottom one, which shows the slots or the list. The list goes in one column,
# for the same reason as the item screen's.
EQ_WEAPON, EQ_SHIELD = 0, 1
EQ_STATUS_Y = menus.ITEM_HELP_HEIGHT
EQ_BOTTOM_Y = 128                # four parameters of 16, and RM2k's spacing
EQ_WINDOWS = ((0, 0, WIDTH, menus.ITEM_HELP_HEIGHT),
              (0, EQ_STATUS_Y, WIDTH, EQ_BOTTOM_Y - EQ_STATUS_Y),
              (0, EQ_BOTTOM_Y, WIDTH, HEIGHT - EQ_BOTTOM_Y))
EQ_ACTOR_ROW = EQ_STATUS_Y // CELL + 1
EQ_ACTOR_COL = 19              # two cells of spacing, and twelve letters up to 30
EQ_PARAMS = tuple((EQ_ACTOR_ROW + 2 * n, 1) for n in range(4))
EQ_PARAM_VALUE = 9              # the value, three digits from here, with spacing
EQ_PARAM_ARROW = 12            # ">" and the new value, while choosing
EQ_SLOT_ROW0 = EQ_BOTTOM_Y // CELL + 1
# The three windows start their text in the same column, the parameters':
# the slot terms under the parameter terms, and the list names under them.
# taro asked for it on 2026-09-28, on seeing the slots shifted by one cell
# —column 2 came from making the tip of the bar match the item screen's, not
# from anything visible—.
EQ_TEXT_COL = EQ_PARAMS[0][1]
# The term and what is equipped go together, with no cell in between: that is
# how RM2k puts them —"Right HandModified Blaster-R"— and that is how the
# longest name fits before where the bar ends, which is where the item
# screen's ends.
EQ_SLOT_TERM_COL = EQ_TEXT_COL
EQ_SLOT_TERM_WIDTH = 10       # "Right Hand"
EQ_SLOT_NAME_COL = EQ_SLOT_TERM_COL + EQ_SLOT_TERM_WIDTH
EQ_SLOT_NAME_WIDTH = 19     # up to column 29, like the item count
EQ_LIST_ROW0 = EQ_SLOT_ROW0
EQ_LIST_ROWS = 5              # 17 + 5 * 2 = 27: the bottom frame
# The list, with the names in that column and not in the item screen's; the
# colon and the count, in the item screen's.
EQ_LIST_NAME_COL = EQ_TEXT_COL
# The bars, four pixels wider than the text on each side, as on the item
# screen: the slots' over the term and what is equipped, which is what RM2k
# marks, and the list's over the name and the count. With the text in the
# same column they are the same bar, and it ends where the item screen's
# does.
EQ_BAR_SLOT = (EQ_TEXT_COL * CELL - 4,
               (menus.ITEM_DIGITS_COL + 2 - EQ_TEXT_COL) * CELL
               + 8)
EQ_BAR_LIST = EQ_BAR_SLOT


def equipment_windows(sys_img, bar=None):
    """The equipment screen's windows, in RGBA and the size of the screen:
    what BG1 draws. `bar` is the cursor: the slot number, or
    `EQUIPMENT_SLOTS` plus the visible row of the list."""
    from PIL import Image
    from port import window as window_mod
    outside = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for x, y, width, height in EQ_WINDOWS:
        image = window_mod.window(sys_img, width, height)
        outside.paste(image, (x, y), image)
    if bar is not None:
        x, width = (EQ_BAR_SLOT if bar < EQUIPMENT_SLOTS
                    else EQ_BAR_LIST)
        image = window_mod.cursor(sys_img, width, 2 * CELL)
        outside.paste(image, (x, bar_row(bar) * CELL), image)
    return outside


def bar_row(bar):
    """The first cell row of cursor `bar` of `equipment_windows`."""
    if bar < EQUIPMENT_SLOTS:
        return EQ_SLOT_ROW0 + 2 * bar
    return EQ_LIST_ROW0 + 2 * (bar - EQUIPMENT_SLOTS)


def equipment_layers(sys_img):
    """What `menus.borders` needs from this screen: the windows without a
    cursor and with each cursor —the slots and then the list rows—, in the
    order the ROM indexes them: see `eq_barra`."""
    return (equipment_windows(sys_img),
            [(equipment_windows(sys_img, k), bar_row(k))
             for k in range(EQUIPMENT_SLOTS + EQ_LIST_ROWS)])


def new_value_color(now, then):
    """`Window_EquipStatus::GetNewParameterColor`: the value that would
    result goes in color 0 if it does not change, in 2 if it goes up and in
    3 if it goes down. In ABL's skin 2 is a peach and 3 the "cannot" gray;
    that is how the original shows it, captured with the 2015 RPG_RT on
    2026-09-28. Returns the font variant —`menus.ITEM_*`—, which is what the
    ROM compares in `eq_componer`."""
    if then == now:
        return menus.ITEM_WHITE
    return menus.ITEM_UP if then > now else menus.ITEM_GRAY


def slot_kind(slot):
    """The item type that goes in the slot: 1 weapon ... 5 accessory."""
    return slot + 1


def candidates(db, actor, slot, inventory, items_rom=None):
    """What the actor can put in the slot, in number order, and the 0 at the
    end which is unequipping. Only what the ROM knows."""
    return [i for i in sorted(inventory)
            if inventory[i] > 0 and (items_rom is None or i in items_rom)
            and db.items[i].type == slot_kind(slot)
            and db.items[i].equippable_by(actor)] + [0]


def equip(db, equipment, inventory, slot, item):
    """`Game_Actor::ChangeEquipment`: what it had goes back to the inventory
    and the new one comes out of there. A two-handed weapon removes the
    shield, and a shield removes the two-handed weapon. `item` at 0 is
    unequipping the slot."""
    def remove(r):
        if equipment[r]:
            inventory[equipment[r]] = inventory.get(equipment[r], 0) + 1
            equipment[r] = 0

    remove(slot)
    if item:
        inventory[item] -= 1
        equipment[slot] = item
        if slot == EQ_WEAPON and db.items[item].two_handed:
            remove(EQ_SHIELD)
        if slot == EQ_SHIELD and equipment[EQ_WEAPON] \
                and db.items[equipment[EQ_WEAPON]].two_handed:
            remove(EQ_WEAPON)


def equipment_screen(db, actor, equipment, inventory, slot, choosing=False,
                     chosen=0, top=0, items_rom=None):
    """The actor's equipment: with `choosing`, the slot's list with the
    cursor on `chosen` and the first visible one at `top`."""
    t = TextGrid()
    t.write(EQ_ACTOR_ROW, EQ_ACTOR_COL, db.actors[actor].name)
    choices = candidates(db, actor, slot, inventory, items_rom)
    bar = EQUIPMENT_SLOTS + chosen - top if choosing else slot
    t.windows = lambda sys_img: equipment_windows(sys_img, bar)
    now = equipped_params(db, actor, equipment)
    then = None
    if choosing:
        trial = list(equipment)
        inv = dict(inventory)
        equip(db, trial, inv, slot, choices[chosen])
        then = equipped_params(db, actor, trial)
        if choices[chosen]:
            description(t, db.items[choices[chosen]].description)
    elif equipment[slot]:
        description(t, db.items[equipment[slot]].description)
    for n, (row, col) in enumerate(EQ_PARAMS):
        t.write(row, col, db.term_params[n][:EQ_PARAM_VALUE - 1],
                menus.ITEM_RED)
        t.write_number(row, col + EQ_PARAM_VALUE, now[n], 3)
        if then is not None:
            t.write(row, col + EQ_PARAM_ARROW, ">", menus.ITEM_RED)
            t.write_number(row, col + EQ_PARAM_ARROW + 1, then[n], 3,
                           new_value_color(now[n], then[n]))
    if not choosing:
        for r in range(EQUIPMENT_SLOTS):
            row = EQ_SLOT_ROW0 + 2 * r
            t.write(row, EQ_SLOT_TERM_COL,
                    db.term_equipment[r][:EQ_SLOT_TERM_WIDTH],
                    menus.ITEM_RED)
            if equipment[r]:
                t.write(row, EQ_SLOT_NAME_COL, menus.item_text(
                    db.items[equipment[r]].name, EQ_SLOT_NAME_WIDTH))
        return t
    for f in range(EQ_LIST_ROWS):
        k = top + f
        if k >= len(choices):
            break
        row = EQ_LIST_ROW0 + 2 * f
        if choices[k]:
            t.write(row, EQ_LIST_NAME_COL, menus.item_text(
                db.items[choices[k]].name, menus.ITEM_NAME_WIDTH))
            t.write(row, menus.ITEM_COLON_COL,
                    ":%2d" % min(inventory[choices[k]], 99))
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
TI_MAIN, TI_BUY, TI_COUNT_BUY, TI_BOUGHT, TI_SELL, \
    TI_COUNT_SALE, TI_SOLD = range(7)
TI_SECOND = 60                 # frames the "done" lasts: DEFAULT_FPS
TI_LAYER_MAIN, TI_LAYER_BUY, TI_LAYER_SALE = range(3)
TI_LAYER_OF_MODE = (TI_LAYER_MAIN, TI_LAYER_BUY, TI_LAYER_BUY,
                    TI_LAYER_BUY, TI_LAYER_SALE, TI_LAYER_BUY,
                    TI_LAYER_BUY)
TI_MIDDLE_Y = menus.ITEM_HELP_HEIGHT             # 48
# The main one: the message at the bottom with two lines —the regreeting of
# sets 1 and 2 is 31 and 32 letters and a line fits 30— and the three
# commands. The commands go **right after the message**, as in RM2k: with a
# one-line greeting they start one line higher, and the window has room for
# the two-line case.
TI_MAIN_MSG_Y = 128
TI_MAIN_MSG_ROW = TI_MAIN_MSG_Y // CELL + 1     # 17
TI_COMMAND_COL = 3                # 16 pixels further in than the message: RM2k
TI_COMMAND_POSITIONS = 4         # the first, with a one-line greeting
# The buy one: the count and the gold under the list, side by side, and the
# one-line message.
TI_STATUS_Y = 144
TI_MSG_Y = 192
TI_GOLD_X = 152                  # "Equipped Items" and two digits, and the frame
TI_MSG_ROW = TI_MSG_Y // CELL + 1                          # 25
TI_OWNED_ROW = TI_STATUS_Y // CELL + 1                     # 19
TI_CARRIED_ROW = TI_OWNED_ROW + 2
TI_STATUS_COL = 1
TI_STATUS_NUM = TI_GOLD_X // CELL - 3     # two digits, up to the frame
TI_GOLD_ROW = TI_OWNED_ROW + 1                 # in the middle of its window
TI_GOLD_COL = 28                 # the gold's last digit; the currency after it
TI_LIST_ROW0 = TI_MIDDLE_Y // CELL + 1                     # 7
TI_LIST_COL = 1
TI_LIST_ROWS_BUY = 5       # 7 + 5 * 2 = 17: the bottom frame
TI_LIST_ROWS_SALE = 8        # 7 + 8 * 2 = 23
TI_PRICE_COL = 29              # the price's last digit
# The quantity: the item, "x" and the two digits, which carry the bar, and
# the total below, like RM2k, which puts them at a third of the window.
TI_COUNT_ROW = TI_LIST_ROW0 + 2                               # 9
TI_COUNT_X_COL = 24
TI_COUNT_COL = 26             # two digits
TI_TOTAL_ROW = TI_COUNT_ROW + 4
TI_WINDOWS = {
    TI_LAYER_MAIN: ((0, TI_MIDDLE_Y, WIDTH,
                     TI_MAIN_MSG_Y - TI_MIDDLE_Y),
                    (0, TI_MAIN_MSG_Y, WIDTH,
                     HEIGHT - TI_MAIN_MSG_Y)),
    TI_LAYER_BUY: ((0, TI_MIDDLE_Y, WIDTH, TI_STATUS_Y - TI_MIDDLE_Y),
                   (0, TI_STATUS_Y, TI_GOLD_X, TI_MSG_Y - TI_STATUS_Y),
                   (TI_GOLD_X, TI_STATUS_Y, WIDTH - TI_GOLD_X,
                    TI_MSG_Y - TI_STATUS_Y),
                   (0, TI_MSG_Y, WIDTH, HEIGHT - TI_MSG_Y)),
    TI_LAYER_SALE: ((0, TI_MIDDLE_Y, WIDTH, TI_MSG_Y - TI_MIDDLE_Y),
                    (0, TI_MSG_Y, WIDTH, HEIGHT - TI_MSG_Y)),
}
# The bars. The lists' are the equipment one —four pixels before the name and
# up to four after the price or the count—. The commands' starts where the
# message does and ends where the others do: in RM2k it crosses the window.
# The quantity's, over the two digits, with two pixels of spacing like the
# rest.
TI_BAR_LIST = (TI_LIST_COL * CELL - 4,
               (TI_PRICE_COL + 1 - TI_LIST_COL) * CELL + 8)
TI_BAR_COMMAND = (12, TI_BAR_LIST[0] + TI_BAR_LIST[1] - 12)
TI_BAR_COUNT = (TI_COUNT_COL * CELL - 4, 2 * CELL + 8)
# Where they go in VRAM. The tiles, with **their own BG1 base**: there is no
# room left in the font's —items and equipment reach exactly $3800—, and
# `$4000..$4C00` is always in the BG1 bank that `load_map` restores on
# closing; the actor choice uses the same, but it is never open at the same
# time. The tilemap, where the items' and equipment's is. `_controlar_tienda`
# checks it, in the converter.
TI_VRAM = 0x4000
TI_MAP = menus.ITEM_BORDER_MAP


def shop_bars(layer):
    """The layer's cursor positions, in the order the ROM counts them:
    `(x, ancho, fila)`, with `row` the first of the two cell rows it
    covers."""
    if layer == TI_LAYER_MAIN:
        return [TI_BAR_COMMAND + (TI_MAIN_MSG_ROW + 2 + 2 * n,)
                for n in range(TI_COMMAND_POSITIONS)]
    rows = (TI_LIST_ROWS_BUY if layer == TI_LAYER_BUY
            else TI_LIST_ROWS_SALE)
    bars = [TI_BAR_LIST + (TI_LIST_ROW0 + 2 * f,)
            for f in range(rows)]
    if layer == TI_LAYER_BUY:
        bars.append(TI_BAR_COUNT + (TI_COUNT_ROW,))
    return bars


def shop_windows(sys_img, layer, bar=None):
    """The shop's windows in layer `layer`, in RGBA and the size of the
    screen: what BG1 draws. `bar` is the cursor's position in
    `shop_bars(layer)`."""
    from PIL import Image
    from port import window as window_mod
    outside = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    for x, y, width, height in ((0, 0, WIDTH, TI_MIDDLE_Y),) \
            + TI_WINDOWS[layer]:
        image = window_mod.window(sys_img, width, height)
        outside.paste(image, (x, y), image)
    if bar is not None:
        x, width, row = shop_bars(layer)[bar]
        image = window_mod.cursor(sys_img, width, 2 * CELL)
        outside.paste(image, (x, row * CELL), image)
    return outside


def shop_layers(sys_img):
    """What `menus.borders` needs from the shop: each layer without a cursor,
    and with each cursor from its first cell row."""
    return [(shop_windows(sys_img, layer),
             [(shop_windows(sys_img, layer, k), row)
              for k, (_, _, row) in enumerate(shop_bars(layer))])
            for layer in (TI_LAYER_MAIN, TI_LAYER_BUY, TI_LAYER_SALE)]


def shop_bar(mode, chosen, top, two_lines):
    """The bar's position in `shop_bars` of the mode's layer, or None:
    the two "done"s have no cursor."""
    if mode == TI_MAIN:
        return chosen + (1 if two_lines else 0)
    if mode in (TI_BUY, TI_SELL):
        return chosen - top
    if mode in (TI_COUNT_BUY, TI_COUNT_SALE):
        return TI_LIST_ROWS_BUY
    return None


def compact_shop(tilemaps):
    """What the ROM stores of `marcos(shop_layers(...))`, which is much
    less than what `marcos` returns.

    * **The three layers share the help rows**, which are uploaded once on
      opening: it is checked that they are equal.
    * **The rest of each layer, as runs of rows**, and a run already stored
      —from another layer, or earlier in the same one— is not stored again.
    * **Each bar, only where it changes**: the rectangle of cells that
      differs from its cursorless layer, and a rectangle equal to another is
      not repeated.

    Returns `(filas, arriba, capas, parches, barras)`: `rows` the stored
    tilemap rows, 32 words each, with the help's `top` ones first;
    `capas[c]` the runs of layer `c` from row `top`, as
    `(fila, origen, cuantas)` with `source` the index in `rows`; `patches`
    the bars' words, one after another; and `barras[c][k]` the rectangle of
    bar `k` of layer `c` as `(fila, col, filas, cols, origen)`, with `source`
    the index of its first word in `patches`.
    """
    COLS, ROWS_ = constants.COLS, constants.ROWS
    top = TI_MIDDLE_Y // CELL

    def row(tilemap, n):
        return tuple(tilemap[n * COLS:(n + 1) * COLS])

    backdrops = [tilemap for tilemap, _ in tilemaps]
    if any(row(f, n) != row(backdrops[0], n)
           for f in backdrops for n in range(top)):
        raise SystemExit("the shop's layers do not share the help")
    rows = [row(backdrops[0], n) for n in range(top)]
    layers = []
    for tilemap in backdrops:
        stretches, n = [], top
        while n < ROWS_:
            length, source = 0, None
            for o in range(len(rows)):
                k = 0
                while (n + k < ROWS_ and o + k < len(rows)
                       and rows[o + k] == row(tilemap, n + k)):
                    k += 1
                if k > length:
                    length, source = k, o
            if not length:
                rows.append(row(tilemap, n))
                length, source = 1, len(rows) - 1
            if stretches and stretches[-1][0] + stretches[-1][2] == n \
                    and stretches[-1][1] + stretches[-1][2] == source:
                d, o, k = stretches.pop()
                stretches.append((d, o, k + length))
            else:
                stretches.append((n, source, length))
            n += length
        layers.append(stretches)
    patches, seen, bars = [], {}, []
    for layer, (tilemap, cursors) in enumerate(tilemaps):
        layer_pieces = []
        for (_, _, row0), cursor in zip(shop_bars(layer), cursors):
            distinct = [(f, c) for f in range(2) for c in range(COLS)
                        if cursor[f * COLS + c] != tilemap[(row0 + f) * COLS
                                                           + c]]
            f0 = min(f for f, _ in distinct)
            nf = max(f for f, _ in distinct) + 1 - f0
            c0 = min(c for _, c in distinct)
            nc = max(c for _, c in distinct) + 1 - c0
            piece = tuple(cursor[(f0 + f) * COLS + c0 + c]
                          for f in range(nf) for c in range(nc))
            if piece not in seen:
                seen[piece] = len(patches)
                patches.extend(piece)
            layer_pieces.append((row0 + f0, c0, nf, nc, seen[piece]))
        bars.append(layer_pieces)
    return rows, top, layers, patches, bars


# The terms of a message set. In the LDB there are three sets, and the name of
# each term ends in which one it is: `shop_greeting1`, `shop_greeting2`.
# Until 2026-09-20 there was a chunk number here —thirteen in a row from
# 0x29—, which worked because the three sets come one after the other; now it
# is the name, which is what `db.terms` has.
TI_TERMS = (
    ("saludo", "shop_greeting"), ("resaludo", "shop_regreeting"),
    ("comprar", "shop_buy"), ("vender", "shop_sell"),
    ("salir", "shop_leave"), ("que_compra", "shop_buy_select"),
    ("cuantos_compra", "shop_buy_number"), ("comprado", "shop_purchased"),
    ("que_vende", "shop_sell_select"),
    ("cuantos_vende", "shop_sell_number"), ("vendido", "shop_sold"),
)
TI_TERM_OWNED, TI_TERM_CARRIED = "possessed_items", "equipped_items"


def shop_terms(db, term_set):
    from rpgmaker import lcf
    return {n: lcf.to_string(db.terms["%s%d" % (t, term_set + 1)])
            for n, t in TI_TERMS}


def shop_commands(kind):
    """Which commands there are: `OpenShop` 0 buys and sells, 1 only buys, 2
    only sells. With a single one there is no main screen: it goes straight
    in."""
    return {0: ("comprar", "vender", "salir"), 1: ("comprar",),
            2: ("vender",)}[kind]


def can_buy(db, number, gold, inventory):
    """`Window_ShopBuy::CheckEnable`: that there is enough and that it does
    not have 99."""
    price = db.items[number].price
    return price <= gold and inventory.get(number, 0) < ITEM_MAX


def carried(party_equipment, number):
    """How many the party has equipped: `GetEquippedItemCount`."""
    return sum(1 for eq in party_equipment for i in eq if i == number)


def sale_list(items_rom, inventory):
    return [i for i in sorted(inventory)
            if inventory[i] > 0 and i in items_rom]


def shop_screen(db, kind, term_set, sells, gold, inventory, party_equipment, mode,
                chosen=0, top=0, count=1, regreeting=False,
                items_rom=None):
    """The shop in `mode`. `sells` are the items of `OpenShop`, `party_equipment`
    the equipment of each party member, `chosen` the cursor —of the main
    one or of the list—, `top` the first visible one of the list and
    `count` the quantity being chosen."""
    t = TextGrid()
    term = shop_terms(db, term_set)
    items_rom = set(items_rom if items_rom is not None else
                    list(sells) + list(inventory))
    message = {TI_MAIN: "resaludo" if regreeting else "saludo",
               TI_BUY: "que_compra", TI_COUNT_BUY: "cuantos_compra",
               TI_BOUGHT: "comprado", TI_SELL: "que_vende",
               TI_COUNT_SALE: "cuantos_vende", TI_SOLD: "vendido"}[mode]
    layer = TI_LAYER_OF_MODE[mode]
    lines = menus.split_description(term[message])
    red = menus.ITEM_RED
    if mode == TI_MAIN:
        for n, line in enumerate(lines):
            t.write(TI_MAIN_MSG_ROW + 2 * n, menus.ITEM_DESC_COL,
                    line)
        two = bool(lines[1])
        row0 = TI_MAIN_MSG_ROW + (4 if two else 2)
        for n, command in enumerate(shop_commands(kind)):
            # From the first line, like the ROM, which stores them split: set
            # 0 has them with a leading space —" Buy"— and splitting the
            # lines eats it.
            t.write(row0 + 2 * n, TI_COMMAND_COL,
                    menus.split_description(term[command])[0])
        bar = shop_bar(mode, chosen, top, two)
        t.windows = lambda sys_img: shop_windows(sys_img, layer, bar)
        return t
    # The other messages are 26 letters at most: one line. The converter
    # checks it.
    t.write(TI_MSG_ROW, menus.ITEM_DESC_COL, lines[0])
    buying = mode in (TI_BUY, TI_COUNT_BUY, TI_BOUGHT)
    choices = ([i for i in sells if i in items_rom] if buying
               else sale_list(items_rom, inventory))
    bar = shop_bar(mode, chosen, top, False) if choices else None
    t.windows = lambda sys_img: shop_windows(sys_img, layer, bar)
    if choices:
        description(t, db.items[choices[chosen]].description)
    if layer == TI_LAYER_BUY:
        # The gold, and how many of the one the cursor marks the party owns
        # and has equipped.
        digits = str(min(gold, 999999))
        t.write(TI_GOLD_ROW, TI_GOLD_COL + 1 - len(digits), digits)
        t.write(TI_GOLD_ROW, TI_GOLD_COL + 1, db.term_gold, red)
        if choices:
            number = choices[chosen]
            t.write(TI_OWNED_ROW, TI_STATUS_COL,
                    lcf_term(db, TI_TERM_OWNED), red)
            t.write_number(TI_OWNED_ROW, TI_STATUS_NUM,
                           inventory.get(number, 0), 2)
            t.write(TI_CARRIED_ROW, TI_STATUS_COL,
                    lcf_term(db, TI_TERM_CARRIED), red)
            t.write_number(TI_CARRIED_ROW, TI_STATUS_NUM, carried(party_equipment, number),
                           2)
    if mode in (TI_COUNT_BUY, TI_COUNT_SALE):
        number = choices[chosen]
        price = db.items[number].price
        if mode == TI_COUNT_SALE:
            price //= 2
        t.write(TI_COUNT_ROW, TI_LIST_COL, menus.item_text(
            db.items[number].name, menus.ITEM_NAME_WIDTH))
        t.write(TI_COUNT_ROW, TI_COUNT_X_COL, "x")
        t.write_number(TI_COUNT_ROW, TI_COUNT_COL, count, 2)
        total = str(price * count)
        t.write(TI_TOTAL_ROW, TI_GOLD_COL + 1 - len(total), total)
        t.write(TI_TOTAL_ROW, TI_GOLD_COL + 1, db.term_gold, red)
        return t
    if mode in (TI_BOUGHT, TI_SOLD):
        return t                # the middle window, empty: RM2k
    rows = TI_LIST_ROWS_BUY if buying else TI_LIST_ROWS_SALE
    for f in range(rows):
        k = top + f
        if k >= len(choices):
            break
        number = choices[k]
        item = db.items[number]
        row = TI_LIST_ROW0 + 2 * f
        if buying:
            gray = 0 if can_buy(db, number, gold, inventory) else 1
        else:
            gray = 0 if item.price > 0 else 1
        t.write(row, TI_LIST_COL, menus.item_text(
            item.name, menus.ITEM_NAME_WIDTH), gray)
        if buying:
            price = str(item.price)
            t.write(row, TI_PRICE_COL + 1 - len(price), price, gray)
        else:
            t.write(row, menus.ITEM_COLON_COL,
                    ":%2d" % min(inventory[number], 99), gray)
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
# math, which lives in `battle.py`.
#
# One thing on this screen is not in RM2k and is a decision:
#
# * **escaping is an actor command** and not a party one. In RM2k "Escape" is
#   in the top menu, before choosing what each one does; putting it in each
#   actor's list saves a whole mode of the machine. Declared.
BA_ENEMY_ROW0 = 0
BA_PARTY_ROW0 = 16
BA_MSG_ROW1 = 24
BA_MSG_ROW2 = 26
BA_CURSOR_COL = 0
BA_NAME_COL = 2
BA_NAME_WIDTH = 14
# **An enemy's HP is not shown**, as in RM2k: its line is just the name.
# With `[debug] enemy_hp` in the project file it comes back, in these same
# columns, for debugging.
BA_HP_COL = 18
BA_HP_NUM = 21                  # three digits
BA_BAR_COL = 24
BA_HP_MAX_NUM = 25              # and the three of the maximum, in the party
# The five commands of ABL's battle menu, on the two message lines: three on
# top and two below. While choosing, the bottom one is free.
#
# Until 2026-09-13 they were three on one line —`Attack`, `Defend`, `Escape`—
# and taro asked for the original's menu, which also has `Use Item` and
# `Tech Skill`. The width is ten because that is the length of the longest
# command: `Tech Skill`, and `AgentTrain`, which is what Kersh's is called.
BA_COMMAND_WIDTH = 10
# **The order is the original's**: Attack, the skill, Defend, Use Item. In a
# capture of the real game, from 2026-09-12, Manta's menu says
# Attack / Slicing / Defend / Use Item. `Escape` is not there —escaping is a
# party command, from another menu— and here it goes fifth; it is the
# simplification `battle.py` declares.
(BA_COMMAND_ATTACK, BA_COMMAND_SKILL, BA_COMMAND_DEFEND, BA_COMMAND_USE,
 BA_COMMAND_ESCAPE) = range(5)
# Per command: which term names it, which line it goes on and in which column.
#
# **The skill's column has to leave ten free cells**: its text is the actor's
# `skill_name`, and `AgentTrain` and `Tech Skill` are exactly ten, leaving no
# room for the next one's cursor —which goes one cell before the text—. That
# is why the top line is 1 / 11 / 22 and not 1 / 11 / 21: the skill goes in
# the middle and Defend starts one cell further. ABL's other four words are
# eight or less.
BA_COMMANDS = (
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
BA_COMMAND_UNDONE = ()

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
BA_SKILL_DESC_ROW = 0
BA_SKILL_DESC_COL = 1
BA_SKILL_DESC_WIDTH = 31
BA_SKILL_ROW0 = 2
BA_SKILL_ROWS = 7
BA_SKILL_COLUMNS = 2
BA_SKILL_COLUMN_DX = 16          # from one column to the next
BA_SKILL_NAME_COL = 2           # relative to the start of the column
BA_SKILL_NAME_WIDTH = 11
BA_SKILL_DASH_COL = 13
# The cost goes in **two digits and not three**, which is what lets the two
# columns fit in the 32 cells: the second starts at 16 and its number ends
# exactly at 31. With three it went past the screen. No `sp_cost` in ABL
# reaches 100 —the most expensive of the seven the party knows is 20— and the
# converter **stops if one ever did**, instead of drawing wrong.
BA_SKILL_COST_COL = 14
BA_SKILL_COST_DIGITS = 2

# The item list takes the enemies' lines: while choosing what to use, the
# enemies are not needed and the party is, since it is who gets healed.
BA_ITEM_COUNT_COL = 18

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
BA_PAGE_MSG_ROW0 = BA_PARTY_ROW0
BA_PAGE_MSG_COL = 1
BA_PAGE_MSG_WIDTH = 31


# What the victory reports goes, as in RM2k, in the message window that covers
# the party: the same four lines of `BA_PAGE_MSG_ROW0`, with its width. The
# first page is the victory term and the experience; each actor that leveled
# up has its own after that.
#
# ABL's victory term does not fit in one line —" The combat has resulted in
# victory!" is 36— so the converter splits it in two, at a space:
# `victory_lines`. The rest is built in the ROM with a number or a
# name in the middle, and what the converter enforces is that it fits.
BA_VICTORY_TERM_MAX = 2


def victory_lines(term, width=BA_PAGE_MSG_WIDTH):
    """The victory term split into lines of `width`, at the spaces. **The
    leading spaces stay**: RM2k writes them, and in this port's map window
    they show too."""
    indent = term[:len(term) - len(term.lstrip(" "))]
    lines, current = [], indent
    for word in term.split():
        empty = not current.strip()
        together = current + word if empty else current + " " + word
        if len(together) <= width:
            current = together
            continue
        if empty:
            raise SystemExit("the victory term has a word longer than the "
                             "line: %r" % word)
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def exp_line(term, exp):
    """RM2k's `GetExperienceGainedMessage` without placeholders: the number
    stuck to the term. The `\\.` easyrpg adds is a wait, not a letter."""
    return "%d%s" % (exp, term["exp_recibida"])


def level_line(term, name, level):
    """RM2k's `GetLevelUpMessage` in English: "<name> <level> <n><level_up>",
    which in ABL is "Kersh LEVEL 21 achieved!"."""
    return "%s %s %d%s" % (name, term["nivel"], level, term["subio"])


def skill_line(term, skill):
    """`GetLearningMessage`: the name stuck to the term."""
    return skill + term["aprendio"]


def gold_line(term, gold):
    """RM2k's `GetGoldReceivedMessage` without placeholders:
    `gold_recieved_a`, a space, the number stuck to `gold` and
    `gold_recieved_b`. In ABL, " You found 285Cr credits!": the currency and
    "credits" both go, which is what RM2k builds with these terms."""
    return "%s %d%s%s" % (term["oro_a"], gold, term["moneda"], term["oro_b"])


def item_line(term, name):
    """RM2k's `GetItemReceivedMessage`: the name stuck to `item_recieved`,
    with no space in between —that one is RM2k3's—. The name is the one the
    ROM carries, cut to `ITEM_NAME_WIDTH`."""
    from port import menus
    return menus.item_text(name, menus.ITEM_NAME_WIDTH) \
        + term["obtenido"]


def collect_victory(term, exp_max, actors, skills, gold_max=0,
                    items=()):
    """Stops the build if any victory line does not fit in
    `BA_PAGE_MSG_WIDTH`: the ROM builds them by joining pieces and does not
    split them, so a long one would spill onto the line below. Levels are
    measured with two digits, which is RM2k's cap."""
    lines = ([exp_line(term, exp_max)]
             + [gold_line(term, gold_max)]
             + [item_line(term, n) for n in items]
             + [level_line(term, n, 99) for n in actors]
             + [skill_line(term, h) for h in skills])
    lengths = [r for r in lines if len(r) > BA_PAGE_MSG_WIDTH]
    if lengths:
        raise SystemExit("these victory lines do not fit in the window's %d "
                         "characters: %r"
                         % (BA_PAGE_MSG_WIDTH, lengths))


def revived_text(db):
    """What the battle writes after the name of a downed one an item revived:
    the `message_recovery` of state 1, the dead one, which is what
    `BattleMessage::GetStateRecoveryMessage` sticks to the name. In ABL it
    says " has revived!"."""
    from rpgmaker import lcf
    dead = lcf.by_id(db.sections["states"])[1]
    return lcf.field(dead, "message_recovery")


def command_text(term):
    """One of the five commands as the screen writes it.

    The LDB terms carry leading spaces —ABL's `battle_escape` says
    " Escape"— and on the bottom line that would shift the text out of its
    column. It goes here and not in the ROM because the converter emits the
    text **already trimmed**: that way the ROM does not have to know how to
    trim.
    """
    return menus.item_text(term.strip(), BA_COMMAND_WIDTH)


def lcf_term(db, name):
    from rpgmaker import lcf
    return lcf.to_string(db.terms[name])

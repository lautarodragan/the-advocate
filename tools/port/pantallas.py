"""Las pantallas de texto del menú: el equipo y la tienda.

Son pantallas de puro texto, así que no llevan bloques dibujados de antemano
como las ranuras o el menú: usan la fuente de la pantalla de ítems —cada
carácter en dos celdas, en blanco y en gris, ver `titulo.pantalla_items`— y
se componen **enteras**. La ROM arma el tilemap completo, 32 por 28 celdas, en
`texto_buf` y lo sube de un DMA por cuadro: son 1792 bytes y entran en el
vblank, así que no hay que cuidar qué se escribe cuándo. Acá `Texto` es lo
mismo: una grilla de (carácter, gris) que se pinta con las mismas celdas.

Lo que hace cada pantalla —qué se equipa, qué suma, qué se compra— también
vive acá, y la ROM lo copia. La geometría es nuestra: RM2k tiene estas
pantallas en 320x240 con ventanas y la fuente a 6 pixeles; acá van en
256x224, sobre negro y a una letra por celda. Es cosmético y está declarado.
"""

from port import titulo
from port.eventos import ELEGIR_CURSOR, ITEM_MAX

FILAS, COLS = 28, 32


class Texto:
    """La pantalla como grilla de celdas, como la arma la ROM."""

    def __init__(self):
        self.celdas = {}

    def escribir(self, fila, col, texto, gris=0):
        for n, c in enumerate(texto):
            if col + n < COLS:
                self.celdas[(fila, col + n)] = (c, gris)

    def numero(self, fila, col, valor, ancho, gris=0):
        """Alineado a la derecha, con espacios adelante."""
        self.escribir(fila, col, ("%*d" % (ancho, valor))[-ancho:], gris)

    def render(self, sys_img, font_id=None):
        from PIL import Image
        tiles, paletas, glifos = titulo.pantalla_items(sys_img, font_id)
        fuera = Image.new("RGB", (titulo.ANCHO, titulo.ALTO), (0, 0, 0))
        pegar = titulo._pintor(fuera, tiles, paletas)
        for (fila, col), (c, gris) in self.celdas.items():
            pegar(glifos[gris][c], fila, col, 1)
        return fuera


def descripcion(pantalla, texto):
    """Los dos renglones de arriba, como en la pantalla de ítems."""
    for n, renglon in enumerate(titulo.partir_descripcion(texto)):
        pantalla.escribir(titulo.ITEM_DESC_Y // titulo.CELL + 2 * n,
                          titulo.ITEM_DESC_COL, renglon)


# --- el equipo -----------------------------------------------------------------
#
# `Scene_Equip`: el actor, sus cuatro parámetros, las cinco ranuras con lo que
# tiene puesto, y al elegir una ranura la lista de lo que puede ponerse ahí,
# con los parámetros que quedarían. RM2k muestra la ranura y la lista a la vez;
# acá la lista **reemplaza** a las ranuras mientras se elige. Al final de la
# lista hay una línea vacía, que es sacarse lo que tiene: es lo de RM2k.
RANURAS_EQUIPO = 5              # arma, escudo, armadura, casco, accesorio
EQ_ARMA, EQ_ESCUDO = 0, 1
EQ_ACTOR_FILA = 6
EQ_PARAMS = ((8, 1), (8, 17), (10, 1), (10, 17))
EQ_PARAM_VALOR = 8              # el valor, tres cifras desde acá
EQ_PARAM_FLECHA = 11            # ">" y el valor nuevo, en la elección
EQ_RANURA_FILA0 = 12
EQ_RANURA_TERM_COL = 3
EQ_RANURA_NOMBRE_COL = 14
EQ_RANURA_NOMBRE_ANCHO = 18
EQ_LISTA_FILA0 = 12
EQ_LISTA_FILAS = 8              # 12 + 8 * 2 = 28
EQ_CURSOR_COL = 1
PARAM_MAX = 999


def tipo_de_ranura(ranura):
    """El tipo de ítem que va en la ranura: 1 arma ... 5 accesorio."""
    return ranura + 1


def parametros(db, actor, equipo, nivel=None):
    """Ataque, defensa, espíritu y agilidad: los del nivel más lo que suma el
    equipo, topados en [1, 999] como `Game_Actor::GetAtk` y sus hermanas. Sin
    `nivel`, el de arranque."""
    base = [titulo.parametro_de(db.actors[actor], k, nivel)
            for k in ("attack", "defense", "spirit", "agility")]
    for item in equipo:
        if item:
            base = [b + p for b, p in zip(base, db.items[item].puntos)]
    return [max(1, min(PARAM_MAX, b)) for b in base]


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
    t.escribir(EQ_ACTOR_FILA, 1, db.actors[actor].name)
    lista = candidatos(db, actor, ranura, inventario, items_rom)
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
        t.escribir(fila, col, db.term_params[n][:EQ_PARAM_VALOR - 1])
        t.numero(fila, col + EQ_PARAM_VALOR, ahora[n], 3)
        if luego is not None:
            t.escribir(fila, col + EQ_PARAM_FLECHA, ">")
            t.numero(fila, col + EQ_PARAM_FLECHA + 1, luego[n], 3)
    if not eligiendo:
        for r in range(RANURAS_EQUIPO):
            fila = EQ_RANURA_FILA0 + 2 * r
            if r == ranura:
                t.escribir(fila, EQ_CURSOR_COL, ">")
            t.escribir(fila, EQ_RANURA_TERM_COL,
                       db.term_equipo[r][:EQ_RANURA_NOMBRE_COL
                                         - EQ_RANURA_TERM_COL - 1])
            if equipo[r]:
                t.escribir(fila, EQ_RANURA_NOMBRE_COL, titulo.texto_de_item(
                    db.items[equipo[r]].name, EQ_RANURA_NOMBRE_ANCHO))
        return t
    for f in range(EQ_LISTA_FILAS):
        k = arriba + f
        if k >= len(lista):
            break
        fila = EQ_LISTA_FILA0 + 2 * f
        if k == elegido:
            t.escribir(fila, EQ_CURSOR_COL, ">")
        if lista[k]:
            t.escribir(fila, titulo.ITEM_NOMBRE_COL, titulo.texto_de_item(
                db.items[lista[k]].name, titulo.ITEM_NOMBRE_ANCHO))
            t.escribir(fila, titulo.ITEM_DOS_PUNTOS_COL,
                       ":%2d" % min(inventario[lista[k]], 99))
    return t


# --- la tienda ----------------------------------------------------------------
#
# `Scene_Shop`. Arriba el mensaje del tendero, del juego de términos que pide
# `OpenShop`; en la principal, las órdenes. Comprar muestra lo que vende con su
# precio —en gris lo que no alcanza el oro o ya se tiene 99— y el oro, cuántos
# se tienen y cuántos lleva puestos el grupo; vender, el inventario a mitad de
# precio —en gris lo que vale 0—. Elegido uno, la cantidad: derecha e
# izquierda de a uno, arriba y abajo de a diez, entre 1 y lo que se puede.
# Después de cada compra o venta el mensaje dice "listo" un segundo.
TI_PRINCIPAL, TI_COMPRAR, TI_CUANTOS_COMPRA, TI_COMPRADO, TI_VENDER, \
    TI_CUANTOS_VENTA, TI_VENDIDO = range(7)
TI_SEGUNDO = 60                 # cuadros que dura el "listo": DEFAULT_FPS
TI_ORDEN_FILA0 = 6
TI_ORO_FILA = 6
TI_ORO_COL = 28                 # la última cifra del oro
TI_TENGO_FILA = 8
TI_LLEVO_FILA = 10
TI_ESTADO_COL = 14
TI_ESTADO_NUM = 29              # dos cifras
TI_LISTA_FILA0 = 12
TI_LISTA_FILAS = 8
TI_PRECIO_COL = 29              # la última cifra del precio
TI_CUANTOS_COL = 25             # "x" y dos cifras
TI_TOTAL_FILA = 14
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
    de la lista— y `cuantos` la cantidad que se está eligiendo."""
    t = Texto()
    term = terminos_tienda(db, juego)
    items_rom = set(items_rom if items_rom is not None else
                    list(vende) + list(inventario))
    mensaje = {TI_PRINCIPAL: "resaludo" if resaludo else "saludo",
               TI_COMPRAR: "que_compra", TI_CUANTOS_COMPRA: "cuantos_compra",
               TI_COMPRADO: "comprado", TI_VENDER: "que_vende",
               TI_CUANTOS_VENTA: "cuantos_vende", TI_VENDIDO: "vendido"}[modo]
    descripcion(t, term[mensaje])
    if modo == TI_PRINCIPAL:
        for n, orden in enumerate(ordenes_tienda(tipo)):
            fila = TI_ORDEN_FILA0 + 2 * n
            if n == elegido:
                t.escribir(fila, EQ_CURSOR_COL, ">")
            # Del primer renglón, como la ROM, que los guarda partidos: el
            # juego 0 los trae con un espacio adelante —" Buy"— y partir los
            # renglones lo come.
            t.escribir(fila, titulo.ITEM_NOMBRE_COL,
                       titulo.partir_descripcion(term[orden])[0])
        return t
    comprando = modo in (TI_COMPRAR, TI_CUANTOS_COMPRA, TI_COMPRADO)
    lista = ([i for i in vende if i in items_rom] if comprando
             else lista_venta(items_rom, inventario))
    if modo != TI_VENDER:
        # El oro, y cuántos tiene y lleva puestos del que marca el cursor.
        cifras = str(min(oro, 999999))
        t.escribir(TI_ORO_FILA, TI_ORO_COL + 1 - len(cifras), cifras)
        t.escribir(TI_ORO_FILA, TI_ORO_COL + 1, db.term_gold, 0)
        if lista:
            numero = lista[elegido]
            t.escribir(TI_TENGO_FILA, TI_ESTADO_COL,
                       lcf_termino(db, TI_TERMINO_TENGO))
            t.numero(TI_TENGO_FILA, TI_ESTADO_NUM,
                     inventario.get(numero, 0), 2)
            t.escribir(TI_LLEVO_FILA, TI_ESTADO_COL,
                       lcf_termino(db, TI_TERMINO_LLEVO))
            t.numero(TI_LLEVO_FILA, TI_ESTADO_NUM, llevados(equipos, numero),
                     2)
    if modo in (TI_CUANTOS_COMPRA, TI_CUANTOS_VENTA):
        numero = lista[elegido]
        precio = db.items[numero].price
        if modo == TI_CUANTOS_VENTA:
            precio //= 2
        fila = TI_LISTA_FILA0
        t.escribir(fila, titulo.ITEM_NOMBRE_COL, titulo.texto_de_item(
            db.items[numero].name, titulo.ITEM_NOMBRE_ANCHO))
        t.escribir(fila, TI_CUANTOS_COL, "x")
        t.numero(fila, TI_CUANTOS_COL + 1, cuantos, 2)
        total = str(precio * cuantos)
        t.escribir(TI_TOTAL_FILA, TI_ORO_COL + 1 - len(total), total)
        t.escribir(TI_TOTAL_FILA, TI_ORO_COL + 1, db.term_gold)
        return t
    for f in range(TI_LISTA_FILAS):
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
        if k == elegido and modo in (TI_COMPRAR, TI_VENDER):
            t.escribir(fila, EQ_CURSOR_COL, ">")
        t.escribir(fila, titulo.ITEM_NOMBRE_COL, titulo.texto_de_item(
            item.name, titulo.ITEM_NOMBRE_ANCHO), gris)
        if comprando:
            precio = str(item.price)
            t.escribir(fila, TI_PRECIO_COL + 1 - len(precio), precio, gris)
        else:
            t.escribir(fila, titulo.ITEM_DOS_PUNTOS_COL,
                       ":%2d" % min(inventario[numero], 99), gris)
    return t


# --- la batalla ----------------------------------------------------------------
#
# `Scene_Battle_Rpg2k`, pero **de texto y sobre un color plano**. taro lo pidió
# así el 2026-09-12, con todas las letras: *"podemos ignorar desafíos
# relacionados con la imagen de fondo ... así nos podemos enfocar en la
# mecánica de la batalla por turnos"*. Así que no hay fondo, no hay battlers
# dibujados y no hay ventanas: la misma grilla de 32 por 28 celdas que usan el
# equipo y la tienda, sobre negro.
#
# Lo que **sí** es de RM2k son las palabras —todas del LDB, ninguna inventada—
# y las cuentas, que viven en `batalla.py`.
#
# Dos cosas de esta pantalla no están en RM2k y son decisiones:
#
# * **se ven los HP de los enemigos.** RM2k no los muestra. Acá sí, porque lo
#   que esta vuelta tiene que dejar ver es justamente la mecánica: sin eso, un
#   golpe que pega y uno que falla se ven igual.
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
# **El orden es el del original**: Attack, la habilidad, Defend, Use Item. Se
# ve en la captura `pruebas-manuales/capturas-batalla/auto_20260912_123013.png`,
# donde el menú de Manta dice Attack / Slicing / Defend / Use Item. `Escape` no
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

# Los términos del LDB que la pantalla usa, en el orden en que el conversor los
# emite. Los nombres son los de liblcf —`fields.csv`, struct `Terms`— y no de
# memoria: ver data/README.md. Hasta el 2026-09-20 eran los números de chunk
# de `ldb/chunks.h`, con el nombre al lado en un comentario; hoy el nombre es
# el dato y el comentario es lo que dice el término en el juego.
BA_TERMINOS = (
    ("atacar", "command_attack"),        # "Attack"
    ("defender", "command_defend"),      # "Defend"
    ("huir", "battle_escape"),           # "Escape"
    ("hp", "hp_short"),                  # "HP"
    ("ataca", "attacking"),              # " attacks the enemy"
    ("defiende", "defending"),
    ("critico", "actor_critical"),
    ("dano_enemigo", "enemy_damaged"),   # " health lost."
    ("sin_dano_enemigo", "enemy_undamaged"),
    ("dano_actor", "actor_damaged"),
    ("sin_dano_actor", "actor_undamaged"),
    ("victoria", "victory"),
    ("derrota", "defeat"),
    ("huyo", "escape_success"),
    ("no_huyo", "escape_failure"),
    # Los cuatro del 2026-09-13: las dos órdenes que faltaban y los dos
    # renglones del mensaje de usar un ítem.
    ("usar", "command_item"),            # "Use Item"
    ("habilidad", "command_skill"),      # "Tech Skill"
    ("uso", "use_item"),                 # " used."
    ("recupero", "hp_recovery"),         # " Recovered"
)


def terminos_batalla(db):
    from rpgmaker import lcf
    return {n: lcf.to_string(db.terminos[t]) for n, t in BA_TERMINOS}


def texto_de_orden(termino):
    """Una de las cinco órdenes como la escribe la pantalla.

    Los términos del LDB traen espacios adelante —`battle_escape` del ABL dice
    " Escape"— y en el renglón de abajo eso correría el texto de su columna.
    Va acá y no en la ROM porque el conversor emite el texto **ya recortado**:
    así los dos lados escriben los mismos bytes sin que la ROM tenga que saber
    recortar.
    """
    return titulo.texto_de_item(termino.strip(), BA_ORDEN_ANCHO)


def lcf_termino(db, nombre):
    from rpgmaker import lcf
    return lcf.to_string(db.terminos[nombre])

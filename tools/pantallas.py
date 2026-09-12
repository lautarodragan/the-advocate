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

import titulo
from eventos import ELEGIR_CURSOR, ITEM_MAX

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

    def render(self, sys_img, font_id=None, fondo=None):
        from PIL import Image
        tiles, paletas, glifos = titulo.pantalla_items(sys_img, font_id)
        fuera = Image.new("RGB", (titulo.ANCHO, titulo.ALTO), (0, 0, 0))
        if fondo is not None:
            # La escena de la pelea, arriba de todo y **debajo del texto**: es
            # BG1 y el texto es BG2 con el bit de prioridad puesto. Ver
            # `escena_prender` en main.s.
            fuera.paste(fondo, (0, 0))
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


def parametros(db, actor, equipo):
    """Ataque, defensa, espíritu y agilidad: los del nivel más lo que suma el
    equipo, topados en [1, 999] como `Game_Actor::GetAtk` y sus hermanas."""
    base = [titulo.parametro_de(db.actors[actor], k)
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
# Los términos de un juego de mensajes: son trece seguidos desde 0x29.
TI_TERMINOS = ("saludo", "resaludo", "comprar", "vender", "salir",
               "que_compra", "cuantos_compra", "comprado", "que_vende",
               "cuantos_vende", "vendido")
TI_TERMINO_TENGO, TI_TERMINO_LLEVO = 0x5C, 0x5D


def terminos_tienda(db, juego):
    import lcf
    base = 0x29 + 13 * juego
    return {n: lcf.to_string(db.terminos.get(base + k, b""))
            for k, n in enumerate(TI_TERMINOS)}


def ordenes_tienda(tipo):
    """Qué órdenes hay: `OpenShop` 0 compra y vende, 1 sólo compra, 2 sólo
    vende. Con una sola no hay pantalla principal: se entra derecho."""
    return {0: ("comprar", "vender", "salir"), 1: ("comprar",),
            2: ("vender",)}[tipo]


def puede_comprar(db, numero, oro, inventario):
    """`Window_ShopBuy::CheckEnable`: que alcance y que no tenga 99."""
    precio = db.items[numero].price
    return precio <= oro and inventario.get(numero, 0) < ITEM_MAX


def maximo_compra(db, numero, oro, inventario):
    precio = db.items[numero].price
    tope = ITEM_MAX - inventario.get(numero, 0)
    return min(tope, oro // precio) if precio else tope


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
BA_ENEMIGOS_FILAS = 8           # `batalla.ENEMIGOS_MAX`
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
# El ancho pasó de nueve a diez porque `Tech Skill` mide diez justos, y tres
# columnas de diez en 1, 11 y 21 terminan en la celda 30 de las 32.
BA_ORDEN_ANCHO = 10
(BA_ORDEN_ATACAR, BA_ORDEN_DEFENDER, BA_ORDEN_USAR, BA_ORDEN_HABILIDAD,
 BA_ORDEN_HUIR) = range(5)
# Por orden: qué término la nombra, en qué renglón va y en qué columna.
#
# Las columnas del segundo renglón **no son las del primero**: `Tech Skill`
# mide diez justos y llena su ancho sin dejarle lugar al cursor del que sigue,
# que va una celda antes del texto. Arriba eso no pasa porque las tres palabras
# son más cortas que el ancho y el relleno son espacios.
BA_ORDENES = (
    ("atacar", 0, 1),
    ("defender", 0, 11),
    ("usar", 0, 21),
    ("habilidad", 1, 1),
    ("huir", 1, 13),
)

# **`Tech Skill` va siempre en gris y A no hace nada con ella**, que es lo que
# el menú de pausa ya hace con las tres órdenes que no están.
#
# **Y el motivo que decía acá era falso.** Decía que a este nivel nadie sabe
# ninguna habilidad, y salía de leer los parámetros con un nivel 1 mockeado.
# Desde que el nivel sale del `initial_level` del LDB —Kersh 20, Core y Manta
# 15— los tres saben las suyas desde la primera pelea. Lo que falta es el
# trabajo, medido y en orden en ESTADO.md.
#
# Cuando eso entre, esta orden deja de estar en gris **y deja de llamarse
# "Tech Skill"**: el original la nombra con el `skill_name` de cada actor
# —"AgentTrain", "Telepathy", "Slicing"— y va segunda, antes de Defend.
BA_ORDEN_SIN_HACER = (BA_ORDEN_HABILIDAD,)

# Los modos de la pantalla, que la ROM lleva en `ba_modo`. **El orden importa**:
# la ROM pregunta `cmp #BA_M_MENSAJE / bcs` para decir "mensaje o fin", así que
# los que eligen algo van todos antes.
(BA_ELIGE_ORDEN, BA_ELIGE_BLANCO, BA_ELIGE_ITEM, BA_ELIGE_ACTOR,
 BA_MENSAJE, BA_FIN) = range(6)

# La lista de ítems ocupa los renglones de los enemigos: mientras se elige qué
# usar, los enemigos no hacen falta y el grupo sí, que es a quién se cura.
BA_ITEM_FILAS = BA_ENEMIGOS_FILAS
BA_ITEM_CUENTA_COL = 18

# Los términos del LDB que la pantalla usa, en el orden en que el conversor los
# emite. Los códigos salen de `ldb/chunks.h` de liblcf —ChunkTerms— y no de
# memoria: ver data/README.md.
BA_TERMINOS = (
    ("atacar", 0x68),           # command_attack: "Attack"
    ("defender", 0x69),         # command_defend: "Defend"
    ("huir", 0x67),             # battle_escape: "Escape"
    ("hp", 0x81),               # hp_short: "HP"
    ("ataca", 0x0B),            # attacking: " attacks the enemy"
    ("defiende", 0x0E),         # defending
    ("critico", 0x0D),          # actor_critical
    ("dano_enemigo", 0x14),     # enemy_damaged: " health lost."
    ("sin_dano_enemigo", 0x15),  # enemy_undamaged
    ("dano_actor", 0x16),       # actor_damaged
    ("sin_dano_actor", 0x17),   # actor_undamaged
    ("victoria", 0x05),         # victory
    ("derrota", 0x06),          # defeat
    ("huyo", 0x03),             # escape_success
    ("no_huyo", 0x04),          # escape_failure
    # Los cuatro del 2026-09-13: las dos órdenes que faltaban y los dos
    # renglones del mensaje de usar un ítem.
    ("usar", 0x6A),             # command_item: "Use Item"
    ("habilidad", 0x6B),        # command_skill: "Tech Skill"
    ("uso", 0x1C),              # use_item: " used."
    ("recupero", 0x1D),         # hp_recovery: " Recovered"
)


def terminos_batalla(db):
    import lcf
    return {n: lcf.to_string(db.terminos.get(c, b"")) for n, c in BA_TERMINOS}


def texto_de_orden(termino):
    """Una de las cinco órdenes como la escribe la pantalla.

    Los términos del LDB traen espacios adelante —`battle_escape` del ABL dice
    " Escape"— y en el renglón de abajo eso correría el texto de su columna.
    Va acá y no en la ROM porque el conversor emite el texto **ya recortado**:
    así los dos lados escriben los mismos bytes sin que la ROM tenga que saber
    recortar.
    """
    return titulo.texto_de_item(termino.strip(), BA_ORDEN_ANCHO)


def pantalla_batalla(db, combate, modo=BA_ELIGE_ORDEN, actor=0, orden=0,
                     blanco=0, mensaje=("", ""), items=(), item=0, arriba=0):
    """La pantalla como la compone la ROM.

    `combate` es una `batalla.Batalla`. `modo` dice qué se está eligiendo:
    `BA_ELIGE_ORDEN` pone el cursor en la orden de `orden` y marca al actor
    `actor`; `BA_ELIGE_BLANCO` lo pone en el enemigo `blanco`; `BA_ELIGE_ITEM`
    reemplaza la lista de enemigos por la de ítems y pone el cursor en `item`,
    con `arriba` como el primero que se ve; `BA_ELIGE_ACTOR` deja la lista de
    ítems y pone el cursor en el actor `blanco`; `BA_MENSAJE` y `BA_FIN`
    muestran los dos renglones de `mensaje`.

    `items` es la lista de ítems usables, como `(numero, cuantos)`.

    Un enemigo muerto **se sigue mostrando**, en gris y con los HP en cero, que
    es lo que hace la ROM: sacarlo de la lista movería a los de abajo en mitad
    de un turno.
    """
    t = Texto()
    eligiendo_item = modo in (BA_ELIGE_ITEM, BA_ELIGE_ACTOR)
    if eligiendo_item:
        # La lista de ítems, donde iban los enemigos: mientras se elige qué
        # usar lo que hace falta ver es el grupo, que es a quién se cura.
        lista = list(items)
        for f in range(BA_ITEM_FILAS):
            k = arriba + f
            if k >= len(lista):
                break
            numero, cuantos = lista[k]
            fila = BA_ENEMIGO_FILA0 + 2 * f
            gris = 0 if modo == BA_ELIGE_ITEM else 1
            if modo == BA_ELIGE_ITEM and k == item:
                t.escribir(fila, BA_CURSOR_COL, ELEGIR_CURSOR)
            t.escribir(fila, BA_NOMBRE_COL, titulo.texto_de_item(
                db.items[numero].name, BA_NOMBRE_ANCHO), gris)
            t.escribir(fila, BA_ITEM_CUENTA_COL,
                       ":%2d" % min(cuantos, 99), gris)
    else:
        for n, enemigo in enumerate(combate.enemigos[:BA_ENEMIGOS_FILAS]):
            fila = BA_ENEMIGO_FILA0 + 2 * n
            gris = 0 if enemigo.vivo else 1
            if modo == BA_ELIGE_BLANCO and n == blanco:
                t.escribir(fila, BA_CURSOR_COL, ELEGIR_CURSOR)
            t.escribir(fila, BA_NOMBRE_COL, titulo.texto_de_item(
                enemigo.nombre, BA_NOMBRE_ANCHO), gris)
            t.escribir(fila, BA_HP_COL, db.term_hp_short, gris)
            t.numero(fila, BA_HP_NUM, min(enemigo.hp, 999), 3, gris)
    for n, quien in enumerate(combate.actores[:4]):
        fila = BA_GRUPO_FILA0 + 2 * n
        gris = 0 if quien.vivo else 1
        marcado = blanco if modo == BA_ELIGE_ACTOR else actor
        if modo in (BA_ELIGE_ORDEN, BA_ELIGE_BLANCO,
                    BA_ELIGE_ITEM, BA_ELIGE_ACTOR) and n == marcado:
            t.escribir(fila, BA_CURSOR_COL, ELEGIR_CURSOR)
        t.escribir(fila, BA_NOMBRE_COL, titulo.texto_de_item(
            quien.nombre, BA_NOMBRE_ANCHO), gris)
        t.escribir(fila, BA_HP_COL, db.term_hp_short, gris)
        t.numero(fila, BA_HP_NUM, min(quien.hp, 999), 3, gris)
        t.escribir(fila, BA_BARRA_COL, "/", gris)
        t.numero(fila, BA_HP_MAX_NUM, min(quien.hp_max, 999), 3, gris)
    if modo < BA_MENSAJE:
        term = terminos_batalla(db)
        for n, (nombre, renglon, col) in enumerate(BA_ORDENES):
            fila = (BA_MSG_FILA1, BA_MSG_FILA2)[renglon]
            # En blanco sólo la que se puede elegir ahora, y nunca la que no
            # está hecha: es lo mismo que hace el menú de pausa.
            gris = 0 if (modo == BA_ELIGE_ORDEN
                         and n not in BA_ORDEN_SIN_HACER) else 1
            if modo == BA_ELIGE_ORDEN and n == orden:
                t.escribir(fila, col - 1, ELEGIR_CURSOR)
            t.escribir(fila, col, texto_de_orden(term[nombre]), gris)
    else:
        escribir_corrido(t, BA_MSG_FILA1, 1, mensaje[0])
        escribir_corrido(t, BA_MSG_FILA2, 1, mensaje[1])
    return t


def escribir_corrido(pantalla, fila, col, texto):
    """Un texto que **sigue en el renglón de abajo** cuando no entra.

    No es una decisión de diseño: es lo que hace `pant_glifo` en la ROM, que
    avanza dos bytes por carácter dentro de un búfer de 32 celdas de ancho y
    al pasarse cae en la fila siguiente. La referencia lo copia en vez de
    cortar el texto porque los dos lados tienen que dibujar lo mismo, y el
    mensaje de escapar del ABL —"You extricate yourself from the fray!"— mide
    36 caracteres y se pasa.

    El corte no queda en un espacio, como no queda en la ROM.

    **Lo que esto modela no lo compara nada**, y conviene decirlo: la tanda
    sólo mira la pantalla con el menú de órdenes, no con un mensaje puesto.
    Medido contra una captura de la consola del mensaje de escapar —el más
    largo, el único que se pasa de renglón— quedan 66 pixeles de diferencia en
    la fila donde los dos textos se enciman. Es deuda declarada y no un camino
    a medias: el día que un caso compare un mensaje, hay que cerrarla.
    """
    for c in titulo.texto_de_item(texto, 255):
        if col >= COLS:
            # **Una fila y no dos**: la ROM avanza 64 bytes, que es una fila
            # del tilemap, no un renglón de texto. El carácter que sigue queda
            # medio renglón más abajo, encimado con la mitad de abajo del
            # anterior. Se ve raro y es lo que hace la ROM; corregirlo sería
            # corregir los dos lados.
            fila, col = fila + 1, 0
        if fila >= FILAS:
            return
        pantalla.escribir(fila, col, c)
        col += 1


def lcf_termino(db, chunk):
    import lcf
    return lcf.to_string(db.terminos.get(chunk, b""))


def main():
    import argparse
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from render_map import GAME_DIR
    import lcf
    import ventana

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--equipo", type=int, metavar="ACTOR",
                        help="la pantalla de equipo de este actor")
    parser.add_argument("--puesto", default=None, metavar="I,I,I,I,I",
                        help="lo que tiene puesto; sin esto, el inicial")
    parser.add_argument("--items", default="", metavar="ITEM:CUANTOS,...")
    parser.add_argument("--ranura", type=int, default=0)
    parser.add_argument("--eligiendo", action="store_true")
    parser.add_argument("--elegido", type=int, default=0)
    parser.add_argument("--arriba", type=int, default=0)
    parser.add_argument("--tienda", default=None, metavar="TIPO:JUEGO:I,I,...",
                        help="la tienda de `OpenShop` con estos ítems")
    parser.add_argument("--modo", type=int, default=0)
    parser.add_argument("--oro", type=int, default=0)
    parser.add_argument("--cuantos", type=int, default=1)
    parser.add_argument("--resaludo", action="store_true")
    parser.add_argument("--grupo", default="", metavar="ACTOR,...",
                        help="el grupo, para contar lo que lleva puesto")
    parser.add_argument("--batalla", type=int, default=None, metavar="TROPA",
                        help="la pantalla de batalla contra esta tropa")
    parser.add_argument("--turnos", type=int, default=0,
                        help="cuántos turnos jugar antes de dibujar, todos "
                             "atacando al primero que quede vivo")
    parser.add_argument("--item", type=int, default=0,
                        help="qué ítem de la lista marca el cursor")
    parser.add_argument("--fondo", default="", metavar="NOMBRE",
                        help="el fondo de batalla, con los battlers de la "
                             "tropa horneados encima: ver tools/escena.py")
    parser.add_argument("--blanco", type=int, default=0)
    parser.add_argument("--actor", type=int, default=0)
    parser.add_argument("--orden", type=int, default=0)
    args = parser.parse_args()
    db = lcf.Database(os.path.join(args.game_dir, "RPG_RT.ldb"))
    skin = ventana.skin(args.game_dir, db.system_name)
    inventario = {}
    for par in args.items.split(","):
        if par:
            n, _, c = par.partition(":")
            inventario[int(n)] = int(c or 1)
    if args.batalla is not None:
        import batalla
        grupo = [int(a) for a in args.grupo.split(",") if a]
        combate = batalla.Batalla(
            [batalla.actor_de(db, a) for a in grupo],
            [batalla.enemigo_de(db, e, n)
             for n, e in enumerate(db.troops[args.batalla].members)])
        for _ in range(args.turnos):
            if combate.resultado is not None:
                break
            vivo = next((n for n, e in enumerate(combate.enemigos) if e.vivo),
                        0)
            combate.jugar_turno([(batalla.ORDEN_ATACAR, vivo)]
                                * len(combate.vivos(combate.actores)))
        # La lista de ítems usables, con la misma regla que la ROM: ver
        # `batalla.item_usable_en_batalla`. `--items` trae el inventario.
        usables = [(n, c) for n, c in sorted(inventario.items())
                   if c > 0 and batalla.item_usable_en_batalla(db.items[n])]
        escena_img = None
        if args.fondo:
            import escena
            info = escena.convertir(db, args.batalla, args.fondo,
                                    args.game_dir)
            escena_img = escena.render(info) if info else None
        pantalla_batalla(db, combate, args.modo, args.actor, args.orden,
                         args.blanco, items=usables,
                         item=args.item).render(skin, db.font_id,
                                                escena_img).save(args.output)
        print("batalla %d sobre %r -> %s"
              % (args.batalla, args.fondo, args.output))
        return
    if args.tienda is not None:
        tipo, juego, lista = args.tienda.split(":")
        vende = [int(x) for x in lista.split(",") if x]
        equipos = [list(db.actors[int(a)].initial_equipment)
                   for a in args.grupo.split(",") if a]
        pantalla_tienda(db, int(tipo), int(juego), vende, args.oro,
                        inventario, equipos, args.modo, args.elegido,
                        args.arriba, args.cuantos, args.resaludo).render(
            skin, db.font_id).save(args.output)
        print("tienda -> %s" % args.output)
        return
    equipo = ([int(x) for x in args.puesto.split(",")] if args.puesto
              else list(db.actors[args.equipo].initial_equipment))
    pantalla_equipo(db, args.equipo, equipo, inventario, args.ranura,
                    args.eligiendo, args.elegido,
                    args.arriba).render(skin, db.font_id).save(args.output)
    print("equipo de %d -> %s" % (args.equipo, args.output))


if __name__ == "__main__":
    main()

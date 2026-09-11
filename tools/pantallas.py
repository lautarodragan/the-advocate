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


def parametros(db, actor, equipo):
    """Ataque, defensa, espíritu y agilidad: los del nivel más lo que suma el
    equipo, topados en [1, 999] como `Game_Actor::GetAtk` y sus hermanas."""
    params = db.actors[actor].params
    base = [params.get(k, [0])[titulo.NIVEL - 1]
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
    args = parser.parse_args()
    db = lcf.Database(os.path.join(args.game_dir, "RPG_RT.ldb"))
    skin = ventana.skin(args.game_dir, db.system_name)
    inventario = {}
    for par in args.items.split(","):
        if par:
            n, _, c = par.partition(":")
            inventario[int(n)] = int(c or 1)
    equipo = ([int(x) for x in args.puesto.split(",")] if args.puesto
              else list(db.actors[args.equipo].initial_equipment))
    pantalla_equipo(db, args.equipo, equipo, inventario, args.ranura,
                    args.eligiendo, args.elegido,
                    args.arriba).render(skin, db.font_id).save(args.output)
    print("equipo de %d -> %s" % (args.equipo, args.output))


if __name__ == "__main__":
    main()

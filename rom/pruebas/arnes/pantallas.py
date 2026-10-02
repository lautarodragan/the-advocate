"""Las pantallas como las tiene que mostrar la consola, contra las que se
comparan las capturas: el menú, los ítems, la elección de actor, las
ranuras, el equipo, la tienda y End Game.

Las dibuja la etapa del conversor, `rm2k-snes-screens render`, con los
mismos bloques que sube la ROM y el mismo juego que lee el conversor. Hasta
el 2026-09-30 las dibujaba el modelo de Python —`menus.render_menu`,
`screens.shop_screen` y compañía—, que se fue cuando las pantallas pasaron
a Rust: dibujar con otro código que el que arma la ROM sería comparar contra
algo que no corre.

Lo que se le pasa es el estado del juego que la pantalla muestra, con los
nombres del pedido de la etapa; ver `render.rs` en `rm2k-snes-screens`.
"""

from port import screen_stage


def disposicion():
    """La geometría con que la etapa dibuja las pantallas, por nombre:
    `disposicion().ITEM_ROWS`."""
    return screen_stage.layout()


def menu(ranuras, grupo, oro, elegida=0, guardar=True, actores=None,
         hp=None, niveles=None, exps=None, eligiendo=None):
    """El menú de pausa con `grupo` y `oro`, el cursor en `elegida` y el
    permiso de guardar. `actores` son los que conoce la ROM —sin ellos, el
    grupo—; `hp`, `niveles` y `exps`, de actor a valor, los de la partida
    —sin ellos, los de arranque—. Con `eligiendo`, la fila del grupo con la
    barra, mientras se elige para quién es la orden."""
    return screen_stage.render(
        "menu", slots=ranuras, party=list(grupo), gold=oro, chosen=elegida,
        save_allowed=guardar, actors=actores, hp=hp or {},
        levels=niveles or {}, exps=exps or {},
        choosing=-1 if eligiendo is None else eligiendo)


def items(inventario, elegida=0, arriba=0, conocidos=None):
    """La pantalla de ítems: `inventario` de número a cuántos; `conocidos`,
    los que conoce la ROM —sin ellos, los del inventario—."""
    return screen_stage.render(
        "items", inventory=inventario, chosen=elegida, top=arriba,
        items=conocidos)


def objetivo(ranuras, grupo, elegida=0, actores=None, hp=None, item=None,
             cantidad=0):
    """La elección de actor: con `item`, la medicina que se usa y
    `cantidad` las que quedan. A quién equipar se elige en el menú: ver
    `menu(eligiendo=...)`."""
    return screen_stage.render(
        "target", slots=ranuras, party=list(grupo), chosen=elegida,
        actors=actores, hp=hp or {}, item=item, amount=cantidad)


def pantalla_de_ranuras(ranuras, llenas, elegida, modo=0, grupos=None,
                        niveles=None):
    """Las ranuras: `llenas`, una por ranura; `modo`, 0 cargar y 1 guardar;
    `grupos`, de ranura al grupo guardado; `niveles`, de ranura al nivel que
    tenía el líder."""
    return screen_stage.render(
        "slots", slots=ranuras, full=[bool(x) for x in llenas],
        chosen=elegida, mode=modo, parties=grupos or {},
        levels=niveles or {})


def equipo(actor, puesto, inventario, ranura, eligiendo=False, elegida=0,
           arriba=0, conocidos=None):
    """El equipo del actor: con `eligiendo`, la lista de la ranura con el
    cursor en `elegida` y la primera visible en `arriba`."""
    return screen_stage.render(
        "equipment", actor=actor, equipment=list(puesto),
        inventory=inventario, slot=ranura, choosing=eligiendo,
        chosen=elegida, top=arriba, items=conocidos)


def tienda(tipo, juego_de_terminos, vende, oro, inventario, equipo_grupo,
           modo, elegida=0, arriba=0, cantidad=1, resaludo=False,
           conocidos=None):
    """La tienda de `OpenShop` en `modo` —`disposicion().TI_MAIN` y
    compañía—."""
    return screen_stage.render(
        "shop", kind=tipo, term_set=juego_de_terminos, sells=list(vende),
        gold=oro, inventory=inventario,
        party_equipment=[list(e) for e in equipo_grupo], mode=modo,
        chosen=elegida, top=arriba, count=cantidad, regreeting=resaludo,
        items=conocidos)


def fin(elegida):
    """End Game con el cursor en `elegida`: 0 sí, 1 no."""
    return screen_stage.render("end_game", chosen=elegida)


def equipar(puesto, inventario, ranura, item):
    """`Game_Actor::ChangeEquipment` sobre `puesto` e `inventario`, que
    cambia: lo que tenía vuelve al inventario y lo nuevo sale de ahí. Un arma
    de dos manos saca el escudo, y un escudo saca el arma de dos manos.
    `item` en 0 es desequipar la ranura.

    Es la regla que corre la ROM, y se la pide a la etapa —`rm2k-snes-screens
    equip`, que es la de `rm2k-rules`— para saber qué esperar de la partida:
    hasta el 2026-10-02 estaba copiada acá.
    """
    nuevo, quedan = screen_stage.equip(puesto, inventario, ranura, item)
    puesto[:] = nuevo
    inventario.clear()
    inventario.update(quedan)

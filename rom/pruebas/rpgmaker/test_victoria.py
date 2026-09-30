"""Lo que la victoria da y cuenta: "N EXP", el oro, los ítems y una página por
cada actor que subió.

`ProcessSceneActionVictory` de `Scene_Battle_Rpg2k`: el primer mensaje es el
término de la victoria, la experiencia, el oro y un renglón por ítem que
soltaron los enemigos, de a cuatro renglones por página; después cada actor que subió
de nivel tiene la suya, con "<nombre> LEVEL <n> achieved!" y una línea por
habilidad aprendida. Acá van en los cuatro renglones del grupo —ver
`battle_victory.s`—.

No se compara contra una golden sino **contra el texto**: se lee el tilemap de
la pantalla, `text_buf`, y se traduce cada celda con la tabla de glifos del
cartucho. Así la prueba dice qué renglón está mal y con qué letras, y los
renglones esperados salen de `modelo.renglones`, que le pide a
`rm2k-snes-battle` el armado de `game_message_terms.cpp`: lo mismo con que el
conversor cobra que entren. Los niveles y las habilidades salen de
`experience.add_exp` y del LDB, no de acá.
"""

from port import experience

from batalla import (ARDEN, GRUPO, Pelea, en_el_droide, paginas, poner_exp,
                     primera_pagina)
import datos
import modelo

TROPA_DROIDE = 82
KERSH, CORE, MANTA = GRUPO


def ganar_hasta_el_fin(una, grupo):
    """Pelea atacando hasta que la pantalla queda en la del fin, **sin
    cerrarla**. Cuántos órdenes da cada turno lo dice la RAM: los actores del
    grupo que siguen en pie."""
    pelea = Pelea(una).abrir()
    for _ in range(30):
        if pelea.modo() == "END":
            return pelea
        vivos = sum(1 for k in range(len(grupo))
                    if pelea.hp_del_combatiente(k) > 0)
        pelea.turno(vivos)
    raise AssertionError("la pelea no terminó")


def pagina_de_nivel(base, actor, antes, despues):
    """El renglón del nivel y los de las habilidades que enseñan los niveles
    que pasó, nivel por nivel, en el orden de la tabla del LDB."""
    habilidades = [s for nivel in range(antes + 1, despues + 1)
                   for n, s in base.actors[actor].skills if n == nivel]
    return [r for rs in modelo.renglones(
        ("level", actor, despues), *[("skill", h) for h in habilidades])
        for r in rs]


def test_la_victoria_dice_la_experiencia_y_se_cierra(partida):
    """El grupo de la intro en sus niveles del LDB: el droide no alcanza para
    que nadie suba, así que hay una sola página —la victoria partida en dos
    renglones y "90 EXP"— y la A que sigue cierra la pelea.

    El término del ABL son 36 letras y la ventana tiene 31: sin partirlo se
    pasaba al renglón de abajo, cortado a la mitad de "victory!"."""
    una = en_el_droide(partida)
    base = datos.base()
    ganada = experience.troop_exp(base, TROPA_DROIDE)
    for actor in GRUPO:
        nivel = experience.initial_level(base.actors[actor])
        exp = experience.initial_exp(base.actors[actor])
        assert experience.add_exp(base.actors[actor], nivel, exp, ganada)[0] \
            == nivel, "el caso quiere que nadie suba: el %d sube" % actor
    pelea = ganar_hasta_el_fin(una, GRUPO)
    assert paginas(una, pelea) == [primera_pagina(ganada)]


def test_el_que_sube_tiene_su_pagina_y_el_que_no_no(partida):
    """Arden sube del 3 al 6 y aprende una habilidad en cada nivel; Kersh
    queda en el suyo; Manta sube uno y no aprende nada. Las páginas son la de
    la victoria, la de Arden y la de Manta, en el orden del grupo, y **ninguna
    de Kersh**.

    Lurk In Shadows, la del 5, es de las que la pelea no sabe ofrecer —no
    está en la lista de habilidades de la pantalla— y la victoria la cuenta
    igual, que es lo que hace RM2k."""
    una = en_el_droide(partida)
    base = datos.base()
    ganada = experience.troop_exp(base, TROPA_DROIDE)
    grupo = (ARDEN, KERSH, MANTA)
    una.poner_grupo(*grupo)
    lista = experience.exp_list(base.actors[ARDEN])
    exp_arden = lista[5] - 50
    poner_exp(una, ARDEN, exp_arden, 3)
    nivel_m = experience.initial_level(base.actors[MANTA])
    exp_m = experience.exp_list(base.actors[MANTA])[nivel_m] - 10
    poner_exp(una, MANTA, exp_m, nivel_m)
    assert experience.add_exp(base.actors[ARDEN], 3, exp_arden, ganada)[0] == 6
    assert experience.add_exp(base.actors[MANTA], nivel_m, exp_m,
                              ganada)[0] == nivel_m + 1
    nivel_k = experience.initial_level(base.actors[KERSH])
    assert experience.add_exp(base.actors[KERSH], nivel_k,
                              experience.initial_exp(base.actors[KERSH]),
                              ganada)[0] == nivel_k
    pelea = ganar_hasta_el_fin(una, grupo)
    vivos = {grupo[k] for k in range(len(grupo))
             if pelea.hp_del_combatiente(k) > 0}
    assert vivos == set(grupo), "el caso quiere a los tres en pie: %r" % vivos
    assert paginas(una, pelea) == [
        primera_pagina(ganada),
        pagina_de_nivel(base, ARDEN, 3, 6),
        pagina_de_nivel(base, MANTA, nivel_m, nivel_m + 1),
    ]


def test_las_habilidades_que_no_entran_siguen_en_otra_pagina(partida):
    """Arden del 3 al 9: seis habilidades, y la ventana tiene cuatro
    renglones. La primera página lleva el nivel y tres; la segunda, las otras
    tres, sin repetir el nivel. Es lo que hace la ventana de RM2k con un
    mensaje de más de cuatro renglones."""
    una = en_el_droide(partida)
    base = datos.base()
    ganada = experience.troop_exp(base, TROPA_DROIDE)
    grupo = (ARDEN, KERSH)
    una.poner_grupo(*grupo)
    exp_arden = experience.exp_list(base.actors[ARDEN])[8] - 50
    poner_exp(una, ARDEN, exp_arden, 3)
    assert experience.add_exp(base.actors[ARDEN], 3, exp_arden, ganada)[0] == 9
    esperada = pagina_de_nivel(base, ARDEN, 3, 9)
    assert len(esperada) == 7, "el caso quiere seis habilidades: %r" % esperada
    pelea = ganar_hasta_el_fin(una, grupo)
    assert pelea.hp_del_combatiente(0) > 0, "Arden tiene que quedar en pie"
    assert paginas(una, pelea) == [
        primera_pagina(ganada), esperada[:4], esperada[4:]]


# --- el oro y los ítems -------------------------------------------------------
#
# Tres Crazed Marauder, que dan 95 de oro cada uno y sueltan una Healing
# Draught-HP con chance 35: tres tiros de botín, uno por enemigo. **La semilla
# la elige el modelo**: se escribe en `BA_SEED` al abrir la pelea, y es la
# primera con la que `battle.Battle` gana sin que caiga nadie y alguno suelta
# su ítem y otro no. Así la prueba pasa por los dos lados del tiro y no depende
# de que la semilla de fábrica caiga en uno. Los tres enemigos arrancan con 1
# HP, en la ROM y en el modelo, para que la pelea dure lo que dura un golpe.

TROPA_MERODEADORES = 222
MERODEADOR = 144
HEALING_DRAUGHT = 257


def modelo_de_los_merodeadores(base, semilla):
    esperado = modelo.Battle(
        [modelo.actor_of(a) for a in GRUPO],
        [modelo.enemy_of(e, n)
         for n, e in enumerate(base.troops[TROPA_MERODEADORES].members)],
        semilla)
    for enemigo in esperado.enemies:
        enemigo.hp = 1
    return esperado


def jugar_el_modelo(esperado, tope=10):
    for _ in range(tope):
        vivos = len(esperado.living(esperado.actors))
        if esperado.play_turn([(modelo.COMMAND_ATTACK, 0)] * vivos) is not None:
            return esperado
    return esperado


def semilla_con_botin_a_medias(base):
    """La primera semilla con la que el grupo gana entero y los tres tiros no
    salen todos iguales."""
    for semilla in range(1, 4000):
        esperado = jugar_el_modelo(modelo_de_los_merodeadores(base, semilla))
        if (esperado.result == modelo.VICTORY
                and len(esperado.living(esperado.actors)) == len(GRUPO)
                and 0 < len(esperado.drops) < 3):
            return semilla, esperado
    raise AssertionError("ninguna semilla deja el botín a medias")


def test_la_tropa_del_botin_es_la_que_se_espera():
    """Lo que las pruebas de abajo suponen del LDB."""
    base = datos.base()
    assert base.troops[TROPA_MERODEADORES].members == [MERODEADOR] * 3
    e = base.enemies[MERODEADOR]
    assert (e.gold, e.drop_id, e.drop_prob) == (95, HEALING_DRAUGHT, 35)
    assert modelo.troop_gold(TROPA_MERODEADORES) == 285


def a_los_merodeadores(partida, semilla, tope=600):
    """La página del caso hasta que abre la pelea, y en el primer pedido de
    órdenes la semilla y el 1 HP de cada enemigo."""
    una = partida(caso="pelea-222")
    for _ in range(tope):
        una.consola.run(1)
        if una.menu_abierto():
            break
    else:
        raise AssertionError("la página no abrió la pelea")
    pelea = Pelea(una).esperar("COMMAND")
    una.consola.write_ram(una.simbolos["BA_SEED"],
                          [semilla & 0xFF, semilla >> 8])
    g = una.simbolos["BA_PARTY_MAX"]
    for k in range(3):
        una.consola.write_ram(
            una.simbolos["BA_ONE"] + (g + k) * una.simbolos["BA_BYTES"],
            [1, 0])
    return una, pelea


def test_la_victoria_da_el_oro_y_los_items_y_los_cuenta(partida):
    """`ProcessSceneActionVictory`: el oro de los tres va al grupo, cada ítem
    que salió suma uno, y la primera página del mensaje —la victoria, la
    experiencia y el oro— sigue en otra con un renglón por ítem, en el orden
    de la tropa. El número de ítems y cuáles lo dice el modelo, que tira el
    botín con el mismo azar después del último golpe."""
    base = datos.base()
    semilla, esperado = semilla_con_botin_a_medias(base)
    una, pelea = a_los_merodeadores(partida, semilla)
    oro_antes = una.oro()
    items_antes = una.item(HEALING_DRAUGHT)
    for _ in range(10):
        if pelea.modo() == "END":
            break
        vivos = sum(1 for k in range(len(GRUPO))
                    if pelea.hp_del_combatiente(k) > 0)
        pelea.turno(vivos)
    assert pelea.modo() == "END"
    assert pelea.byte("BA_RESULT") == modelo.VICTORY
    assert una.oro() == oro_antes + 285
    assert una.item(HEALING_DRAUGHT) == items_antes + len(esperado.drops), \
        "el modelo soltó %d ítems con la semilla %d" % (len(esperado.drops),
                                                        semilla)
    ganada = experience.troop_exp(base, TROPA_MERODEADORES)
    vistas = paginas(una, pelea)
    assert vistas[:2] == [
        primera_pagina(ganada) + [modelo.renglon_de_oro(285)],
        [modelo.renglon_de_item(i) for i in esperado.drops],
    ]


def test_el_item_que_sale_no_pasa_del_tope(partida):
    """`Game_Party::AddItem` topa en 99: con 99 en el inventario el ítem se
    cuenta en la página igual, y el inventario queda en 99."""
    base = datos.base()
    semilla, esperado = semilla_con_botin_a_medias(base)
    una, pelea = a_los_merodeadores(partida, semilla)
    tope = una.simbolos["ITEM_MAX"]
    una.consola.write_ram(una.simbolos["FAR_ITEMS"] + HEALING_DRAUGHT,
                          [tope])
    for _ in range(10):
        if pelea.modo() == "END":
            break
        pelea.turno(len(GRUPO))
    assert pelea.modo() == "END"
    assert esperado.drops
    assert una.item(HEALING_DRAUGHT) == tope
    assert pelea.byte("BA_DROP_N") == len(esperado.drops)

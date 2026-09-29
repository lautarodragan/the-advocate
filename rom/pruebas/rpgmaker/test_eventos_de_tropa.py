"""Las páginas de tropa que miran el turno y los HP, los enemigos ocultos y los
comandos que las peleas de `release` piden: lo de
`workflow/tasks/*/eventos-de-tropa-de-release.md`.

Tres peleas del juego, cada una con su caso:

* **el Rat King** (tropa 97, `pelea-97`): empieza solo, con sus dos ratas
  ocultas, y las llama con dos páginas **por HP del enemigo 0** —el 60% y el
  30%— que hacen `ShowHiddenMonster`. Se juega turno por turno contra
  `battle.Battle` con las páginas del LDB, que dice en qué turno aparece cada
  una y con qué HP queda cada uno;
* **los agentes** (tropa 102, `pelea-102`): una página de **turno 1** con el
  `PlaySound`, la sacudida y "The Captain has taken off in the ship!";
* **los Lazer Teeth** (tropa 86, `pelea-86`): una página de turno **con
  múltiplo** —base 1, cada 3— y los HP de Talan.

Y `pelea-97-sin-ratas`, que prende antes los dos switches con que las páginas
del Rat King se cierran, así que las ratas no aparecen nunca: es lo que mide
que un oculto no se puede elegir de blanco ni cuenta para ganar, ni da su
experiencia ni su oro.

**Lo que se espera sale del LDB**, no se escribe a mano: las condiciones y
los mensajes de cada página, con un recorrido que no comparte nada con el
compilador.
"""

from port import battle as modelo
from port import events
from port import rules

from batalla import (Pelea, mensaje_en_pantalla, modelo_de, paginas,
                     primera_pagina)
from consola import en_la_rom
import datos

KERSH, TALAN, AG7 = 11, 14, 18
KING_RAT, GIANT_RAT = 56, 64
TROPA_RAT_KING, TROPA_AGENTES, TROPA_LAZER = 97, 102, 86


def a_la_pelea(una, tope=600):
    for _ in range(tope):
        una.consola.run(1)
        if una.menu_abierto():
            return Pelea(una).esperar("ORDEN")
    raise AssertionError("la página no abrió la pelea")


def flags(una, k):
    s = una.simbolos
    return una.consola.ram(s["BA_UNO"] + k * s["BA_BYTES"] + s["BA_FLAGS"],
                           1)[0]


def ocultos_de_la_rom(una, cuantos):
    g = una.simbolos["BA_GRUPO_MAX"]
    return [bool(flags(una, g + k) & una.simbolos["BAF_OCULTO"])
            for k in range(cuantos)]


def dibujados(una):
    return una.consola.ram(una.simbolos["ESC_VIS"], 1)[0]


def pintado(una):
    """Cuántos bytes de la escena compuesta difieren del fondo limpio: los dos
    búferes de 32 KB del banco $7F —`ESC_ESCENA` y `ESC_LIMPIO`—. Es lo que
    tapan los battlers que están dibujados, **en los pixeles** y no en el bit
    de `ESC_VIS`, que podría decir una cosa y la escena otra."""
    limpio = una.consola.ram(una.simbolos["ESC_LIMPIO"] & 0x1FFFF, 0x8000)
    escena = una.consola.ram(una.simbolos["ESC_ESCENA"] & 0x1FFFF, 0x8000)
    return sum(1 for a, b in zip(limpio, escena) if a != b)


def lo_que_dicen(pagina):
    """Los mensajes de una página, cada uno con sus renglones."""
    mensajes = []
    for cmd in pagina.commands:
        if cmd.code == events.SHOW_MESSAGE:
            mensajes.append([cmd.string])
        elif cmd.code == events.SHOW_MESSAGE_2 and mensajes:
            mensajes[-1].append(cmd.string)
    return mensajes


def paginas_del_modelo(base, tropa):
    return [modelo.TroopPage(p) for p in base.troops[tropa].pages]


def turno_contando(una, pelea, ordenes, tope=3000, cada_cuadro=None):
    """Da las órdenes —una tupla de `Pelea.ordenar` por actor vivo— y pasa el
    turno hasta que vuelve a pedir órdenes o termina. Devuelve los mensajes de
    página que salieron, en orden, y el `BA_TURNO` con que salió cada uno.
    `cada_cuadro()` corre antes de cada cuadro del turno."""
    for orden in ordenes:
        pelea.ordenar(orden)
    vistos = []
    antes = 0xFFFF
    for n in range(tope):
        if cada_cuadro:
            cada_cuadro()
        if pelea.modo() in ("ORDEN", "FIN"):
            return vistos
        msg = pelea.palabra(una.simbolos["BA_PAG_MSG"])
        if pelea.modo() == "PAGINA" and msg != 0xFFFF and msg != antes:
            vistos.append((mensaje_en_pantalla(una, pelea),
                           pelea.palabra(una.simbolos["BA_TURNO"])))
        antes = msg if pelea.modo() == "PAGINA" else 0xFFFF
        una.consola.hold(*(("a",) if n % 6 < 2 else ()))
        una.consola.run(1)
    raise AssertionError("el turno no terminó")


# --- lo que las pruebas suponen del LDB -------------------------------------

def test_las_tropas_son_las_que_se_espera():
    """Si el juego cambiara, los casos de abajo pasarían por otro camino."""
    base = datos.base()
    rey = base.troops[TROPA_RAT_KING]
    assert rey.members == [KING_RAT, GIANT_RAT, GIANT_RAT]
    assert rey.hidden == [False, True, True]
    llaman = [p for p in rey.pages if p.active == ["enemy_hp"]]
    assert [(p.condition["enemy_id"], p.condition["enemy_hp_max"])
            for p in llaman] == [(0, 60), (0, 30)]
    # Y la del despegue, en el turno 1: `turn_b` es la base.
    despegue = [p for p in base.troops[TROPA_AGENTES].pages
                if any(c.code == events.SHAKE_SCREEN for c in p.commands)]
    assert len(despegue) == 1
    d = events.troop_trigger(despegue[0])
    assert (d.turn_base, d.turn_mult) == (1, 0)


def test_la_condicion_de_turno_es_la_de_easyrpg():
    """`CheckTurns(turno, base, múltiplo)`: sin múltiplo, justo en la base; con
    él, en la base y cada tantos. Y la página de los Lazer Teeth: base 1,
    cada 3."""
    assert [t for t in range(10) if modelo._turns(t, 1, 0)] == [1]
    assert [t for t in range(10) if modelo._turns(t, 0, 0)] == [0]
    assert [t for t in range(10) if modelo._turns(t, 1, 3)] == [1, 4, 7]
    assert [t for t in range(10) if modelo._turns(t, 0, 2)] == [0, 2, 4, 6, 8]
    base = datos.base()
    primera = base.troops[TROPA_LAZER].pages[0]
    d = events.troop_trigger(primera)
    assert (d.turn_base, d.turn_mult, d.actor) == (1, 3, TALAN)


# --- el Rat King --------------------------------------------------------------

def test_el_rat_king_empieza_solo_y_llama_a_sus_ratas(partida):
    """AG7 contra el Rat King, pegándole siempre al primero vivo. Después de
    cada turno, los HP de los cuatro y quién sigue oculto tienen que ser los
    del modelo, y la escena tiene que dibujar a los que están en la pelea y a
    nadie más. **El caso exige que las dos ratas aparezcan, en turnos
    distintos**, cada una con su mensaje, o no midió nada. AG7 y no Kersh
    porque Kersh deja al rey en menos del 30% de un golpe y las dos aparecen
    juntas."""
    base = datos.base()
    rey = base.troops[TROPA_RAT_KING]
    llaman = [lo_que_dicen(p)[0] for p in rey.pages if p.active == ["enemy_hp"]]
    una = partida(caso="pelea-97")
    pelea = a_la_pelea(una)
    esperado = modelo_de(base, (AG7,), TROPA_RAT_KING,
                         pages=paginas_del_modelo(base, TROPA_RAT_KING))
    esperado.start()
    g = una.simbolos["BA_GRUPO_MAX"]
    assert ocultos_de_la_rom(una, 3) == [False, True, True]
    una.consola.run(4)
    assert dibujados(una) == 0b001, "al empezar se dibuja sólo el rey"
    pintados = {0: pintado(una)}

    aparecio = {}
    dichos = []
    for turno in range(1, 20):
        if pelea.modo() == "FIN":
            break
        blanco = [i for i, e in enumerate(esperado.enemies) if e.alive][0]
        dichos += [m for m, _t in turno_contando(una, pelea, [("atacar", 0)])]
        esperado.play_turn([(modelo.COMMAND_ATTACK, blanco)])
        de_la_rom = ([pelea.hp_del_combatiente(0)]
                     + [pelea.hp_del_combatiente(g + k) for k in range(3)])
        del_modelo = [c.hp for c in esperado.actors + esperado.enemies]
        assert de_la_rom == del_modelo, (
            "turno %d: la consola dejó %r y el modelo %r"
            % (turno, de_la_rom, del_modelo))
        assert ocultos_de_la_rom(una, 3) == [e.hidden
                                             for e in esperado.enemies], (
            "turno %d: ocultos %r en la consola y %r en el modelo"
            % (turno, ocultos_de_la_rom(una, 3),
               [e.hidden for e in esperado.enemies]))
        for k in (1, 2):
            if not esperado.enemies[k].hidden:
                aparecio.setdefault(k, turno)
        una.consola.run(30)      # lo que tarda en subir un battler
        pintados[turno] = pintado(una)
        vivos = sum(1 << k for k, e in enumerate(esperado.enemies) if e.alive)
        if pelea.modo() != "FIN":
            assert dibujados(una) == vivos, (
                "turno %d: la escena dibuja $%02X y en la pelea están $%02X"
                % (turno, dibujados(una), vivos))
    assert set(aparecio) == {1, 2}, (
        "las dos ratas tenían que aparecer, y aparecieron %r" % aparecio)
    assert aparecio[1] < aparecio[2]
    # Y en los pixeles: cada rata que aparece tapa más fondo. Entre las dos
    # no muere nadie —el rey cae después—, así que sólo puede crecer.
    assert pintados[0] < pintados[aparecio[1]] < pintados[aparecio[2]], (
        "la escena no creció al aparecer las ratas: %r" % pintados)
    assert dichos == llaman, (
        "los mensajes de las páginas fueron %r y el LDB dice %r"
        % (dichos, llaman))


def test_un_oculto_no_es_blanco_ni_cuenta_para_ganar(partida):
    """Con los dos switches de las páginas del rey ya prendidos, las ratas no
    aparecen: el cursor de blanco no pasa del rey, matarlo gana la pelea, y
    la victoria da la experiencia y el oro **del rey solo** —`GetExp` y
    `GetMoney` suman los muertos—."""
    base = datos.base()
    term = rules.battle_terms(base)
    una = partida(caso="pelea-97-sin-ratas")
    pelea = a_la_pelea(una)
    assert pelea.switch(1005) and pelea.switch(1006)
    oro_antes = una.oro()
    # El cursor de blanco: abajo no llega a ninguna rata.
    for _ in range(5):
        pelea.tocar_cuadros("left")
    pelea.tocar_cuadros()
    pelea.esperar("BLANCO")
    primero = pelea.byte("BA_BLANCO")
    for _ in range(3):
        pelea.tocar_cuadros("down")
        assert pelea.byte("BA_BLANCO") == primero, \
            "el cursor de blanco llegó a una rata oculta"
    pelea.tocar_cuadros("b")
    pelea.esperar("ORDEN")
    for _ in range(30):
        if pelea.modo() == "FIN":
            break
        turno_contando(una, pelea, [("atacar", 0)])
    assert pelea.modo() == "FIN"
    assert pelea.byte("BA_RESULT") == modelo.VICTORY
    assert ocultos_de_la_rom(una, 3) == [False, True, True]
    esperado = modelo_de(base, (KERSH,), TROPA_RAT_KING)
    esperado.enemies[0].hp = 0
    assert esperado.experience() == base.enemies[KING_RAT].exp
    assert una.oro() == oro_antes + esperado.gold() == oro_antes + \
        base.enemies[KING_RAT].gold
    vistas = paginas(una, pelea)
    assert vistas[0][:len(primera_pagina(term, esperado.experience()))] \
        == primera_pagina(term, esperado.experience())


# --- los agentes ------------------------------------------------------------

def la_pagina_del_despegue(base):
    return [p for p in base.troops[TROPA_AGENTES].pages
            if any(c.code == events.SHAKE_SCREEN for c in p.commands)][0]


def test_el_despegue_sale_en_el_turno_uno_con_su_sacudida(partida):
    """La página de turno 1 de la pelea de los agentes: no corre al empezar,
    corre apenas se dan las órdenes del primer turno —antes de la primera
    acción—, sacude la escena los dos segundos que dice su `ShakeScreen`
    antes del mensaje, y no vuelve en el turno 2."""
    base = datos.base()
    despegue = la_pagina_del_despegue(base)
    una = partida(caso="pelea-102")
    pelea = a_la_pelea(una)
    assert pelea.palabra(una.simbolos["BA_PAG_MSG"]) == 0xFFFF, \
        "en el turno 0 no hay ningún mensaje de página"
    pelea.ordenar(("defender",))
    # La sacudida, antes del mensaje.
    sacudio = False
    for _ in range(400):
        if pelea.palabra(una.simbolos["BA_PAG_MSG"]) != 0xFFFF:
            break
        if una.palabra("sacudida_resta"):
            sacudio = True
        una.consola.run(1)
    assert sacudio, "el ShakeScreen de la página no sacudió"
    assert pelea.modo() == "PAGINA"
    assert pelea.palabra(una.simbolos["BA_TURNO"]) == 1
    hpmax = pelea.palabra(una.simbolos["BA_UNO"] + una.simbolos["BA_HPMAX"])
    assert pelea.hp_del_combatiente(0) == hpmax, \
        "la página corre antes de la primera acción: nadie le pegó a Kersh"
    assert mensaje_en_pantalla(una, pelea) == lo_que_dicen(despegue)[0]
    # Y en el turno 2, nada.
    for n in range(3000):
        if pelea.modo() in ("ORDEN", "FIN"):
            break
        una.consola.hold(*(("a",) if n % 6 < 2 else ()))
        una.consola.run(1)
    assert pelea.modo() == "ORDEN"
    assert turno_contando(una, pelea, [("defender",)]) == []


def test_el_despegue_pide_su_efecto(partida):
    """El `PlaySound` del despegue se compila: el primer opcode de la página
    es el OP_SOUND del `Thunder9` a 60 de volumen y 50 de tempo. Que suene
    depende de que esté en el paquete de la pelea —ver
    `se_troop_in_package` en snes_music.py—; lo que se cobra acá es que
    la página lo pida."""
    base = datos.base()
    una = partida(caso="pelea-102")
    s = una.simbolos
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()

    def palabra(simbolo, k):
        i = en_la_rom(s[simbolo]) + 2 * k
        return rom[i] | rom[i + 1] << 8

    tropas = [palabra("tropa_id", k) for k in range(80)]
    k = tropas.index(TROPA_AGENTES)
    ini, n = palabra("tropa_pag_ini", k), rom[en_la_rom(s["tropa_pag_n"]) + k]
    con_turno = [j for j in range(ini, ini + n)
                 if rom[en_la_rom(s["tpag_flags"]) + j] & s["TPAG_TURNO"]]
    codigos = []
    for j in con_turno:
        ofs = palabra("tpag_cod", j) - (s["tropa_codigo"] & 0xFFFF)
        codigos.append(rom[en_la_rom(s["tropa_codigo"]) + ofs:][:3])
    import json
    import os
    with open(os.path.join(os.path.dirname(una.sfc), "efectos.json")) as f:
        sonidos = [tuple(x) for x in json.load(f)["sonidos"]]
    p = [c for c in la_pagina_del_despegue(base).commands
         if c.code == events.PLAY_SOUND][0]
    trueno = sonidos.index((p.string, p.parameters[0], p.parameters[1],
                            p.parameters[2]))
    assert bytes([events.OP_SOUND, trueno & 0xFF, trueno >> 8]) in codigos


# --- el turno con múltiplo --------------------------------------------------

def test_la_pagina_de_los_lazer_teeth_vuelve_cada_tres_turnos(partida):
    """Kersh y Talan defendiéndose contra los cuatro Lazer Teeth, con los HP
    repuestos en cada cuadro: la página "It's not too late to surrender!"
    —turno base 1, cada 3, con Talan en 50% o más— sale en los turnos 1 y 4 y
    no en el 2, el 3 ni el 5; la del 30% o menos, nunca."""
    base = datos.base()
    primera = base.troops[TROPA_LAZER].pages[0]
    una = partida(caso="pelea-86")
    pelea = a_la_pelea(una)
    s = una.simbolos
    salieron = {}

    def llenos():
        for k in range(2):
            d = s["BA_UNO"] + k * s["BA_BYTES"]
            una.consola.write_ram(d + s["BA_HP"],
                                  una.consola.ram(d + s["BA_HPMAX"], 2))

    for turno in range(1, 6):
        llenos()
        vistos = turno_contando(una, pelea, [("defender",), ("defender",)],
                                cada_cuadro=llenos)
        salieron[turno] = [m for m, t in vistos]
        assert all(t == turno for _m, t in vistos)
        assert pelea.modo() == "ORDEN"
    esperados = {t: (lo_que_dicen(primera)
                     if modelo._turns(t, 1, 3) else [])
                 for t in range(1, 6)}
    assert salieron == esperados, salieron
    assert salieron[1] and salieron[4] and not salieron[2]
